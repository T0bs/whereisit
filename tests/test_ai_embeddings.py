"""M11 — embeddings cascade tests.

Covers the cosine helper, backfill, semantic + hybrid search, and the
REST surface (`/embeddings`, `/embeddings/backfill`). The embedding
provider is stubbed; no real Ollama calls.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.ai import GenerateResult, LLMError, LLMProvider
from backend.app.ai.embeddings import (
    backfill,
    cosine_similarity,
    reciprocal_rank_fusion,
    semantic_search,
)
from backend.app.database import SessionLocal
from backend.app.models import Embedding, Node


# Hybrid search uses FULLTEXT which only sees committed rows.
pytestmark = pytest.mark.committed_writes


# ---------------------------------------------------------------------------
# stub embed provider
# ---------------------------------------------------------------------------


class FakeEmbedProvider(LLMProvider):
    """Returns canned vectors per text. Records every call."""

    def __init__(
        self,
        *,
        name: str = "fake",
        embed_model: str = "fake-embed",
        table: dict[str, list[float]] | None = None,
        default: list[float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.embed_model = embed_model
        self.table = table or {}
        self.default = default or [0.0]
        self._error = error
        self.calls: list[list[str]] = []

    def generate(self, messages, *, system=None):
        return GenerateResult(text="ok")

    def tool_use_loop(self, messages, tools, on_tool_call, *, system=None, max_iterations=8):
        return GenerateResult(text="ok")

    def embed(self, texts):
        self.calls.append(list(texts))
        if self._error is not None:
            raise self._error
        return [self.table.get(t, list(self.default)) for t in texts]


def _patch_search_provider(monkeypatch, provider):
    monkeypatch.setattr("backend.app.routers.search.get_provider", lambda _: provider)


def _patch_embeddings_provider(monkeypatch, provider):
    monkeypatch.setattr("backend.app.routers.embeddings.get_provider", lambda _: provider)


# ---------------------------------------------------------------------------
# unit: cosine + RRF
# ---------------------------------------------------------------------------


def test_cosine_identity():
    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_dim_mismatch_returns_zero():
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_rrf_basic_fusion():
    # doc A: rank 1 in both → strongest
    # doc B: rank 2 in both → second
    # doc C: only appears in list 1
    fused = reciprocal_rank_fusion(["A", "B", "C"], ["A", "B"])
    ids = [doc for doc, _ in fused]
    assert ids[0] == "A"
    assert ids[1] == "B"
    assert ids[-1] == "C"


def test_rrf_handles_disjoint_lists():
    fused = reciprocal_rank_fusion(["A"], ["B"])
    assert {d for d, _ in fused} == {"A", "B"}
    # both at rank 1 → equal score → tied
    assert fused[0][1] == fused[1][1]


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


def _make(client, name, kind="item", **kw):
    body = {"name": name, "kind": kind}
    body.update(kw)
    return client.post("/nodes", json=body).json()


def test_backfill_embeds_every_node_first_time(client):
    a = _make(client, "Hammer", "tool")
    b = _make(client, "Drill", "tool")

    provider = FakeEmbedProvider(
        table={
            "Hammer": [1.0, 0.0, 0.0],
            "Drill": [0.0, 1.0, 0.0],
        }
    )

    db = SessionLocal()
    try:
        report = backfill(db, provider)
    finally:
        db.close()

    assert report.embedded == 2
    assert report.skipped_fresh == 0
    assert report.failed == 0
    assert report.total_seen == 2

    db = SessionLocal()
    try:
        rows = db.execute(select(Embedding).where(Embedding.model == "fake-embed")).scalars().all()
        by_node = {r.node_id: json.loads(r.vector) for r in rows}
    finally:
        db.close()
    assert by_node[a["id"]] == [1.0, 0.0, 0.0]
    assert by_node[b["id"]] == [0.0, 1.0, 0.0]


def test_backfill_skips_fresh_rows(client):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(default=[0.5, 0.5])

    db = SessionLocal()
    try:
        backfill(db, provider)
        # Second pass — nothing changed
        second = backfill(db, provider)
    finally:
        db.close()

    assert second.embedded == 0
    assert second.skipped_fresh == 1


def test_backfill_force_reembeds(client):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(default=[0.5, 0.5])

    db = SessionLocal()
    try:
        backfill(db, provider)
        provider.calls.clear()
        report = backfill(db, provider, force=True)
    finally:
        db.close()

    assert report.embedded == 1
    assert report.skipped_fresh == 0
    assert provider.calls  # provider was called the second time too


def test_backfill_picks_up_stale_after_update(client):
    node = _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(default=[1.0, 0.0])

    db = SessionLocal()
    try:
        backfill(db, provider)
        # Age the embedding row so the node's updated_at is later.
        emb = (
            db.execute(select(Embedding).where(Embedding.node_id == node["id"]))
            .scalars()
            .one()
        )
        emb.embedded_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        client.patch(f"/nodes/{node['id']}", json={"description": "updated"})
        provider.calls.clear()
        report = backfill(db, provider)
    finally:
        db.close()

    assert report.embedded == 1
    assert provider.calls == [["Hammer\nupdated"]]


def test_backfill_provider_failure_recorded(client):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(error=LLMError("ollama unavailable"))

    db = SessionLocal()
    try:
        report = backfill(db, provider)
    finally:
        db.close()

    assert report.embedded == 0
    assert report.failed == 1


def test_backfill_requires_embed_model(client):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider()
    provider.embed_model = None  # type: ignore[assignment]

    db = SessionLocal()
    try:
        with pytest.raises(LLMError, match="embed_model"):
            backfill(db, provider)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# semantic_search (function-level)
# ---------------------------------------------------------------------------


def test_semantic_search_ranks_by_cosine(client):
    a = _make(client, "Hammer", "tool")
    b = _make(client, "Drill", "tool")
    c = _make(client, "Sledgehammer", "tool")

    table = {
        "Hammer": [1.0, 0.0, 0.0],
        "Drill": [0.0, 1.0, 0.0],
        "Sledgehammer": [0.9, 0.1, 0.0],
        "hammer-like thing": [1.0, 0.0, 0.0],
    }
    provider = FakeEmbedProvider(table=table)

    db = SessionLocal()
    try:
        backfill(db, provider)
        ranked = semantic_search(db, provider, "hammer-like thing")
    finally:
        db.close()

    ids = [nid for nid, _ in ranked]
    assert ids[0] == a["id"]
    assert ids[1] == c["id"]
    assert ids[-1] == b["id"]


def test_semantic_search_empty_when_no_embeddings(client):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(table={"hammer": [1.0, 0.0]})

    db = SessionLocal()
    try:
        # No backfill — no rows in embeddings table.
        ranked = semantic_search(db, provider, "hammer")
    finally:
        db.close()

    assert ranked == []


def test_semantic_search_filters_by_kind(client):
    _make(client, "Cupboard", "cupboard", can_contain=True)
    hammer = _make(client, "Hammer", "tool")

    provider = FakeEmbedProvider(
        table={"Cupboard": [1.0, 0.0], "Hammer": [1.0, 0.0], "looking for storage": [1.0, 0.0]}
    )

    db = SessionLocal()
    try:
        backfill(db, provider)
        ranked = semantic_search(db, provider, "looking for storage", kind="tool")
    finally:
        db.close()

    ids = [nid for nid, _ in ranked]
    assert ids == [hammer["id"]]


# ---------------------------------------------------------------------------
# /search?mode=semantic|hybrid
# ---------------------------------------------------------------------------


def test_search_semantic_route(client, monkeypatch):
    a = _make(client, "Hammer", "tool")
    _make(client, "Drill", "tool")

    provider = FakeEmbedProvider(
        table={
            "Hammer": [1.0, 0.0],
            "Drill": [0.0, 1.0],
            "claw hammer": [1.0, 0.0],
        }
    )
    _patch_embeddings_provider(monkeypatch, provider)
    _patch_search_provider(monkeypatch, provider)

    client.post("/embeddings/backfill", json={"force": True})

    response = client.get("/search", params={"q": "claw hammer", "mode": "semantic"})
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows[0]["id"] == a["id"]
    assert rows[0]["match_reason"].startswith("cosine similarity")


def test_search_semantic_requires_q(client, monkeypatch):
    _patch_search_provider(monkeypatch, FakeEmbedProvider())
    response = client.get("/search", params={"mode": "semantic"})
    assert response.status_code == 400


def test_search_hybrid_uses_rrf(client, monkeypatch):
    a = _make(client, "Claw hammer", "tool")
    b = _make(client, "Sledgehammer", "tool")
    _make(client, "Drill", "tool")

    provider = FakeEmbedProvider(
        table={
            "Claw hammer": [1.0, 0.0, 0.0],
            "Sledgehammer": [0.9, 0.1, 0.0],
            "Drill": [0.0, 1.0, 0.0],
            "hammer": [1.0, 0.0, 0.0],
        }
    )
    _patch_embeddings_provider(monkeypatch, provider)
    _patch_search_provider(monkeypatch, provider)

    client.post("/embeddings/backfill", json={"force": True})

    response = client.get("/search", params={"q": "hammer", "mode": "hybrid"})
    assert response.status_code == 200, response.text
    rows = response.json()
    ids = [r["id"] for r in rows]
    # "Claw hammer" wins keyword (FULLTEXT) and ties semantic (vector 1.0) → top
    # "Sledgehammer" wins semantic by closeness but loses keyword (no "hammer" token? actually it does match)
    # both should appear ahead of Drill
    assert ids[0] == a["id"]
    assert b["id"] in ids
    assert all(r["match_reason"] == "RRF (keyword + semantic)" for r in rows)


def test_search_semantic_provider_unavailable_returns_503(client, monkeypatch):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(error=LLMError("ollama down"))
    # backfill writes some rows first so semantic_search has something to query
    provider2 = FakeEmbedProvider(table={"Hammer": [1.0]})
    _patch_embeddings_provider(monkeypatch, provider2)
    client.post("/embeddings/backfill", json={"force": True})

    _patch_search_provider(monkeypatch, provider)
    response = client.get("/search", params={"q": "hammer", "mode": "semantic"})
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /embeddings router
# ---------------------------------------------------------------------------


def test_embeddings_status_empty(client):
    response = client.get("/embeddings")
    assert response.status_code == 200
    assert response.json() == []


def test_embeddings_status_after_backfill(client, monkeypatch):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider(table={"Hammer": [1.0]})
    _patch_embeddings_provider(monkeypatch, provider)

    client.post("/embeddings/backfill", json={})

    response = client.get("/embeddings")
    assert response.status_code == 200
    body = response.json()
    assert body == [{"model": "fake-embed", "rows": 1}]


def test_embeddings_backfill_route(client, monkeypatch):
    _make(client, "Hammer", "tool")
    _make(client, "Drill", "tool")

    provider = FakeEmbedProvider(table={"Hammer": [1.0, 0.0], "Drill": [0.0, 1.0]})
    _patch_embeddings_provider(monkeypatch, provider)

    response = client.post("/embeddings/backfill", json={"batch_size": 16})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["embedded"] == 2
    assert body["model"] == "fake-embed"
    assert body["total_seen"] == 2


def test_embeddings_backfill_provider_error_503(client, monkeypatch):
    _make(client, "Hammer", "tool")
    provider = FakeEmbedProvider()
    provider.embed_model = None  # type: ignore[assignment]
    _patch_embeddings_provider(monkeypatch, provider)

    response = client.post("/embeddings/backfill", json={})
    assert response.status_code == 503


def test_embeddings_backfill_validation(client, monkeypatch):
    _patch_embeddings_provider(monkeypatch, FakeEmbedProvider())
    response = client.post("/embeddings/backfill", json={"batch_size": 999})
    assert response.status_code == 422

"""M13 — bulk-add + suggest/accept categories tests.

Stubs the LLM provider; no live Ollama traffic.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.ai import GenerateResult, LLMError, LLMProvider


pytestmark = pytest.mark.committed_writes


# ---------------------------------------------------------------------------
# stub provider — only the embed/generate surface we touch
# ---------------------------------------------------------------------------


class StubProvider(LLMProvider):
    def __init__(self, name="local", *, text="", error=None):
        self.name = name
        self._text = text
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages, *, system=None):
        self.calls.append({"messages": list(messages), "system": system})
        if self._error is not None:
            raise self._error
        return GenerateResult(text=self._text)

    def tool_use_loop(self, messages, tools, on_tool_call, *, system=None, max_iterations=8):
        return self.generate(messages, system=system)


def _patch_ai_provider(monkeypatch, *, local=None, cloud=None):
    def fake_get_provider(name):
        if name == "local":
            return local if local is not None else StubProvider("local", text="")
        if name == "anthropic":
            return cloud if cloud is not None else StubProvider("anthropic", text="")
        raise LLMError(f"unexpected: {name}")

    monkeypatch.setattr("backend.app.routers.ai.get_provider", fake_get_provider)


def _make_container(client, name, kind, *, parent_id=None, tags=()):
    body = {"name": name, "kind": kind, "can_contain": True}
    if parent_id is not None:
        body["parent_id"] = parent_id
    node = client.post("/nodes", json=body).json()
    for t in tags:
        client.post(f"/nodes/{node['id']}/tags", json={"name": t})
    return node


# ---------------------------------------------------------------------------
# /bulk-add
# ---------------------------------------------------------------------------


def test_bulk_add_creates_items_under_lazy_inbox(client):
    response = client.post("/bulk-add", json={"names": ["Hammer", "Drill"]})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["inbox_id"] > 0
    assert len(body["created"]) == 2
    assert {c["name"] for c in body["created"]} == {"Hammer", "Drill"}
    for c in body["created"]:
        assert c["kind"]["slug"] == "item"
        assert c["can_contain"] is False
        assert c["parent_id"] == body["inbox_id"]

    inbox = client.get(f"/nodes/{body['inbox_id']}").json()
    assert inbox["name"] == "Uncategorized"
    assert inbox["kind"]["slug"] == "inbox"
    assert inbox["can_contain"] is True
    assert inbox["parent_id"] is None


def test_bulk_add_reuses_existing_inbox(client):
    first = client.post("/bulk-add", json={"names": ["Hammer"]}).json()
    second = client.post("/bulk-add", json={"names": ["Drill"]}).json()
    assert first["inbox_id"] == second["inbox_id"]

    children = client.get(f"/nodes/{first['inbox_id']}/children").json()
    assert {c["name"] for c in children} == {"Hammer", "Drill"}


def test_bulk_add_trims_blanks_and_too_long(client):
    response = client.post(
        "/bulk-add",
        json={"names": ["  Hammer  ", "", "  ", "Drill", "x" * 256]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    names = [c["name"] for c in body["created"]]
    assert names == ["Hammer", "Drill"]
    assert body["skipped"] == ["x" * 256]


def test_bulk_add_all_blank_400(client):
    response = client.post("/bulk-add", json={"names": ["  ", ""]})
    assert response.status_code == 400


def test_bulk_add_validation_limits(client):
    r = client.post("/bulk-add", json={"names": []})
    assert r.status_code == 422
    r = client.post("/bulk-add", json={"names": ["x"] * 101})
    assert r.status_code == 422


def test_inbox_cannot_be_deleted(client):
    inbox_id = client.post("/bulk-add", json={"names": ["x"]}).json()["inbox_id"]
    # remove the only child so cascade isn't the blocker
    children = client.get(f"/nodes/{inbox_id}/children").json()
    for c in children:
        client.delete(f"/nodes/{c['id']}")
    response = client.delete(f"/nodes/{inbox_id}")
    assert response.status_code == 400
    assert "inbox" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /ai/suggest-categories
# ---------------------------------------------------------------------------


def test_suggest_categories_writes_suggested_parent_id(client, monkeypatch):
    """Heuristic-strong placement returns tier=heuristic without LLM call."""
    garage = _make_container(client, "Garage", "room")
    tool_drawer = _make_container(
        client,
        "Tool drawer",
        "drawer",
        parent_id=garage["id"],
        tags=["metal", "tool"],
    )

    bulk = client.post("/bulk-add", json={"names": ["Hammer"]}).json()
    hammer_id = bulk["created"][0]["id"]
    # give it tags so the heuristic latches on
    client.post(f"/nodes/{hammer_id}/tags", json={"name": "metal"})
    client.post(f"/nodes/{hammer_id}/tags", json={"name": "tool"})

    local = StubProvider("local", text="should not be called")
    _patch_ai_provider(monkeypatch, local=local)

    response = client.post(
        "/ai/suggest-categories", json={"node_ids": [hammer_id]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    s = body["suggestions"][0]
    assert s["node_id"] == hammer_id
    assert s["suggested_parent_id"] == tool_drawer["id"]
    assert s["suggested_parent_path"].startswith("Garage / Tool drawer")
    assert s["tier_used"] == "heuristic"
    # persisted on the node
    node = client.get(f"/nodes/{hammer_id}").json()
    assert node["suggested_parent_id"] == tool_drawer["id"]


def test_suggest_categories_excludes_inbox(client, monkeypatch):
    """The inbox itself is never offered as a category."""
    # Make the inbox the only can_contain=true node, then suggest.
    bulk = client.post("/bulk-add", json={"names": ["Hammer"]}).json()
    hammer_id = bulk["created"][0]["id"]

    local = StubProvider("local", text='{"picks": []}')
    _patch_ai_provider(monkeypatch, local=local)

    response = client.post(
        "/ai/suggest-categories", json={"node_ids": [hammer_id]}
    )
    assert response.status_code == 200, response.text
    s = response.json()["suggestions"][0]
    # No valid categories outside inbox → no suggestion
    assert s["suggested_parent_id"] is None
    node = client.get(f"/nodes/{hammer_id}").json()
    assert node["suggested_parent_id"] is None


def test_suggest_categories_missing_node_marked(client, monkeypatch):
    _patch_ai_provider(monkeypatch)
    response = client.post(
        "/ai/suggest-categories", json={"node_ids": [99999]}
    )
    assert response.status_code == 200
    s = response.json()["suggestions"][0]
    assert s["tier_used"] == "not_found"
    assert s["suggested_parent_id"] is None


def test_suggest_categories_cloud_gate(client, monkeypatch):
    monkeypatch.delenv("WHEREISIT_CLOUD_ENABLED", raising=False)
    _patch_ai_provider(monkeypatch)
    bulk = client.post("/bulk-add", json={"names": ["X"]}).json()
    nid = bulk["created"][0]["id"]
    r = client.post(
        "/ai/suggest-categories",
        json={"node_ids": [nid], "confirm_remote": True},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "cloud_disabled"


# ---------------------------------------------------------------------------
# /ai/accept-categories
# ---------------------------------------------------------------------------


def test_accept_categories_moves_node_and_clears_suggestion(client, monkeypatch):
    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Drawer", "drawer", parent_id=garage["id"])
    bulk = client.post("/bulk-add", json={"names": ["Hammer"]}).json()
    inbox_id = bulk["inbox_id"]
    hammer_id = bulk["created"][0]["id"]

    # pretend a prior suggest run wrote a value
    local = StubProvider("local", text="ignored")
    _patch_ai_provider(monkeypatch, local=local)
    # manually attach a tag so heuristic catches it later (not strictly needed here)
    client.post(
        "/ai/suggest-categories", json={"node_ids": [hammer_id]}
    )

    response = client.post(
        "/ai/accept-categories",
        json={"accepts": [{"node_id": hammer_id, "parent_id": drawer["id"]}]},
    )
    assert response.status_code == 200, response.text
    r = response.json()["results"][0]
    assert r["ok"] is True
    assert r["parent_id"] == drawer["id"]

    node = client.get(f"/nodes/{hammer_id}").json()
    assert node["parent_id"] == drawer["id"]
    assert node["suggested_parent_id"] is None
    # gone from inbox children
    children = client.get(f"/nodes/{inbox_id}/children").json()
    assert all(c["id"] != hammer_id for c in children)


def test_accept_categories_partial_failure(client, monkeypatch):
    """One bad row reports the error; the good rows still commit."""
    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Drawer", "drawer", parent_id=garage["id"])
    # a non-container; using it as parent must fail
    leaf = client.post("/nodes", json={"name": "Leaf", "kind": "tool"}).json()

    bulk = client.post("/bulk-add", json={"names": ["Hammer", "Drill"]}).json()
    h = bulk["created"][0]["id"]
    d = bulk["created"][1]["id"]

    response = client.post(
        "/ai/accept-categories",
        json={
            "accepts": [
                {"node_id": h, "parent_id": drawer["id"]},
                {"node_id": d, "parent_id": leaf["id"]},
            ]
        },
    )
    body = response.json()
    assert body["results"][0]["ok"] is True
    assert body["results"][1]["ok"] is False
    assert "does not accept children" in body["results"][1]["error"]

    # Hammer landed in drawer; Drill stayed in inbox
    hn = client.get(f"/nodes/{h}").json()
    dn = client.get(f"/nodes/{d}").json()
    assert hn["parent_id"] == drawer["id"]
    assert dn["parent_id"] == bulk["inbox_id"]


def test_accept_categories_rejects_cycle(client, monkeypatch):
    a = _make_container(client, "A", "cupboard")
    b = _make_container(client, "B", "drawer", parent_id=a["id"])

    response = client.post(
        "/ai/accept-categories",
        json={"accepts": [{"node_id": a["id"], "parent_id": b["id"]}]},
    )
    body = response.json()
    assert body["results"][0]["ok"] is False
    assert "cycle" in body["results"][0]["error"]


def test_accept_categories_validation(client):
    r = client.post("/ai/accept-categories", json={"accepts": []})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# placement.cascade exclude_ids
# ---------------------------------------------------------------------------


def test_cascade_exclude_ids_filters_candidates(client, monkeypatch):
    """The excluded container is never returned even if it would score top."""
    from backend.app.ai.placement import PlacementInput, cascade
    from backend.app.database import SessionLocal

    a = _make_container(client, "A", "cupboard", tags=["metal", "tool"])
    b = _make_container(client, "B", "drawer", tags=["metal", "tool"])

    local = StubProvider("local", text='{"picks": []}')

    db = SessionLocal()
    try:
        result = cascade(
            db=db,
            placement=PlacementInput(
                description="hammer", tags=["metal", "tool"], kind="tool"
            ),
            local_provider=local,
            exclude_ids={a["id"]},
        )
    finally:
        db.close()

    ids = [c.node.id for c in result.suggestions]
    assert a["id"] not in ids
    assert b["id"] in ids

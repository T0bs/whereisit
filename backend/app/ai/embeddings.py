"""Embeddings: backfill + semantic search + hybrid (RRF) fusion.

Vectors are JSON-serialized lists of floats stored in `embeddings.vector`.
Cosine similarity is computed in Python — fine for personal-scale (thousands
of nodes); swap to pgvector / Qdrant if you outgrow it.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Embedding, Kind, Node, Tag
from .provider import LLMError, LLMProvider

logger = logging.getLogger(__name__)


RRF_K = 60  # standard "smoothing" constant for Reciprocal Rank Fusion


@dataclass
class BackfillReport:
    model: str
    embedded: int
    skipped_fresh: int
    failed: int
    total_seen: int


# ---------------------------------------------------------------------------
# vector math
# ---------------------------------------------------------------------------


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _embedding_text(node: Node) -> str:
    parts = [node.name]
    if node.description:
        parts.append(node.description)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


def backfill(
    db: Session,
    provider: LLMProvider,
    *,
    model: Optional[str] = None,
    batch_size: int = 32,
    force: bool = False,
) -> BackfillReport:
    """Embed every node missing or stale for `model`. Returns a summary."""
    embed_model = model or provider.embed_model
    if not embed_model:
        raise LLMError(f"provider {provider.name!r} has no embed_model configured")

    nodes = db.execute(select(Node).order_by(Node.id)).scalars().unique().all()
    existing = {
        e.node_id: e
        for e in db.execute(
            select(Embedding).where(Embedding.model == embed_model)
        ).scalars()
    }

    stale_nodes: list[Node] = []
    skipped_fresh = 0
    for node in nodes:
        e = existing.get(node.id)
        if e is None:
            stale_nodes.append(node)
            continue
        if force or node.updated_at > e.embedded_at:
            stale_nodes.append(node)
        else:
            skipped_fresh += 1

    embedded = 0
    failed = 0
    for batch in _batches(stale_nodes, batch_size):
        texts = [_embedding_text(n) for n in batch]
        try:
            vectors = provider.embed(texts)
        except LLMError as exc:
            logger.warning("embeddings.backfill: embed failed: %s", exc)
            failed += len(batch)
            continue

        for node, vector in zip(batch, vectors):
            existing_row = existing.get(node.id)
            if existing_row is None:
                db.add(
                    Embedding(
                        node_id=node.id,
                        model=embed_model,
                        vector=json.dumps(vector),
                    )
                )
            else:
                existing_row.vector = json.dumps(vector)
                # embedded_at updates via session flush + onupdate? we don't
                # have onupdate on this column; bump explicitly.
                from datetime import datetime, timezone

                existing_row.embedded_at = datetime.now(timezone.utc)
            embedded += 1

    db.commit()
    return BackfillReport(
        model=embed_model,
        embedded=embedded,
        skipped_fresh=skipped_fresh,
        failed=failed,
        total_seen=len(nodes),
    )


def _batches(seq: list[Node], size: int) -> Iterable[list[Node]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ---------------------------------------------------------------------------
# semantic search
# ---------------------------------------------------------------------------


def semantic_search(
    db: Session,
    provider: LLMProvider,
    query: str,
    *,
    model: Optional[str] = None,
    parent: Optional[str] = None,
    kind: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
) -> list[tuple[int, float]]:
    """Return [(node_id, cosine_similarity)] ranked desc. Empty if no embeddings exist."""
    embed_model = model or provider.embed_model
    if not embed_model:
        raise LLMError(f"provider {provider.name!r} has no embed_model configured")

    if not query or not query.strip():
        return []

    candidate_ids = _filter_candidate_ids(db, parent=parent, kind=kind, tag=tag)
    if candidate_ids is not None and not candidate_ids:
        return []

    stmt = select(Embedding).where(Embedding.model == embed_model)
    if candidate_ids is not None:
        stmt = stmt.where(Embedding.node_id.in_(candidate_ids))
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return []

    query_vec = provider.embed([query])[0]

    scored: list[tuple[int, float]] = []
    for row in rows:
        try:
            vec = json.loads(row.vector)
        except (TypeError, ValueError):
            continue
        scored.append((row.node_id, cosine_similarity(query_vec, vec)))

    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored[:limit]


# ---------------------------------------------------------------------------
# hybrid (RRF)
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    *ranked_lists: list[int],
    k: int = RRF_K,
) -> list[tuple[int, float]]:
    """Combine multiple ranked id lists into one. Score = sum 1/(k+rank)."""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, node_id in enumerate(ranked, start=1):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank)
    fused = sorted(scores.items(), key=lambda t: (-t[1], t[0]))
    return fused


def _filter_candidate_ids(
    db: Session,
    *,
    parent: Optional[str],
    kind: Optional[str],
    tag: Optional[str],
) -> Optional[set[int]]:
    """Return the set of node_ids matching filters, or None if no filters applied."""
    if parent is None and kind is None and tag is None:
        return None

    stmt = select(Node.id)
    if parent is not None:
        if parent == "root":
            stmt = stmt.where(Node.parent_id.is_(None))
        else:
            try:
                pid = int(parent)
            except ValueError:
                return set()
            stmt = stmt.where(Node.parent_id == pid)
    if kind is not None:
        stmt = stmt.join(Node.kind).where(Kind.slug == kind)
    if tag is not None:
        stmt = stmt.join(Node.tags).where(Tag.name == tag)

    return {row[0] for row in db.execute(stmt).all()}

import re
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..ai import get_provider
from ..ai.embeddings import reciprocal_rank_fusion, semantic_search
from ..ai.provider import LLMError
from ..database import get_db
from ..models import Kind, Node, Tag
from ..schemas import KindRef, NodeSummary, SearchResult

router = APIRouter(tags=["search"])


SUPPORTED_MODES = {"keyword", "semantic", "hybrid"}

_FT_OPERATOR_STRIP = re.compile(r"[+\-<>~*\"()@]")


def _build_boolean_term(q: str) -> str:
    """Turn a user query into a MySQL FULLTEXT BOOLEAN MODE expression.

    Each whitespace-separated token becomes `+token*` — mandatory match with a
    trailing wildcard so partial words ('hamm' → 'hammer') hit. BOOLEAN MODE
    operators from user input are stripped so they can't change semantics.
    """
    cleaned = _FT_OPERATOR_STRIP.sub(" ", q)
    tokens = [t for t in cleaned.split() if t]
    return " ".join(f"+{t}*" for t in tokens)


def _fulltext_scores(db: Session, boolean_term: str) -> Dict[int, float]:
    """Run the MySQL FULLTEXT query and return {node_id: score}."""
    rows = db.execute(
        text(
            "SELECT id, "
            "MATCH(name, description) AGAINST(:search_term IN BOOLEAN MODE) "
            "AS score "
            "FROM nodes "
            "WHERE MATCH(name, description) "
            "AGAINST(:search_term IN BOOLEAN MODE)"
        ),
        {"search_term": boolean_term},
    ).all()
    return {row[0]: float(row[1]) for row in rows}


def _batch_paths(db: Session, leaf_ids: List[int]) -> Dict[int, List[Node]]:
    """Compute ancestor chains for many leaves in O(depth) round-trips."""
    if not leaf_ids:
        return {}
    needed: Set[int] = set(leaf_ids)
    frontier: Set[int] = set(leaf_ids)
    while frontier:
        parents = db.execute(
            select(Node.id, Node.parent_id).where(Node.id.in_(frontier))
        ).all()
        next_frontier: Set[int] = set()
        for _, pid in parents:
            if pid is not None and pid not in needed:
                needed.add(pid)
                next_frontier.add(pid)
        frontier = next_frontier

    nodes_by_id: Dict[int, Node] = {
        n.id: n
        for n in db.execute(select(Node).where(Node.id.in_(needed))).scalars()
    }

    paths: Dict[int, List[Node]] = {}
    for leaf_id in leaf_ids:
        chain: List[Node] = []
        current: Optional[int] = leaf_id
        seen: Set[int] = set()
        while current is not None and current not in seen:
            seen.add(current)
            node = nodes_by_id.get(current)
            if node is None:
                break
            chain.append(node)
            current = node.parent_id
        chain.reverse()
        paths[leaf_id] = chain
    return paths


@router.get("/search", response_model=List[SearchResult])
def search(
    q: Optional[str] = Query(
        None, description="Full-text query over node name + description."
    ),
    parent: Optional[str] = Query(
        None, description="Confine to a subtree: 'root' or an integer node id."
    ),
    kind: Optional[str] = Query(None, description="Filter by kind slug."),
    tag: Optional[str] = Query(None, description="Filter by tag name."),
    mode: str = Query(
        "keyword",
        description=(
            "Search mode. 'keyword' uses MySQL FULLTEXT. "
            "'semantic' / 'hybrid' are reserved for M11."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if mode not in SUPPORTED_MODES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"mode {mode!r} not yet supported "
            f"(available: {sorted(SUPPORTED_MODES)})",
        )

    if mode in ("semantic", "hybrid"):
        return _search_with_embeddings(
            db=db,
            mode=mode,
            q=q,
            parent=parent,
            kind=kind,
            tag=tag,
            limit=limit,
            offset=offset,
        )

    use_fulltext = q is not None and q.strip() != ""
    scores: Dict[int, float] = {}
    if use_fulltext:
        boolean_term = _build_boolean_term(q)
        if not boolean_term:
            # Query was all whitespace/operators after cleaning.
            return []
        scores = _fulltext_scores(db, boolean_term)
        if not scores:
            return []

    stmt = select(Node)
    if use_fulltext:
        stmt = stmt.where(Node.id.in_(scores.keys()))

    if parent is not None:
        if parent == "root":
            stmt = stmt.where(Node.parent_id.is_(None))
        else:
            try:
                pid = int(parent)
            except ValueError:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "parent must be 'root' or an integer node id",
                )
            stmt = stmt.where(Node.parent_id == pid)

    if kind is not None:
        stmt = stmt.join(Node.kind).where(Kind.slug == kind)

    if tag is not None:
        stmt = stmt.join(Node.tags).where(Tag.name == tag)

    matches: List[Node] = list(db.execute(stmt).scalars().unique().all())

    if use_fulltext:
        matches.sort(key=lambda n: (-scores.get(n.id, 0.0), n.id))
    else:
        matches.sort(key=lambda n: (n.created_at, n.id), reverse=False)
        matches = list(reversed(matches))

    page = matches[offset : offset + limit]
    leaf_ids = [n.id for n in page]
    paths = _batch_paths(db, leaf_ids)

    return [
        SearchResult(
            id=node.id,
            name=node.name,
            kind=KindRef.model_validate(node.kind),
            parent_id=node.parent_id,
            can_contain=node.can_contain,
            quantity=node.quantity,
            score=scores.get(node.id) if use_fulltext else None,
            match_reason=(
                "fulltext name+description match" if use_fulltext else None
            ),
            path=[NodeSummary.model_validate(n) for n in paths.get(node.id, [])],
        )
        for node in page
    ]


# ---------- semantic / hybrid (M11) ----------


def _search_with_embeddings(
    *,
    db: Session,
    mode: str,
    q: Optional[str],
    parent: Optional[str],
    kind: Optional[str],
    tag: Optional[str],
    limit: int,
    offset: int,
) -> List[SearchResult]:
    if not q or not q.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"mode={mode} requires a non-empty q",
        )

    provider = get_provider("local")
    try:
        semantic = semantic_search(
            db=db,
            provider=provider,
            query=q,
            parent=parent,
            kind=kind,
            tag=tag,
            limit=max(limit + offset, 200),
        )
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"embedding provider unavailable: {exc}",
        )

    if mode == "semantic":
        ranked: List[tuple[int, float]] = semantic
        reason = f"cosine similarity ({provider.embed_model})"
    else:
        boolean_term = _build_boolean_term(q)
        keyword_scores: Dict[int, float] = (
            _fulltext_scores(db, boolean_term) if boolean_term else {}
        )
        candidate_ids = _filtered_keyword_ids(
            db, keyword_scores, parent=parent, kind=kind, tag=tag
        )
        keyword_ranked = sorted(
            candidate_ids, key=lambda nid: (-keyword_scores.get(nid, 0.0), nid)
        )
        semantic_ranked = [nid for nid, _ in semantic]
        ranked = reciprocal_rank_fusion(keyword_ranked, semantic_ranked)
        reason = "RRF (keyword + semantic)"

    page = ranked[offset : offset + limit]
    if not page:
        return []

    node_ids = [nid for nid, _ in page]
    nodes_by_id = {
        n.id: n
        for n in db.execute(select(Node).where(Node.id.in_(node_ids))).scalars().all()
    }
    paths = _batch_paths(db, node_ids)

    results: List[SearchResult] = []
    for node_id, score in page:
        node = nodes_by_id.get(node_id)
        if node is None:
            continue  # row referenced by embedding but node since deleted
        results.append(
            SearchResult(
                id=node.id,
                name=node.name,
                kind=KindRef.model_validate(node.kind),
                parent_id=node.parent_id,
                can_contain=node.can_contain,
                quantity=node.quantity,
                score=score,
                match_reason=reason,
                path=[NodeSummary.model_validate(n) for n in paths.get(node.id, [])],
            )
        )
    return results


def _filtered_keyword_ids(
    db: Session,
    scores: Dict[int, float],
    *,
    parent: Optional[str],
    kind: Optional[str],
    tag: Optional[str],
) -> Set[int]:
    if not scores:
        return set()
    stmt = select(Node.id).where(Node.id.in_(scores.keys()))
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

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Node
from .provider import LLMError, LLMProvider, Message

logger = logging.getLogger(__name__)


# How much affinity each "thing" kind has for being placed inside each container kind.
# Scores are in [0, 1]. Missing entries default to 0.
KIND_AFFINITY: dict[str, dict[str, float]] = {
    "tool": {"cupboard": 0.9, "drawer": 0.8, "box": 0.7, "shelf": 0.5, "bag": 0.3},
    "item": {"box": 0.7, "drawer": 0.7, "shelf": 0.6, "cupboard": 0.6, "bag": 0.4},
    "consumable": {"box": 0.9, "bag": 0.8, "cupboard": 0.7, "drawer": 0.5, "shelf": 0.4},
    "room": {"building": 1.0},
    "cupboard": {"room": 0.8, "building": 0.4},
    "shelf": {"room": 0.7, "cupboard": 0.5},
    "drawer": {"cupboard": 0.9, "room": 0.3},
    "box": {"shelf": 0.7, "drawer": 0.6, "cupboard": 0.5, "room": 0.4},
    "bag": {"cupboard": 0.7, "shelf": 0.5, "drawer": 0.5},
}

TAG_WEIGHT = 0.6
KIND_WEIGHT = 0.4
NEIGHBOR_SCALE = 1.5  # see score_containers for the rationale
HIGH_CONFIDENCE = 0.6
LLM_CANDIDATE_CAP = 50


# Tokens we strip when comparing item names for "neighbour" similarity (M14).
# Tiny English-only stopword set — we're matching short product names, not prose.
_NAME_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "with", "for", "and", "or", "to", "in", "on", "at",
        "my", "your", "our", "this", "that", "these", "those",
        "is", "are", "was", "were", "be",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class PlacementInput:
    description: str
    tags: list[str] = field(default_factory=list)
    kind: Optional[str] = None
    max_suggestions: int = 5


@dataclass
class Candidate:
    node: Node
    score: float
    reason: str = ""


@dataclass
class SuggestionResult:
    suggestions: list[Candidate]
    tier_used: str  # "heuristic" | "local" | "anthropic" | "heuristic_fallback" | "empty_db"
    message: Optional[str] = None


def cascade(
    db: Session,
    placement: PlacementInput,
    local_provider: LLMProvider,
    cloud_provider: Optional[LLMProvider] = None,
    *,
    exclude_ids: Optional[set[int]] = None,
) -> SuggestionResult:
    """Run the DB → local LLM → cloud cascade. Returns at most max_suggestions picks."""

    candidates = score_containers(db, placement, exclude_ids=exclude_ids)
    if not candidates:
        return SuggestionResult(suggestions=[], tier_used="empty_db", message="no containers exist yet")

    best = candidates[0].score
    if best >= HIGH_CONFIDENCE:
        for c in candidates[: placement.max_suggestions]:
            c.reason = _heuristic_reason(c, placement)
        return SuggestionResult(
            suggestions=candidates[: placement.max_suggestions], tier_used="heuristic"
        )

    pool = candidates[:LLM_CANDIDATE_CAP]

    local_picks = llm_rerank(local_provider, placement, pool)
    if local_picks:
        return SuggestionResult(suggestions=local_picks, tier_used="local")

    if cloud_provider is not None:
        cloud_picks = llm_rerank(cloud_provider, placement, pool)
        if cloud_picks:
            return SuggestionResult(suggestions=cloud_picks, tier_used="anthropic")

    fallback = candidates[: placement.max_suggestions]
    for c in fallback:
        c.reason = _heuristic_reason(c, placement)
    return SuggestionResult(
        suggestions=fallback,
        tier_used="heuristic_fallback",
        message="local LLM did not return usable picks; falling back to heuristic ranking",
    )


def score_containers(
    db: Session,
    placement: PlacementInput,
    *,
    exclude_ids: Optional[set[int]] = None,
) -> list[Candidate]:
    """Tier 1: rank every can_contain=true node.

    Each container gets two independent signals — `tag_kind_score` (tag overlap
    weighted with kind affinity, M9) and `neighbor_score` (max Dice similarity
    between the new item name and an existing child's name, M14). The final
    score is the max of the two: a container can win either by being a good
    semantic fit for the kind/tags, or by already holding similar things.
    """
    stmt = (
        select(Node)
        .where(Node.can_contain.is_(True))
        .options(joinedload(Node.kind), joinedload(Node.tags), joinedload(Node.parent))
    )
    if exclude_ids:
        stmt = stmt.where(~Node.id.in_(exclude_ids))
    nodes = db.execute(stmt).unique().scalars().all()

    wanted_tags = {t.lower() for t in placement.tags if t}
    wanted_kind = (placement.kind or "").lower() or None
    new_name_tokens = _tokenize(placement.description)

    children_by_parent = _load_children_names(db, [n.id for n in nodes])

    scored: list[Candidate] = []
    for node in nodes:
        tag_overlap = _tag_overlap_score(wanted_tags, node)
        kind_score = _kind_affinity_score(wanted_kind, node)
        tag_kind_score = TAG_WEIGHT * tag_overlap + KIND_WEIGHT * kind_score

        children_names = children_by_parent.get(node.id, [])
        neighbor_score, neighbor_match = _neighbor_score(new_name_tokens, children_names)
        # Dice over short item names tops out around 0.4 even when a clear word
        # matches ("Claw hammer" vs "Ball-peen hammer" → 0.4). Scale so a real
        # match crosses HIGH_CONFIDENCE; cap at 1.0.
        neighbor_score = min(neighbor_score * NEIGHBOR_SCALE, 1.0)

        score = max(tag_kind_score, neighbor_score)
        candidate = Candidate(node=node, score=score)
        # Stash the winning neighbour's name on a private attr — _heuristic_reason
        # picks it up to explain "matched a sibling" cases.
        candidate._neighbor_match = neighbor_match  # type: ignore[attr-defined]
        candidate._neighbor_score = neighbor_score  # type: ignore[attr-defined]
        scored.append(candidate)

    scored.sort(key=lambda c: (c.score, c.node.id), reverse=True)
    return scored


def _load_children_names(db: Session, parent_ids: list[int]) -> dict[int, list[str]]:
    """One query that returns {parent_id: [child_name, ...]} for the given parents."""
    if not parent_ids:
        return {}
    rows = db.execute(
        select(Node.parent_id, Node.name).where(Node.parent_id.in_(parent_ids))
    ).all()
    out: dict[int, list[str]] = {}
    for parent_id, child_name in rows:
        if parent_id is None:
            continue
        out.setdefault(parent_id, []).append(child_name)
    return out


def _tokenize(name: str) -> set[str]:
    """Lowercase, strip punctuation, drop stopwords and single-char tokens."""
    tokens = _TOKEN_RE.findall((name or "").lower())
    return {t for t in tokens if len(t) > 1 and t not in _NAME_STOPWORDS}


def _dice(a: set[str], b: set[str]) -> float:
    """Sørensen–Dice coefficient over token sets: 2|A∩B| / (|A|+|B|). 0 if either is empty."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return 2.0 * inter / (len(a) + len(b))


def _neighbor_score(
    new_tokens: set[str], children_names: list[str]
) -> tuple[float, Optional[str]]:
    """Best Dice match between the new item's tokens and any child's. Returns (score, child_name)."""
    if not new_tokens or not children_names:
        return 0.0, None
    best_score = 0.0
    best_name: Optional[str] = None
    for child_name in children_names:
        score = _dice(new_tokens, _tokenize(child_name))
        if score > best_score:
            best_score = score
            best_name = child_name
    return best_score, best_name


def llm_rerank(
    provider: LLMProvider,
    placement: PlacementInput,
    pool: list[Candidate],
) -> Optional[list[Candidate]]:
    """Tier 2/3: ask the LLM to pick top N from the candidate pool. Returns None on failure."""
    if not pool:
        return None

    prompt = _build_prompt(placement, pool)
    try:
        result = provider.generate(
            [Message(role="user", content=prompt)],
            system=_SYSTEM_PROMPT,
        )
    except LLMError as exc:
        logger.warning("placement: LLM call failed via %s: %s", provider.name, exc)
        return None

    try:
        data = _extract_json(result.text)
        raw_picks = data["picks"]
        if not isinstance(raw_picks, list):
            raise ValueError("picks is not a list")
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("placement: LLM output unparseable from %s: %s", provider.name, exc)
        return None

    by_id = {c.node.id: c for c in pool}
    picks: list[Candidate] = []
    for item in raw_picks:
        if not isinstance(item, dict):
            continue
        nid = item.get("node_id")
        if not isinstance(nid, int) or nid not in by_id:
            continue
        c = by_id[nid]
        reason = str(item.get("reason", "")).strip() or "selected by LLM"
        picks.append(Candidate(node=c.node, score=c.score, reason=reason))

    if not picks:
        return None
    return picks[: placement.max_suggestions]


def node_path(node: Node) -> str:
    """Ancestor chain as 'Garage / Workbench / Tool drawer'."""
    parts: list[str] = []
    cur: Optional[Node] = node
    while cur is not None:
        parts.append(cur.name)
        cur = cur.parent
    return " / ".join(reversed(parts))


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You help a personal-inventory app suggest where to store an item. "
    "Pick from the candidates the user gives you and return strict JSON only — "
    "no prose, no markdown, no preamble."
)


def _build_prompt(placement: PlacementInput, pool: list[Candidate]) -> str:
    lines = ["Candidates (id, kind, tags, path):"]
    for c in pool:
        kind_slug = c.node.kind.slug if c.node.kind else "?"
        tag_names = ", ".join(t.name for t in c.node.tags) or "-"
        lines.append(f"- [{c.node.id}] kind={kind_slug} tags=[{tag_names}] path={node_path(c.node)}")
    lines.extend(
        [
            "",
            f"User wants to place: {placement.description}",
            f"Input tags: {placement.tags or '-'}",
            f"Input kind: {placement.kind or '-'}",
            "",
            f"Return up to {placement.max_suggestions} picks as JSON ONLY:",
            '{"picks": [{"node_id": <int>, "reason": "<one short sentence>"}, ...]}',
            "Pick fewer if nothing is a good match. node_id must come from the list above.",
        ]
    )
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the LLM's response."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end < start:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


def _tag_overlap_score(wanted: set[str], node: Node) -> float:
    if not wanted:
        return 0.0
    node_tags = {t.name.lower() for t in node.tags}
    matches = wanted & node_tags
    return len(matches) / len(wanted)


def _kind_affinity_score(wanted_kind: Optional[str], node: Node) -> float:
    if not wanted_kind or not node.kind:
        return 0.0
    return KIND_AFFINITY.get(wanted_kind, {}).get(node.kind.slug, 0.0)


def _heuristic_reason(c: Candidate, placement: PlacementInput) -> str:
    parts = []
    wanted = {t.lower() for t in placement.tags if t}
    if wanted:
        matches = wanted & {t.name.lower() for t in c.node.tags}
        if matches:
            parts.append(f"shares tag(s) {sorted(matches)}")
    if placement.kind and c.node.kind:
        aff = KIND_AFFINITY.get(placement.kind.lower(), {}).get(c.node.kind.slug, 0.0)
        if aff > 0:
            parts.append(f"{placement.kind} fits well in {c.node.kind.slug}")
    neighbor_match = getattr(c, "_neighbor_match", None)
    neighbor_score = getattr(c, "_neighbor_score", 0.0)
    if neighbor_match and neighbor_score > 0:
        parts.append(
            f"name overlaps existing sibling {neighbor_match!r} (sim={neighbor_score:.2f})"
        )
    if not parts:
        parts.append("best heuristic match available")
    return "; ".join(parts)


# Re-export the regex helper for tests
_JSON_PROBE = re.compile(r"\{.*\}", re.DOTALL)

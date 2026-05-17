"""M14 — heuristic learns from prior placements (sibling-name matching)."""

from __future__ import annotations

import pytest

from backend.app.ai import LLMProvider, GenerateResult
from backend.app.ai.placement import (
    HIGH_CONFIDENCE,
    PlacementInput,
    _dice,
    _neighbor_score,
    _tokenize,
    score_containers,
)
from backend.app.database import SessionLocal


pytestmark = pytest.mark.committed_writes


class _SilentProvider(LLMProvider):
    """Stub — score_containers shouldn't call into providers."""

    name = "stub"

    def generate(self, messages, *, system=None):
        return GenerateResult(text="")

    def tool_use_loop(self, messages, tools, on_tool_call, *, system=None, max_iterations=8):
        return GenerateResult(text="")


def _make(client, name, kind, *, can_contain=False, parent_id=None, tags=()):
    body = {"name": name, "kind": kind, "can_contain": can_contain}
    if parent_id is not None:
        body["parent_id"] = parent_id
    node = client.post("/nodes", json=body).json()
    for t in tags:
        client.post(f"/nodes/{node['id']}/tags", json={"name": t})
    return node


# ---------------------------------------------------------------------------
# tokenizer + Dice — unit
# ---------------------------------------------------------------------------


def test_tokenize_drops_stopwords_and_short_tokens():
    assert _tokenize("The Big Box of Things") == {"big", "box", "things"}


def test_tokenize_is_punctuation_aware():
    assert _tokenize("Ball-peen hammer (#2)") == {"ball", "peen", "hammer"}


def test_tokenize_empty_string():
    assert _tokenize("") == set()


def test_dice_identical():
    assert _dice({"hammer"}, {"hammer"}) == pytest.approx(1.0)


def test_dice_partial():
    # {a,b} vs {b,c} = 2*1/(2+2) = 0.5
    assert _dice({"a", "b"}, {"b", "c"}) == pytest.approx(0.5)


def test_dice_disjoint():
    assert _dice({"a"}, {"b"}) == 0.0


def test_dice_one_empty():
    assert _dice(set(), {"a"}) == 0.0


def test_neighbor_picks_best_child():
    score, name = _neighbor_score(
        _tokenize("Ball-peen hammer"),
        ["Claw hammer", "Cordless drill", "Screwdriver"],
    )
    assert name == "Claw hammer"
    assert score == pytest.approx(0.4)  # 2*1 / (3+2)


def test_neighbor_no_match():
    score, name = _neighbor_score(_tokenize("Hammer"), ["Cordless drill"])
    assert score == 0.0
    assert name is None


def test_neighbor_empty_children():
    score, name = _neighbor_score(_tokenize("Hammer"), [])
    assert score == 0.0
    assert name is None


# ---------------------------------------------------------------------------
# score_containers — the integration
# ---------------------------------------------------------------------------


def test_neighbor_match_lifts_an_untagged_container_to_high_confidence(client):
    """A container holding "Claw hammer" beats an empty one for "Ball-peen hammer"."""
    garage = _make(client, "Garage", "room", can_contain=True)
    tool_drawer = _make(
        client, "Tool drawer", "drawer", can_contain=True, parent_id=garage["id"]
    )
    _make(client, "Empty drawer", "drawer", can_contain=True, parent_id=garage["id"])

    # populate tool drawer with one hammer
    _make(client, "Claw hammer", "tool", parent_id=tool_drawer["id"])

    db = SessionLocal()
    try:
        ranked = score_containers(
            db,
            PlacementInput(description="Ball-peen hammer", max_suggestions=5),
        )
    finally:
        db.close()

    # Tool drawer wins on neighbor alone; scaled Dice 0.4 * 1.5 = 0.6 ≥ HIGH_CONFIDENCE
    assert ranked[0].node.id == tool_drawer["id"]
    assert ranked[0].score >= HIGH_CONFIDENCE
    # Reason mentions the matched sibling
    from backend.app.ai.placement import _heuristic_reason

    reason = _heuristic_reason(
        ranked[0], PlacementInput(description="Ball-peen hammer")
    )
    assert "Claw hammer" in reason


def test_neighbor_max_combines_with_tag_kind(client):
    """When tag+kind already scores high, neighbour shouldn't drag it down."""
    garage = _make(client, "Garage", "room", can_contain=True)
    # Tool drawer is tagged metal+tool AND has matching kind for "tool".
    cupboard = _make(
        client,
        "Tool cupboard",
        "cupboard",
        can_contain=True,
        parent_id=garage["id"],
        tags=["metal", "tool"],
    )
    # No matching sibling, but strong tag+kind.

    db = SessionLocal()
    try:
        ranked = score_containers(
            db,
            PlacementInput(
                description="Hammer", tags=["metal", "tool"], kind="tool"
            ),
        )
    finally:
        db.close()

    top = ranked[0]
    assert top.node.id == cupboard["id"]
    # tag_overlap=1.0, kind_affinity tool→cupboard=0.9 → tag_kind = 0.96
    assert top.score >= 0.9


def test_neighbor_beats_weak_tag_kind(client):
    """A container with a name match wins over one with no signal at all."""
    garage = _make(client, "Garage", "room", can_contain=True)
    has_hammer = _make(client, "A", "drawer", can_contain=True, parent_id=garage["id"])
    _make(client, "Old hammer", "tool", parent_id=has_hammer["id"])
    _make(client, "B", "drawer", can_contain=True, parent_id=garage["id"])

    db = SessionLocal()
    try:
        ranked = score_containers(
            db,
            # no tags, no kind — only the neighbour signal can fire
            PlacementInput(description="New hammer"),
        )
    finally:
        db.close()

    assert ranked[0].node.id == has_hammer["id"]


def test_stopwords_dont_create_false_matches(client):
    """'The box' and 'The bag' shouldn't be considered similar."""
    garage = _make(client, "Garage", "room", can_contain=True)
    a = _make(client, "Holder A", "box", can_contain=True, parent_id=garage["id"])
    _make(client, "The thing", "item", parent_id=a["id"])
    b = _make(client, "Holder B", "box", can_contain=True, parent_id=garage["id"])

    db = SessionLocal()
    try:
        ranked = score_containers(
            db, PlacementInput(description="The hammer")
        )
    finally:
        db.close()

    # Neither container should score above zero from 'the' (a stopword).
    # Both should rank equally at 0.
    assert all(c.score == 0.0 for c in ranked if c.node.id in (a["id"], b["id"]))


def test_multiple_matching_siblings_dont_double_count_max_takes_winner(client):
    """N hammers in one drawer still gives 'max' Dice, not sum."""
    garage = _make(client, "Garage", "room", can_contain=True)
    drawer = _make(client, "Drawer", "drawer", can_contain=True, parent_id=garage["id"])
    _make(client, "Hammer one", "tool", parent_id=drawer["id"])
    _make(client, "Hammer two", "tool", parent_id=drawer["id"])
    _make(client, "Hammer three", "tool", parent_id=drawer["id"])

    db = SessionLocal()
    try:
        ranked = score_containers(db, PlacementInput(description="Hammer four"))
    finally:
        db.close()

    top = next(c for c in ranked if c.node.id == drawer["id"])
    # Each "Hammer N" shares 1 of 2 tokens with "Hammer four" → Dice 0.5 → scaled 0.75.
    # Multiple siblings don't compound; the score is the best single match.
    assert top.score == pytest.approx(0.75)


def test_empty_container_with_no_signals_scores_zero(client):
    """No tag/kind hint, no children → score 0 (falls through to LLM)."""
    _make(client, "Empty", "drawer", can_contain=True)
    db = SessionLocal()
    try:
        ranked = score_containers(db, PlacementInput(description="Whatever"))
    finally:
        db.close()

    assert ranked[0].score == 0.0

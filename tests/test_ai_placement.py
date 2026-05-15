from __future__ import annotations

import json
from typing import Any

import pytest

from backend.app.ai import GenerateResult, LLMError, LLMProvider


class StubProvider(LLMProvider):
    """Test double — captures calls and returns a canned response or raises."""

    def __init__(self, name: str, *, text: str = "", error: Exception | None = None) -> None:
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


def _patch_providers(monkeypatch, *, local: StubProvider | None = None, cloud: StubProvider | None = None):
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
# tier 1 — high-confidence heuristic
# ---------------------------------------------------------------------------


def test_tier1_heuristic_high_confidence(client, monkeypatch):
    """Strong tag+kind match → return tier_used=heuristic without calling LLM."""
    local = StubProvider("local", text="SHOULD NOT BE CALLED")
    _patch_providers(monkeypatch, local=local)

    garage = _make_container(client, "Garage", "room")
    tool_cupboard = _make_container(
        client, "Tool cupboard", "cupboard", parent_id=garage["id"], tags=["metal", "tool"]
    )
    _make_container(client, "Coat closet", "cupboard", parent_id=garage["id"], tags=["clothes"])

    response = client.post(
        "/ai/suggest-placement",
        json={"description": "claw hammer", "tags": ["metal", "tool"], "kind": "tool"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "heuristic"
    assert body["cloud_enabled"] is False
    assert body["suggestions"][0]["node_id"] == tool_cupboard["id"]
    assert body["suggestions"][0]["path"].startswith("Garage / Tool cupboard")
    assert body["suggestions"][0]["score"] >= 0.6
    assert local.calls == []  # LLM not consulted


# ---------------------------------------------------------------------------
# tier 2 — local LLM rerank when heuristic is weak
# ---------------------------------------------------------------------------


def test_tier2_local_llm_picks_when_heuristic_weak(client, monkeypatch):
    """No matching tags or kind → cascade falls to local LLM, which picks one."""
    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Misc drawer", "drawer", parent_id=garage["id"])
    _make_container(client, "Coat closet", "cupboard", parent_id=garage["id"])

    local = StubProvider(
        "local",
        text=json.dumps({"picks": [{"node_id": drawer["id"], "reason": "small items fit here"}]}),
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post(
        "/ai/suggest-placement",
        json={"description": "an unusual gadget"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    assert len(body["suggestions"]) == 1
    assert body["suggestions"][0]["node_id"] == drawer["id"]
    assert body["suggestions"][0]["reason"] == "small items fit here"
    assert len(local.calls) == 1


def test_tier2_handles_llm_preamble_and_trailing_text(client, monkeypatch):
    """LLM wraps JSON in markdown/prose → cascade extracts the JSON object."""
    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Misc drawer", "drawer", parent_id=garage["id"])

    local = StubProvider(
        "local",
        text=(
            "Sure, here are my picks:\n```json\n"
            + json.dumps({"picks": [{"node_id": drawer["id"], "reason": "ok"}]})
            + "\n```\nHope that helps!"
        ),
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/suggest-placement", json={"description": "thing"})
    assert response.status_code == 200, response.text
    assert response.json()["tier_used"] == "local"


def test_tier2_invalid_json_falls_back_to_heuristic(client, monkeypatch):
    garage = _make_container(client, "Garage", "room")
    _make_container(client, "Misc drawer", "drawer", parent_id=garage["id"])

    local = StubProvider("local", text="not json at all, sorry")
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/suggest-placement", json={"description": "thing"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "heuristic_fallback"
    assert body["message"]
    assert body["suggestions"], "should still return heuristic ranking as fallback"


def test_tier2_llm_error_falls_back_to_heuristic(client, monkeypatch):
    garage = _make_container(client, "Garage", "room")
    _make_container(client, "Misc drawer", "drawer", parent_id=garage["id"])

    local = StubProvider("local", error=LLMError("ollama down"))
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/suggest-placement", json={"description": "thing"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "heuristic_fallback"


def test_tier2_picks_unknown_node_ids_are_ignored(client, monkeypatch):
    """LLM hallucinates node ids → ignored; if no valid picks, fall back."""
    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Misc drawer", "drawer", parent_id=garage["id"])

    local = StubProvider(
        "local",
        text=json.dumps(
            {
                "picks": [
                    {"node_id": 99999, "reason": "fake"},
                    {"node_id": drawer["id"], "reason": "real"},
                ]
            }
        ),
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/suggest-placement", json={"description": "x"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    ids = [s["node_id"] for s in body["suggestions"]]
    assert ids == [drawer["id"]]


# ---------------------------------------------------------------------------
# tier 3 — cloud (kill switch + per-call gate)
# ---------------------------------------------------------------------------


def test_cloud_off_with_confirm_remote_returns_400(client, monkeypatch):
    monkeypatch.delenv("WHEREISIT_CLOUD_ENABLED", raising=False)
    _patch_providers(monkeypatch)

    _make_container(client, "Garage", "room")
    response = client.post(
        "/ai/suggest-placement",
        json={"description": "x", "confirm_remote": True},
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "cloud_disabled"


def test_cloud_on_with_confirm_remote_uses_anthropic(client, monkeypatch):
    monkeypatch.setenv("WHEREISIT_CLOUD_ENABLED", "true")

    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Drawer", "drawer", parent_id=garage["id"])

    local = StubProvider("local", text="garbage from local")
    cloud = StubProvider(
        "anthropic",
        text=json.dumps({"picks": [{"node_id": drawer["id"], "reason": "cloud picked"}]}),
    )
    _patch_providers(monkeypatch, local=local, cloud=cloud)

    response = client.post(
        "/ai/suggest-placement",
        json={"description": "thing", "confirm_remote": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "anthropic"
    assert body["cloud_enabled"] is True
    assert body["suggestions"][0]["reason"] == "cloud picked"
    assert len(local.calls) == 1  # local tried first
    assert len(cloud.calls) == 1  # then cloud


def test_cloud_on_no_confirm_remote_stays_local(client, monkeypatch):
    monkeypatch.setenv("WHEREISIT_CLOUD_ENABLED", "true")

    garage = _make_container(client, "Garage", "room")
    drawer = _make_container(client, "Drawer", "drawer", parent_id=garage["id"])

    local = StubProvider(
        "local",
        text=json.dumps({"picks": [{"node_id": drawer["id"], "reason": "local"}]}),
    )
    cloud = StubProvider("anthropic", text="SHOULD NOT BE CALLED")
    _patch_providers(monkeypatch, local=local, cloud=cloud)

    response = client.post("/ai/suggest-placement", json={"description": "thing"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    assert body["cloud_enabled"] is True
    assert cloud.calls == []


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def test_empty_db_returns_empty_db_tier(client, monkeypatch):
    local = StubProvider("local", text="SHOULD NOT BE CALLED")
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/suggest-placement", json={"description": "x"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "empty_db"
    assert body["suggestions"] == []
    assert local.calls == []


def test_validation_errors(client, monkeypatch):
    _patch_providers(monkeypatch)
    # empty description rejected
    r = client.post("/ai/suggest-placement", json={"description": ""})
    assert r.status_code == 422
    # max_suggestions out of bounds
    r = client.post(
        "/ai/suggest-placement",
        json={"description": "x", "max_suggestions": 99},
    )
    assert r.status_code == 422


def test_max_suggestions_caps_results(client, monkeypatch):
    """tier=heuristic respects max_suggestions."""
    _patch_providers(monkeypatch)

    garage = _make_container(client, "Garage", "room")
    for i in range(5):
        _make_container(
            client, f"Box {i}", "box", parent_id=garage["id"], tags=["metal", "tool"]
        )

    response = client.post(
        "/ai/suggest-placement",
        json={
            "description": "hammer",
            "tags": ["metal", "tool"],
            "kind": "tool",
            "max_suggestions": 2,
        },
    )
    body = response.json()
    assert body["tier_used"] == "heuristic"
    assert len(body["suggestions"]) == 2

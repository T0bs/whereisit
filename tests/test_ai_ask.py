from __future__ import annotations

from typing import Any

import pytest

from backend.app.ai import GenerateResult, LLMError, LLMProvider, Message, Tool


# Tier-1 hits FULLTEXT, dispatcher writes via routes — both need committed rows.
pytestmark = pytest.mark.committed_writes


# ---------------------------------------------------------------------------
# stub providers
# ---------------------------------------------------------------------------


class ScriptedToolLoopProvider(LLMProvider):
    """Provider that runs a scripted list of tool calls, then returns final_text."""

    def __init__(
        self,
        name: str,
        *,
        calls: list[tuple[str, dict[str, Any]]] | None = None,
        final_text: str = "done",
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.scripted_calls = list(calls or [])
        self.final_text = final_text
        self._error = error
        self.last_tools: list[Tool] | None = None
        self.last_system: str | None = None
        self.last_messages: list[Message] | None = None
        self.captured_tool_outputs: list[str] = []

    def generate(self, messages, *, system=None):
        return GenerateResult(text=self.final_text)

    def tool_use_loop(self, messages, tools, on_tool_call, *, system=None, max_iterations=8):
        self.last_messages = list(messages)
        self.last_system = system
        self.last_tools = list(tools)
        if self._error is not None:
            raise self._error
        for name, args in self.scripted_calls:
            output = on_tool_call(name, args)
            self.captured_tool_outputs.append(output)
        return GenerateResult(text=self.final_text)


def _patch_providers(monkeypatch, *, local: LLMProvider | None = None, cloud: LLMProvider | None = None):
    def fake_get_provider(name):
        if name == "local":
            return local if local is not None else ScriptedToolLoopProvider("local")
        if name == "anthropic":
            return cloud if cloud is not None else ScriptedToolLoopProvider("anthropic")
        raise LLMError(f"unexpected: {name}")

    monkeypatch.setattr("backend.app.routers.ai.get_provider", fake_get_provider)


def _make_node(client, name, kind="item", *, parent_id=None, can_contain=False, description=None, tags=()):
    body = {"name": name, "kind": kind, "can_contain": can_contain}
    if parent_id is not None:
        body["parent_id"] = parent_id
    if description is not None:
        body["description"] = description
    node = client.post("/nodes", json=body).json()
    for t in tags:
        client.post(f"/nodes/{node['id']}/tags", json={"name": t})
    return node


# ---------------------------------------------------------------------------
# tier 1 — literal search
# ---------------------------------------------------------------------------


def test_tier1_keyword_returns_search_match(client, monkeypatch):
    local = ScriptedToolLoopProvider("local", final_text="SHOULD NOT BE CALLED")
    _patch_providers(monkeypatch, local=local)

    garage = _make_node(client, "Garage", "room", can_contain=True)
    cupboard = _make_node(client, "Tool cupboard", "cupboard", parent_id=garage["id"], can_contain=True)
    _make_node(client, "Claw hammer", "tool", parent_id=cupboard["id"])

    response = client.post("/ai/ask", json={"question": "where is my hammer?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "search"
    assert "Claw hammer" in body["answer"]
    assert "Garage" in body["answer"] and "Tool cupboard" in body["answer"]
    assert body["tool_calls"] == []
    assert local.last_tools is None


def test_tier1_strips_stopwords(client, monkeypatch):
    """All stopwords → tier 1 returns None → cascade falls through."""
    local = ScriptedToolLoopProvider("local", final_text="I need a real question.")
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/ask", json={"question": "where is it?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    # the LLM was invoked because tier 1 had no keywords to search on
    assert local.last_tools is not None


def test_tier1_no_match_falls_through_to_llm(client, monkeypatch):
    _make_node(client, "Garage", "room", can_contain=True)

    local = ScriptedToolLoopProvider(
        "local",
        calls=[("list_root_nodes", {"limit": 50})],
        final_text="There is one room: Garage.",
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/ask", json={"question": "tell me about nonexistentwidgetxyz"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    assert body["answer"] == "There is one room: Garage."
    assert len(body["tool_calls"]) == 1
    assert body["tool_calls"][0]["tool"] == "list_root_nodes"


# ---------------------------------------------------------------------------
# tier 2 — local LLM tool-use loop
# ---------------------------------------------------------------------------


def test_tier2_search_tool_traces(client, monkeypatch):
    _make_node(client, "Hammer", "tool")

    local = ScriptedToolLoopProvider(
        "local",
        calls=[("search", {"q": "hammer"})],
        final_text="Found one hammer.",
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/ask", json={"question": "what hammers exist"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    assert len(body["tool_calls"]) == 1
    trace = body["tool_calls"][0]
    assert trace["tool"] == "search"
    assert trace["input"] == {"q": "hammer"}
    assert trace["is_error"] is False
    # tool output is JSON serialized
    assert "Hammer" in trace["output"]


def test_tier2_write_tool_actually_creates_node(client, monkeypatch):
    garage = _make_node(client, "Garage", "room", can_contain=True)

    local = ScriptedToolLoopProvider(
        "local",
        calls=[
            ("add_node", {"name": "Drill", "kind": "tool", "parent_id": garage["id"]}),
        ],
        final_text="Added the drill.",
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/ask", json={"question": "please add a drill to the garage"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    assert body["tool_calls"][0]["is_error"] is False

    # The node really exists now
    listing = client.get(f"/nodes/{garage['id']}/children").json()
    names = [n["name"] for n in listing]
    assert "Drill" in names


def test_tier2_tool_error_surfaces_as_is_error(client, monkeypatch):
    """LLM calls a write tool with invalid args → is_error=true in trace, loop continues."""
    local = ScriptedToolLoopProvider(
        "local",
        calls=[("get_node", {"node_id": 99999})],  # not found → 404
        final_text="That node does not exist.",
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/ask", json={"question": "describe node 99999"})
    assert response.status_code == 200, response.text
    body = response.json()
    trace = body["tool_calls"][0]
    assert trace["is_error"] is True
    assert "not found" in trace["output"].lower()


def test_tier2_unknown_tool_is_error(client, monkeypatch):
    local = ScriptedToolLoopProvider(
        "local",
        calls=[("hallucinated_tool", {})],
        final_text="I'll try something else.",
    )
    _patch_providers(monkeypatch, local=local)

    response = client.post("/ai/ask", json={"question": "anything"})
    assert response.status_code == 200, response.text
    body = response.json()
    trace = body["tool_calls"][0]
    assert trace["is_error"] is True
    assert "unknown tool" in trace["output"]


def test_tier2_llm_error_exhausted(client, monkeypatch):
    local = ScriptedToolLoopProvider("local", error=LLMError("ollama down"))
    _patch_providers(monkeypatch, local=local)

    _make_node(client, "Garage", "room", can_contain=True)
    response = client.post(
        "/ai/ask", json={"question": "any nonexistentthing in inventory"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "exhausted"
    assert body["message"]


# ---------------------------------------------------------------------------
# tier 3 — cloud gate
# ---------------------------------------------------------------------------


def test_cloud_off_with_confirm_remote_returns_400(client, monkeypatch):
    monkeypatch.delenv("WHEREISIT_CLOUD_ENABLED", raising=False)
    _patch_providers(monkeypatch)

    response = client.post(
        "/ai/ask", json={"question": "anything", "confirm_remote": True}
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "cloud_disabled"


def test_cloud_on_with_confirm_remote_uses_anthropic_when_local_fails(client, monkeypatch):
    monkeypatch.setenv("WHEREISIT_CLOUD_ENABLED", "true")

    _make_node(client, "Garage", "room", can_contain=True)

    local = ScriptedToolLoopProvider("local", error=LLMError("local down"))
    cloud = ScriptedToolLoopProvider(
        "anthropic",
        calls=[("list_root_nodes", {})],
        final_text="One room: Garage.",
    )
    _patch_providers(monkeypatch, local=local, cloud=cloud)

    response = client.post(
        "/ai/ask",
        json={"question": "list nonexistentitem rooms", "confirm_remote": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "anthropic"
    assert body["cloud_enabled"] is True
    assert body["answer"] == "One room: Garage."


def test_cloud_on_no_confirm_remote_keeps_local(client, monkeypatch):
    monkeypatch.setenv("WHEREISIT_CLOUD_ENABLED", "true")

    local = ScriptedToolLoopProvider("local", final_text="local answer")
    cloud = ScriptedToolLoopProvider("anthropic", final_text="SHOULD NOT BE CALLED")
    _patch_providers(monkeypatch, local=local, cloud=cloud)

    _make_node(client, "Garage", "room", can_contain=True)
    response = client.post(
        "/ai/ask", json={"question": "what nonexistentthing is here"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_used"] == "local"
    assert body["cloud_enabled"] is True
    assert cloud.last_tools is None  # cloud never called


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def test_validation_empty_question(client, monkeypatch):
    _patch_providers(monkeypatch)
    r = client.post("/ai/ask", json={"question": ""})
    assert r.status_code == 422


def test_validation_max_iterations_out_of_range(client, monkeypatch):
    _patch_providers(monkeypatch)
    r = client.post("/ai/ask", json={"question": "x", "max_iterations": 99})
    assert r.status_code == 422


def test_system_prompt_passed_to_llm(client, monkeypatch):
    """Sanity: the cascade actually provides a system prompt to the provider."""
    local = ScriptedToolLoopProvider("local", final_text="ok")
    _patch_providers(monkeypatch, local=local)

    _make_node(client, "Room", "room", can_contain=True)
    client.post("/ai/ask", json={"question": "what nonexistentitem is here"})

    assert local.last_system is not None
    assert "inventory" in local.last_system.lower()


def test_all_inventory_tools_exposed_to_llm(client, monkeypatch):
    """The LLM should see the full 14-tool surface (read + write)."""
    local = ScriptedToolLoopProvider("local", final_text="ok")
    _patch_providers(monkeypatch, local=local)

    _make_node(client, "Room", "room", can_contain=True)
    client.post("/ai/ask", json={"question": "what nonexistentitem is here"})

    tool_names = {t.name for t in local.last_tools}
    assert tool_names == {
        "search", "get_node", "get_children", "get_path",
        "list_root_nodes", "list_kinds", "list_tags",
        "add_node", "update_node", "move_node", "delete_node",
        "add_tag", "remove_tag", "set_property",
    }

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from backend.app.ai import (
    AnthropicProvider,
    LLMError,
    LocalProvider,
    Message,
    Tool,
    get_provider,
)


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------


def test_factory_default_is_local(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert get_provider().name == "local"


def test_factory_picks_anthropic_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    p = get_provider()
    assert p.name == "anthropic"
    assert isinstance(p, AnthropicProvider)


def test_factory_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert get_provider("local").name == "local"


def test_factory_unknown_raises():
    with pytest.raises(LLMError):
        get_provider("bogus")


def test_factory_respects_local_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_LOCAL_URL", "http://example.test:9999")
    monkeypatch.setenv("LLM_LOCAL_MODEL", "qwen2.5:7b")
    p = get_provider()
    assert isinstance(p, LocalProvider)
    assert p.base_url == "http://example.test:9999"
    assert p.model == "qwen2.5:7b"


# ---------------------------------------------------------------------------
# AnthropicProvider — fake client
# ---------------------------------------------------------------------------


class FakeAnthropicMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeAnthropicClient:
    def __init__(self, responses):
        self.messages = FakeAnthropicMessages(responses)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id: str, name: str, input: dict):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _anthropic_response(content_blocks, stop_reason="end_turn", **usage):
    u = SimpleNamespace(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
        cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
    )
    return SimpleNamespace(content=content_blocks, stop_reason=stop_reason, usage=u)


def test_anthropic_generate_basic():
    client = FakeAnthropicClient(
        [_anthropic_response([_text_block("Hello")], input_tokens=10, output_tokens=2)]
    )
    p = AnthropicProvider(client=client, model="claude-haiku-4-5", cache_system=True)
    result = p.generate([Message(role="user", content="hi")], system="be brief")

    assert result.text == "Hello"
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 2

    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["max_tokens"] == 4096
    assert call["system"] == [
        {"type": "text", "text": "be brief", "cache_control": {"type": "ephemeral"}}
    ]
    assert call["messages"] == [{"role": "user", "content": "hi"}]


def test_anthropic_generate_no_cache():
    client = FakeAnthropicClient([_anthropic_response([_text_block("Hi")])])
    p = AnthropicProvider(client=client, cache_system=False)
    p.generate([Message(role="user", content="hi")], system="x")
    assert client.messages.calls[0]["system"] == "x"


def test_anthropic_generate_no_system_omits_field():
    client = FakeAnthropicClient([_anthropic_response([_text_block("Hi")])])
    p = AnthropicProvider(client=client)
    p.generate([Message(role="user", content="hi")])
    assert "system" not in client.messages.calls[0]


def test_anthropic_tool_use_loop_two_turns():
    client = FakeAnthropicClient(
        [
            _anthropic_response(
                [_tool_use_block("tu_1", "get_x", {"q": "abc"})],
                stop_reason="tool_use",
            ),
            _anthropic_response([_text_block("answer is 42")], stop_reason="end_turn"),
        ]
    )
    p = AnthropicProvider(client=client, cache_system=False)
    seen: list[tuple[str, dict]] = []

    def cb(name, inp):
        seen.append((name, inp))
        return "got 42"

    result = p.tool_use_loop(
        [Message(role="user", content="ask")],
        [Tool(name="get_x", description="X", input_schema={"type": "object"})],
        on_tool_call=cb,
    )
    assert result.text == "answer is 42"
    assert seen == [("get_x", {"q": "abc"})]
    assert len(client.messages.calls) == 2

    # second call carries the assistant tool_use turn and the user tool_result turn
    second = client.messages.calls[1]["messages"]
    assert second[1]["role"] == "assistant"
    assert second[2]["role"] == "user"
    tool_result = second[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tu_1"
    assert tool_result["content"] == "got 42"


def test_anthropic_tool_use_loop_callback_error_returns_is_error():
    client = FakeAnthropicClient(
        [
            _anthropic_response(
                [_tool_use_block("tu_1", "get_x", {})], stop_reason="tool_use"
            ),
            _anthropic_response([_text_block("recovered")], stop_reason="end_turn"),
        ]
    )
    p = AnthropicProvider(client=client, cache_system=False)

    def cb(name, inp):
        raise RuntimeError("boom")

    result = p.tool_use_loop(
        [Message(role="user", content="hi")],
        [Tool(name="get_x", description="X", input_schema={"type": "object"})],
        on_tool_call=cb,
    )
    assert result.text == "recovered"
    tool_result = client.messages.calls[1]["messages"][2]["content"][0]
    assert tool_result["is_error"] is True
    assert "boom" in tool_result["content"]


def test_anthropic_tool_use_loop_max_iterations():
    responses = [
        _anthropic_response(
            [_tool_use_block(f"tu_{i}", "get_x", {})], stop_reason="tool_use"
        )
        for i in range(10)
    ]
    client = FakeAnthropicClient(responses)
    p = AnthropicProvider(client=client, cache_system=False)
    with pytest.raises(LLMError, match="max_iterations"):
        p.tool_use_loop(
            [Message(role="user", content="hi")],
            [Tool(name="get_x", description="X", input_schema={"type": "object"})],
            on_tool_call=lambda n, i: "ok",
            max_iterations=3,
        )


def test_anthropic_api_error_wraps():
    request = httpx.Request("POST", "http://api.anthropic.com/v1/messages")

    class BoomMessages:
        def create(self, **kwargs):
            raise anthropic.APIConnectionError(request=request)

    p = AnthropicProvider(client=SimpleNamespace(messages=BoomMessages()))
    with pytest.raises(LLMError, match="Anthropic API error"):
        p.generate([Message(role="user", content="hi")])


# ---------------------------------------------------------------------------
# LocalProvider — httpx MockTransport
# ---------------------------------------------------------------------------


def _ollama_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_local_generate_basic():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hello back"},
                "prompt_eval_count": 7,
                "eval_count": 3,
            },
        )

    p = LocalProvider(client=_ollama_client(handler), model="llama3.1:8b")
    result = p.generate([Message(role="user", content="hi")], system="be brief")

    assert result.text == "hello back"
    assert result.usage == {"prompt_tokens": 7, "completion_tokens": 3}
    assert captured["url"].endswith("/api/chat")
    body = captured["body"]
    assert body["model"] == "llama3.1:8b"
    assert body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}
    assert "tools" not in body


def test_local_tool_use_loop_two_turns():
    responses = iter(
        [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "get_x", "arguments": {"q": "abc"}}}
                    ],
                }
            },
            {"message": {"role": "assistant", "content": "answer is 42"}},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    p = LocalProvider(client=_ollama_client(handler))
    seen: list[tuple[str, dict]] = []

    def cb(name, inp):
        seen.append((name, inp))
        return "got 42"

    result = p.tool_use_loop(
        [Message(role="user", content="ask")],
        [Tool(name="get_x", description="X", input_schema={"type": "object"})],
        on_tool_call=cb,
    )
    assert result.text == "answer is 42"
    assert seen == [("get_x", {"q": "abc"})]


def test_local_tool_use_loop_string_arguments():
    responses = iter(
        [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "get_x", "arguments": '{"q": "abc"}'}}
                    ],
                }
            },
            {"message": {"content": "done"}},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    p = LocalProvider(client=_ollama_client(handler))
    seen: list[tuple[str, dict]] = []

    p.tool_use_loop(
        [Message(role="user", content="hi")],
        [Tool(name="get_x", description="X", input_schema={"type": "object"})],
        on_tool_call=lambda n, i: (seen.append((n, i)), "ok")[1],
    )
    assert seen == [("get_x", {"q": "abc"})]


def test_local_http_error_wraps():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    p = LocalProvider(client=_ollama_client(handler))
    with pytest.raises(LLMError, match="Ollama HTTP error"):
        p.generate([Message(role="user", content="hi")])


def test_local_embed_hits_ollama_embed_endpoint():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]},
        )

    p = LocalProvider(client=_ollama_client(handler), model="llama3.1:8b")
    vectors = p.embed(["hello", "world"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert captured["url"].endswith("/api/embed")
    assert captured["body"]["model"] == "nomic-embed-text"
    assert captured["body"]["input"] == ["hello", "world"]


def test_local_embed_empty_input_skips_http():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP should not be hit for empty input")

    p = LocalProvider(client=_ollama_client(handler))
    assert p.embed([]) == []


def test_local_embed_count_mismatch_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0, 2.0]]})

    p = LocalProvider(client=_ollama_client(handler))
    with pytest.raises(LLMError, match="vectors for"):
        p.embed(["a", "b", "c"])


def test_local_embed_http_error_wraps():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model not found"})

    p = LocalProvider(client=_ollama_client(handler))
    with pytest.raises(LLMError, match="Ollama embed HTTP error"):
        p.embed(["hi"])


def test_anthropic_embed_raises_llm_error():
    p = AnthropicProvider(client=SimpleNamespace(messages=None))
    with pytest.raises(LLMError, match="does not support embeddings"):
        p.embed(["hi"])


def test_local_tool_use_loop_max_iterations():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "tool_calls": [{"function": {"name": "x", "arguments": {}}}],
                }
            },
        )

    p = LocalProvider(client=_ollama_client(handler))
    with pytest.raises(LLMError, match="max_iterations"):
        p.tool_use_loop(
            [Message(role="user", content="hi")],
            [Tool(name="x", description="x", input_schema={"type": "object"})],
            on_tool_call=lambda n, i: "ok",
            max_iterations=2,
        )

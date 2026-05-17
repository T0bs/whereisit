from __future__ import annotations

from typing import Any, Callable

import httpx

from .provider import GenerateResult, LLMError, LLMProvider, Message, Tool


class LocalProvider(LLMProvider):
    name = "local"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        embed_model: str = "nomic-embed-text",
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.timeout = timeout
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._client or httpx.Client(timeout=self.timeout)
        owns_client = self._client is None
        try:
            response = client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.embed_model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama embed HTTP error: {exc}") from exc
        finally:
            if owns_client:
                client.close()

        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LLMError(
                f"Ollama embed returned {len(vectors) if isinstance(vectors, list) else '?'} "
                f"vectors for {len(texts)} inputs"
            )
        return [[float(x) for x in v] for v in vectors]

    def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> GenerateResult:
        data = self._chat(
            messages=_to_ollama_messages(messages, system=system),
            tools=None,
        )
        msg = data.get("message") or {}
        return GenerateResult(text=msg.get("content", ""), usage=_extract_usage(data))

    def tool_use_loop(
        self,
        messages: list[Message],
        tools: list[Tool],
        on_tool_call: Callable[[str, dict[str, Any]], str],
        *,
        system: str | None = None,
        max_iterations: int = 8,
    ) -> GenerateResult:
        api_messages = _to_ollama_messages(messages, system=system)
        api_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

        last_data: dict[str, Any] | None = None
        for _ in range(max_iterations):
            data = self._chat(messages=api_messages, tools=api_tools)
            last_data = data
            msg = data.get("message") or {}
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                break

            assistant_turn: dict[str, Any] = {
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            }
            api_messages.append(assistant_turn)

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                try:
                    result = on_tool_call(name, dict(args))
                except Exception as exc:
                    result = f"Error: {exc}"
                api_messages.append({"role": "tool", "content": result})
        else:
            raise LLMError(f"tool_use_loop exceeded max_iterations={max_iterations}")

        assert last_data is not None
        msg = last_data.get("message") or {}
        return GenerateResult(text=msg.get("content", ""), usage=_extract_usage(last_data))

    def _chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        client = self._client or httpx.Client(timeout=self.timeout)
        owns_client = self._client is None
        try:
            response = client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama HTTP error: {exc}") from exc
        finally:
            if owns_client:
                client.close()


def _to_ollama_messages(
    messages: list[Message], *, system: str | None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    out.extend({"role": m.role, "content": m.content} for m in messages)
    return out


def _extract_usage(data: dict[str, Any]) -> dict[str, int]:
    return {
        "prompt_tokens": int(data.get("prompt_eval_count", 0) or 0),
        "completion_tokens": int(data.get("eval_count", 0) or 0),
    }

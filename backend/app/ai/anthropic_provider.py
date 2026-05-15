from __future__ import annotations

from typing import Any, Callable

import anthropic

from .provider import GenerateResult, LLMError, LLMProvider, Message, Tool


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5",
        max_tokens: int = 4096,
        cache_system: bool = True,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.cache_system = cache_system
        self.client = client if client is not None else anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> GenerateResult:
        try:
            response = self.client.messages.create(
                **self._base_kwargs(system=system),
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        return GenerateResult(text=_extract_text(response), usage=_extract_usage(response))

    def tool_use_loop(
        self,
        messages: list[Message],
        tools: list[Tool],
        on_tool_call: Callable[[str, dict[str, Any]], str],
        *,
        system: str | None = None,
        max_iterations: int = 8,
    ) -> GenerateResult:
        api_messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        api_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

        last_response = None
        for _ in range(max_iterations):
            try:
                response = self.client.messages.create(
                    **self._base_kwargs(system=system),
                    messages=api_messages,
                    tools=api_tools,
                )
            except anthropic.APIError as exc:
                raise LLMError(f"Anthropic API error: {exc}") from exc

            last_response = response
            if response.stop_reason != "tool_use":
                break

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            api_messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                try:
                    result = on_tool_call(tu.name, dict(tu.input))
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": tu.id, "content": result}
                    )
                except Exception as exc:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Error: {exc}",
                            "is_error": True,
                        }
                    )
            api_messages.append({"role": "user", "content": tool_results})
        else:
            raise LLMError(f"tool_use_loop exceeded max_iterations={max_iterations}")

        assert last_response is not None
        return GenerateResult(
            text=_extract_text(last_response), usage=_extract_usage(last_response)
        )

    def _base_kwargs(self, *, system: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens}
        if system is not None:
            if self.cache_system:
                kwargs["system"] = [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ]
            else:
                kwargs["system"] = system
        return kwargs


def _extract_text(response: Any) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def _extract_usage(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }

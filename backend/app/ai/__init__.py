from __future__ import annotations

import os

from .anthropic_provider import AnthropicProvider
from .local_provider import LocalProvider
from .provider import (
    GenerateResult,
    LLMError,
    LLMProvider,
    Message,
    Tool,
    ToolCall,
)


def get_provider(name: str | None = None) -> LLMProvider:
    selected = (name or os.getenv("LLM_PROVIDER", "local")).lower()
    if selected == "local":
        return LocalProvider(
            base_url=os.getenv("LLM_LOCAL_URL", "http://127.0.0.1:11434"),
            model=os.getenv("LLM_LOCAL_MODEL", "qwen2.5:7b"),
            embed_model=os.getenv("LLM_EMBED_MODEL", "nomic-embed-text"),
        )
    if selected == "anthropic":
        return AnthropicProvider(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        )
    raise LLMError(f"unknown LLM provider: {selected!r} (expected 'local' or 'anthropic')")


__all__ = [
    "AnthropicProvider",
    "GenerateResult",
    "LLMError",
    "LLMProvider",
    "LocalProvider",
    "Message",
    "Tool",
    "ToolCall",
    "get_provider",
]

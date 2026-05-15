from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class GenerateResult:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str
    embed_model: str | None = None

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> GenerateResult:
        ...

    @abstractmethod
    def tool_use_loop(
        self,
        messages: list[Message],
        tools: list[Tool],
        on_tool_call: Callable[[str, dict[str, Any]], str],
        *,
        system: str | None = None,
        max_iterations: int = 8,
    ) -> GenerateResult:
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text. Order matches input."""
        raise LLMError(f"{type(self).__name__} does not support embeddings")

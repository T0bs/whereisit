"""Cascade for POST /ai/ask: literal search → local LLM tool-use loop → cloud."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node
from ..routers.search import _batch_paths, _build_boolean_term, _fulltext_scores
from .inventory_tools import (
    ToolCallTrace,
    build_inventory_tools,
    execute_tool,
)
from .provider import LLMError, LLMProvider, Message

logger = logging.getLogger(__name__)


STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "i", "me", "my", "mine", "you", "your", "we", "us", "our",
        "where", "what", "when", "who", "whom", "whose", "why", "how",
        "do", "does", "did", "doing", "done",
        "have", "has", "had", "having",
        "can", "could", "would", "should", "may", "might", "must", "shall",
        "find", "show", "list", "tell", "give", "get",
        "any", "all", "some", "many", "much", "every", "no", "not",
        "in", "on", "at", "to", "from", "of", "for", "with", "by",
        "and", "or", "but", "if", "then", "than", "so",
        "this", "that", "these", "those",
        "it", "its", "there", "here",
        "please", "kindly",
    }
)


SYSTEM_PROMPT = (
    "You are the assistant for a personal home-inventory app. The user's home is "
    "a tree of nodes: rooms, cupboards, drawers, items, tools, consumables. Each "
    "node has a kind, optional tags, and a parent.\n\n"
    "Answer the user's question by calling the provided tools to look things up. "
    "Common patterns:\n"
    "- 'where is my X?' → call `search` with q=X, then describe the path(s).\n"
    "- 'how many X do I have?' → call `search`, count + group by location.\n"
    "- 'what's in the garage?' → `search` with q=garage to find it, then `get_children`.\n\n"
    "Always cite paths like 'Garage / Workbench / Tool drawer'. Aggregate counts "
    "across locations when the user asks 'how many'. Keep answers short — one to "
    "three sentences for simple queries.\n\n"
    "Write tools (add_node, update_node, move_node, delete_node, add_tag, "
    "remove_tag, set_property) are available, but DO NOT call them unless the "
    "user explicitly asks you to. For destructive actions (delete, cascade), "
    "describe what you're about to do in your final answer before calling — the "
    "user will re-issue if they want it done.\n\n"
    "If you can't find what the user is asking about, say so plainly."
)


@dataclass
class AskResult:
    answer: str
    tier_used: str  # "search" | "local" | "anthropic" | "exhausted"
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    message: Optional[str] = None


def cascade(
    db: Session,
    question: str,
    local_provider: LLMProvider,
    cloud_provider: Optional[LLMProvider] = None,
    max_iterations: int = 8,
) -> AskResult:
    """Run the literal-search → local-LLM → cloud cascade."""

    tier1 = literal_search(db, question)
    if tier1 is not None:
        return tier1

    tools = build_inventory_tools()

    local_text, local_traces = run_tool_loop(
        provider=local_provider,
        question=question,
        db=db,
        tools=tools,
        max_iterations=max_iterations,
    )
    if local_text is not None:
        return AskResult(answer=local_text, tier_used="local", tool_calls=local_traces)

    if cloud_provider is not None:
        cloud_text, cloud_traces = run_tool_loop(
            provider=cloud_provider,
            question=question,
            db=db,
            tools=tools,
            max_iterations=max_iterations,
        )
        if cloud_text is not None:
            return AskResult(
                answer=cloud_text, tier_used="anthropic", tool_calls=cloud_traces
            )

    return AskResult(
        answer="I couldn't get an answer for you. Try rephrasing or check the data is loaded.",
        tier_used="exhausted",
        tool_calls=local_traces,
        message="LLM call failed; cloud tier unavailable or also failed",
    )


def literal_search(
    db: Session, question: str, max_results: int = 10
) -> Optional[AskResult]:
    """Tier 1: strip stopwords + FULLTEXT match. Returns None if no matches."""
    keywords = _extract_keywords(question)
    if not keywords:
        return None

    boolean_term = _build_boolean_term(" ".join(keywords))
    if not boolean_term:
        return None

    scores = _fulltext_scores(db, boolean_term)
    if not scores:
        return None

    ranked_ids = sorted(scores, key=lambda nid: (-scores[nid], nid))[:max_results]
    nodes = {
        n.id: n
        for n in db.execute(select(Node).where(Node.id.in_(ranked_ids))).scalars().all()
    }
    paths = _batch_paths(db, ranked_ids)

    lines = [f"Found {len(ranked_ids)} match{'es' if len(ranked_ids) != 1 else ''}:"]
    for nid in ranked_ids:
        node = nodes.get(nid)
        if node is None:
            continue
        chain = " / ".join(n.name for n in paths.get(nid, []))
        lines.append(f"- [{nid}] {node.name} — {chain or node.name}")

    return AskResult(answer="\n".join(lines), tier_used="search")


def run_tool_loop(
    *,
    provider: LLMProvider,
    question: str,
    db: Session,
    tools: list,
    max_iterations: int,
) -> tuple[Optional[str], list[ToolCallTrace]]:
    """Drive the provider's tool_use_loop, capturing every tool call."""
    traces: list[ToolCallTrace] = []

    def on_tool_call(name: str, args: dict[str, Any]) -> str:
        output, is_error = execute_tool(db, name, args)
        traces.append(
            ToolCallTrace(
                tool=name,
                input=dict(args),
                output=_truncate(output, 800),
                is_error=is_error,
            )
        )
        logger.info("ask tool_call: %s %s (error=%s)", name, args, is_error)
        return output

    try:
        result = provider.tool_use_loop(
            messages=[Message(role="user", content=question)],
            tools=tools,
            on_tool_call=on_tool_call,
            system=SYSTEM_PROMPT,
            max_iterations=max_iterations,
        )
    except LLMError as exc:
        logger.warning("ask: tool_use_loop failed via %s: %s", provider.name, exc)
        return None, traces

    return result.text, traces


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _extract_keywords(question: str) -> list[str]:
    keywords: list[str] = []
    for raw in question.split():
        word = "".join(c for c in raw.lower() if c.isalnum())
        if not word or len(word) <= 1 or word in STOPWORDS:
            continue
        keywords.append(word)
    return keywords


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"

"""Conversation history windowing and summarization for Agent context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.services.agent_runner import ChatHistoryMessage

# 传给模型的上下文最多 50 条；超过时把「最近 30 条之前」的内容压成 1 条摘要。
MAX_CONTEXT_MESSAGES = 50
RECENT_KEEP_MESSAGES = 30
SUMMARY_ROLE = "user"
SUMMARY_PREFIX = "[Earlier conversation summary]\n"


Summarizer = Callable[[tuple[ChatHistoryMessage, ...], str | None], str]


@dataclass(frozen=True)
class AgentSummaryState:
    text: str
    covered_message_count: int


@dataclass(frozen=True)
class BuiltAgentHistory:
    messages: tuple[ChatHistoryMessage, ...]
    summary: AgentSummaryState | None


def build_agent_history(
    messages: tuple[ChatHistoryMessage, ...],
    *,
    stored_summary: AgentSummaryState | None = None,
    summarizer: Summarizer | None = None,
) -> BuiltAgentHistory:
    """Build the history slice passed to the Agent runner.

    When total messages <= 50, return all messages.
    When total > 50, return one summary message plus the most recent 30 messages.
    The summary covers every message before the recent window; it is refreshed when
    new messages fall out of that window.
    """
    if len(messages) <= MAX_CONTEXT_MESSAGES:
        return BuiltAgentHistory(messages=messages, summary=stored_summary)

    recent = messages[-RECENT_KEEP_MESSAGES:]
    older_count = len(messages) - RECENT_KEEP_MESSAGES
    older_messages = messages[:older_count]

    summary_state = stored_summary
    if summary_state is None or older_count > summary_state.covered_message_count:
        if summarizer is None:
            summary_text = _fallback_summarize(older_messages, stored_summary.text if stored_summary else None)
        else:
            incremental = messages[summary_state.covered_message_count : older_count] if summary_state else older_messages
            previous = summary_state.text if summary_state else None
            if summary_state and incremental:
                summary_text = summarizer(tuple(incremental), previous)
            else:
                summary_text = summarizer(tuple(older_messages), previous)
        summary_state = AgentSummaryState(text=summary_text, covered_message_count=older_count)

    summary_message = ChatHistoryMessage(
        role=SUMMARY_ROLE,
        content=f"{SUMMARY_PREFIX}{summary_state.text}",
    )
    return BuiltAgentHistory(messages=(summary_message, *recent), summary=summary_state)


def _fallback_summarize(
    messages: tuple[ChatHistoryMessage, ...],
    previous_summary: str | None,
) -> str:
    lines: list[str] = []
    if previous_summary:
        lines.append(previous_summary.strip())
    for item in messages:
        role = item.role
        content = item.content.strip()
        if not content:
            continue
        if role == "tool":
            lines.append(f"- tool: {content[:500]}")
        else:
            lines.append(f"- {role}: {content[:500]}")
    return "\n".join(lines) if lines else "No earlier conversation content."


def format_messages_for_summarization(messages: tuple[ChatHistoryMessage, ...]) -> str:
    parts: list[str] = []
    for item in messages:
        content = item.content.strip()
        if not content:
            continue
        if item.role == "tool":
            parts.append(f"tool: {content}")
        else:
            parts.append(f"{item.role}: {content}")
    return "\n".join(parts)

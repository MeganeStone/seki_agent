from app.services.agent_runner import ChatHistoryMessage
from app.services.conversation_history import (
    RECENT_KEEP_MESSAGES,
    AgentSummaryState,
    build_agent_history,
)


def _messages(count: int) -> tuple[ChatHistoryMessage, ...]:
    return tuple(
        ChatHistoryMessage(role="user" if index % 2 == 0 else "assistant", content=f"m{index}")
        for index in range(count)
    )


def test_build_agent_history_returns_all_when_within_limit() -> None:
    messages = _messages(40)
    built = build_agent_history(messages)
    assert built.messages == messages
    assert built.summary is None


def test_build_agent_history_compresses_when_over_limit() -> None:
    messages = _messages(55)

    def summarizer(chunk: tuple[ChatHistoryMessage, ...], previous: str | None) -> str:
        assert len(chunk) == 25
        return f"summary:{len(chunk)}:{previous or ''}"

    built = build_agent_history(messages, summarizer=summarizer)
    assert len(built.messages) == RECENT_KEEP_MESSAGES + 1
    assert built.messages[0].role == "user"
    assert built.messages[0].content.startswith("[Earlier conversation summary]")
    assert built.messages[1].content == "m25"
    assert built.messages[-1].content == "m54"
    assert built.summary is not None
    assert built.summary.covered_message_count == 25


def test_build_agent_history_reuses_incremental_summary() -> None:
    messages = _messages(61)
    stored = AgentSummaryState(text="old summary", covered_message_count=30)

    def summarizer(chunk: tuple[ChatHistoryMessage, ...], previous: str | None) -> str:
        assert previous == "old summary"
        assert len(chunk) == 1
        return "updated summary"

    built = build_agent_history(messages, stored_summary=stored, summarizer=summarizer)
    assert built.summary is not None
    assert built.summary.text == "updated summary"
    assert built.summary.covered_message_count == 61 - RECENT_KEEP_MESSAGES

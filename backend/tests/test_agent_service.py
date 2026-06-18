import psycopg
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.db.postgres import connect
from app.services.agent_runner import AgentRequest, AgentResponse, AgentStreamEvent, ChatHistoryMessage
from app.services.agent_service import AgentService
from app.services.chat_model_service import ChatModelService
from app.services.rag_service import RagService


@pytest.fixture
def test_db(pg_dsn: str) -> psycopg.Connection:
    conn = connect(pg_dsn)
    try:
        yield conn
    finally:
        conn.close()


def test_agent_service_delegates_to_rag_and_records_messages(test_db: psycopg.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "什么是 TSU？")

    assert response.answer == "runner answer: 什么是 TSU？"
    assert response.route == "test-route"

    rows = test_db.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "什么是 TSU？"),
        ("assistant", "runner answer: 什么是 TSU？"),
    ]


def test_agent_service_conversations_are_owner_isolated(test_db: psycopg.Connection) -> None:
    service = AgentService(test_db, rag_service=RagService(answerer=lambda question: "ok"))
    conversation = service.create_conversation("alice")

    with pytest.raises(HTTPException) as exc_info:
        service.ask("bob", conversation.conversation_id, "hello")

    assert exc_info.value.status_code == 404


def test_agent_service_creates_pending_operation_from_runner_data(test_db: psycopg.Connection) -> None:
    class PendingRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                answer="删除 existing.txt 需要确认。",
                route="code_agent",
                data={
                    "requires_confirmation": True,
                    "operation_type": "delete_path",
                    "agent_name": "code_agent",
                    "path": "existing.txt",
                    "recursive": False,
                },
            )

    service = AgentService(test_db, runner=PendingRunner())
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "delete existing.txt")

    assert response.data is not None
    pending = response.data["pending_operation"]
    assert pending["status"] == "pending"
    assert pending["operation_type"] == "delete_path"
    assert pending["payload"]["path"] == "existing.txt"


def test_agent_service_records_tool_messages_from_runner(test_db: psycopg.Connection) -> None:
    class ToolMessageRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                answer="工具已执行。",
                route="code_agent",
                data={"active_agent": "code_agent"},
                messages_to_store=(ChatHistoryMessage(role="tool", content="code_list_dir: ok"),),
            )

    service = AgentService(test_db, runner=ToolMessageRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "列目录")

    rows = test_db.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "列目录"),
        ("tool", "code_list_dir: ok"),
        ("assistant", "工具已执行。"),
    ]

def test_agent_service_records_ai_tool_call_message_but_hides_it_from_chat_history(
    test_db: psycopg.Connection,
) -> None:
    class ToolCallRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                answer="done",
                route="code_agent",
                data={"active_agent": "code_agent"},
                messages_to_store=(
                    ChatHistoryMessage(
                        role="assistant",
                        content="",
                        metadata={
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "name": "code_list_dir",
                                    "args": {"path": "."},
                                    "type": "tool_call",
                                }
                            ]
                        },
                    ),
                    ChatHistoryMessage(
                        role="tool",
                        content="ok",
                        metadata={"tool_call_id": "call-1", "tool_name": "code_list_dir"},
                    ),
                ),
            )

    service = AgentService(test_db, runner=ToolCallRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "list")

    rows = test_db.execute(
        """
        SELECT role, content, metadata
        FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [row["role"] for row in rows] == ["user", "assistant", "tool", "assistant"]
    assert '"tool_calls"' in rows[1]["metadata"]
    assert '"tool_call_id":"call-1"' in rows[2]["metadata"]

    visible = service.list_messages("alice", conversation.conversation_id)
    assert [(item.role, item.content) for item in visible] == [
        ("user", "list"),
        ("assistant", "done"),
    ]


def test_agent_service_starts_next_turn_from_previous_active_agent(test_db: psycopg.Connection) -> None:
    class SwitchingRunner:
        def __init__(self) -> None:
            self.requests: list[AgentRequest] = []

        def run(self, request: AgentRequest) -> AgentResponse:
            self.requests.append(request)
            return AgentResponse(
                answer="ok",
                route=request.agent_name,
                data={"active_agent": "code_agent"},
            )

    runner = SwitchingRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "进入代码助手")
    service.ask("alice", conversation.conversation_id, "继续")

    assert [request.agent_name for request in runner.requests] == ["main_agent", "code_agent"]


class FakeRunner:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    def run(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        return AgentResponse(
            answer=f"runner answer: {request.message}",
            sources=[],
            data={"task_id": "runner-task", "status": "succeeded"},
            route="test-route",
        )


def test_agent_service_can_inject_runner_boundary(test_db: psycopg.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "hello", use_knowledge_base=False)

    assert response.answer == "runner answer: hello"
    assert response.route == "test-route"
    business_data = {key: value for key, value in response.data.items() if key != "token_usage"}
    assert business_data == {"task_id": "runner-task", "status": "succeeded"}
    assert runner.requests[0] == AgentRequest(
        owner_username="alice",
        conversation_id=conversation.conversation_id,
        message="hello",
        use_knowledge_base=False,
        agent_name="main_agent",
        api_key=None,
        agent_histories={"main_agent": (), "code_agent": ()},
    )


def test_agent_service_passes_request_api_key_to_runner(test_db: psycopg.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "hello", api_key="request-key")

    assert runner.requests[0].api_key == "request-key"


def test_agent_service_passes_web_search_api_key_to_runner(test_db: psycopg.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask(
        "alice",
        conversation.conversation_id,
        "请联网搜索",
        web_search_api_key="volc-key",
    )

    assert runner.requests[0].web_search_api_key == "volc-key"


def test_agent_service_injected_runner_can_chat_without_knowledge_base(test_db: psycopg.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    response = service.ask(
        "alice",
        conversation.conversation_id,
        "hello",
        use_knowledge_base=False,
        api_key="request-key",
    )

    assert response.route == "test-route"
    assert response.answer == "runner answer: hello"
    assert runner.requests[0].use_knowledge_base is False


def test_agent_service_passes_recent_conversation_history_to_runner(test_db: psycopg.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "第一句")
    service.ask("alice", conversation.conversation_id, "第二句")

    assert [item.role for item in runner.requests[1].history] == ["user", "assistant"]
    assert [item.content for item in runner.requests[1].history] == [
        "第一句",
        "runner answer: 第一句",
    ]


def test_agent_service_isolates_history_by_active_agent(test_db: psycopg.Connection) -> None:
    class RecordingRunner:
        def __init__(self) -> None:
            self.requests: list[AgentRequest] = []

        def run(self, request: AgentRequest) -> AgentResponse:
            self.requests.append(request)
            if request.agent_name == "main_agent":
                return AgentResponse(
                    answer="handoff",
                    route="main_agent",
                    data={"active_agent": "code_agent"},
                )
            return AgentResponse(
                answer="code answer",
                route="code_agent",
                data={"active_agent": "code_agent"},
            )

    runner = RecordingRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "请写代码")
    service.ask("alice", conversation.conversation_id, "继续写")

    assert runner.requests[1].agent_name == "code_agent"
    assert runner.requests[1].history == ()
    assert runner.requests[1].agent_histories == {
        "main_agent": (
            ChatHistoryMessage(role="user", content="请写代码"),
            ChatHistoryMessage(role="assistant", content="handoff"),
        ),
        "code_agent": (),
    }


def test_agent_service_passes_separate_histories_for_main_and_code_agents(test_db: psycopg.Connection) -> None:
    class AlternatingRunner:
        def __init__(self) -> None:
            self.requests: list[AgentRequest] = []

        def run(self, request: AgentRequest) -> AgentResponse:
            self.requests.append(request)
            if len(self.requests) == 1:
                return AgentResponse(answer="main one", route="main_agent", data={"active_agent": "code_agent"})
            if len(self.requests) == 2:
                return AgentResponse(answer="code one", route="code_agent", data={"active_agent": "main_agent"})
            return AgentResponse(answer="main two", route="main_agent", data={"active_agent": "main_agent"})

    runner = AlternatingRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "main question")
    service.ask("alice", conversation.conversation_id, "code question")
    service.ask("alice", conversation.conversation_id, "main followup")

    assert runner.requests[2].agent_name == "main_agent"
    assert runner.requests[2].history == (
        ChatHistoryMessage(role="user", content="main question"),
        ChatHistoryMessage(role="assistant", content="main one"),
    )
    assert runner.requests[2].agent_histories == {
        "main_agent": (
            ChatHistoryMessage(role="user", content="main question"),
            ChatHistoryMessage(role="assistant", content="main one"),
        ),
        "code_agent": (
            ChatHistoryMessage(role="user", content="code question"),
            ChatHistoryMessage(role="assistant", content="code one"),
        ),
    }


def test_agent_service_stores_handoff_turn_under_final_answering_agent_when_route_is_generic(
    test_db: psycopg.Connection,
) -> None:
    class FinalCodeRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                answer="code answer",
                route="langgraph",
                data={"active_agent": "code_agent"},
            )

    service = AgentService(test_db, runner=FinalCodeRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "帮我写代码")

    rows = test_db.execute(
        """
        SELECT role, content, agent_name
        FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [(row["role"], row["content"], row["agent_name"]) for row in rows] == [
        ("user", "帮我写代码", "code_agent"),
        ("assistant", "code answer", "code_agent"),
    ]


def test_agent_service_keeps_explicit_main_handoff_decision_under_main_agent(
    test_db: psycopg.Connection,
) -> None:
    class HandoffDecisionRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                answer="handoff",
                route="main_agent",
                data={"active_agent": "code_agent"},
            )

    service = AgentService(test_db, runner=HandoffDecisionRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "帮我写代码")

    rows = test_db.execute(
        """
        SELECT role, content, agent_name
        FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [(row["role"], row["content"], row["agent_name"]) for row in rows] == [
        ("user", "帮我写代码", "main_agent"),
        ("assistant", "handoff", "main_agent"),
    ]


def test_agent_service_includes_tool_messages_in_agent_history(test_db: psycopg.Connection) -> None:
    class ToolThenAnswerRunner:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, request: AgentRequest) -> AgentResponse:
            self.calls += 1
            if self.calls == 1:
                return AgentResponse(
                    answer="已列出目录。",
                    route="code_agent",
                    data={"active_agent": "code_agent"},
                    messages_to_store=(ChatHistoryMessage(role="tool", content="code_list_dir: ok"),),
                )
            assert request.agent_name == "code_agent"
            assert request.history == (
                ChatHistoryMessage(role="user", content="列目录"),
                ChatHistoryMessage(role="tool", content="code_list_dir: ok"),
                ChatHistoryMessage(role="assistant", content="已列出目录。"),
            )
            return AgentResponse(answer="继续处理。", route="code_agent", data={"active_agent": "code_agent"})

    service = AgentService(test_db, runner=ToolThenAnswerRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "列目录")
    service.ask("alice", conversation.conversation_id, "继续")


def test_agent_service_list_messages_hides_tool_messages(test_db: psycopg.Connection) -> None:
    service = AgentService(test_db, runner=FakeRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "hello")

    rows = test_db.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE conversation_id = %s
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [row["role"] for row in rows] == ["user", "assistant"]

    service.chats.add_message(
        "tool-msg",
        conversation.conversation_id,
        "alice",
        "tool",
        "hidden tool output",
        agent_name="code_agent",
    )

    visible = service.list_messages("alice", conversation.conversation_id)
    assert [(item.role, item.content) for item in visible] == [
        ("user", "hello"),
        ("assistant", "runner answer: hello"),
    ]


class FakeTask:
    def __init__(self, task_id: str, status: str = "succeeded") -> None:
        self.task_id = task_id
        self.status = status
        self.result_file_id = "result-file"
        self.error = None
        self.summary = None


class FakeTranslationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str | None]] = []

    def create_task(
        self,
        owner_username: str,
        file_id: str,
        target_language: str,
        api_key: str | None = None,
    ) -> FakeTask:
        self.calls.append((owner_username, file_id, target_language, api_key))
        return FakeTask("translation-task")


class FakeSpiService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_task(self, owner_username: str, file_id: str) -> FakeTask:
        self.calls.append((owner_username, file_id))
        return FakeTask("spi-task")


class FakeDiffService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def create_task(self, owner_username: str, left_file_id: str, right_file_id: str) -> FakeTask:
        self.calls.append((owner_username, left_file_id, right_file_id))
        return FakeTask("diff-task")


def test_agent_service_injected_runner_can_return_translation_tool_data(test_db: psycopg.Connection) -> None:
    translation_service = FakeTranslationService()
    runner = FakeRunner()
    service = AgentService(
        test_db,
        rag_service=RagService(answerer=lambda question: "rag"),
        translation_service=translation_service,
        runner=runner,
    )
    conversation = service.create_conversation("alice")

    response = service.ask(
        "alice",
        conversation.conversation_id,
        "请翻译 file_id=file-1 target_language=英语",
    )

    assert response.answer == "runner answer: 请翻译 file_id=file-1 target_language=英语"
    assert response.route == "test-route"
    business_data = {key: value for key, value in response.data.items() if key != "token_usage"}
    assert business_data == {
        "task_id": "runner-task",
        "status": "succeeded",
    }
    assert translation_service.calls == []


def test_agent_service_injected_runner_keeps_spi_request_boundary(test_db: psycopg.Connection) -> None:
    spi_service = FakeSpiService()
    runner = FakeRunner()
    service = AgentService(
        test_db,
        rag_service=RagService(answerer=lambda question: "rag"),
        spi_service=spi_service,
        runner=runner,
    )
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "解析 SPI file_id=log-1")

    assert response.route == "test-route"
    assert runner.requests[0].message == "解析 SPI file_id=log-1"
    assert spi_service.calls == []


def test_agent_service_injected_runner_keeps_diff_request_boundary(test_db: psycopg.Connection) -> None:
    diff_service = FakeDiffService()
    runner = FakeRunner()
    service = AgentService(
        test_db,
        rag_service=RagService(answerer=lambda question: "rag"),
        diff_service=diff_service,
        runner=runner,
    )
    conversation = service.create_conversation("alice")

    response = service.ask(
        "alice",
        conversation.conversation_id,
        "比较版本 left_file_id=old-1 right_file_id=new-1",
    )

    assert response.route == "test-route"
    assert runner.requests[0].message == "比较版本 left_file_id=old-1 right_file_id=new-1"
    assert diff_service.calls == []


def test_agent_service_builds_summary_history_when_over_limit(test_db: psycopg.Connection) -> None:
    class SummarizingChatModel:
        def summarize_messages(self, messages, previous_summary=None, api_key=None):
            return f"summary:{len(messages)}:{previous_summary or ''}"

    class RecordingRunner:
        def __init__(self) -> None:
            self.requests: list[AgentRequest] = []

        def run(self, request: AgentRequest) -> AgentResponse:
            self.requests.append(request)
            return AgentResponse(answer="ok", route="direct")

    runner = RecordingRunner()
    service = AgentService(test_db, runner=runner, chat_model_service=SummarizingChatModel())
    conversation = service.create_conversation("alice")

    for index in range(51):
        service.ask("alice", conversation.conversation_id, f"message-{index}")

    service.ask("alice", conversation.conversation_id, "message-51")
    last_history = runner.requests[-1].history
    assert last_history[0].content.startswith("[Earlier conversation summary]")
    assert len(last_history) == 31
    assert any(item.content == "message-50" for item in last_history)

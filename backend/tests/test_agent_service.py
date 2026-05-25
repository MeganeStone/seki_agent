import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.db.sqlite import connect
from app.services.agent_runner import AgentRequest, AgentResponse, ChatHistoryMessage
from app.services.agent_service import AgentService
from app.services.chat_model_service import ChatModelService
from app.services.rag_service import RagService


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    try:
        yield conn
    finally:
        conn.close()


def test_agent_service_delegates_to_rag_and_records_messages(test_db: sqlite3.Connection) -> None:
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
        WHERE conversation_id = ?
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "什么是 TSU？"),
        ("assistant", "runner answer: 什么是 TSU？"),
    ]


def test_agent_service_conversations_are_owner_isolated(test_db: sqlite3.Connection) -> None:
    service = AgentService(test_db, rag_service=RagService(answerer=lambda question: "ok"))
    conversation = service.create_conversation("alice")

    with pytest.raises(HTTPException) as exc_info:
        service.ask("bob", conversation.conversation_id, "hello")

    assert exc_info.value.status_code == 404


def test_agent_service_creates_pending_operation_from_runner_data(test_db: sqlite3.Connection) -> None:
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


def test_agent_service_records_tool_messages_from_runner(test_db: sqlite3.Connection) -> None:
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
        WHERE conversation_id = ?
        ORDER BY created_at
        """,
        (conversation.conversation_id,),
    ).fetchall()
    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "列目录"),
        ("tool", "code_list_dir: ok"),
        ("assistant", "工具已执行。"),
    ]


def test_agent_service_starts_next_turn_from_previous_active_agent(test_db: sqlite3.Connection) -> None:
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


def test_agent_service_can_inject_runner_boundary(test_db: sqlite3.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "hello", use_knowledge_base=False)

    assert response.answer == "runner answer: hello"
    assert response.route == "test-route"
    assert response.data == {"task_id": "runner-task", "status": "succeeded"}
    assert runner.requests == [
        AgentRequest(
            owner_username="alice",
            conversation_id=conversation.conversation_id,
            message="hello",
            use_knowledge_base=False,
            agent_name="main_agent",
            api_key=None,
        )
    ]


def test_agent_service_passes_request_api_key_to_runner(test_db: sqlite3.Connection) -> None:
    runner = FakeRunner()
    service = AgentService(test_db, runner=runner)
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "hello", api_key="request-key")

    assert runner.requests[0].api_key == "request-key"


def test_agent_service_passes_web_search_api_key_to_runner(test_db: sqlite3.Connection) -> None:
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


def test_agent_service_injected_runner_can_chat_without_knowledge_base(test_db: sqlite3.Connection) -> None:
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


def test_agent_service_passes_recent_conversation_history_to_runner(test_db: sqlite3.Connection) -> None:
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


def test_agent_service_injected_runner_can_return_translation_tool_data(test_db: sqlite3.Connection) -> None:
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
    assert response.data == {
        "task_id": "runner-task",
        "status": "succeeded",
    }
    assert translation_service.calls == []


def test_agent_service_injected_runner_keeps_spi_request_boundary(test_db: sqlite3.Connection) -> None:
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


def test_agent_service_injected_runner_keeps_diff_request_boundary(test_db: sqlite3.Connection) -> None:
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

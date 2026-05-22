import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.db.sqlite import connect
from app.services.agent_runner import AgentRequest, AgentResponse
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
    def fake_answerer(question: str) -> dict:
        return {
            "answer": f"agent answer: {question}",
            "sources": [{"file_name": "manual.pdf", "page_number": 1, "snippet": "hello"}],
        }

    service = AgentService(test_db, rag_service=RagService(answerer=fake_answerer))
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "什么是 TSU？")

    assert response.answer == "agent answer: 什么是 TSU？"
    assert response.sources[0].file_name == "manual.pdf"

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
        ("assistant", "agent answer: 什么是 TSU？"),
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


def test_agent_service_default_runner_can_chat_without_knowledge_base(test_db: sqlite3.Connection, monkeypatch) -> None:
    from app.services import agent_runner_factory

    class FakeChatModelService:
        def answer(self, message: str, api_key: str | None = None) -> dict:
            return {"answer": f"chat answer: {message}:{api_key}", "sources": []}

    monkeypatch.setattr(agent_runner_factory, "ChatModelService", lambda: FakeChatModelService())
    service = AgentService(test_db, rag_service=RagService(answerer=lambda question: "rag"))
    conversation = service.create_conversation("alice")

    response = service.ask(
        "alice",
        conversation.conversation_id,
        "hello",
        use_knowledge_base=False,
        api_key="request-key",
    )

    assert response.route == "direct"
    assert response.answer == "chat answer: hello:request-key"


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


def test_agent_service_default_runner_can_route_translation_tool(test_db: sqlite3.Connection) -> None:
    translation_service = FakeTranslationService()
    service = AgentService(
        test_db,
        rag_service=RagService(answerer=lambda question: "rag"),
        translation_service=translation_service,
    )
    conversation = service.create_conversation("alice")

    response = service.ask(
        "alice",
        conversation.conversation_id,
        "请翻译 file_id=file-1 target_language=英语",
    )

    assert "翻译任务已创建" in response.answer
    assert response.route == "translation"
    assert response.data == {
        "task_id": "translation-task",
        "status": "succeeded",
        "result_file_id": "result-file",
        "error": None,
    }
    assert translation_service.calls == [("alice", "file-1", "英语", None)]


def test_agent_service_default_runner_can_route_spi_tool(test_db: sqlite3.Connection) -> None:
    spi_service = FakeSpiService()
    service = AgentService(
        test_db,
        rag_service=RagService(answerer=lambda question: "rag"),
        spi_service=spi_service,
    )
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "解析 SPI file_id=log-1")

    assert "SPI 解析任务已创建" in response.answer
    assert response.route == "spi"
    assert response.data == {
        "task_id": "spi-task",
        "status": "succeeded",
        "result_file_id": "result-file",
        "error": None,
    }
    assert spi_service.calls == [("alice", "log-1")]


def test_agent_service_default_runner_can_route_diff_tool(test_db: sqlite3.Connection) -> None:
    diff_service = FakeDiffService()
    service = AgentService(
        test_db,
        rag_service=RagService(answerer=lambda question: "rag"),
        diff_service=diff_service,
    )
    conversation = service.create_conversation("alice")

    response = service.ask(
        "alice",
        conversation.conversation_id,
        "比较版本 left_file_id=old-1 right_file_id=new-1",
    )

    assert "版本差分任务已创建" in response.answer
    assert response.route == "diff"
    assert response.data == {
        "task_id": "diff-task",
        "status": "succeeded",
        "summary": None,
        "result_file_id": "result-file",
        "error": None,
    }
    assert diff_service.calls == [("alice", "old-1", "new-1")]

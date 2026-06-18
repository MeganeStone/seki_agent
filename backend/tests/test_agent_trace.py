import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_agent_trace_service, get_auth_service
from app.db.postgres import connect
from app.main import create_app
from app.services.agent_runner import AgentResponse
from app.services.agent_service import AgentService
from app.services.agent_trace_service import AgentTraceService
from app.services.auth_service import AuthService


@pytest.fixture
def test_db(pg_dsn: str) -> psycopg.Connection:
    conn = connect(pg_dsn)
    try:
        yield conn
    finally:
        conn.close()


class UsageRunner:
    def run(self, request) -> AgentResponse:
        return AgentResponse(
            answer="done",
            route="main_agent",
            data={"token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}},
        )


class FailingRunner:
    def run(self, request) -> AgentResponse:
        raise RuntimeError("model exploded")


def test_ask_records_trace_run_with_usage(test_db: psycopg.Connection) -> None:
    service = AgentService(test_db, runner=UsageRunner())
    conversation = service.create_conversation("alice")

    response = service.ask("alice", conversation.conversation_id, "你好")

    trace = AgentTraceService(test_db)
    runs = trace.list_runs("alice")
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "succeeded"
    assert run.conversation_id == conversation.conversation_id
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert run.total_tokens == 150
    assert run.answer_preview == "done"
    assert run.duration_ms is not None

    detail = trace.get_run_detail("alice", run.run_id)
    assert [event.event_type for event in detail.events] == ["model_call"]
    assert detail.events[0].input_tokens == 100

    usage = (response.data or {}).get("token_usage")
    assert usage["turn_tokens"] == 150
    assert usage["conversation_total_tokens"] == 150


def test_ask_failure_marks_trace_run_failed(test_db: psycopg.Connection) -> None:
    service = AgentService(test_db, runner=FailingRunner())
    conversation = service.create_conversation("alice")

    with pytest.raises(RuntimeError):
        service.ask("alice", conversation.conversation_id, "你好")

    runs = AgentTraceService(test_db).list_runs("alice")
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert "model exploded" in (runs[0].error or "")


def test_conversation_total_tokens_accumulate(test_db: psycopg.Connection) -> None:
    service = AgentService(test_db, runner=UsageRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "第一轮")
    response = service.ask("alice", conversation.conversation_id, "第二轮")

    usage = (response.data or {}).get("token_usage")
    assert usage["conversation_total_tokens"] == 300


def test_token_limit_blocks_and_extend_allows(test_db: psycopg.Connection, monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_conversation_tokens", 200)

    service = AgentService(test_db, runner=UsageRunner())
    conversation = service.create_conversation("alice")

    service.ask("alice", conversation.conversation_id, "第一轮")  # 150 tokens
    service.ask("alice", conversation.conversation_id, "第二轮")  # 300 tokens >= 200

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        service.ask("alice", conversation.conversation_id, "第三轮")
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "token_limit_reached"
    assert exc_info.value.detail["current_limit"] == 200

    extended = service.extend_token_limit("alice", conversation.conversation_id)
    assert extended["multiplier"] == 2
    assert extended["current_limit"] == 400

    response = service.ask("alice", conversation.conversation_id, "第三轮重试")
    assert response.answer == "done"


def test_trace_api_returns_only_own_runs(test_db: psycopg.Connection) -> None:
    service = AgentService(test_db, runner=UsageRunner())
    alice_conv = service.create_conversation("alice")
    bob_conv = service.create_conversation("bob")
    service.ask("alice", alice_conv.conversation_id, "alice 的问题")
    service.ask("bob", bob_conv.conversation_id, "bob 的问题")

    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: AuthService(test_db)
    app.dependency_overrides[get_agent_trace_service] = lambda: AgentTraceService(test_db)
    client = TestClient(app)
    AuthService(test_db).create_user("alice", "secret")
    token = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "secret"}
    ).json()["access_token"]

    listed = client.get("/api/v1/agent-trace/runs", headers={"Authorization": f"Bearer {token}"})

    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["input_preview"] == "alice 的问题"

    detail = client.get(
        f"/api/v1/agent-trace/runs/{items[0]['run_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["run"]["status"] == "succeeded"

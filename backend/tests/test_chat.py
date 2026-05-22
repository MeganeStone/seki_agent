import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_agent_service, get_auth_service
from app.db.sqlite import connect
from app.main import create_app
from app.services.agent_service import AgentService
from app.services.agent_runner import AgentRequest, AgentResponse
from app.services.auth_service import AuthService
from app.services.rag_service import RagService


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client(test_db: sqlite3.Connection) -> TestClient:
    app = create_app()

    class FakeRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                answer=f"answer for: {request.message}",
                sources=[
                    {
                        "file_name": "manual.pdf",
                        "page_number": 3,
                        "snippet": "source snippet",
                    }
                ],
                data={
                    "sources": [
                        {
                            "file_name": "manual.pdf",
                            "page_number": 3,
                            "snippet": "source snippet",
                        }
                    ]
                },
                route="rag",
            )

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_agent_service() -> AgentService:
        return AgentService(test_db, rag_service=RagService(answerer=lambda question: "unused"), runner=FakeRunner())

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_agent_service] = override_agent_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: sqlite3.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_conversation_and_send_message(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)

    conv_response = client.post("/api/v1/chat/conversations", headers=headers)
    assert conv_response.status_code == 200
    conversation_id = conv_response.json()["conversation_id"]

    msg_response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "什么是 TSU？", "use_knowledge_base": True},
    )

    assert msg_response.status_code == 200
    body = msg_response.json()
    assert body["conversation_id"] == conversation_id
    assert body["answer"] == "answer for: 什么是 TSU？"
    assert body["sources"] == [
        {
            "file_name": "manual.pdf",
            "page_number": 3,
            "snippet": "source snippet",
        }
    ]
    assert body["route"] == "rag"
    assert body["data"] == {
        "sources": [
            {
                "file_name": "manual.pdf",
                "page_number": 3,
                "snippet": "source snippet",
            }
        ]
    }


def test_stream_chat_message_returns_delta_and_final_events(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    conv_response = client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = conv_response.json()["conversation_id"]

    with client.stream(
        "POST",
        f"/api/v1/chat/conversations/{conversation_id}/messages/stream",
        headers=headers,
        json={"message": "什么是 TSU？", "use_knowledge_base": True},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "event: delta" in body
    assert "event: final" in body
    assert '"answer":"answer for: 什么是 TSU？"' in body


def test_chat_conversations_are_isolated_by_user(client: TestClient, test_db: sqlite3.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")
    conv_response = client.post("/api/v1/chat/conversations", headers=alice_headers)
    conversation_id = conv_response.json()["conversation_id"]

    bob_response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=bob_headers,
        json={"message": "hello", "use_knowledge_base": True},
    )

    assert bob_response.status_code == 404


def test_chat_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/chat/conversations")

    assert response.status_code == 401


def test_chat_rejects_empty_message(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    conv_response = client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = conv_response.json()["conversation_id"]

    response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "", "use_knowledge_base": True},
    )

    assert response.status_code == 422


def test_chat_accepts_request_api_key(test_db: sqlite3.Connection) -> None:
    app = create_app()
    seen_requests: list[AgentRequest] = []

    class RecordingRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            seen_requests.append(request)
            return AgentResponse(answer="ok", route="direct")

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_agent_service() -> AgentService:
        return AgentService(test_db, runner=RecordingRunner())

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_agent_service] = override_agent_service
    client = TestClient(app)
    headers = auth_headers(client, test_db)
    conv_response = client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = conv_response.json()["conversation_id"]

    response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "hello", "use_knowledge_base": True, "api_key": "request-key"},
    )

    assert response.status_code == 200
    assert seen_requests[0].api_key == "request-key"


def test_chat_accepts_request_web_search_api_key(test_db: sqlite3.Connection) -> None:
    app = create_app()
    seen_requests: list[AgentRequest] = []

    class RecordingRunner:
        def run(self, request: AgentRequest) -> AgentResponse:
            seen_requests.append(request)
            return AgentResponse(answer="ok", route="web_search")

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_agent_service() -> AgentService:
        return AgentService(test_db, runner=RecordingRunner())

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_agent_service] = override_agent_service
    client = TestClient(app)
    headers = auth_headers(client, test_db)
    conv_response = client.post("/api/v1/chat/conversations", headers=headers)
    conversation_id = conv_response.json()["conversation_id"]

    response = client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "hello", "use_knowledge_base": True, "web_search_api_key": "volc-key"},
    )

    assert response.status_code == 200
    assert seen_requests[0].web_search_api_key == "volc-key"

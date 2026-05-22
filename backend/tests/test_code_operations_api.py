import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_code_operation_service
from app.db.sqlite import connect
from app.main import create_app
from app.repositories.chat_repository import ChatRepository
from app.services.auth_service import AuthService
from app.services.code_operation_service import CodeOperationService


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

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_code_operation_service() -> CodeOperationService:
        return CodeOperationService(test_db)

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_code_operation_service] = override_code_operation_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: sqlite3.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_conversation(conn: sqlite3.Connection, owner: str = "alice", conversation_id: str = "conv-1") -> None:
    chats = ChatRepository(conn)
    chats.initialize()
    chats.create_conversation(conversation_id, owner)


def test_list_and_cancel_code_operation_api(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    create_conversation(test_db)
    service = CodeOperationService(test_db)
    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="delete_path",
        payload={"path": "existing.txt"},
    )

    list_response = client.get(
        "/api/v1/code-operations?conversation_id=conv-1&status=pending",
        headers=headers,
    )
    cancel_response = client.post(
        f"/api/v1/code-operations/{created.operation_id}/cancel",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["operation_id"] == created.operation_id
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_code_operation_api_requires_owner(client: TestClient, test_db: sqlite3.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")
    create_conversation(test_db)
    service = CodeOperationService(test_db)
    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="delete_path",
        payload={"path": "existing.txt"},
    )

    alice_response = client.get(f"/api/v1/code-operations/{created.operation_id}", headers=alice_headers)
    bob_response = client.get(f"/api/v1/code-operations/{created.operation_id}", headers=bob_headers)

    assert alice_response.status_code == 200
    assert bob_response.status_code == 404

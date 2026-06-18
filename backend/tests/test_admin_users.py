from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_user_admin_service
from app.db.postgres import connect
from app.main import create_app
from app.repositories.chat_repository import ChatRepository
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.user_admin_service import UserAdminService


@pytest.fixture
def test_db(pg_dsn: str) -> psycopg.Connection:
    conn = connect(pg_dsn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client(test_db: psycopg.Connection, tmp_path: Path) -> TestClient:
    app = create_app()

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_user_admin_service() -> UserAdminService:
        return UserAdminService(test_db, workspace_dir=tmp_path / "workspace")

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_user_admin_service] = override_user_admin_service
    return TestClient(app)


def login_headers(client: TestClient, test_db: psycopg.Connection, username: str, is_admin: bool) -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret", is_admin=is_admin)
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_can_list_create_and_delete_users(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = login_headers(client, test_db, "boss", is_admin=True)

    created = client.post(
        "/api/v1/admin/users",
        json={"username": "worker", "password": "pw", "is_admin": False},
        headers=headers,
    )
    listed = client.get("/api/v1/admin/users", headers=headers)
    deleted = client.delete("/api/v1/admin/users/worker", headers=headers)
    listed_after = client.get("/api/v1/admin/users", headers=headers)

    assert created.status_code == 201
    assert created.json()["username"] == "worker"
    assert {item["username"] for item in listed.json()["items"]} == {"boss", "worker"}
    assert deleted.status_code == 204
    assert {item["username"] for item in listed_after.json()["items"]} == {"boss"}


def test_non_admin_cannot_access_admin_api(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = login_headers(client, test_db, "plain", is_admin=False)

    listed = client.get("/api/v1/admin/users", headers=headers)
    created = client.post(
        "/api/v1/admin/users",
        json={"username": "x", "password": "y"},
        headers=headers,
    )

    assert listed.status_code == 403
    assert created.status_code == 403


def test_admin_cannot_delete_self(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = login_headers(client, test_db, "boss", is_admin=True)

    response = client.delete("/api/v1/admin/users/boss", headers=headers)

    assert response.status_code == 409


def test_delete_user_cascades_owned_data(test_db: psycopg.Connection, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    auth = AuthService(test_db)
    auth.create_user("boss", "secret", is_admin=True)
    auth.create_user("victim", "secret")

    file_service = FileService(test_db, workspace_dir=workspace)
    file_service.save_generated_content("victim", "data.txt", b"abc")
    chats = ChatRepository(test_db)
    chats.initialize()
    chats.create_conversation("conv-v", "victim")
    chats.add_message("m1", "conv-v", "victim", "user", "hello")

    service = UserAdminService(test_db, workspace_dir=workspace)
    service.delete_user("victim", acting_username="boss")

    assert test_db.execute("SELECT 1 FROM users WHERE username = 'victim'").fetchone() is None
    assert test_db.execute("SELECT 1 FROM files WHERE owner_username = 'victim'").fetchone() is None
    assert test_db.execute("SELECT 1 FROM conversations WHERE owner_username = 'victim'").fetchone() is None
    assert test_db.execute("SELECT 1 FROM chat_messages WHERE owner_username = 'victim'").fetchone() is None
    assert not (workspace / "victim").exists()


def test_login_response_includes_admin_flag(client: TestClient, test_db: psycopg.Connection) -> None:
    AuthService(test_db).create_user("boss", "secret", is_admin=True)

    response = client.post("/api/v1/auth/login", json={"username": "boss", "password": "secret"})

    assert response.status_code == 200
    assert response.json()["user"]["is_admin"] is True

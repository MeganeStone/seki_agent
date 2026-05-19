import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_file_service
from app.db.sqlite import connect
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.file_service import FileService


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client(test_db: sqlite3.Connection, tmp_path: Path) -> TestClient:
    app = create_app()
    workspace_dir = tmp_path / "workspace"

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_file_service() -> FileService:
        return FileService(test_db, workspace_dir=workspace_dir, max_upload_size_bytes=20)

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_file_service] = override_file_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: sqlite3.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_list_download_and_delete_file(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)

    upload_response = client.post(
        "/api/v1/files",
        headers=headers,
        files={"file": ("hello.txt", b"hello", "text/plain")},
    )
    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["filename"] == "hello.txt"
    assert uploaded["size"] == 5

    list_response = client.get("/api/v1/files", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == uploaded["id"]

    download_response = client.get(f"/api/v1/files/{uploaded['id']}/download", headers=headers)
    assert download_response.status_code == 200
    assert download_response.content == b"hello"

    delete_response = client.delete(f"/api/v1/files/{uploaded['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    missing_response = client.get(f"/api/v1/files/{uploaded['id']}/download", headers=headers)
    assert missing_response.status_code == 404


def test_files_are_isolated_by_user(client: TestClient, test_db: sqlite3.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")

    upload_response = client.post(
        "/api/v1/files",
        headers=alice_headers,
        files={"file": ("hello.txt", b"hello", "text/plain")},
    )
    file_id = upload_response.json()["id"]

    bob_download = client.get(f"/api/v1/files/{file_id}/download", headers=bob_headers)
    assert bob_download.status_code == 404


def test_upload_rejects_file_over_limit(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)

    response = client.post(
        "/api/v1/files",
        headers=headers,
        files={"file": ("large.bin", b"x" * 21, "application/octet-stream")},
    )

    assert response.status_code == 413


def test_files_require_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/files")

    assert response.status_code == 401


import io
import psycopg
import tarfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_diff_service, get_file_service
from app.db.postgres import connect
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.diff_service import DiffService
from app.services.file_service import FileService


@pytest.fixture
def test_db(pg_dsn: str) -> psycopg.Connection:
    conn = connect(pg_dsn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def client(test_db: psycopg.Connection, workspace_dir: Path, tmp_path: Path) -> TestClient:
    app = create_app()

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_file_service() -> FileService:
        return FileService(test_db, workspace_dir=workspace_dir)

    def override_diff_service() -> DiffService:
        file_service = FileService(test_db, workspace_dir=workspace_dir)

        def fake_compare(left_path: Path, right_path: Path, left_name: str, right_name: str, task_id: str) -> str:
            return f"=== bin_size.txt diff ===\n--- {left_name}\n+++ {right_name}\n- app 1\n+ app 2\n\nlib_size.txt no diff"

        return DiffService(
            test_db,
            file_service=file_service,
            diff_work_dir=tmp_path / "diff_work",
            comparator=fake_compare,
        )

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_file_service] = override_file_service
    app.dependency_overrides[get_diff_service] = override_diff_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: psycopg.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client: TestClient, headers: dict[str, str], filename: str, content: bytes = b"data") -> str:
    response = client.post(
        "/api/v1/files",
        headers=headers,
        files={"file": (filename, content, "application/gzip")},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_create_and_get_diff_task(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    left_id = upload(client, headers, "old.tar.gz")
    right_id = upload(client, headers, "new.tar.gz")

    response = client.post(
        "/api/v1/diff/tasks",
        headers=headers,
        json={"left_file_id": left_id, "right_file_id": right_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["summary"] == {"changed": True, "bin_changed": True, "lib_changed": False}
    assert body["result_file_id"]
    assert "bin_size.txt diff" in body["result_text"]

    get_response = client.get(f"/api/v1/diff/tasks/{body['task_id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["task_id"] == body["task_id"]


def test_diff_rejects_non_tar_gz(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    left_id = upload(client, headers, "old.zip")
    right_id = upload(client, headers, "new.tar.gz")

    response = client.post(
        "/api/v1/diff/tasks",
        headers=headers,
        json={"left_file_id": left_id, "right_file_id": right_id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "Only .tar.gz archives are supported"


def test_diff_tasks_are_isolated_by_user(client: TestClient, test_db: psycopg.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")
    left_id = upload(client, alice_headers, "old.tar.gz")
    right_id = upload(client, alice_headers, "new.tar.gz")

    create_response = client.post(
        "/api/v1/diff/tasks",
        headers=alice_headers,
        json={"left_file_id": left_id, "right_file_id": right_id},
    )
    task_id = create_response.json()["task_id"]

    bob_response = client.get(f"/api/v1/diff/tasks/{task_id}", headers=bob_headers)

    assert bob_response.status_code == 404


def test_safe_extract_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    destination = tmp_path / "extract"
    destination.mkdir()

    payload = b"bad"
    info = tarfile.TarInfo("../escape.txt")
    info.size = len(payload)
    with tarfile.open(archive, "w:gz") as tar:
        tar.addfile(info, io.BytesIO(payload))

    with pytest.raises(HTTPException) as exc_info:
        DiffService._extract_tar_gz(archive, destination)

    assert exc_info.value.status_code == 400
    assert not (tmp_path / "escape.txt").exists()


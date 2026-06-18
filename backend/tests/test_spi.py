import psycopg
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_file_service, get_spi_service
from app.db.postgres import connect
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.spi_service import SpiService


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

    def override_spi_service() -> SpiService:
        file_service = FileService(test_db, workspace_dir=workspace_dir)

        def fake_parser(task_workspace: Path, logs_dir: str, config_path: str, template_path: str) -> dict:
            output_path = task_workspace / "result.xlsx"
            output_path.write_bytes(b"fake excel")
            return {
                "success": True,
                "message": "ok",
                "output_path": str(output_path),
                "count": 1,
                "types": ["61"],
            }

        return SpiService(
            test_db,
            file_service=file_service,
            spi_work_dir=tmp_path / "spi_work",
            parser=fake_parser,
        )

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_file_service] = override_file_service
    app.dependency_overrides[get_spi_service] = override_spi_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: psycopg.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client: TestClient, headers: dict[str, str], filename: str, content: bytes = b"log") -> str:
    response = client.post(
        "/api/v1/files",
        headers=headers,
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_create_and_get_spi_task(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    file_id = upload(client, headers, "spi.log")

    response = client.post("/api/v1/spi/tasks", headers=headers, json={"file_id": file_id})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["result_file_id"]
    assert body["error"] is None

    get_response = client.get(f"/api/v1/spi/tasks/{body['task_id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["task_id"] == body["task_id"]

    download_response = client.get(f"/api/v1/files/{body['result_file_id']}/download", headers=headers)
    assert download_response.status_code == 200
    assert download_response.content == b"fake excel"


def test_create_spi_task_accepts_multiple_logs(
    test_db: psycopg.Connection,
    workspace_dir: Path,
    tmp_path: Path,
) -> None:
    file_service = FileService(test_db, workspace_dir=workspace_dir)
    first_id = file_service.save_generated_content("alice", "第一.log", b"one").id
    second_id = file_service.save_generated_content("alice", "第二.log", b"two").id
    seen_logs: list[str] = []

    def fake_parser(task_workspace: Path, logs_dir: str, config_path: str, template_path: str) -> dict:
        logs_path = task_workspace / logs_dir
        seen_logs.extend(sorted(path.name for path in logs_path.glob("*.log")))
        output_path = task_workspace / "61_67报文提取结果_20260520_195839.xlsx"
        output_path.write_bytes(b"fake excel")
        return {
            "success": True,
            "message": "ok",
            "output_path": str(output_path),
            "count": 2,
            "types": ["61", "67"],
        }

    service = SpiService(
        test_db,
        file_service=file_service,
        spi_work_dir=tmp_path / "spi_work",
        parser=fake_parser,
    )

    result = service.create_task("alice", [first_id, second_id])

    assert result.status == "succeeded"
    assert result.result_file_id
    assert seen_logs == ["第一.log", "第二.log"]
    result_path, result_name = file_service.get_file_path("alice", result.result_file_id)
    assert result_path.read_bytes() == b"fake excel"
    assert result_name == "61_67报文提取结果_20260520_195839.xlsx"


def test_spi_rejects_non_log_file(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    file_id = upload(client, headers, "spi.txt")

    response = client.post("/api/v1/spi/tasks", headers=headers, json={"file_id": file_id})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "Only .log files are supported"


def test_spi_tasks_are_isolated_by_user(client: TestClient, test_db: psycopg.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")
    file_id = upload(client, alice_headers, "spi.log")

    create_response = client.post("/api/v1/spi/tasks", headers=alice_headers, json={"file_id": file_id})
    task_id = create_response.json()["task_id"]

    bob_response = client.get(f"/api/v1/spi/tasks/{task_id}", headers=bob_headers)

    assert bob_response.status_code == 404

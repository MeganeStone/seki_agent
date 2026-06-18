import psycopg
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_file_service, get_translation_service
from app.db.postgres import connect
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.translation_service import TranslationService


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
def client(
    test_db: psycopg.Connection,
    workspace_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    app = create_app()
    monkeypatch.setenv("TRANSLATE_API_KEY", "test-key")

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_file_service() -> FileService:
        return FileService(test_db, workspace_dir=workspace_dir)

    def override_translation_service() -> TranslationService:
        file_service = FileService(test_db, workspace_dir=workspace_dir)

        def fake_translator(file_name: str, workspace_dir: str, target_language: str) -> str:
            source = Path(workspace_dir) / file_name
            output = Path(workspace_dir) / f"{source.stem}_{target_language}{source.suffix}"
            output.write_bytes(b"translated")
            return f"translated: {output}"

        return TranslationService(
            test_db,
            file_service=file_service,
            translation_work_dir=tmp_path / "translation_work",
            translator=fake_translator,
        )

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_file_service] = override_file_service
    app.dependency_overrides[get_translation_service] = override_translation_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: psycopg.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client: TestClient, headers: dict[str, str], filename: str, content: bytes = b"doc") -> str:
    response = client.post(
        "/api/v1/files",
        headers=headers,
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_create_and_get_translation_task(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    file_id = upload(client, headers, "demo.docx")

    response = client.post(
        "/api/v1/translation/tasks",
        headers=headers,
        json={"file_id": file_id, "target_language": "英语"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["target_language"] == "英语"
    assert body["result_file_id"]
    assert body["error"] is None

    get_response = client.get(f"/api/v1/translation/tasks/{body['task_id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["task_id"] == body["task_id"]

    download_response = client.get(f"/api/v1/files/{body['result_file_id']}/download", headers=headers)
    assert download_response.status_code == 200
    assert download_response.content == b"translated"


def test_translation_requires_target_language(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    file_id = upload(client, headers, "demo.docx")

    response = client.post(
        "/api/v1/translation/tasks",
        headers=headers,
        json={"file_id": file_id},
    )

    assert response.status_code == 422


def test_translation_rejects_unsupported_file(client: TestClient, test_db: psycopg.Connection) -> None:
    headers = auth_headers(client, test_db)
    file_id = upload(client, headers, "demo.txt")

    response = client.post(
        "/api/v1/translation/tasks",
        headers=headers,
        json={"file_id": file_id, "target_language": "英语"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "Only .pptx, .xlsx and .docx files are supported"


def test_translation_requires_api_key(test_db: psycopg.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_service = FileService(test_db, workspace_dir=tmp_path / "workspace")
    file_id = file_service.save_generated_content("alice", "demo.docx", b"doc").id
    monkeypatch.setenv("TRANSLATE_API_KEY", "")

    service = TranslationService(
        test_db,
        file_service=file_service,
        translation_work_dir=tmp_path / "translation_work",
    )

    result = service.create_task("alice", file_id, "英语")

    assert result.status == "failed"
    assert result.error == "请先配置翻译 API key，或在前端输入临时 API key。"


def test_translation_accepts_request_api_key_when_env_is_missing(
    test_db: psycopg.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_service = FileService(test_db, workspace_dir=tmp_path / "workspace")
    file_id = file_service.save_generated_content("alice", "demo.docx", b"doc").id
    monkeypatch.delenv("TRANSLATE_API_KEY", raising=False)
    seen_api_keys: list[str | None] = []

    def fake_translator(file_name: str, workspace_dir: str, target_language: str) -> str:
        seen_api_keys.append(os.environ.get("TRANSLATE_API_KEY"))
        source = Path(workspace_dir) / file_name
        output = Path(workspace_dir) / f"{source.stem}_{target_language}{source.suffix}"
        output.write_bytes(b"translated")
        return "ok"

    service = TranslationService(
        test_db,
        file_service=file_service,
        translation_work_dir=tmp_path / "translation_work",
        translator=fake_translator,
    )
    service.uses_legacy_translator = True

    result = service.create_task("alice", file_id, "英语", api_key="request-key")

    assert result.status == "succeeded"
    assert seen_api_keys == ["request-key"]
    assert "TRANSLATE_API_KEY" not in os.environ


def test_translation_tasks_are_isolated_by_user(client: TestClient, test_db: psycopg.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")
    file_id = upload(client, alice_headers, "demo.docx")

    create_response = client.post(
        "/api/v1/translation/tasks",
        headers=alice_headers,
        json={"file_id": file_id, "target_language": "英语"},
    )
    task_id = create_response.json()["task_id"]

    bob_response = client.get(f"/api/v1/translation/tasks/{task_id}", headers=bob_headers)

    assert bob_response.status_code == 404

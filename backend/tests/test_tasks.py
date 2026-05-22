import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_task_service
from app.db.sqlite import connect
from app.main import create_app
from app.repositories.diff_repository import DiffRepository
from app.repositories.spi_repository import SpiRepository
from app.repositories.translation_repository import TranslationRepository
from app.services.auth_service import AuthService
from app.services.task_service import TaskService


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

    def override_task_service() -> TaskService:
        return TaskService(test_db)

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_task_service] = override_task_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: sqlite3.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_tasks(conn: sqlite3.Connection, owner_username: str = "alice") -> dict[str, str]:
    translations = TranslationRepository(conn)
    spi = SpiRepository(conn)
    diff = DiffRepository(conn)
    translations.initialize()
    spi.initialize()
    diff.initialize()

    translations.create("translation-1", owner_username, "file-1", "英语")
    translations.update_result("translation-1", owner_username, status="succeeded", result_file_id="result-1")
    spi.create("spi-1", owner_username, '["file-2"]')
    spi.update_result("spi-1", owner_username, status="failed", error="parse failed")
    diff.create("diff-1", owner_username, "left-1", "right-1")

    return {
        "translation": "translation-1",
        "spi": "spi-1",
        "diff": "diff-1",
    }


def test_list_tasks_returns_all_task_types_for_current_user(
    client: TestClient,
    test_db: sqlite3.Connection,
) -> None:
    headers = auth_headers(client, test_db)
    seed_tasks(test_db)

    response = client.get("/api/v1/tasks", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["type"] for item in items} == {"translation", "spi", "diff"}
    assert {item["task_id"] for item in items} == {"translation-1", "spi-1", "diff-1"}


def test_list_tasks_is_limited(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    seed_tasks(test_db)

    response = client.get("/api/v1/tasks?limit=2", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_get_task_returns_unified_task_shape(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    task_ids = seed_tasks(test_db)

    response = client.get(f"/api/v1/tasks/{task_ids['translation']}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "translation-1"
    assert body["type"] == "translation"
    assert body["status"] == "succeeded"
    assert body["result_file_id"] == "result-1"
    assert body["error"] is None


def test_tasks_are_isolated_by_user(client: TestClient, test_db: sqlite3.Connection) -> None:
    alice_headers = auth_headers(client, test_db, "alice")
    bob_headers = auth_headers(client, test_db, "bob")
    seed_tasks(test_db, "alice")

    bob_list = client.get("/api/v1/tasks", headers=bob_headers)
    bob_get = client.get("/api/v1/tasks/translation-1", headers=bob_headers)
    alice_get = client.get("/api/v1/tasks/translation-1", headers=alice_headers)

    assert bob_list.status_code == 200
    assert bob_list.json()["items"] == []
    assert bob_get.status_code == 404
    assert alice_get.status_code == 200


def test_cancel_task_updates_pending_task(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    task_ids = seed_tasks(test_db)
    TranslationRepository(test_db).update_result(task_ids["translation"], "alice", status="pending")

    response = client.post(f"/api/v1/tasks/{task_ids['translation']}/cancel", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_ids["translation"]
    assert body["status"] == "cancelled"


def test_cancel_task_keeps_finished_task_status(client: TestClient, test_db: sqlite3.Connection) -> None:
    headers = auth_headers(client, test_db)
    task_ids = seed_tasks(test_db)

    response = client.post(f"/api/v1/tasks/{task_ids['translation']}/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_cancel_task_is_isolated_by_user(client: TestClient, test_db: sqlite3.Connection) -> None:
    bob_headers = auth_headers(client, test_db, "bob")
    task_ids = seed_tasks(test_db, "alice")

    response = client.post(f"/api/v1/tasks/{task_ids['translation']}/cancel", headers=bob_headers)

    assert response.status_code == 404

import psycopg
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_code_operation_service
from app.db.postgres import connect
from app.main import create_app
from app.repositories.code_audit_repository import CodeAuditRepository
from app.services.auth_service import AuthService
from app.services.code_audit_service import _clean_detail, audit_row_to_read
from app.services.code_execution_service import CodeExecutionService
from app.services.code_operation_service import CodeOperationService


@pytest.fixture
def test_db(pg_dsn: str) -> psycopg.Connection:
    conn = connect(pg_dsn)
    try:
        yield conn
    finally:
        conn.close()


def make_service(tmp_path: Path, audit_sink=None) -> CodeExecutionService:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return CodeExecutionService(
        allowed_roots=[workspace],
        default_root=workspace,
        writable_roots=[workspace],
        audit_sink=audit_sink,
    )


def make_db_sink(conn: psycopg.Connection):
    """构造写入指定连接的 sink，模拟 create_default_audit_sink 的落库行为。"""
    repository = CodeAuditRepository(conn)
    repository.initialize()

    def sink(record, detail):
        repository.create(
            record_id=record.operation_id,
            owner_username=record.owner_username,
            conversation_id=record.conversation_id,
            agent_name=record.agent_name,
            tool_name=record.tool_name,
            status=record.status,
            target=record.target,
            message=record.message,
            detail=_clean_detail(detail),
            started_at=record.started_at.isoformat(),
            finished_at=record.finished_at.isoformat(),
        )

    return sink


def test_audit_sink_persists_succeeded_and_rejected_operations(
    tmp_path: Path, test_db: psycopg.Connection
) -> None:
    service = make_service(tmp_path, audit_sink=make_db_sink(test_db))

    write_result = service.write_text_file(
        "note.txt", "hello", owner_username="alice", conversation_id="conv-1"
    )
    rejected_result = service.read_text_file(
        "../outside.txt", owner_username="alice", conversation_id="conv-1"
    )

    assert write_result.status == "succeeded"
    assert rejected_result.status == "rejected"

    rows = CodeAuditRepository(test_db).list_for_owner("alice")
    statuses = {row["tool_name"]: row["status"] for row in rows}
    assert statuses["write_text_file"] == "succeeded"
    assert statuses["read_text_file"] == "rejected"


def test_audit_detail_excludes_file_content(tmp_path: Path, test_db: psycopg.Connection) -> None:
    service = make_service(tmp_path, audit_sink=make_db_sink(test_db))
    (tmp_path / "workspace" / "data.txt").write_text("secret-content", encoding="utf-8")

    result = service.read_text_file("data.txt", owner_username="alice", conversation_id="conv-1")

    assert result.status == "succeeded"
    rows = CodeAuditRepository(test_db).list_for_owner("alice")
    read = audit_row_to_read(rows[0])
    assert read.tool_name == "read_text_file"
    assert read.detail is not None
    assert "content" not in read.detail
    assert read.detail["size"] == len("secret-content")


def test_audit_sink_failure_does_not_break_tool(tmp_path: Path) -> None:
    def broken_sink(record, detail):
        raise RuntimeError("audit db down")

    service = make_service(tmp_path, audit_sink=broken_sink)

    result = service.write_text_file(
        "note.txt", "hello", owner_username="alice", conversation_id="conv-1"
    )

    assert result.status == "succeeded"
    assert (tmp_path / "workspace" / "note.txt").read_text(encoding="utf-8") == "hello"


def test_audit_repository_filters_by_owner_and_conversation(test_db: psycopg.Connection) -> None:
    repository = CodeAuditRepository(test_db)
    repository.initialize()
    for index, (owner, conversation) in enumerate(
        [("alice", "conv-1"), ("alice", "conv-2"), ("bob", "conv-1")]
    ):
        repository.create(
            record_id=f"rec-{index}",
            owner_username=owner,
            conversation_id=conversation,
            agent_name="code_agent",
            tool_name="list_dir",
            status="succeeded",
            target=".",
            message="ok",
            detail=None,
            started_at="2026-06-10T00:00:00+00:00",
            finished_at="2026-06-10T00:00:01+00:00",
        )

    alice_all = repository.list_for_owner("alice")
    alice_conv1 = repository.list_for_owner("alice", conversation_id="conv-1")

    assert {row["id"] for row in alice_all} == {"rec-0", "rec-1"}
    assert [row["id"] for row in alice_conv1] == ["rec-0"]


@pytest.fixture
def client(test_db: psycopg.Connection) -> TestClient:
    app = create_app()

    def override_auth_service() -> AuthService:
        return AuthService(test_db)

    def override_code_operation_service() -> CodeOperationService:
        return CodeOperationService(test_db)

    app.dependency_overrides[get_auth_service] = override_auth_service
    app.dependency_overrides[get_code_operation_service] = override_code_operation_service
    return TestClient(app)


def auth_headers(client: TestClient, test_db: psycopg.Connection, username: str = "alice") -> dict[str, str]:
    AuthService(test_db).create_user(username, "secret")
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "secret"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_audit_api_returns_only_current_user_records(
    client: TestClient, test_db: psycopg.Connection
) -> None:
    headers = auth_headers(client, test_db, "alice")
    repository = CodeAuditRepository(test_db)
    repository.initialize()
    repository.create(
        record_id="rec-alice",
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        tool_name="delete_path",
        status="succeeded",
        target="old.txt",
        message="文件删除成功。",
        detail={"recursive": False},
        started_at="2026-06-10T00:00:00+00:00",
        finished_at="2026-06-10T00:00:01+00:00",
    )
    repository.create(
        record_id="rec-bob",
        owner_username="bob",
        conversation_id="conv-9",
        agent_name="code_agent",
        tool_name="delete_path",
        status="succeeded",
        target="bob.txt",
        message="文件删除成功。",
        detail=None,
        started_at="2026-06-10T00:00:00+00:00",
        finished_at="2026-06-10T00:00:01+00:00",
    )

    response = client.get("/api/v1/code-operations/audit", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["record_id"] for item in items] == ["rec-alice"]
    assert items[0]["tool_name"] == "delete_path"
    assert items[0]["detail"] == {"recursive": False}

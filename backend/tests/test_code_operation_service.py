import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.db.sqlite import connect
from app.repositories.chat_repository import ChatRepository
from app.services.code_agent_tools import CodeAgentFileTool
from app.services.code_execution_service import CodeExecutionService
from app.services.code_operation_service import CodeOperationService


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "test.db")
    try:
        yield conn
    finally:
        conn.close()


def create_conversation(conn: sqlite3.Connection, owner: str = "alice", conversation_id: str = "conv-1") -> None:
    chats = ChatRepository(conn)
    chats.initialize()
    chats.create_conversation(conversation_id, owner)


def test_create_and_list_pending_operation_for_owner(test_db: sqlite3.Connection) -> None:
    create_conversation(test_db)
    service = CodeOperationService(test_db)

    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="delete_path",
        payload={"path": "existing.txt", "recursive": False},
    )

    listed = service.list_operations("alice", conversation_id="conv-1", operation_status="pending")
    assert listed == [created]
    assert service.list_operations("bob") == []


def test_cancel_pending_operation(test_db: sqlite3.Connection) -> None:
    create_conversation(test_db)
    service = CodeOperationService(test_db)
    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="delete_path",
        payload={"path": "existing.txt", "recursive": False},
    )

    cancelled = service.cancel_operation("alice", created.operation_id)

    assert cancelled.status == "cancelled"
    assert cancelled.result is not None
    assert cancelled.result.message == "用户已取消该操作。"


def test_confirm_delete_path_executes_and_records_message(test_db: sqlite3.Connection, tmp_path: Path) -> None:
    create_conversation(test_db)
    root = tmp_path / "project"
    root.mkdir()
    existing = root / "existing.txt"
    existing.write_text("remove me", encoding="utf-8")
    execution = CodeExecutionService(allowed_roots=[root], default_root=root)
    service = CodeOperationService(test_db, file_tool=CodeAgentFileTool(execution))
    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="delete_path",
        payload={"path": "existing.txt", "recursive": False},
    )

    confirmed = service.confirm_operation("alice", created.operation_id)

    assert confirmed.status == "executed"
    assert confirmed.result is not None
    assert confirmed.result.status == "succeeded"
    assert not existing.exists()
    cursor = test_db.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("conv-1",),
    )
    row = cursor.fetchone()
    assert row["role"] == "assistant"
    assert "待确认操作已执行" in row["content"]


def test_confirm_unknown_command_does_not_execute_yet(test_db: sqlite3.Connection, tmp_path: Path) -> None:
    create_conversation(test_db)
    root = tmp_path / "project"
    root.mkdir()
    execution = CodeExecutionService(allowed_roots=[root], default_root=root)
    service = CodeOperationService(test_db, file_tool=CodeAgentFileTool(execution))
    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="run_allowed_command",
        payload={"command": "whoami", "args": []},
    )

    confirmed = service.confirm_operation("alice", created.operation_id)

    assert confirmed.status == "failed"
    assert confirmed.result is not None
    assert confirmed.result.status == "failed"
    assert confirmed.result.message == "该命令已确认，但未匹配确认后可执行的配置前缀。"


def test_operation_owner_isolated(test_db: sqlite3.Connection) -> None:
    create_conversation(test_db)
    service = CodeOperationService(test_db)
    created = service.create_pending_from_result(
        owner_username="alice",
        conversation_id="conv-1",
        agent_name="code_agent",
        operation_type="delete_path",
        payload={"path": "existing.txt", "recursive": False},
    )

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_operation("bob", created.operation_id)

    assert exc_info.value.status_code == 404

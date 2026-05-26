from pathlib import Path

from app.db.sqlite import connect
from app.repositories.chat_repository import ChatRepository
from app.services.code_agent_tools import CodeAgentFileTool
from app.services.code_execution_service import CodeExecutionService
from app.services.code_langchain_tool_adapter import create_code_langchain_tools
from app.services.code_operation_service import CodeOperationService


def test_create_code_langchain_tools_wraps_restricted_file_service(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("hello", encoding="utf-8")
    service = CodeExecutionService(allowed_roots=[root], default_root=root)
    tools = create_code_langchain_tools(
        file_tool=CodeAgentFileTool(service),
        owner_username="alice",
        conversation_id="conv-1",
    )
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {
        "code_list_dir",
        "code_create_dir",
        "code_read_text_file",
        "code_write_text_file",
        "code_run_python_script",
        "code_run_allowed_command",
        "code_delete_path",
    }
    assert "shell" in by_name["code_write_text_file"].description
    assert "README.md" in by_name["code_list_dir"].invoke({"path": ".", "limit": 10})
    assert "content:\nhello" in by_name["code_read_text_file"].invoke({"path": "README.md"})

    write_result = by_name["code_write_text_file"].invoke(
        {"path": "notes.txt", "content": "new file", "overwrite": False}
    )

    assert "status=succeeded" in write_result
    assert (root / "notes.txt").read_text(encoding="utf-8") == "new file"
    assert service.audit_records[-1].owner_username == "alice"
    assert service.audit_records[-1].conversation_id == "conv-1"
    assert service.audit_records[-1].agent_name == "code_agent"

    script = root / "hello.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    run_result = by_name["code_run_python_script"].invoke(
        {"path": "hello.py", "script_args": [], "timeout_seconds": 5}
    )

    assert "status=succeeded" in run_result
    assert "stdout:\nhello\n" in run_result

    command_result = by_name["code_run_allowed_command"].invoke(
        {"command": "python", "command_args": ["-m", "pytest", "--version"], "timeout_seconds": 10}
    )

    assert "status=succeeded" in command_result
    assert "pytest" in command_result.lower()

    create_dir_result = by_name["code_create_dir"].invoke({"path": "scratch"})
    delete_dir_result = by_name["code_delete_path"].invoke({"path": "scratch", "recursive": True})

    assert "status=succeeded" in create_dir_result
    assert "status=succeeded" in delete_dir_result
    assert not (root / "scratch").exists()


def test_code_tools_do_not_expose_delete_or_shell(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    tools = create_code_langchain_tools(
        file_tool=CodeAgentFileTool(CodeExecutionService(allowed_roots=[root], default_root=root)),
        owner_username="alice",
        conversation_id="conv-1",
    )

    names = {tool.name for tool in tools}

    assert "delete_file" not in names
    assert "execute_shell" not in names
    assert "run_command" not in names
    assert "execute_shell" not in by_name_descriptions(tools)


def by_name_descriptions(tools) -> str:
    return "\n".join(tool.description for tool in tools)


def test_code_tool_deletes_existing_workspace_file_without_pending_operation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "existing.txt").write_text("keep", encoding="utf-8")
    conn = connect(tmp_path / "test.db")
    try:
        chats = ChatRepository(conn)
        chats.initialize()
        chats.create_conversation("conv-1", "alice")
        operation_service = CodeOperationService(conn)
        tools = create_code_langchain_tools(
            file_tool=CodeAgentFileTool(CodeExecutionService(allowed_roots=[root], default_root=root)),
            owner_username="alice",
            conversation_id="conv-1",
            operation_service=operation_service,
        )
        by_name = {tool.name: tool for tool in tools}

        result = by_name["code_delete_path"].invoke({"path": "existing.txt", "recursive": False})

        operations = operation_service.list_operations("alice", conversation_id="conv-1", operation_status="pending")
        assert "status=succeeded" in result
        assert operations == []
        assert not (root / "existing.txt").exists()
    finally:
        conn.close()


def test_code_tool_creates_pending_operation_for_unknown_command(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    conn = connect(tmp_path / "test.db")
    try:
        chats = ChatRepository(conn)
        chats.initialize()
        chats.create_conversation("conv-1", "alice")
        operation_service = CodeOperationService(conn)
        tools = create_code_langchain_tools(
            file_tool=CodeAgentFileTool(CodeExecutionService(allowed_roots=[root], default_root=root)),
            owner_username="alice",
            conversation_id="conv-1",
            operation_service=operation_service,
        )
        by_name = {tool.name: tool for tool in tools}

        result = by_name["code_run_allowed_command"].invoke(
            {"command": "whoami", "command_args": [], "timeout_seconds": 10}
        )

        operations = operation_service.list_operations("alice", conversation_id="conv-1", operation_status="pending")
        assert "status=requires_confirmation" in result
        assert f"pending_operation_id={operations[0].operation_id}" in result
        assert operations[0].operation_type == "run_allowed_command"
        assert operations[0].payload["command"] == "whoami"
    finally:
        conn.close()

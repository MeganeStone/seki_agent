from pathlib import Path

import sys

from app.services.code_execution_service import CodeExecutionService


def service(tmp_path: Path, **kwargs) -> CodeExecutionService:
    root = tmp_path / "project"
    root.mkdir()
    return CodeExecutionService(allowed_roots=[root], default_root=root, **kwargs)


def service_with_policy(tmp_path: Path, allowed_prefixes=None, confirmed_prefixes=None, **kwargs) -> CodeExecutionService:
    svc = service(tmp_path, **kwargs)
    svc.command_policy.allowed_prefixes = [
        [part.lower() for part in prefix.split()]
        for prefix in (allowed_prefixes or [])
    ]
    svc.command_policy.confirmed_prefixes = [
        [part.lower() for part in prefix.split()]
        for prefix in (confirmed_prefixes or [])
    ]
    return svc


def test_list_dir_returns_entries_and_records_audit(tmp_path: Path) -> None:
    svc = service(tmp_path)
    (tmp_path / "project" / "src").mkdir()
    (tmp_path / "project" / "README.md").write_text("hello", encoding="utf-8")

    result = svc.list_dir(".", owner_username="alice", conversation_id="conv-1")

    assert result.status == "succeeded"
    assert result.message == "列出 2 个条目。"
    assert [item["name"] for item in result.data["items"]] == ["src", "README.md"]
    assert svc.audit_records[-1].tool_name == "list_dir"
    assert svc.audit_records[-1].owner_username == "alice"
    assert svc.audit_records[-1].conversation_id == "conv-1"


def test_list_dir_rejects_path_outside_allowed_roots(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.list_dir(str(tmp_path.parent))

    assert result.status == "rejected"
    assert result.message == "该路径不在允许的工作目录内。"


def test_read_text_file_returns_content(tmp_path: Path) -> None:
    svc = service(tmp_path)
    (tmp_path / "project" / "note.txt").write_text("hello", encoding="utf-8")

    result = svc.read_text_file("note.txt")

    assert result.status == "succeeded"
    assert result.data["content"] == "hello"
    assert result.data["size"] == 5


def test_read_text_file_rejects_large_file(tmp_path: Path) -> None:
    svc = service(tmp_path, max_read_bytes=4)
    (tmp_path / "project" / "note.txt").write_text("hello", encoding="utf-8")

    result = svc.read_text_file("note.txt")

    assert result.status == "rejected"
    assert result.message == "文件超过当前读取限制。"
    assert result.data["max_bytes"] == 4


def test_read_text_file_rejects_non_utf8_file(tmp_path: Path) -> None:
    svc = service(tmp_path)
    (tmp_path / "project" / "binary.bin").write_bytes(b"\xff\xfe\x00")

    result = svc.read_text_file("binary.bin")

    assert result.status == "failed"
    assert result.message == "文件不是 UTF-8 文本，当前只支持读取文本文件。"


def test_write_text_file_creates_new_file(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.write_text_file("scripts/task.py", "print('ok')")

    assert result.status == "rejected"
    assert result.message == "父目录不存在或不是目录。"

    (tmp_path / "project" / "scripts").mkdir()
    result = svc.write_text_file("scripts/task.py", "print('ok')")

    assert result.status == "succeeded"
    assert (tmp_path / "project" / "scripts" / "task.py").read_text(encoding="utf-8") == "print('ok')"
    assert result.data["overwrite"] is False


def test_write_text_file_requires_explicit_overwrite(tmp_path: Path) -> None:
    svc = service(tmp_path)
    path = tmp_path / "project" / "note.txt"
    path.write_text("old", encoding="utf-8")

    result = svc.write_text_file("note.txt", "new")

    assert result.status == "rejected"
    assert result.message == "目标文件已存在，覆盖写入需要显式 overwrite=true。"
    assert path.read_text(encoding="utf-8") == "old"

    overwrite_result = svc.write_text_file("note.txt", "new", overwrite=True)

    assert overwrite_result.status == "succeeded"
    assert path.read_text(encoding="utf-8") == "new"


def test_delete_agent_created_file_without_confirmation(tmp_path: Path) -> None:
    svc = service(tmp_path)
    svc.write_text_file("generated.txt", "temp")

    result = svc.delete_path("generated.txt")

    assert result.status == "succeeded"
    assert result.message == "文件删除成功。"
    assert not (tmp_path / "project" / "generated.txt").exists()
    assert svc.audit_records[-1].tool_name == "delete_path"


def test_delete_existing_workspace_file_without_confirmation(tmp_path: Path) -> None:
    svc = service(tmp_path)
    existing = tmp_path / "project" / "existing.txt"
    existing.write_text("keep", encoding="utf-8")

    result = svc.delete_path("existing.txt")

    assert result.status == "succeeded"
    assert result.message == "文件删除成功。"
    assert not existing.exists()


def test_delete_rejects_read_only_allowed_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workspace_root = tmp_path / "workspace" / "alice"
    project_root.mkdir()
    workspace_root.mkdir(parents=True)
    existing = project_root / "existing.txt"
    existing.write_text("keep", encoding="utf-8")
    svc = CodeExecutionService(
        allowed_roots=[workspace_root, project_root],
        default_root=workspace_root,
        writable_roots=[workspace_root],
    )

    result = svc.delete_path(str(existing))

    assert result.status == "rejected"
    assert result.message == "该路径不在 code agent 的可写工作目录内。"
    assert existing.exists()


def test_create_and_delete_agent_created_directory(tmp_path: Path) -> None:
    svc = service(tmp_path)
    create_result = svc.create_dir("scratch")
    (tmp_path / "project" / "scratch" / "note.txt").write_text("temp", encoding="utf-8")

    non_recursive_result = svc.delete_path("scratch")
    recursive_result = svc.delete_path("scratch", recursive=True)

    assert create_result.status == "succeeded"
    assert non_recursive_result.status == "rejected"
    assert non_recursive_result.message == "删除目录需要显式 recursive=true。"
    assert recursive_result.status == "succeeded"
    assert recursive_result.message == "目录删除成功。"
    assert not (tmp_path / "project" / "scratch").exists()


def test_delete_nested_file_in_agent_created_directory(tmp_path: Path) -> None:
    svc = service(tmp_path)
    svc.create_dir("scratch")
    nested = tmp_path / "project" / "scratch" / "note.txt"
    nested.write_text("temp", encoding="utf-8")

    result = svc.delete_path("scratch/note.txt")

    assert result.status == "succeeded"
    assert not nested.exists()


def test_write_text_file_rejects_large_content(tmp_path: Path) -> None:
    svc = service(tmp_path, max_write_bytes=4)

    result = svc.write_text_file("note.txt", "hello")

    assert result.status == "rejected"
    assert result.message == "写入内容超过当前大小限制。"


def test_write_text_file_rejects_outside_allowed_root(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.write_text_file(str(tmp_path / "outside.txt"), "nope")

    assert result.status == "rejected"
    assert result.message == "该路径不在允许的工作目录内。"


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    svc = service(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = tmp_path / "project" / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        return

    result = svc.read_text_file("link/secret.txt")

    assert result.status == "rejected"
    assert result.message == "该路径不在允许的工作目录内。"


def test_rejects_sensitive_files_by_default(tmp_path: Path) -> None:
    svc = service(tmp_path)
    env_file = tmp_path / "project" / ".env"
    env_file.write_text("SECRET=value", encoding="utf-8")

    read_result = svc.read_text_file(".env")
    write_result = svc.write_text_file(".env", "new", overwrite=True)

    assert read_result.status == "rejected"
    assert read_result.message == "当前阶段不允许 code agent 访问敏感文件。"
    assert write_result.status == "rejected"
    assert write_result.message == "当前阶段不允许 code agent 访问敏感文件。"
    assert env_file.read_text(encoding="utf-8") == "SECRET=value"


def test_every_call_creates_operation_id(tmp_path: Path) -> None:
    svc = service(tmp_path)
    (tmp_path / "project" / "note.txt").write_text("hello", encoding="utf-8")

    first = svc.read_text_file("note.txt")
    second = svc.list_dir(".")

    assert first.data["operation_id"]
    assert second.data["operation_id"]
    assert first.data["operation_id"] != second.data["operation_id"]
    assert len(svc.audit_records) == 2


def test_run_python_script_succeeds_with_args(tmp_path: Path) -> None:
    svc = service(tmp_path)
    script = tmp_path / "project" / "hello.py"
    script.write_text(
        "import sys\nprint('hello ' + sys.argv[1])\n",
        encoding="utf-8",
    )

    result = svc.run_python_script("hello.py", args=["seki"], owner_username="alice", conversation_id="conv-1")

    assert result.status == "succeeded"
    assert result.data["returncode"] == 0
    assert result.data["stdout"] == "hello seki\n"
    assert result.data["stderr"] == ""
    assert svc.audit_records[-1].tool_name == "run_python_script"
    assert svc.audit_records[-1].owner_username == "alice"


def test_run_python_script_reports_failure(tmp_path: Path) -> None:
    svc = service(tmp_path)
    script = tmp_path / "project" / "fail.py"
    script.write_text("import sys\nprint('bad')\nsys.exit(3)\n", encoding="utf-8")

    result = svc.run_python_script("fail.py")

    assert result.status == "failed"
    assert result.message == "Python 脚本执行失败。"
    assert result.data["returncode"] == 3
    assert result.data["stdout"] == "bad\n"


def test_run_python_script_rejects_non_python_file(tmp_path: Path) -> None:
    svc = service(tmp_path)
    (tmp_path / "project" / "note.txt").write_text("hello", encoding="utf-8")

    result = svc.run_python_script("note.txt")

    assert result.status == "rejected"
    assert result.message == "当前只允许运行 .py 脚本。"


def test_run_python_script_times_out(tmp_path: Path) -> None:
    svc = service(tmp_path, default_timeout_seconds=1)
    script = tmp_path / "project" / "sleep.py"
    script.write_text("import time\ntime.sleep(2)\n", encoding="utf-8")

    result = svc.run_python_script("sleep.py", timeout_seconds=1)

    assert result.status == "failed"
    assert result.message == "Python 脚本执行超时。"
    assert result.data["timeout_seconds"] == 1


def test_run_python_script_truncates_output(tmp_path: Path) -> None:
    svc = service(tmp_path, max_output_chars=5)
    script = tmp_path / "project" / "spam.py"
    script.write_text("print('1234567890')\n", encoding="utf-8")

    result = svc.run_python_script("spam.py")

    assert result.status == "succeeded"
    assert result.data["stdout"] == "12345"
    assert result.data["stdout_truncated"] is True


def test_allowed_roots_can_include_shared_skills_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    skills_root = tmp_path / "skills"
    project_root.mkdir()
    skills_root.mkdir()
    (skills_root / "skill.py").write_text("print('skill ok')\n", encoding="utf-8")
    svc = CodeExecutionService(
        allowed_roots=[project_root, skills_root],
        default_root=project_root,
    )

    read_result = svc.read_text_file(str(skills_root / "skill.py"))
    run_result = svc.run_python_script(str(skills_root / "skill.py"))

    assert read_result.status == "succeeded"
    assert read_result.data["content"] == "print('skill ok')\n"
    assert run_result.status == "succeeded"
    assert run_result.data["stdout"] == "skill ok\n"


def test_default_workspace_is_writable_while_project_root_is_read_only(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workspace_root = tmp_path / "workspace" / "alice"
    project_root.mkdir()
    workspace_root.mkdir(parents=True)
    (project_root / "helper.py").write_text("print('project ok')\n", encoding="utf-8")
    svc = CodeExecutionService(
        allowed_roots=[workspace_root, project_root],
        default_root=workspace_root,
        writable_roots=[workspace_root],
    )

    write_result = svc.write_text_file("notes/todo.txt", "hello")
    (workspace_root / "notes").mkdir()
    write_result = svc.write_text_file("notes/todo.txt", "hello")
    read_result = svc.read_text_file(str(project_root / "helper.py"))
    run_result = svc.run_python_script(str(project_root / "helper.py"))
    root_write_result = svc.write_text_file(str(project_root / "new.txt"), "nope")

    assert write_result.status == "succeeded"
    assert (workspace_root / "notes" / "todo.txt").read_text(encoding="utf-8") == "hello"
    assert read_result.status == "succeeded"
    assert run_result.status == "succeeded"
    assert root_write_result.status == "rejected"
    assert root_write_result.message == "该路径不在 code agent 的可写工作目录内。"


def test_run_allowed_command_allows_python_m_pytest(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.run_allowed_command("python", ["-m", "pytest", "--version"])

    assert result.status == "succeeded"
    assert result.data["returncode"] == 0
    assert "pytest" in result.data["stdout"].lower()
    assert svc.audit_records[-1].tool_name == "run_allowed_command"


def test_run_allowed_command_allows_pytest_alias(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.run_allowed_command("pytest", ["--version"])

    assert result.status == "succeeded"
    assert "pytest" in result.data["stdout"].lower()


def test_run_allowed_command_requires_confirmation_for_unknown_command(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.run_allowed_command("whoami", [])

    assert result.status == "requires_confirmation"
    assert result.message == "该命令未在白名单中，执行前需要用户确认。"
    assert result.data["requires_confirmation"] is True
    assert result.data["command"] == "whoami"


def test_run_allowed_command_rejects_dangerous_command(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.run_allowed_command("rm", ["-rf", "."])

    assert result.status == "rejected"
    assert result.message == "该命令被安全策略禁止。"


def test_run_allowed_command_rejects_shell_control_operators(tmp_path: Path) -> None:
    svc = service(tmp_path)

    result = svc.run_allowed_command("python", ["-m", "pytest", "x", "&&", "whoami"])

    assert result.status == "rejected"
    assert result.message == "命令包含未开放的 shell 控制符。"


def test_run_allowed_command_times_out(tmp_path: Path) -> None:
    svc = service(tmp_path, default_timeout_seconds=1)
    (tmp_path / "project" / "test_sleep.py").write_text(
        "import time\n\ndef test_sleep():\n    time.sleep(2)\n",
        encoding="utf-8",
    )

    result = svc.run_allowed_command(
        "pytest",
        ["test_sleep.py"],
        timeout_seconds=1,
    )

    assert result.status == "failed"
    assert result.message == "命令执行超时。"


def test_run_allowed_command_allows_configured_prefix(tmp_path: Path) -> None:
    svc = service_with_policy(tmp_path, allowed_prefixes=["python --version"])

    result = svc.run_allowed_command("python", ["--version"])

    assert result.status == "succeeded"
    assert result.data["returncode"] == 0
    assert "python" in (result.data["stdout"] + result.data["stderr"]).lower()


def test_run_allowed_command_configured_confirmed_prefix_requires_confirmation(tmp_path: Path) -> None:
    svc = service_with_policy(tmp_path, confirmed_prefixes=["python --version"])

    result = svc.run_allowed_command("python", ["--version"])

    assert result.status == "requires_confirmation"
    assert result.data["requires_confirmation"] is True
    assert result.data["policy"] == "confirmed_prefix"


def test_run_allowed_command_executes_configured_confirmed_prefix_after_confirmation(tmp_path: Path) -> None:
    svc = service_with_policy(tmp_path, confirmed_prefixes=["python --version"])

    result = svc.run_allowed_command("python", ["--version"], confirmed=True)

    assert result.status == "succeeded"
    assert result.data["returncode"] == 0
    assert "python" in (result.data["stdout"] + result.data["stderr"]).lower()
    assert sys.executable

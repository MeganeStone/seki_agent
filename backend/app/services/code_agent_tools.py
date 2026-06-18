from app.services.code_execution_service import CodeExecutionService, CodeExecutionResult


class CodeAgentFileTool:
    def __init__(self, service: CodeExecutionService):
        self.service = service

    def list_dir(
        self,
        path: str = ".",
        limit: int = 100,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        return self.service.list_dir(
            path=path,
            limit=limit,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
        )

    def create_dir(
        self,
        path: str,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        return self.service.create_dir(
            path=path,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
        )

    def delete_path(
        self,
        path: str,
        recursive: bool = False,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
        confirmed: bool = False,
    ) -> CodeExecutionResult:
        return self.service.delete_path(
            path=path,
            recursive=recursive,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
            confirmed=confirmed,
        )

    def read_text_file(
        self,
        path: str,
        max_bytes: int | None = None,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        return self.service.read_text_file(
            path=path,
            max_bytes=max_bytes,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
        )

    def write_text_file(
        self,
        path: str,
        content: str,
        overwrite: bool = False,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
        confirmed: bool = False,
    ) -> CodeExecutionResult:
        return self.service.write_text_file(
            path=path,
            content=content,
            overwrite=overwrite,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
            confirmed=confirmed,
        )

    def run_python_script(
        self,
        path: str,
        args: list[str] | None = None,
        timeout_seconds: int | None = None,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
    ) -> CodeExecutionResult:
        return self.service.run_python_script(
            path=path,
            args=args,
            timeout_seconds=timeout_seconds,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
        )

    def run_allowed_command(
        self,
        command: str,
        args: list[str] | None = None,
        timeout_seconds: int | None = None,
        owner_username: str = "",
        conversation_id: str = "",
        agent_name: str = "code_agent",
        confirmed: bool = False,
    ) -> CodeExecutionResult:
        return self.service.run_allowed_command(
            command=command,
            args=args,
            timeout_seconds=timeout_seconds,
            owner_username=owner_username,
            conversation_id=conversation_id,
            agent_name=agent_name,
            confirmed=confirmed,
        )


def format_code_execution_result(result: CodeExecutionResult) -> str:
    lines = [
        f"status={result.status}",
        f"message={result.message}",
        f"operation_id={result.data.get('operation_id', '')}",
    ]

    if "items" in result.data:
        rendered_items = []
        for item in result.data["items"]:
            suffix = "/" if item.get("type") == "dir" else ""
            rendered_items.append(f"- {item.get('path')}{suffix}")
        lines.append("items:\n" + "\n".join(rendered_items))

    if "diff_preview" in result.data:
        # 覆盖写入确认结果：给模型回显 diff 即可，不再重复整份新文件内容。
        lines.append("diff_preview:\n" + str(result.data["diff_preview"]))
    elif "content" in result.data:
        lines.append("content:\n" + str(result.data["content"]))

    if "size" in result.data:
        lines.append(f"size={result.data['size']}")

    if "returncode" in result.data:
        lines.append(f"returncode={result.data['returncode']}")

    if "stdout" in result.data:
        lines.append("stdout:\n" + str(result.data["stdout"]))

    if "stderr" in result.data:
        lines.append("stderr:\n" + str(result.data["stderr"]))

    return "\n".join(lines)

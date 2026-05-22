from collections.abc import Callable
from typing import Any

from app.services.code_agent_tools import CodeAgentFileTool, format_code_execution_result
from app.services.code_execution_service import CodeExecutionResult
from app.services.code_operation_service import CodeOperationService


class MissingCodeLangChainToolDependencyError(RuntimeError):
    pass


def create_code_langchain_tools(
    file_tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str = "code_agent",
    operation_service: CodeOperationService | None = None,
) -> list[Any]:
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise MissingCodeLangChainToolDependencyError("langchain-core is required to create code tools") from exc

    return [
        StructuredTool.from_function(
            func=_list_dir_func(file_tool, owner_username, conversation_id, agent_name),
            name="code_list_dir",
            description=(
                "列出允许工作目录内的文件和子目录。"
                "只能访问后端配置允许的项目目录或 workspace，不能访问敏感文件。"
                "参数：path 相对路径或允许目录内绝对路径，limit 最大返回数量。"
            ),
        ),
        StructuredTool.from_function(
            func=_create_dir_func(file_tool, owner_username, conversation_id, agent_name),
            name="code_create_dir",
            description=(
                "在允许工作目录内创建目录。"
                "只能创建父目录已存在的目录，创建后的目录会被标记为 code agent 本次运行创建。"
                "参数：path 目录路径。"
            ),
        ),
        StructuredTool.from_function(
            func=_read_text_file_func(file_tool, owner_username, conversation_id, agent_name),
            name="code_read_text_file",
            description=(
                "读取允许工作目录内的小型 UTF-8 文本文件。"
                "不能读取 .env、私钥、证书、数据库文件等敏感文件。"
                "参数：path 文件路径，max_bytes 可选读取上限。"
            ),
        ),
        StructuredTool.from_function(
            func=_write_text_file_func(file_tool, owner_username, conversation_id, agent_name),
            name="code_write_text_file",
            description=(
                "写入允许工作目录内的 UTF-8 文本文件。"
                "默认不覆盖已有文件，覆盖必须显式 overwrite=true。"
                "当前不支持删除、移动文件或执行 shell。"
                "参数：path 文件路径，content 文件内容，overwrite 是否覆盖。"
            ),
        ),
        StructuredTool.from_function(
            func=_run_python_script_func(file_tool, owner_username, conversation_id, agent_name),
            name="code_run_python_script",
            description=(
                "运行允许工作目录内的 .py 脚本。"
                "只能运行已存在的 Python 文件，工作目录为脚本所在目录，带超时和输出裁剪。"
                "不能运行任意 shell、不能删除文件、不能访问敏感路径。"
                "参数：path 脚本路径，script_args 参数列表，timeout_seconds 超时秒数。"
            ),
        ),
        StructuredTool.from_function(
            func=_run_allowed_command_func(
                file_tool,
                owner_username,
                conversation_id,
                agent_name,
                operation_service,
            ),
            name="code_run_allowed_command",
            description=(
                "运行 code agent 白名单中的命令。"
                "命令必须拆成 command 和 args，不接受 shell 字符串。"
                "当前允许 git status、git diff、pytest、python -m pytest、npm run lint、npm run build。"
                "危险命令和 shell 控制符会被拒绝。"
                "参数：command 命令名，args 参数列表，timeout_seconds 超时秒数。"
            ),
        ),
        StructuredTool.from_function(
            func=_delete_path_func(file_tool, owner_username, conversation_id, agent_name, operation_service),
            name="code_delete_path",
            description=(
                "删除 code agent 本次运行创建的文件或目录。"
                "非 code agent 本次运行创建的既有文件不会直接删除，会返回 requires_confirmation。"
                "删除目录必须显式 recursive=true。"
                "参数：path 路径，recursive 是否递归删除目录。"
            ),
        ),
    ]


def _list_dir_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
) -> Callable[[str, int], str]:
    def code_list_dir(path: str = ".", limit: int = 100) -> str:
        """列出允许工作目录内的文件和子目录。"""

        return format_code_execution_result(
            tool.list_dir(path, limit, owner_username, conversation_id, agent_name)
        )

    return code_list_dir


def _create_dir_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
) -> Callable[[str], str]:
    def code_create_dir(path: str) -> str:
        """在允许工作目录内创建目录。"""

        return format_code_execution_result(
            tool.create_dir(path, owner_username, conversation_id, agent_name)
        )

    return code_create_dir


def _read_text_file_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
) -> Callable:
    def code_read_text_file(path: str, max_bytes: int | None = None) -> str:
        """读取允许工作目录内的小型 UTF-8 文本文件。"""

        return format_code_execution_result(
            tool.read_text_file(path, max_bytes, owner_username, conversation_id, agent_name)
        )

    return code_read_text_file


def _write_text_file_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
) -> Callable[[str, str, bool], str]:
    def code_write_text_file(path: str, content: str, overwrite: bool = False) -> str:
        """写入允许工作目录内的 UTF-8 文本文件。"""

        return format_code_execution_result(
            tool.write_text_file(path, content, overwrite, owner_username, conversation_id, agent_name)
        )

    return code_write_text_file


def _run_python_script_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
) -> Callable:
    def code_run_python_script(
        path: str,
        script_args: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """运行允许工作目录内的 .py 脚本。"""

        return format_code_execution_result(
            tool.run_python_script(path, script_args, timeout_seconds, owner_username, conversation_id, agent_name)
        )

    return code_run_python_script


def _run_allowed_command_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
    operation_service: CodeOperationService | None = None,
) -> Callable:
    def code_run_allowed_command(
        command: str,
        command_args: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """运行 code agent 白名单中的命令。"""

        return _format_and_record_pending(
            tool.run_allowed_command(command, command_args, timeout_seconds, owner_username, conversation_id, agent_name),
            operation_service,
            owner_username,
            conversation_id,
            agent_name,
        )

    return code_run_allowed_command


def _delete_path_func(
    tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
    operation_service: CodeOperationService | None = None,
) -> Callable[[str, bool], str]:
    def code_delete_path(path: str, recursive: bool = False) -> str:
        """删除 code agent 本次运行创建的文件或目录。"""

        return _format_and_record_pending(
            tool.delete_path(path, recursive, owner_username, conversation_id, agent_name),
            operation_service,
            owner_username,
            conversation_id,
            agent_name,
        )

    return code_delete_path


def _format_and_record_pending(
    result: CodeExecutionResult,
    operation_service: CodeOperationService | None,
    owner_username: str,
    conversation_id: str,
    agent_name: str,
) -> str:
    if result.status != "requires_confirmation" or operation_service is None:
        return format_code_execution_result(result)

    operation = operation_service.create_pending_from_result(
        owner_username=owner_username,
        conversation_id=conversation_id,
        agent_name=agent_name,
        operation_type=str(result.data.get("operation_type") or ""),
        payload=result.data,
    )
    return "\n".join(
        [
            format_code_execution_result(result),
            f"pending_operation_id={operation.operation_id}",
            f"pending_operation_status={operation.status}",
            "pending_operation_message=该操作已进入待确认列表，请用户在前端 Agent 页面确认或取消。",
        ]
    )

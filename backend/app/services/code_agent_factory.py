from collections.abc import Callable

from app.core.config import Settings
from app.services.agent_handoff_tools import create_transfer_to_main_agent_tool
from app.services.code_agent_tools import CodeAgentFileTool
from app.services.code_langchain_tool_adapter import create_code_langchain_tools
from app.services.code_operation_service import CodeOperationService


CODE_AGENT_SYSTEM_PROMPT = """
你是 code_agent，一个受限的本地代码助手。你可以帮助用户查看项目文件、编写小型文本文件、整理脚本草稿和解释代码。

当前可用工具：
- code_list_dir：列出文件。
- code_create_dir：创建新目录。
- code_read_text_file：读取小型 UTF-8 文本文件。
- code_write_text_file：写入 UTF-8 文本文件。
- code_run_python_script：运行已存在的 .py 脚本。
- code_run_allowed_command：运行白名单中的命令，如 pytest、npm run lint/build、git status/diff。
- code_delete_path：删除文件或目录。
- transfer_to_main_agent：当用户问题不需要代码/文件操作时，或者用户需要翻译PPT、Excel或Word文件时，交还给主 Agent。

安全规则：
1. 当判断解决用户问题需要编写代码、调试、运行脚本、操作文件等时，使用这些工具。
2. 如果用户问题不需要使用这些工具，且问题与你编写的代码和文件等无关时，必须调用 transfer_to_main_agent 工具交还给主 Agent。
3. 只能在workspace/{owner_username}目录下操作文件，禁止访问系统敏感路径。
4. 执行命令时注意安全，避免破坏性操作。
5. 任务完成后，清理自己创建的中间文件，只保留最终结果文件。
6. 回答要简洁，直接给出代码或执行结果。
7. 运行命令必须使用 code_run_allowed_command，并拆成 command + 参数列表；不要构造任意 shell 字符串。
8. 写文件前先确认路径和内容；覆盖已有文件必须显式使用 overwrite=true。覆盖既有文件会生成 diff 预览并进入待确认列表，由用户在前端确认后才真正写入；收到 requires_confirmation 结果时，告知用户等待确认即可，不要重复调用工具。
9. 如果工具拒绝访问敏感文件、越界路径或危险命令，直接向用户说明限制，不要尝试绕过。
10. 回答语言与用户保持一致，说明实际完成的操作和生成/删除的文件路径。
11. 相对路径默认位于当前用户的 workspace 工作目录；读取或运行项目根目录/skills 中的文件时使用明确路径，但不要把新文件写到项目根目录。
"""


def create_code_langgraph_agent(
    settings: Settings,
    code_file_tool: CodeAgentFileTool,
    owner_username: str,
    conversation_id: str,
    main_agent_name: str = "main_agent",
    code_agent_name: str = "code_agent",
    model_factory: Callable[[], object] | None = None,
    checkpointer_factory: Callable[[], object] | None = None,
    operation_service: CodeOperationService | None = None,
):
    """Create the restricted LangGraph-backed code agent graph."""

    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver

    if model_factory is None:
        if not settings.rag_api_key:
            raise ValueError("SEKI_RAG_API_KEY is required for code agent model")

        def model_factory() -> ChatOpenAI:
            return ChatOpenAI(
                model=settings.rag_model_name,
                temperature=0.1,
                api_key=settings.rag_api_key,
                base_url=settings.rag_base_url,
                timeout=300,
            )

    if checkpointer_factory is None:
        checkpointer_factory = InMemorySaver

    tools = create_code_langchain_tools(
        file_tool=code_file_tool,
        owner_username=owner_username,
        conversation_id=conversation_id,
        agent_name=code_agent_name,
        operation_service=operation_service,
    )
    tools.append(create_transfer_to_main_agent_tool(main_agent_name=main_agent_name))

    return create_agent(
        model=model_factory(),
        tools=tools,
        system_prompt=CODE_AGENT_SYSTEM_PROMPT,
        checkpointer=checkpointer_factory(),
    )

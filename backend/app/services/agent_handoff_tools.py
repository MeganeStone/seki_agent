from typing import Any


class MissingLangGraphHandoffDependencyError(RuntimeError):
    pass


def create_transfer_to_code_agent_tool(code_agent_name: str = "code_agent") -> Any:
    """Create a LangGraph handoff tool for routing from main agent to code agent."""

    try:
        from langchain_core.tools import StructuredTool
        from langgraph.types import Command
    except ImportError as exc:
        raise MissingLangGraphHandoffDependencyError(
            "langchain-core and langgraph are required to create handoff tools"
        ) from exc

    def transfer_to_code_agent() -> Command:
        """将对话交接给代码助手。"""

        return Command(
            goto=code_agent_name,
            update={"active_agent": code_agent_name},
            graph=Command.PARENT,
        )

    return StructuredTool.from_function(
        func=transfer_to_code_agent,
        name="transfer_to_code_agent",
        description=(
            "当用户请求需要编写代码、调试脚本、分析代码文件或后续受限代码执行能力时，"
            "调用此工具把对话交接给 code_agent。不要用于普通业务问答、翻译、SPI 解析或版本差分。"
        ),
    )


def create_transfer_to_main_agent_tool(main_agent_name: str = "main_agent") -> Any:
    """Create a LangGraph handoff tool for routing from code agent to main agent."""

    try:
        from langchain_core.tools import StructuredTool
        from langgraph.types import Command
    except ImportError as exc:
        raise MissingLangGraphHandoffDependencyError(
            "langchain-core and langgraph are required to create handoff tools"
        ) from exc

    def transfer_to_main_agent() -> Command:
        """将对话交还给主助手。"""

        return Command(
            goto=main_agent_name,
            update={"active_agent": main_agent_name},
            graph=Command.PARENT,
        )

    return StructuredTool.from_function(
        func=transfer_to_main_agent,
        name="transfer_to_main_agent",
        description=(
            "当用户问题不需要代码、脚本或本地文件操作时，调用此工具把对话交还给 main_agent。"
        ),
    )

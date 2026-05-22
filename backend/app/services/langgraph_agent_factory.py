from collections.abc import Callable

from app.core.config import Settings
from app.services.agent_prompts import TBOX_AGENT_SYSTEM_PROMPT
from app.services.agent_tools import (
    DiffAgentTool,
    FileLookupAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
    WebSearchAgentTool,
)
from app.services.agent_handoff_tools import create_transfer_to_code_agent_tool
from app.services.langchain_tool_adapter import create_langchain_tools


def create_tbox_langgraph_agent(
    settings: Settings,
    rag_tool: RagAgentTool,
    owner_username: str | None = None,
    web_search_tool: WebSearchAgentTool | None = None,
    file_lookup_tool: FileLookupAgentTool | None = None,
    translation_tool: TranslationAgentTool | None = None,
    spi_tool: SpiAgentTool | None = None,
    diff_tool: DiffAgentTool | None = None,
    model_factory: Callable[[], object] | None = None,
    checkpointer_factory: Callable[[], object] | None = None,
    include_code_handoff_tool: bool = True,
    code_agent_name: str = "code_agent",
):
    """创建主 TBOX/Seki LangGraph Agent。

    这里只负责“把模型、系统 prompt、工具、记忆 checkpointer 装配成 graph”。
    model_factory/checkpointer_factory 可注入，是为了单元测试不需要真实访问模型服务。
    运行时默认使用千问兼容 OpenAI 接口和 LangGraph InMemorySaver。
    """

    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver

    if model_factory is None:
        if not settings.rag_api_key:
            raise ValueError("SEKI_RAG_API_KEY is required for LangGraph Agent model")

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

    tools = create_langchain_tools(
        rag_tool=rag_tool,
        web_search_tool=web_search_tool,
        file_lookup_tool=file_lookup_tool,
        translation_tool=translation_tool,
        spi_tool=spi_tool,
        diff_tool=diff_tool,
        owner_username=owner_username,
    )
    if include_code_handoff_tool:
        # 主 Agent 自己不直接执行代码类高风险操作，而是通过 handoff 交给 code agent。
        tools.append(create_transfer_to_code_agent_tool(code_agent_name=code_agent_name))

    return create_agent(
        model=model_factory(),
        tools=tools,
        system_prompt=TBOX_AGENT_SYSTEM_PROMPT,
        checkpointer=checkpointer_factory(),
    )

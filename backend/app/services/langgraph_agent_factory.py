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
    """Create the LangGraph-backed TBOX agent graph.

    Model and checkpointer factories are injectable so tests can validate the
    graph factory without calling real external models.
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
        tools.append(create_transfer_to_code_agent_tool(code_agent_name=code_agent_name))

    return create_agent(
        model=model_factory(),
        tools=tools,
        system_prompt=TBOX_AGENT_SYSTEM_PROMPT,
        checkpointer=checkpointer_factory(),
    )

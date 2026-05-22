from app.services.agent_runner import AgentRunner, HandoffAgentRunner, RuleBasedAgentRunner
from app.services.agent_tools import (
    DiffAgentTool,
    ChatAgentTool,
    FileLookupAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
    WebSearchAgentTool,
)
from app.services.code_agent_factory import create_code_langgraph_agent
from app.services.code_agent_tools import CodeAgentFileTool
from app.services.code_execution_service import CodeExecutionService
from app.services.code_operation_service import CodeOperationService
from app.services.chat_model_service import ChatModelService
from app.services.langgraph_agent_factory import create_tbox_langgraph_agent
from app.services.diff_service import DiffService
from app.core.config import get_settings
from app.services.file_service import FileService
from app.services.langgraph_agent_runner import MissingAgentDependencyError, create_langgraph_agent_runner
from app.services.multi_agent_graph_factory import create_multi_agent_graph
from app.services.rag_service import RagService
from app.services.spi_service import SpiService
from app.services.translation_service import TranslationService
from app.services.web_search_service import DisabledWebSearchService


def create_default_agent_runner(
    rag_service: RagService,
    file_service: FileService | None = None,
    translation_service: TranslationService | None = None,
    spi_service: SpiService | None = None,
    diff_service: DiffService | None = None,
    code_operation_service: CodeOperationService | None = None,
    prefer_langgraph: bool = False,
) -> AgentRunner:
    settings = get_settings()
    should_use_langgraph = prefer_langgraph or settings.agent_runner.lower() == "langgraph"

    if should_use_langgraph:
        try:
            langgraph_runner = create_langgraph_agent_runner(
                graph_factory=lambda request: create_multi_agent_graph(
                    main_agent_graph=create_tbox_langgraph_agent(
                        settings=settings.model_copy(update={"rag_api_key": settings.rag_api_key or request.api_key}),
                        rag_tool=RagAgentTool(rag_service),
                        owner_username=request.owner_username,
                        web_search_tool=WebSearchAgentTool(DisabledWebSearchService()),
                        file_lookup_tool=FileLookupAgentTool(file_service) if file_service else None,
                        translation_tool=TranslationAgentTool(translation_service) if translation_service else None,
                        spi_tool=SpiAgentTool(spi_service) if spi_service else None,
                        diff_tool=DiffAgentTool(diff_service) if diff_service else None,
                    ),
                    code_agent_graph=create_code_langgraph_agent(
                        settings=settings.model_copy(update={"rag_api_key": settings.rag_api_key or request.api_key}),
                        code_file_tool=CodeAgentFileTool(CodeExecutionService()),
                        owner_username=request.owner_username,
                        conversation_id=request.conversation_id,
                        operation_service=code_operation_service,
                    ),
                )
            )
            return HandoffAgentRunner(main_runner=langgraph_runner)
        except (MissingAgentDependencyError, NotImplementedError):
            pass

    rule_runner = RuleBasedAgentRunner(
        rag_tool=RagAgentTool(rag_service),
        chat_tool=ChatAgentTool(ChatModelService()),
        translation_tool=TranslationAgentTool(translation_service) if translation_service else None,
        spi_tool=SpiAgentTool(spi_service) if spi_service else None,
        diff_tool=DiffAgentTool(diff_service) if diff_service else None,
    )
    return HandoffAgentRunner(
        main_runner=rule_runner,
        enable_keyword_routing=settings.agent_enable_keyword_handoff,
    )

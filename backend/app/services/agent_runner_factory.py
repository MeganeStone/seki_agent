from app.services.agent_runner import AgentRunner, HandoffAgentRunner
from app.services.agent_tools import (
    DiffAgentTool,
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
from app.services.langgraph_agent_factory import create_tbox_langgraph_agent
from app.services.diff_service import DiffService
from app.core.config import get_settings
from app.services.file_service import FileService
from app.services.langgraph_agent_runner import create_langgraph_agent_runner
from app.services.multi_agent_graph_factory import create_multi_agent_graph
from app.services.rag_service import RagService
from app.services.spi_service import SpiService
from app.services.translation_service import TranslationService
from app.services.web_search_service import DisabledWebSearchService, VolcWebSearchService


def create_default_agent_runner(
    rag_service: RagService,
    file_service: FileService | None = None,
    translation_service: TranslationService | None = None,
    spi_service: SpiService | None = None,
    diff_service: DiffService | None = None,
    code_operation_service: CodeOperationService | None = None,
) -> AgentRunner:
    settings = get_settings()
    langgraph_runner = create_langgraph_agent_runner(
        graph_factory=lambda request: create_multi_agent_graph(
            main_agent_graph=create_tbox_langgraph_agent(
                settings=settings.model_copy(update={"rag_api_key": settings.rag_api_key or request.api_key}),
                rag_tool=RagAgentTool(rag_service),
                owner_username=request.owner_username,
                web_search_tool=WebSearchAgentTool(_create_web_search_service(settings, request.web_search_api_key)),
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


def _create_web_search_service(settings, request_api_key: str | None = None):
    api_key = settings.web_search_api_key or request_api_key
    if api_key:
        return VolcWebSearchService(
            api_key=api_key,
            api_url=settings.web_search_api_url,
            timeout_seconds=settings.web_search_timeout_seconds,
            max_summary_chars=settings.web_search_max_summary_chars,
        )
    return DisabledWebSearchService()

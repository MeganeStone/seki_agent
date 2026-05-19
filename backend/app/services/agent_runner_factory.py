from app.services.agent_runner import AgentRunner, RuleBasedAgentRunner
from app.services.agent_tools import (
    DiffAgentTool,
    FileLookupAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
    WebSearchAgentTool,
)
from app.services.langgraph_agent_factory import create_tbox_langgraph_agent
from app.services.diff_service import DiffService
from app.core.config import get_settings
from app.services.file_service import FileService
from app.services.langgraph_agent_runner import MissingAgentDependencyError, create_langgraph_agent_runner
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
    prefer_langgraph: bool = False,
) -> AgentRunner:
    settings = get_settings()
    should_use_langgraph = prefer_langgraph or settings.agent_runner.lower() == "langgraph"

    if should_use_langgraph:
        try:
            return create_langgraph_agent_runner(
                graph_factory=lambda request: create_tbox_langgraph_agent(
                    settings=settings,
                    rag_tool=RagAgentTool(rag_service),
                    owner_username=request.owner_username,
                    web_search_tool=WebSearchAgentTool(DisabledWebSearchService()),
                    file_lookup_tool=FileLookupAgentTool(file_service) if file_service else None,
                    translation_tool=TranslationAgentTool(translation_service) if translation_service else None,
                    spi_tool=SpiAgentTool(spi_service) if spi_service else None,
                    diff_tool=DiffAgentTool(diff_service) if diff_service else None,
                )
            )
        except (MissingAgentDependencyError, NotImplementedError):
            pass

    return RuleBasedAgentRunner(
        rag_tool=RagAgentTool(rag_service),
        translation_tool=TranslationAgentTool(translation_service) if translation_service else None,
        spi_tool=SpiAgentTool(spi_service) if spi_service else None,
        diff_tool=DiffAgentTool(diff_service) if diff_service else None,
    )

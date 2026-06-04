import re

from app.services.agent_runner import AgentRunner
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
                code_file_tool=CodeAgentFileTool(
                    _create_code_execution_service(request.owner_username, file_service=file_service)
                ),
                owner_username=request.owner_username,
                conversation_id=request.conversation_id,
                operation_service=code_operation_service,
            ),
        )
    )
    return langgraph_runner


def _create_code_execution_service(
    owner_username: str,
    file_service: FileService | None = None,
) -> CodeExecutionService:
    settings = get_settings()
    safe_owner = re.sub(r"[^a-zA-Z0-9_-]", "_", owner_username.strip()) or "anonymous"
    user_workspace = (settings.workspace_dir / safe_owner).resolve()
    user_workspace.mkdir(parents=True, exist_ok=True)
    allowed_roots = settings.code_agent_allowed_roots or [
        user_workspace,
        settings.project_root,
        settings.skills_dir,
    ]
    return CodeExecutionService(
        allowed_roots=allowed_roots,
        default_root=user_workspace,
        writable_roots=[user_workspace],
        after_delete_path=(lambda owner, _path: file_service.sync_workspace_files(owner)) if file_service else None,
    )


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

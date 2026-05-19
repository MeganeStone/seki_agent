import pytest
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import get_settings
from app.services.agent_runner import AgentRequest
from app.services.langgraph_agent_factory import create_tbox_langgraph_agent
from app.services.langgraph_agent_runner import LangGraphAgentRunner
from app.services.agent_tools import DiffAgentTool, FileLookupAgentTool, RagAgentTool, SpiAgentTool, TranslationAgentTool


class LiveSmokeRagService:
    def answer(self, message: str, use_knowledge_base: bool = True) -> dict:
        return {"answer": f"mock rag answer: {message}", "sources": []}


@dataclass
class LiveSmokeFile:
    id: str
    filename: str
    size: int = 100
    created_at: datetime = datetime(2026, 5, 19, tzinfo=timezone.utc)


class LiveSmokeFileService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_files(self, owner_username: str) -> list[LiveSmokeFile]:
        self.calls.append(owner_username)
        return [
            LiveSmokeFile(id="live-manual-file", filename="live_manual.docx"),
            LiveSmokeFile(id="live-spi-log-file", filename="live_spi_capture.log"),
            LiveSmokeFile(id="live-old-version-file", filename="live_version_old.tar.gz"),
            LiveSmokeFile(id="live-new-version-file", filename="live_version_new.tar.gz"),
        ]


@dataclass
class LiveSmokeTask:
    task_id: str = "live-translation-task"
    status: str = "succeeded"
    result_file_id: str | None = "live-result-file"
    error: str | None = None
    summary = None


class LiveSmokeTranslationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def create_task(self, owner_username: str, file_id: str, target_language: str) -> LiveSmokeTask:
        self.calls.append((owner_username, file_id, target_language))
        return LiveSmokeTask()


class LiveSmokeSpiService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_task(self, owner_username: str, file_id: str) -> LiveSmokeTask:
        self.calls.append((owner_username, file_id))
        return LiveSmokeTask(task_id="live-spi-task")


class LiveSmokeDiffService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def create_task(self, owner_username: str, left_file_id: str, right_file_id: str) -> LiveSmokeTask:
        self.calls.append((owner_username, left_file_id, right_file_id))
        return LiveSmokeTask(task_id="live-diff-task")


@pytest.mark.live
def test_live_langgraph_agent_smoke() -> None:
    settings = get_settings()
    if not settings.run_live_agent_tests:
        pytest.skip("Set SEKI_RUN_LIVE_AGENT_TESTS=true to run live Agent tests")
    if not settings.rag_api_key:
        pytest.skip("Set SEKI_RAG_API_KEY to run live Agent tests")

    graph = create_tbox_langgraph_agent(
        settings=settings,
        rag_tool=RagAgentTool(LiveSmokeRagService()),
    )
    runner = LangGraphAgentRunner(graph_factory=lambda: graph)

    response = runner.run(
        AgentRequest(
            owner_username="live-test",
            conversation_id="live-test-conversation",
            message="请简单回复：Agent live smoke ok",
            use_knowledge_base=False,
        )
    )

    assert response.answer


@pytest.mark.live
def test_live_langgraph_agent_uses_file_lookup_before_translation() -> None:
    settings = get_settings()
    if not settings.run_live_agent_tests:
        pytest.skip("Set SEKI_RUN_LIVE_AGENT_TESTS=true to run live Agent tests")
    if not settings.rag_api_key:
        pytest.skip("Set SEKI_RAG_API_KEY to run live Agent tests")

    file_service = LiveSmokeFileService()
    translation_service = LiveSmokeTranslationService()
    graph = create_tbox_langgraph_agent(
        settings=settings,
        rag_tool=RagAgentTool(LiveSmokeRagService()),
        owner_username="live-test",
        file_lookup_tool=FileLookupAgentTool(file_service),
        translation_tool=TranslationAgentTool(translation_service),
    )
    runner = LangGraphAgentRunner(graph_factory=lambda: graph)

    response = runner.run(
        AgentRequest(
            owner_username="live-test",
            conversation_id="live-test-file-lookup-translation",
            message="请把我已上传的 live_manual.docx 翻译成英语。不要让我提供 file_id，请你先查询文件。",
            use_knowledge_base=False,
        )
    )

    assert response.answer
    assert file_service.calls == ["live-test"]
    assert len(translation_service.calls) == 1
    owner_username, file_id, target_language = translation_service.calls[0]
    assert owner_username == "live-test"
    assert file_id == "live-manual-file"
    assert target_language == "英语"


@pytest.mark.live
def test_live_langgraph_agent_uses_file_lookup_before_spi() -> None:
    settings = get_settings()
    if not settings.run_live_agent_tests:
        pytest.skip("Set SEKI_RUN_LIVE_AGENT_TESTS=true to run live Agent tests")
    if not settings.rag_api_key:
        pytest.skip("Set SEKI_RAG_API_KEY to run live Agent tests")

    file_service = LiveSmokeFileService()
    spi_service = LiveSmokeSpiService()
    graph = create_tbox_langgraph_agent(
        settings=settings,
        rag_tool=RagAgentTool(LiveSmokeRagService()),
        owner_username="live-test",
        file_lookup_tool=FileLookupAgentTool(file_service),
        spi_tool=SpiAgentTool(spi_service),
    )
    runner = LangGraphAgentRunner(graph_factory=lambda: graph)

    response = runner.run(
        AgentRequest(
            owner_username="live-test",
            conversation_id="live-test-file-lookup-spi",
            message="请解析我已上传的 live_spi_capture.log。不要让我提供 file_id，请你先查询文件。",
            use_knowledge_base=False,
        )
    )

    assert response.answer
    assert file_service.calls == ["live-test"]
    assert spi_service.calls == [("live-test", "live-spi-log-file")]


@pytest.mark.live
def test_live_langgraph_agent_uses_file_lookup_before_diff() -> None:
    settings = get_settings()
    if not settings.run_live_agent_tests:
        pytest.skip("Set SEKI_RUN_LIVE_AGENT_TESTS=true to run live Agent tests")
    if not settings.rag_api_key:
        pytest.skip("Set SEKI_RAG_API_KEY to run live Agent tests")

    file_service = LiveSmokeFileService()
    diff_service = LiveSmokeDiffService()
    graph = create_tbox_langgraph_agent(
        settings=settings,
        rag_tool=RagAgentTool(LiveSmokeRagService()),
        owner_username="live-test",
        file_lookup_tool=FileLookupAgentTool(file_service),
        diff_tool=DiffAgentTool(diff_service),
    )
    runner = LangGraphAgentRunner(graph_factory=lambda: graph)

    response = runner.run(
        AgentRequest(
            owner_username="live-test",
            conversation_id="live-test-file-lookup-diff",
            message=(
                "请比较我已上传的 live_version_old.tar.gz 和 live_version_new.tar.gz 的版本差异。"
                "不要让我提供 file_id，请你先查询文件。"
            ),
            use_knowledge_base=False,
        )
    )

    assert response.answer
    assert file_service.calls == ["live-test", "live-test"]
    assert diff_service.calls == [("live-test", "live-old-version-file", "live-new-version-file")]

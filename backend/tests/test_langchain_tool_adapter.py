from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.agent_tools import (
    DiffAgentTool,
    FileLookupAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
    WebSearchAgentTool,
)
from app.services.langchain_tool_adapter import create_langchain_tools
from app.services.web_search_service import WebSearchResult


@dataclass
class FakeTask:
    task_id: str = "task-1"
    status: str = "succeeded"
    result_file_id: str | None = "file-1"
    error: str | None = None
    summary = None


@dataclass
class FakeFile:
    id: str
    filename: str
    size: int = 100
    created_at: datetime = datetime(2026, 5, 19, tzinfo=timezone.utc)


class FakeRagService:
    def answer(self, message: str, use_knowledge_base: bool = True) -> dict:
        return {"answer": f"rag: {message}", "sources": []}


class FakeWebSearchService:
    def search(self, query: str, max_results: int = 5) -> WebSearchResult:
        return WebSearchResult(summary=f"web: {query} / {max_results}", items=[])


class FakeTranslationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def create_task(self, owner_username: str, file_id: str, target_language: str) -> FakeTask:
        self.calls.append((owner_username, file_id, target_language))
        return FakeTask(task_id="translation-task")


class FakeSpiService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_task(self, owner_username: str, file_id: str) -> FakeTask:
        self.calls.append((owner_username, file_id))
        return FakeTask(task_id="spi-task")


class FakeDiffService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def create_task(self, owner_username: str, left_file_id: str, right_file_id: str) -> FakeTask:
        self.calls.append((owner_username, left_file_id, right_file_id))
        return FakeTask(task_id="diff-task")


class FakeFileService:
    def list_files(self, owner_username: str) -> list[FakeFile]:
        return [
            FakeFile(id="manual-file", filename="manual.docx"),
            FakeFile(id="spi-log", filename="spi_capture.log"),
            FakeFile(id="old-version", filename="version_old.tar.gz"),
            FakeFile(id="new-version", filename="version_new.tar.gz"),
        ]


def test_create_langchain_tools_wraps_agent_adapters() -> None:
    translation_service = FakeTranslationService()
    spi_service = FakeSpiService()
    diff_service = FakeDiffService()
    tools = create_langchain_tools(
        rag_tool=RagAgentTool(FakeRagService()),
        web_search_tool=WebSearchAgentTool(FakeWebSearchService()),
        file_lookup_tool=FileLookupAgentTool(FakeFileService()),
        translation_tool=TranslationAgentTool(translation_service),
        spi_tool=SpiAgentTool(spi_service),
        diff_tool=DiffAgentTool(diff_service),
    )

    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {"rag", "web_search", "file_lookup", "translation", "spi", "diff"}
    assert "联网搜索公开信息" in by_name["web_search"].description
    assert "必须先使用此工具" in by_name["file_lookup"].description
    assert "不要编造 file_id" in by_name["translation"].description
    assert "不要编造 file_id" in by_name["spi"].description
    assert "不要编造文件 ID" in by_name["diff"].description
    assert by_name["rag"].invoke({"question": "什么是 TSU？"}) == "rag: 什么是 TSU？"
    assert by_name["web_search"].invoke({"query": "qwen", "max_results": 3}) == "web: qwen / 3"
    assert "file_id=manual-file" in by_name["file_lookup"].invoke(
        {"owner_username": "alice", "filename_contains": "manual", "suffix": ".docx", "limit": 5}
    )
    assert "翻译任务已创建" in by_name["translation"].invoke(
        {"owner_username": "alice", "file_id": "file-1", "target_language": "英语"}
    )
    assert "SPI 解析任务已创建" in by_name["spi"].invoke({"owner_username": "alice", "file_id": "log-1"})
    assert "版本差分任务已创建" in by_name["diff"].invoke(
        {"owner_username": "alice", "left_file_id": "old-1", "right_file_id": "new-1"}
    )


def test_file_lookup_then_translation_tool_contract() -> None:
    translation_service = FakeTranslationService()
    tools = create_langchain_tools(
        rag_tool=RagAgentTool(FakeRagService()),
        file_lookup_tool=FileLookupAgentTool(FakeFileService()),
        translation_tool=TranslationAgentTool(translation_service),
    )
    by_name = {tool.name: tool for tool in tools}

    lookup_result = by_name["file_lookup"].invoke(
        {"owner_username": "alice", "filename_contains": "manual", "suffix": ".docx", "limit": 1}
    )
    assert "file_id=manual-file" in lookup_result

    by_name["translation"].invoke(
        {"owner_username": "alice", "file_id": "manual-file", "target_language": "日语"}
    )

    assert translation_service.calls == [("alice", "manual-file", "日语")]


def test_file_lookup_then_spi_tool_contract() -> None:
    spi_service = FakeSpiService()
    tools = create_langchain_tools(
        rag_tool=RagAgentTool(FakeRagService()),
        file_lookup_tool=FileLookupAgentTool(FakeFileService()),
        spi_tool=SpiAgentTool(spi_service),
    )
    by_name = {tool.name: tool for tool in tools}

    lookup_result = by_name["file_lookup"].invoke(
        {"owner_username": "alice", "filename_contains": "spi", "suffix": ".log", "limit": 1}
    )
    assert "file_id=spi-log" in lookup_result

    by_name["spi"].invoke({"owner_username": "alice", "file_id": "spi-log"})

    assert spi_service.calls == [("alice", "spi-log")]


def test_file_lookup_then_diff_tool_contract() -> None:
    diff_service = FakeDiffService()
    tools = create_langchain_tools(
        rag_tool=RagAgentTool(FakeRagService()),
        file_lookup_tool=FileLookupAgentTool(FakeFileService()),
        diff_tool=DiffAgentTool(diff_service),
    )
    by_name = {tool.name: tool for tool in tools}

    old_lookup_result = by_name["file_lookup"].invoke(
        {"owner_username": "alice", "filename_contains": "old", "suffix": ".tar.gz", "limit": 1}
    )
    new_lookup_result = by_name["file_lookup"].invoke(
        {"owner_username": "alice", "filename_contains": "new", "suffix": ".tar.gz", "limit": 1}
    )
    assert "file_id=old-version" in old_lookup_result
    assert "file_id=new-version" in new_lookup_result

    by_name["diff"].invoke(
        {"owner_username": "alice", "left_file_id": "old-version", "right_file_id": "new-version"}
    )

    assert diff_service.calls == [("alice", "old-version", "new-version")]


def test_bound_owner_tools_do_not_require_model_supplied_username() -> None:
    translation_service = FakeTranslationService()
    spi_service = FakeSpiService()
    diff_service = FakeDiffService()
    tools = create_langchain_tools(
        rag_tool=RagAgentTool(FakeRagService()),
        file_lookup_tool=FileLookupAgentTool(FakeFileService()),
        translation_tool=TranslationAgentTool(translation_service),
        spi_tool=SpiAgentTool(spi_service),
        diff_tool=DiffAgentTool(diff_service),
        owner_username="alice",
    )
    by_name = {tool.name: tool for tool in tools}

    assert "owner_username" not in by_name["file_lookup"].args
    assert "owner_username" not in by_name["translation"].args
    assert "owner_username" not in by_name["spi"].args
    assert "owner_username" not in by_name["diff"].args

    assert "file_id=manual-file" in by_name["file_lookup"].invoke(
        {"filename_contains": "manual", "suffix": ".docx", "limit": 1}
    )
    by_name["translation"].invoke({"file_id": "manual-file", "target_language": "英语"})
    by_name["spi"].invoke({"file_id": "spi-log"})
    by_name["diff"].invoke({"left_file_id": "old-version", "right_file_id": "new-version"})

    assert translation_service.calls == [("alice", "manual-file", "英语")]
    assert spi_service.calls == [("alice", "spi-log")]
    assert diff_service.calls == [("alice", "old-version", "new-version")]

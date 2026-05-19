from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.diff import DiffSummary
from app.services.agent_tools import (
    DiffAgentTool,
    FileLookupAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
    WebSearchAgentTool,
    normalize_target_language,
)
from app.services.web_search_service import DisabledWebSearchService, WebSearchResult


@dataclass
class FakeTask:
    task_id: str = "task-1"
    status: str = "succeeded"
    result_file_id: str | None = "file-1"
    error: str | None = None
    summary: DiffSummary | None = None


@dataclass
class FakeFile:
    id: str
    filename: str
    size: int = 128
    created_at: datetime = datetime(2026, 5, 19, tzinfo=timezone.utc)


class FakeRagService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def answer(self, message: str, use_knowledge_base: bool = True) -> dict:
        self.calls.append((message, use_knowledge_base))
        return {
            "answer": f"answer: {message}",
            "sources": [{"file_name": "manual.pdf", "page_number": 2, "snippet": "source"}],
        }


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
        return FakeTask(
            task_id="diff-task",
            summary=DiffSummary(changed=True, bin_changed=True, lib_changed=False),
        )


class FakeFileService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_files(self, owner_username: str) -> list[FakeFile]:
        self.calls.append(owner_username)
        return [
            FakeFile(id="file-docx", filename="TBOX_design.docx"),
            FakeFile(id="file-log", filename="spi_capture.log"),
            FakeFile(id="file-old", filename="version_old.tar.gz"),
            FakeFile(id="file-new", filename="version_new.tar.gz"),
        ]


class FakeWebSearchService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int = 5) -> WebSearchResult:
        self.calls.append((query, max_results))
        return WebSearchResult(
            summary=f"search summary: {query}",
            items=[{"title": "result", "url": "https://example.com"}],
        )


def test_rag_agent_tool_delegates_to_rag_service() -> None:
    service = FakeRagService()
    tool = RagAgentTool(service)

    result = tool("什么是 TSU？")

    assert service.calls == [("什么是 TSU？", True)]
    assert "answer: 什么是 TSU？" in result.content
    assert result.data == {
        "sources": [{"file_name": "manual.pdf", "page_number": 2, "snippet": "source"}],
    }


def test_web_search_agent_tool_delegates_to_search_service() -> None:
    service = FakeWebSearchService()
    tool = WebSearchAgentTool(service)

    result = tool("qwen latest", max_results=20)

    assert service.calls == [("qwen latest", 10)]
    assert result.content == "search summary: qwen latest"
    assert result.data == {"items": [{"title": "result", "url": "https://example.com"}]}


def test_web_search_agent_tool_returns_friendly_message_when_disabled() -> None:
    tool = WebSearchAgentTool(DisabledWebSearchService())

    result = tool("latest news")

    assert "联网搜索尚未配置" in result.content
    assert result.data == {"items": []}


def test_file_lookup_agent_tool_filters_by_filename_and_suffix() -> None:
    service = FakeFileService()
    tool = FileLookupAgentTool(service)

    result = tool("alice", filename_contains="version", suffix="tar.gz")

    assert service.calls == ["alice"]
    assert result.data == {
        "files": [
            {
                "id": "file-old",
                "filename": "version_old.tar.gz",
                "size": 128,
                "created_at": "2026-05-19T00:00:00+00:00",
            },
            {
                "id": "file-new",
                "filename": "version_new.tar.gz",
                "size": 128,
                "created_at": "2026-05-19T00:00:00+00:00",
            },
        ]
    }
    assert "file_id=file-old" in result.content
    assert "file_id=file-new" in result.content


def test_file_lookup_agent_tool_returns_empty_result_when_no_match() -> None:
    tool = FileLookupAgentTool(FakeFileService())

    result = tool("alice", filename_contains="missing")

    assert result.data == {"files": []}
    assert "未找到匹配文件" in result.content


def test_translation_agent_tool_maps_arguments_and_result() -> None:
    service = FakeTranslationService()
    tool = TranslationAgentTool(service)

    result = tool("alice", "file-1", "英语")

    assert service.calls == [("alice", "file-1", "英语")]
    assert result.data == {
        "task_id": "translation-task",
        "status": "succeeded",
        "result_file_id": "file-1",
        "error": None,
    }


def test_translation_agent_tool_normalizes_common_language_codes() -> None:
    service = FakeTranslationService()
    tool = TranslationAgentTool(service)

    tool("alice", "file-1", "en")
    tool("alice", "file-2", "japanese")

    assert service.calls == [
        ("alice", "file-1", "英语"),
        ("alice", "file-2", "日语"),
    ]


def test_normalize_target_language_keeps_custom_language() -> None:
    assert normalize_target_language("葡萄牙语") == "葡萄牙语"


def test_spi_agent_tool_maps_arguments_and_result() -> None:
    service = FakeSpiService()
    tool = SpiAgentTool(service)

    result = tool("alice", "log-1")

    assert service.calls == [("alice", "log-1")]
    assert result.data == {
        "task_id": "spi-task",
        "status": "succeeded",
        "result_file_id": "file-1",
        "error": None,
    }


def test_diff_agent_tool_maps_arguments_and_summary() -> None:
    service = FakeDiffService()
    tool = DiffAgentTool(service)

    result = tool("alice", "old-1", "new-1")

    assert service.calls == [("alice", "old-1", "new-1")]
    assert result.data == {
        "task_id": "diff-task",
        "status": "succeeded",
        "summary": {"changed": True, "bin_changed": True, "lib_changed": False},
        "result_file_id": "file-1",
        "error": None,
    }

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Protocol

from app.services.web_search_service import WebSearchDisabledError

if TYPE_CHECKING:
    from app.services.agent_runner import ChatHistoryMessage


@dataclass(frozen=True)
class AgentToolResult:
    """内部工具统一返回结构。

    content 会交给模型/前端作为文本说明，data 保存结构化结果，例如 task_id、
    sources、匹配文件列表等，便于前端继续展示按钮或状态。
    """
    content: str
    data: dict | None = None


class RagAnswerService(Protocol):
    def answer(self, message: str, use_knowledge_base: bool = True) -> dict:
        ...


class ChatAnswerService(Protocol):
    def answer(
        self,
        message: str,
        api_key: str | None = None,
        history: tuple[ChatHistoryMessage, ...] = (),
    ) -> dict:
        ...


class TranslationTaskService(Protocol):
    def create_task(self, owner_username: str, file_id: str, target_language: str):
        ...


class SpiTaskService(Protocol):
    def create_task(self, owner_username: str, file_id: str):
        ...


class DiffTaskService(Protocol):
    def create_task(self, owner_username: str, left_file_id: str, right_file_id: str):
        ...


class FileLookupService(Protocol):
    def list_files(self, owner_username: str):
        ...


class WebSearchService(Protocol):
    def search(self, query: str, max_results: int = 5):
        ...


class RagAgentTool:
    """把 RAG service 包装为 Agent 可调用工具。"""

    def __init__(self, rag_service: RagAnswerService):
        self.rag_service = rag_service

    def __call__(self, question: str) -> AgentToolResult:
        result = self.rag_service.answer(question, use_knowledge_base=True)
        sources = result.get("sources", [])
        content = str(result.get("answer", ""))
        return AgentToolResult(content=content, data={"sources": sources})


class ChatAgentTool:
    def __init__(self, chat_service: ChatAnswerService):
        self.chat_service = chat_service

    def __call__(
        self,
        message: str,
        api_key: str | None = None,
        history: tuple[ChatHistoryMessage, ...] = (),
    ) -> AgentToolResult:
        result = self.chat_service.answer(message, api_key=api_key, history=history)
        return AgentToolResult(content=str(result.get("answer", "")), data={"sources": result.get("sources", [])})


class WebSearchAgentTool:
    """把联网搜索 service 包装为 Agent 工具，并处理未配置 key 的友好提示。"""

    def __init__(self, web_search_service: WebSearchService):
        self.web_search_service = web_search_service

    def __call__(self, query: str, max_results: int = 5) -> AgentToolResult:
        clean_query = query.strip()
        if not clean_query:
            return AgentToolResult(content="请提供要搜索的关键词。", data={"items": []})

        try:
            result = self.web_search_service.search(clean_query, max_results=max(1, min(max_results, 10)))
        except WebSearchDisabledError:
            return AgentToolResult(
                content="联网搜索尚未配置，请先配置搜索服务后再使用。",
                data={"items": []},
            )
        return AgentToolResult(
            content=result.summary,
            data={"items": result.items},
        )


class FileLookupAgentTool:
    """按当前用户 workspace 文件名查找 file_id。

    Agent 后续调用 translation/spi/diff 时必须使用 file_id，因此这个工具是
    自然语言文件名和后端任务接口之间的桥。
    """

    def __init__(self, file_service: FileLookupService):
        self.file_service = file_service

    def __call__(
        self,
        owner_username: str,
        filename_contains: str | None = None,
        suffix: str | None = None,
        limit: int = 10,
    ) -> AgentToolResult:
        normalized_query = _normalize_filename_query(filename_contains or "")
        normalized_suffix = (suffix or "").strip().lower()
        if normalized_suffix and not normalized_suffix.startswith("."):
            normalized_suffix = f".{normalized_suffix}"

        files = self.file_service.list_files(owner_username)
        matches = []
        for file in files:
            filename = file.filename
            normalized_filename = _normalize_filename_query(filename)
            if normalized_query and normalized_query not in normalized_filename:
                continue
            if normalized_suffix and not filename.lower().endswith(normalized_suffix):
                continue
            matches.append(
                {
                    "id": file.id,
                    "filename": filename,
                    "size": file.size,
                    "created_at": file.created_at.isoformat(),
                }
            )
            if len(matches) >= max(1, min(limit, 20)):
                break

        if not matches:
            return AgentToolResult(
                content="未找到匹配文件，请先上传文件或提供更准确的文件名。",
                data={"files": []},
            )

        lines = [f"{item['filename']} -> file_id={item['id']}" for item in matches]
        return AgentToolResult(
            content=(
                "找到以下文件。后续调用 translation/spi/diff 工具时必须直接使用对应 file_id：\n"
                + "\n".join(lines)
            ),
            data={"files": matches},
        )


def _normalize_filename_query(value: str) -> str:
    """把文件名查询归一化，降低空格、符号、大小写导致的匹配失败。"""
    lowered = value.strip().lower()
    return "".join(char for char in lowered if char.isalnum() or "\u4e00" <= char <= "\u9fff")


class TranslationAgentTool:
    """创建文档翻译任务的 Agent 工具。"""

    def __init__(self, translation_service: TranslationTaskService):
        self.translation_service = translation_service

    def __call__(self, owner_username: str, file_id: str, target_language: str) -> AgentToolResult:
        normalized_target_language = normalize_target_language(target_language)
        task = self.translation_service.create_task(owner_username, file_id, normalized_target_language)
        return AgentToolResult(
            content=f"翻译任务已创建，状态：{task.status}",
            data={
                "task_id": task.task_id,
                "status": task.status,
                "result_file_id": task.result_file_id,
                "error": task.error,
            },
        )


def normalize_target_language(target_language: str) -> str:
    clean_value = target_language.strip()
    normalized = clean_value.lower().replace("_", "-")
    aliases = {
        "en": "英语",
        "eng": "英语",
        "english": "英语",
        "英语": "英语",
        "英文": "英语",
        "ja": "日语",
        "jp": "日语",
        "jpn": "日语",
        "japanese": "日语",
        "日语": "日语",
        "日文": "日语",
        "zh": "中文",
        "zh-cn": "中文",
        "chinese": "中文",
        "中文": "中文",
        "汉语": "中文",
        "de": "德语",
        "deu": "德语",
        "german": "德语",
        "德语": "德语",
        "fr": "法语",
        "fra": "法语",
        "french": "法语",
        "法语": "法语",
    }
    return aliases.get(normalized, clean_value)


class SpiAgentTool:
    """创建 SPI log 解析任务的 Agent 工具。"""

    def __init__(self, spi_service: SpiTaskService):
        self.spi_service = spi_service

    def __call__(self, owner_username: str, file_id: str) -> AgentToolResult:
        task = self.spi_service.create_task(owner_username, file_id)
        return AgentToolResult(
            content=f"SPI 解析任务已创建，状态：{task.status}",
            data={
                "task_id": task.task_id,
                "status": task.status,
                "result_file_id": task.result_file_id,
                "error": task.error,
            },
        )


class DiffAgentTool:
    """创建版本差分任务的 Agent 工具。"""

    def __init__(self, diff_service: DiffTaskService):
        self.diff_service = diff_service

    def __call__(self, owner_username: str, left_file_id: str, right_file_id: str) -> AgentToolResult:
        task = self.diff_service.create_task(owner_username, left_file_id, right_file_id)
        summary = None
        if task.summary is not None:
            summary = {
                "changed": task.summary.changed,
                "bin_changed": task.summary.bin_changed,
                "lib_changed": task.summary.lib_changed,
            }
        return AgentToolResult(
            content=f"版本差分任务已创建，状态：{task.status}",
            data={
                "task_id": task.task_id,
                "status": task.status,
                "summary": summary,
                "result_file_id": task.result_file_id,
                "error": task.error,
            },
        )

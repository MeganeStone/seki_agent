import re
from dataclasses import dataclass
from typing import Protocol

from app.services.agent_tools import (
    AgentToolResult,
    DiffAgentTool,
    RagAgentTool,
    SpiAgentTool,
    TranslationAgentTool,
)


@dataclass(frozen=True)
class AgentRequest:
    owner_username: str
    conversation_id: str
    message: str
    use_knowledge_base: bool = True


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    sources: list = None
    data: dict | None = None
    route: str = "rag"

    def __post_init__(self) -> None:
        if self.sources is None:
            object.__setattr__(self, "sources", [])


class AgentRunner(Protocol):
    def run(self, request: AgentRequest) -> AgentResponse:
        ...


class RuleBasedAgentRunner:
    """Temporary deterministic runner for Agent wiring tests.

    This runner keeps orchestration testable before the real LangGraph runner is
    introduced. It routes explicit tool requests by simple text patterns and
    delegates everything else to RAG when knowledge base usage is enabled.
    """

    def __init__(
        self,
        rag_tool: RagAgentTool,
        translation_tool: TranslationAgentTool | None = None,
        spi_tool: SpiAgentTool | None = None,
        diff_tool: DiffAgentTool | None = None,
    ):
        self.rag_tool = rag_tool
        self.translation_tool = translation_tool
        self.spi_tool = spi_tool
        self.diff_tool = diff_tool

    def run(self, request: AgentRequest) -> AgentResponse:
        message = request.message.strip()

        if self.translation_tool and self._looks_like_translation(message):
            file_id = self._extract_value(message, "file_id")
            target_language = self._extract_value(message, "target_language") or self._extract_value(message, "target_lang")
            if file_id and target_language:
                result = self.translation_tool(request.owner_username, file_id, target_language)
                return self._from_tool_result(result, route="translation")

        if self.spi_tool and self._looks_like_spi(message):
            file_id = self._extract_value(message, "file_id")
            if file_id:
                result = self.spi_tool(request.owner_username, file_id)
                return self._from_tool_result(result, route="spi")

        if self.diff_tool and self._looks_like_diff(message):
            left_file_id = self._extract_value(message, "left_file_id")
            right_file_id = self._extract_value(message, "right_file_id")
            if left_file_id and right_file_id:
                result = self.diff_tool(request.owner_username, left_file_id, right_file_id)
                return self._from_tool_result(result, route="diff")

        if not request.use_knowledge_base:
            return AgentResponse(answer="知识库已禁用，当前 Agent runner 未配置普通聊天模型。", route="direct")

        result = self.rag_tool(message)
        return self._from_tool_result(result, route="rag")

    @staticmethod
    def _from_tool_result(result: AgentToolResult, route: str) -> AgentResponse:
        data = result.data or {}
        return AgentResponse(
            answer=result.content,
            sources=data.get("sources", []),
            data=data,
            route=route,
        )

    @staticmethod
    def _looks_like_translation(message: str) -> bool:
        lowered = message.lower()
        return "translate" in lowered or "翻译" in message

    @staticmethod
    def _looks_like_spi(message: str) -> bool:
        lowered = message.lower()
        return "spi" in lowered or "解析" in message

    @staticmethod
    def _looks_like_diff(message: str) -> bool:
        lowered = message.lower()
        return "diff" in lowered or "差分" in message or "比较" in message

    @staticmethod
    def _extract_value(message: str, key: str) -> str | None:
        pattern = rf"{re.escape(key)}\s*[:=]\s*([^\s,，;；]+)"
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
        return None

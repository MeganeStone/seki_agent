import re
from dataclasses import dataclass, replace
from typing import Protocol

from app.core.api_keys import temporary_env_api_key
from app.services.agent_tools import (
    AgentToolResult,
    ChatAgentTool,
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
    agent_name: str = "main_agent"
    api_key: str | None = None


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


class CodeAgentUnavailableRunner:
    """Placeholder code-agent boundary until safe code execution is designed."""

    def run(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            answer=(
                "代码助手能力正在迁移中。当前已建立上下文隔离的 code_agent 边界，"
                "但尚未开放文件写入、删除或命令执行。"
            ),
            data={"agent_name": request.agent_name},
            route="code_agent",
        )


class HandoffAgentRunner:
    """Routes requests between the main agent and isolated sub-agents."""

    def __init__(
        self,
        main_runner: AgentRunner,
        code_runner: AgentRunner | None = None,
        main_agent_name: str = "main_agent",
        code_agent_name: str = "code_agent",
        enable_keyword_routing: bool = False,
    ):
        self.main_runner = main_runner
        self.code_runner = code_runner or CodeAgentUnavailableRunner()
        self.main_agent_name = main_agent_name
        self.code_agent_name = code_agent_name
        self.enable_keyword_routing = enable_keyword_routing

    def run(self, request: AgentRequest) -> AgentResponse:
        if request.agent_name == self.code_agent_name or (
            self.enable_keyword_routing and self._looks_like_code_task(request.message)
        ):
            return self.code_runner.run(replace(request, agent_name=self.code_agent_name))
        return self.main_runner.run(replace(request, agent_name=self.main_agent_name))

    @staticmethod
    def _looks_like_code_task(message: str) -> bool:
        lowered = message.lower()
        code_keywords = [
            "code",
            "python",
            "script",
            "shell",
            "debug",
            "代码",
            "脚本",
            "调试",
            "运行命令",
            "修改文件",
            "写文件",
        ]
        return any(keyword in lowered or keyword in message for keyword in code_keywords)


class RuleBasedAgentRunner:
    """Temporary deterministic runner for Agent wiring tests.

    This runner keeps orchestration testable before the real LangGraph runner is
    introduced. It routes explicit tool requests by simple text patterns and
    delegates everything else to RAG when knowledge base usage is enabled.
    """

    def __init__(
        self,
        rag_tool: RagAgentTool,
        chat_tool: ChatAgentTool | None = None,
        translation_tool: TranslationAgentTool | None = None,
        spi_tool: SpiAgentTool | None = None,
        diff_tool: DiffAgentTool | None = None,
    ):
        self.rag_tool = rag_tool
        self.chat_tool = chat_tool
        self.translation_tool = translation_tool
        self.spi_tool = spi_tool
        self.diff_tool = diff_tool

    def run(self, request: AgentRequest) -> AgentResponse:
        message = request.message.strip()

        if self.translation_tool and self._looks_like_translation(message):
            file_id = self._extract_value(message, "file_id")
            target_language = self._extract_value(message, "target_language") or self._extract_value(message, "target_lang")
            if file_id and target_language:
                with temporary_env_api_key("TRANSLATE_API_KEY", request.api_key):
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
            if self.chat_tool is None:
                return AgentResponse(answer="知识库已禁用，当前 Agent runner 未配置普通聊天模型。", route="direct")
            result = self.chat_tool(message, api_key=request.api_key)
            return self._from_tool_result(result, route="direct")

        with temporary_env_api_key("SEKI_RAG_API_KEY", request.api_key):
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

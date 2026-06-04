import json
import sqlite3
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import HTTPException, status

from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import ChatMessageRead, ChatMessageResponse, ConversationCreateResponse, ConversationRead
from app.services.agent_runner import AgentRequest, AgentResponse, AgentRunner, ChatHistoryMessage
from app.services.agent_runner_factory import create_default_agent_runner
from app.services.agent_streaming import iter_runner_stream
from app.services.chat_model_service import ChatModelService
from app.services.code_operation_service import CodeOperationService
from app.services.conversation_history import (
    MAX_CONTEXT_MESSAGES,
    AgentSummaryState,
    BuiltAgentHistory,
    build_agent_history,
)
from app.services.diff_service import DiffService
from app.services.file_service import FileService
from app.services.rag_service import RagService
from app.services.spi_service import SpiService
from app.services.translation_service import TranslationService


class AgentService:
    """面向前端 Chat API 的 Agent 对话边界。

    这一层负责校验会话归属、持久化 user/assistant 消息、整理历史上下文，
    然后把真正的推理和工具调用交给 AgentRunner。这样以后替换 LangGraph、
    增加流式协议或接入更多工具时，不需要改前端 API 契约。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        rag_service: RagService | None = None,
        file_service: FileService | None = None,
        translation_service: TranslationService | None = None,
        spi_service: SpiService | None = None,
        diff_service: DiffService | None = None,
        runner: AgentRunner | None = None,
        chat_model_service: ChatModelService | None = None,
    ):
        self.conn = conn
        self.chats = ChatRepository(conn)
        self.chats.initialize()
        self.rag_service = rag_service or RagService()
        self.chat_model_service = chat_model_service or ChatModelService()
        self._last_built_histories: dict[str, BuiltAgentHistory] = {}
        self.runner = runner or create_default_agent_runner(
            self.rag_service,
            file_service=file_service,
            translation_service=translation_service,
            spi_service=spi_service,
            diff_service=diff_service,
            code_operation_service=CodeOperationService(self.conn),
        )

    def create_conversation(self, owner_username: str) -> ConversationCreateResponse:
        """为指定用户创建会话记录，conversation_id 使用随机 uuid hex。"""
        conversation_id = uuid4().hex
        row = self.chats.create_conversation(conversation_id, owner_username)
        return ConversationCreateResponse(conversation_id=row["id"], created_at=row["created_at"])

    def list_conversations(self, owner_username: str, limit: int = 50) -> list[ConversationRead]:
        return [
            ConversationRead(
                conversation_id=row["id"],
                title=self._conversation_title(row["title"], row["id"]),
                message_count=int(row["message_count"] or 0),
                active_agent=row["active_agent"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in self.chats.list_conversations(owner_username, limit=limit)
        ]

    def delete_conversation(self, owner_username: str, conversation_id: str) -> None:
        deleted = self.chats.delete_conversation(conversation_id, owner_username)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    def ask(
        self,
        owner_username: str,
        conversation_id: str,
        message: str,
        use_knowledge_base: bool = True,
        api_key: str | None = None,
        web_search_api_key: str | None = None,
    ) -> ChatMessageResponse:
        """执行一次 Agent 问答并落库。

        处理顺序很重要：
        1. 先读取历史，再写入本轮 user 消息，避免本轮消息在 history 中重复出现。
        2. runner 返回 pending 操作时，把它持久化到 code_operations，前端才能确认。
        3. assistant 最终回答始终写入聊天记录，保证下一轮 Agent 有记忆。
        """
        clean_message = message.strip()
        if not clean_message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required")

        conversation, active_agent, agent_request = self._build_agent_request(
            owner_username=owner_username,
            conversation_id=conversation_id,
            message=clean_message,
            use_knowledge_base=use_knowledge_base,
            api_key=api_key,
            web_search_api_key=web_search_api_key,
        )
        result = self.runner.run(agent_request)
        return self._finalize_agent_result(
            owner_username=owner_username,
            conversation_id=conversation_id,
            clean_message=clean_message,
            active_agent=active_agent,
            result=result,
            built_histories=self._last_built_histories,
        )

    async def ask_stream(
        self,
        owner_username: str,
        conversation_id: str,
        message: str,
        use_knowledge_base: bool = True,
        api_key: str | None = None,
        web_search_api_key: str | None = None,
    ) -> AsyncIterator:
        from app.services.agent_runner import AgentStreamEvent

        clean_message = message.strip()
        if not clean_message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required")

        conversation, active_agent, agent_request = self._build_agent_request(
            owner_username=owner_username,
            conversation_id=conversation_id,
            message=clean_message,
            use_knowledge_base=use_knowledge_base,
            api_key=api_key,
            web_search_api_key=web_search_api_key,
        )

        final_response: ChatMessageResponse | None = None
        async for event in iter_runner_stream(agent_request, self.runner):
            if event.kind == "final" and event.response is not None:
                final_response = self._finalize_agent_result(
                    owner_username=owner_username,
                    conversation_id=conversation_id,
                    clean_message=clean_message,
                    active_agent=active_agent,
                    result=event.response,
                    built_histories=self._last_built_histories,
                )
                yield AgentStreamEvent(kind="final", response=final_response)
                continue
            yield event

        if final_response is None:
            result = self.runner.run(agent_request)
            final_response = self._finalize_agent_result(
                owner_username=owner_username,
                conversation_id=conversation_id,
                clean_message=clean_message,
                active_agent=active_agent,
                result=result,
                built_histories=self._last_built_histories,
            )
            yield AgentStreamEvent(kind="final", response=final_response)

    def _build_agent_request(
        self,
        *,
        owner_username: str,
        conversation_id: str,
        message: str,
        use_knowledge_base: bool,
        api_key: str | None,
        web_search_api_key: str | None,
    ) -> tuple[sqlite3.Row, str, AgentRequest]:
        conversation = self.chats.get_conversation(conversation_id, owner_username)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        active_agent = str(conversation["active_agent"] or "main_agent")

        built_histories: dict[str, BuiltAgentHistory] = {}
        agent_histories: dict[str, tuple[ChatHistoryMessage, ...]] = {}
        for agent_name in ("main_agent", "code_agent"):
            built = self._history_for_agent(
                conversation_id,
                owner_username,
                agent_name,
                conversation=conversation,
                api_key=api_key,
            )
            built_histories[agent_name] = built
            agent_histories[agent_name] = built.messages

        self._last_built_histories = built_histories
        history = agent_histories.get(active_agent, ())
        request = AgentRequest(
            owner_username=owner_username,
            conversation_id=conversation_id,
            message=message,
            use_knowledge_base=use_knowledge_base,
            agent_name=active_agent,
            api_key=api_key.strip() if api_key else None,
            web_search_api_key=web_search_api_key.strip() if web_search_api_key else None,
            history=history,
            agent_histories=agent_histories,
        )
        return conversation, active_agent, request

    def _finalize_agent_result(
        self,
        *,
        owner_username: str,
        conversation_id: str,
        clean_message: str,
        active_agent: str,
        result: AgentResponse,
        built_histories: dict[str, BuiltAgentHistory],
    ) -> ChatMessageResponse:
        self._persist_summary_states(conversation_id, owner_username, built_histories)
        self._update_active_agent_from_result(owner_username, conversation_id, result)
        response_agent = self._response_agent_name(active_agent, result)
        self.chats.add_message(
            uuid4().hex,
            conversation_id,
            owner_username,
            "user",
            clean_message,
            agent_name=response_agent,
        )
        answer = result.answer
        for item in result.messages_to_store:
            if item.role not in {"assistant", "tool"}:
                continue
            if not item.content.strip() and not (item.metadata or {}).get("tool_calls"):
                continue
            self.chats.add_message(
                uuid4().hex,
                conversation_id,
                owner_username,
                item.role,
                item.content,
                agent_name=response_agent,
                metadata=item.metadata,
            )
        self.chats.add_message(
            uuid4().hex,
            conversation_id,
            owner_username,
            "assistant",
            answer,
            agent_name=response_agent,
        )
        data = result.data
        if data and data.get("requires_confirmation"):
            operation = CodeOperationService(self.conn).create_pending_from_result(
                owner_username=owner_username,
                conversation_id=conversation_id,
                agent_name=str(data.get("agent_name") or "code_agent"),
                operation_type=str(data.get("operation_type") or result.route),
                payload=data,
            )
            data = {**data, "pending_operation": operation.model_dump(mode="json")}

        return ChatMessageResponse(
            conversation_id=conversation_id,
            answer=answer,
            sources=result.sources,
            route=result.route,
            data=data,
        )

    def _history_for_agent(
        self,
        conversation_id: str,
        owner_username: str,
        agent_name: str,
        *,
        conversation: sqlite3.Row | None = None,
        api_key: str | None = None,
    ) -> BuiltAgentHistory:
        raw_messages = tuple(
            ChatHistoryMessage(
                role=row["role"],
                content=row["content"],
                metadata=self._message_metadata(row),
            )
            for row in self.chats.list_messages(
                conversation_id,
                owner_username,
                limit=500,
                agent_name=agent_name,
            )
            if row["role"] in {"user", "assistant", "tool"}
        )
        stored_summary = self._load_summary_state(conversation, agent_name) if conversation is not None else None
        summarizer = None
        if len(raw_messages) > MAX_CONTEXT_MESSAGES:
            summarizer = lambda messages, previous: self.chat_model_service.summarize_messages(
                messages,
                previous_summary=previous,
                api_key=api_key,
            )
        return build_agent_history(
            raw_messages,
            stored_summary=stored_summary,
            summarizer=summarizer,
        )

    def _persist_summary_states(
        self,
        conversation_id: str,
        owner_username: str,
        built_histories: dict[str, BuiltAgentHistory],
    ) -> None:
        summaries = self._load_all_summaries(conversation_id, owner_username)
        changed = False
        for agent_name, built in built_histories.items():
            if built.summary is None:
                continue
            summaries[agent_name] = {
                "text": built.summary.text,
                "covered_message_count": built.summary.covered_message_count,
            }
            changed = True
        if changed:
            self.chats.update_agent_summaries(conversation_id, owner_username, summaries)

    @staticmethod
    def _load_summary_state(conversation: sqlite3.Row, agent_name: str) -> AgentSummaryState | None:
        raw = conversation["agent_summaries"] if "agent_summaries" in conversation.keys() else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        entry = payload.get(agent_name)
        if not isinstance(entry, dict):
            return None
        text = entry.get("text")
        count = entry.get("covered_message_count")
        if not isinstance(text, str) or not text.strip():
            return None
        if not isinstance(count, int) or count < 0:
            return None
        return AgentSummaryState(text=text.strip(), covered_message_count=count)

    def _load_all_summaries(self, conversation_id: str, owner_username: str) -> dict[str, dict[str, object]]:
        conversation = self.chats.get_conversation(conversation_id, owner_username)
        if conversation is None:
            return {}
        raw = conversation["agent_summaries"] if "agent_summaries" in conversation.keys() else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def list_messages(
        self,
        owner_username: str,
        conversation_id: str,
        limit: int = 100,
    ) -> list[ChatMessageRead]:
        conversation = self.chats.get_conversation(conversation_id, owner_username)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return [
            ChatMessageRead(
                id=row["id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in self.chats.list_messages(
                conversation_id,
                owner_username,
                limit=limit,
                exclude_roles=("tool",),
            )
            if not (row["role"] == "assistant" and (self._message_metadata(row) or {}).get("tool_calls"))
        ]

    @staticmethod
    def _response_agent_name(active_agent: str, result: AgentResponse) -> str:
        data = result.data or {}
        for candidate in (result.route, data.get("agent_name"), data.get("active_agent"), active_agent):
            agent_name = str(candidate or "")
            if agent_name in {"main_agent", "code_agent"}:
                return agent_name
        return active_agent

    def _update_active_agent_from_result(
        self,
        owner_username: str,
        conversation_id: str,
        result: AgentResponse,
    ) -> None:
        data = result.data or {}
        next_agent = str(data.get("active_agent") or data.get("agent_name") or result.route or "main_agent")
        if next_agent not in {"main_agent", "code_agent"}:
            next_agent = "main_agent"
        self.chats.update_active_agent(conversation_id, owner_username, next_agent)

    @staticmethod
    def _message_metadata(row: sqlite3.Row) -> dict | None:
        raw = row["metadata"] if "metadata" in row.keys() else None
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) and value else None

    @staticmethod
    def _conversation_title(title: object, conversation_id: str) -> str:
        if isinstance(title, str):
            normalized = " ".join(title.split())
            if normalized:
                return normalized[:40]
        return f"新对话 {conversation_id[:8]}"

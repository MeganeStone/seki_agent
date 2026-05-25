import sqlite3
from uuid import uuid4

from fastapi import HTTPException, status

from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import ChatMessageRead, ChatMessageResponse, ConversationCreateResponse
from app.services.agent_runner import AgentRequest, AgentResponse, AgentRunner, ChatHistoryMessage
from app.services.agent_runner_factory import create_default_agent_runner
from app.services.code_operation_service import CodeOperationService
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
    ):
        self.conn = conn
        self.chats = ChatRepository(conn)
        self.chats.initialize()
        self.rag_service = rag_service or RagService()
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

        conversation = self.chats.get_conversation(conversation_id, owner_username)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        active_agent = str(conversation["active_agent"] or "main_agent")

        history = tuple(
            ChatHistoryMessage(role=row["role"], content=row["content"])
            for row in self.chats.list_messages(conversation_id, owner_username, limit=20)
            if row["role"] in {"user", "assistant"}
        )
        self.chats.add_message(uuid4().hex, conversation_id, owner_username, "user", clean_message)
        result = self.runner.run(
            AgentRequest(
                owner_username=owner_username,
                conversation_id=conversation_id,
                message=clean_message,
                use_knowledge_base=use_knowledge_base,
                agent_name=active_agent,
                api_key=api_key.strip() if api_key else None,
                web_search_api_key=web_search_api_key.strip() if web_search_api_key else None,
                history=history,
            )
        )
        self._update_active_agent_from_result(owner_username, conversation_id, result)
        answer = result.answer
        for item in result.messages_to_store:
            if item.role == "tool" and item.content.strip():
                self.chats.add_message(uuid4().hex, conversation_id, owner_username, "tool", item.content)
        self.chats.add_message(uuid4().hex, conversation_id, owner_username, "assistant", answer)
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
            for row in self.chats.list_messages(conversation_id, owner_username, limit=limit)
        ]

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

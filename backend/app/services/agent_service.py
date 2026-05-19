import sqlite3
from uuid import uuid4

from fastapi import HTTPException, status

from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import ChatMessageResponse, ConversationCreateResponse
from app.services.agent_runner import AgentRequest, AgentRunner
from app.services.agent_runner_factory import create_default_agent_runner
from app.services.diff_service import DiffService
from app.services.file_service import FileService
from app.services.rag_service import RagService
from app.services.spi_service import SpiService
from app.services.translation_service import TranslationService


class AgentService:
    """Conversation boundary for the user-facing Agent entrypoint.

    The first implementation delegates answer generation to RagService. Keeping
    this boundary separate lets us add LangGraph orchestration and tool routing
    without changing the Chat API or frontend contract.
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
        )

    def create_conversation(self, owner_username: str) -> ConversationCreateResponse:
        conversation_id = uuid4().hex
        row = self.chats.create_conversation(conversation_id, owner_username)
        return ConversationCreateResponse(conversation_id=row["id"], created_at=row["created_at"])

    def ask(
        self,
        owner_username: str,
        conversation_id: str,
        message: str,
        use_knowledge_base: bool = True,
    ) -> ChatMessageResponse:
        clean_message = message.strip()
        if not clean_message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required")

        conversation = self.chats.get_conversation(conversation_id, owner_username)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        self.chats.add_message(uuid4().hex, conversation_id, owner_username, "user", clean_message)
        result = self.runner.run(
            AgentRequest(
                owner_username=owner_username,
                conversation_id=conversation_id,
                message=clean_message,
                use_knowledge_base=use_knowledge_base,
            )
        )
        answer = result.answer
        self.chats.add_message(uuid4().hex, conversation_id, owner_username, "assistant", answer)

        return ChatMessageResponse(
            conversation_id=conversation_id,
            answer=answer,
            sources=result.sources,
            route=result.route,
            data=result.data,
        )

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_agent_service, get_current_user
from app.schemas.auth import UserRead
from app.schemas.chat import ChatMessageCreate, ChatMessageResponse, ConversationCreateResponse
from app.services.agent_service import AgentService


router = APIRouter(prefix="/chat")


@router.post("/conversations", response_model=ConversationCreateResponse)
def create_conversation(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ConversationCreateResponse:
    return agent_service.create_conversation(current_user.username)


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageResponse)
def create_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatMessageResponse:
    return agent_service.ask(
        current_user.username,
        conversation_id,
        payload.message,
        use_knowledge_base=payload.use_knowledge_base,
        api_key=payload.api_key,
    )

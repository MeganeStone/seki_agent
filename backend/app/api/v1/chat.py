import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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
    """创建一个归属于当前用户的新 Agent 对话。"""
    return agent_service.create_conversation(current_user.username)


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageResponse)
def create_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatMessageResponse:
    """非流式 Agent 消息接口。

    主要供兼容或调试使用；前端优先走 `/messages/stream`，失败时会回退到此接口。
    """
    return agent_service.ask(
        current_user.username,
        conversation_id,
        payload.message,
        use_knowledge_base=payload.use_knowledge_base,
        api_key=payload.api_key,
        web_search_api_key=payload.web_search_api_key,
    )


@router.post("/conversations/{conversation_id}/messages/stream")
def create_message_stream(
    conversation_id: str,
    payload: ChatMessageCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> StreamingResponse:
    """SSE 流式消息接口。

    当前实现是在 API 层把完整回答按字符切成 delta 事件，前端因此能看到增量
    输出；后续要做真正 token 级流式，需要把 AgentRunner 协议扩展为原生 stream。
    """
    def event_stream() -> Iterator[str]:
        response = agent_service.ask(
            current_user.username,
            conversation_id,
            payload.message,
            use_knowledge_base=payload.use_knowledge_base,
            api_key=payload.api_key,
            web_search_api_key=payload.web_search_api_key,
        )
        for char in response.answer:
            yield f"event: delta\ndata: {json.dumps({'text': char}, ensure_ascii=False)}\n\n"
        yield f"event: final\ndata: {response.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

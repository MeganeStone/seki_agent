from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_agent_service, get_current_user
from app.schemas.auth import UserRead
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatMessageResponse,
    ConversationCreateResponse,
    ConversationRead,
)
from app.services.agent_service import AgentService
from app.services.agent_streaming import stream_event_to_sse


router = APIRouter(prefix="/chat")


@router.post("/conversations", response_model=ConversationCreateResponse)
def create_conversation(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ConversationCreateResponse:
    """创建一个归属于当前用户的新 Agent 对话。"""
    return agent_service.create_conversation(current_user.username)


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    limit: int = 50,
) -> list[ConversationRead]:
    """列出当前用户的 Agent 会话，供前端侧栏恢复历史对话。"""
    return agent_service.list_conversations(current_user.username, limit=limit)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> Response:
    """删除当前用户自己的会话及消息。"""
    agent_service.delete_conversation(current_user.username, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    )


@router.post("/conversations/{conversation_id}/messages/stream")
async def create_message_stream(
    conversation_id: str,
    payload: ChatMessageCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> StreamingResponse:
    """SSE 流式消息接口。

    通过 LangGraph `astream_events` 推送 token delta、工具开始/结束/错误和最终
    `final` 事件；前端可实时展示回答与工具执行状态。
    """

    async def event_stream() -> AsyncIterator[str]:
        async for event in agent_service.ask_stream(
            current_user.username,
            conversation_id,
            payload.message,
            use_knowledge_base=payload.use_knowledge_base,
        ):
            yield stream_event_to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/conversations/{conversation_id}/token-limit/extend")
def extend_token_limit(
    conversation_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> dict:
    """用户在前端确认继续对话后，把该会话的 token 限额倍数 +1。"""
    return agent_service.extend_token_limit(current_user.username, conversation_id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageRead])
def list_messages(
    conversation_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
    limit: int = 100,
) -> list[ChatMessageRead]:
    """读取当前用户某个 conversation 的历史消息，供前端页面恢复对话使用。"""
    return agent_service.list_messages(current_user.username, conversation_id, limit=limit)

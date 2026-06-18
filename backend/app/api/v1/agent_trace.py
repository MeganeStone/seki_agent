from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_agent_trace_service, get_current_user
from app.schemas.agent_trace import AgentTraceRunDetailResponse, AgentTraceRunListResponse
from app.schemas.auth import UserRead
from app.services.agent_trace_service import AgentTraceService


router = APIRouter(prefix="/agent-trace")


@router.get("/runs", response_model=AgentTraceRunListResponse)
def list_trace_runs(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    trace_service: Annotated[AgentTraceService, Depends(get_agent_trace_service)],
    conversation_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AgentTraceRunListResponse:
    """列出当前用户的 Agent 运行追踪记录。"""
    return AgentTraceRunListResponse(
        items=trace_service.list_runs(current_user.username, conversation_id=conversation_id, limit=limit)
    )


@router.get("/runs/{run_id}", response_model=AgentTraceRunDetailResponse)
def get_trace_run(
    run_id: str,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    trace_service: Annotated[AgentTraceService, Depends(get_agent_trace_service)],
) -> AgentTraceRunDetailResponse:
    """查看一次 Agent 运行的详细事件（工具调用、模型 token 用量）。"""
    return trace_service.get_run_detail(current_user.username, run_id)

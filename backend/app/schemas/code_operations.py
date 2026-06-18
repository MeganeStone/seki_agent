from datetime import datetime

from pydantic import BaseModel, Field


class CodeOperationResult(BaseModel):
    status: str | None = None
    message: str | None = None
    data: dict = Field(default_factory=dict)


class CodeOperationRead(BaseModel):
    operation_id: str
    conversation_id: str
    agent_name: str
    operation_type: str
    status: str
    payload: dict = Field(default_factory=dict)
    result: CodeOperationResult | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class CodeOperationListResponse(BaseModel):
    items: list[CodeOperationRead]


class CodeAuditRead(BaseModel):
    record_id: str
    conversation_id: str
    agent_name: str
    tool_name: str
    status: str
    target: str
    message: str
    detail: dict | None = None
    started_at: datetime
    finished_at: datetime


class CodeAuditListResponse(BaseModel):
    items: list[CodeAuditRead]

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

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreateResponse(BaseModel):
    conversation_id: str
    created_at: datetime


class ChatMessageCreate(BaseModel):
    message: str = Field(min_length=1)
    use_knowledge_base: bool = True


class ChatMessageRead(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class ChatSource(BaseModel):
    file_name: str | None = None
    page_number: str | int | None = None
    snippet: str | None = None


class ChatMessageResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
    route: str | None = None
    data: dict | None = None

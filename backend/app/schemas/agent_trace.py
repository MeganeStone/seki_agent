from pydantic import BaseModel


class AgentTraceEventRead(BaseModel):
    event_id: str
    seq: int
    event_type: str
    name: str
    status: str
    preview: str = ""
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    created_at: str


class AgentTraceRunRead(BaseModel):
    run_id: str
    conversation_id: str
    agent_name: str
    status: str
    input_preview: str = ""
    answer_preview: str = ""
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None


class AgentTraceRunListResponse(BaseModel):
    items: list[AgentTraceRunRead]


class AgentTraceRunDetailResponse(BaseModel):
    run: AgentTraceRunRead
    events: list[AgentTraceEventRead]

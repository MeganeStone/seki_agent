from datetime import datetime

from pydantic import BaseModel


class DiffTaskCreate(BaseModel):
    left_file_id: str
    right_file_id: str


class DiffSummary(BaseModel):
    changed: bool
    bin_changed: bool
    lib_changed: bool


class DiffTaskRead(BaseModel):
    task_id: str
    status: str
    summary: DiffSummary | None = None
    result_file_id: str | None = None
    result_text: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


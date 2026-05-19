from datetime import datetime

from pydantic import BaseModel


class SpiTaskCreate(BaseModel):
    file_id: str


class SpiTaskRead(BaseModel):
    task_id: str
    status: str
    result_file_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


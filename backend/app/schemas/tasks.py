from datetime import datetime
from typing import Literal

from pydantic import BaseModel


TaskType = Literal["translation", "spi", "diff"]


class TaskRead(BaseModel):
    task_id: str
    type: TaskType
    status: str
    result_file_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskRead]

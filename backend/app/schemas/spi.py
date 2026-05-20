from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SpiTaskCreate(BaseModel):
    file_id: str | None = None
    file_ids: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_file_id_or_file_ids(self) -> "SpiTaskCreate":
        if self.file_ids:
            return self
        if self.file_id:
            self.file_ids = [self.file_id]
            return self
        raise ValueError("file_id or file_ids is required")


class SpiTaskRead(BaseModel):
    task_id: str
    status: str
    result_file_id: str | None = None
    result_filename: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

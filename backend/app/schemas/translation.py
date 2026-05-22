from datetime import datetime

from pydantic import BaseModel, Field


class TranslationTaskCreate(BaseModel):
    file_id: str
    target_language: str = Field(min_length=1)
    api_key: str | None = None


class TranslationTaskRead(BaseModel):
    task_id: str
    status: str
    target_language: str
    result_file_id: str | None = None
    result_filename: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

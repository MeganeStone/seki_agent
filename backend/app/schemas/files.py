from datetime import datetime

from pydantic import BaseModel


class FileRead(BaseModel):
    id: str
    filename: str
    size: int
    created_at: datetime


class FileListResponse(BaseModel):
    items: list[FileRead]


class DeleteFileResponse(BaseModel):
    deleted: bool


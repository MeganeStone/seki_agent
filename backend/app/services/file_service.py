import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.repositories.file_repository import FileRepository
from app.schemas.files import FileRead

CHUNK_SIZE = 1024 * 1024


class FileService:
    def __init__(self, conn: sqlite3.Connection, workspace_dir: Path | None = None, max_upload_size_bytes: int | None = None):
        settings = get_settings()
        self.files = FileRepository(conn)
        self.files.initialize()
        self.workspace_dir = workspace_dir or settings.workspace_dir
        self.max_upload_size_bytes = max_upload_size_bytes or settings.max_upload_size_bytes

    def list_files(self, owner_username: str) -> list[FileRead]:
        return [self._to_schema(row) for row in self.files.list_for_owner(owner_username)]

    async def save_upload(self, owner_username: str, upload: UploadFile) -> FileRead:
        safe_name = self._sanitize_filename(upload.filename or "uploaded-file")
        file_id = uuid4().hex
        owner_dir = self._owner_dir(owner_username)
        owner_dir.mkdir(parents=True, exist_ok=True)
        target_path = owner_dir / f"{file_id}_{safe_name}"

        size = 0
        try:
            with target_path.open("wb") as output:
                while chunk := await upload.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_upload_size_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="Uploaded file is too large",
                        )
                    output.write(chunk)
        except Exception:
            if target_path.exists():
                target_path.unlink()
            raise
        finally:
            await upload.close()

        row = self.files.create(file_id, owner_username, safe_name, str(target_path), size)
        return self._to_schema(row)

    def get_file_path(self, owner_username: str, file_id: str) -> tuple[Path, str]:
        row = self.files.get_for_owner(file_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        path = Path(row["storage_path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File content not found")
        self._ensure_under_workspace(path)
        return path, row["filename"]

    def save_generated_content(self, owner_username: str, filename: str, content: bytes) -> FileRead:
        safe_name = self._sanitize_filename(filename)
        file_id = uuid4().hex
        owner_dir = self._owner_dir(owner_username)
        owner_dir.mkdir(parents=True, exist_ok=True)
        target_path = owner_dir / f"{file_id}_{safe_name}"
        target_path.write_bytes(content)
        row = self.files.create(file_id, owner_username, safe_name, str(target_path), len(content))
        return self._to_schema(row)

    def delete_file(self, owner_username: str, file_id: str) -> bool:
        row = self.files.delete_for_owner(file_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        path = Path(row["storage_path"])
        self._ensure_under_workspace(path)
        if path.exists() and path.is_file():
            path.unlink()
        return True

    def _owner_dir(self, owner_username: str) -> Path:
        safe_owner = re.sub(r"[^a-zA-Z0-9_-]", "_", owner_username.strip())
        path = self.workspace_dir / safe_owner
        self._ensure_under_workspace(path)
        return path

    def _ensure_under_workspace(self, path: Path) -> None:
        workspace = self.workspace_dir.resolve()
        resolved = path.resolve()
        if workspace != resolved and workspace not in resolved.parents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        name = Path(filename).name.strip()
        name = re.sub(r"[^a-zA-Z0-9._ -]", "_", name)
        return name or "uploaded-file"

    @staticmethod
    def _to_schema(row: sqlite3.Row) -> FileRead:
        return FileRead(
            id=row["id"],
            filename=row["filename"],
            size=row["size"],
            created_at=row["created_at"],
        )

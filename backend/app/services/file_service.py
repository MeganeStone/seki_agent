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
    """用户文件管理服务。

    负责把上传文件保存到 `workspace/{owner}`，并把元数据写入数据库。所有读取、
    下载、删除都会再次校验 owner 和真实路径，防止用户通过 file_id 或路径越权。
    """

    def __init__(self, conn: sqlite3.Connection, workspace_dir: Path | None = None, max_upload_size_bytes: int | None = None):
        settings = get_settings()
        self.files = FileRepository(conn)
        self.files.initialize()
        self.workspace_dir = workspace_dir or settings.workspace_dir
        self.max_upload_size_bytes = max_upload_size_bytes or settings.max_upload_size_bytes

    def list_files(self, owner_username: str) -> list[FileRead]:
        self.sync_workspace_files(owner_username)
        return [self._to_schema(row) for row in self.files.list_for_owner(owner_username)]

    def sync_workspace_files(self, owner_username: str) -> None:
        """让 files 表与当前用户 workspace 目录保持一致。

        文件可能由 code agent 直接创建或删除，不一定经过文件管理 API。刷新文件
        列表时需要同时补录磁盘新增文件，并清理磁盘上已经不存在的旧记录。
        """
        self._remove_missing_workspace_records(owner_username)
        self._sync_workspace_files(owner_username)

    def get_file(self, owner_username: str, file_id: str) -> FileRead:
        row = self.files.get_for_owner(file_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return self._to_schema(row)

    async def save_upload(self, owner_username: str, upload: UploadFile) -> FileRead:
        """分块保存上传文件，避免一次性把大文件读入内存。"""
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
        """返回后端内部可读取的真实文件路径。

        业务 service 需要拿到路径交给 legacy 脚本处理，但这个路径不会直接暴露给前端。
        """
        row = self.files.get_for_owner(file_id, owner_username)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        path = Path(row["storage_path"])
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File content not found")
        self._ensure_under_workspace(path)
        return path, row["filename"]

    def save_generated_content(self, owner_username: str, filename: str, content: bytes) -> FileRead:
        """保存业务任务生成的结果文件，并复用统一文件表作为下载入口。"""
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

    def _sync_workspace_files(self, owner_username: str) -> None:
        """把 workspace 目录里尚未登记的文件补录到 files 表。

        code agent 会直接写入用户 workspace，不会走 upload API；列表接口在返回前
        先做一次轻量同步，保证文件管理页能看到 workspace 下的全部文件。
        """
        owner_dir = self._owner_dir(owner_username)
        if not owner_dir.exists():
            return

        owner_root = owner_dir.resolve()
        for path in owner_root.rglob("*"):
            if not path.is_file():
                continue
            resolved = path.resolve()
            self._ensure_under_workspace(resolved)
            if self.files.get_by_storage_path(owner_username, str(resolved)) is not None:
                continue
            relative_name = path.relative_to(owner_root).as_posix()
            self.files.create(
                uuid4().hex,
                owner_username,
                relative_name,
                str(resolved),
                resolved.stat().st_size,
            )

    def _remove_missing_workspace_records(self, owner_username: str) -> None:
        for row in self.files.list_for_owner(owner_username):
            path = Path(row["storage_path"])
            try:
                self._ensure_under_workspace(path)
            except HTTPException:
                # Path is from another machine/environment; treat as orphaned
                self.files.delete_by_storage_path(owner_username, row["storage_path"])
                continue
            if path.exists() and path.is_file():
                continue
            self.files.delete_by_storage_path(owner_username, row["storage_path"])

    def _ensure_under_workspace(self, path: Path) -> None:
        workspace = self.workspace_dir.resolve()
        resolved = path.resolve()
        if workspace != resolved and workspace not in resolved.parents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        name = Path(filename).name.strip()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = re.sub(r"\s+", " ", name)
        return name or "uploaded-file"

    @staticmethod
    def _to_schema(row: sqlite3.Row) -> FileRead:
        return FileRead(
            id=row["id"],
            filename=row["filename"],
            size=row["size"],
            created_at=row["created_at"],
        )

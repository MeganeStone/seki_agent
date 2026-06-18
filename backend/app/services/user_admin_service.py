"""管理员用户管理服务：列出、创建、删除用户并级联清理其数据。"""
import logging
import re
import shutil

from pathlib import Path

import psycopg
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AdminUserRead
from app.services.auth_service import AuthService

logger = logging.getLogger("seki.admin")

# 删除用户时按 owner_username 清理的业务表。
_OWNED_TABLES = [
    "chat_messages",
    "code_pending_operations",
    "code_audit_records",
    "agent_trace_events",
    "agent_trace_runs",
    "conversations",
    "translation_tasks",
    "spi_tasks",
    "diff_tasks",
    "files",
]


class UserAdminService:
    def __init__(self, conn: psycopg.Connection, workspace_dir: Path | None = None):
        self.conn = conn
        self.users = UserRepository(conn)
        self.users.initialize()
        self.auth = AuthService(conn)
        self.workspace_dir = workspace_dir or get_settings().workspace_dir

    def list_users(self) -> list[AdminUserRead]:
        return [
            AdminUserRead(
                username=row["username"],
                is_admin=bool(row["is_admin"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in self.users.list_all()
        ]

    def create_user(self, username: str, password: str, is_admin: bool = False) -> AdminUserRead:
        try:
            user = self.auth.create_user(username, password, is_admin=is_admin)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        row = self.users.get_by_username(user.username)
        return AdminUserRead(
            username=row["username"],
            is_admin=bool(row["is_admin"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def delete_user(self, username: str, acting_username: str) -> None:
        """删除用户并级联清理其文件、任务、会话和审计数据。"""
        clean_username = username.strip()
        if clean_username == acting_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能删除当前登录的管理员自己")
        if self.users.get_by_username(clean_username) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        for table in _OWNED_TABLES:
            if self._table_exists(table):
                self.conn.execute(
                    f"DELETE FROM {table} WHERE owner_username = %s",
                    (clean_username,),
                )
        self.users.delete_user(clean_username)
        self.conn.commit()

        self._remove_workspace_dir(clean_username)
        logger.info(
            "user_deleted",
            extra={"deleted_username": clean_username, "acting_username": acting_username},
        )

    def _table_exists(self, table_name: str) -> bool:
        cursor = self.conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            (table_name,),
        )
        return cursor.fetchone() is not None

    def _remove_workspace_dir(self, username: str) -> None:
        safe_owner = re.sub(r"[^a-zA-Z0-9_-]", "_", username.strip())
        if not safe_owner:
            return
        workspace = (self.workspace_dir / safe_owner).resolve()
        if workspace.exists() and self.workspace_dir.resolve() in workspace.parents:
            shutil.rmtree(workspace, ignore_errors=True)

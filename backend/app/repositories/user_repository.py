import psycopg
from datetime import datetime, timezone


class UserRepository:
    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
        )
        self.conn.commit()

    def get_by_username(self, username: str) -> dict | None:
        cursor = self.conn.execute(
            "SELECT username, password_hash, is_admin, created_at, updated_at FROM users WHERE username = %s",
            (username,),
        )
        return cursor.fetchone()

    def list_all(self) -> list[dict]:
        cursor = self.conn.execute(
            """
            SELECT username, is_admin, created_at, updated_at
            FROM users
            ORDER BY created_at ASC
            """
        )
        return list(cursor.fetchall())

    def upsert_user(self, username: str, password_hash: str, is_admin: bool | None = None) -> None:
        """创建或更新用户。is_admin 为 None 时更新保持原值，新建默认 False。"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO users (username, password_hash, is_admin, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                is_admin = COALESCE(%s, users.is_admin),
                updated_at = excluded.updated_at
            """,
            (username, password_hash, bool(is_admin), now, now, is_admin),
        )
        self.conn.commit()

    def delete_user(self, username: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM users WHERE username = %s RETURNING username",
            (username,),
        )
        deleted = cursor.fetchone() is not None
        self.conn.commit()
        return deleted

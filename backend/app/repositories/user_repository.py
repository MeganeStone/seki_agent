import sqlite3
from datetime import datetime, timezone


class UserRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def get_by_username(self, username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            "SELECT username, password_hash, created_at, updated_at FROM users WHERE username = ?",
            (username,),
        )
        return cursor.fetchone()

    def upsert_user(self, username: str, password_hash: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO users (username, password_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                updated_at = excluded.updated_at
            """,
            (username, password_hash, now, now),
        )
        self.conn.commit()

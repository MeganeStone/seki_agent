import sqlite3
from datetime import datetime, timezone


class SpiRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spi_tasks (
                task_id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                file_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_file_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spi_tasks_owner_username ON spi_tasks(owner_username)"
        )
        self.conn.commit()

    def create(self, task_id: str, owner_username: str, file_id: str) -> sqlite3.Row:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO spi_tasks (
                task_id, owner_username, file_id, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, owner_username, file_id, "pending", now, now),
        )
        self.conn.commit()
        row = self.get_for_owner(task_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create SPI task")
        return row

    def update_result(
        self,
        task_id: str,
        owner_username: str,
        status: str,
        result_file_id: str | None = None,
        error: str | None = None,
    ) -> sqlite3.Row:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE spi_tasks
            SET status = ?, result_file_id = ?, error = ?, updated_at = ?
            WHERE task_id = ? AND owner_username = ?
            """,
            (status, result_file_id, error, now, task_id, owner_username),
        )
        self.conn.commit()
        row = self.get_for_owner(task_id, owner_username)
        if row is None:
            raise RuntimeError("SPI task disappeared")
        return row

    def get_for_owner(self, task_id: str, owner_username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            """
            SELECT task_id, owner_username, file_id, status, result_file_id,
                   error, created_at, updated_at
            FROM spi_tasks
            WHERE task_id = ? AND owner_username = ?
            """,
            (task_id, owner_username),
        )
        return cursor.fetchone()


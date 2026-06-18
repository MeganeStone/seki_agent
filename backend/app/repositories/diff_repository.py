import psycopg
from datetime import datetime, timezone


class DiffRepository:
    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS diff_tasks (
                task_id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                left_file_id TEXT NOT NULL,
                right_file_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_text TEXT,
                result_file_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_diff_tasks_owner_username ON diff_tasks(owner_username)"
        )
        self.conn.commit()

    def create(self, task_id: str, owner_username: str, left_file_id: str, right_file_id: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO diff_tasks (
                task_id, owner_username, left_file_id, right_file_id,
                status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (task_id, owner_username, left_file_id, right_file_id, "pending", now, now),
        )
        self.conn.commit()
        row = self.get_for_owner(task_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create diff task")
        return row

    def update_result(
        self,
        task_id: str,
        owner_username: str,
        status: str,
        result_text: str | None = None,
        result_file_id: str | None = None,
        error: str | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE diff_tasks
            SET status = %s, result_text = %s, result_file_id = %s, error = %s, updated_at = %s
            WHERE task_id = %s AND owner_username = %s
            """,
            (status, result_text, result_file_id, error, now, task_id, owner_username),
        )
        self.conn.commit()
        row = self.get_for_owner(task_id, owner_username)
        if row is None:
            raise RuntimeError("Diff task disappeared")
        return row

    def cancel_for_owner(self, task_id: str, owner_username: str) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE diff_tasks
            SET status = %s, error = NULL, updated_at = %s
            WHERE task_id = %s AND owner_username = %s AND status IN ('pending', 'running')
            """,
            ("cancelled", now, task_id, owner_username),
        )
        self.conn.commit()
        return self.get_for_owner(task_id, owner_username)

    def get_for_owner(self, task_id: str, owner_username: str) -> dict | None:
        cursor = self.conn.execute(
            """
            SELECT task_id, owner_username, left_file_id, right_file_id, status,
                   result_text, result_file_id, error, created_at, updated_at
            FROM diff_tasks
            WHERE task_id = %s AND owner_username = %s
            """,
            (task_id, owner_username),
        )
        return cursor.fetchone()

    def list_for_owner(self, owner_username: str, limit: int = 50) -> list[dict]:
        cursor = self.conn.execute(
            """
            SELECT task_id, owner_username, left_file_id, right_file_id, status,
                   result_text, result_file_id, error, created_at, updated_at
            FROM diff_tasks
            WHERE owner_username = %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (owner_username, limit),
        )
        return list(cursor.fetchall())

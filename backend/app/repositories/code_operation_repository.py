import json
import sqlite3
from datetime import datetime, timezone


class CodeOperationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS code_pending_operations (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_code_pending_operations_owner_status
            ON code_pending_operations(owner_username, status)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_code_pending_operations_conversation
            ON code_pending_operations(owner_username, conversation_id)
            """
        )
        self.conn.commit()

    def create(
        self,
        operation_id: str,
        owner_username: str,
        conversation_id: str,
        agent_name: str,
        operation_type: str,
        payload: dict,
        expires_at: datetime,
    ) -> sqlite3.Row:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO code_pending_operations (
                id, owner_username, conversation_id, agent_name, operation_type,
                payload_json, status, result_json, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_id,
                owner_username,
                conversation_id,
                agent_name,
                operation_type,
                json.dumps(payload, ensure_ascii=False),
                "pending",
                None,
                now,
                now,
                expires_at.isoformat(),
            ),
        )
        self.conn.commit()
        row = self.get_for_owner(operation_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create code pending operation")
        return row

    def list_for_owner(
        self,
        owner_username: str,
        conversation_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        filters = ["owner_username = ?"]
        params: list[object] = [owner_username]
        if conversation_id:
            filters.append("conversation_id = ?")
            params.append(conversation_id)
        if status:
            filters.append("status = ?")
            params.append(status)
        params.append(limit)
        cursor = self.conn.execute(
            f"""
            SELECT *
            FROM code_pending_operations
            WHERE {" AND ".join(filters)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )
        return list(cursor.fetchall())

    def get_for_owner(self, operation_id: str, owner_username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            """
            SELECT *
            FROM code_pending_operations
            WHERE id = ? AND owner_username = ?
            """,
            (operation_id, owner_username),
        )
        return cursor.fetchone()

    def update_status(
        self,
        operation_id: str,
        owner_username: str,
        status: str,
        result: dict | None = None,
    ) -> sqlite3.Row | None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE code_pending_operations
            SET status = ?, result_json = ?, updated_at = ?
            WHERE id = ? AND owner_username = ?
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                now,
                operation_id,
                owner_username,
            ),
        )
        self.conn.commit()
        return self.get_for_owner(operation_id, owner_username)

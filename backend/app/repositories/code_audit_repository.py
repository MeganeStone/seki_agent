import json
import psycopg


class CodeAuditRepository:
    """code agent 操作审计表读写。

    每次 CodeExecutionService 执行工具（无论成功、失败还是被拒绝）都会落一条
    记录，用于事后追溯“哪个用户在哪个会话里让 code agent 做了什么”。
    """

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS code_audit_records (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                target TEXT NOT NULL,
                message TEXT NOT NULL,
                detail_json TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_code_audit_records_owner_time
            ON code_audit_records(owner_username, finished_at)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_code_audit_records_conversation
            ON code_audit_records(owner_username, conversation_id)
            """
        )
        self.conn.commit()

    def create(
        self,
        record_id: str,
        owner_username: str,
        conversation_id: str,
        agent_name: str,
        tool_name: str,
        status: str,
        target: str,
        message: str,
        detail: dict | None,
        started_at: str,
        finished_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO code_audit_records (
                id, owner_username, conversation_id, agent_name, tool_name,
                status, target, message, detail_json, started_at, finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record_id,
                owner_username,
                conversation_id,
                agent_name,
                tool_name,
                status,
                target,
                message,
                json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                started_at,
                finished_at,
            ),
        )
        self.conn.commit()

    def list_for_owner(
        self,
        owner_username: str,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        filters = ["owner_username = %s"]
        params: list[object] = [owner_username]
        if conversation_id:
            filters.append("conversation_id = %s")
            params.append(conversation_id)
        params.append(limit)
        cursor = self.conn.execute(
            f"""
            SELECT *
            FROM code_audit_records
            WHERE {" AND ".join(filters)}
            ORDER BY finished_at DESC
            LIMIT %s
            """,
            params,
        )
        return list(cursor.fetchall())

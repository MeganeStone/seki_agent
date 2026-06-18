import psycopg


class AgentTraceRepository:
    """Agent 运行追踪表读写：每轮对话一条 run，工具/模型调用各一条 event。"""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_trace_runs (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                input_preview TEXT NOT NULL DEFAULT '',
                answer_preview TEXT NOT NULL DEFAULT '',
                error TEXT,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms INTEGER
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_trace_runs_owner_time
            ON agent_trace_runs(owner_username, started_at)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_trace_runs_conversation
            ON agent_trace_runs(owner_username, conversation_id)
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_trace_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                preview TEXT NOT NULL DEFAULT '',
                error TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                duration_ms INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_trace_events_run
            ON agent_trace_events(run_id, seq)
            """
        )
        self.conn.commit()

    def create_run(
        self,
        run_id: str,
        owner_username: str,
        conversation_id: str,
        agent_name: str,
        input_preview: str,
        started_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_trace_runs (
                id, owner_username, conversation_id, agent_name, status,
                input_preview, started_at
            )
            VALUES (%s, %s, %s, %s, 'running', %s, %s)
            """,
            (run_id, owner_username, conversation_id, agent_name, input_preview, started_at),
        )
        self.conn.commit()

    def finish_run(
        self,
        run_id: str,
        owner_username: str,
        status: str,
        answer_preview: str,
        error: str | None,
        input_tokens: int,
        output_tokens: int,
        finished_at: str,
        duration_ms: int,
        agent_name: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE agent_trace_runs
            SET status = %s, answer_preview = %s, error = %s,
                input_tokens = %s, output_tokens = %s, total_tokens = %s,
                finished_at = %s, duration_ms = %s,
                agent_name = COALESCE(%s, agent_name)
            WHERE id = %s AND owner_username = %s
            """,
            (
                status,
                answer_preview,
                error,
                input_tokens,
                output_tokens,
                input_tokens + output_tokens,
                finished_at,
                duration_ms,
                agent_name,
                run_id,
                owner_username,
            ),
        )
        self.conn.commit()

    def add_event(
        self,
        event_id: str,
        run_id: str,
        owner_username: str,
        seq: int,
        event_type: str,
        name: str,
        status: str,
        preview: str,
        error: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        duration_ms: int | None,
        created_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_trace_events (
                id, run_id, owner_username, seq, event_type, name, status,
                preview, error, input_tokens, output_tokens, duration_ms, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_id,
                run_id,
                owner_username,
                seq,
                event_type,
                name,
                status,
                preview,
                error,
                input_tokens,
                output_tokens,
                duration_ms,
                created_at,
            ),
        )
        self.conn.commit()

    def list_runs(
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
            FROM agent_trace_runs
            WHERE {" AND ".join(filters)}
            ORDER BY started_at DESC
            LIMIT %s
            """,
            params,
        )
        return list(cursor.fetchall())

    def get_run(self, run_id: str, owner_username: str) -> dict | None:
        cursor = self.conn.execute(
            "SELECT * FROM agent_trace_runs WHERE id = %s AND owner_username = %s",
            (run_id, owner_username),
        )
        return cursor.fetchone()

    def list_events(self, run_id: str, owner_username: str) -> list[dict]:
        cursor = self.conn.execute(
            """
            SELECT *
            FROM agent_trace_events
            WHERE run_id = %s AND owner_username = %s
            ORDER BY seq ASC
            """,
            (run_id, owner_username),
        )
        return list(cursor.fetchall())

import psycopg
import json
from datetime import datetime, timezone


class ChatRepository:
    """对话和消息表仓储。

    仓储层只负责 SQL 和行数据，不包含业务判断；用户归属过滤在 SQL 条件里完成，
    上层 service 再决定不存在时返回什么 HTTP 错误。
    """

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                active_agent TEXT NOT NULL DEFAULT 'main_agent',
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS active_agent TEXT NOT NULL DEFAULT 'main_agent'"
        )
        self.conn.execute(
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS agent_summaries TEXT NOT NULL DEFAULT '{}'"
        )
        self.conn.execute(
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS total_tokens BIGINT NOT NULL DEFAULT 0"
        )
        self.conn.execute(
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS token_limit_multiplier INTEGER NOT NULL DEFAULT 1"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                agent_name TEXT NOT NULL DEFAULT 'main_agent',
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            )
            """
        )
        self.conn.execute(
            "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS agent_name TEXT NOT NULL DEFAULT 'main_agent'"
        )
        self.conn.execute(
            "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS metadata TEXT NOT NULL DEFAULT '{}'"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_owner_username ON conversations(owner_username)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id)"
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_agent
            ON chat_messages(conversation_id, agent_name)
            """
        )
        self.conn.commit()

    def create_conversation(self, conversation_id: str, owner_username: str) -> dict:
        created_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO conversations (id, owner_username, active_agent, created_at) VALUES (%s, %s, %s, %s)",
            (conversation_id, owner_username, "main_agent", created_at),
        )
        self.conn.commit()
        row = self.get_conversation(conversation_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create conversation")
        return row

    def list_conversations(self, owner_username: str, limit: int = 50) -> list[dict]:
        cursor = self.conn.execute(
            """
            SELECT
                c.id,
                c.owner_username,
                c.active_agent,
                c.created_at,
                COALESCE(MAX(m.created_at), c.created_at) AS updated_at,
                COUNT(m.id) AS message_count,
                (
                    SELECT m2.content
                    FROM chat_messages AS m2
                    WHERE m2.conversation_id = c.id
                      AND m2.owner_username = c.owner_username
                      AND m2.role = 'user'
                    ORDER BY m2.created_at ASC
                    LIMIT 1
                ) AS title
            FROM conversations AS c
            LEFT JOIN chat_messages AS m
              ON m.conversation_id = c.id
             AND m.owner_username = c.owner_username
            WHERE c.owner_username = %s
            GROUP BY c.id, c.owner_username, c.active_agent, c.created_at
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (owner_username, max(1, min(limit, 200))),
        )
        return list(cursor.fetchall())

    def get_conversation(self, conversation_id: str, owner_username: str) -> dict | None:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, active_agent, agent_summaries,
                   total_tokens, token_limit_multiplier, created_at
            FROM conversations
            WHERE id = %s AND owner_username = %s
            """,
            (conversation_id, owner_username),
        )
        return cursor.fetchone()

    def add_conversation_tokens(self, conversation_id: str, owner_username: str, tokens: int) -> int:
        """把本轮 token 累加到会话总量，返回累加后的总量。"""
        cursor = self.conn.execute(
            """
            UPDATE conversations
            SET total_tokens = total_tokens + %s
            WHERE id = %s AND owner_username = %s
            RETURNING total_tokens
            """,
            (max(0, tokens), conversation_id, owner_username),
        )
        row = cursor.fetchone()
        self.conn.commit()
        return int(row["total_tokens"]) if row else 0

    def increment_token_limit_multiplier(self, conversation_id: str, owner_username: str) -> int:
        """用户确认继续后把限额倍数 +1，返回新的倍数。"""
        cursor = self.conn.execute(
            """
            UPDATE conversations
            SET token_limit_multiplier = token_limit_multiplier + 1
            WHERE id = %s AND owner_username = %s
            RETURNING token_limit_multiplier
            """,
            (conversation_id, owner_username),
        )
        row = cursor.fetchone()
        self.conn.commit()
        return int(row["token_limit_multiplier"]) if row else 1

    def delete_conversation(self, conversation_id: str, owner_username: str) -> bool:
        conversation = self.get_conversation(conversation_id, owner_username)
        if conversation is None:
            return False

        self.conn.execute(
            "DELETE FROM chat_messages WHERE conversation_id = %s AND owner_username = %s",
            (conversation_id, owner_username),
        )
        if self._table_exists("code_pending_operations"):
            self.conn.execute(
                "DELETE FROM code_pending_operations WHERE conversation_id = %s AND owner_username = %s",
                (conversation_id, owner_username),
            )
        self.conn.execute(
            "DELETE FROM conversations WHERE id = %s AND owner_username = %s",
            (conversation_id, owner_username),
        )
        self.conn.commit()
        return True

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

    def update_agent_summaries(
        self,
        conversation_id: str,
        owner_username: str,
        summaries: dict[str, dict[str, object]],
    ) -> None:
        payload = json.dumps(summaries, ensure_ascii=False, separators=(",", ":"))
        self.conn.execute(
            """
            UPDATE conversations
            SET agent_summaries = %s
            WHERE id = %s AND owner_username = %s
            """,
            (payload, conversation_id, owner_username),
        )
        self.conn.commit()

    def count_messages(
        self,
        conversation_id: str,
        owner_username: str,
        *,
        agent_name: str | None = None,
    ) -> int:
        query = """
            SELECT COUNT(*) AS total
            FROM chat_messages
            WHERE conversation_id = %s AND owner_username = %s
        """
        params: list[object] = [conversation_id, owner_username]
        if agent_name is not None:
            query += " AND agent_name = %s"
            params.append(agent_name)
        cursor = self.conn.execute(query, params)
        row = cursor.fetchone()
        return int(row["total"] if row else 0)

    def update_active_agent(self, conversation_id: str, owner_username: str, active_agent: str) -> None:
        self.conn.execute(
            """
            UPDATE conversations
            SET active_agent = %s
            WHERE id = %s AND owner_username = %s
            """,
            (active_agent, conversation_id, owner_username),
        )
        self.conn.commit()

    def add_message(
        self,
        message_id: str,
        conversation_id: str,
        owner_username: str,
        role: str,
        content: str,
        agent_name: str = "main_agent",
        metadata: dict | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))
        self.conn.execute(
            """
            INSERT INTO chat_messages (id, conversation_id, owner_username, role, content, agent_name, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (message_id, conversation_id, owner_username, role, content, agent_name, metadata_json, created_at),
        )
        self.conn.commit()

    def list_messages(
        self,
        conversation_id: str,
        owner_username: str,
        limit: int = 20,
        *,
        exclude_roles: tuple[str, ...] | None = None,
        agent_name: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT id, conversation_id, owner_username, role, content, agent_name, metadata, created_at
            FROM chat_messages
            WHERE conversation_id = %s AND owner_username = %s
        """
        params: list[object] = [conversation_id, owner_username]
        if agent_name is not None:
            query += " AND agent_name = %s"
            params.append(agent_name)
        if exclude_roles:
            placeholders = ", ".join("%s" for _ in exclude_roles)
            query += f" AND role NOT IN ({placeholders})"
            params.extend(exclude_roles)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(max(1, min(limit, 500)))
        cursor = self.conn.execute(query, params)
        rows = list(cursor.fetchall())
        return list(reversed(rows))

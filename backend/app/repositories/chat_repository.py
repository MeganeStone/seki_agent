import sqlite3
import json
from datetime import datetime, timezone


class ChatRepository:
    """对话和消息表仓储。

    仓储层只负责 SQL 和行数据，不包含业务判断；用户归属过滤在 SQL 条件里完成，
    上层 service 再决定不存在时返回什么 HTTP 错误。
    """

    def __init__(self, conn: sqlite3.Connection):
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
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        if "active_agent" not in columns:
            self.conn.execute(
                "ALTER TABLE conversations ADD COLUMN active_agent TEXT NOT NULL DEFAULT 'main_agent'"
            )
        if "agent_summaries" not in columns:
            self.conn.execute(
                "ALTER TABLE conversations ADD COLUMN agent_summaries TEXT NOT NULL DEFAULT '{}'"
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
        message_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        if "agent_name" not in message_columns:
            self.conn.execute(
                "ALTER TABLE chat_messages ADD COLUMN agent_name TEXT NOT NULL DEFAULT 'main_agent'"
            )
        if "metadata" not in message_columns:
            self.conn.execute(
                "ALTER TABLE chat_messages ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'"
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

    def create_conversation(self, conversation_id: str, owner_username: str) -> sqlite3.Row:
        created_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO conversations (id, owner_username, active_agent, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, owner_username, "main_agent", created_at),
        )
        self.conn.commit()
        row = self.get_conversation(conversation_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create conversation")
        return row

    def list_conversations(self, owner_username: str, limit: int = 50) -> list[sqlite3.Row]:
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
            WHERE c.owner_username = ?
            GROUP BY c.id, c.owner_username, c.active_agent, c.created_at
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (owner_username, max(1, min(limit, 200))),
        )
        return list(cursor.fetchall())

    def get_conversation(self, conversation_id: str, owner_username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, active_agent, agent_summaries, created_at
            FROM conversations
            WHERE id = ? AND owner_username = ?
            """,
            (conversation_id, owner_username),
        )
        return cursor.fetchone()

    def delete_conversation(self, conversation_id: str, owner_username: str) -> bool:
        conversation = self.get_conversation(conversation_id, owner_username)
        if conversation is None:
            return False

        self.conn.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ? AND owner_username = ?",
            (conversation_id, owner_username),
        )
        if self._table_exists("code_pending_operations"):
            self.conn.execute(
                "DELETE FROM code_pending_operations WHERE conversation_id = ? AND owner_username = ?",
                (conversation_id, owner_username),
            )
        self.conn.execute(
            "DELETE FROM conversations WHERE id = ? AND owner_username = ?",
            (conversation_id, owner_username),
        )
        self.conn.commit()
        return True

    def _table_exists(self, table_name: str) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
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
            SET agent_summaries = ?
            WHERE id = ? AND owner_username = ?
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
            WHERE conversation_id = ? AND owner_username = ?
        """
        params: list[object] = [conversation_id, owner_username]
        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)
        cursor = self.conn.execute(query, params)
        row = cursor.fetchone()
        return int(row["total"] if row else 0)

    def update_active_agent(self, conversation_id: str, owner_username: str, active_agent: str) -> None:
        self.conn.execute(
            """
            UPDATE conversations
            SET active_agent = ?
            WHERE id = ? AND owner_username = ?
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    ) -> list[sqlite3.Row]:
        query = """
            SELECT id, conversation_id, owner_username, role, content, agent_name, metadata, created_at
            FROM chat_messages
            WHERE conversation_id = ? AND owner_username = ?
        """
        params: list[object] = [conversation_id, owner_username]
        if agent_name is not None:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if exclude_roles:
            placeholders = ", ".join("?" for _ in exclude_roles)
            query += f" AND role NOT IN ({placeholders})"
            params.extend(exclude_roles)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        cursor = self.conn.execute(query, params)
        rows = list(cursor.fetchall())
        return list(reversed(rows))

import sqlite3
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
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                owner_username TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_owner_username ON conversations(owner_username)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id)"
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

    def get_conversation(self, conversation_id: str, owner_username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            "SELECT id, owner_username, active_agent, created_at FROM conversations WHERE id = ? AND owner_username = ?",
            (conversation_id, owner_username),
        )
        return cursor.fetchone()

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

    def add_message(self, message_id: str, conversation_id: str, owner_username: str, role: str, content: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO chat_messages (id, conversation_id, owner_username, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, owner_username, role, content, created_at),
        )
        self.conn.commit()

    def list_messages(
        self,
        conversation_id: str,
        owner_username: str,
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT id, conversation_id, owner_username, role, content, created_at
            FROM chat_messages
            WHERE conversation_id = ? AND owner_username = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (conversation_id, owner_username, max(1, min(limit, 100))),
        )
        rows = list(cursor.fetchall())
        return list(reversed(rows))

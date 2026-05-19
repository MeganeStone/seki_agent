import sqlite3
from datetime import datetime, timezone


class ChatRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
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
            "INSERT INTO conversations (id, owner_username, created_at) VALUES (?, ?, ?)",
            (conversation_id, owner_username, created_at),
        )
        self.conn.commit()
        row = self.get_conversation(conversation_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create conversation")
        return row

    def get_conversation(self, conversation_id: str, owner_username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            "SELECT id, owner_username, created_at FROM conversations WHERE id = ? AND owner_username = ?",
            (conversation_id, owner_username),
        )
        return cursor.fetchone()

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


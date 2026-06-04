import sqlite3
from datetime import datetime, timezone


class FileRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                owner_username TEXT NOT NULL,
                filename TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_owner_username ON files(owner_username)"
        )
        self.conn.commit()

    def create(self, file_id: str, owner_username: str, filename: str, storage_path: str, size: int) -> sqlite3.Row:
        created_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO files (id, owner_username, filename, storage_path, size, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_id, owner_username, filename, storage_path, size, created_at),
        )
        self.conn.commit()
        row = self.get_for_owner(file_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create file record")
        return row

    def list_for_owner(self, owner_username: str) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, filename, storage_path, size, created_at
            FROM files
            WHERE owner_username = ?
            ORDER BY created_at DESC
            """,
            (owner_username,),
        )
        return list(cursor.fetchall())

    def get_for_owner(self, file_id: str, owner_username: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, filename, storage_path, size, created_at
            FROM files
            WHERE id = ? AND owner_username = ?
            """,
            (file_id, owner_username),
        )
        return cursor.fetchone()

    def get_by_storage_path(self, owner_username: str, storage_path: str) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, filename, storage_path, size, created_at
            FROM files
            WHERE owner_username = ? AND storage_path = ?
            """,
            (owner_username, storage_path),
        )
        return cursor.fetchone()

    def delete_by_storage_path(self, owner_username: str, storage_path: str) -> sqlite3.Row | None:
        row = self.get_by_storage_path(owner_username, storage_path)
        if row is None:
            return None
        self.conn.execute(
            "DELETE FROM files WHERE owner_username = ? AND storage_path = ?",
            (owner_username, storage_path),
        )
        self.conn.commit()
        return row

    def delete_for_owner(self, file_id: str, owner_username: str) -> sqlite3.Row | None:
        row = self.get_for_owner(file_id, owner_username)
        if row is None:
            return None
        self.conn.execute(
            "DELETE FROM files WHERE id = ? AND owner_username = ?",
            (file_id, owner_username),
        )
        self.conn.commit()
        return row


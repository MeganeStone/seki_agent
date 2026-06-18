import psycopg
from datetime import datetime, timezone


class FileRepository:
    def __init__(self, conn: psycopg.Connection):
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

    def create(self, file_id: str, owner_username: str, filename: str, storage_path: str, size: int) -> dict:
        created_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO files (id, owner_username, filename, storage_path, size, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (file_id, owner_username, filename, storage_path, size, created_at),
        )
        self.conn.commit()
        row = self.get_for_owner(file_id, owner_username)
        if row is None:
            raise RuntimeError("Failed to create file record")
        return row

    def list_for_owner(self, owner_username: str) -> list[dict]:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, filename, storage_path, size, created_at
            FROM files
            WHERE owner_username = %s
            ORDER BY created_at DESC
            """,
            (owner_username,),
        )
        return list(cursor.fetchall())

    def get_for_owner(self, file_id: str, owner_username: str) -> dict | None:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, filename, storage_path, size, created_at
            FROM files
            WHERE id = %s AND owner_username = %s
            """,
            (file_id, owner_username),
        )
        return cursor.fetchone()

    def get_by_storage_path(self, owner_username: str, storage_path: str) -> dict | None:
        cursor = self.conn.execute(
            """
            SELECT id, owner_username, filename, storage_path, size, created_at
            FROM files
            WHERE owner_username = %s AND storage_path = %s
            """,
            (owner_username, storage_path),
        )
        return cursor.fetchone()

    def delete_by_storage_path(self, owner_username: str, storage_path: str) -> dict | None:
        row = self.get_by_storage_path(owner_username, storage_path)
        if row is None:
            return None
        self.conn.execute(
            "DELETE FROM files WHERE owner_username = %s AND storage_path = %s",
            (owner_username, storage_path),
        )
        self.conn.commit()
        return row

    def delete_for_owner(self, file_id: str, owner_username: str) -> dict | None:
        row = self.get_for_owner(file_id, owner_username)
        if row is None:
            return None
        self.conn.execute(
            "DELETE FROM files WHERE id = %s AND owner_username = %s",
            (file_id, owner_username),
        )
        self.conn.commit()
        return row


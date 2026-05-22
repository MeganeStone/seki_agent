import sqlite3
from collections.abc import Iterator
from pathlib import Path

from app.core.config import get_settings


def get_db_path() -> Path:
    return get_settings().database_path


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """创建 SQLite 连接并启用 Row factory。

    check_same_thread=False 是为了线程池任务能用自己创建的连接；不要跨线程复用
    同一个连接，后台任务 service 已按这个原则重新 connect。
    """
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_connection() -> Iterator[sqlite3.Connection]:
    """FastAPI 请求级数据库连接依赖。"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()

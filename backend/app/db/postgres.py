from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


def get_dsn() -> str:
    return get_settings().database_url


def connect(dsn: str | None = None) -> psycopg.Connection:
    """创建 PostgreSQL 连接，行以 dict 返回。

    每个请求/后台任务使用自己的短连接，不跨线程复用同一个连接对象；
    线程池/Celery 任务会带着同一个 dsn 自行重连。
    """
    return psycopg.connect(dsn or get_dsn(), row_factory=dict_row)


def get_connection() -> Iterator[psycopg.Connection]:
    """FastAPI 请求级数据库连接依赖。"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()

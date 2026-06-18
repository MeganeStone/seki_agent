"""pytest 公共 fixture：PostgreSQL 测试库与按测试隔离的 schema。

每个测试拿到一个独立 schema 的 dsn（通过 search_path 隔离），测试结束后整个
schema 级联删除；后台线程/服务用同一个 dsn 重连也会落在同一个 schema 里。
"""
import os
import uuid

import psycopg
import pytest

DEFAULT_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/seki_agent_test"


def _base_url() -> str:
    return os.getenv("SEKI_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def _test_database() -> str:
    """确保测试数据库存在，返回其连接串。"""
    url = _base_url()
    base, _, dbname = url.rpartition("/")
    dbname = dbname.split("?")[0]
    with psycopg.connect(f"{base}/postgres", autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
    return url


@pytest.fixture
def pg_dsn(_test_database: str):
    schema = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_test_database, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    separator = "&" if "?" in _test_database else "?"
    dsn = f"{_test_database}{separator}options=-csearch_path%3D{schema}"
    try:
        yield dsn
    finally:
        with psycopg.connect(_test_database, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')

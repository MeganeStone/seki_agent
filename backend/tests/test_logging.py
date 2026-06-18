import json
import logging
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.context import current_user_var
from app.core.logging import JsonLogFormatter, configure_logging, shutdown_logging
from app.main import create_app


def _make_log_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="seki_test_logs_"))


def _cleanup_log_dir(log_dir: Path) -> None:
    """先关闭 handler 释放文件锁，再删除临时目录。"""
    shutdown_logging()
    shutil.rmtree(log_dir, ignore_errors=True)


def test_json_formatter_outputs_single_line_json_with_extras() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="seki.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.duration_ms = 12.5

    line = formatter.format(record)
    payload = json.loads(line)

    assert "\n" not in line
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "seki.test"
    assert payload["request_id"] == "req-123"
    assert payload["duration_ms"] == 12.5
    assert "timestamp" in payload


def test_configure_logging_is_idempotent() -> None:
    log_dir = _make_log_dir()
    try:
        configure_logging("INFO", "json", log_dir)
        configure_logging("INFO", "json", log_dir)

        root = logging.getLogger()
        seki_handlers = [h for h in root.handlers if getattr(h, "_seki_logging_handler", False)]
        assert len(seki_handlers) == 2  # app.log + error.log

        request_logger = logging.getLogger("seki.request")
        request_handlers = [h for h in request_logger.handlers if getattr(h, "_seki_logging_handler", False)]
        assert len(request_handlers) == 1
    finally:
        _cleanup_log_dir(log_dir)


def test_configure_logging_creates_isolated_log_files() -> None:
    log_dir = _make_log_dir()
    try:
        configure_logging("INFO", "json", log_dir)

        # 写入不同 logger 的日志
        logging.getLogger("seki.request").info("access log")
        logging.getLogger("seki.audit").info("audit log")
        logging.getLogger("seki.trace").info("trace log")
        logging.getLogger("app.business").info("app log")
        logging.getLogger("app.business").error("error log")

        # 刷新所有 handler
        for handler in logging.getLogger().handlers:
            handler.flush()
        for logger_name in ("seki.request", "seki.audit", "seki.trace"):
            for handler in logging.getLogger(logger_name).handlers:
                handler.flush()

        # 验证日志文件存在
        assert (log_dir / "access.log").exists()
        assert (log_dir / "audit.log").exists()
        assert (log_dir / "trace.log").exists()
        assert (log_dir / "app.log").exists()
        assert (log_dir / "error.log").exists()

        # 验证日志内容隔离
        access_content = (log_dir / "access.log").read_text(encoding="utf-8")
        assert "access log" in access_content
        assert "app log" not in access_content

        app_content = (log_dir / "app.log").read_text(encoding="utf-8")
        assert "app log" in app_content
        assert "access log" not in app_content
        assert "audit log" not in app_content

        error_content = (log_dir / "error.log").read_text(encoding="utf-8")
        assert "error log" in error_content
        assert "app log" not in error_content
    finally:
        _cleanup_log_dir(log_dir)


def test_request_middleware_logs_to_access_log_file() -> None:
    """验证 HTTP 请求日志写入 access.log 文件（seki.request 不传播到 root）。"""
    log_dir = _make_log_dir()
    try:
        # create_app 内部会调用 configure_logging，之后再覆盖为临时目录
        client = TestClient(create_app())
        configure_logging("INFO", "json", log_dir)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        request_id = response.headers.get("x-request-id")
        assert request_id

        # 刷新 access.log handler
        for handler in logging.getLogger("seki.request").handlers:
            handler.flush()

        access_content = (log_dir / "access.log").read_text(encoding="utf-8")
        assert request_id in access_content
        assert "/api/v1/health" in access_content
        assert "GET" in access_content
    finally:
        _cleanup_log_dir(log_dir)


def test_user_context_filter_injects_username_into_log_records() -> None:
    """验证 _UserContextFilter 自动将 ContextVar 中的用户名注入到日志记录。"""
    log_dir = _make_log_dir()
    try:
        configure_logging("INFO", "json", log_dir)

        # 设置用户上下文
        token = current_user_var.set("alice")
        try:
            logging.getLogger("app.business").info("user action")

            # 刷新 handler
            for handler in logging.getLogger().handlers:
                handler.flush()

            app_content = (log_dir / "app.log").read_text(encoding="utf-8")
            payload = json.loads(app_content.strip().split("\n")[-1])
            assert payload["user"] == "alice"
            assert payload["message"] == "user action"
        finally:
            current_user_var.reset(token)
    finally:
        _cleanup_log_dir(log_dir)


def test_request_middleware_extracts_verified_user_from_auth_header() -> None:
    """公开接口可从已验签 token 注入用户名，便于 access.log 区分用户。"""
    from app.core.security import create_access_token

    log_dir = _make_log_dir()
    try:
        client = TestClient(create_app())
        configure_logging("INFO", "json", log_dir)

        # 直接生成 token，不依赖数据库
        token = create_access_token("bob")

        response = client.get("/api/v1/health", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

        # 刷新 access.log handler
        for handler in logging.getLogger("seki.request").handlers:
            handler.flush()

        access_content = (log_dir / "access.log").read_text(encoding="utf-8")
        payload = json.loads(access_content.strip().split("\n")[-1])
        assert payload["user"] == "bob"
        assert payload["path"] == "/api/v1/health"
    finally:
        _cleanup_log_dir(log_dir)


def test_request_middleware_rejects_invalid_auth_header_user() -> None:
    """无效 token 不应污染访问日志里的用户名。"""
    log_dir = _make_log_dir()
    try:
        client = TestClient(create_app())
        configure_logging("INFO", "json", log_dir)

        response = client.get("/api/v1/health", headers={"Authorization": "Bearer invalid.token"})
        assert response.status_code == 200

        for handler in logging.getLogger("seki.request").handlers:
            handler.flush()

        access_content = (log_dir / "access.log").read_text(encoding="utf-8")
        payload = json.loads(access_content.strip().split("\n")[-1])
        assert payload["user"] == ""
        assert payload["path"] == "/api/v1/health"
    finally:
        _cleanup_log_dir(log_dir)


def test_authenticated_dependency_injects_verified_user_into_access_log() -> None:
    """验证鉴权依赖校验 token 后将真实用户名注入到 access.log。"""
    from app.core.security import create_access_token
    from app.schemas.auth import UserRead

    log_dir = _make_log_dir()
    try:
        app = create_app()

        def fake_current_user() -> UserRead:
            current_user_var.set("bob")
            return UserRead(username="bob", is_admin=False)

        from app.api.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = fake_current_user
        client = TestClient(app)
        configure_logging("INFO", "json", log_dir)

        token = create_access_token("bob")
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

        for handler in logging.getLogger("seki.request").handlers:
            handler.flush()

        access_content = (log_dir / "access.log").read_text(encoding="utf-8")
        payload = json.loads(access_content.strip().split("\n")[-1])
        assert payload["user"] == "bob"
        assert payload["path"] == "/api/v1/auth/me"
    finally:
        _cleanup_log_dir(log_dir)

import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonLogFormatter, configure_logging
from app.main import create_app


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
    root = logging.getLogger()
    configure_logging("INFO", "json")
    configure_logging("INFO", "json")

    seki_handlers = [h for h in root.handlers if getattr(h, "_seki_logging_handler", False)]
    assert len(seki_handlers) == 1


def test_request_middleware_logs_and_sets_request_id_header(caplog) -> None:
    client = TestClient(create_app())

    with caplog.at_level(logging.INFO, logger="seki.request"):
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    records = [r for r in caplog.records if r.name == "seki.request"]
    assert records
    record = records[-1]
    assert record.method == "GET"
    assert record.path == "/api/v1/health"
    assert record.status_code == 200
    assert record.request_id == response.headers["x-request-id"]
    assert record.duration_ms >= 0

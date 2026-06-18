"""结构化日志配置。

SEKI_LOG_FORMAT=json 时所有日志输出单行 JSON（含 logger extra 字段），便于
采集进 ELK/Loki 等系统；SEKI_LOG_FORMAT=console 保持人类可读格式，适合本地调试。
"""
import json
import logging
import sys
from datetime import datetime, timezone

# logging.LogRecord 自带属性集合；除此之外的属性都视为业务 extra 字段输出。
_STANDARD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """配置根 logger。幂等：重复调用会替换之前由本函数安装的 handler。"""
    root = logging.getLogger()
    root.setLevel(log_level.upper())

    for handler in list(root.handlers):
        if getattr(handler, "_seki_logging_handler", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler._seki_logging_handler = True
    if log_format.strip().lower() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root.addHandler(handler)

    # 请求访问日志由 RequestLoggingMiddleware 输出结构化记录，
    # 关掉 uvicorn 自带 access log 避免重复行。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

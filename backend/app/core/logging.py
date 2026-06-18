"""结构化日志配置，按业务隔离到不同文件。

日志文件布局（位于 ``SEKI_LOG_DIR``，默认 ``data/logs/``）::

    logs/
    ├── access.log      ← HTTP 请求日志（seki.request）
    ├── app.log         ← 业务主日志（agent、task、auth、admin 等）
    ├── audit.log       ← 安全审计日志（code agent 操作、用户管理）
    ├── trace.log       ← Agent 运行追踪日志（seki.trace）
    └── error.log       ← 所有 ERROR 级别日志的副本（快速定位问题）

SEKI_LOG_FORMAT=json 时所有日志输出单行 JSON（含 logger extra 字段），便于
采集进 ELK/Loki 等系统；SEKI_LOG_FORMAT=console 保持人类可读格式，适合本地调试。
日志按大小轮转（单文件 50 MB，保留 10 个备份），多进程安全。
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.context import current_user_var

# logging.LogRecord 自带属性集合；除此之外的属性都视为业务 extra 字段输出。
_STANDARD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}

# 专属日志文件对应的 logger 名称前缀；这些 logger 不传播到 root，
# 避免记录在 app.log 里重复出现。
_ISOLATED_LOGGERS = ("seki.request", "seki.audit", "seki.trace")

# 已安装 seki handler 的 logger 名称；幂等清理时使用。
_configured_logger_names: list[str] = []


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


class ConsoleLogFormatter(logging.Formatter):
    """人类可读格式，同时保留 logger extra 字段。"""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRS and key != "user" and not key.startswith("_")
        }
        if extras:
            fields = " ".join(f"{key}={value}" for key, value in sorted(extras.items()))
            line = f"{line} {fields}"
        return line


class _PrefixAcceptFilter(logging.Filter):
    """只允许名称以指定前缀开头的日志记录通过。"""

    def __init__(self, prefix: str):
        super().__init__()
        self._prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == self._prefix or record.name.startswith(f"{self._prefix}.")


class _PrefixRejectFilter(logging.Filter):
    """拒绝名称以指定前缀开头的日志记录。"""

    def __init__(self, prefix: str):
        super().__init__()
        self._prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name == self._prefix or record.name.startswith(f"{self._prefix}."))


class _ErrorLevelFilter(logging.Filter):
    """只允许 ERROR 及以上级别的日志记录通过。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.ERROR


class _UserContextFilter(logging.Filter):
    """自动将当前用户名注入到日志记录中。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "user"):
            record.user = current_user_var.get()
        return True


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_dir: Path | None = None,
) -> None:
    """配置日志系统：按业务隔离到不同文件，按大小轮转，多进程安全。

    幂等：重复调用会替换之前由本函数安装的所有 handler。
    """
    if log_dir is None:
        from app.core.config import get_settings
        log_dir = get_settings().log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    level = log_level.upper()
    fmt = log_format.strip().lower()

    # 清理之前由本函数安装的所有 handler（root + 专属 logger）。
    names_to_clean = list(dict.fromkeys([""] + _configured_logger_names))
    for name in names_to_clean:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if getattr(handler, "_seki_logging_handler", False):
                logger.removeHandler(handler)
    _configured_logger_names.clear()

    def make_handler(filename: str) -> logging.Handler:
        handler = logging.handlers.RotatingFileHandler(
            log_dir / filename,
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=10,
            encoding="utf-8",
        )
        handler._seki_logging_handler = True
        handler.addFilter(_UserContextFilter())
        if fmt == "json":
            handler.setFormatter(JsonLogFormatter())
        else:
            handler.setFormatter(ConsoleLogFormatter("%(asctime)s %(levelname)s %(name)s [%(user)s] %(message)s"))
        return handler

    # --- 专属 logger：各自写入独立日志文件，不传播到 root ---
    for logger_name, filename in (
        ("seki.request", "access.log"),
        ("seki.audit", "audit.log"),
        ("seki.trace", "trace.log"),
    ):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False
        h = make_handler(filename)
        logger.addHandler(h)
        _configured_logger_names.append(logger_name)

    # --- root logger：app.log（排除专属 logger）+ error.log（仅 ERROR+）---
    root = logging.getLogger()
    root.setLevel(level)

    app_handler = make_handler("app.log")
    for prefix in _ISOLATED_LOGGERS:
        app_handler.addFilter(_PrefixRejectFilter(prefix))
    root.addHandler(app_handler)

    error_handler = make_handler("error.log")
    error_handler.addFilter(_ErrorLevelFilter())
    root.addHandler(error_handler)

    # 请求访问日志由 RequestLoggingMiddleware 输出结构化记录，
    # 关掉 uvicorn 自带 access log 避免重复行。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def shutdown_logging() -> None:
    """关闭并移除所有由 configure_logging 安装的 handler。

    主要用于测试清理：Windows 下文件句柄未关闭时无法删除临时目录。
    """
    names_to_clean = list(dict.fromkeys([""] + _configured_logger_names))
    for name in names_to_clean:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if getattr(handler, "_seki_logging_handler", False):
                handler.flush()
                handler.close()
                logger.removeHandler(handler)
    _configured_logger_names.clear()


# 延迟导入避免循环依赖；logging.handlers 在顶层 import 时不一定可用。
import logging.handlers  # noqa: E402

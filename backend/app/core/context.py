"""请求级上下文变量，用于在中间件、依赖注入和日志之间传递信息。"""
from contextvars import ContextVar

# 当前请求的用户名；由 RequestLoggingMiddleware 或 get_current_user 设置，
# 由 _UserContextFilter 注入到每条日志记录中。
current_user_var: ContextVar[str] = ContextVar("current_user", default="")

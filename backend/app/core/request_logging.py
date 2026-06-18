"""HTTP 请求结构化访问日志中间件（纯 ASGI，避免干扰 SSE 流式响应）。"""
import logging
import time
from uuid import uuid4

from app.core.context import current_user_var
from app.core.security import decode_access_token

logger = logging.getLogger("seki.request")


def _extract_verified_user_from_auth_header(headers: list[tuple[bytes, bytes]]) -> str:
    """从 Bearer token 中提取已验签且未过期的用户名，仅用于访问日志。"""
    for key, value in headers:
        if key.lower() != b"authorization":
            continue
        raw = value.decode("ascii", errors="replace")
        if not raw.startswith("Bearer "):
            return ""
        payload = decode_access_token(raw[7:])
        if payload is None:
            return ""
        return str(payload.get("sub") or "")
    return ""


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex[:16]
        start = time.perf_counter()
        status_holder = {"status": 0}

        username = _extract_verified_user_from_auth_header(scope.get("headers", []))
        token = current_user_var.set(username)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                hdrs = message.setdefault("headers", [])
                hdrs.append((b"x-request-id", request_id.encode("ascii")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            client = scope.get("client") or ("", 0)
            logger.info(
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status_code": status_holder["status"],
                    "duration_ms": duration_ms,
                    "client_ip": client[0],
                },
            )
            current_user_var.reset(token)

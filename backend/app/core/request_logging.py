"""HTTP 请求结构化访问日志中间件（纯 ASGI，避免干扰 SSE 流式响应）。"""
import logging
import time
from uuid import uuid4

logger = logging.getLogger("seki.request")


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

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("ascii")))
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

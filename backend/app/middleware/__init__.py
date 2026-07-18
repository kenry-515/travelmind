"""
TravelMind Agent — ASGI Middleware
Request ID tracking, timing, and logging middleware.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid the
streaming-response buffering bug in Starlette:
  https://github.com/encode/starlette/issues/919
"""

import time
import uuid
import logging

from starlette.types import ASGIApp, Receive, Scope, Send, Message

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Inject X-Request-ID header into every response and log request timing.

    Written as pure ASGI middleware so StreamingResponse (SSE) works correctly.
    BaseHTTPMiddleware buffers and re-streams response bodies, which breaks
    server-sent events.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            path = scope.get("path", "?")
            method = scope.get("method", "?")
            logger.info(
                "%s %s — %d (%.3fs) [%s]",
                method, path, status_code, elapsed, request_id,
            )


__all__ = ["RequestIDMiddleware"]

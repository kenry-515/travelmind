"""
TravelMind Agent — 令牌桶请求限流中间件（Phase 12.28c）

基于 IP 的令牌桶算法，60 req/min 默认。作为纯 ASGI middleware 实现
以避免 StreamingResponse 被 BaseHTTPMiddleware 缓冲的问题。

用法（main.py）：
    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, rate=60, per_seconds=60)
"""

import time
import logging
from collections import defaultdict
from typing import Dict, Optional, Tuple

from starlette.types import ASGIApp, Receive, Scope, Send, Message

logger = logging.getLogger(__name__)


class TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate          # tokens per second
        self.capacity = capacity  # max burst
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        now = time.monotonic()
        # Refill
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware:
    """ASGI middleware for token-bucket rate limiting by client IP."""

    def __init__(
        self,
        app: ASGIApp,
        rate: int = 60,
        per_seconds: int = 60,
        exempt_paths: Tuple[str, ...] = ("/api/v1/health", "/health"),
    ):
        """
        Args:
            app: The ASGI application.
            rate: Max requests per `per_seconds` window.
            per_seconds: Time window in seconds.
            exempt_paths: Paths not subject to rate limiting.
        """
        self.app = app
        self.rate = rate / per_seconds  # tokens per second
        self.capacity = rate            # burst = full window
        self.exempt_paths = set(exempt_paths)
        self._buckets: Dict[str, TokenBucket] = {}
        self._last_cleanup = time.monotonic()

    # Phase 12.29: 可信代理列表（生产环境配置，为空时不信任 X-Forwarded-For）
    TRUSTED_PROXIES: Tuple[str, ...] = tuple()

    def _get_client_ip(self, scope: Scope) -> str:
        """Extract client IP from scope.

        Phase 12.29: 只有在配置了可信代理时，才信任 X-Forwarded-For 头。
        默认（空列表）下直接取 client IP，避免 IP 伪造。

        验证算法（RFC 7239 推荐）：
        从右向左遍历 X-Forwarded-For 链，逐一验证每个代理 IP 是否在
        TRUSTED_PROXIES 中。遇到第一个不在信任列表中的 IP 即为真实客户端 IP。
        """
        # Only trust X-Forwarded-For when proxies are explicitly configured
        forwarded = self._get_forwarded_for(scope)
        if forwarded and self.TRUSTED_PROXIES:
            # Phase 12.29: 从右向左遍历代理链
            forwarded_ips = [ip.strip() for ip in forwarded.split(",")]
            # 从最右开始向左遍历，跳过所有可信代理
            # 最后一个代理（最右）必须是可信代理（它是上游加的头）
            # 然后继续向左找第一个不可信 IP → 那就是真实客户端
            for i in range(len(forwarded_ips) - 1, -1, -1):
                ip = forwarded_ips[i].strip()
                if ip not in self.TRUSTED_PROXIES:
                    return ip
            # 全部可信 → 返回最左的 IP（可能是内部监控自己调自己）
            return forwarded_ips[0].strip()
        # Fallback to direct client
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"

    def _get_forwarded_for(self, scope: Scope) -> Optional[str]:
        """Extract X-Forwarded-For header value, if present."""
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for")
        if forwarded:
            return forwarded.decode()
        return None

    def _cleanup_expired(self) -> None:
        """Periodically remove stale buckets to prevent memory leak."""
        now = time.monotonic()
        if now - self._last_cleanup < 300:  # Every 5 min
            return
        self._last_cleanup = now
        stale = [
            ip for ip, bucket in self._buckets.items()
            if bucket.tokens >= self.capacity * 0.99  # Full bucket = idle
        ]
        for ip in stale:
            del self._buckets[ip]
        if stale:
            logger.debug(f"RateLimit: cleaned {len(stale)} idle buckets")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        ip = self._get_client_ip(scope)
        if ip not in self._buckets:
            self._buckets[ip] = TokenBucket(self.rate, self.capacity)

        if self._buckets[ip].consume():
            self._cleanup_expired()
            await self.app(scope, receive, send)
            return

        # Rate limited
        logger.warning(f"RateLimit: {ip} exceeded limit on {path}")
        retry_after = int(60 / self.capacity) + 1  # seconds until next token
        headers = [
            (b"content-type", b"application/json"),
            (b"retry-after", str(retry_after).encode()),
        ]
        body = (
            b'{"error":{"code":"RATE_LIMITED","message":'
            b'"Request rate exceeded. Try again later.",'
            b'"details":{"retry_after_seconds":' + str(retry_after).encode() + b'}}}'
        )
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


__all__ = ["RateLimitMiddleware"]

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
import re
from collections import defaultdict
from typing import Dict, Optional, Tuple

from starlette.types import ASGIApp, Receive, Scope, Send, Message

logger = logging.getLogger(__name__)

# Phase 18 M5.3: 日志脱敏 — 截断用户输入避免日志爆炸 + 移除敏感字段
_SENSITIVE_PATTERNS = [
    (re.compile(r'(api[_-]?key|token|password|secret)["\']?\s*[:=]\s*["\']?[\w\-]+', re.I),
     r'\1=<redacted>'),
    (re.compile(r'sk-[a-zA-Z0-9]{8,}\b'), 'sk-<redacted>'),
]


def _sanitize_log_value(value: str, max_len: int = 200) -> str:
    """Sanitize user-controlled text for safe logging.

    - Truncate to max_len to prevent log spam
    - Strip API keys, tokens, passwords
    """
    if not isinstance(value, str):
        return str(value)[:max_len]
    out = value
    for pattern, replacement in _SENSITIVE_PATTERNS:
        out = pattern.sub(replacement, out)
    if len(out) > max_len:
        out = out[:max_len] + f"...<truncated {len(value)-max_len} chars>"
    return out


__all__ = ["RateLimitMiddleware", "_sanitize_log_value"]


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
        per_endpoint: Optional[Dict[str, Tuple[int, int]]] = None,
    ):
        """
        Args:
            app: The ASGI application.
            rate: Max requests per `per_seconds` window (default).
            per_seconds: Time window in seconds.
            exempt_paths: Paths not subject to rate limiting.
            per_endpoint: {path_prefix: (rate, per_seconds)} for special endpoints.
                          Example: {"/api/v1/resources/calendar": (10, 60)} for stricter limit.
        """
        self.app = app
        self.default_rate = rate / per_seconds
        self.default_capacity = rate
        self.exempt_paths = set(exempt_paths)
        # Per-endpoint limits (path_prefix -> (tokens_per_sec, capacity))
        self.per_endpoint: Dict[str, Tuple[float, float]] = {}
        if per_endpoint:
            for prefix, (r, ps) in per_endpoint.items():
                self.per_endpoint[prefix] = (r / ps, r)
        # Use (ip, endpoint_key) tuple as bucket key
        self._buckets: Dict[Tuple[str, str], TokenBucket] = {}
        self._last_cleanup = time.monotonic()

    def _make_bucket(self, rate_per_sec: float, capacity: float) -> TokenBucket:
        return TokenBucket(rate_per_sec, capacity)

    def _get_endpoint_key(self, path: str) -> Tuple[float, float]:
        """Match path prefix to per-endpoint limit. Returns (rate, capacity)."""
        for prefix, (rate, cap) in self.per_endpoint.items():
            if path.startswith(prefix):
                return rate, cap
        return self.default_rate, self.default_capacity

    async def _check_rate_async(
        self, bucket_key: Tuple[str, str], rate_per_sec: float, capacity: float,
    ) -> Tuple[bool, int]:
        """Async 限流检测 (Phase 18 P4: Redis Lua 跨 worker 一致)。

        策略:
        1. 先检查内存 bucket (廉价)
        2. 如果内存允许, 再尝试 Redis (生产跨 worker 一致)
        3. Redis 失败仍用内存结果 (fail-safe)
        """
        # Step 1: in-memory check (always available)
        if bucket_key not in self._buckets:
            self._buckets[bucket_key] = TokenBucket(rate_per_sec, capacity)
        memory_allowed = self._buckets[bucket_key].consume()

        # If memory denied, return immediately (no Redis query needed)
        if not memory_allowed:
            bucket = self._buckets[bucket_key]
            needed = 1 - bucket.tokens
            retry_after = int(needed / rate_per_sec) + 1 if rate_per_sec > 0 else 60
            return False, retry_after

        # Step 2: memory allowed, also check Redis (production path)
        redis_key = f"ratelimit:{bucket_key[0]}:{bucket_key[1]}"
        try:
            from app.middleware.redis_rate_limit import get_redis_rate_limiter
            limiter = get_redis_rate_limiter()
            redis_allowed, redis_retry = await limiter.consume(redis_key, rate_per_sec, capacity)
            if limiter._redis is not None:
                # Redis is live, use Redis decision
                return redis_allowed, redis_retry
        except Exception as e:
            logger.debug(f"Redis rate limiter unavailable, using memory: {e}")

        # Redis not connected → return memory result
        return memory_allowed, 0

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
        default_cap = self.default_capacity
        stale = [
            k for k, bucket in self._buckets.items()
            if bucket.tokens >= bucket.capacity * 0.99  # Full bucket = idle
        ]
        for k in stale:
            del self._buckets[k]
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
        rate_per_sec, capacity = self._get_endpoint_key(path)
        # Phase 5 P0.4: Use safe endpoint key (avoid IndexError on short paths like /favicon.ico)
        parts = [p for p in path.split("/") if p]
        endpoint_id = parts[2] if len(parts) >= 3 else (parts[0] if parts else "root")
        bucket_key = (ip, endpoint_id)  # by IP+endpoint

        # Phase 18 P4: Redis 限流 (跨 worker 一致), 失败降级到内存
        allowed, retry_after = await self._check_rate_async(bucket_key, rate_per_sec, capacity)
        if allowed:
            self._cleanup_expired()
            await self.app(scope, receive, send)
            return

        # Phase 18 M5.3: 限流响应也用统一错误结构(含 suggestion + retryable)
        from app.api.errors import ErrorPresets
        if retry_after == 0:
            retry_after = int(60 / capacity) + 1
        preset = ErrorPresets.get("rate_limited", retry_after=retry_after)
        import json
        body_dict = {
            "error": {
                "code": "RATE_LIMITED",
                "message": preset["message"],
                "suggestion": preset["suggestion"],
                "retryable": preset["retryable"],
                "details": {"retry_after_seconds": retry_after},
            }
        }
        body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"retry-after", str(retry_after).encode()),
        ]
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

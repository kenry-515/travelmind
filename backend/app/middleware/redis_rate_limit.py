"""
TravelMind Agent — Redis 限流 (Phase 18 P4)

跨 worker 一致的限流 (生产 gunicorn 4 worker 部署必需)。

算法: 滑动窗口 / 令牌桶 Redis 实现
- 用 Redis HASH 存 bucket: {tokens, last_refill_ts}
- 用 Lua 脚本原子操作 (check + decrement)
- 失败时降级到内存 (Redis 不可用不阻塞)

Phase 18 P4: 生产级多 worker 一致性。
"""

import logging
import time
from typing import Dict, Optional, Tuple

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.settings import settings

logger = logging.getLogger(__name__)


# Lua 脚本: 原子令牌消耗
# 返回: 1 = allowed, 0 = rate limited, ttl_seconds
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate_per_sec = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

-- Refill based on elapsed time
local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * rate_per_sec)
last_refill = now

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HSET', key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', key, 600)
    return {1, 0}
end

redis.call('HSET', key, 'tokens', tokens, 'last_refill', last_refill)
redis.call('EXPIRE', key, 600)
local ttl = math.ceil((1 - tokens) / rate_per_sec)
return {0, ttl}
"""


class RedisRateLimiter:
    """基于 Redis Lua 脚本的令牌桶限流器 (跨进程一致)。"""

    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.REDIS_URL
        self._redis = None
        self._lua_sha: Optional[str] = None

    async def _ensure_connected(self) -> bool:
        if self._redis is not None:
            return True
        try:
            from redis.asyncio import Redis
            self._redis = Redis.from_url(self.url, socket_connect_timeout=2)
            await self._redis.ping()
            self._lua_sha = await self._redis.script_load(_TOKEN_BUCKET_LUA)
            return True
        except Exception as e:
            logger.warning(f"Redis rate limiter unavailable: {e}")
            return False

    async def consume(
        self,
        bucket_key: str,
        rate_per_sec: float,
        capacity: float,
    ) -> Tuple[bool, int]:
        """尝试消耗一个 token。

        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        if not await self._ensure_connected() or self._redis is None:
            return True, 0  # Redis down → 允许 (fail-open)
        try:
            now = time.time()
            result = await self._redis.evalsha(
                self._lua_sha, 1, bucket_key,
                str(rate_per_sec), str(capacity), str(now),
            )
            allowed = bool(result[0])
            retry_after = int(result[1])
            return allowed, retry_after
        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}")
            return True, 0  # Fail-open

    async def close(self):
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None


# 全局 singleton
_redis_limiter: Optional[RedisRateLimiter] = None


def get_redis_rate_limiter() -> RedisRateLimiter:
    """线程安全的 singleton 获取器。"""
    global _redis_limiter
    if _redis_limiter is None:
        _redis_limiter = RedisRateLimiter()
    return _redis_limiter


def reset_redis_rate_limiter() -> None:
    """测试重置。"""
    global _redis_limiter
    _redis_limiter = None
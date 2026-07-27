"""
TravelMind Agent — Cache Service

Generic Redis cache layer following the same pattern as session_store.py:
  - RedisSessionStore connection via redis.asyncio.Redis.from_url()
  - Module-level singleton factory get_cache()
  - Graceful degradation to NoOpCache when Redis is unavailable

Usage:
    from app.services.cache_service import get_cache
    cache = get_cache()
    cached = await cache.get("key")
    if cached:
        return json.loads(cached)
    result = await expensive_call()
    await cache.set("key", json.dumps(result), ttl=600)
"""

import json
import logging
from typing import Any, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── Abstract interface ──────────────────────────────────────


class BaseCache:
    """Async cache interface. Implementations: RedisCache, NoOpCache."""

    async def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    async def set(self, key: str, value: str, ttl: int) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def invalidate(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""
        raise NotImplementedError

    async def close(self) -> None:
        """Close the underlying connection (no-op for stateless implementations)."""
        pass


# ── Redis implementation ─────────────────────────────────────


class RedisCache(BaseCache):
    """Redis-backed cache with key prefix and TTL support."""

    PREFIX = "travelmind:cache:"

    def __init__(self, url: Optional[str] = None, client: Any = None) -> None:
        if client is not None:
            self._redis = client
        else:
            from redis.asyncio import Redis
            self._redis = Redis.from_url(url or settings.REDIS_URL)

    def _key(self, k: str) -> str:
        return f"{self.PREFIX}{k}"

    async def get(self, key: str) -> Optional[str]:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.set(self._key(key), value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))

    async def invalidate(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern (pipelined for efficiency)."""
        full_pattern = f"{self.PREFIX}{pattern}"
        keys = [k async for k in self._redis.scan_iter(match=full_pattern)]
        if keys:
            await self._redis.delete(*keys)
        return len(keys)

    async def close(self) -> None:
        """Close the Redis connection pool."""
        await self._redis.aclose()


# ── No-op fallback ───────────────────────────────────────────


class NoOpCache(BaseCache):
    """No-op cache — all operations silently succeed with empty results.
    Used when Redis is unavailable so the application continues to work.
    """

    async def get(self, key: str) -> Optional[str]:
        return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def invalidate(self, pattern: str) -> int:
        return 0


# ── Factory singleton ────────────────────────────────────────

_cache: Optional[BaseCache] = None


def get_cache() -> BaseCache:
    """Return the singleton cache instance.

    Tries Redis first; falls back to NoOpCache if:
    - SESSION_STORE is not 'redis' (no Redis configured)
    - Redis connection fails
    """
    global _cache
    if _cache is not None:
        return _cache

    backend = (settings.SESSION_STORE or "memory").lower()
    if backend == "redis":
        try:
            _cache = RedisCache()
            logger.info("Cache: Redis (%s)", settings.REDIS_URL)
            return _cache
        except Exception as e:
            logger.warning(
                "Redis cache init failed (%s), falling back to no-op cache", e
            )
    else:
        logger.debug("Cache: no-op (SESSION_STORE=%s)", backend)

    _cache = NoOpCache()
    return _cache


def reset_cache() -> None:
    """Reset the singleton (for testing)."""
    global _cache
    _cache = None

"""
TravelMind Agent — Redis 监控聚合 (Phase 18 P4)

跨 worker 聚合 metrics:
- Redis HASH per (method, path) 存 total + count + max
- /metrics 端点合并本地 + Redis 数据

如果 Redis 不可用,降级到纯本地 metrics。
"""

import logging
import time
from typing import Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class RedisMetricsBackend:
    """Redis 持久化 metrics backend (跨 worker 聚合)。"""

    KEY_PREFIX = "travelmind:metrics:"

    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.REDIS_URL
        self._redis = None

    async def connect(self) -> bool:
        try:
            from redis.asyncio import Redis
            self._redis = Redis.from_url(self.url, socket_connect_timeout=2)
            await self._redis.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis metrics backend unavailable: {e}")
            self._redis = None
            return False

    def _key(self, method: str, path: str, status: int) -> str:
        return f"{self.KEY_PREFIX}{method}:{path}:{status}"

    def _path_key(self, method: str, path: str) -> str:
        return f"{self.KEY_PREFIX}path:{method}:{path}"

    async def increment(self, method: str, path: str, status: int, duration: float) -> None:
        """Atomic INCR + HSET updates."""
        if self._redis is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.hincrby(self._key(method, path, status), "count", 1)
            pipe.hincrbyfloat(self._path_key(method, path), "total_duration", duration)
            pipe.hincrby(self._path_key(method, path), "count", 1)
            # Track max duration (GET + COMPARE + SET)
            pipe.hget(self._path_key(method, path), "max_duration")
            results = await pipe.execute()
            current_max_raw = results[3]
            try:
                current_max = float(current_max_raw) if current_max_raw else 0.0
            except (TypeError, ValueError):
                current_max = 0.0
            if duration > current_max:
                await self._redis.hset(
                    self._path_key(method, path), "max_duration", str(duration)
                )
            # TTL 1 hour (metrics 滚动)
            await self._redis.expire(self._key(method, path), 3600)
            await self._redis.expire(self._path_key(method, path), 3600)
        except Exception as e:
            logger.debug(f"Redis metrics update failed: {e}")

    async def aggregate(self) -> Dict[str, Dict]:
        """读所有 metrics key 并合并."""
        if self._redis is None:
            await self.connect()
        if self._redis is None:
            return {}

        try:
            result = {
                "requests": {},
                "durations": {},
                "status_counts": {},
            }
            async for key in self._redis.scan_iter(match=f"{self.KEY_PREFIX}*"):
                data = await self._redis.hgetall(key)
                if not data:
                    continue
                # Parse key: "travelmind:metrics:METHOD:PATH:STATUS" or "path:METHOD:PATH"
                tail = key.decode().split(":", 2)[2]  # Skip "travelmind:metrics:"
                if tail.startswith("path:"):
                    parts = tail.split(":", 2)
                    _, method, path = parts
                    if path not in result["durations"]:
                        result["durations"][(method, path)] = {"total": 0.0, "count": 0, "max": 0.0}
                    result["durations"][(method, path)]["total"] = float(data.get(b"total_duration", 0))
                    result["durations"][(method, path)]["count"] = int(data.get(b"count", 0))
                    result["durations"][(method, path)]["max"] = float(data.get(b"max_duration", 0))
                else:
                    parts = tail.split(":", 2)
                    method, path, status = parts[0], parts[1], int(parts[2])
                    count = int(data.get(b"count", 0))
                    result["requests"][(method, path, status)] = count
                    result["status_counts"][status] = result["status_counts"].get(status, 0) + count
            return result
        except Exception as e:
            logger.warning(f"Redis metrics aggregate failed: {e}")
            return {}

    async def close(self) -> None:
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None


_backend: Optional[RedisMetricsBackend] = None


async def get_redis_metrics_backend() -> Optional[RedisMetricsBackend]:
    """Lazy connect to Redis metrics backend (None if unavailable)."""
    global _backend
    if _backend is not None:
        return _backend if _backend._redis else None
    backend = RedisMetricsBackend()
    if await backend.connect():
        _backend = backend
        return backend
    return None
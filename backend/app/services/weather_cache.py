"""
TravelMind Agent — 天气缓存层（Phase 12.28c）

内存 TTL 30min 天气缓存：同一城市同一天数的 Open-Meteo 预报命中缓存
直接返回，避免重复网络请求。后端重启后缓存自动清空（非持久化）。

用法：
    from app.services.weather_cache import WeatherCache
    cache = WeatherCache(ttl_seconds=1800)

    # 缓存键 = (city, days)
    key = ("重庆", 7)
    cached = cache.get(key)
    if cached:
        return cached

    forecast = await fetch_from_open_meteo(...)
    cache.set(key, forecast)
    return forecast
"""

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 缓存键类型： (city_name, forecast_days)
CacheKey = Tuple[str, int]


class WeatherCache:
    """Thread-safe TTL cache for weather forecasts."""

    def __init__(self, ttl_seconds: int = 1800):
        """
        Args:
            ttl_seconds: Time-to-live in seconds (default 30 min).
        """
        self._ttl = ttl_seconds
        self._store: Dict[CacheKey, Any] = {}
        self._timestamps: Dict[CacheKey, float] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: CacheKey) -> Optional[Any]:
        """Get cached forecast. Returns None if expired or not found."""
        with self._lock:
            entry = self._store.get(key)
            ts = self._timestamps.get(key, 0)
            if entry is not None and (time.monotonic() - ts) < self._ttl:
                self._hits += 1
                logger.debug(f"WeatherCache HIT: {key}")
                return entry
            # Expired or not found
            self._misses += 1
            if entry is not None:
                # Remove expired entry
                del self._store[key]
                del self._timestamps[key]
                logger.debug(f"WeatherCache EXPIRED: {key}")
            return None

    def set(self, key: CacheKey, value: Any) -> None:
        """Store forecast in cache."""
        with self._lock:
            self._store[key] = value
            self._timestamps[key] = time.monotonic()
            logger.debug(f"WeatherCache SET: {key}")

    def invalidate(self, key: Optional[CacheKey] = None) -> None:
        """Invalidate cached entries.

        Args:
            key: Specific key to invalidate. If None, invalidates all.
        """
        with self._lock:
            if key is None:
                self._store.clear()
                self._timestamps.clear()
                logger.info("WeatherCache: 全部清空")
            elif key in self._store:
                del self._store[key]
                del self._timestamps[key]
                logger.info(f"WeatherCache: 清除 {key}")

    @property
    def hit_rate(self) -> float:
        """Cache hit rate since creation."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> Dict[str, Any]:
        """Cache statistics for monitoring."""
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self.hit_rate, 3),
                "ttl_seconds": self._ttl,
            }


# Singleton
_weather_cache: Optional[WeatherCache] = None
_weather_cache_lock = threading.Lock()


def get_weather_cache() -> WeatherCache:
    """Get or create the singleton weather cache."""
    global _weather_cache
    if _weather_cache is None:
        with _weather_cache_lock:
            if _weather_cache is None:
                _weather_cache = WeatherCache()
    return _weather_cache

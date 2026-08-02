"""
TravelMind Agent — In-process cache utilities (Phase 18 P3 生产级)

提供:
  - @ttl_lru_cache(ttl=300, maxsize=128) — 带 TTL 的 LRU 缓存装饰器
  - @memoize_with_ttl(ttl=60) — async 函数记忆化 (with TTL)
  - invalidate_all() — 清除所有缓存 (测试 / 重启用)

适用场景:
  - 频繁调用的同步函数 (例如 _load_attractions, _get_kb_cities)
  - async 函数 (用 memoize_with_ttl)
  - 不需要跨进程共享的纯本地缓存 (走 Redis 仍是 cache_service.py)

线程安全: 每个 cache entry 自己的锁; LRU 用 OrderedDict + lock.
"""

import asyncio
import functools
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Tuple


# ── 进程内 TTL+LRU ─────────────────────────────────────────

class _TTLCache:
    """LRU + TTL 进程内缓存 (thread-safe)."""

    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Tuple[bool, Any]:
        with self._lock:
            if key not in self._cache:
                return False, None
            expire_at, value = self._cache[key]
            if expire_at < time.monotonic():
                del self._cache[key]
                return False, None
            # Move to end (LRU)
            self._cache.move_to_end(key)
            return True, value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            expire_at = time.monotonic() + ttl
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (expire_at, value)
            # Evict LRU if over capacity
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


def ttl_lru_cache(ttl: int = 300, maxsize: int = 128):
    """同步函数装饰器: TTL + LRU 缓存.

    Args:
        ttl: 过期时间 (秒)
        maxsize: 最大 entry 数

    Example:
        @ttl_lru_cache(ttl=600, maxsize=1)
        def load_attractions():
            return json.load(open("attractions.json"))
    """
    cache = _TTLCache(maxsize=maxsize)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            hit, value = cache.get(key)
            if hit:
                return value
            value = func(*args, **kwargs)
            cache.set(key, value, ttl)
            return value

        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _make_key(args, kwargs) -> str:
    """稳定 hashable key from args/kwargs."""
    return repr((args, sorted(kwargs.items())))


# ── async 函数记忆化 ────────────────────────────────────────

def memoize_with_ttl(ttl: int = 60):
    """async 函数装饰器: TTL 缓存.

    Example:
        @memoize_with_ttl(ttl=60)
        async def fetch_user_profile(user_id):
            return await db.get_user(user_id)
    """
    cache = _TTLCache(maxsize=128)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            hit, value = cache.get(key)
            if hit:
                return value
            value = await func(*args, **kwargs)
            cache.set(key, value, ttl)
            return value

        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ── 全局 invalidation (test / startup hook) ────────────────

def invalidate_all_caches() -> int:
    """Clear all ttl_lru_cache / memoize_with_ttl entries.

    Returns number of caches cleared (not entries).

    Note: This only works if caches are registered. For now, just
    provide a hook so future global-cache registry can hook in.
    """
    # Find all _TTLCache instances in gc and clear them
    import gc
    cleared = 0
    for obj in gc.get_objects():
        if isinstance(obj, _TTLCache):
            obj.clear()
            cleared += 1
    return cleared


__all__ = [
    "ttl_lru_cache",
    "memoize_with_ttl",
    "invalidate_all_caches",
]
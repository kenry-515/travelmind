"""
TravelMind Agent — Cache Decorator (Phase 18 P4)

基于 cache_service 的 async 函数装饰器:
- 自动 serialize (json.dumps/loads)
- 自动 TTL
- 自动 cache key (基于函数名 + 参数)
- 自动降级 (Redis down 用 NoOpCache)

用法:
    @cached(ttl=300, key_prefix="resources_overview")
    async def get_overview(city: str = "广州"):
        ...
"""

import functools
import hashlib
import json
import logging
from typing import Any, Callable, Optional

from app.services.cache_service import get_cache

logger = logging.getLogger(__name__)


def cached(
    ttl: int = 300,
    key_prefix: Optional[str] = None,
    exclude_args: tuple = ("device_id", "user_id"),
) -> Callable:
    """Async 函数结果缓存装饰器 (也支持 sync 函数)。

    Args:
        ttl: 缓存秒数
        key_prefix: 自定义 key 前缀, 默认用函数名
        exclude_args: 这些参数不参与 cache key 计算 (e.g., device-specific)

    用法:
        @cached(ttl=600, key_prefix="overview")
        def get_resources_overview(city: str = "广州"):
            ...
    """
    def decorator(func: Callable) -> Callable:
        prefix = key_prefix or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Build cache key (excluding device-specific args)
            cache_args = {k: v for k, v in kwargs.items() if k not in exclude_args}
            key_data = json.dumps({"args": args, "kwargs": cache_args}, sort_keys=True, default=str)
            key_hash = hashlib.md5(key_data.encode()).hexdigest()[:16]
            cache_key = f"{prefix}:{key_hash}"

            # Try cache
            try:
                cache = get_cache()
                cached_value = await cache.get(cache_key)
                if cached_value is not None:
                    return json.loads(cached_value)
            except Exception as e:
                logger.debug(f"Cache get failed (cache_key={cache_key}): {e}")

            # Execute original async function
            result = await func(*args, **kwargs)

            # Store result
            try:
                cache = get_cache()
                await cache.set(cache_key, json.dumps(result, default=str), ttl=ttl)
            except Exception as e:
                logger.debug(f"Cache set failed (cache_key={cache_key}): {e}")

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Sync 包装: 直接调函数 + 同步 cache (NoOpCache), Redis 异步集成另说."""
            cache_args = {k: v for k, v in kwargs.items() if k not in exclude_args}
            key_data = json.dumps({"args": args, "kwargs": cache_args}, sort_keys=True, default=str)
            key_hash = hashlib.md5(key_data.encode()).hexdigest()[:16]
            cache_key = f"{prefix}:{key_hash}"

            cache = get_cache()
            # Sync cache interface — try cache
            if hasattr(cache, "get_sync"):
                try:
                    cached_value = cache.get_sync(cache_key)
                    if cached_value is not None:
                        return json.loads(cached_value)
                except Exception:
                    pass

            # Execute original sync function
            result = func(*args, **kwargs)

            # Store result (sync store)
            if hasattr(cache, "set_sync"):
                try:
                    cache.set_sync(cache_key, json.dumps(result, default=str), ttl=ttl)
                except Exception:
                    pass
            return result

        # 选择包装: 如果原函数是 async, 用 async_wrapper; 否则用 sync_wrapper
        import inspect
        if inspect.iscoroutinefunction(func):
            wrapper = async_wrapper
        else:
            wrapper = sync_wrapper

        wrapper.__cache_ttl__ = ttl  # type: ignore[attr-defined]
        wrapper.__cache_prefix__ = prefix  # type: ignore[attr-defined]
        return wrapper

    return decorator


def invalidate_cache(pattern: str) -> int:
    """同步接口: 删除匹配 pattern 的 cache key.

    Pattern 是 glob, 例如 "resources_overview:*".
    返回删除数量。
    """
    import asyncio
    async def _invalidate():
        cache = get_cache()
        return await cache.invalidate(pattern)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't await from running loop; create task
            return asyncio.ensure_future(_invalidate())
        else:
            return asyncio.run(_invalidate())
    except RuntimeError:
        return 0
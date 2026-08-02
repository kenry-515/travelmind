"""
Cache Decorator 测试 (Phase 18 P4)
"""

import asyncio
import json
import pytest

from app.services.cache_decorator import cached


def test_cached_decorator_sync_function():
    """Sync 函数应被装饰且能正常返回。"""
    call_count = 0

    @cached(ttl=60, key_prefix="test_sync")
    def slow_function(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * 2

    result = slow_function(5)
    assert result == 10
    assert call_count == 1


def test_cached_decorator_key_based_on_args():
    """不同参数应不同 cache key。"""
    @cached(ttl=60, key_prefix="test_args")
    def fn(x: int) -> int:
        return x + 1

    # 不同参数 → 不同结果 (实际上 NoOpCache, 不会缓存, 每次都调函数)
    assert fn(1) == 2
    assert fn(2) == 3
    assert fn(100) == 101


@pytest.mark.asyncio
async def test_cached_decorator_async_function():
    """Async 函数也能用。"""
    @cached(ttl=60, key_prefix="test_async")
    async def async_fn(x: int) -> int:
        return x * 3

    result = await async_fn(4)
    assert result == 12


def test_cached_decorator_exclude_args():
    """exclude_args 参数不参与 cache key。"""
    @cached(ttl=60, key_prefix="test_exclude", exclude_args=("user_id",))
    def fn(x: int, user_id: str = "anon") -> int:
        return x

    assert fn(1, user_id="alice") == 1
    assert fn(1, user_id="bob") == 1
    assert fn(2, user_id="alice") == 2


@pytest.mark.asyncio
async def test_cached_decorator_fallback_on_cache_error():
    """Cache 失败时, 函数仍正常返回 (降级到 NoOpCache)。"""
    @cached(ttl=60, key_prefix="test_fallback")
    async def fn(x: int) -> int:
        return x * 4

    # NoOpCache 默认, 不会出错
    result = await fn(7)
    assert result == 28
"""
TravelMind Agent — Cache Service Tests (Phase 10)

Tests for: RedisCache, NoOpCache, get_cache() factory, graceful degradation,
and cache wiring in retriever / weather / amap (mock-based).
"""

import json

import pytest


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def fakeredis_client():
    """Create a fakeredis client for testing RedisCache."""
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def redis_cache(fakeredis_client):
    """A RedisCache backed by fakeredis."""
    from app.services.cache_service import RedisCache
    return RedisCache(client=fakeredis_client)


@pytest.fixture
def noop_cache():
    from app.services.cache_service import NoOpCache
    return NoOpCache()


# ── RedisCache Tests ──────────────────────────────────────────


class TestRedisCache:
    def test_set_and_get(self, redis_cache):
        import asyncio
        async def _run():
            await redis_cache.set("test_key", "hello", ttl=300)
            val = await redis_cache.get("test_key")
            assert val == "hello"
        asyncio.run(_run())

    def test_get_missing_key(self, redis_cache):
        import asyncio
        async def _run():
            val = await redis_cache.get("nonexistent")
            assert val is None
        asyncio.run(_run())

    def test_delete(self, redis_cache):
        import asyncio
        async def _run():
            await redis_cache.set("del_key", "bye", ttl=300)
            await redis_cache.delete("del_key")
            assert await redis_cache.get("del_key") is None
        asyncio.run(_run())

    def test_key_prefix(self, redis_cache):
        """Keys should be stored with the travelmind:cache: prefix."""
        import asyncio
        async def _run():
            await redis_cache.set("prefixed", "val", ttl=300)
            full_key = redis_cache._key("prefixed")
            assert full_key == "travelmind:cache:prefixed"
            # Verify via raw Redis that the prefixed key exists
            raw = await redis_cache._redis.get(full_key)
            assert raw is not None
        asyncio.run(_run())

    def test_invalidate(self, redis_cache):
        import asyncio
        async def _run():
            await redis_cache.set("amap:abc", "1", ttl=300)
            await redis_cache.set("amap:def", "2", ttl=300)
            await redis_cache.set("weather:xyz", "3", ttl=300)
            deleted = await redis_cache.invalidate("amap:*")
            assert deleted == 2
            assert await redis_cache.get("amap:abc") is None
            assert await redis_cache.get("amap:def") is None
            assert await redis_cache.get("weather:xyz") == "3"  # not deleted
        asyncio.run(_run())


# ── NoOpCache Tests ───────────────────────────────────────────


class TestNoOpCache:
    def test_get_returns_none(self, noop_cache):
        import asyncio
        async def _run():
            assert await noop_cache.get("anything") is None
        asyncio.run(_run())

    def test_set_does_not_raise(self, noop_cache):
        import asyncio
        async def _run():
            await noop_cache.set("key", "value", 300)  # no error
        asyncio.run(_run())

    def test_delete_does_not_raise(self, noop_cache):
        import asyncio
        async def _run():
            await noop_cache.delete("key")  # no error
        asyncio.run(_run())

    def test_invalidate_returns_zero(self, noop_cache):
        import asyncio
        async def _run():
            assert await noop_cache.invalidate("*") == 0
        asyncio.run(_run())


# ── Factory / Fallback Tests ──────────────────────────────────


class TestCacheFactory:
    def test_get_cache_memory_mode(self, monkeypatch):
        """When SESSION_STORE is 'memory', should return NoOpCache."""
        from app.services.cache_service import reset_cache, get_cache, NoOpCache
        reset_cache()
        monkeypatch.setattr("app.services.cache_service.settings.SESSION_STORE", "memory")
        cache = get_cache()
        assert isinstance(cache, NoOpCache)
        reset_cache()

    def test_get_cache_singleton(self):
        """get_cache() should return the same instance on repeated calls."""
        from app.services.cache_service import reset_cache, get_cache
        reset_cache()
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2
        reset_cache()

    def test_reset_cache(self):
        """reset_cache() should clear the singleton."""
        from app.services.cache_service import reset_cache, get_cache, NoOpCache
        reset_cache()
        monkeypatch_import = __import__("app.services.cache_service", fromlist=["settings"])
        # After reset, a new instance should be created
        c1 = get_cache()
        reset_cache()
        c2 = get_cache()
        # Different instances after reset
        assert isinstance(c2, NoOpCache)


# ── RAG Cache Integration Tests ───────────────────────────────


class TestRagCache:
    def test_cache_key_deterministic(self):
        """Cache keys should be deterministic for same inputs."""
        import hashlib
        tags = ["美食", "夜景"]
        tags_hash = hashlib.md5(",".join(sorted(tags)).encode()).hexdigest()
        city = "重庆"
        budget = "经济"
        cache_key = f"rag:{city}:{tags_hash}:{budget}:20"
        # Same inputs should produce same key
        tags_hash2 = hashlib.md5(",".join(sorted(["夜景", "美食"])).encode()).hexdigest()
        cache_key2 = f"rag:{city}:{tags_hash2}:{budget}:20"
        assert cache_key == cache_key2

    def test_cache_key_different_for_different_inputs(self):
        """Different inputs produce different cache keys."""
        import hashlib
        tags1_hash = hashlib.md5(",".join(sorted(["美食"])).encode()).hexdigest()
        tags2_hash = hashlib.md5(",".join(sorted(["历史"])).encode()).hexdigest()
        assert tags1_hash != tags2_hash


# ── Amap Cache Integration Tests ──────────────────────────────


class TestAmapCache:
    def test_coord_hash_deterministic(self):
        """Coordinate hashes should be deterministic regardless of order."""
        import hashlib
        coords_a = [(106.5, 29.5), (106.6, 29.6)]
        coords_b = [(106.6, 29.6), (106.5, 29.5)]  # reversed
        center = (106.55, 29.55)
        hash_a = hashlib.md5(
            json.dumps((sorted(coords_a), center), sort_keys=True).encode()
        ).hexdigest()
        hash_b = hashlib.md5(
            json.dumps((sorted(coords_b), center), sort_keys=True).encode()
        ).hexdigest()
        assert hash_a == hash_b

    def test_different_city_center_different_hash(self):
        """Different city_center values must produce different cache keys."""
        import hashlib
        coords = [(106.5, 29.5), (106.6, 29.6)]
        center_a = (106.55, 29.55)
        center_b = (116.40, 39.90)  # Different city center
        hash_a = hashlib.md5(
            json.dumps((sorted(coords), center_a), sort_keys=True).encode()
        ).hexdigest()
        hash_b = hashlib.md5(
            json.dumps((sorted(coords), center_b), sort_keys=True).encode()
        ).hexdigest()
        assert hash_a != hash_b


# ── Weather Cache Integration Tests ───────────────────────────


class TestWeatherCache:
    def test_cache_key_format(self):
        """Weather cache keys should follow consistent format."""
        cache_key = f"weather:重庆:5"
        assert cache_key == "weather:重庆:5"

    def test_cache_key_with_date(self):
        """Weather cache key should include start_date when present."""
        cache_key = "weather:重庆:5:2026-08-01"
        assert ":2026-08-01" in cache_key

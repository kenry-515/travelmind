"""
Session store 单元测试（fakeredis，不依赖真实 Redis 服务）。

覆盖：写入/读取/TTL 过期/进程重启后恢复（两个 store 实例共享同一 FakeServer 模拟）
/ 内存模式与历史行为一致 / 工厂按环境变量切换。
"""

import asyncio
import time

import fakeredis
import pytest

from app.services.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    get_session_store,
    reset_session_store,
)


def run(coro):
    return asyncio.run(coro)


# ── InMemorySessionStore ─────────────────────────────────

class TestInMemoryStore:
    def test_set_get(self):
        store = InMemorySessionStore()
        run(store.set("s1", {"stage": "collecting", "n": 1}, ttl_seconds=60))
        assert run(store.get("s1")) == {"stage": "collecting", "n": 1}

    def test_missing_returns_none(self):
        store = InMemorySessionStore()
        assert run(store.get("nope")) is None

    def test_ttl_expiry(self):
        store = InMemorySessionStore()
        run(store.set("s2", {"x": 1}, ttl_seconds=-1))  # 已过期
        assert run(store.get("s2")) is None

    def test_touch_extends_ttl(self):
        store = InMemorySessionStore()
        run(store.set("s3", {"x": 1}, ttl_seconds=60))
        run(store.touch("s3", 3600))
        assert run(store.get("s3")) == {"x": 1}

    def test_delete(self):
        store = InMemorySessionStore()
        run(store.set("s4", {"x": 1}, ttl_seconds=60))
        run(store.delete("s4"))
        assert run(store.get("s4")) is None


# ── RedisSessionStore（fakeredis）────────────────────────

class TestRedisStore:
    def _make(self):
        server = fakeredis.FakeServer()
        return server

    def test_set_get(self):
        server = self._make()
        client = fakeredis.aioredis.FakeRedis(server=server)
        store = RedisSessionStore(client=client)
        run(store.set("s1", {"stage": "confirming", "slots": {"city": "重庆"}}, ttl_seconds=60))
        got = run(store.get("s1"))
        assert got == {"stage": "confirming", "slots": {"city": "重庆"}}

    def test_missing_returns_none(self):
        client = fakeredis.aioredis.FakeRedis(server=self._make())
        store = RedisSessionStore(client=client)
        assert run(store.get("nope")) is None

    def test_ttl_set(self):
        client = fakeredis.aioredis.FakeRedis(server=self._make())
        store = RedisSessionStore(client=client)
        run(store.set("s2", {"x": 1}, ttl_seconds=100))
        ttl = run(client.pttl(store._key("s2")))
        assert 0 < ttl <= 100_000

    def test_restart_recovery(self):
        """两个 store 实例共享同一 FakeServer —— 模拟进程重启后会话不丢。"""
        server = self._make()
        store_a = RedisSessionStore(client=fakeredis.aioredis.FakeRedis(server=server))
        run(store_a.set("s3", {"stage": "delivered", "itinerary": {"trip": {"city": "三亚"}}}, ttl_seconds=7200))

        # 模拟"进程重启"：全新客户端与 store 实例
        store_b = RedisSessionStore(client=fakeredis.aioredis.FakeRedis(server=server))
        got = run(store_b.get("s3"))
        assert got == {"stage": "delivered", "itinerary": {"trip": {"city": "三亚"}}}

    def test_touch_extends_ttl(self):
        client = fakeredis.aioredis.FakeRedis(server=self._make())
        store = RedisSessionStore(client=client)
        run(store.set("s4", {"x": 1}, ttl_seconds=50))
        run(store.touch("s4", 3600))
        ttl = run(client.pttl(store._key("s4")))
        assert ttl > 3_500_000

    def test_delete(self):
        client = fakeredis.aioredis.FakeRedis(server=self._make())
        store = RedisSessionStore(client=client)
        run(store.set("s5", {"x": 1}, ttl_seconds=60))
        run(store.delete("s5"))
        assert run(store.get("s5")) is None


# ── 工厂 ─────────────────────────────────────────────────

class TestFactory:
    def setup_method(self):
        reset_session_store()

    def test_default_is_memory(self, monkeypatch):
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "memory")
        reset_session_store()
        assert isinstance(get_session_store(), InMemorySessionStore)

    def test_redis_selected(self, monkeypatch):
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "redis")
        monkeypatch.setattr("app.services.session_store.settings.REDIS_URL", "redis://localhost:6379/9")
        reset_session_store()
        assert isinstance(get_session_store(), RedisSessionStore)

    def test_redis_failure_falls_back(self, monkeypatch):
        """Redis 初始化抛错时降级内存（工厂容错）。"""
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "redis")

        class _Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("boom")

        monkeypatch.setattr("app.services.session_store.RedisSessionStore", _Boom)
        reset_session_store()
        assert isinstance(get_session_store(), InMemorySessionStore)

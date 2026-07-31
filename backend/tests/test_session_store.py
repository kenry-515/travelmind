"""
Session store 单元测试（fakeredis + tmp_path SQLite，不依赖真实 Redis 服务）。

覆盖：写入/读取/TTL 过期/进程重启后恢复 / 内存/SQLite/Redis 三后端
/ 工厂按环境变量切换 / 生产环境 Redis 失败 fast-fail / 开发环境降级。
"""

import asyncio
import time

import fakeredis
import pytest

from app.services.session_store import (
    InMemorySessionStore,
    SQLiteSessionStore,
    RedisSessionStore,
    get_session_store,
    reset_session_store,
    SESSION_STORE_DEGRADED,
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


# ── SQLiteSessionStore ───────────────────────────────────

class TestSQLiteStore:
    """SQLite 后端测试——用 tmp_path 隔离，不碰真实文件系统。"""

    def test_set_get(self, tmp_path):
        store = SQLiteSessionStore(str(tmp_path / "test.db"))
        run(store.set("s1", {"stage": "collecting", "n": 1}, ttl_seconds=60))
        assert run(store.get("s1")) == {"stage": "collecting", "n": 1}

    def test_missing_returns_none(self, tmp_path):
        store = SQLiteSessionStore(str(tmp_path / "test.db"))
        assert run(store.get("nope")) is None

    def test_ttl_expiry(self):
        # 用临时文件，TTL 设为 -1（已过期）
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            store = SQLiteSessionStore(path)
            run(store.set("s2", {"x": 1}, ttl_seconds=-1))
            assert run(store.get("s2")) is None
        finally:
            os.unlink(path)
            # 清理 WAL 文件
            for suffix in ("-wal", "-shm"):
                wal = path + suffix
                if os.path.exists(wal):
                    os.unlink(wal)

    def test_touch_extends_ttl(self, tmp_path):
        store = SQLiteSessionStore(str(tmp_path / "test.db"))
        run(store.set("s3", {"x": 1}, ttl_seconds=60))
        run(store.touch("s3", 3600))
        assert run(store.get("s3")) == {"x": 1}

    def test_delete(self, tmp_path):
        store = SQLiteSessionStore(str(tmp_path / "test.db"))
        run(store.set("s4", {"x": 1}, ttl_seconds=60))
        run(store.delete("s4"))
        assert run(store.get("s4")) is None

    def test_restart_recovery(self, tmp_path):
        """两个 store 实例指向同一文件——模拟进程重启后会话不丢。"""
        db_path = str(tmp_path / "restart.db")
        store_a = SQLiteSessionStore(db_path)
        run(store_a.set("s5", {"stage": "delivered", "itinerary": {"trip": {"city": "三亚"}}}, ttl_seconds=7200))

        # 模拟"进程重启"：全新 store 实例指向同一文件
        store_b = SQLiteSessionStore(db_path)
        got = run(store_b.get("s5"))
        assert got == {"stage": "delivered", "itinerary": {"trip": {"city": "三亚"}}}

    def test_creates_directory(self, tmp_path):
        """目录不存在时自动创建。"""
        nested = str(tmp_path / "nested" / "deep" / "sessions.db")
        store = SQLiteSessionStore(nested)
        run(store.set("s6", {"x": 1}, ttl_seconds=60))
        assert run(store.get("s6")) == {"x": 1}


# ── 工厂 ─────────────────────────────────────────────────

class TestFactory:
    def setup_method(self):
        reset_session_store()

    def test_default_is_sqlite(self, monkeypatch, tmp_path):
        """Phase 16.5: 默认后端从 memory 改为 sqlite。"""
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "sqlite")
        monkeypatch.setattr("app.services.session_store.settings.SESSION_SQLITE_PATH", str(tmp_path / "factory.db"))
        reset_session_store()
        assert isinstance(get_session_store(), SQLiteSessionStore)

    def test_memory_selected(self, monkeypatch):
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "memory")
        reset_session_store()
        assert isinstance(get_session_store(), InMemorySessionStore)

    def test_redis_selected(self, monkeypatch):
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "redis")
        monkeypatch.setattr("app.services.session_store.settings.REDIS_URL", "redis://localhost:6379/9")
        reset_session_store()
        assert isinstance(get_session_store(), RedisSessionStore)

    def test_redis_failure_falls_back_in_dev(self, monkeypatch):
        """Phase 16.5: 开发环境 Redis 失败降级到 SQLite（不是 InMemory）。"""
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "redis")
        monkeypatch.setattr("app.services.session_store.settings.APP_ENV", "development")
        monkeypatch.setattr("app.services.session_store.settings.SESSION_SQLITE_PATH", ":memory:")

        class _Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("boom")

        monkeypatch.setattr("app.services.session_store.RedisSessionStore", _Boom)
        reset_session_store()
        store = get_session_store()
        assert isinstance(store, SQLiteSessionStore)
        # 降级标志应被设置
        from app.services.session_store import SESSION_STORE_DEGRADED
        assert SESSION_STORE_DEGRADED is True

    def test_redis_failure_raises_in_production(self, monkeypatch):
        """Phase 16.5: 生产环境 Redis 失败必须 fast-fail（raise）。"""
        monkeypatch.setattr("app.services.session_store.settings.SESSION_STORE", "redis")
        monkeypatch.setattr("app.services.session_store.settings.APP_ENV", "production")

        class _Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("boom")

        monkeypatch.setattr("app.services.session_store.RedisSessionStore", _Boom)
        reset_session_store()
        with pytest.raises(RuntimeError, match="boom"):
            get_session_store()

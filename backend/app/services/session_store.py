"""
TravelMind Agent — Session Store（对话会话存储抽象）

意图层对话会话（dialog_manager 的槽位/阶段/行程）的存储抽象：
- `InMemorySessionStore`：进程内字典，仅用于测试/临时——单 worker 有效，重启丢会话
- `SQLiteSessionStore`：SQLite 文件持久化（stdlib，零额外依赖），dev 默认后端，
  支持 WAL 多 worker 读 + 重启恢复
- `RedisSessionStore`：Redis 外置（async redis-py），生产后端，
  TTL 2h 与现状一致，支持多 worker 与进程重启后会话恢复

切换方式：环境变量 `SESSION_STORE=memory|sqlite|redis`（默认 sqlite）；
Redis 连接走 `REDIS_URL`（默认 redis://localhost:6379/0）。
SQLite 路径走 `SESSION_SQLITE_PATH`（默认 ./.sessions/sessions.db）。
生产部署多 worker 时请将 SESSION_STORE 设为 redis。
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Phase 16.5: 降级标志——生产环境 Redis 失败时不应静默降级
# 此标志由工厂函数设置，health 端点透出
SESSION_STORE_DEGRADED: bool = False


class BaseSessionStore(ABC):
    """对话会话存储接口（值即 dialog_manager 的 state dict），全异步。"""

    @abstractmethod
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """读取会话；不存在或已过期返回 None。"""

    @abstractmethod
    async def set(self, session_id: str, state: Dict[str, Any], ttl_seconds: int) -> None:
        """写入会话并设置 TTL。"""

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """删除会话。"""

    @abstractmethod
    async def touch(self, session_id: str, ttl_seconds: int) -> None:
        """仅刷新 TTL（不改变内容）。"""


# ── 内存实现（默认/降级）────────────────────────────────

class InMemorySessionStore(BaseSessionStore):
    """进程内字典 + 惰性过期清理（与历史 _sessions 行为一致）。"""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._expires: Dict[str, float] = {}

    def _gc(self) -> None:
        now = time.time()
        for sid in [s for s, exp in self._expires.items() if exp <= now]:
            self._data.pop(sid, None)
            self._expires.pop(sid, None)

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        self._gc()
        return self._data.get(session_id)

    async def set(self, session_id: str, state: Dict[str, Any], ttl_seconds: int) -> None:
        self._data[session_id] = state
        self._expires[session_id] = time.time() + ttl_seconds

    async def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)
        self._expires.pop(session_id, None)

    async def touch(self, session_id: str, ttl_seconds: int) -> None:
        if session_id in self._data:
            self._expires[session_id] = time.time() + ttl_seconds


# ── SQLite 实现（dev 默认，零额外依赖，WAL 多 worker 读）──


class SQLiteSessionStore(BaseSessionStore):
    """SQLite 文件持久化（stdlib sqlite3 + asyncio.to_thread）。

    - 每次 IO 新建连接（低频操作，微秒级开销，零并发坑）
    - WAL 模式 + busy_timeout 确保多 worker 读不阻塞、写串行等待
    - 进程重启后会话不丢（文件持久化）
    - 仅用于 dev 环境；生产请用 Redis
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or settings.SESSION_SQLITE_PATH
        # 确保目录存在
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        # 初始化表结构（幂等）
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """每次操作新建连接，设置 WAL + busy_timeout。"""
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
            conn.commit()
        finally:
            conn.close()

    def _set_sync(self, session_id: str, state_json: str, expires_at: float) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, data, expires_at) VALUES (?, ?, ?)",
                (session_id, state_json, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _get_sync(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT data FROM sessions WHERE id = ? AND expires_at > ?",
                (session_id, time.time()),
            ).fetchone()
            if not row:
                return None
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        finally:
            conn.close()

    def _delete_sync(self, session_id: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def _touch_sync(self, session_id: str, expires_at: float) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE id = ?",
                (expires_at, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_sync, session_id)

    async def set(self, session_id: str, state: Dict[str, Any], ttl_seconds: int) -> None:
        await asyncio.to_thread(
            self._set_sync,
            session_id,
            json.dumps(state, ensure_ascii=False),
            time.time() + ttl_seconds,
        )

    async def delete(self, session_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, session_id)

    async def touch(self, session_id: str, ttl_seconds: int) -> None:
        await asyncio.to_thread(self._touch_sync, session_id, time.time() + ttl_seconds)


# ── Redis 实现（多 worker / 重启恢复）────────────────────

class RedisSessionStore(BaseSessionStore):
    """Redis 外置存储（JSON 序列化 + EXPIRE）。"""

    PREFIX = "travelmind:dialog:"

    def __init__(self, url: Optional[str] = None, client: Any = None) -> None:
        if client is not None:
            self._redis = client
        else:
            # 延迟导入：未安装 redis 包时内存模式仍可运行
            from redis.asyncio import Redis
            self._redis = Redis.from_url(url or settings.REDIS_URL)

    def _key(self, session_id: str) -> str:
        return f"{self.PREFIX}{session_id}"

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        raw = await self._redis.get(self._key(session_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    async def set(self, session_id: str, state: Dict[str, Any], ttl_seconds: int) -> None:
        await self._redis.set(
            self._key(session_id),
            json.dumps(state, ensure_ascii=False),
            ex=ttl_seconds,
        )

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def touch(self, session_id: str, ttl_seconds: int) -> None:
        await self._redis.expire(self._key(session_id), ttl_seconds)


# ── 工厂（线程安全单例） ──────────────────────────────────

_store: Optional[BaseSessionStore] = None
_store_lock: threading.Lock = threading.Lock()


def _is_production_env() -> bool:
    """判断是否为生产/staging 环境——决定 Redis 失败时 fast-fail 还是降级。"""
    return settings.APP_ENV.lower() in ("production", "staging", "prod")


def get_session_store() -> BaseSessionStore:
    """按 SESSION_STORE 环境变量返回单例存储实现（线程安全）。

    Phase 16.5: 生产环境 Redis 失败时 fast-fail（raise），
    开发环境降级到 SQLite 并设置 SESSION_STORE_DEGRADED 标志。
    """
    global _store, SESSION_STORE_DEGRADED
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        backend = (settings.SESSION_STORE or "sqlite").lower()

        if backend == "redis":
            try:
                _store = RedisSessionStore()
                logger.info(f"Session store: Redis ({settings.REDIS_URL})")
            except Exception as e:
                if _is_production_env():
                    # 生产环境：Redis 是硬依赖，失败必须崩溃重启
                    logger.error(f"Redis session store 初始化失败（生产环境，不降级）: {e}")
                    raise
                # 开发环境：降级到 SQLite（比 InMemory 更安全——至少持久化）
                logger.error(f"Redis session store 初始化失败（{e}），降级为 SQLite")
                SESSION_STORE_DEGRADED = True
                _store = SQLiteSessionStore()

        elif backend == "sqlite":
            try:
                _store = SQLiteSessionStore()
                logger.info(f"Session store: SQLite ({settings.SESSION_SQLITE_PATH})")
            except Exception as e:
                logger.error(f"SQLite session store 初始化失败（{e}），降级为内存模式")
                SESSION_STORE_DEGRADED = True
                _store = InMemorySessionStore()

        else:  # memory
            _store = InMemorySessionStore()
            logger.info("Session store: in-memory (single worker)")
    return _store


def reset_session_store() -> None:
    """测试用：重置工厂单例和降级标志。"""
    global _store, SESSION_STORE_DEGRADED
    with _store_lock:
        _store = None
        SESSION_STORE_DEGRADED = False

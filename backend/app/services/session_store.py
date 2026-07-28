"""
TravelMind Agent — Session Store（对话会话存储抽象）

意图层对话会话（dialog_manager 的槽位/阶段/行程）的存储抽象：
- `InMemorySessionStore`：进程内字典，默认实现（离线开发零依赖），
  行为与历史实现一致——单 worker 有效，重启丢会话
- `RedisSessionStore`：Redis 外置（async redis-py），TTL 2h 与现状一致，
  支持多 worker 与进程重启后会话恢复

切换方式：环境变量 `SESSION_STORE=memory|redis`（默认 memory）；
Redis 连接走 `REDIS_URL`（默认 redis://localhost:6379/0）。
生产部署多 worker 时请将 SESSION_STORE 设为 redis。
"""

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


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


def get_session_store() -> BaseSessionStore:
    """按 SESSION_STORE 环境变量返回单例存储实现（线程安全）。"""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        backend = (settings.SESSION_STORE or "memory").lower()
        if backend == "redis":
            try:
                _store = RedisSessionStore()
                logger.info(f"Session store: Redis ({settings.REDIS_URL})")
            except Exception as e:
                logger.warning(
                    f"Redis session store 初始化失败（{e}），降级为内存模式"
                )
                _store = InMemorySessionStore()
        else:
            _store = InMemorySessionStore()
            logger.info("Session store: in-memory (single worker)")
    return _store


def reset_session_store() -> None:
    """测试用：重置工厂单例。"""
    global _store
    with _store_lock:
        _store = None

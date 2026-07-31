"""pytest 公共夹具：让 tests/ 能直接 import app.*（从 backend/ 根运行）。

Phase 12.30: 启用真实 PostgreSQL 测试模式。
- 模块级设置 DB_HEALTHY=True + 初始化 RAG（在任何测试文件 import 之前）
- 会话级 fixture 建表和清理数据
- asyncio_default_fixture_loop_scope = session 共享事件循环
"""

import logging
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ============================================================
# Phase 12.30: 模块级初始化 —— 在 test 文件 import 之前执行
# ============================================================
# 1. 设置 DB_HEALTHY=True（create_app() 在 test 文件导入时执行）
from app.database import connection as _db_conn
_db_conn.DB_HEALTHY = True

# 2. 初始化 RAG（ASGITransport 不触发 FastAPI lifespan，需手动初始化）
try:
    from app.rag import init_rag_from_data
    _data_dir = Path(__file__).resolve().parent.parent / "data"
    _attractions_file = _data_dir / "attractions.json"
    if _attractions_file.exists():
        logging.getLogger("pytest.init").info(f"Attempting RAG init from: {_attractions_file}")
        _rag_ok = init_rag_from_data(_attractions_file)
        logging.getLogger("pytest.init").info(
            f"Module-level RAG init: {'OK' if _rag_ok else 'FAILED'}"
        )
    else:
        logging.getLogger("pytest.init").warning(
            f"attractions.json not found at {_attractions_file}, RAG not initialized"
        )
except Exception as _e:
    import traceback
    logging.getLogger("pytest.init").warning(
        f"RAG init failed: {_e}\n{traceback.format_exc()}"
    )


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """阻断真实网络；loopback 和 PostgreSQL 走真实连接。

    Phase 12.30: 真实 DB 测试模式 — 放行所有本地连接（127.0.0.1, ::1, localhost），
    以及 Docker 网络桥接的 PostgreSQL 连接。
    """
    real_connect = socket.socket.connect

    def _guarded(self, address, *args, **kwargs):
        try:
            host = address[0] if isinstance(address, tuple) else address
        except (IndexError, TypeError):
            return real_connect(self, address, *args, **kwargs)
        if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return real_connect(self, address, *args, **kwargs)
        # Also allow private/docker network ranges for PG
        if host.startswith("10.") or host.startswith("172.") or host.startswith("192.168."):
            return real_connect(self, address, *args, **kwargs)
        raise RuntimeError(f"unit tests must not call the network: {address}")

    monkeypatch.setattr(socket.socket, "connect", _guarded)


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Initialize test database: create tables, clean up after.

    Phase 12.30: Real DB testing mode.
    - Creates all tables via SQLAlchemy Base metadata
    - DB_HEALTHY + RAG already initialized at module level
    - Manages its own event loop (session scope, independent of pytest-asyncio)
    - If PG unreachable, sets DB_HEALTHY=False and skips all tests
    - Cleans up test users and their data after session
    """
    import asyncio
    from app.database.connection import engine
    from app.database import connection as db_conn
    from app.database.models import Base

    logger = logging.getLogger("pytest.db")
    loop = asyncio.new_event_loop()

    # 1. Create all tables (verify PG is actually reachable)
    try:
        loop.run_until_complete(_create_tables(engine, Base))
        logger.info("Test DB: all tables created successfully (real PostgreSQL).")
    except Exception as e:
        logger.error(f"Test DB init failed: {e}")
        db_conn.DB_HEALTHY = False
        loop.close()
        pytest.skip(f"PostgreSQL not available: {e}")
        return

    yield

    # 2. Cleanup: remove test users and cascading data
    try:
        loop.run_until_complete(_cleanup_test_data(engine))
        logger.info("Test DB: test data cleaned up.")
    except Exception as e:
        logger.warning(f"Test DB cleanup failed (non-fatal): {e}")
    finally:
        loop.close()


async def _create_tables(engine, Base):
    """Create all tables using the given engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _cleanup_test_data(engine):
    """Clean up test data from all tables."""
    import sqlalchemy
    async with engine.begin() as conn:
        await conn.execute(
            sqlalchemy.text(
                "DELETE FROM favorites WHERE user_id IN "
                "(SELECT id FROM users WHERE device_id LIKE 'test-%')"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "DELETE FROM itineraries WHERE user_id IN "
                "(SELECT id FROM users WHERE device_id LIKE 'test-%')"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "DELETE FROM recommendation_history WHERE user_id IN "
                "(SELECT id FROM users WHERE device_id LIKE 'test-%')"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "DELETE FROM user_profiles WHERE user_id IN "
                "(SELECT id FROM users WHERE device_id LIKE 'test-%')"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "DELETE FROM feedback WHERE user_id IN "
                "(SELECT id FROM users WHERE device_id LIKE 'test-%')"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "DELETE FROM users WHERE device_id LIKE 'test-%'"
            )
        )

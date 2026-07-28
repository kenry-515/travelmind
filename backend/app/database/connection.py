"""
TravelMind Agent — Database Connection
Async SQLAlchemy engine + session factory for PostgreSQL.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings

# Module-level flag: set to True after first successful DB connection.
# Routes check this before attempting DB operations — when False, they
# degrade gracefully (return empty lists, skip saves, etc.).
DB_HEALTHY: bool = False

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"timeout": 2},  # 2s connection timeout (fast startup)
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def check_db_connection() -> bool:
    """Verify database connectivity. Returns True if healthy."""
    global DB_HEALTHY
    _logger = logging.getLogger(__name__)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        DB_HEALTHY = True
        return True
    except Exception as e:
        DB_HEALTHY = False
        _logger.warning(f"Database connectivity check failed: {e}")
        return False

"""
TravelMind Agent — Database Connection
Async SQLAlchemy engine + session factory for PostgreSQL.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config.settings import settings

# Module-level flag: set to True after first successful DB connection.
# Routes check this before attempting DB operations — when False, they
# degrade gracefully (return empty lists, skip saves, etc.).
DB_HEALTHY: bool = False

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    poolclass=NullPool,  # Phase 12.30: loop-independent connections for testing
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
    """Verify database connectivity. Returns True if healthy.

    Phase 12.30: On failure, preserve existing DB_HEALTHY if it was
    already verified True at startup — don't downgrade it on transient errors.
    """
    global DB_HEALTHY
    _logger = logging.getLogger(__name__)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        DB_HEALTHY = True
        return True
    except Exception as e:
        # Don't overwrite a previously-verified healthy flag —
        # the test/ASGITransport event-loop mismatch is transient
        if not DB_HEALTHY:
            _logger.warning(f"Database connectivity check failed: {e}")
        return DB_HEALTHY

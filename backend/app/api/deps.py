"""
TravelMind Agent — API Dependencies

FastAPI dependencies for device_id extraction and optional database sessions.
These are injected into route handlers via Depends().
"""

import logging
from typing import AsyncGenerator, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import connection as db_conn

logger = logging.getLogger(__name__)


async def get_device_id(request: Request) -> Optional[str]:
    """Extract X-Device-ID from request header (set by frontend via localStorage).

    Returns None if the header is missing — routes should degrade gracefully.
    """
    return request.headers.get("X-Device-ID")


async def get_db() -> AsyncGenerator[Optional[AsyncSession], None]:
    """Yield an async DB session if the database is healthy; yield None otherwise.

    Routes that need the database should accept Optional[AsyncSession] and
    check for None before performing DB operations.
    """
    if not db_conn.DB_HEALTHY:
        yield None
        return

    session = db_conn.async_session()
    try:
        yield session
    finally:
        await session.close()

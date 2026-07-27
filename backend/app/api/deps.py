"""
TravelMind Agent — API Dependencies

FastAPI dependencies for device_id extraction and optional database sessions.
These are injected into route handlers via Depends().
"""

import logging
import re
from typing import AsyncGenerator, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import connection as db_conn

logger = logging.getLogger(__name__)

# Phase 12.29: device_id 格式校验 — 只允许 1-64 字符的字母数字和连字符
_DEVICE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


async def get_device_id(request: Request) -> Optional[str]:
    """Extract X-Device-ID from request header (set by frontend via localStorage).

    Returns None if the header is missing, empty, or fails format validation.
    """
    raw = request.headers.get("X-Device-ID")
    if not raw:
        return None
    # Phase 12.29: validate format to prevent spoofing/path traversal
    if not _DEVICE_ID_RE.match(raw):
        logger.warning(f"Rejected invalid X-Device-ID: {raw[:32]}...")
        return None
    return raw


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

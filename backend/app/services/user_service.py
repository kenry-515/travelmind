"""
TravelMind Agent — User Service

Anonymous user lifecycle: lookup or create by device_id.
No registration flow — device_id is the sole identity for anonymous users.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User

logger = logging.getLogger(__name__)


async def get_or_create_user(
    db: AsyncSession,
    device_id: str,
    nickname: Optional[str] = None,
) -> User:
    """Look up a User by device_id; create one if not found.

    Updates last_active_at on every call. This is the primary entry point
    for anonymous user identity — no email, no password, no registration.
    """
    result = await db.execute(
        select(User).where(User.device_id == device_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            device_id=device_id,
            nickname=nickname,
            is_anonymous=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"Created new anonymous user: {user.id} (device={device_id[:12]}...)")
    else:
        # Phase 12.29: Touch last_active_at for analytics/cleanup
        user.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()

    return user


async def get_user_by_device_id(
    db: AsyncSession,
    device_id: str,
) -> Optional[User]:
    """Read-only lookup. Returns None if no user exists for this device_id."""
    result = await db.execute(
        select(User).where(User.device_id == device_id)
    )
    return result.scalar_one_or_none()

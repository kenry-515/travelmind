"""
TravelMind Agent — Favorites Service

CRUD for user favorites (attractions and itineraries).
All functions degrade gracefully when DB is unavailable.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Favorite

logger = logging.getLogger(__name__)


async def add_favorite(
    db: AsyncSession,
    user_id: str,
    target_type: str,
    target_id: str,
) -> Optional[Favorite]:
    """Add a favorite. Returns the Favorite ORM object or None."""
    if db is None:
        return None

    # Idempotency: don't duplicate the same favorite
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.target_type == target_type,
            Favorite.target_id == target_id,
        )
    )
    if existing.scalar_one_or_none():
        return None  # Already favorited — caller can treat as success

    fav = Favorite(
        user_id=user_id,
        target_type=target_type,
        target_id=target_id,
    )
    db.add(fav)
    try:
        await db.commit()
        await db.refresh(fav)
        return fav
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to add favorite: {e}")
        return None


async def remove_favorite(
    db: AsyncSession,
    favorite_id: str,
    user_id: str,
) -> bool:
    """Remove a favorite. Only the owner can remove it.

    Returns True on success, False if not found or not owned.
    """
    if db is None:
        return False

    try:
        result = await db.execute(
            select(Favorite).where(Favorite.id == favorite_id)
        )
        fav = result.scalar_one_or_none()

        if fav is None or str(fav.user_id) != str(user_id):
            return False

        await db.delete(fav)
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to remove favorite {favorite_id}: {e}")
        return False


async def list_favorites(
    db: AsyncSession,
    user_id: str,
    target_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List favorites for a user, optionally filtered by type.

    Returns a list of {id, target_type, target_id, created_at} dicts.
    """
    if db is None:
        return []

    try:
        stmt = (
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(desc(Favorite.created_at))
        )
        if target_type:
            stmt = stmt.where(Favorite.target_type == target_type)

        result = await db.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "id": row.id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list favorites: {e}")
        return []

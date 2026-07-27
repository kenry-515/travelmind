"""
TravelMind Agent — Itinerary Persistence Service

CRUD operations for the itineraries table. All functions accept an optional
AsyncSession — when None (DB degraded), they return safe defaults.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Itinerary

logger = logging.getLogger(__name__)


async def save_itinerary(
    db: AsyncSession,
    user_id: str,
    itinerary: Dict[str, Any],
    validation_report: Optional[Dict[str, Any]] = None,
    profile_snapshot: Optional[Dict[str, Any]] = None,
    weather_snapshot: Optional[Dict[str, Any]] = None,
) -> Optional[Itinerary]:
    """Persist a generated itinerary to the database.

    Returns the saved Itinerary ORM object, or None if the database is
    unavailable.
    """
    if db is None:
        return None

    trip = itinerary.get("trip", {})
    title = trip.get("title", "")
    days_count = trip.get("daysCount", len(itinerary.get("days", [])))

    # Use the validation_report from the itinerary if not explicitly passed
    vr = validation_report or itinerary.get("validation_report")

    obj = Itinerary(
        user_id=user_id,
        title=title,
        days=days_count,
        plan=itinerary,
        validation_report=vr,
        profile_snapshot=profile_snapshot,
        weather_snapshot=weather_snapshot,
    )
    db.add(obj)
    try:
        await db.commit()
        await db.refresh(obj)
        logger.info(f"Itinerary saved: {obj.id} (user={user_id[:8]}...)")

        # Phase 8.3: Auto-create version 1 (initial snapshot)
        try:
            from app.services.itinerary_version_service import create_version
            await create_version(
                db, obj.id, itinerary,
                change_description="初始生成",
            )
        except Exception as e:
            logger.warning(f"Version v1 creation skipped (non-fatal): {e}")

        return obj
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to save itinerary: {e}")
        return None


async def list_itineraries(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return a paginated list of itinerary summaries for a user.

    Returns ([{id, title, city, days, created_at}, ...], total_count).
    When DB is unavailable, returns ([], 0).
    """
    if db is None:
        return [], 0

    try:
        # Count total
        count_stmt = (
            select(func.count())
            .select_from(Itinerary)
            .where(Itinerary.user_id == user_id)
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        # Fetch page
        stmt = (
            select(Itinerary)
            .where(Itinerary.user_id == user_id)
            .order_by(desc(Itinerary.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        summaries = []
        for row in rows:
            plan = row.plan or {}
            trip = plan.get("trip", {})
            summaries.append({
                "id": row.id,
                "title": row.title or trip.get("title", "未命名行程"),
                "city": trip.get("city", ""),
                "days": row.days,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            })

        return summaries, total
    except Exception as e:
        logger.error(f"Failed to list itineraries: {e}")
        return [], 0


async def get_itinerary(
    db: AsyncSession,
    itinerary_id: str,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get a single itinerary by ID.

    If user_id is provided, verifies ownership — returns None if the
    itinerary belongs to a different user (privacy).
    """
    if db is None:
        return None

    try:
        result = await db.execute(
            select(Itinerary).where(Itinerary.id == itinerary_id)
        )
        row = result.scalar_one_or_none()

        if row is None:
            return None

        # Privacy: only the owner can read
        if user_id is not None and str(row.user_id) != str(user_id):
            return None

        return {
            "id": row.id,
            "title": row.title,
            "days": row.days,
            "plan": row.plan,
            "validation_report": row.validation_report,
            "profile_snapshot": row.profile_snapshot,
            "weather_snapshot": row.weather_snapshot,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }
    except Exception as e:
        logger.error(f"Failed to get itinerary {itinerary_id}: {e}")
        return None


async def update_itinerary_plan(
    db: AsyncSession,
    itinerary_id: str,
    plan: Dict[str, Any],
) -> bool:
    """Update just the plan (+ days, title) of an existing itinerary.

    Used by version restore. Does NOT create a new version — the caller
    should have already created the restore version.
    """
    if db is None:
        return False

    try:
        result = await db.execute(
            select(Itinerary).where(Itinerary.id == itinerary_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False

        trip = plan.get("trip", {})
        row.title = trip.get("title", row.title)
        row.days = trip.get("daysCount", len(plan.get("days", [])))
        row.plan = plan
        row.validation_report = plan.get("validation_report", row.validation_report)

        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update itinerary plan {itinerary_id}: {e}")
        return False


async def delete_itinerary(
    db: AsyncSession,
    itinerary_id: str,
    user_id: str,
) -> bool:
    """Delete an itinerary. Only the owner can delete.

    Returns True on success, False if not found or not owned.
    """
    if db is None:
        return False

    try:
        result = await db.execute(
            select(Itinerary).where(Itinerary.id == itinerary_id)
        )
        row = result.scalar_one_or_none()

        if row is None or str(row.user_id) != str(user_id):
            return False

        await db.delete(row)
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete itinerary {itinerary_id}: {e}")
        return False

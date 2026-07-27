"""
TravelMind Agent — Itinerary Version Service (Phase 8.3)

Snapshot version chain for itinerary changes. Each regeneration creates
a new version with the full plan JSON. Restore copies the target version
into a new version (copy-on-restore).

Database-backed only — no in-memory fallback. If DB is unhealthy, versioning
is silently skipped (non-fatal for the generation flow).
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ItineraryVersion

logger = logging.getLogger(__name__)


async def get_latest_version_number(
    db: AsyncSession,
    itinerary_id: str,
) -> int:
    """Get the current highest version number for an itinerary. Returns 0 if none."""
    result = await db.execute(
        select(func.max(ItineraryVersion.version_number))
        .where(ItineraryVersion.itinerary_id == itinerary_id)
    )
    max_n = result.scalar()
    return max_n or 0


async def create_version(
    db: AsyncSession,
    itinerary_id: str,
    plan: Dict[str, Any],
    change_description: str = "",
) -> Optional[ItineraryVersion]:
    """Create a new version snapshot. Returns the new version or None on failure."""
    try:
        latest = await get_latest_version_number(db, itinerary_id)
        version = ItineraryVersion(
            itinerary_id=itinerary_id,
            version_number=latest + 1,
            plan=plan,
            change_description=change_description,
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)
        logger.info(
            f"Created version {version.version_number} for itinerary {itinerary_id}"
        )
        return version
    except Exception as e:
        logger.warning(f"Failed to create version (non-fatal): {e}")
        await db.rollback()
        return None


async def list_versions(
    db: AsyncSession,
    itinerary_id: str,
) -> List[Dict[str, Any]]:
    """List versions for an itinerary, newest first. Returns summary without plan."""
    result = await db.execute(
        select(ItineraryVersion)
        .where(ItineraryVersion.itinerary_id == itinerary_id)
        .order_by(ItineraryVersion.version_number.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "change_description": v.change_description or "",
            "created_at": v.created_at.isoformat() if v.created_at else "",
        }
        for v in versions
    ]


async def get_version(
    db: AsyncSession,
    itinerary_id: str,
    version_id: str,
) -> Optional[Dict[str, Any]]:
    """Get a specific version with full plan."""
    result = await db.execute(
        select(ItineraryVersion)
        .where(
            ItineraryVersion.itinerary_id == itinerary_id,
            ItineraryVersion.id == version_id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        return None
    return {
        "id": version.id,
        "version_number": version.version_number,
        "plan": version.plan,
        "change_description": version.change_description or "",
        "created_at": version.created_at.isoformat() if version.created_at else "",
    }


async def restore_version(
    db: AsyncSession,
    itinerary_id: str,
    version_id: str,
) -> Optional[Dict[str, Any]]:
    """Restore a previous version by creating a NEW version with its plan.

    Returns:
        {"itinerary": <full plan>, "version": {"number": N, "description": "..."}}
        or None if target version not found.
    """
    target = await get_version(db, itinerary_id, version_id)
    if target is None:
        return None

    plan = target["plan"]
    target_num = target["version_number"]
    desc = f"恢复到版本 V{target_num}"

    version = await create_version(db, itinerary_id, plan, change_description=desc)
    if version is None:
        return None

    return {
        "itinerary": plan,
        "version": {
            "number": version.version_number,
            "description": desc,
            "id": version.id,
        },
    }

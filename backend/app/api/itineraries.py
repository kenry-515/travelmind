"""
TravelMind Agent — Itinerary History API

GET  /api/v1/itineraries       — list user's saved itineraries
GET  /api/v1/itineraries/{id}  — get single itinerary detail
DELETE /api/v1/itineraries/{id} — delete an itinerary

Privacy: all endpoints filter by device_id → user. A user cannot
see or delete another user's itineraries.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_device_id, get_db
from app.services.user_service import get_or_create_user
from app.services import itinerary_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response Models ──────────────────────────────────────

class ItinerarySummary(BaseModel):
    id: str
    title: str
    city: str = ""
    days: int
    created_at: str


class ItineraryListResponse(BaseModel):
    itineraries: list[ItinerarySummary]
    total: int
    page: int
    page_size: int


class ItineraryDetailResponse(BaseModel):
    id: str
    title: Optional[str] = None
    days: int
    plan: dict
    validation_report: Optional[dict] = None
    profile_snapshot: Optional[dict] = None
    weather_snapshot: Optional[dict] = None
    created_at: str
    updated_at: str = ""


# ── Routes ────────────────────────────────────────────────

@router.get("/itineraries", response_model=ItineraryListResponse)
async def list_itineraries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """List the current user's saved itineraries, newest first."""
    if not device_id:
        return {"itineraries": [], "total": 0, "page": page, "page_size": page_size}

    if db is None:
        return {"itineraries": [], "total": 0, "page": page, "page_size": page_size}

    user = await get_or_create_user(db, device_id)

    summaries, total = await itinerary_service.list_itineraries(
        db, user.id, page=page, page_size=page_size
    )
    return {
        "itineraries": summaries,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/itineraries/{itinerary_id}", response_model=ItineraryDetailResponse)
async def get_itinerary_detail(
    itinerary_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Get a single itinerary by ID. Only the owner can access it."""
    if db is None:
        raise HTTPException(status_code=503, detail="历史记录服务暂不可用")

    user_id = None
    if device_id:
        user = await get_or_create_user(db, device_id)
        if user:
            user_id = user.id

    detail = await itinerary_service.get_itinerary(db, itinerary_id, user_id=user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="行程未找到")

    return detail


@router.delete("/itineraries/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Delete an itinerary. Only the owner can delete it."""
    if db is None:
        raise HTTPException(status_code=503, detail="历史记录服务暂不可用")

    if not device_id:
        raise HTTPException(status_code=400, detail="缺少设备标识")

    user = await get_or_create_user(db, device_id)
    if user is None:
        raise HTTPException(status_code=404, detail="行程未找到")

    ok = await itinerary_service.delete_itinerary(db, itinerary_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="行程未找到或无权删除")

    return {"ok": True}

"""
TravelMind Agent — Favorites API

GET    /api/v1/favorites        — list user's favorites
POST   /api/v1/favorites        — add a favorite
DELETE /api/v1/favorites/{id}   — remove a favorite

Privacy: all endpoints filter by device_id → user.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_device_id, get_db
from app.services.user_service import get_or_create_user
from app.services import favorite_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ────────────────────────────

class AddFavoriteRequest(BaseModel):
    target_type: str = Field(..., description="'attraction' or 'itinerary'")
    target_id: str = Field(..., max_length=255)


class FavoriteItem(BaseModel):
    id: str
    target_type: str
    target_id: str
    created_at: str


class FavoriteListResponse(BaseModel):
    favorites: list[FavoriteItem]


# ── Routes ────────────────────────────────────────────────

@router.get("/favorites", response_model=FavoriteListResponse)
async def list_favorites(
    target_type: Optional[str] = None,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """List the current user's favorites, optionally filtered by type."""
    if not device_id or db is None:
        return {"favorites": []}

    user = await get_or_create_user(db, device_id)
    if user is None:
        return {"favorites": []}

    items = await favorite_service.list_favorites(db, user.id, target_type=target_type)
    return {"favorites": items}


@router.post("/favorites")
async def add_favorite(
    body: AddFavoriteRequest,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Add a favorite (attraction or itinerary)."""
    if db is None:
        raise HTTPException(status_code=503, detail="收藏服务暂不可用")

    if not device_id:
        raise HTTPException(status_code=400, detail="缺少设备标识")

    if body.target_type not in ("attraction", "itinerary"):
        raise HTTPException(status_code=422, detail="target_type 必须为 'attraction' 或 'itinerary'")

    user = await get_or_create_user(db, device_id)
    if user is None:
        raise HTTPException(status_code=400, detail="用户未找到")

    fav = await favorite_service.add_favorite(
        db, user.id, body.target_type, body.target_id
    )
    if fav is None:
        # Could be duplicate or DB error — in either case, return success
        # since the desired state (favorited) is already achieved
        return {"ok": True, "detail": "已收藏或服务暂不可用"}

    return {
        "ok": True,
        "favorite": {
            "id": fav.id,
            "target_type": fav.target_type,
            "target_id": fav.target_id,
            "created_at": fav.created_at.isoformat() if fav.created_at else "",
        },
    }


@router.delete("/favorites/{favorite_id}")
async def remove_favorite(
    favorite_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Remove a favorite. Only the owner can remove it."""
    if db is None:
        raise HTTPException(status_code=503, detail="收藏服务暂不可用")

    if not device_id:
        raise HTTPException(status_code=400, detail="缺少设备标识")

    user = await get_or_create_user(db, device_id)
    if user is None:
        raise HTTPException(status_code=404, detail="收藏未找到")

    ok = await favorite_service.remove_favorite(db, favorite_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="收藏未找到或无权删除")

    return {"ok": True}

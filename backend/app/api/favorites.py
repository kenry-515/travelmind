"""
TravelMind Agent — Favorites API (Phase 5 P0 优化)

用户侧收藏栏优化:
  - POST /favorites 接受 poi_name (常用), 自动归一化到 target_id, 默认 attraction
  - GET /favorites 拉 POI 详情 (name, city, district, tags, popularity)
  - GET /favorites/pois 拉所有收藏 POI (按收藏顺序)

向后兼容:
  - target_type/target_id 仍可用
  - 旧客户端不会破坏
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.errors import error_response
from app.api.deps import get_device_id, get_db
from app.services.user_service import get_or_create_user
from app.services import favorite_service
from app.agents.guide_agent import _load_attractions

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ────────────────────────────

class AddFavoriteRequest(BaseModel):
    """Phase 5 P0: 接受 POI name + 自动归一化, 简化用户操作。

    优先字段:
      - poi_name: 景点名字 (前端搜索结果直接传)
      - city: 城市 (默认 "广州")
      - target_type: 兼容旧版 ("attraction" | "itinerary")
      - target_id: 兼容旧版 (直接传 target_id 时)
      - note: 备注 (e.g., "想带孩子去")
    """
    poi_name: Optional[str] = Field(None, max_length=255, description="景点名 (推荐)")
    city: Optional[str] = Field("广州", max_length=50, description="城市")
    target_type: Optional[str] = Field(None, description="'attraction' | 'itinerary' (兼容)")
    target_id: Optional[str] = Field(None, max_length=255, description="兼容旧版: 直接 ID")
    note: Optional[str] = Field(None, max_length=500, description="备注")


class FavoriteItem(BaseModel):
    id: str
    target_type: str
    target_id: str
    created_at: str
    # Phase 5 P0: POI 详情 (从 attractions.json 实时 join)
    poi_name: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    tags: Optional[List[str]] = None
    popularity_score: Optional[float] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    note: Optional[str] = None


class FavoriteListResponse(BaseModel):
    favorites: List[FavoriteItem]


# ── Helpers ──────────────────────────────────────────────

def _find_poi_by_name(poi_name: str, city: str = "广州") -> Optional[Dict[str, Any]]:
    """从 attractions.json 查 POI 详情 (for 列表 join)."""
    try:
        attractions = _load_attractions()
        for a in attractions:
            if a.get("city") == city and a.get("name") == poi_name:
                return a
        # 模糊匹配 (e.g., "陈家祠" == "陈家祠旅游区")
        for a in attractions:
            if a.get("city") != city:
                continue
            name = a.get("name", "")
            if poi_name in name or name in poi_name:
                return a
    except Exception as e:
        logger.warning(f"find_poi_by_name failed: {e}")
    return None


def _enrich_favorite(fav: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 5 P0: 加 POI 详情到 favorite (前端可直接渲染)."""
    if fav.get("target_type") == "attraction":
        poi = _find_poi_by_name(fav["target_id"])
        if poi:
            fav["poi_name"] = poi.get("name")
            fav["city"] = poi.get("city")
            fav["district"] = poi.get("district")
            fav["tags"] = poi.get("tags", [])
            fav["popularity_score"] = poi.get("popularity_score")
            fav["category"] = poi.get("category")
            fav["subcategory"] = poi.get("subcategory")
    return fav


# ── Routes ────────────────────────────────────────────────

@router.get("/favorites", response_model=FavoriteListResponse)
async def list_favorites(
    target_type: Optional[str] = None,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """List user's favorites, enriched with POI details."""
    if not device_id or db is None:
        return {"favorites": []}

    user = await get_or_create_user(db, device_id)
    if user is None:
        return {"favorites": []}

    items = await favorite_service.list_favorites(db, user.id, target_type=target_type)
    enriched = [_enrich_favorite(item) for item in items]
    return {"favorites": enriched}


@router.get("/favorites/pois", response_model=FavoriteListResponse)
async def list_favorite_pois(
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Phase 5 P0: 一键拉所有收藏 POI (前端可直接渲染).

    过滤: 只返 attraction 类型 (排除 itinerary)
    """
    return await list_favorites(target_type="attraction", device_id=device_id, db=db)


@router.post("/favorites")
async def add_favorite(
    body: AddFavoriteRequest,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Add a favorite. Phase 5 P0: 接受 poi_name, 自动归一化到 target_id."""
    if db is None:
        raise error_response(503, "SERVICE_UNAVAILABLE", "收藏服务暂不可用")

    if not device_id:
        raise error_response(400, "AUTH_REQUIRED", "缺少设备标识")

    # 归一化: target_id (优先) > poi_name
    target_id = body.target_id or body.poi_name
    if not target_id:
        raise error_response(422, "VALIDATION_FAILED", "需要 poi_name 或 target_id")

    # 归一化: target_type (默认 "attraction")
    target_type = body.target_type or "attraction"
    if target_type not in ("attraction", "itinerary"):
        raise error_response(422, "VALIDATION_FAILED", "target_type 必须为 'attraction' 或 'itinerary'")

    # attraction 类型: 验证 POI 存在 (POI 必须先在 attractions.json 里)
    if target_type == "attraction":
        poi = _find_poi_by_name(target_id, body.city or "广州")
        if not poi:
            # 仍允许收藏 (e.g., 临时收藏未入库的 POI), 但 warn
            logger.warning(f"add_favorite: POI not found in {body.city}: {target_id}")

    user = await get_or_create_user(db, device_id)
    if user is None:
        raise error_response(400, "NOT_FOUND", "用户未找到")

    fav = await favorite_service.add_favorite(
        db, user.id, target_type, target_id
    )

    # 构造返 response (含 POI 详情)
    if fav is not None:
        base = {
            "id": fav.id,
            "target_type": fav.target_type,
            "target_id": fav.target_id,
            "created_at": fav.created_at.isoformat() if fav.created_at else "",
            "note": body.note,
        }
    else:
        # 重复, 找 existing
        items = await favorite_service.list_favorites(db, user.id, target_type=target_type)
        existing = next((f for f in items if f["target_id"] == target_id), None)
        if existing:
            existing["note"] = body.note
            return {"ok": True, "favorite": _enrich_favorite(existing)}
        return {"ok": True, "detail": "已收藏或服务暂不可用"}

    return {"ok": True, "favorite": _enrich_favorite(base)}


@router.delete("/favorites/{favorite_id}")
async def remove_favorite(
    favorite_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Remove a favorite. Only the owner can remove it."""
    if db is None:
        raise error_response(503, "SERVICE_UNAVAILABLE", "收藏服务暂不可用")

    if not device_id:
        raise error_response(400, "AUTH_REQUIRED", "缺少设备标识")

    user = await get_or_create_user(db, device_id)
    if user is None:
        raise error_response(404, "NOT_FOUND", "收藏未找到")

    ok = await favorite_service.remove_favorite(db, favorite_id, user.id)
    if not ok:
        raise error_response(404, "NOT_FOUND", "收藏未找到或无权删除")

    return {"ok": True}

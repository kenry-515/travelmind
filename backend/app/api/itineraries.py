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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.errors import error_response

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
    # Phase 8.2: Revalidation alerts when revalidate=true
    revalidation_alerts: Optional[list[dict]] = None


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
        # PG 不可达 → 本地文件存储
        from app.services import local_itinerary_store
        summaries, total = local_itinerary_store.list_itineraries(
            device_id, page=page, page_size=page_size
        )
        return {
            "itineraries": summaries,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

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
    revalidate: bool = Query(False, description="重新运行POI存续校验，检测是否有景点已关闭"),
):
    """Get a single itinerary by ID. Only the owner can access it.

    With revalidate=true, re-runs POI existence checks against the current
    known_closures list and returns any new alerts. The saved plan is NOT
    modified — this is a read-only re-check.
    """
    if db is None:
        if not device_id:
            raise error_response(400, "AUTH_REQUIRED", "缺少设备标识")
        from app.services import local_itinerary_store
        detail = local_itinerary_store.get_itinerary(device_id, itinerary_id)
        if detail is None:
            raise error_response(404, "NOT_FOUND", "行程未找到")
        return detail

    user_id = None
    if device_id:
        user = await get_or_create_user(db, device_id)
        if user:
            user_id = user.id

    detail = await itinerary_service.get_itinerary(db, itinerary_id, user_id=user_id)
    if detail is None:
        raise error_response(404, "NOT_FOUND", "行程未找到")

    # Phase 8.2: Revalidate POI status on demand
    revalidation_alerts = None
    if revalidate and isinstance(detail, dict) and detail.get("plan"):
        try:
            from app.agents.route_optimizer import _load_closures, _base_name, _is_visit
            closures = _load_closures()
            alerts = []
            plan = detail["plan"]
            seen = set()
            for day in plan.get("days", []):
                for item in day.get("items", []):
                    poi = item.get("poi", "")
                    if not _is_visit(poi):
                        continue
                    base = _base_name(poi)
                    if base in seen:
                        continue
                    seen.add(base)
                    if base in closures:
                        closure = closures[base]
                        alerts.append({
                            "poi": poi,
                            "day": day.get("day"),
                            "status": "closed",
                            "evidence": closure.get("evidence", ""),
                            "suggested_replacement": closure.get("replacement_keyword", ""),
                            "note": closure.get("replacement_note",
                                f"该景点已确认关闭（{closure.get('closed_since', '未知')}）"),
                        })
            if alerts:
                revalidation_alerts = alerts
        except Exception as e:
            logger.warning(f"Revalidation failed (non-fatal): {e}")

    if revalidation_alerts:
        detail["revalidation_alerts"] = revalidation_alerts

    return detail


# ── 版本历史 (Phase 8.3) ────────────────────────────────


class VersionSummary(BaseModel):
    id: str
    version_number: int
    change_description: str
    created_at: str


class VersionListResponse(BaseModel):
    versions: list[VersionSummary]


class VersionDetailResponse(BaseModel):
    id: str
    version_number: int
    plan: dict
    change_description: str
    created_at: str


class RestoreResponse(BaseModel):
    itinerary: dict
    version: VersionSummary


@router.get(
    "/itineraries/{itinerary_id}/versions",
    response_model=VersionListResponse,
)
async def list_versions(
    itinerary_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """List all versions for an itinerary, newest first."""
    if db is None:
        raise error_response(503, "SERVICE_UNAVAILABLE", "版本历史暂不可用")

    from app.services import itinerary_version_service as ver_svc

    # Verify ownership
    detail = await itinerary_service.get_itinerary(
        db, itinerary_id,
        user_id=(await _get_user_id(db, device_id)) if device_id else None,
    )
    if detail is None:
        raise error_response(404, "NOT_FOUND", "行程未找到")

    versions = await ver_svc.list_versions(db, itinerary_id)
    return {"versions": versions}


@router.get(
    "/itineraries/{itinerary_id}/versions/{version_id}",
    response_model=VersionDetailResponse,
)
async def get_version_detail(
    itinerary_id: str,
    version_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Get a specific version with its full plan."""
    if db is None:
        raise error_response(503, "SERVICE_UNAVAILABLE", "版本历史暂不可用")

    from app.services import itinerary_version_service as ver_svc

    # Verify ownership
    detail = await itinerary_service.get_itinerary(
        db, itinerary_id,
        user_id=(await _get_user_id(db, device_id)) if device_id else None,
    )
    if detail is None:
        raise error_response(404, "NOT_FOUND", "行程未找到")

    version = await ver_svc.get_version(db, itinerary_id, version_id)
    if version is None:
        raise error_response(404, "NOT_FOUND", "版本未找到")

    return version


@router.post(
    "/itineraries/{itinerary_id}/restore/{version_id}",
    response_model=RestoreResponse,
)
async def restore_version(
    itinerary_id: str,
    version_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Restore an itinerary to a previous version (creates new version)."""
    if db is None:
        raise error_response(503, "SERVICE_UNAVAILABLE", "版本历史暂不可用")

    user_id = await _get_user_id(db, device_id) if device_id else None

    # Verify ownership
    detail = await itinerary_service.get_itinerary(db, itinerary_id, user_id=user_id)
    if detail is None:
        raise error_response(404, "NOT_FOUND", "行程未找到")

    from app.services import itinerary_version_service as ver_svc

    result = await ver_svc.restore_version(db, itinerary_id, version_id)
    if result is None:
        raise error_response(404, "NOT_FOUND", "版本未找到")

    # Update the current itinerary plan
    await itinerary_service.update_itinerary_plan(
        db, itinerary_id, result["itinerary"]
    )

    return result


async def _get_user_id(db, device_id: Optional[str]) -> Optional[str]:
    """Helper: resolve device_id to user_id."""
    if not device_id or db is None:
        return None
    user = await get_or_create_user(db, device_id)
    return user.id if user else None


@router.delete("/itineraries/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str,
    device_id: Optional[str] = Depends(get_device_id),
    db=Depends(get_db),
):
    """Delete an itinerary. Only the owner can delete it."""
    if db is None:
        if not device_id:
            raise error_response(400, "AUTH_REQUIRED", "缺少设备标识")
        from app.services import local_itinerary_store
        if not local_itinerary_store.delete_itinerary(device_id, itinerary_id):
            raise error_response(404, "NOT_FOUND", "行程未找到或无权删除")
        return {"ok": True}

    if not device_id:
        raise error_response(400, "AUTH_REQUIRED", "缺少设备标识")

    user = await get_or_create_user(db, device_id)
    if user is None:
        raise error_response(404, "NOT_FOUND", "行程未找到")

    ok = await itinerary_service.delete_itinerary(db, itinerary_id, user.id)
    if not ok:
        raise error_response(404, "NOT_FOUND", "行程未找到或无权删除")

    return {"ok": True}

"""
TravelMind Agent — Agent API
Endpoints for the multi-agent travel planning workflow.

POST /api/v1/agent/plan                — Run the full orchestrated workflow.
POST /api/v1/agent/plan/stream         — Run workflow with SSE progress events.
POST /api/v1/agent/profile             — Standalone profile extraction.
POST /api/v1/agent/plan/regenerate-day — Rebuild one day of an itinerary.
GET  /api/v1/agent/plan/status/{task_id} — Poll for stream task status.
POST /api/v1/agent/itinerary/share/{itinerary_id} — Create share link.
GET  /api/v1/agent/share/{share_id} — Get shared itinerary.
DELETE /api/v1/agent/share/{share_id} — Delete share link.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.errors import error_response, ErrorPresets
from pydantic import BaseModel, Field, field_validator

from app.agents.orchestrator import run_travel_workflow, run_travel_workflow_stream
from app.agents.planning_agent import regenerate_day
from app.agents.profile_agent import extract_profile
from app.api.deps import get_device_id
from app.database import connection as db_conn
from app.rag.retriever import retrieve
from app.services.user_service import get_or_create_user
from app.services import itinerary_service
from app.services import plan_status_store as pss
from app.services import share_service
from app.services import local_itinerary_store

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ───────────────────────────

class PlanRequest(BaseModel):
    user_input: str = Field(
        ..., min_length=1, max_length=2000,
        description="Natural language travel request from the user",
    )
    messages: Optional[List[Dict[str, str]]] = Field(
        None, max_length=50,
        description="Optional conversation history",
    )

    @field_validator("user_input")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_input must not be blank")
        return v


class ProfileRequest(BaseModel):
    user_input: str = Field(
        ..., min_length=1, max_length=2000,
        description="Natural language input to extract profile from",
    )

    @field_validator("user_input")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_input must not be blank")
        return v


class PlanResponse(BaseModel):
    """Filtered view of TravelState for API consumers.

    Only returns user/assistant messages — internal system prompts are filtered.
    """
    user_input: str
    user_profile: Optional[Dict[str, Any]]
    trend_data: Optional[List[Dict[str, Any]]]
    candidate_places: Optional[List[Dict[str, Any]]]
    recommendations: Optional[List[Dict[str, Any]]]
    itinerary: Optional[Dict[str, Any]]
    weather: Optional[Dict[str, Any]]
    current_step: str
    error: Optional[str]
    messages: List[Dict[str, str]]
    itinerary_id: Optional[str] = None  # DB ID when auto-saved


class PlanStatusResponse(BaseModel):
    """Response for plan generation status polling."""
    task_id: str
    status: str  # "generating", "completed", "error", "not_found"
    data: Optional[Dict[str, Any]] = None


class ProfileResponse(BaseModel):
    profile: Dict[str, Any]


class RegenerateDayRequest(BaseModel):
    """Partial itinerary regeneration request."""

    itinerary: Dict[str, Any] = Field(..., description="当前完整行程 JSON（契约结构）")
    day_index: int = Field(..., ge=0, description="要重生成的天的 0 基索引")
    feedback: str = Field(..., min_length=1, max_length=500, description="用户反馈，如「第二天太赶了」")
    user_input: Optional[str] = Field(
        None, max_length=2000,
        description="原始需求文本（可选，用于重建用户画像）",
    )


class RegenerateDayResponse(BaseModel):
    itinerary: Dict[str, Any]


# ── Helpers ─────────────────────────────────────────────

def _sanitize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Filter internal messages — only return user / assistant visible content."""
    return [m for m in messages if m.get("role") in ("user", "assistant")]


async def _save_itinerary(
    state: Dict[str, Any],
    device_id: Optional[str],
) -> Optional[str]:
    """Auto-save a generated itinerary (best-effort, non-blocking).

    PG 不可达时回退到本地文件存储（local_itinerary_store），
    保证「我的行程」在单机开发环境也可用。
    """
    itinerary = state.get("itinerary") or {}
    if not itinerary or not device_id:
        return None
    if not db_conn.DB_HEALTHY:
        try:
            from app.services import local_itinerary_store
            saved_id = local_itinerary_store.save_itinerary(
                device_id=device_id,
                itinerary=itinerary,
                validation_report=itinerary.get("validation_report"),
                profile_snapshot=state.get("user_profile"),
                weather_snapshot=state.get("weather"),
            )
            logger.info(f"Itinerary saved to local store: {saved_id}")
            return saved_id
        except Exception as e:
            logger.warning(f"Itinerary local save failed (non-fatal): {e}")
            return None

    try:
        async with db_conn.async_session() as db:
            user = await get_or_create_user(db, device_id)
            saved = await itinerary_service.save_itinerary(
                db=db,
                user_id=user.id,
                itinerary=itinerary,
                validation_report=itinerary.get("validation_report"),
                profile_snapshot=state.get("user_profile"),
                weather_snapshot=state.get("weather"),
            )
            if saved:
                logger.info(f"Itinerary auto-saved: {saved.id}")
                return saved.id
    except Exception as e:
        logger.warning(f"Itinerary auto-save skipped (non-fatal): {e}")
    return None


# ── Routes ──────────────────────────────────────────────

@router.post("/agent/plan", response_model=PlanResponse)
async def agent_plan(
    request: PlanRequest,
    device_id: Optional[str] = Depends(get_device_id),
):
    """Run the full multi-agent travel planning workflow.

    This endpoint orchestrates all agents in sequence:
    Profile → Trend → RAG → Recommendation → Planning → Aggregator.

    Agents that are not yet implemented (stubs) will be skipped gracefully.
    The workflow never fails — errors are captured in the `error` field.
    """
    logger.info(f"Agent plan request: {request.user_input[:80]}...")

    try:
        state = await run_travel_workflow(
            user_input=request.user_input,
            messages=request.messages,
        )
    except Exception as e:
        logger.error(f"Workflow fatal error: {e}", exc_info=True)
        raise error_response(
            status_code=500,
            code="WORKFLOW_ERROR",
            message="Agent workflow failed due to an internal error.",
        )

    # Auto-save itinerary to DB (best-effort, non-blocking)
    saved_id = await _save_itinerary(state, device_id)

    return PlanResponse(
        user_input=state.get("user_input", ""),
        user_profile=state.get("user_profile"),
        trend_data=state.get("trend_data"),
        candidate_places=state.get("candidate_places"),
        recommendations=state.get("recommendations"),
        itinerary=state.get("itinerary"),
        weather=state.get("weather") or None,
        current_step=state.get("current_step", "unknown"),
        error=state.get("error"),
        messages=_sanitize_messages(state.get("messages", [])),
        itinerary_id=saved_id,
    )


@router.post("/agent/profile", response_model=ProfileResponse)
async def agent_profile(request: ProfileRequest):
    """Extract a structured user profile from natural language input.

    Uses the Profile Agent (DeepSeek chat_structured) to parse
    destination, budget, tags, travel style, etc. from free-text.
    """
    logger.info(f"Profile extraction request: {request.user_input[:80]}...")

    try:
        profile = await extract_profile(request.user_input)
    except Exception as e:
        logger.error(f"Profile extraction error: {e}", exc_info=True)
        raise error_response(
            status_code=502,
            code="UPSTREAM_ERROR",
            message="LLM service is currently unavailable. Please try again later.",
        )

    return ProfileResponse(profile=profile)


@router.post("/agent/plan/regenerate-day", response_model=RegenerateDayResponse)
async def agent_regenerate_day(request: RegenerateDayRequest):
    """Regenerate a single day of an existing itinerary （局部重生成）.

    The frontend sends the full current itinerary + user feedback; only
    days[day_index] is rebuilt by the LLM — everything else is returned
    byte-identical after full contract revalidation.
    """
    trip = request.itinerary.get("trip")
    if not isinstance(trip, dict):
        trip = {}
    logger.info(
        f"Regenerate day: city={trip.get('city')}, day_index={request.day_index}, "
        f"feedback={request.feedback[:50]}"
    )

    # Profile context: re-extract from the original request when available,
    # otherwise build a minimal one from the itinerary itself.
    if request.user_input:
        try:
            profile = await extract_profile(request.user_input)
        except Exception:
            profile = {}
    else:
        profile = {}
    if not profile.get("destination"):
        profile["destination"] = trip.get("city", "")
    profile.setdefault("days", trip.get("daysCount", len(request.itinerary.get("days", []))))

    # Candidate places for the regeneration prompt (RAG; non-fatal fallback)
    places: List[Dict[str, Any]] = []
    try:
        places = await retrieve(profile, request.feedback, top_k=10)
    except Exception as e:
        logger.warning(f"RAG retrieve failed for regen (non-fatal): {e}")

    try:
        updated = await regenerate_day(
            itinerary=request.itinerary,
            day_index=request.day_index,
            feedback=request.feedback,
            profile=profile,
            places=places,
        )
    except ValueError as e:
        raise error_response(400, "INVALID_INPUT", str(e),
                             suggestion="请检查输入参数后重试")
    except RuntimeError as e:
        logger.error(f"Day regeneration failed: {e}")
        p = ErrorPresets.get("llm_timeout")
        raise error_response(
            502, "UPSTREAM_ERROR",
            "行程重生成失败,请重试",
            suggestion=p["suggestion"],
            retryable=True,
        )

    return RegenerateDayResponse(itinerary=updated)


@router.get("/agent/plan/status/{task_id}", response_model=PlanStatusResponse)
async def agent_plan_status(task_id: str):
    """Get the status of a plan generation task (for SSE fallback polling)."""
    status_data = await pss.get_status(task_id)
    if not status_data:
        return PlanStatusResponse(task_id=task_id, status="not_found")
    
    return PlanStatusResponse(
        task_id=task_id,
        status=status_data["status"],
        data=status_data.get("data"),
    )


@router.post("/agent/plan/stream")
async def agent_plan_stream(
    request: PlanRequest,
    device_id: Optional[str] = Depends(get_device_id),
):
    """Run the full multi-agent workflow with SSE progress streaming.

    Returns text/event-stream with two event types:
      - progress: {step, status, message, task_id} — one per pipeline step
      - result: {data: PlanResponse} — final full state (includes itinerary_id if saved)
    """
    logger.info(f"Agent plan stream: {request.user_input[:80]}...")
    
    # Generate a unique task_id for this generation
    task_id = str(uuid.uuid4())

    async def event_generator():
        state: Dict[str, Any] = {}
        # Set initial status
        await pss.set_status(task_id, "generating")
        
        try:
            async for event in run_travel_workflow_stream(
                user_input=request.user_input,
                messages=request.messages,
            ):
                # Add task_id to the first progress event
                if event.get("event") == "progress" and "task_id" not in event:
                    event["task_id"] = task_id

                # Capture the final state for post-stream save
                if event.get("event") == "result" and isinstance(event.get("data"), dict):
                    state = event["data"]
                    # Update status to completed with the final data
                    await pss.set_status(task_id, "completed", state)

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
        except Exception as e:
            logger.error(f"Stream workflow error: {e}", exc_info=True)
            # Update status to error
            await pss.set_status(task_id, "error", {"message": str(e)})
            yield f"data: {json.dumps({'event': 'error', 'message': '行程规划服务暂时不可用，请稍后重试。'}, ensure_ascii=False)}\n\n".encode("utf-8")
            return

        # Auto-save after all events are yielded (best-effort)
        saved_id = await _save_itinerary(state, device_id)
        if saved_id:
            # Update status with saved_id
            if state:
                state["itinerary_id"] = saved_id
                await pss.set_status(task_id, "completed", state)
                
            # Yield a supplemental event with the itinerary_id
            yield f"data: {json.dumps({'event': 'saved', 'itinerary_id': saved_id}, ensure_ascii=False)}\n\n".encode("utf-8")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# ── Share Endpoints ──────────────────────────────────────

class ShareResponse(BaseModel):
    """Response for share creation.

    Phase 18 M5.3: 新增 signature + expires_at 字段,前端用这两项
    构造可验证的分享 URL: /share/{share_id}?sig={signature}&exp={expires_at}
    """
    share_id: str
    share_url: str
    signature: str = ""  # HMAC-SHA256(16hex),验签用
    expires_at: str = ""
    expires_days: int


class SharedItineraryResponse(BaseModel):
    """Response for getting a shared itinerary."""
    share_id: str
    itinerary: Dict[str, Any]
    title: str
    city: str
    days: int
    created_at: str


@router.post("/agent/itinerary/share/{itinerary_id}", response_model=ShareResponse)
async def create_share(
    itinerary_id: str,
    expires_days: int = 30,
    device_id: Optional[str] = Depends(get_device_id),
):
    """Create a share link for an itinerary."""
    if not device_id:
        raise error_response(400, "INVALID_INPUT", "Device ID is required for sharing.")
    
    # Try to get itinerary from local store first, then DB
    itinerary_data = local_itinerary_store.get_itinerary(device_id, itinerary_id)
    
    # Also try to get from DB if local not found
    if not itinerary_data and db_conn.DB_HEALTHY:
        try:
            async with db_conn.async_session() as db:
                user = await get_or_create_user(db, device_id)
                itinerary_obj = await itinerary_service.get_itinerary(db, user.id, itinerary_id)
                if itinerary_obj:
                    itinerary_data = {
                        "plan": itinerary_obj.itinerary_data,
                        "title": itinerary_obj.title,
                        "city": itinerary_obj.city,
                        "days": len(itinerary_obj.itinerary_data.get("days", [])),
                    }
        except Exception as e:
            logger.warning(f"Failed to fetch itinerary from DB: {e}")
    
    if not itinerary_data:
        raise error_response(404, "NOT_FOUND", f"Itinerary {itinerary_id} not found.")
    
    share_record = share_service.create_share(device_id, itinerary_id, expires_days)

    # Phase 18 M5.3: 构造带签名的 URL
    share_id = share_record["share_id"]
    sig = share_record["signature"]
    expires_at = share_record["expires_at"]
    share_url = f"/share/{share_id}?sig={sig}&exp={expires_at}"

    return ShareResponse(
        share_id=share_id,
        share_url=share_url,
        signature=sig,
        expires_at=expires_at,
        expires_days=expires_days,
    )


@router.get("/agent/share/{share_id}", response_model=SharedItineraryResponse)
async def get_shared_itinerary(
    share_id: str,
    sig: Optional[str] = None,
    device_id: Optional[str] = Depends(get_device_id),
):
    """Get a shared itinerary by share ID + signature.

    Phase 18 M5.3: 验证 ?sig=... 参数,无效签名返回 404(防扫描/暴力枚举)。
    """
    share_record = share_service.get_share(share_id, signature=sig)
    
    if not share_record:
        raise error_response(404, "NOT_FOUND", "Share link not found or has expired.")
    
    # Get the original itinerary
    owner_device_id = share_record.get("device_id", "")
    itinerary_id = share_record.get("itinerary_id", "")
    
    itinerary_data = None
    
    # Try local store
    if owner_device_id:
        itinerary_data = local_itinerary_store.get_itinerary(owner_device_id, itinerary_id)
    
    # Try DB
    if not itinerary_data and db_conn.DB_HEALTHY:
        try:
            async with db_conn.async_session() as db:
                if owner_device_id:
                    user = await get_or_create_user(db, owner_device_id)
                    itinerary_obj = await itinerary_service.get_itinerary(db, user.id, itinerary_id)
                    if itinerary_obj:
                        itinerary_data = {
                            "plan": itinerary_obj.itinerary_data,
                            "title": itinerary_obj.title,
                            "city": itinerary_obj.city,
                            "days": len(itinerary_obj.itinerary_data.get("days", [])),
                        }
        except Exception as e:
            logger.warning(f"Failed to fetch shared itinerary from DB: {e}")
    
    if not itinerary_data:
        raise error_response(404, "NOT_FOUND", "Original itinerary not found.")
    
    plan = itinerary_data.get("plan", {})
    trip = plan.get("trip", {})
    
    return SharedItineraryResponse(
        share_id=share_id,
        itinerary=plan,
        title=itinerary_data.get("title") or trip.get("title", "共享行程"),
        city=itinerary_data.get("city") or trip.get("city", ""),
        days=itinerary_data.get("days") or trip.get("daysCount", len(plan.get("days", []))),
        created_at=share_record.get("created_at", ""),
    )


@router.delete("/agent/share/{share_id}")
async def delete_share(
    share_id: str,
    device_id: Optional[str] = Depends(get_device_id),
):
    """Delete a share link. Only the owner can delete."""
    share_record = share_service.get_share(share_id)
    
    if not share_record:
        raise error_response(404, "NOT_FOUND", "Share link not found.")
    
    # Check ownership
    if share_record.get("device_id") != device_id:
        raise error_response(403, "FORBIDDEN", "Only the owner can delete this share link.")
    
    deleted = share_service.delete_share(share_id)
    
    if deleted:
        return {"message": "Share link deleted successfully."}
    else:
        raise error_response(500, "INTERNAL_ERROR", "Failed to delete share link.")

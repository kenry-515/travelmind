"""
TravelMind Agent — Agent API
Endpoints for the multi-agent travel planning workflow.

POST /api/v1/agent/plan                — Run the full orchestrated workflow.
POST /api/v1/agent/profile             — Standalone profile extraction.
POST /api/v1/agent/plan/regenerate-day — Rebuild one day of an itinerary.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.agents.orchestrator import run_travel_workflow
from app.agents.planning_agent import regenerate_day
from app.agents.profile_agent import extract_profile
from app.rag.retriever import retrieve

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


# ── Routes ──────────────────────────────────────────────

@router.post("/agent/plan", response_model=PlanResponse)
async def agent_plan(request: PlanRequest):
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
        raise HTTPException(
            status_code=500,
            detail="Agent workflow failed due to an internal error.",
        )

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
        raise HTTPException(
            status_code=502,
            detail="LLM service is currently unavailable. Please try again later.",
        )

    return ProfileResponse(profile=profile)


@router.post("/agent/plan/regenerate-day", response_model=RegenerateDayResponse)
async def agent_regenerate_day(request: RegenerateDayRequest):
    """Regenerate a single day of an existing itinerary （局部重生成）.

    The frontend sends the full current itinerary + user feedback; only
    days[day_index] is rebuilt by the LLM — everything else is returned
    byte-identical after full contract revalidation.
    """
    trip = request.itinerary.get("trip") or {}
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
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Day regeneration failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    return RegenerateDayResponse(itinerary=updated)

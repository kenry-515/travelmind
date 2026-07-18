"""
TravelMind Agent — Recommend API

Lightweight recommendation endpoint that runs the agent pipeline
through the recommendation scoring step (stops before LLM itinerary generation).

POST /api/v1/recommend       — Profile → Trend → RAG → Recommend
POST /api/v1/recommend/quick — Fast path: just RAG → Recommend (requires pre-extracted tags)
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.agents.profile_agent import extract_profile
from app.agents.recommendation_agent import recommend
from app.agents.trend_agent import analyze_trends
from app.rag.retriever import retrieve

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ─────────────────────────────


class RecommendRequest(BaseModel):
    """Natural language query → full recommendation pipeline."""

    user_input: str = Field(
        ..., min_length=1, max_length=2000,
        description="Natural language travel request",
    )

    @field_validator("user_input")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_input must not be blank")
        return v


class QuickRecommendRequest(BaseModel):
    """Pre-extracted parameters → fast recommendation path."""

    city: str = Field(..., min_length=1, max_length=50)
    tags: List[str] = Field(default_factory=list, max_length=20)
    budget: str = Field("适中", max_length=20)
    travel_month: int = Field(0, ge=0, le=12)
    top_k: int = Field(20, ge=5, le=50)


class ScoredPlace(BaseModel):
    """A recommended attraction with full score breakdown."""

    name: str
    city: str
    tags: List[str]
    price_level: str
    total_score: float
    score_breakdown: Dict[str, float]


class RecommendResponse(BaseModel):
    """Recommendation results."""

    city: str
    total_results: int
    places: List[Dict[str, Any]]
    trend_summary: Dict[str, Any]


class QuickRecommendResponse(BaseModel):
    """Quick recommendation results."""

    city: str
    total_results: int
    places: List[Dict[str, Any]]


# ── Helpers ───────────────────────────────────────────────


def _summarize_trends(trends: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a summary of trend data for the response."""
    if not trends:
        return {"total": 0, "top_trending": []}

    sorted_trends = sorted(
        trends,
        key=lambda t: t.get("effective_score", t.get("normalized_score", 0)),
        reverse=True,
    )
    top = [
        {
            "name": t.get("place_name", ""),
            "score": t.get("effective_score", t.get("normalized_score", 0)),
            "tag": t.get("tag", ""),
            "source": t.get("source", ""),
        }
        for t in sorted_trends[:5]
    ]

    return {
        "total": len(trends),
        "top_trending": top,
    }


def _extract_place_summary(places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract a clean summary of each recommended place for API response."""
    summaries = []
    for p in places:
        breakdown = p.get("_score_breakdown", {})
        summaries.append({
            "name": p.get("name", ""),
            "city": p.get("city", ""),
            "tags": p.get("tags", []),
            "price_level": p.get("price_level", ""),
            "best_time": p.get("best_time", ""),
            "suitable_for": p.get("suitable_for", ""),
            "total_score": p.get("total_score", 0),
            "score_breakdown": {
                "preference_match": breakdown.get("preference_match", 0),
                "trend_heat": breakdown.get("trend_heat", 0),
                "budget_match": breakdown.get("budget_match", 0),
                "location_efficiency": breakdown.get("location_efficiency", 0),
                "time_match": breakdown.get("time_match", 0),
                "data_reliability": breakdown.get("data_reliability", 0),
            },
        })
    return summaries


# ── Routes ────────────────────────────────────────────────


@router.post("/recommend", response_model=RecommendResponse)
async def get_recommendations(request: RecommendRequest):
    """Run the recommendation pipeline from a natural language query.

    This endpoint runs Profile → Trend → RAG → Recommend (stops
    before the expensive LLM itinerary generation). Use this for
    quick place discovery when a full day plan is not yet needed.

    Returns ranked attractions with 6-factor score breakdowns.
    """
    logger.info(f"Recommend request: {request.user_input[:80]}...")

    try:
        # Step 1: Profile extraction
        profile = await extract_profile(request.user_input)
        city = profile.get("destination", "")
        tags = profile.get("tags", [])
        if not city:
            raise HTTPException(
                status_code=422,
                detail="无法识别目的地城市，请提供更详细的旅行需求。",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile extraction failed: {e}")
        raise HTTPException(
            status_code=502,
            detail="LLM 服务暂不可用，请稍后重试。",
        )

    try:
        # Step 2: Trend analysis
        trends = await analyze_trends(city, tags)
    except Exception as e:
        logger.warning(f"Trend analysis failed (non-fatal): {e}")
        trends = []

    try:
        # Step 3: RAG retrieval
        rag_profile = {
            "destination": city,
            "tags": tags,
            "budget_level": profile.get("budget_level", ""),
            "days": profile.get("days", 3),
        }
        candidates = await retrieve(rag_profile, request.user_input, top_k=20)
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        raise HTTPException(
            status_code=502,
            detail="知识库检索服务暂不可用。",
        )

    if not candidates:
        return RecommendResponse(
            city=city,
            total_results=0,
            places=[],
            trend_summary=_summarize_trends(trends),
        )

    try:
        # Step 4: Recommendation scoring
        scored = await recommend(profile, candidates, trends)
    except Exception as e:
        logger.error(f"Recommendation scoring failed: {e}")
        raise HTTPException(
            status_code=502,
            detail="推荐评分服务暂不可用。",
        )

    return RecommendResponse(
        city=city,
        total_results=len(scored),
        places=_extract_place_summary(scored),
        trend_summary=_summarize_trends(trends),
    )


@router.post("/recommend/quick", response_model=QuickRecommendResponse)
async def get_quick_recommendations(request: QuickRecommendRequest):
    """Fast-path recommendations with pre-extracted parameters.

    Skips profile extraction — caller provides city, tags, budget directly.
    Useful for frontend tag pickers or saved preferences.
    """
    logger.info(
        f"Quick recommend: city={request.city}, tags={request.tags}, "
        f"budget={request.budget}, month={request.travel_month}"
    )

    profile = {
        "destination": request.city,
        "tags": request.tags,
        "budget_level": request.budget,
        "travel_month": request.travel_month,
        "days": 3,
    }

    try:
        trends = await analyze_trends(request.city, request.tags)
    except Exception:
        trends = []

    try:
        candidates = await retrieve(profile, "", top_k=request.top_k)
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        raise HTTPException(status_code=502, detail="知识库检索服务暂不可用。")

    if not candidates:
        return QuickRecommendResponse(
            city=request.city,
            total_results=0,
            places=[],
        )

    try:
        scored = await recommend(profile, candidates, trends)
    except Exception as e:
        logger.error(f"Recommendation scoring failed: {e}")
        raise HTTPException(status_code=502, detail="推荐评分服务暂不可用。")

    return QuickRecommendResponse(
        city=request.city,
        total_results=len(scored),
        places=_extract_place_summary(scored),
    )

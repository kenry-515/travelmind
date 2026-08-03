"""
TravelMind Agent — Orchestrator

Coordinates all agents in a 6-step pipeline:

  Profile Extraction → Trend Analysis → Weather Fetch
  → RAG Retrieval → Recommendation Agent
  → Planning Agent → Response Aggregator

Each step reads/writes shared TravelState. Errors are captured
in state["error"] so the pipeline can continue with graceful degradation.

Two entry points:
  - run_travel_workflow()       → blocking, returns final TravelState
  - run_travel_workflow_stream() → async generator, yields SSE progress events
"""

import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)

# ── Lazy imports (module-level) ──────────────────────────

_extract_profile = None
_analyze_trends = None
_retrieve = None
_recommend = None
_generate_itinerary = None

try:
    from app.agents.profile_agent import extract_profile as _extract_profile
except ImportError:
    pass

try:
    from app.agents.trend_agent import analyze_trends as _analyze_trends
except ImportError:
    pass

try:
    from app.rag.retriever import retrieve as _retrieve
except ImportError:
    pass

try:
    from app.agents.recommendation_agent import recommend as _recommend
except ImportError:
    pass

try:
    from app.agents.planning_agent import generate_itinerary as _generate_itinerary
except ImportError:
    pass

# Weather service — optional, graceful degradation if unavailable
_get_weather_forecast = None
try:
    from app.services.weather_service import get_weather_forecast as _get_weather_forecast
except ImportError:
    pass

# ── Startup validation ─────────────────────────────────

_IMPORT_WARNINGS = []
if _extract_profile is None: _IMPORT_WARNINGS.append("extract_profile")
if _analyze_trends is None: _IMPORT_WARNINGS.append("analyze_trends")
if _retrieve is None: _IMPORT_WARNINGS.append("retrieve")
if _recommend is None: _IMPORT_WARNINGS.append("recommend")
if _generate_itinerary is None: _IMPORT_WARNINGS.append("generate_itinerary")
if _IMPORT_WARNINGS:
    logger.warning(f"Orchestrator imports failed for: {', '.join(_IMPORT_WARNINGS)}")


# ── TravelState ─────────────────────────────────────────

class TravelState(TypedDict, total=False):
    """Shared state passed between all agent nodes.

    Each agent reads the fields it needs and writes its results.
    Only user_input is required at entry; all other fields are
    populated as the workflow progresses.
    """

    # ── Input ──
    user_input: str
    messages: List[Dict[str, str]]

    # ── Profile Agent output ──
    user_profile: Optional[Dict[str, Any]]

    # ── Trend Agent output ──
    trend_data: Optional[List[Dict[str, Any]]]

    # ── RAG Retriever output ──
    candidate_places: Optional[List[Dict[str, Any]]]

    # ── Recommendation Agent output ──
    recommendations: Optional[List[Dict[str, Any]]]

    # ── Planning Agent output ──
    itinerary: Optional[Dict[str, Any]]

    # ── External context (weather, etc.) ──
    weather: Optional[Dict[str, Any]]

    # ── Flow control ──
    current_step: str
    error: Optional[str]

    # ── Phase 8.1: Coverage / quality signals ──
    coverage_level: str          # "normal" | "low"
    coverage_warning: Optional[str]


def _append_error(state: TravelState, step: str, error: Exception) -> None:
    """Accumulate errors across nodes without overwriting prior errors."""
    prior = state.get("error")
    prefix = "; " if prior else ""
    state["error"] = f"{prior or ''}{prefix}{step}: {error}"


# ── Node Implementations ────────────────────────────────

async def _profile_extraction(state: TravelState) -> TravelState:
    """Extract structured user profile from natural language input."""
    logger.info("Orchestrator → Profile Extraction")
    state["current_step"] = "profile_extraction"

    try:
        profile = await _extract_profile(state["user_input"])
        state["user_profile"] = profile

        # Validate critical fields
        dest = (profile or {}).get("destination", "")
        if not dest or not dest.strip():
            logger.warning("Profile extracted but destination is empty — "
                           "auto-recommending based on user intent")
            # Phase 15a: recommend destination based on tags/companions/intent
            from app.agents.profile_agent import _recommend_destination
            tags = (profile or {}).get("tags", [])
            companions = (profile or {}).get("companions", "")
            constraints = (profile or {}).get("constraints", [])
            intent = (profile or {}).get("search_intent", "general")
            recs = _recommend_destination(tags, companions, constraints, intent)
            if recs:
                # Phase 5 P3.2: 不要 auto-recommend 替换空 destination
                # 设 recommended_cities 但不直接选一个填到 destination
                # 让用户选或后端根据 dialog state 决定
                profile["recommended_cities"] = recs
                profile["auto_recommended"] = False  # 不要自动选
                logger.info(f"Recommended cities (user chooses): "
                           f"{[r['city'] for r in recs[:3]]}")
                state["user_profile"] = profile
                _append_error(
                    state, "profile_extraction",
                    ValueError(
                        "未识别到具体目的地，请说明想去哪个城市。"
                        f"推荐：{[r['city'] for r in recs[:3]]}"
                    ),
                )
            else:
                _append_error(
                    state, "profile_extraction",
                    ValueError(
                        "无法识别目的地，请提供更详细的旅行需求"
                        "（例如：'想去广州玩3天'）"
                    ),
                )
        else:
            logger.info(f"Profile extracted: {dest}")
            # Phase 5 P3.2: 校验 city 是否在 KB (广州专属)
            from app.agents.dialog_manager import check_city_coverage
            covered, reason = check_city_coverage(dest)
            if not covered:
                logger.warning(f"Destination '{dest}' not in KB — refusing")
                profile["destination"] = ""
                profile["auto_recommended"] = False
                _append_error(
                    state, "profile_extraction",
                    ValueError(reason),  # 包含用户提示: "抱歉「上海」暂不在..."
                )
    except Exception as e:
        logger.error(f"Profile extraction failed: {e}")
        _append_error(state, "profile_extraction", e)
        state["user_profile"] = {}

    return state


async def _trend_analysis(state: TravelState) -> TravelState:
    """Analyze trending places for the destination city."""
    logger.info("Orchestrator → Trend Analysis")
    state["current_step"] = "trend_analysis"

    if _analyze_trends is None:
        logger.debug("Trend agent not yet implemented — skipping")
        state["trend_data"] = []
        return state

    try:
        profile = state.get("user_profile") or {}
        city = profile.get("destination", "")
        tags = profile.get("tags", [])

        trends = await _analyze_trends(city, tags)
        state["trend_data"] = trends
        logger.info(f"Trend data: {len(trends)} trending places")
    except Exception as e:
        logger.error(f"Trend analysis failed: {e}")
        state["trend_data"] = []
        _append_error(state, "trend_analysis", e)

    return state


async def _rag_retrieval(state: TravelState) -> TravelState:
    """Retrieve candidate places from the vector knowledge base.

    Phase 12.16: Passes weather forecast to the retriever for indoor/outdoor
    scoring boost — when rain is forecast, indoor POIs rank higher.

    Phase 13 (Hybrid POI Pool): After RAG retrieval, builds a hybrid POI
    pool for ALL cities using get_hybrid_poi_pool(), which fuses static KB
    data with runtime API queries. This ensures both KB cities (32 known
    cities) and non-KB cities (any city in China) get supplemented with
    real-time POI data from Wikipedia, Bing, etc.
    """
    logger.info("Orchestrator → RAG Retrieval")
    state["current_step"] = "rag_retrieval"
    state["coverage_level"] = "normal"
    state["coverage_warning"] = None

    if _retrieve is None:
        logger.debug("RAG retriever not yet implemented — skipping")
        state["candidate_places"] = []
        return state

    try:
        profile = state.get("user_profile") or {}
        query = state["user_input"]
        weather = state.get("weather")  # Phase 12.16: weather-aware RAG
        candidates = await _retrieve(profile, query, top_k=20, weather=weather)
        state["candidate_places"] = candidates
        logger.info(f"RAG retrieved {len(candidates)} candidates")

        # Phase 13: Hybrid POI pool for ALL cities (KB + runtime fusion)
        dest = profile.get("destination", "") or ""
        if dest and len(candidates) < 30:
            try:
                from app.services.runtime_poi_service import (
                    get_hybrid_poi_pool,
                )
                logger.info(
                    f"Building hybrid POI pool for '{dest}' "
                    f"(KB base + runtime supplement)"
                )
                hybrid_pool = await get_hybrid_poi_pool(
                    dest,
                    categories=["attractions", "restaurants"],
                    limit_per_category=15,
                )
                hybrid_items = (
                    hybrid_pool.get("attractions", {}).get("items", [])
                    + hybrid_pool.get("restaurants", {}).get("items", [])
                )
                if hybrid_items:
                    # Merge hybrid POIs into candidates with dedup
                    existing_names = {
                        c.get("name", "") for c in candidates
                    }
                    added = 0
                    for poi in hybrid_items:
                        name = poi.get("name", "")
                        if name and name not in existing_names:
                            poi.setdefault("metadata", {})
                            if poi.get("source") == "kb":
                                poi["kb_verified"] = True
                            else:
                                poi["kb_verified"] = False
                                poi["runtime_verified"] = True
                            candidates.append(poi)
                            existing_names.add(name)
                            added += 1
                    logger.info(
                        f"Added {added} hybrid POIs for '{dest}' "
                        f"(total candidates: {len(candidates)})"
                    )
                    state["candidate_places"] = candidates
            except Exception as e:
                logger.warning(f"Hybrid POI pool failed (non-fatal): {e}")

        # Phase 8.1: Detect low evidence — <3 candidates = degraded
        if len(candidates) < 3:
            dest = profile.get("destination", "") or "该城市"
            state["coverage_level"] = "low"
            state["coverage_warning"] = (
                f"「{dest}」数据有限，以下建议未经完全校验，仅供参考。"
            )
            logger.warning(f"Low coverage for '{dest}': {len(candidates)} candidates")
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        state["candidate_places"] = []
        _append_error(state, "rag_retrieval", e)

    return state


async def _recommendation(state: TravelState) -> TravelState:
    """Score and rank candidate places using 6-factor formula."""
    logger.info("Orchestrator → Recommendation")
    state["current_step"] = "recommendation"

    if _recommend is None:
        logger.debug("Recommendation agent not yet implemented — skipping")
        state["recommendations"] = []
        return state

    try:
        profile = state.get("user_profile") or {}
        candidates = state.get("candidate_places") or []
        trends = state.get("trend_data") or []

        if candidates:
            weather = state.get("weather")  # Phase 12.16: weather-aware scoring
            ranked = await _recommend(profile, candidates, trends, weather=weather)
            state["recommendations"] = ranked
            logger.info(f"Recommendations: top {len(ranked)} places ranked")
        else:
            logger.warning("No candidates to rank — skipping recommendation")
            state["recommendations"] = []
    except Exception as e:
        logger.error(f"Recommendation failed: {e}")
        state["recommendations"] = []
        _append_error(state, "recommendation", e)

    return state


async def _planning(state: TravelState) -> TravelState:
    """Generate a day-by-day itinerary from ranked recommendations."""
    logger.info("Orchestrator → Planning")
    state["current_step"] = "planning"

    if _generate_itinerary is None:
        logger.debug("Planning agent not yet implemented — skipping")
        state["itinerary"] = {}
        return state

    try:
        profile = state.get("user_profile") or {}
        recommendations = state.get("recommendations") or []

        if recommendations:
            # Weather-adaptive: pass the fetched forecast into planning
            itinerary = await _generate_itinerary(
                profile, recommendations, weather=state.get("weather")
            )
            state["itinerary"] = itinerary
            if not itinerary:
                # generate_itinerary 已达重试上限的结构化失败
                _append_error(state, "planning", "行程生成失败（已达重试上限）")
            elif isinstance(itinerary, dict):
                logger.info(
                    f"Itinerary: {itinerary.get('trip', {}).get('daysCount', 0)} days planned "
                    f"({len(itinerary.get('days', []))} day-entries)"
                )
        else:
            logger.warning("No recommendations to plan — skipping")
            state["itinerary"] = {}
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        state["itinerary"] = {}
        _append_error(state, "planning", e)

    return state


async def _weather_fetch(state: TravelState) -> TravelState:
    """Fetch weather forecast for the destination city (Open-Meteo)."""
    logger.info("Orchestrator → Weather Fetch")
    state["current_step"] = "weather_fetch"

    if _get_weather_forecast is None:
        logger.debug("Weather service not available — skipping")
        state["weather"] = {}
        return state

    try:
        profile = state.get("user_profile") or {}
        city = profile.get("destination", "")
        days = profile.get("days", 5)

        if city:
            forecast = await _get_weather_forecast(city, days=min(days, 7))
            state["weather"] = forecast.to_dict() if forecast else {}
            logger.info(
                f"Weather: {city} {len(forecast.daily)}d forecast "
                f"(score={forecast.overall_score:.2f})"
            )
        else:
            state["weather"] = {}
    except Exception as e:
        logger.warning(f"Weather fetch failed (non-fatal): {e}")
        state["weather"] = {}
        _append_error(state, "weather_fetch", e)

    return state


async def _response_aggregator(state: TravelState) -> TravelState:
    """Aggregate all agent results into a final response."""
    logger.info("Orchestrator → Response Aggregator")
    state["current_step"] = "done"

    # Build a human-readable summary message
    parts: List[str] = []

    profile = state.get("user_profile") or {}
    if profile:
        dest = profile.get("destination", "")
        days = profile.get("days", "")
        parts.append(f"已解析用户需求：目的地={dest}, 天数={days}")

    recommendations = state.get("recommendations") or []
    if recommendations:
        top_names = [
            r.get("name", "?") for r in recommendations[:5]
        ]
        parts.append(f"推荐景点 (Top 5): {', '.join(top_names)}")

    itinerary = state.get("itinerary") or {}
    if isinstance(itinerary, dict) and itinerary.get("plan"):
        plan_len = len(itinerary["plan"]) if isinstance(itinerary["plan"], list) else 0
        parts.append(f"行程已规划 ({plan_len} 天)")

    weather = state.get("weather") or {}
    if hasattr(weather, 'to_dict'):
        weather = weather.to_dict()
    if isinstance(weather, dict) and weather.get("advice"):
        parts.append(f"🌤️ 天气: {weather['advice']}")

    error = state.get("error")
    if error:
        parts.append(f"⚠️ 部分步骤出现问题: {error}")

    # Phase 8.1: Surface coverage warning
    coverage_warning = state.get("coverage_warning")
    if coverage_warning:
        parts.append(f"⚠️ {coverage_warning}")

    if not parts:
        parts.append("AI 规划引擎已启动，正在处理你的需求...")

    summary = "\n".join(parts)

    # Append summary as an assistant message
    messages = state.get("messages", [])
    messages.append({"role": "assistant", "content": summary})
    state["messages"] = messages

    return state


# ── Public API ──────────────────────────────────────────

async def run_travel_workflow(
    user_input: str,
    messages: Optional[List[Dict[str, str]]] = None,
) -> TravelState:
    """Run the full multi-agent travel planning workflow.

    Delegates to run_travel_workflow_stream() and consumes only the final
    result event. This keeps both code paths (blocking + streaming) in sync.

    Args:
        user_input: Natural language travel request from the user.
        messages: Optional conversation history for context.

    Returns:
        Complete TravelState with all agent outputs populated.
    """
    logger.info(f"Starting workflow for: {user_input[:80]}...")
    final_state: TravelState = {}
    async for event in run_travel_workflow_stream(user_input, messages):
        if event.get("event") == "result":
            final_state = event["data"]
    logger.info(f"Workflow complete — step: {final_state.get('current_step')}")
    return final_state


async def run_travel_workflow_stream(
    user_input: str,
    messages: Optional[List[Dict[str, str]]] = None,
):
    """Run the travel planning workflow with SSE progress events.

    Yields dict events:
      - {"event": "progress", "step": "...", "status": "running"|"done", "message": "..."}
      - {"event": "result", "data": TravelState}

    The existing run_travel_workflow() delegates to this generator and
    consumes only the final result (backward-compatible).
    """
    state: TravelState = {
        "user_input": user_input,
        "messages": list(messages) if messages else [
            {"role": "user", "content": user_input}
        ],
        "user_profile": None,
        "trend_data": None,
        "candidate_places": None,
        "recommendations": None,
        "itinerary": None,
        "weather": None,
        "current_step": "start",
        "error": None,
        "coverage_level": "normal",
        "coverage_warning": None,
    }

    logger.info(f"Starting streaming workflow for: {user_input[:80]}...")

    # ── Step 1: Profile Extraction ──
    yield {
        "event": "progress",
        "step": "profile_extraction",
        "status": "running",
        "message": "正在提取用户画像...",
    }
    state = await _profile_extraction(state)
    yield {
        "event": "progress",
        "step": "profile_extraction",
        "status": "done",
        "message": f"已识别目的地：{(state.get('user_profile') or {}).get('destination', '未知')}",
    }

    # ── Step 2+3 并行: Trend Analysis + Weather Fetch ──
    # Phase 18 D.4: 两步都依赖 profile.destination,互不依赖,并发跑省端到端时间。
    # progress event 顺序保持稳定(先 trend 再 weather),内容异步收集。
    yield {
        "event": "progress",
        "step": "trend_analysis",
        "status": "running",
        "message": "正在分析热门趋势...",
    }
    yield {
        "event": "progress",
        "step": "weather_fetch",
        "status": "running",
        "message": "正在获取天气数据...",
    }

    import asyncio
    trend_task = asyncio.create_task(_trend_analysis(state))
    weather_task = asyncio.create_task(_weather_fetch(state))
    trend_state, weather_state = await asyncio.gather(trend_task, weather_task)
    # 合并两个 state(都写了同一 state 的不同字段,合并后谁都不丢)
    state.update({k: v for k, v in weather_state.items() if k not in state or state.get(k) is None})
    state.update(trend_state)

    yield {
        "event": "progress",
        "step": "trend_analysis",
        "status": "done",
    }
    yield {
        "event": "progress",
        "step": "weather_fetch",
        "status": "done",
    }

    # ── Step 4: RAG Retrieval ──
    yield {
        "event": "progress",
        "step": "rag_retrieval",
        "status": "running",
        "message": "正在检索知识库...",
    }
    state = await _rag_retrieval(state)
    yield {
        "event": "progress",
        "step": "rag_retrieval",
        "status": "done",
        "message": f"已检索 {(state.get('candidate_places') or []).__len__()} 个候选景点",
    }

    # ── Step 5: Recommendation ──
    yield {
        "event": "progress",
        "step": "recommendation",
        "status": "running",
        "message": "正在评分和排序...",
    }
    state = await _recommendation(state)
    yield {
        "event": "progress",
        "step": "recommendation",
        "status": "done",
    }

    # ── Step 6: Planning (slowest step) ──
    yield {
        "event": "progress",
        "step": "planning",
        "status": "running",
        "message": "正在生成行程规划（约需 30-60 秒）...",
    }
    state = await _planning(state)
    yield {
        "event": "progress",
        "step": "planning",
        "status": "done",
    }

    # ── Step 7: Response Aggregator ──
    state = await _response_aggregator(state)

    logger.info(f"Streaming workflow complete — step: {state.get('current_step')}")

    yield {
        "event": "result",
        "data": state,
    }

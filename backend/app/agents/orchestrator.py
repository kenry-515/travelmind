"""
TravelMind Agent — Orchestrator
LangGraph StateGraph that coordinates all agents in sequence.

Workflow:
  START -> Profile Extraction -> Trend Analysis -> Weather Fetch
        -> RAG Retrieval -> Recommendation Agent
        -> Planning Agent -> Response Aggregator -> END

Each node reads/writes shared TravelState. Errors are captured
in state["error"] so the graph can continue with graceful degradation.
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)

# ── Lazy imports (module-level) ──────────────────────────

# langgraph is only needed when the graph is actually compiled.
_StateGraph = None
_END = None

# Agent imports — tried once at module load; None if not yet implemented.
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


def _get_langgraph():
    """Lazy-import langgraph so the module loads without it installed."""
    global _StateGraph, _END
    if _StateGraph is None:
        from langgraph.graph import END as _END_, StateGraph as _SG
        _StateGraph = _SG
        _END = _END_
    return _StateGraph, _END


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


def _append_error(state: TravelState, step: str, error: Exception) -> None:
    """Accumulate errors across nodes without overwriting prior errors."""
    prefix = "; " if state.get("error") else ""
    state["error"] = f"{state.get('error', '')}{prefix}{step}: {error}"


# ── Node Implementations ────────────────────────────────

async def _profile_extraction(state: TravelState) -> TravelState:
    """Extract structured user profile from natural language input."""
    logger.info("Orchestrator → Profile Extraction")
    state["current_step"] = "profile_extraction"

    try:
        profile = await _extract_profile(state["user_input"])
        state["user_profile"] = profile

        # Validate critical fields — short-circuit if destination is empty
        dest = (profile or {}).get("destination", "")
        if not dest or not dest.strip():
            logger.warning("Profile extracted but destination is empty — "
                           "user input may be incomplete")
            _append_error(
                state, "profile_extraction",
                ValueError(
                    "无法识别目的地，请提供更详细的旅行需求"
                    "（例如：'想去重庆玩3天'）"
                ),
            )
        else:
            logger.info(f"Profile extracted: {dest}")
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
    """Retrieve candidate places from the vector knowledge base."""
    logger.info("Orchestrator → RAG Retrieval")
    state["current_step"] = "rag_retrieval"

    if _retrieve is None:
        logger.debug("RAG retriever not yet implemented — skipping")
        state["candidate_places"] = []
        return state

    try:
        profile = state.get("user_profile") or {}
        query = state["user_input"]
        candidates = await _retrieve(profile, query, top_k=20)
        state["candidate_places"] = candidates
        logger.info(f"RAG retrieved {len(candidates)} candidates")
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
            ranked = await _recommend(profile, candidates, trends)
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
    if isinstance(weather, dict) and weather.get("advice"):
        parts.append(f"🌤️ 天气: {weather['advice']}")

    error = state.get("error")
    if error:
        parts.append(f"⚠️ 部分步骤出现问题: {error}")

    if not parts:
        parts.append("AI 规划引擎已启动，正在处理你的需求...")

    summary = "\n".join(parts)

    # Append summary as an assistant message
    messages = state.get("messages", [])
    messages.append({"role": "assistant", "content": summary})
    state["messages"] = messages

    return state


# ── Graph Builder ───────────────────────────────────────

def _build_graph():
    """Construct the LangGraph StateGraph for travel planning."""
    StateGraph, END = _get_langgraph()

    graph = StateGraph(TravelState)

    # Register nodes
    graph.add_node("profile_extraction", _profile_extraction)
    graph.add_node("trend_analysis", _trend_analysis)
    graph.add_node("weather_fetch", _weather_fetch)
    graph.add_node("rag_retrieval", _rag_retrieval)
    graph.add_node("recommendation", _recommendation)
    graph.add_node("planning", _planning)
    graph.add_node("response_aggregator", _response_aggregator)

    # Edges — linear pipeline
    graph.set_entry_point("profile_extraction")

    # Profile → Trend → Weather → RAG → Recommend → Plan → Aggregator
    graph.add_edge("profile_extraction", "trend_analysis")
    graph.add_edge("trend_analysis", "weather_fetch")
    graph.add_edge("weather_fetch", "rag_retrieval")
    graph.add_edge("rag_retrieval", "recommendation")
    graph.add_edge("recommendation", "planning")
    graph.add_edge("planning", "response_aggregator")
    # Aggregator → END
    graph.add_edge("response_aggregator", END)

    return graph


# ── Singleton ───────────────────────────────────────────

_graph = None  # compiled graph instance (lazy built)


def get_graph():
    """Get or build the singleton compiled graph (lazy construction)."""
    global _graph
    if _graph is None:
        raw_graph = _build_graph()
        _graph = raw_graph.compile()
    return _graph


# ── Public API ──────────────────────────────────────────

async def run_travel_workflow(
    user_input: str,
    messages: Optional[List[Dict[str, str]]] = None,
) -> TravelState:
    """Run the full multi-agent travel planning workflow.

    Args:
        user_input: Natural language travel request from the user.
        messages: Optional conversation history for context.

    Returns:
        Complete TravelState with all agent outputs populated.
        Nodes that fail set state["error"] but do not halt the graph.
    """
    initial_state: TravelState = {
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
    }

    compiled = get_graph()

    logger.info(f"Starting workflow for: {user_input[:80]}...")
    final_state = await compiled.ainvoke(initial_state)
    logger.info(f"Workflow complete — step: {final_state.get('current_step')}")

    return final_state

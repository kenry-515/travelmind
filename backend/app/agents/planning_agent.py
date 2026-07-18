"""
TravelMind Agent — Planning Agent

LLM-powered day-by-day itinerary generator using DeepSeek chat_structured().

Takes top-ranked recommendations + user profile → generates a structured
day-by-day travel plan with attractions, time slots, meals, and transport tips.

Usage:
    from app.agents.planning_agent import generate_itinerary
    itinerary = await generate_itinerary(profile, recommendations)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── Output Schema ─────────────────────────────────────────

ITINERARY_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "string",
            "description": "A 1-2 sentence overview of the trip plan.",
        },
        "days": {
            "type": "integer",
            "description": "Total number of days in the plan.",
        },
        "plan": {
            "type": "array",
            "description": "Day-by-day itinerary.",
            "items": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "integer",
                        "description": "Day number (1-indexed).",
                    },
                    "theme": {
                        "type": "string",
                        "description": "Theme for this day (e.g., 城市探索, 历史文化, 自然风光, 美食之旅).",
                    },
                    "attractions": {
                        "type": "array",
                        "description": "Attractions to visit this day (3-5 recommended).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "time": {
                                    "type": "string",
                                    "description": "Suggested time slot (e.g., 09:00-11:00).",
                                },
                                "duration_min": {
                                    "type": "integer",
                                    "description": "Estimated visit duration in minutes.",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Tips for visiting (crowd avoidance, ticket info, photo spots).",
                                },
                            },
                            "required": ["name", "time", "duration_min", "notes"],
                            "additionalProperties": False,
                        },
                        "minItems": 2,
                        "maxItems": 6,
                    },
                    "meals": {
                        "type": "array",
                        "description": "Meal suggestions for the day.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["早餐", "午餐", "晚餐", "小吃"],
                                },
                                "suggestion": {"type": "string"},
                            },
                            "required": ["type", "suggestion"],
                            "additionalProperties": False,
                        },
                        "maxItems": 4,
                    },
                    "transport_tips": {
                        "type": "string",
                        "description": "Transport suggestion for this day.",
                    },
                },
                "required": ["day", "theme", "attractions", "meals", "transport_tips"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 14,
        },
        "general_tips": {
            "type": "string",
            "description": "General travel tips for the trip (weather, clothing, booking advice).",
        },
    },
    "required": ["overview", "days", "plan", "general_tips"],
    "additionalProperties": False,
}


# ── Helpers ──────────────────────────────────────────────


def _build_planning_prompt(profile: Dict[str, Any], places: List[Dict[str, Any]]) -> str:
    """Build a detailed prompt for the itinerary planning LLM call."""
    dest = profile.get("destination", "未知城市")
    days = profile.get("days", 3)
    budget = profile.get("budget_level", "") or profile.get("budget", "") or "中等"
    tags = profile.get("tags", []) or []
    companions = profile.get("companions", "") or "独自"
    style = profile.get("travel_style", "") or "休闲"
    constraints = profile.get("constraints", "") or "无特殊要求"

    # Build the list of recommended places with details
    place_lines = []
    for i, p in enumerate(places[:15]):  # top 15 for planning
        name = p.get("name", p.get("metadata", {}).get("name", f"景点{i+1}"))
        score = p.get("total_score", p.get("relevance_score", 0))
        tags_p = p.get("tags", []) or p.get("metadata", {}).get("tags", "")
        if isinstance(tags_p, str):
            tags_p = [t.strip() for t in tags_p.split(",") if t.strip()]
        suitable = p.get("suitable_for", "") or p.get("metadata", {}).get("suitable_for", "")
        best_time = p.get("best_time", "") or p.get("metadata", {}).get("best_time", "")
        price = p.get("price_level", "") or p.get("metadata", {}).get("price_level", "")

        place_lines.append(
            f"{i + 1}. {name} "
            f"(标签: {', '.join(tags_p[:5])}; "
            f"适合: {suitable}; "
            f"最佳时间: {best_time}; "
            f"价格: {price}; "
            f"推荐分: {score:.2f})"
        )

    prompt = f"""请为以下旅行需求生成一份详细的 {days} 日行程规划：

【目的地】{dest}
【天数】{days} 天
【预算】{budget}
【同行人员】{companions}
【兴趣标签】{', '.join(tags) if tags else '不限'}
【旅行风格】{style}
【特殊要求】{constraints}

【推荐景点】（按推荐度排序，请从中选取合适的景点安排行程）
{chr(10).join(place_lines)}

【规划要求】
1. 每天安排 3-5 个景点，考虑地理位置就近原则，避免来回奔波
2. 每个景点给出建议游览时段和时长
3. 每天推荐早/午/晚餐（考虑当地特色美食）
4. 给出每天的交通建议
5. 考虑景点开放时间和最佳游览时间
6. 行程张弛有度，避免过于紧凑
7. 如果有特殊同行人员（老人、小孩），考虑体力因素"""

    return prompt


def _get_llm_client() -> AsyncOpenAI:
    """Create a DeepSeek AsyncOpenAI client from settings."""
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=90.0,
        max_retries=1,
    )


# ── Main API ─────────────────────────────────────────────


async def generate_itinerary(
    profile: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate a day-by-day itinerary from ranked recommendations.

    Args:
        profile: User profile dict (destination, days, tags, budget, etc.).
        recommendations: Ranked list of attractions (from recommendation_agent).

    Returns:
        Dict with keys: overview, days, plan (list of day objects),
        general_tips. Empty dict on failure.
    """
    if not recommendations:
        logger.warning("No recommendations to plan — returning empty itinerary")
        return {}

    if not settings.DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not configured — cannot generate itinerary")
        return {}

    # Take top-N for planning (enough variety, not overwhelming)
    top_n = min(len(recommendations), 20)
    places = recommendations[:top_n]
    days = profile.get("days", 3)

    prompt = _build_planning_prompt(profile, places)

    system_prompt = f"""你是 TravelMind 高级旅行规划师。你的任务是根据用户需求和推荐景点，
生成一份专业、可执行的 {days} 日旅行行程。

行程要符合以下标准：
- 景点顺序合理，考虑地理邻近性
- 时间安排恰当，预留通勤和用餐时间
- 每天有一个主题，内容丰富但不赶
- 餐饮推荐体现当地特色
- 交通建议实用

你必须调用 'output' 函数返回结构化结果。不要返回纯文本。"""

    itinerary = None
    last_error = None

    for attempt in range(2):  # retry once on empty/failure
        try:
            client = _get_llm_client()

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            tools = [{
                "type": "function",
                "function": {
                    "name": "output",
                    "description": f"Return the {days}-day itinerary as structured JSON.",
                    "parameters": ITINERARY_SCHEMA,
                },
            }]

            logger.info(
                f"Planning itinerary: {days}d from {len(places)} places"
                + (f" (attempt {attempt + 1})" if attempt > 0 else "")
            )
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,  # type: ignore
                temperature=0.5,
                tools=tools,  # type: ignore
                tool_choice={"type": "function", "function": {"name": "output"}},
            )

            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and tool_calls[0].function.arguments:
                itinerary = json.loads(tool_calls[0].function.arguments)
                if itinerary.get("plan"):
                    logger.info(
                        f"Itinerary generated: {itinerary.get('days', 0)} days, "
                        f"{len(itinerary.get('plan', []))} day-entries"
                    )
                    return itinerary
                logger.warning("Itinerary has no plan — retrying")

            # Fallback: try content
            content = response.choices[0].message.content
            if content:
                try:
                    parsed = json.loads(content)
                    if parsed.get("plan"):
                        return parsed
                except json.JSONDecodeError:
                    pass

            logger.warning(f"Empty itinerary response (attempt {attempt + 1})")

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
        except Exception as e:
            last_error = e
            logger.warning(f"Itinerary generation error (attempt {attempt + 1}): {e}")

    if last_error:
        logger.error(f"Itinerary generation failed after retries: {last_error}")
    else:
        logger.error("Itinerary generation failed: empty response after retries")
    return {}

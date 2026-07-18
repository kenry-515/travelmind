"""
TravelMind Agent — Profile Agent
Extracts a structured user profile from natural language travel requests.

Uses DeepSeek chat_structured() to parse user intent into JSON with fields:
  destination, budget_level, days, companions, tags, travel_style, constraints.
"""

import logging
from typing import Any, Dict

from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

# ── Output Schema for chat_structured() ──────────────────

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "destination": {
            "type": "string",
            "description": "Primary destination city or region in Chinese, e.g. '重庆' or '成都'",
        },
        "secondary_destinations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Other cities or areas mentioned",
        },
        "budget_level": {
            "type": "string",
            "enum": ["经济", "舒适", "奢华", "不限"],
            "description": "Budget preference level",
        },
        "days": {
            "type": "integer",
            "description": "Number of travel days (estimate from context if not explicit, default 3)",
        },
        "companions": {
            "type": "string",
            "enum": ["独自", "情侣", "朋友", "亲子", "家庭", "不限"],
            "description": "Travel companion type",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Interest tags from: 美食, 历史, 摄影, 自然, 购物, 亲子, 情侣, "
                "夜生活, 小众, 文艺, 探险, 休闲, 网红打卡, 博物馆, 古镇, 温泉, "
                "滑雪, 海岛, 爬山, 寺庙, 日出, 日落, 赏花, 红叶, 演出"
            ),
        },
        "travel_style": {
            "type": "string",
            "enum": ["休闲", "特种兵", "深度", "打卡", "不限"],
            "description": "Travel pace and style",
        },
        "constraints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Special constraints or requirements, e.g. '老人同行需少走路', '需无障碍设施'",
        },
        "preferred_months": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Preferred travel months mentioned, e.g. ['3月', '4月']",
        },
        "departure_city": {
            "type": "string",
            "description": "Departure city if mentioned, e.g. '广州'",
        },
    },
    "required": ["destination", "days", "tags"],
}


# ── System Prompt ───────────────────────────────────────

PROFILE_SYSTEM_PROMPT = """你是一个旅行需求分析专家。你的任务是从用户的自然语言中提取结构化的旅行偏好信息。

规则：
1. 如果用户没有明确提到某个字段，使用合理的默认值或 null
2. destination 必须提取；如果有歧义，选择最可能的城市
3. tags 从用户提到的兴趣和偏好中推断；每个用户至少提取 2 个标签
4. budget_level 从关键词推断：'穷游'/'便宜'→经济，'奢侈'/'五星'→奢华，默认→舒适
5. days 从上下文推断；无法确定时填 3
6. companions 从关键词推断；没有提到填 '不限'
7. travel_style 从上下文推断；没有提到填 '不限'

只输出 JSON，不要输出其他内容。"""


# ── Allowed tags (must match schema description) ────────────

VALID_TAGS = {
    "美食", "历史", "摄影", "自然", "购物", "亲子", "情侣",
    "夜生活", "小众", "文艺", "探险", "休闲", "网红打卡", "博物馆", "古镇", "温泉",
    "滑雪", "海岛", "爬山", "寺庙", "日出", "日落", "赏花", "红叶", "演出",
}

# ── Post-processing ──────────────────────────────────────

def _clean_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize LLM output — fix null strings, null arrays, empty values."""
    # Convert "null" / "None" / "none" strings to actual None for optional string fields
    nullable_str_fields = {"departure_city"}
    for key in nullable_str_fields:
        val = profile.get(key)
        if isinstance(val, str) and val.lower() in ("null", "none", ""):
            profile[key] = None

    # Convert null arrays to empty list
    array_fields = {
        "tags", "secondary_destinations", "constraints", "preferred_months"
    }
    for key in array_fields:
        if profile.get(key) is None:
            profile[key] = []

    # Ensure tags are non-empty (minimum 2 tags for downstream matching)
    tags = profile.get("tags", [])
    if not tags:
        profile["tags"] = ["旅行"]
    # Filter unknown tags and log warnings
    filtered_tags = [t for t in tags if t in VALID_TAGS]
    if len(filtered_tags) != len(tags):
        removed = set(tags) - set(filtered_tags)
        logger.warning(f"Removed unknown tags: {removed}")
    profile["tags"] = filtered_tags
    if not profile["tags"]:
        profile["tags"] = ["旅行"]

    # Ensure days has a default (schema requires it, but LLM may omit on edge cases)
    if profile.get("days") is None:
        profile["days"] = 3

    return profile


# ── Public API ──────────────────────────────────────────

async def extract_profile(user_input: str) -> Dict[str, Any]:
    """Extract a structured user profile from natural language input.

    Args:
        user_input: Natural language travel request, e.g.
            "想带5岁孩子去成都玩3天，预算中等，喜欢美食和熊猫"

    Returns:
        Dict with fields: destination, budget_level, days, companions,
        tags, travel_style, constraints, secondary_destinations,
        preferred_months, departure_city.
        Returns empty dict on failure.
    """
    llm = get_llm_provider()

    messages = [
        {
            "role": "user",
            "content": f"用户输入：{user_input}\n\n请提取结构化的旅行需求信息。",
        }
    ]

    try:
        result = await llm.chat_structured(
            messages=messages,
            output_schema=PROFILE_SCHEMA,
            system_prompt=PROFILE_SYSTEM_PROMPT,
            temperature=0.3,
        )
        result = _clean_profile(result)
        logger.info(f"Profile extracted: dest={result.get('destination')}, "
                     f"tags={result.get('tags')}")
        return result

    except Exception as e:
        logger.error(f"Profile extraction failed: {e}")
        # Return a minimal profile on failure so downstream agents can still try.
        # IMPORTANT: pass through _clean_profile so all fields are normalized.
        return _clean_profile({
            "destination": "",
            "budget_level": "舒适",
            "days": 3,
            "companions": "不限",
            "tags": [],
            "travel_style": "不限",
            "constraints": [],
        })

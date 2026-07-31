"""
TravelMind Agent — Profile Agent
Extracts a structured user profile from natural language travel requests.

Uses DeepSeek chat_structured() to parse user intent into JSON with fields:
  destination, budget_level, days, companions, tags, travel_style, constraints.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

# Phase 12.10: City alias resolver for normalizing non-standard destinations
_resolve_city_alias = None

# Phase 4.1: Dynamically load valid tags from tags.json
def _load_valid_tags() -> set:
    """Load valid tags from tags.json with fallback to hardcoded defaults."""
    try:
        tags_path = Path(__file__).parent.parent.parent / "data" / "tags.json"
        if tags_path.exists():
            with open(tags_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("all_tags", []))
    except Exception as e:
        logger.warning(f"Failed to load tags.json: {e}")
    
    # Fallback to defaults
    return {
        "美食", "历史", "摄影", "自然", "购物", "亲子", "情侣",
        "夜生活", "小众", "文艺", "探险", "休闲", "网红打卡", "博物馆", "古镇", "温泉",
        "滑雪", "海岛", "爬山", "寺庙", "日出", "日落", "赏花", "红叶", "演出",
        "文化", "海滩", "海边", "小吃", "火锅", "登山", "观景"
    }


# VALID_TAGS is now dynamically loaded from tags.json
VALID_TAGS = _load_valid_tags()
logger.info(f"Loaded {len(VALID_TAGS)} valid tags from tags.json")


def _get_city_alias_resolver():
    """Lazy-load the city alias resolver to avoid circular imports."""
    global _resolve_city_alias
    if _resolve_city_alias is None:
        try:
            from app.services.weather_service import resolve_city_alias
            _resolve_city_alias = resolve_city_alias
        except ImportError:
            _resolve_city_alias = lambda c: None  # noqa: E731
    return _resolve_city_alias

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
        "search_intent": {
            "type": "string",
            "enum": ["food", "nature", "history", "shopping", "general"],
            "description": (
                "Inferred primary search intent from user input. "
                "Detect from keywords: food/美食/吃→food, "
                "nature/山/海/自然/户外→nature, history/博物馆/古/文化→history, "
                "shopping/购物/打卡/网红→shopping. Default: general."
            ),
        },
        "arrival_time": {
            "type": "string",
            "description": (
                "When the user arrives at the destination, extracted from context. "
                "E.g. '周五下午2点', '周六早上8点到', '明天中午到'. "
                "If user mentions flight/train arrival time, use that. "
                "If not mentioned, leave empty string."
            ),
        },
        "departure_time": {
            "type": "string",
            "description": (
                "When the user leaves the destination / goes home. "
                "E.g. '周日上午11点走', '周日晚上飞机', '周一早上退房'. "
                "If not mentioned, leave empty string."
            ),
        },
        "must_visit": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Specific places/attractions/restaurants the user explicitly mentioned "
                "they want to visit. E.g. '洪崖洞', '解放碑', '磁器口'. "
                "Extract these naturally — if user says '想去洪崖洞看看', "
                "that means they want to visit it. Even casual mentions like "
                "'听说洪崖洞不错' count as must_visit. "
                "If the user doesn't name any specific place, leave empty array."
            ),
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
8. must_visit：用户提到的具体地名/景点名/餐厅名都算，即使只是顺便一提。用户只给了目的地没给具体地方就留空数组。
9. arrival_time：用户提到的到达时间，没提就留空
10. departure_time：用户提到的离开时间，没提就留空

只输出 JSON，不要输出其他内容。"""

# ── Note: VALID_TAGS is now dynamically loaded from tags.json at module top ───

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

    # Phase 14: 归一化 must_visit
    must_visit = profile.get("must_visit", [])
    if must_visit is None or not isinstance(must_visit, list):
        profile["must_visit"] = []
    else:
        profile["must_visit"] = [p.strip() for p in must_visit if isinstance(p, str) and p.strip()]

    # Phase 14: 归一化 arrival_time / departure_time
    for key in ("arrival_time", "departure_time"):
        val = profile.get(key)
        if not isinstance(val, str) or not val.strip():
            profile[key] = ""
        else:
            profile[key] = val.strip()

    # Phase 12.2: Ensure search_intent is populated — infer from tags + user input
    if not profile.get("search_intent") or profile.get("search_intent") == "general":
        profile["search_intent"] = _infer_search_intent(
            profile.get("tags", []),
            profile.get("constraints", []),
        )

    # Phase 13: 特殊查询 → 映射到支持的城市
    _SPECIAL_QUERIES = {
        "极光": "哈尔滨", "北极光": "哈尔滨", "漠河": "哈尔滨",
        "河西走廊": "兰州", "敦煌": "兰州", "青海湖": "成都",
        "川西": "成都", "香格里拉": "香格里拉",
        "西陲": "喀什", "最西端": "喀什", "帕米尔": "喀什", "南疆": "喀什",
        "喀什": "喀什", "新疆": "喀什",
        "兰州": "兰州", "甘南": "兰州",
        "边境": "哈尔滨", "骑行": "成都",
    }
    dest = profile.get("destination", "")
    if dest:
        for keyword, mapped in _SPECIAL_QUERIES.items():
            if keyword in dest:
                logger.info(f"Special query '{dest}' mapped to '{mapped}'")
                profile["original_destination"] = dest
                profile["destination"] = mapped
                break

    # Phase 12.10: Normalize non-standard destinations to nearest KB city.
    dest = profile.get("destination", "")
    if dest:
        resolver = _get_city_alias_resolver()
        canonical = resolver(dest)
        if canonical and canonical != dest:
            logger.info(
                f"City alias: '{dest}' → '{canonical}' (weather/POI base)"
            )
            profile["original_destination"] = dest
            profile["destination"] = canonical
            # Also add canonical as secondary if not already present
            sec = profile.get("secondary_destinations") or []
            if canonical not in sec:
                sec.append(canonical)
                profile["secondary_destinations"] = sec

    return profile


# ── Search intent inference ────────────────────────────────

_FOOD_INTENT_KW = {"美食", "火锅", "小吃", "烧烤", "海鲜", "早茶", "川菜", "粤菜",
                   "面食", "夜市", "自助", "甜品", "奶茶", "咖啡", "吃"}
_NATURE_INTENT_KW = {"自然", "爬山", "湖泊", "森林", "海岛", "海滩", "瀑布", "峡谷",
                     "日出", "日落", "草原", "雪山", "温泉", "赏花", "红叶"}
_HISTORY_INTENT_KW = {"历史", "博物馆", "古镇", "寺庙", "古迹", "园林", "建筑", "文化", "传统"}
_SHOPPING_INTENT_KW = {"购物", "打卡", "网红打卡", "城市", "文艺", "夜生活", "酒吧"}


def _infer_search_intent(
    tags: List[str],
    constraints: List[str] = None,
) -> str:
    """Infer primary search intent from user tags and constraints.

    Returns one of: food, nature, history, shopping, general.
    """
    tag_set = {t for t in tags}
    scores = {"food": 0, "nature": 0, "history": 0, "shopping": 0}

    for tag in tag_set:
        if tag in _FOOD_INTENT_KW:
            scores["food"] += 2
        if tag in _NATURE_INTENT_KW:
            scores["nature"] += 2
        if tag in _HISTORY_INTENT_KW:
            scores["history"] += 2
        if tag in _SHOPPING_INTENT_KW:
            scores["shopping"] += 2

    # Also check constraints for intent keywords
    if constraints:
        constraint_text = " ".join(str(c) for c in constraints)
        for kw in _FOOD_INTENT_KW:
            if kw in constraint_text:
                scores["food"] += 1
        for kw in _NATURE_INTENT_KW:
            if kw in constraint_text:
                scores["nature"] += 1
        for kw in _HISTORY_INTENT_KW:
            if kw in constraint_text:
                scores["history"] += 1
        for kw in _SHOPPING_INTENT_KW:
            if kw in constraint_text:
                scores["shopping"] += 1

    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        logger.debug(f"Inferred search_intent={best} from tags={tags}, scores={scores}")
        return best
    return "general"


# ── Destination Recommendation（Phase 15a）─────────────────
# 当用户没有明确说目的地时，根据意图推荐合适的城市。

_DEST_RULES: List[tuple[set[str], str, list[str]]] = []


def _build_dest_rules() -> list[tuple[set[str], str, list[str]]]:
    """Build destination recommendation rules lazily."""
    if _DEST_RULES:
        return _DEST_RULES

    rules: list[tuple[set[str], str, list[str]]] = [
        # (trigger_keywords, reasoning_label, recommended_cities)
        ({"安静", "放空", "发呆", "放松", "悠闲", "慢生活"}, "放松慢生活",
         ["大理", "丽江", "厦门", "苏州", "杭州"]),
        ({"老人", "父母", "长辈", "奶奶", "爷爷", "外婆", "外公"}, "适合长辈的轻松旅行",
         ["三亚", "杭州", "苏州", "桂林", "南京"]),
        ({"小孩", "孩子", "宝宝", "亲子", "乐园", "动物园"}, "适合亲子游",
         ["三亚", "成都", "广州", "杭州", "上海"]),
        ({"家庭", "全家", "一起"}, "适合全家出游",
         ["三亚", "杭州", "成都", "厦门", "苏州"]),
        ({"情侣", "浪漫", "蜜月", "二人"}, "浪漫之旅",
         ["厦门", "大理", "三亚", "丽江", "杭州"]),
        ({"冒险", "刺激", "挑战", "探险"}, "冒险之旅",
         ["重庆", "张家界", "西安", "黄山", "桂林"]),
        ({"美食", "火锅", "小吃", "烧烤", "吃"}, "美食之旅",
         ["成都", "重庆", "广州", "长沙", "西安"]),
        ({"自然", "风景", "摄影", "山", "湖", "海", "户外"}, "自然风光",
         ["桂林", "张家界", "黄山", "香格里拉", "大理", "三亚"]),
        ({"历史", "文化", "博物馆", "古迹", "古"}, "历史文化之旅",
         ["北京", "西安", "南京", "洛阳", "成都"]),
        ({"夜生活", "酒吧", "夜市", "不夜城"}, "夜生活丰富",
         ["重庆", "成都", "长沙", "上海", "广州"]),
        ({"文艺", "小清新", "拍照", "打卡"}, "文艺打卡",
         ["厦门", "大理", "丽江", "苏州", "杭州"]),
        ({"滑雪"}, "滑雪胜地",
         ["哈尔滨"]),
        ({"温泉"}, "温泉休养",
         ["南京", "福州", "重庆"]),
        ({"海岛", "海滩", "度假", "游泳"}, "海岛度假",
         ["三亚", "厦门", "青岛", "大连"]),
    ]
    _DEST_RULES.extend(rules)
    return _DEST_RULES


def _recommend_destination(
    tags: list[str],
    companions: str = "",
    constraints: Optional[list[str]] = None,
    search_intent: str = "general",
) -> list[dict[str, str]]:
    """根据用户画像推荐目的地。

    Returns:
        list of {city, reason} 按匹配度排序。
    """
    keywords = set(t.lower() for t in tags if isinstance(t, str))
    keywords.add(companions.lower())
    if constraints:
        for c in constraints:
            for w in c.split():
                keywords.add(w.lower())

    # Score each rule
    from collections import Counter
    scores: Counter[str] = Counter()
    reasons: dict[str, str] = {}

    rules = _build_dest_rules()
    for trigger_set, label, cities in rules:
        matches = keywords & trigger_set
        if matches:
            for city in cities:
                scores[city] += len(matches)
                if city not in reasons:
                    reasons[city] = label

    # Intent-based boost
    intent_cities = {
        "food": ["成都", "重庆", "广州", "长沙", "西安"],
        "nature": ["桂林", "张家界", "黄山", "香格里拉", "大理", "三亚"],
        "history": ["北京", "西安", "南京", "成都", "洛阳"],
        "shopping": ["上海", "广州", "成都", "重庆", "杭州"],
    }
    for city in intent_cities.get(search_intent, []):
        scores[city] += 1
        if city not in reasons:
            reasons[city] = f"{search_intent}主题推荐"

    # If nothing matched, use hot general cities
    if not scores:
        for city in ["成都", "重庆", "北京", "杭州", "西安", "厦门", "大理", "三亚"]:
            scores[city] = 1
            reasons[city] = "热门旅游城市推荐"

    # Sort by score descending
    sorted_cities = sorted(scores.keys(), key=lambda c: (-scores[c], c))
    return [
        {"city": c, "reason": reasons.get(c, "推荐目的地")}
        for c in sorted_cities[:5]
    ]


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
    llm = await get_llm_provider()

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

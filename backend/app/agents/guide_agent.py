"""
TravelMind Agent — Guide Agent (AI虚拟导游)

Provides an immersive AI tour guide experience for specific POIs.
Unlike the general chat agent, this module:

1. Looks up detailed POI information from the knowledge base
2. Generates a rich, first-person tour guide narration
3. Supports follow-up Q&A in the context of the current "tour stop"
4. Includes practical info: photo spots, nearby food, tips

Designed for the Guangdong AI Agent Competition — "AI+旅游休闲" track,
specifically the "AI虚拟导游" theme.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

# ── Data path ────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_ATTRACTIONS_FILE = _DATA_DIR / "attractions.json"
_ATTRACTIONS_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_attractions() -> List[Dict[str, Any]]:
    """Load attractions from JSON, caching in memory."""
    global _ATTRACTIONS_CACHE
    if _ATTRACTIONS_CACHE is not None:
        return _ATTRACTIONS_CACHE
    try:
        with open(_ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
            _ATTRACTIONS_CACHE = json.load(f).get("attractions", [])
    except Exception as e:
        logger.warning(f"Failed to load attractions.json: {e}")
        _ATTRACTIONS_CACHE = []
    return _ATTRACTIONS_CACHE


def find_poi(name: str, city: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a POI by name (fuzzy match), optionally filtered by city.

    Tries exact match first, then contains-match, then reverse contains.
    Returns the first match or None.
    """
    attractions = _load_attractions()
    name_lower = name.strip().lower()

    # 1. Exact match (case-insensitive)
    for a in attractions:
        if city and a.get("city") != city:
            continue
        if a.get("name", "").strip().lower() == name_lower:
            return a

    # 2. Input contains POI name
    for a in attractions:
        if city and a.get("city") != city:
            continue
        poi_name = a.get("name", "").strip().lower()
        if poi_name and poi_name in name_lower:
            return a

    # 3. POI name contains input
    for a in attractions:
        if city and a.get("city") != city:
            continue
        poi_name = a.get("name", "").strip().lower()
        if poi_name and name_lower in poi_name:
            return a

    return None


# ── Guide narration system prompt ────────────────────────

GUIDE_NARRATION_PROMPT = """你是一位专业的广州本地导游，正在带领游客参观景点。
请根据提供的景点信息，生成一段生动、有温度的导游讲解词。

讲解要求：
1. 用第一人称"我"来讲述，像真实的导游在身边讲解
2. 开头用热情的问候引入景点，例如："欢迎来到XXX！我是你的AI导游，今天让我带你走进..."
3. 内容要涵盖：历史背景、建筑特色、文化内涵、游览亮点
4. 穿插1-2个有趣的小故事或冷知识，增加趣味性
5. 推荐最佳拍照机位（具体到位置和角度）
6. 提醒游览注意事项（如开放时间、预约要求、穿着建议等）
7. 结尾推荐周边值得顺路游览的景点或美食
8. 语气亲切自然，像朋友聊天，不要太官方
9. 长度控制在400-600字，分段清晰，用emoji点缀增加可读性

【重要】只讲解给定景点的信息，不要编造不存在的内容。如果信息不足，诚实说明。"""

GUIDE_CHAT_PROMPT = """你是一位专业的广州本地导游，正在陪同游客参观景点。
游客会就当前景点提出问题，请以导游的身份自然地回答。

回答要求：
1. 保持导游的专业性和亲和力
2. 回答要具体、实用，避免空泛
3. 如果游客问的是其他景点或非景点问题，可以简短回答并引导回到当前景点
4. 如果不确定某些信息，诚实说明，不要编造
5. 回答控制在2-4句话，简洁有力
6. 可以适当加入本地人的视角和建议"""


# ── Public API ───────────────────────────────────────────

async def generate_guide_narration(
    poi_name: str,
    city: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a guided tour narration for a specific POI.

    Args:
        poi_name: Name of the POI to narrate.
        city: Optional city filter for disambiguation.

    Returns:
        Dict with:
          - poi: POI basic info (name, address, tags, etc.)
          - narration: The generated guide narration text.
          - practical: Practical info (price, hours, tips).
          - nearby: Nearby POIs worth visiting.
    """
    poi = find_poi(poi_name, city)
    if not poi:
        return {
            "found": False,
            "message": f"未找到景点「{poi_name}」，请确认名称是否正确。",
        }

    # Build context from POI data
    poi_context = _build_poi_context(poi)

    # Generate narration via LLM
    messages = [
        {"role": "system", "content": GUIDE_NARRATION_PROMPT},
        {"role": "system", "content": f"【景点信息】\n{poi_context}"},
        {"role": "user", "content": f"请为我讲解「{poi['name']}」这个景点。"},
    ]

    narration = ""
    try:
        provider = await get_llm_provider()
        narration = await provider.chat(
            messages=messages,
            temperature=0.8,
            max_tokens=800,
        )
        if narration:
            narration = narration.strip()
    except Exception as e:
        logger.warning(f"Guide narration LLM call failed: {e}")
        narration = _fallback_narration(poi)

    # Find nearby POIs (same city, different name)
    nearby = _find_nearby_pois(poi, limit=4)

    return {
        "found": True,
        "poi": {
            "name": poi.get("name", ""),
            "name_en": poi.get("name_en", ""),
            "city": poi.get("city", ""),
            "address": poi.get("address", ""),
            "tags": poi.get("tags", []),
            "lat": poi.get("lat"),
            "lon": poi.get("lon"),
            "description": poi.get("description", ""),
            "thumbnail_url": poi.get("amap_photo_url"),
            "price_level": poi.get("price_level", ""),
            "price_range": poi.get("price_range", {}),
            "best_time": poi.get("best_time", ""),
            "suitable_for": poi.get("suitable_for", ""),
            "popularity_score": poi.get("popularity_score", 0),
        },
        "narration": narration,
        "practical": {
            "price_level": poi.get("price_level", "未知"),
            "price_range": poi.get("price_range", {}),
            "address": poi.get("address", "未知"),
            "best_time": poi.get("best_time", "全年"),
            "suitable_for": poi.get("suitable_for", "所有人群"),
        },
        "nearby": nearby,
    }


async def guide_chat(
    poi_name: str,
    user_question: str,
    city: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Answer a follow-up question about a POI in guide mode.

    Args:
        poi_name: Name of the POI being toured.
        user_question: The visitor's question.
        city: Optional city filter.
        history: Optional conversation history.

    Returns:
        Guide-style response string.
    """
    poi = find_poi(poi_name, city)
    if not poi:
        return f"抱歉，我没有找到「{poi_name}」的相关信息，请确认景点名称。"

    poi_context = _build_poi_context(poi)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": GUIDE_CHAT_PROMPT},
        {"role": "system", "content": f"【当前景点：{poi['name']}】\n{poi_context}"},
    ]

    if history:
        messages.extend(history[-10:])

    messages.append({"role": "user", "content": user_question})

    try:
        provider = await get_llm_provider()
        reply = await provider.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        if reply and len(reply.strip()) >= 5:
            return reply.strip()
    except Exception as e:
        logger.warning(f"Guide chat LLM call failed: {e}")

    return f"这个问题我不太确定，建议你到{poi.get('name', '该景点')}的官方渠道查询最新信息。"


def search_pois_for_guide(
    query: str,
    city: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search POIs for the guide page search box.

    Returns simplified POI info for display.
    """
    attractions = _load_attractions()
    query_lower = query.strip().lower()
    results = []

    for a in attractions:
        if city and a.get("city") != city:
            continue
        name = a.get("name", "")
        tags = a.get("tags", [])
        tag_str = " ".join(tags) if isinstance(tags, list) else str(tags)
        searchable = f"{name} {tag_str} {a.get('description', '')}".lower()

        if query_lower in searchable or any(
            query_lower in str(t).lower() for t in tags
        ):
            results.append({
                "name": name,
                "city": a.get("city", ""),
                "tags": tags if isinstance(tags, list) else [],
                "price_level": a.get("price_level", ""),
                "popularity_score": a.get("popularity_score", 0),
                "address": a.get("address", ""),
            })
            if len(results) >= limit:
                break

    return results


def get_featured_pois(city: str = "广州", limit: int = 8) -> List[Dict[str, Any]]:
    """Get featured POIs for the guide homepage, prioritizing Guangzhou landmarks."""
    attractions = _load_attractions()

    # Priority landmarks for Guangzhou (competition focus)
    gz_priority = [
        "广州塔", "永庆坊", "陈家祠", "沙面", "西汉南越王博物馆",
        "越秀公园", "白云山", "上下九步行街", "北京路步行街",
        "珠江夜游", "花城广场", "光孝寺", "岭南印象园", "正佳广场",
    ]

    city_pois = [a for a in attractions if a.get("city") == city]

    # Sort: priority landmarks first, then by popularity
    def _sort_key(p: Dict[str, Any]) -> tuple:
        name = p.get("name", "")
        priority_idx = (
            min(i for i, n in enumerate(gz_priority) if n in name)
            if any(n in name for n in gz_priority)
            else 99
        )
        return (priority_idx, -p.get("popularity_score", 0))

    city_pois.sort(key=_sort_key)

    return [
        {
            "name": p.get("name", ""),
            "tags": p.get("tags", []) if isinstance(p.get("tags"), list) else [],
            "price_level": p.get("price_level", ""),
            "popularity_score": p.get("popularity_score", 0),
            "address": p.get("address", ""),
            "thumbnail_url": p.get("amap_photo_url"),
        }
        for p in city_pois[:limit]
    ]


# ── Private helpers ──────────────────────────────────────

def _build_poi_context(poi: Dict[str, Any]) -> str:
    """Build a text context from POI data for LLM consumption."""
    parts = []
    parts.append(f"景点名称: {poi.get('name', '未知')}")
    if poi.get("name_en"):
        parts.append(f"英文名: {poi['name_en']}")
    parts.append(f"城市: {poi.get('city', '未知')}")
    if poi.get("address"):
        parts.append(f"地址: {poi['address']}")
    if poi.get("description"):
        parts.append(f"简介: {poi['description']}")
    tags = poi.get("tags", [])
    if tags:
        tag_str = "、".join(tags) if isinstance(tags, list) else str(tags)
        parts.append(f"标签: {tag_str}")
    if poi.get("best_time"):
        parts.append(f"最佳游览时间: {poi['best_time']}")
    if poi.get("price_level"):
        parts.append(f"价格级别: {poi['price_level']}")
    price_range = poi.get("price_range", {})
    if price_range and price_range.get("min") is not None:
        parts.append(f"门票价格: {price_range['min']}-{price_range.get('max', price_range['min'])}元")
    if poi.get("suitable_for"):
        parts.append(f"适合人群: {poi['suitable_for']}")
    return "\n".join(parts)


def _find_nearby_pois(poi: Dict[str, Any], limit: int = 4) -> List[Dict[str, Any]]:
    """Find nearby POIs in the same city, sorted by distance."""
    city = poi.get("city", "")
    lat = poi.get("lat")
    lon = poi.get("lon")
    name = poi.get("name", "")

    attractions = _load_attractions()
    candidates = [
        a for a in attractions
        if a.get("city") == city and a.get("name") != name
    ]

    # If coordinates available, sort by distance
    if lat is not None and lon is not None:
        def _distance(a: Dict[str, Any]) -> float:
            a_lat = a.get("lat")
            a_lon = a.get("lon")
            if a_lat is None or a_lon is None:
                return 999.0
            return ((a_lat - lat) ** 2 + (a_lon - lon) ** 2) ** 0.5
        candidates.sort(key=_distance)
    else:
        # Fallback: sort by popularity
        candidates.sort(key=lambda a: -a.get("popularity_score", 0))

    return [
        {
            "name": a.get("name", ""),
            "tags": a.get("tags", []) if isinstance(a.get("tags"), list) else [],
            "price_level": a.get("price_level", ""),
            "address": a.get("address", ""),
        }
        for a in candidates[:limit]
    ]


def _fallback_narration(poi: Dict[str, Any]) -> str:
    """Fallback narration when LLM is unavailable."""
    name = poi.get("name", "这个景点")
    desc = poi.get("description", "")
    address = poi.get("address", "")
    price = poi.get("price_level", "未知")

    return (
        f"🏛️ 欢迎来到{name}！\n\n"
        f"{desc[:200]}...\n\n"
        f"📍 地址：{address}\n"
        f"💰 价格：{price}\n\n"
        f"（AI导游服务暂时不可用，以上为基础信息介绍。）"
    )

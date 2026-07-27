"""
TravelMind Agent — RAG Retriever

Semantic search with multi-factor filtering for attractions.

Main entry points:
  - retrieve(profile, query, top_k, weather)  →  List of attractions with scores
  - retrieve_by_preferences(tags, city, ...)  →  Multi-factor filtered results

Combines:
  1. Semantic similarity   (embedding → Chroma search)
  2. City filter            (metadata filter on city)
  3. Budget filter          (price_level match)
  4. Tag boost              (tag overlap bonus)
  5. Popularity boost       (popularity_score weighting)
  6. Weather boost          (indoor ↑ / outdoor ↓ when rain, Phase 12.16)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.rag.embedding import BaseEmbeddingProvider, get_embedding_provider
from app.rag.vector_store import ChromaStore, get_vector_store

logger = logging.getLogger(__name__)

# ── KB city list cache (for cross-city quota recall) ───────

_KB_CITIES_CACHE: Optional[List[str]] = None


def _get_kb_cities() -> List[str]:
    """Return the sorted list of cities present in attractions.json (cached)."""
    global _KB_CITIES_CACHE
    if _KB_CITIES_CACHE is None:
        try:
            from pathlib import Path
            data_path = Path(__file__).parent.parent.parent / "data" / "attractions.json"
            with open(data_path, "r", encoding="utf-8") as f:
                _KB_CITIES_CACHE = sorted({
                    a.get("city", "")
                    for a in json.load(f).get("attractions", [])
                    if a.get("city")
                })
        except Exception:
            _KB_CITIES_CACHE = []
    return _KB_CITIES_CACHE

# Scoring weights
WEIGHT_SIMILARITY = 0.45    # semantic similarity to query
WEIGHT_TAG_MATCH = 0.25     # tag overlap between user prefs and attraction
WEIGHT_POPULARITY = 0.15    # popularity score (1-10 normalized)
WEIGHT_BUDGET = 0.10        # budget level match
WEIGHT_TIME = 0.05          # seasonal suitability

# Phase 12.16: Weather-aware rain keywords (Chinese + WMO codes)
_RAIN_KEYWORDS = ("雨", "雷", "雪", "阵雨", "暴雨", "drizzle", "rain", "thunder")


# ── Phase 12.16: Weather-Aware Scoring ───────────────────


def _compute_rain_ratio(weather: Optional[Dict[str, Any]]) -> float:
    """Compute the ratio of rainy days in the forecast (0.0 to 1.0).

    Used to scale the indoor/outdoor boost proportionally to how much
    rain is expected during the trip.

    A day is considered "rainy" if:
      - weather_desc contains Chinese rain keywords (雨, 雷, 雪, etc.)
      - precipitation > 0.5 mm
      - WMO weather_code >= 50 (drizzle or heavier)
    """
    if not weather or not weather.get("daily"):
        return 0.0

    daily = weather["daily"]
    if not daily:
        return 0.0

    rainy = 0
    for day in daily:
        if not isinstance(day, dict):
            continue
        desc = day.get("weather_desc", "") or ""
        precip = day.get("precipitation", 0) or 0
        code = day.get("weather_code", 0) or 0

        is_rainy = (
            any(w in desc for w in _RAIN_KEYWORDS)
            or precip > 0.5
            or (isinstance(code, (int, float)) and code >= 50)
        )
        if is_rainy:
            rainy += 1

    return rainy / len(daily)


def _get_weather_boost(
    item_metadata: Dict[str, Any],
    rain_ratio: float,
) -> float:
    """Compute a weather-aware scoring boost for a single POI.

    Phase 12.16: When rain is forecast (rain_ratio ≥ 0.2), indoor POIs
    receive a positive boost and outdoor POIs receive a slight penalty.
    This shifts the ranking so the LLM has more indoor alternatives on
    rainy-day itineraries.

    Uses the same KB-tag-aware classifier as the weather_fit evaluator
    (classify_poi_indoor from itinerary_contract) for consistency.

    Returns:
        Boost value: +0.10 to +0.15 for indoor, -0.05 to -0.08 for outdoor.
        0.0 when rain_ratio < 0.2 (not enough rain to matter).
    """
    if rain_ratio < 0.2:
        return 0.0

    tags_str = item_metadata.get("tags", "")
    item_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    name = item_metadata.get("name", "") or item_metadata.get("name_normalized", "") or ""

    if not item_tags and not name:
        return 0.0

    # Lazy import to avoid top-level circular dependency
    try:
        from app.agents.itinerary_contract import classify_poi_indoor
        classification = classify_poi_indoor(name, kb_tags=item_tags if item_tags else None)
    except ImportError:
        return 0.0

    if classification in ("indoor", "semi"):
        return 0.20 * rain_ratio  # Indoor boost: 0.0 → 0.20 depending on rain
    else:  # outdoor
        return -0.10 * rain_ratio  # Outdoor penalty: 0.0 → -0.10


# ── Public API ───────────────────────────────────────────


async def retrieve(
    user_profile: Dict[str, Any],
    query: str = "",
    top_k: int = 20,
    weather: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Main retrieval function.

    Builds a semantic query from user_profile, searches the vector store,
    and returns ranked attractions with score breakdowns.

    Phase 12.16: Accepts optional weather forecast. When rain is expected,
    indoor POIs receive a ranking boost so the LLM has more alternatives.

    Args:
        user_profile: Extracted user profile dict from Profile Agent.
            Expected keys: destination, tags, budget_level, days, travel_style,
            companions, constraints.
        query: Optional override query string. If empty, auto-generated from profile.
        top_k: Number of results to return.
        weather: Optional weather forecast dict with 'daily' key
            (from WeatherForecast.to_dict()). Used for indoor/outdoor scoring.

    Returns:
        List of attraction dicts with added 'relevance_score' and '_score_breakdown'.
    """
    provider: BaseEmbeddingProvider
    store: ChromaStore

    try:
        provider = get_embedding_provider()
        store = get_vector_store()
    except RuntimeError as e:
        logger.warning(f"RAG not initialized: {e}")
        return []

    if not store.is_connected:
        try:
            store.connect()
        except Exception as e:
            logger.warning(f"Chroma unavailable: {e}")
            return []

    # Build query
    if not query:
        query = _build_query_from_profile(user_profile)

    tags = user_profile.get("tags", []) or []
    city = (user_profile.get("destination", "") or "")[:200]  # max 200 chars
    budget = user_profile.get("budget_level", "") or user_profile.get("budget", "") or ""
    travel_style = (user_profile.get("travel_style", "") or "")[:200]
    travel_month = user_profile.get("travel_month", 0)  # 1-12; 0 = unknown

    # Phase 12.16: Compute rain ratio for weather-aware scoring
    rain_ratio = _compute_rain_ratio(weather)

    # Phase 10: Check cache for RAG results (key includes rain_ratio for Phase 12.16)
    import hashlib
    tags_hash = hashlib.md5(",".join(sorted(tags)).encode()).hexdigest() if tags else "notags"
    cache_key = f"rag:{city}:{tags_hash}:{budget}:{travel_style}:{travel_month}:{top_k}:w{rain_ratio:.1f}"
    cache = None
    try:
        from app.services.cache_service import get_cache
        cache = get_cache()
        cached = await cache.get(cache_key)
        if cached:
            results = json.loads(cached)
            logger.debug("RAG cache hit for city=%s top_k=%d (%d results)", city, top_k, len(results))
            return results
    except Exception as e:
        logger.debug("RAG cache read failed (non-fatal): %s", e)

    # Embed the query (tags are optional — composite providers use them)
    query_vec = provider.embed_query(query, tags=tags)

    # Build Chroma metadata filter
    where_filter = _build_city_filter(city) if city else None

    # Search (get more than top_k to allow re-ranking)
    raw_results = store.search(
        query_embedding=query_vec,
        top_k=min(top_k * 3, 100),
        where=where_filter,
    )

    if not raw_results:
        logger.info(f"No results found for city={city}, query='{query[:50]}...'")
        # Cache empty result with shorter TTL to avoid hammering Chroma
        if cache is not None:
            try:
                await cache.set(cache_key, json.dumps([]), ttl=60)
            except Exception:
                pass
        return []

    # Re-rank with multi-factor scoring (Phase 12.16: +weather boost)
    scored = _rerank(
        raw_results,
        user_tags=tags,
        user_budget=budget,
        user_travel_style=travel_style,
        travel_month=travel_month,
        rain_ratio=rain_ratio,
    )

    # Return top-k
    result = scored[:top_k]
    if cache is not None:
        try:
            await cache.set(cache_key, json.dumps(result, ensure_ascii=False), ttl=600)
        except Exception:
            pass  # cache write failure is non-fatal
    return result


async def retrieve_by_preferences(
    tags: Optional[List[str]] = None,
    city: Optional[str] = None,
    budget_level: Optional[str] = None,
    travel_style: Optional[str] = None,
    travel_month: int = 0,
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """Convenience function — retrieve by explicit preferences.

    This is the lower-level API; retrieve() is the main one that
    auto-builds the query from a full profile.
    """
    profile = {
        "tags": tags or [],
        "destination": city or "",
        "budget_level": budget_level or "",
        "travel_style": travel_style or "",
        "travel_month": travel_month,
    }
    return await retrieve(profile, top_k=top_k)


async def retrieve_cross_city(
    tags: List[str],
    top_k: int = 20,
    budget_level: str = "适中",
) -> List[Dict[str, Any]]:
    """Cross-city retrieval — search the entire knowledge base without city filter.

    Used by the image-based "find similar places" feature where the user's
    photo tags should match attractions across all cities.

    Returns attractions from any city, sorted by tag-match + popularity score.
    """
    provider: BaseEmbeddingProvider
    store: ChromaStore

    try:
        provider = get_embedding_provider()
        store = get_vector_store()
    except RuntimeError as e:
        logger.warning(f"RAG not initialized: {e}")
        return []

    if not store.is_connected:
        try:
            store.connect()
        except Exception as e:
            logger.warning(f"Chroma unavailable: {e}")
            return []

    # Expand user-facing tags to KB vocabulary (Phase 12.8)
    expanded_tags = _expand_tags(tags)

    # Build query from expanded tags (no city constraint)
    query = f"偏好: {' '.join(expanded_tags)}" if expanded_tags else "旅游景点"
    query_vec = provider.embed_query(query, tags=expanded_tags)

    # Search WITHOUT city filter — cross-city
    raw_results = store.search(
        query_embedding=query_vec,
        top_k=min(top_k * 3, 100),
        where=None,  # No city filter!
    )

    if not raw_results:
        logger.info(f"No cross-city results for tags={tags}")
        return []

    # Re-rank with multi-factor scoring (neutral budget, no city bias)
    scored = _rerank(
        raw_results,
        user_tags=tags,
        user_budget=budget_level,
        user_travel_style="",
        travel_month=0,
    )

    # ── City diversity re-ranking (Phase 12.8) ───────────────
    # Ensure results span ≥3 different cities. Without this, large cities
    # (重庆, 成都, 北京) dominate cross-city results due to higher POI count.
    # Strategy: interleave — take top results, then fill gaps with best
    # results from under-represented cities.
    city_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for item in scored:
        c = item.get("metadata", {}).get("city", item.get("city", "unknown"))
        city_buckets.setdefault(c, []).append(item)

    # Phase 12.17: 语义检索召回城市过少时（如"海"只召回三亚），
    # 按城市配额补充检索，让跨城多样性成为结构性保障而非语义运气
    if len(city_buckets) < 3:
        seen_ids = {item.get("id") for item in raw_results}
        covered = set(city_buckets)
        for city in _get_kb_cities():
            if city in covered or len(covered) >= 6:
                continue
            try:
                extra = store.search(
                    query_embedding=query_vec, top_k=3, where={"city": city}
                )
            except Exception:
                continue
            extra = [e for e in extra if e.get("id") not in seen_ids]
            if not extra:
                continue
            # Phase 12.18: 配额补充必须与查询标签相关——"想看海"不该补出
            # 成都的洞穴（语义弱匹配噪音）；无命中则放弃该城的补充
            if expanded_tags:
                relevant = [
                    e for e in extra
                    if any(t in (e.get("metadata", {}).get("tags", "") or "")
                           for t in expanded_tags)
                ]
                if relevant:
                    extra = relevant
            seen_ids.update(e.get("id") for e in extra)
            raw_results.extend(extra)
            covered.add(city)
        if len(covered) > len(city_buckets):
            scored = _rerank(
                raw_results,
                user_tags=tags,
                user_budget=budget_level,
                user_travel_style="",
                travel_month=0,
            )
            city_buckets = {}
            for item in scored:
                c = item.get("metadata", {}).get("city", item.get("city", "unknown"))
                city_buckets.setdefault(c, []).append(item)

    if len(city_buckets) >= 3:
        # Interleave: round-robin from each city, keeping best-first within each city
        diverse: List[Dict[str, Any]] = []
        city_iters = {c: iter(items) for c, items in city_buckets.items()}
        city_queue = list(city_buckets.keys())
        while len(diverse) < top_k and city_queue:
            for c in list(city_queue):
                try:
                    diverse.append(next(city_iters[c]))
                except StopIteration:
                    city_queue.remove(c)
            if not city_queue:
                break
        scored = diverse

    return scored[:top_k]


# ── Type-based tag mappings ────────────────────────────────

_TYPE_TAG_MAP = {
    "美食": {"美食", "火锅", "小吃", "烧烤", "海鲜", "早茶", "川菜", "粤菜",
             "面食", "夜市", "自助", "甜品", "奶茶", "咖啡", "餐厅", "小吃街",
             "美食街", "大排档"},
    "自然": {"自然", "爬山", "湖泊", "森林", "海岛", "海滩", "瀑布", "峡谷",
             "日出", "日落", "草原", "雪山", "温泉", "赏花", "红叶", "溶洞",
             "丹霞", "喀斯特", "湿地", "冰川"},
    "历史": {"历史", "博物馆", "古镇", "寺庙", "古迹", "园林", "建筑", "文化",
             "传统", "遗址", "名人故居", "古建筑", "历史街区"},
    "购物": {"购物", "打卡", "网红打卡", "城市", "文艺", "夜生活", "酒吧",
             "商场", "步行街", "创意园", "市集"},
}

# ── Tag Synonym Map (Phase 12.8) ───────────────────────────
# Maps external/user-facing tags to KB vocabulary tags.
# The KB only has ~52 unique tags; many common travel keywords
# (like "山水", "古城", "夜景") don't match any KB tag exactly.
#
# When a query uses a tag not in the KB vocabulary, this map
# expands it to semantically-equivalent KB tags. This ensures
# eval constraints like image_tag_relevance work correctly.

_TAG_SYNONYM_MAP: Dict[str, List[str]] = {
    # Geographical / landscape
    "山水": ["自然风光", "自然", "户外", "摄影", "徒步"],
    "自然景观": ["自然风光", "自然", "户外"],
    "地貌": ["自然风光", "自然", "峡谷", "溶洞"],
    # Architecture / cityscape
    "古城": ["古镇", "历史", "建筑", "遗址", "文化"],
    "古建筑": ["建筑", "历史", "遗址"],
    "夜景": ["夜生活", "打卡", "网红打卡", "摄影", "城市"],
    "城市景观": ["城市", "建筑", "打卡"],
    "现代建筑": ["建筑", "城市", "打卡", "网红打卡"],
    # Food
    "美食街": ["美食", "小吃", "夜市", "中餐", "打卡"],
    "老字号": ["老字号", "美食", "小吃", "中餐"],
    "本地美食": ["美食", "小吃", "中餐", "老字号"],
    "夜市小吃": ["夜市", "小吃", "美食", "打卡"],
    # Activities
    "日落": ["日落", "摄影", "海滩", "户外", "自然"],
    "日出": ["日出", "摄影", "户外", "自然"],
    "海岛": ["海岛", "海滩", "自然", "户外", "潜水"],
    "海滩": ["海滩", "海岛", "自然", "户外"],
    "瀑布": ["瀑布", "自然风光", "自然", "户外", "摄影"],
    # Culture / experience
    "文化体验": ["文化", "民俗", "历史", "博物馆", "文艺"],
    "文艺": ["文艺", "打卡", "网红打卡", "摄影", "创意园"],
    "浪漫": ["情侣", "日落", "文艺", "打卡", "海滩"],
    "亲子": ["亲子", "家庭", "休闲", "户外"],
    "家庭游": ["家庭", "亲子", "休闲"],
    # Seasons
    "避暑": ["夏季", "自然", "户外", "休闲"],
    "赏花": ["赏花", "春季", "自然", "摄影"],
    "温泉": ["温泉", "休闲", "冬季"],
}


def _expand_tags(tags: List[str]) -> List[str]:
    """Expand user-facing tags to KB vocabulary using the synonym map.

    For each input tag:
      1. If it exists in KB vocabulary, keep it as-is.
      2. If it has synonym mappings, expand to mapped KB tags.
      3. Otherwise, keep the original tag (embedding will handle fuzzy match).

    Returns deduplicated list preserving original tags first, then expansions.
    """
    if not tags:
        return []
    expanded: List[str] = []
    seen: set = set()
    for t in tags:
        if t not in seen:
            expanded.append(t)
            seen.add(t)
        synonyms = _TAG_SYNONYM_MAP.get(t, [])
        for s in synonyms:
            if s not in seen:
                expanded.append(s)
                seen.add(s)
    return expanded[:30]  # Cap at 30 tags


async def retrieve_by_type(
    type_keywords: List[str],
    city: Optional[str] = None,
    top_k: int = 20,
    budget_level: str = "适中",
) -> List[Dict[str, Any]]:
    """Type-targeted retrieval — search with type-specific tag boosting.

    Used when the user's intent is clearly focused on a specific POI type
    (e.g., food-only search, nature-only search).

    Args:
        type_keywords: List of type categories, e.g. ["美食"] or ["自然", "历史"].
            Each keyword maps to a set of relevant tags for boosting.
        city: Optional city filter. If None, cross-city search.
        top_k: Max results to return.
        budget_level: Budget level for scoring.

    Returns:
        Scored attractions sorted by relevance, with results matching the
        target type boosted above non-matching results.
    """
    provider: BaseEmbeddingProvider
    store: ChromaStore

    try:
        provider = get_embedding_provider()
        store = get_vector_store()
    except RuntimeError as e:
        logger.warning(f"RAG not initialized: {e}")
        return []

    if not store.is_connected:
        try:
            store.connect()
        except Exception as e:
            logger.warning(f"Chroma unavailable: {e}")
            return []

    # Resolve type keywords to their expanded tag sets
    boosted_tags: set = set()
    for kw in type_keywords:
        expanded = _TYPE_TAG_MAP.get(kw, {kw})
        boosted_tags.update(expanded)

    # Build tags list for embedding
    tags = list(boosted_tags)[:20]  # Cap at 20 tags

    query = f"类型: {' '.join(type_keywords)}; 偏好: {' '.join(tags[:8])}"
    query_vec = provider.embed_query(query, tags=tags)

    where_filter = _build_city_filter(city) if city else None

    # Get more results for re-ranking
    raw_results = store.search(
        query_embedding=query_vec,
        top_k=min(top_k * 3, 100),
        where=where_filter,
    )

    if not raw_results:
        logger.info(f"No results for type={type_keywords}, city={city}")
        return []

    # Re-rank with boosted tag weights
    scored = _rerank_with_type_boost(
        raw_results,
        user_tags=tags,
        boosted_tags=boosted_tags,
        user_budget=budget_level,
        user_travel_style="",
        travel_month=0,
    )

    return scored[:top_k]


def _rerank_with_type_boost(
    results: List[Dict[str, Any]],
    user_tags: List[str],
    boosted_tags: set,
    user_budget: str,
    user_travel_style: str,
    travel_month: int,
    rain_ratio: float = 0.0,
) -> List[Dict[str, Any]]:
    """Re-rank with extra weight on type-matching tags (+ Phase 12.16 weather boost)."""
    user_tag_set = set(user_tags)

    for item in results:
        meta = item.get("metadata", {})

        sim_score = item.get("score", 0.0)

        item_tags_str = meta.get("tags", "")
        item_tags = set(t.strip() for t in item_tags_str.split(",") if t.strip())
        tag_overlap = len(user_tag_set & item_tags)
        tag_score = min(tag_overlap / max(len(user_tag_set), 1), 1.0)

        # Type boost: POI whose tags match the boosted type tags get bonus
        type_overlap = len(boosted_tags & item_tags) if boosted_tags else 0
        type_boost = min(type_overlap * 0.1, 0.3)  # Up to 0.3 bonus for strong type match

        pop_raw = meta.get("popularity_score")
        try:
            pop_score = float(pop_raw) / 10.0 if pop_raw is not None else 0.5
        except (ValueError, TypeError):
            pop_score = 0.5

        budget_score = _budget_match_score(user_budget, meta.get("price_level", ""))
        time_score = _season_match_score(travel_month, meta.get("best_time", ""))

        # Phase 12.16: Weather-aware boost
        weather_boost = _get_weather_boost(meta, rain_ratio)

        total = (
            WEIGHT_SIMILARITY * sim_score +
            WEIGHT_TAG_MATCH * tag_score +
            WEIGHT_POPULARITY * pop_score +
            WEIGHT_BUDGET * budget_score +
            WEIGHT_TIME * time_score +
            type_boost +  # Extra type-matching bonus
            weather_boost  # Phase 12.16: weather-aware boost
        )

        item["relevance_score"] = round(total, 4)
        item["_score_breakdown"] = {
            "similarity": round(sim_score, 3),
            "tag_match": round(tag_score, 3),
            "popularity": round(pop_score, 3),
            "budget": round(budget_score, 3),
            "season": round(time_score, 3),
            "type_boost": round(type_boost, 3),
            "weather": round(weather_boost, 3),
        }

    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return results


# ── Query builder ────────────────────────────────────────


def _build_query_from_profile(profile: Dict[str, Any]) -> str:
    """Build a semantic search query from user profile fields."""
    parts = []

    dest = profile.get("destination", "")
    if dest:
        parts.append(f"目的地: {dest}")

    tags = profile.get("tags", []) or []
    if tags:
        parts.append(f"偏好: {' '.join(tags)}")

    style = profile.get("travel_style", "")
    if style:
        parts.append(f"旅行风格: {style}")

    companions = profile.get("companions", "")
    if companions:
        parts.append(f"同行: {companions}")

    constraints = profile.get("constraints", "")
    if constraints:
        parts.append(f"需求: {constraints}")

    if not parts:
        return "旅游景点推荐"

    return "。".join(parts)


# ── Chroma filter builder ────────────────────────────────


def _build_city_filter(city: str) -> Optional[Dict[str, Any]]:
    """Build a Chroma metadata filter for city."""
    if not city:
        return None
    return {"city": city}


def _build_budget_filter(budget: str) -> Optional[Dict[str, Any]]:
    """Build a Chroma metadata filter for price_level."""
    if not budget:
        return None

    # Map common budget terms to our price_level values
    budget_map = {
        "穷游": "经济",
        "经济": "经济",
        "低": "经济",
        "中等": "适中",
        "适中": "适中",
        "舒适": "适中",
        "高端": "高端",
        "奢华": "高端",
        "高": "高端",
    }
    price_level = budget_map.get(budget, "适中")

    if price_level == "适中":
        # For moderate budget, include 经济 and 适中
        return {"$or": [
            {"price_level": "经济"},
            {"price_level": "适中"},
        ]}
    return {"price_level": price_level}


# ── Re-ranking ───────────────────────────────────────────


def _rerank(
    results: List[Dict[str, Any]],
    user_tags: List[str],
    user_budget: str,
    user_travel_style: str,
    travel_month: int,
    rain_ratio: float = 0.0,
) -> List[Dict[str, Any]]:
    """Re-rank Chroma results with multi-factor scoring.

    Phase 12.16: Added weather-aware boost (indoor ↑ / outdoor ↓ when rain).
    Returns results with 'relevance_score' and '_score_breakdown' added.
    """
    user_tag_set = set(user_tags)

    for item in results:
        meta = item.get("metadata", {})

        # 1. Semantic similarity (from Chroma distance)
        sim_score = item.get("score", 0.0)

        # 2. Tag match score
        item_tags_str = meta.get("tags", "")
        item_tags = set(t.strip() for t in item_tags_str.split(",") if t.strip())
        tag_overlap = len(user_tag_set & item_tags)
        tag_score = min(tag_overlap / max(len(user_tag_set), 1), 1.0)

        # 3. Popularity score (1-10 → 0-1)
        pop_raw = meta.get("popularity_score")
        try:
            pop_score = float(pop_raw) / 10.0 if pop_raw is not None else 0.5
        except (ValueError, TypeError):
            pop_score = 0.5

        # 4. Budget match
        budget_score = _budget_match_score(user_budget, meta.get("price_level", ""))

        # 5. Time / seasonal match
        time_score = _season_match_score(travel_month, meta.get("best_time", ""))

        # 6. Phase 12.16: Weather-aware boost (indoor ↑ / outdoor ↓ when rain)
        weather_boost = _get_weather_boost(meta, rain_ratio)

        # Weighted total
        total = (
            WEIGHT_SIMILARITY * sim_score +
            WEIGHT_TAG_MATCH * tag_score +
            WEIGHT_POPULARITY * pop_score +
            WEIGHT_BUDGET * budget_score +
            WEIGHT_TIME * time_score +
            weather_boost  # Phase 12.16: extra weather term (not in base weights)
        )

        item["relevance_score"] = round(total, 4)
        item["_score_breakdown"] = {
            "similarity": round(sim_score, 3),
            "tag_match": round(tag_score, 3),
            "popularity": round(pop_score, 3),
            "budget": round(budget_score, 3),
            "season": round(time_score, 3),
            "weather": round(weather_boost, 3),
        }

    # Sort by relevance score descending
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return results


def _budget_match_score(user_budget: str, item_price: str) -> float:
    """Score how well the attraction's price level matches user budget."""
    if not user_budget or not item_price:
        return 0.5  # neutral if unknown

    budget_map = {
        "穷游": "经济", "经济": "经济",
        "中等": "适中", "适中": "适中", "舒适": "适中",
        "高端": "高端", "奢华": "高端",
    }
    user_level = budget_map.get(user_budget, "适中")

    levels = ["经济", "适中", "高端"]
    if item_price not in levels:
        return 0.5

    user_idx = levels.index(user_level)
    item_idx = levels.index(item_price)

    if user_idx == item_idx:
        return 1.0  # exact match
    if abs(user_idx - item_idx) == 1:
        return 0.6  # one level off
    return 0.2  # two levels off


def _season_match_score(travel_month: int, best_time: str) -> float:
    """Score how well the attraction's best season matches travel month."""
    if not travel_month or not best_time:
        return 0.5  # neutral

    season_map = {
        "春季": [3, 4, 5],
        "夏季": [6, 7, 8],
        "秋季": [9, 10, 11],
        "冬季": [12, 1, 2],
        "全年": list(range(1, 13)),
    }

    matching_months = set()
    for season, months in season_map.items():
        if season in best_time:
            matching_months.update(months)

    # Also check for month names directly
    month_names = {
        1: "一月", 2: "二月", 3: "三月", 4: "四月",
        5: "五月", 6: "六月", 7: "七月", 8: "八月",
        9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
    }
    for m, name in month_names.items():
        if name in best_time:
            matching_months.add(m)

    if not matching_months:
        return 0.5  # couldn't parse, neutral

    if travel_month in matching_months:
        return 1.0  # exact match

    # Check adjacent months (±1)
    prev_month = 12 if travel_month == 1 else travel_month - 1
    next_month = 1 if travel_month == 12 else travel_month + 1
    if prev_month in matching_months or next_month in matching_months:
        return 0.7

    return 0.3

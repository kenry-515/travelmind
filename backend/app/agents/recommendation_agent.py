"""
TravelMind Agent — Recommendation Agent

6-factor weighted scoring for attraction ranking.

Formula (from architecture.md):
  Score = 0.35 × Preference_Match     (user tags vs place tags cosine-like overlap)
        + 0.25 × Trend_Heat           (from trend_agent / trends.json)
        + 0.15 × Budget_Match         (user budget vs place price_level)
        + 0.10 × Location_Efficiency  (Amap distance matrix: ≤5km=1.0 … >30km=0.1)
        + 0.10 × Time_Match           (best_time vs travel month)
        + 0.05 × Data_Reliability     (source credibility weight)

Usage:
    from app.agents.recommendation_agent import recommend
    ranked = await recommend(profile, candidates, trends)
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import — Amap routing service is optional
_amap_service = None


def _get_amap_service():
    global _amap_service
    if _amap_service is None:
        try:
            from app.services.amap_service import score_location_efficiency
            _amap_service = score_location_efficiency
        except ImportError:
            _amap_service = False  # sentinel: not available
    return _amap_service if _amap_service is not False else None

# ── Scoring Weights ──────────────────────────────────────

# Base weights (general travel)
W_PREFERENCE = 0.35
W_TREND = 0.25
W_BUDGET = 0.15
W_LOCATION = 0.10
W_TIME = 0.10
W_RELIABILITY = 0.05

# Intent-specific weight overrides (Phase 12.2)
# Food intent: preference match matters more, trend matters less
# Nature intent: location efficiency + time match matter more
INTENT_WEIGHTS = {
    "food": {"W_PREFERENCE": 0.40, "W_TREND": 0.15, "W_BUDGET": 0.15,
             "W_LOCATION": 0.10, "W_TIME": 0.10, "W_RELIABILITY": 0.10},
    "nature": {"W_PREFERENCE": 0.30, "W_TREND": 0.20, "W_BUDGET": 0.15,
               "W_LOCATION": 0.15, "W_TIME": 0.15, "W_RELIABILITY": 0.05},
    "history": {"W_PREFERENCE": 0.35, "W_TREND": 0.20, "W_BUDGET": 0.15,
                "W_LOCATION": 0.10, "W_TIME": 0.15, "W_RELIABILITY": 0.05},
    "shopping": {"W_PREFERENCE": 0.35, "W_TREND": 0.30, "W_BUDGET": 0.15,
                 "W_LOCATION": 0.10, "W_TIME": 0.05, "W_RELIABILITY": 0.05},
}

# Food-specific tags (used to detect food search intent)
_FOOD_TAGS = {
    "美食", "火锅", "小吃", "烧烤", "海鲜", "早茶", "川菜", "粤菜",
    "面食", "夜市", "自助", "甜品", "奶茶", "咖啡",
}

# Nature-specific tags
_NATURE_TAGS = {
    "自然", "爬山", "湖泊", "森林", "海岛", "海滩", "瀑布",
    "峡谷", "日出", "日落", "赏花", "红叶", "草原", "雪山",
}

# History/culture tags
_HISTORY_TAGS = {
    "历史", "博物馆", "古镇", "寺庙", "古迹", "园林",
    "建筑", "文化", "传统",
}

# Shopping/urban tags
_SHOPPING_TAGS = {
    "购物", "打卡", "网红打卡", "城市", "文艺",
    "夜生活", "酒吧",
}


def _detect_search_intent(tags: List[str], user_input: str = "") -> str:
    """Detect the primary search intent from user tags and input text.

    Returns one of: 'food', 'nature', 'history', 'shopping', 'general'.
    """
    tag_set = {t.lower() for t in tags}
    text_lower = user_input.lower()

    scores = {"food": 0, "nature": 0, "history": 0, "shopping": 0}

    # Tag-based scoring
    for tag in tag_set:
        if tag in _FOOD_TAGS:
            scores["food"] += 2
        if tag in _NATURE_TAGS:
            scores["nature"] += 2
        if tag in _HISTORY_TAGS:
            scores["history"] += 2
        if tag in _SHOPPING_TAGS:
            scores["shopping"] += 2

    # Text-based scoring (user input keywords)
    food_kw = ["吃", "美食", "火锅", "餐厅", "小吃", "海鲜", "烧烤", "早茶", "夜市", "好吃"]
    nature_kw = ["山", "湖", "海", "瀑布", "自然", "森林", "徒步", "登", "日出", "日落"]
    history_kw = ["历史", "博物馆", "古", "寺庙", "园林", "文化", "传统"]
    shop_kw = ["购物", "逛街", "商场", "打卡", "网红", "酒吧", "夜生活"]

    for kw in food_kw:
        if kw in text_lower:
            scores["food"] += 1
    for kw in nature_kw:
        if kw in text_lower:
            scores["nature"] += 1
    for kw in history_kw:
        if kw in text_lower:
            scores["history"] += 1
    for kw in shop_kw:
        if kw in text_lower:
            scores["shopping"] += 1

    # Determine primary intent (needs at least 2 points to activate)
    best = max(scores, key=scores.get)  # type: ignore
    if scores[best] >= 2:
        return best
    return "general"


def _diversity_penalty(places: List[Dict[str, Any]], max_same_area: int = 2) -> List[float]:
    """Apply diversity penalty to prevent too many POIs from the same area or tag category.

    Returns a list of penalty multipliers (0.0-1.0) for each place.
    Later places in the same area/category get progressively lower multipliers.

    Phase 12.30: Added tag-category diversity alongside geographic diversity
    to address tag_category_diversity metric (56% → target ≥80%).
    POIs without tags are exempt from tag-category penalty to avoid
    penalizing un-enriched data.
    """
    penalties = []
    area_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    for p in places:
        meta = _extract_metadata(p)
        name = meta["name"]
        tags = meta.get("tags", []) or []

        # Geographic diversity (area key = first 4 chars of name)
        area_key = name[:4] if len(name) >= 4 else name
        count = area_counts.get(area_key, 0)
        area_counts[area_key] = count + 1

        # Tag category diversity (only for POIs with tags)
        penalty = 1.0

        if count >= max_same_area:
            penalty *= 0.5  # Strong penalty for same area
        elif count >= 1:
            penalty *= 0.85  # Mild penalty

        if tags:
            cat_key = _tag_category_key(tags)
            cat_count = category_counts.get(cat_key, 0)
            category_counts[cat_key] = cat_count + 1
            if cat_count >= 3:
                penalty *= 0.6  # Strong penalty for 3+ in same category
            elif cat_count >= 2:
                penalty *= 0.8  # Mild penalty for 2 in same category

        penalties.append(max(0.3, penalty))
    return penalties


# Tag → broad category mapping for diversity enforcement (Phase 12.30)
_TAG_CATEGORY_MAP: Dict[str, str] = {
    # 自然/户外
    "自然": "outdoor", "爬山": "outdoor", "湖泊": "outdoor", "森林": "outdoor",
    "海岛": "outdoor", "海滩": "outdoor", "瀑布": "outdoor", "峡谷": "outdoor",
    "日出": "outdoor", "日落": "outdoor", "赏花": "outdoor", "红叶": "outdoor",
    "草原": "outdoor", "雪山": "outdoor", "徒步": "outdoor", "骑行": "outdoor",
    # 文化/历史
    "历史": "culture", "博物馆": "culture", "古镇": "culture", "寺庙": "culture",
    "遗址": "culture", "建筑": "culture", "文化": "culture", "传统": "culture",
    "园林": "culture", "故居": "culture", "纪念馆": "culture",
    # 美食
    "美食": "food", "火锅": "food", "小吃": "food", "烧烤": "food",
    "海鲜": "food", "早茶": "food", "川菜": "food", "粤菜": "food",
    "面食": "food", "夜市": "food", "甜品": "food", "咖啡": "food",
    # 购物/城市
    "购物": "shopping", "网红打卡": "shopping", "打卡": "shopping",
    "夜生活": "shopping", "酒吧": "shopping", "商场": "shopping",
    # 室内/休闲
    "亲子": "indoor", "情侣": "indoor", "家庭": "indoor", "休闲": "indoor",
    "温泉": "indoor", "美术馆": "indoor", "图书馆": "indoor",
}


def _tag_category_key(tags: List[str]) -> str:
    """Map a list of POI tags to a broad category key for diversity scoring."""
    for tag in tags:
        cat = _TAG_CATEGORY_MAP.get(tag)
        if cat:
            return cat
    return "other"

from app.core.constants import (
    BUDGET_MAP,
    BUDGET_LEVELS,
    MONTH_NAMES,
    SEASON_MONTHS,
    normalize_budget_level,
)


def _parse_months_from_best_time(best_time: str) -> set:
    """Parse a best_time string into a set of matching month numbers.

    Handles strings like "春季", "秋季和春季", "3-5月", "全年", etc.
    """
    if not best_time or best_time == "全年":
        return set(range(1, 13))

    months: set = set()

    # Check for season names
    for season, m_set in SEASON_MONTHS.items():
        if season in best_time:
            months.update(m_set)

    # Check for month names
    for m_num, m_name in MONTH_NAMES.items():
        if m_name in best_time:
            months.add(m_num)

    # Check for "X月" patterns
    month_pattern = re.findall(r"(\d{1,2})\s*月", best_time)
    for m_str in month_pattern:
        m = int(m_str)
        if 1 <= m <= 12:
            months.add(m)

    return months if months else set(range(1, 13))


# ── Data source reliability ──────────────────────────────

SOURCE_RELIABILITY = {
    "wikidata+amap": 0.9,
    "wikidata": 0.85,
    "amap": 0.8,
    "kb-curated": 0.75,
    "osm-overpass": 0.55,
    "amap-food": 0.75,
    "web-social+osm-overpass": 0.5,
    "web-verified-coords": 0.65,
}

# Map data_reliability labels to scores
RELIABILITY_SCORES = {
    "high": 0.9,
    "medium": 0.7,
    "low": 0.5,
    "poor": 0.3,
    "unknown": 0.5,
}


def _get_reliability(source: str, data_reliability: str = "") -> float:
    """Return reliability score from source and data_reliability.

    Uses data_reliability (computed from verifiable signals) when available,
    falls back to source-based reliability.
    """
    # Prefer data_reliability label (from computed signals)
    if data_reliability and data_reliability in RELIABILITY_SCORES:
        return RELIABILITY_SCORES[data_reliability]
    # Fall back to source-based lookup
    if not source:
        return 0.5
    return SOURCE_RELIABILITY.get(source.lower(), 0.5)


# ── Scoring Functions ────────────────────────────────────


def _score_preference(user_tags: List[str], place_tags: List[str]) -> float:
    """Compute preference match: Jaccard-like overlap of user tags vs place tags.

    Returns 0.0-1.0 where 1.0 = perfect overlap.
    """
    if not user_tags:
        return 0.5  # neutral — user didn't specify preferences
    if not place_tags:
        return 0.2  # place has no tags — weak match

    user_set = set(user_tags)
    place_set = set(place_tags)

    intersection = user_set & place_set
    union = user_set | place_set

    if not union:
        return 0.5

    # Jaccard similarity
    jaccard = len(intersection) / len(union)

    # Bonus for exact multi-tag matches
    overlap_ratio = len(intersection) / max(len(user_set), 1)

    # Weighted: 60% Jaccard + 40% overlap ratio
    return round(0.6 * jaccard + 0.4 * overlap_ratio, 3)


def _score_budget(user_budget: str, place_price: str) -> float:
    """Score budget match: 1.0 exact, 0.6 one level off, 0.2 two levels off.

    TRUTHFUL: If price_level is empty/unset, return neutral 0.5
    instead of guessing based on fake data.
    """
    if not user_budget:
        return 0.5  # neutral

    user_level = normalize_budget_level(user_budget)
    if not place_price or place_price not in BUDGET_LEVELS:
        return 0.5  # neutral — price level unknown, don't guess

    try:
        user_idx = BUDGET_LEVELS.index(user_level)
        place_idx = BUDGET_LEVELS.index(place_price)
    except ValueError:
        return 0.5

    diff = abs(user_idx - place_idx)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.6
    return 0.2


def _score_time(travel_month: int, best_time: str) -> float:
    """Score seasonal/time match."""
    if not travel_month or travel_month == 0:
        return 0.5  # unknown month — neutral

    matching_months = _parse_months_from_best_time(best_time)

    if travel_month in matching_months:
        return 1.0

    # Check adjacent months
    prev_m = 12 if travel_month == 1 else travel_month - 1
    next_m = 1 if travel_month == 12 else travel_month + 1
    if prev_m in matching_months or next_m in matching_months:
        return 0.7

    return 0.3


# ── Main Recommendation Logic ────────────────────────────


def _extract_metadata(place: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a candidate place dict.

    Candidate places come from RAG/Chroma with metadata nested under 'metadata' key.
    Original attractions from the data pipeline have flat keys.

    TRUTHFUL: Price range is only shown when price_verifiable is True.
    """
    meta = place.get("metadata", {})
    if meta:
        # Phase 7: Reconstruct price_range from flat Chroma metadata fields
        pr_min = meta.get("price_range_min")
        pr_max = meta.get("price_range_max")
        price_verifiable = meta.get("price_verifiable", False)
        price_range = None
        if price_verifiable and (pr_min is not None or pr_max is not None):
            price_range = {"min": int(pr_min or 0), "max": int(pr_max or 0)}

        return {
            "name": meta.get("name", place.get("name", "")),
            "city": meta.get("city", place.get("city", "")),
            "tags": _parse_tags(meta.get("tags", "")),
            "price_level": meta.get("price_level", ""),
            "price_range": price_range,
            "price_source": meta.get("price_source", ""),
            "price_updated_at": meta.get("price_updated_at", ""),
            "price_verifiable": price_verifiable,
            "amap_id": meta.get("amap_id", ""),
            "popularity_score": _safe_float(meta.get("popularity_score"), 0),
            "best_time": meta.get("best_time", ""),
            "suitable_for": meta.get("suitable_for", ""),
            "source": meta.get("source", place.get("source", "")),
            "lat": _safe_float(meta.get("lat")),
            "lon": _safe_float(meta.get("lon")),
            "internal_rating": _safe_float(meta.get("internal_rating"), 0),
            "data_reliability": meta.get("data_reliability", "unknown"),
            # Preserve original data
            "_original": place,
        }
    # Flat structure (from data pipeline directly)
    return {
        "name": place.get("name", ""),
        "city": place.get("city", ""),
        "tags": place.get("tags", []) or [],
        "price_level": place.get("price_level", ""),
        "price_range": place.get("price_range"),
        "price_source": place.get("price_source", ""),
        "price_updated_at": place.get("price_updated_at", ""),
        "price_verifiable": place.get("price_verifiable", False),
        "amap_id": place.get("amap_id", ""),
        "popularity_score": _safe_float(place.get("popularity_score"), 0),
        "best_time": place.get("best_time", ""),
        "suitable_for": place.get("suitable_for", ""),
        "source": place.get("source", ""),
        "lat": _safe_float(place.get("lat")),
        "lon": _safe_float(place.get("lon")),
        "_original": place,
    }


def _parse_tags(tags_raw) -> List[str]:
    """Parse tags from various formats: list, comma-separated string, etc."""
    if isinstance(tags_raw, list):
        return [str(t).strip() for t in tags_raw if t]
    if isinstance(tags_raw, str) and tags_raw:
        return [t.strip() for t in tags_raw.split(",") if t.strip()]
    return []


def _safe_float(value, default=0.0) -> float:
    """Safely convert a value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


async def recommend(
    profile: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    trends: Optional[List[Dict[str, Any]]] = None,
    weather: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Score and rank candidate attractions using the 6-factor formula.

    Phase 12.16: Added weather-aware indoor/outdoor scoring boost.

    Args:
        profile: User profile dict with keys:
            - tags: list of interest tags
            - budget_level / budget: budget description
            - travel_month: 1-12 (optional)
        candidates: List of candidate attractions from RAG retrieval.
        trends: Optional pre-loaded trend data from trend_agent.
        weather: Optional weather forecast (Phase 12.16, for indoor boost).
            Can be dict or WeatherForecast object.

    Returns:
        Candidates sorted by total_score (descending), each with
        '_score_breakdown' showing all 6 factor scores.
    """
    if not candidates:
        logger.warning("No candidates to score")
        return []
    
    # Normalize weather to dict format (handle WeatherForecast object)
    if weather is not None and hasattr(weather, 'to_dict'):
        weather = weather.to_dict()

    # ── Phase 9: 过滤健康检查标记为 inactive 的 POI ─────
    try:
        from app.services.poi_health_service import _load_inactive_poi_names
        from app.agents.route_optimizer import _normalize
        inactive = _load_inactive_poi_names()
        if inactive:
            original = len(candidates)
            candidates = [
                c for c in candidates
                if _normalize(_extract_metadata(c).get("name", "")) not in inactive
            ]
            filtered = original - len(candidates)
            if filtered > 0:
                logger.info(
                    f"POI health filter: {filtered} inactive removed, "
                    f"{len(candidates)} remaining"
                )
    except Exception as e:
        logger.debug(f"POI health filter unavailable, skipping: {e}")

    if not candidates:
        logger.warning("No candidates after health filter")
        return []

    # Extract user preferences
    user_tags = profile.get("tags", []) or []
    user_budget = profile.get("budget_level", "") or profile.get("budget", "") or ""
    travel_month = profile.get("travel_month", 0)
    user_input = profile.get("user_input", "") or profile.get("_original_input", "")

    # Phase 12.2: Detect search intent and adjust scoring weights
    search_intent = _detect_search_intent(user_tags, user_input)
    intent_w = INTENT_WEIGHTS.get(search_intent)
    if intent_w and search_intent != "general":
        w_pref = intent_w["W_PREFERENCE"]
        w_trend = intent_w["W_TREND"]
        w_budget = intent_w["W_BUDGET"]
        w_loc = intent_w["W_LOCATION"]
        w_time = intent_w["W_TIME"]
        w_rel = intent_w["W_RELIABILITY"]
        logger.info(
            f"Search intent={search_intent}, adaptive weights: "
            f"pref={w_pref} trend={w_trend} budget={w_budget} "
            f"loc={w_loc} time={w_time} rel={w_rel}"
        )
    else:
        w_pref = W_PREFERENCE
        w_trend = W_TREND
        w_budget = W_BUDGET
        w_loc = W_LOCATION
        w_time = W_TIME
        w_rel = W_RELIABILITY

    # Phase 12.2: Apply diversity penalty
    diversity_penalties = _diversity_penalty(candidates)

    # Build trend lookup dict for fast access (index by both original and canonical names)
    trend_map: Dict[str, float] = {}
    trend_src_map: Dict[str, str] = {}  # Phase 12.19: 热度来源（供前端徽章展示）
    if trends:
        for t in trends:
            name = t.get("place_name", "")
            if name:
                # Use effective_score if available, otherwise normalized_score
                score = t.get("effective_score", t.get("normalized_score", 0.5))
                trend_map[name] = score
                trend_src_map[name] = t.get("source", "")
                # Also index by canonical name for cross-source matching
                try:
                    from app.services.name_normalizer import normalize_poi_name
                    canonical = normalize_poi_name(name)
                    if canonical != name:
                        trend_map[canonical] = score
                        trend_src_map[canonical] = t.get("source", "")
                except ImportError:
                    pass

    # ── Location Efficiency (Amap distance matrix) ─────
    # Compute real location efficiency scores via Amap routing.
    # Falls back to 0.5 if Amap is unavailable or coords are missing.
    # Phase 12.21: 跨城模糊意图（profile["_multi_city"]）下"距市中心远近"
    # 没有意义 —— 全国候选池的几何质心会让几乎所有 POI 系统性得 0.1，
    # 保持中性 0.5 并跳过 amap 调用。
    location_scores: List[float] = [0.5] * len(candidates)
    if not profile.get("_multi_city"):
        try:
            amap_location = _get_amap_service()
            if amap_location:
                location_scores = await amap_location(candidates)
            else:
                logger.debug("Amap routing service not available — using neutral location scores")
        except Exception as e:
            logger.debug(f"Amap location scoring failed: {e} — using neutral scores")

    scored = []
    for i, c in enumerate(candidates):
        place = _extract_metadata(c)
        place_name = place["name"]
        place_tags = place["tags"]

        # Factor 1: Preference Match
        pref = _score_preference(user_tags, place_tags)

        # Factor 2: Trend Heat
        # Check trend_map by name (canonical + original + fuzzy)
        trend = trend_map.get(place_name, None)
        trend_source = trend_src_map.get(place_name, "")
        if trend is None:
            # Try canonical name from normalizer
            try:
                from app.services.name_normalizer import normalize_poi_name
                canonical = normalize_poi_name(place_name)
                if canonical != place_name:
                    trend = trend_map.get(canonical, None)
                    trend_source = trend_src_map.get(canonical, "")
            except ImportError:
                pass
        if trend is None and trends:
            from app.agents.trend_agent import get_trend_score
            trend = await get_trend_score(place_name, place["city"], trends)
        if trend is None:
            # Use RAG's relevance_score or popularity as fallback
            rag_score = c.get("relevance_score", 0.5)
            trend = rag_score if isinstance(rag_score, (int, float)) else 0.5

        # Factor 3: Budget Match
        budget = _score_budget(user_budget, place["price_level"])

        # Factor 4: Location Efficiency (Amap routing)
        location = location_scores[i] if i < len(location_scores) else 0.5

        # Factor 5: Time Match
        time_match = _score_time(travel_month, place["best_time"])

        # Factor 6: Data Reliability
        reliability = _get_reliability(
            place["source"],
            place.get("data_reliability", ""),
        )

        # Weighted total (Phase 12.2: adaptive weights + diversity)
        total = (
            w_pref * pref +
            w_trend * trend +
            w_budget * budget +
            w_loc * location +
            w_time * time_match +
            w_rel * reliability
        )
        # Apply diversity penalty
        total *= diversity_penalties[i] if i < len(diversity_penalties) else 1.0

        # Phase 12.16: Weather-aware indoor boost (same logic as RAG retriever)
        weather_boost = 0.0
        if weather:
            # Compute rain_ratio once, cache in closure-like way via first iteration
            if i == 0:
                # Inline rain_ratio: how many days in forecast are rainy
                daily = weather.get("daily") or []
                rainy = sum(1 for d in daily if isinstance(d, dict) and (
                    any(w in (d.get("weather_desc", "") or "") for w in ("雨", "雷", "雪", "阵雨", "暴雨"))
                    or (d.get("precipitation", 0) or 0) > 0.5
                    or (d.get("weather_code", 0) or 0) >= 50
                ))
                # Store on the weather dict as a transient cache (not persisted)
                weather["_rain_ratio"] = rainy / len(daily) if daily else 0.0
            rain_ratio = weather.get("_rain_ratio", 0.0)
            if rain_ratio >= 0.2:
                try:
                    from app.agents.itinerary_contract import classify_poi_indoor
                    poi_name = place.get("name", "") or ""
                    poi_tags = place.get("tags", [])
                    if isinstance(poi_tags, str):
                        poi_tags = [t.strip() for t in poi_tags.split(",") if t.strip()]
                    classification = classify_poi_indoor(poi_name, kb_tags=poi_tags if poi_tags else None)
                    if classification in ("indoor", "semi"):
                        weather_boost = 0.20 * rain_ratio
                    else:
                        weather_boost = -0.10 * rain_ratio
                except ImportError:
                    pass
        total += weather_boost

        # Build enriched result from the NORMALIZED flat fields — NOT from
        # place["_original"], which keeps RAG candidates' nested Chroma shape
        # ({metadata: {...}}) and would blank out name/city/tags in API responses.
        result = {k: v for k, v in place.items() if k != "_original"}
        result["total_score"] = round(total, 4)
        result["_trend_source"] = trend_source
        result["_score_breakdown"] = {
            "preference_match": round(pref, 3),
            "trend_heat": round(trend, 3),
            "budget_match": round(budget, 3),
            "location_efficiency": round(location, 3),
            "time_match": round(time_match, 3),
            "data_reliability": round(reliability, 3),
            "weather": round(weather_boost, 3),
        }
        scored.append(result)

    # ── Supplement with trending places ─────────────────
    # Trend entries that don't have a matching attraction in the KB
    # are added as supplementary recommendations (with reduced data quality).
    if trends:
        from app.agents.trend_agent import _fuzzy_match_name
        scored_names = {r.get("name", ""): r.get("tags", []) for r in scored}
        # Also check fuzzy matches against scored names
        def _already_covered(trend_name: str) -> bool:
            for sname, stags in scored_names.items():
                if _fuzzy_match_name(trend_name, sname):
                    # Phase 12.20: 餐厅名含地标名（如"老甘家…(洪崖洞店)"）
                    # 不算覆盖地标——否则洪崖洞永远被自家门口的餐厅抑制
                    if sname != trend_name and isinstance(stags, list) and any(
                        kw in t for t in stags
                        for kw in ("美食", "中餐", "海鲜", "火锅", "小吃", "餐")
                    ):
                        continue
                    return True
            return False

        for t in trends:
            tname = t.get("place_name", "")
            if not tname or _already_covered(tname):
                continue

            ttag = t.get("tag", "")
            tscore = t.get("effective_score", t.get("normalized_score", 0.5))

            # Build a synthetic recommendation from trend data
            trend_rec = {
                "name": tname,
                "city": profile.get("destination", ""),
                "tags": [ttag] if ttag else [],
                "price_level": "适中",
                "popularity_score": int(tscore * 10),
                "best_time": "全年",
                "suitable_for": "所有人",
                "source": f"trend:{t.get('source', 'unknown')}",
                "total_score": round(
                    W_PREFERENCE * (0.5 if not user_tags or ttag in user_tags else 0.2) +
                    W_TREND * tscore +
                    W_BUDGET * 0.5 +
                    W_LOCATION * 0.5 +
                    W_TIME * 0.5 +
                    W_RELIABILITY * 0.6,  # trend data is moderately reliable
                    4,
                ),
                "_score_breakdown": {
                    "preference_match": round(0.5 if not user_tags or ttag in user_tags else 0.2, 3),
                    "trend_heat": round(tscore, 3),
                    "budget_match": 0.5,
                    "location_efficiency": 0.5,
                    "time_match": 0.5,
                    "data_reliability": 0.6,
                },
            }
            scored.append(trend_rec)

    # Sort by total score descending
    scored.sort(key=lambda x: x["total_score"], reverse=True)

    logger.info(
        f"Recommendation: scored {len(scored)} candidates — "
        f"top: '{scored[0].get('name', '?')}' "
        f"({scored[0]['total_score']:.3f})"
    )
    return scored

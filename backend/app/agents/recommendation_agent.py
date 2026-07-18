"""
TravelMind Agent — Recommendation Agent

6-factor weighted scoring for attraction ranking.

Formula (from architecture.md):
  Score = 0.35 × Preference_Match     (user tags vs place tags cosine-like overlap)
        + 0.25 × Trend_Heat           (from trend_agent / trends.json)
        + 0.15 × Budget_Match         (user budget vs place price_level)
        + 0.10 × Location_Efficiency  (placeholder — Baidu routing in Phase 4)
        + 0.10 × Time_Match           (best_time vs travel month)
        + 0.05 × Data_Reliability     (source credibility weight)

Usage:
    from app.agents.recommendation_agent import recommend
    ranked = await recommend(profile, candidates, trends)
"""

import asyncio
import logging
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

W_PREFERENCE = 0.35
W_TREND = 0.25
W_BUDGET = 0.15
W_LOCATION = 0.10
W_TIME = 0.10
W_RELIABILITY = 0.05

# ── Budget mapping ───────────────────────────────────────

BUDGET_MAP = {
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

BUDGET_LEVELS = ["经济", "适中", "高端"]


def _budget_to_level(budget: str) -> str:
    """Normalize a budget description to one of: 经济/适中/高端."""
    for key, level in BUDGET_MAP.items():
        if key in budget:
            return level
    return "适中"


# ── Season / Month mapping ──────────────────────────────

SEASON_MONTHS = {
    "春季": {3, 4, 5},
    "夏季": {6, 7, 8},
    "秋季": {9, 10, 11},
    "冬季": {12, 1, 2},
}

MONTH_NAMES = {
    1: "一月", 2: "二月", 3: "三月", 4: "四月",
    5: "五月", 6: "六月", 7: "七月", 8: "八月",
    9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
}


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
    import re
    month_pattern = re.findall(r"(\d{1,2})\s*月", best_time)
    for m_str in month_pattern:
        m = int(m_str)
        if 1 <= m <= 12:
            months.add(m)

    return months if months else set(range(1, 13))


# ── Data source reliability ──────────────────────────────

SOURCE_RELIABILITY = {
    "wikidata+amap": 0.9,
    "wikidata": 0.7,
    "amap": 0.8,
}


def _get_reliability(source: str) -> float:
    """Return reliability score for a data source."""
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
    """Score budget match: 1.0 exact, 0.6 one level off, 0.2 two levels off."""
    if not user_budget:
        return 0.5  # neutral

    user_level = _budget_to_level(user_budget)
    if not place_price or place_price not in BUDGET_LEVELS:
        return 0.5  # neutral — place price unknown

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
    """
    meta = place.get("metadata", {})
    if meta:
        return {
            "name": meta.get("name", place.get("name", "")),
            "city": meta.get("city", place.get("city", "")),
            "tags": _parse_tags(meta.get("tags", "")),
            "price_level": meta.get("price_level", "适中"),
            "popularity_score": _safe_float(meta.get("popularity_score"), 5),
            "best_time": meta.get("best_time", "全年"),
            "suitable_for": meta.get("suitable_for", ""),
            "source": meta.get("source", place.get("source", "")),
            "lat": _safe_float(meta.get("lat")),
            "lon": _safe_float(meta.get("lon")),
            # Preserve original data
            "_original": place,
        }
    # Flat structure (from data pipeline directly)
    return {
        "name": place.get("name", ""),
        "city": place.get("city", ""),
        "tags": place.get("tags", []) or [],
        "price_level": place.get("price_level", "适中"),
        "popularity_score": _safe_float(place.get("popularity_score"), 5),
        "best_time": place.get("best_time", "全年"),
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
) -> List[Dict[str, Any]]:
    """Score and rank candidate attractions using the 6-factor formula.

    Args:
        profile: User profile dict with keys:
            - tags: list of interest tags
            - budget_level / budget: budget description
            - travel_month: 1-12 (optional)
        candidates: List of candidate attractions from RAG retrieval.
        trends: Optional pre-loaded trend data from trend_agent.

    Returns:
        Candidates sorted by total_score (descending), each with
        '_score_breakdown' showing all 6 factor scores.
    """
    if not candidates:
        logger.warning("No candidates to score")
        return []

    # Extract user preferences
    user_tags = profile.get("tags", []) or []
    user_budget = profile.get("budget_level", "") or profile.get("budget", "") or ""
    travel_month = profile.get("travel_month", 0)

    # Build trend lookup dict for fast access
    trend_map: Dict[str, float] = {}
    if trends:
        for t in trends:
            name = t.get("place_name", "")
            if name:
                # Use effective_score if available, otherwise normalized_score
                score = t.get("effective_score", t.get("normalized_score", 0.5))
                trend_map[name] = score

    # ── Location Efficiency (Amap distance matrix) ─────
    # Compute real location efficiency scores via Amap routing.
    # Falls back to 0.5 if Amap is unavailable or coords are missing.
    location_scores: List[float] = [0.5] * len(candidates)
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
        # Check trend_map first, then fuzzy match
        trend = trend_map.get(place_name, None)
        if trend is None and trends:
            from app.agents.trend_agent import get_trend_score
            trend = get_trend_score(place_name, place["city"], trends)
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
        reliability = _get_reliability(place["source"])

        # Weighted total
        total = (
            W_PREFERENCE * pref +
            W_TREND * trend +
            W_BUDGET * budget +
            W_LOCATION * location +
            W_TIME * time_match +
            W_RELIABILITY * reliability
        )

        # Build enriched result
        result = dict(place["_original"])
        result["total_score"] = round(total, 4)
        result["_score_breakdown"] = {
            "preference_match": round(pref, 3),
            "trend_heat": round(trend, 3),
            "budget_match": round(budget, 3),
            "location_efficiency": round(location, 3),
            "time_match": round(time_match, 3),
            "data_reliability": round(reliability, 3),
        }
        scored.append(result)

    # ── Supplement with trending places ─────────────────
    # Trend entries that don't have a matching attraction in the KB
    # are added as supplementary recommendations (with reduced data quality).
    if trends:
        from app.agents.trend_agent import _fuzzy_match_name
        scored_names = {r.get("name", "") for r in scored}
        # Also check fuzzy matches against scored names
        def _already_covered(trend_name: str) -> bool:
            for sname in scored_names:
                if _fuzzy_match_name(trend_name, sname):
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

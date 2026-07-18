"""
TravelMind Agent — Trend Analysis Agent

Analyzes trending places for a given city from trends.json.

The trend data is manually curated from public hot lists (Ctrip, Mafengwo,
Xiaohongshu, Douyin) and provides a baseline for the Trend_Heat factor
in the recommendation scoring formula.

Usage:
    from app.agents.trend_agent import analyze_trends
    trends = await analyze_trends("重庆", ["美食", "夜景"])
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Data loading ──────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TRENDS_FILE = _DATA_DIR / "trends.json"

_trends_cache: Optional[List[Dict[str, Any]]] = None


def _load_trends() -> List[Dict[str, Any]]:
    """Load trends from JSON, caching in memory."""
    global _trends_cache
    if _trends_cache is not None:
        return _trends_cache

    if not _TRENDS_FILE.exists():
        logger.warning(f"Trends file not found: {_TRENDS_FILE}")
        _trends_cache = []
        return _trends_cache

    try:
        with open(_TRENDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _trends_cache = data.get("trends", [])
        logger.debug(f"Loaded {len(_trends_cache)} trend entries")
    except Exception as e:
        logger.error(f"Failed to load trends: {e}")
        _trends_cache = []

    return _trends_cache


# ── Core Logic ────────────────────────────────────────────


def _normalize_score(heat_score: int) -> float:
    """Normalize a 0-100 heat score to 0.0-1.0."""
    return max(0.0, min(1.0, heat_score / 100.0))


def _fuzzy_match_name(trend_name: str, place_name: str) -> bool:
    """Check if a trend entry matches a place name.

    Uses multi-strategy matching:
      1. Exact match
      2. Substring containment
      3. Shared core substring (for "重庆磁器口" ↔ "磁器口古镇")
    """
    if not trend_name or not place_name:
        return False
    tn = trend_name.strip()
    pn = place_name.strip()

    # 1. Exact match
    if tn == pn:
        return True

    # 2. Substring containment
    if tn in pn or pn in tn:
        return True

    # 3. Core name overlap — strip common city prefixes / suffixes and compare
    # Common prefixes: city names like 重庆, 成都, 北京
    # Common suffixes: 风景区, 景区, 公园, 古镇, 博物馆, etc.
    _COMMON_PREFIXES = [
        "重庆", "成都", "北京", "上海", "广州", "深圳", "杭州",
        "西安", "长沙", "厦门", "大理", "南京", "武汉", "苏州",
    ]
    _COMMON_SUFFIXES = [
        "风景区", "景区", "公园", "古镇", "博物馆", "博物院",
        "旅游区", "游览区", "步行街", "商业街", "风景区",
        "国家级自然保护区", "省级", "国家森林公园",
    ]

    def _strip_affixes(s: str) -> str:
        for prefix in _COMMON_PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        for suffix in _COMMON_SUFFIXES:
            if s.endswith(suffix) and len(s) > len(suffix) + 1:
                s = s[:-len(suffix)]
        return s.strip()

    core_tn = _strip_affixes(tn)
    core_pn = _strip_affixes(pn)

    if not core_tn or not core_pn:
        return False

    # Check core-to-core containment
    if core_tn in core_pn or core_pn in core_tn:
        return True

    # 4. Shared 3+ character substring
    for i in range(len(core_tn) - 2):
        chunk = core_tn[i:i + 3]
        if chunk in core_pn:
            return True

    return False


async def analyze_trends(
    city: str,
    tags: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Analyze trending places for a city, optionally filtered by user tags.

    Args:
        city: Target city name (e.g. "重庆").
        tags: Optional list of user interest tags for relevance boosting.

    Returns:
        List of trend dicts, each with:
          - place_name: str
          - tag: primary tag
          - heat_score: 0-100 raw score
          - normalized_score: 0.0-1.0 normalized
          - tag_boost: 0.0-1.0 extra boost if user tags match
          - effective_score: final trend score (normalized + 0.5*tag_boost, capped at 1.0)
          - source: data source (douyin_hot, xiaohongshu, ctrip_hot)
    """
    all_trends = _load_trends()
    tags = tags or []
    tag_set = set(tags)

    # Filter by city
    city_trends = [t for t in all_trends if t.get("city") == city]

    if not city_trends:
        logger.debug(f"No trend data for city: {city}")
        # Return empty — caller should handle gracefully
        return []

    # Normalize and optionally boost by tag overlap
    result = []
    for t in city_trends:
        normalized = _normalize_score(t.get("heat_score", 50))
        trend_tag = t.get("tag", "")
        # Tag boost: +0.2 per matching tag (max 0.4)
        tag_match_count = sum(1 for ut in tag_set if ut == trend_tag)
        tag_boost = min(0.4, tag_match_count * 0.2)

        effective = min(1.0, normalized + 0.5 * tag_boost)

        result.append({
            "place_name": t.get("place_name", ""),
            "tag": trend_tag,
            "heat_score": t.get("heat_score", 50),
            "rank": t.get("rank", 99),
            "normalized_score": round(normalized, 3),
            "tag_boost": round(tag_boost, 3),
            "effective_score": round(effective, 3),
            "source": t.get("source", "unknown"),
        })

    # Sort by effective score descending
    result.sort(key=lambda x: x["effective_score"], reverse=True)

    logger.info(
        f"Trend analysis for {city}: {len(result)} trends "
        f"(tags={tags}, top='{result[0]['place_name']}' "
        f"score={result[0]['effective_score']:.2f})"
    )
    return result


def get_trend_score(
    place_name: str,
    city: str,
    trends: Optional[List[Dict[str, Any]]] = None,
) -> float:
    """Look up the trend heat score for a specific place.

    Used by the recommendation agent to incorporate trend data
    into the 6-factor scoring formula.

    Args:
        place_name: Name of the attraction.
        city: City name (fallback if trends not pre-loaded).
        trends: Pre-loaded trend list (from analyze_trends). If None, loads from file.

    Returns:
        Normalized trend score 0.0-1.0 (0.5 if no trend data found).
    """
    if trends is None:
        all_trends = _load_trends()
        trends = [t for t in all_trends if t.get("city") == city]

    if not trends:
        return 0.5

    for t in trends:
        trend_name = t.get("place_name", "")
        if _fuzzy_match_name(trend_name, place_name):
            return _normalize_score(t.get("heat_score", 50))

    return 0.5

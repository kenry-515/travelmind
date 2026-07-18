"""
TravelMind Agent — RAG Retriever

Semantic search with multi-factor filtering for attractions.

Main entry points:
  - retrieve(profile, query, top_k)  →  List of attractions with scores
  - retrieve_by_preferences(tags, city, ...)  →  Multi-factor filtered results

Combines:
  1. Semantic similarity   (embedding → Chroma search)
  2. City filter            (metadata filter on city)
  3. Budget filter          (price_level match)
  4. Tag boost              (tag overlap bonus)
  5. Popularity boost       (popularity_score weighting)
"""

import logging
from typing import Any, Dict, List, Optional

from app.rag.embedding import BaseEmbeddingProvider, get_embedding_provider
from app.rag.vector_store import ChromaStore, get_vector_store

logger = logging.getLogger(__name__)

# Scoring weights
WEIGHT_SIMILARITY = 0.45    # semantic similarity to query
WEIGHT_TAG_MATCH = 0.25     # tag overlap between user prefs and attraction
WEIGHT_POPULARITY = 0.15    # popularity score (1-10 normalized)
WEIGHT_BUDGET = 0.10        # budget level match
WEIGHT_TIME = 0.05          # seasonal suitability


# ── Public API ───────────────────────────────────────────


async def retrieve(
    user_profile: Dict[str, Any],
    query: str = "",
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """Main retrieval function.

    Builds a semantic query from user_profile, searches the vector store,
    and returns ranked attractions with score breakdowns.

    Args:
        user_profile: Extracted user profile dict from Profile Agent.
            Expected keys: destination, tags, budget_level, days, travel_style,
            companions, constraints.
        query: Optional override query string. If empty, auto-generated from profile.
        top_k: Number of results to return.

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
        return []

    # Re-rank with multi-factor scoring
    scored = _rerank(
        raw_results,
        user_tags=tags,
        user_budget=budget,
        user_travel_style=travel_style,
        travel_month=travel_month,
    )

    # Return top-k
    return scored[:top_k]


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
) -> List[Dict[str, Any]]:
    """Re-rank Chroma results with multi-factor scoring.

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

        # Weighted total
        total = (
            WEIGHT_SIMILARITY * sim_score +
            WEIGHT_TAG_MATCH * tag_score +
            WEIGHT_POPULARITY * pop_score +
            WEIGHT_BUDGET * budget_score +
            WEIGHT_TIME * time_score
        )

        item["relevance_score"] = round(total, 4)
        item["_score_breakdown"] = {
            "similarity": round(sim_score, 3),
            "tag_match": round(tag_score, 3),
            "popularity": round(pop_score, 3),
            "budget": round(budget_score, 3),
            "season": round(time_score, 3),
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

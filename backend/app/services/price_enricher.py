"""
TravelMind Agent — Price Enricher (Phase 7)

Post-processing module that enriches LLM-generated itineraries with real
price data from the attraction knowledge base. Runs AFTER LLM generation
and BEFORE contract validation finalization.

Core responsibilities:
  1. Match itinerary POI names to knowledge-base attractions (fuzzy)
  2. Inject price_range, price_source, price_updated_at, booking_url
  3. Compute price_summary with budget comparison and staleness detection

All price data originates from attractions.json — zero hardcoded prices.
"""

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

from app.agents.route_optimizer import _normalize, _core_name
from app.services.name_normalizer import poi_names_match

# ── Constants ──────────────────────────────────────────────

_STALE_DAYS = 90  # prices older than this are flagged as potentially stale

# price_enricher uses a different suffix list than route_optimizer
# for matching POI names to knowledge-base entries
_PRICE_GENERIC_SUFFIXES = (
    "景区", "风景区", "旅游区", "公园", "广场", "步行街",
    "博物馆", "纪念馆", "故居", "寺庙", "道观", "教堂",
    "古镇", "古村", "老街", "遗址", "故城",
)


# ── Booking URL generation ─────────────────────────────────


def build_booking_url(name: str, city: str = "", amap_id: Optional[str] = None) -> str:
    """Generate a booking/price-check deeplink for a POI.

    Priority:
      1. Amap POI detail page (if amap_id available)
      2. Dianping keyword search fallback
    """
    if amap_id:
        return f"https://uri.amap.com/detail?poiid={amap_id}"

    # Fallback: Dianping search
    search_term = f"{name} {city}".strip() if city else name
    encoded = quote(search_term)
    return f"https://m.dianping.com/search/keyword/{encoded}"


# ── Price lookup ────────────────────────────────────────────


def _build_lookup(
    attractions: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a name-indexed lookup from a list of attraction dicts.

    Keys: both full name and core name for fuzzy matching.
    """
    lookup: Dict[str, Dict[str, Any]] = {}
    for attr in attractions:
        name = attr.get("name", "")
        if not name:
            continue
        norm = _normalize(name)
        if norm not in lookup:
            lookup[norm] = attr
        core = _core_name(norm, suffixes=_PRICE_GENERIC_SUFFIXES)
        if core and core not in lookup:
            lookup[core] = attr
    return lookup


def _find_attraction(
    poi_name: str,
    lookup: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the best-matching attraction from the lookup.

    Tries: exact normalized match → substring match → core name match.
    """
    norm = _normalize(poi_name)
    if not norm:
        return None

    # 1. Exact normalized match
    if norm in lookup:
        return lookup[norm]

    # 2. Check all keys for substring containment
    for key, attr in lookup.items():
        if poi_names_match(poi_name, key):
            return attr

    return None


# ── Staleness ───────────────────────────────────────────────


def is_stale(updated_at: str) -> bool:
    """True if the price was updated more than _STALE_DAYS ago."""
    if not updated_at:
        return True
    try:
        updated = datetime.strptime(updated_at, "%Y-%m-%d").date()
        return (date.today() - updated).days > _STALE_DAYS
    except (ValueError, TypeError):
        return True


# ── Price summary ───────────────────────────────────────────


def compute_price_summary(
    data: Dict[str, Any],
    user_budget: str = "",
) -> Dict[str, Any]:
    """Compute aggregate price statistics for the itinerary.

    Args:
        data: The enriched itinerary dict (price fields already injected).
        user_budget: The user's budget level string (经济/适中/舒适/高端/奢华).

    Returns:
        A price_summary dict suitable for the itinerary schema.
    """
    total_min = 0
    total_max = 0
    priced_count = 0
    total_count = 0
    stale_count = 0

    for day in data.get("days", []):
        for item in day.get("items", []):
            total_count += 1
            pr = item.get("price_range")
            if pr and isinstance(pr, dict):
                pmin = pr.get("min", 0)
                pmax = pr.get("max", 0)
                if pmax > 0 or pmin > 0:
                    total_min += pmin
                    total_max += pmax
                    priced_count += 1
                else:
                    # Free attraction — counted but adds zero
                    priced_count += 1
            # Check staleness
            updated = item.get("price_updated_at", "")
            if is_stale(updated):
                stale_count += 1

    # Budget comparison — Phase 12.29: 使用集中化的 BUDGET_PER_DAY
    from app.core.constants import BUDGET_PER_DAY
    budget_slot = BUDGET_PER_DAY.get(user_budget, BUDGET_PER_DAY["适中"])
    over_budget = total_max > budget_slot
    over_budget_warning = ""
    if over_budget:
        over_budget_warning = (
            f"门票总预算估算 ¥{total_min}-{total_max} 超出您的"
            f"「{user_budget or '适中'}」预算参考线 ¥{budget_slot}，"
            f"建议调整景点选择或预算预期。"
        )

    return {
        "total_estimate_min": total_min,
        "total_estimate_max": total_max,
        "priced_items": priced_count,
        "total_items": total_count,
        "stale_items": stale_count,
        "budget_slot": user_budget or "适中",
        "over_budget": over_budget,
        "over_budget_warning": over_budget_warning,
    }


# ── Main enrichment ─────────────────────────────────────────


def enrich_prices(
    data: Dict[str, Any],
    attractions: List[Dict[str, Any]],
    user_budget: str = "",
) -> Dict[str, Any]:
    """Inject real price data into every day item in the itinerary.

    Matches POI names against the attraction knowledge base, adds
    price_range / price_source / price_updated_at / booking_url,
    and computes a price_summary for the root object.

    Args:
        data: The LLM-generated itinerary dict (mutated in-place).
        attractions: List of attraction dicts from the KB (with price fields).
        user_budget: User's budget level for comparison.

    Returns:
        The same dict (mutated) with price fields injected.
    """
    if not data or not attractions:
        return data

    lookup = _build_lookup(attractions)
    city = (data.get("trip") or {}).get("city", "")
    enriched_count = 0

    for day in data.get("days", []):
        for item in day.get("items", []):
            poi_name = item.get("poi", "")
            if not poi_name:
                continue

            matched = _find_attraction(poi_name, lookup)
            if matched:
                item["price_range"] = matched.get("price_range", {"min": 0, "max": 0})
                item["price_source"] = matched.get("price_source", "")
                item["price_updated_at"] = matched.get("price_updated_at", "")
                item["booking_url"] = build_booking_url(
                    poi_name,
                    city=city,
                    amap_id=matched.get("amap_id"),
                )
                enriched_count += 1
            else:
                # No match — set empty defaults
                item["price_range"] = {"min": 0, "max": 0}
                item["price_source"] = ""
                item["price_updated_at"] = ""
                item["booking_url"] = build_booking_url(poi_name, city=city)

    # Compute aggregate summary
    data["price_summary"] = compute_price_summary(data, user_budget)

    logger.info(
        f"Price enrichment: {enriched_count} POIs matched, "
        f"total estimate ¥{data['price_summary']['total_estimate_min']}"
        f"-{data['price_summary']['total_estimate_max']}"
    )

    return data

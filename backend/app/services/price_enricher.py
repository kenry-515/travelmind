"""
TravelMind Agent — Price Enricher (Phase 7 + Runtime)

Post-processing module that enriches LLM-generated itineraries with real
price data. Runs AFTER LLM generation and BEFORE contract validation.

Two enrichment modes:
  1. STATIC (enrich_prices) — uses only the pre-fetched knowledge base
  2. RUNTIME (enrich_prices_runtime) — queries missing prices from external
     APIs at request time (Bing, Trip.com API, etc.)

Core responsibilities:
  1. Match itinerary POI names to knowledge-base attractions (fuzzy)
  2. Inject price_range, price_source, price_updated_at, booking_url
  3. Query missing prices at runtime via external APIs
  4. Compute price_summary with budget comparison and staleness detection

TRUTHFUL DATA ONLY — never fabricate prices.
"""

import asyncio
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
      2. Ctrip ticket search (better for attraction tickets)
      3. Dianping keyword search fallback
    """
    if amap_id:
        return f"https://uri.amap.com/detail?poiid={amap_id}"

    # Prefer Ctrip for attraction ticket search
    search_term = f"{name} {city}".strip() if city else name
    encoded = quote(search_term)
    return f"https://piao.ctrip.com/search?q={encoded}"


def build_query_links(name: str, city: str = "") -> Dict[str, str]:
    """Generate multi-platform query links for user self-service.

    Returns a dict of platform → URL for the user to check prices themselves.
    """
    search_term = f"{city} {name}".strip() if city else name
    encoded = quote(search_term)
    return {
        "ctrip": f"https://piao.ctrip.com/search?q={encoded}",
        "fliggy": f"https://s.alitrip.com/search_union.htm?keyword={encoded}",
        "amap": f"https://uri.amap.com/search?keyword={encoded}",
        "baidu": f"https://www.baidu.com/s?wd={encoded}+门票价格",
        "bing": f"https://cn.bing.com/search?q={encoded}+门票",
    }


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

    TRUTHFUL: Only count verified prices. Unverified prices are
    excluded from totals (they'll show as "待核实" to the user).

    Args:
        data: The enriched itinerary dict (price fields already injected).
        user_budget: The user's budget level string (经济/适中/舒适/高端/奢华).

    Returns:
        A price_summary dict suitable for the itinerary schema.
    """
    total_min = 0
    total_max = 0
    verified_count = 0
    free_count = 0
    unverified_count = 0
    total_count = 0
    stale_count = 0

    for day in data.get("days", []):
        for item in day.get("items", []):
            total_count += 1
            pr = item.get("price_range")
            is_verified = item.get("price_verifiable", False)

            if pr is not None and isinstance(pr, dict) and is_verified:
                pmin = pr.get("min", 0)
                pmax = pr.get("max", 0)
                if pmax > 0 or pmin > 0:
                    total_min += pmin
                    total_max += pmax
                    verified_count += 1
                else:
                    # Free but verified
                    verified_count += 1
                    free_count += 1
            else:
                unverified_count += 1

            # Check staleness for verified prices
            updated = item.get("price_updated_at", "")
            if is_verified and is_stale(updated):
                stale_count += 1

    # Budget comparison — only if we have enough verified prices
    from app.core.constants import BUDGET_PER_DAY
    budget_slot = BUDGET_PER_DAY.get(user_budget, BUDGET_PER_DAY["适中"])
    over_budget = total_max > budget_slot if verified_count > 0 else False
    over_budget_warning = ""
    if over_budget:
        over_budget_warning = (
            f"已核实门票合计 ¥{total_min}-{total_max}，"
            f"超出「{user_budget or '适中'}」预算参考线 ¥{budget_slot}。"
            f"其余 {unverified_count} 项门票价格待核实，建议自行查询。"
        )

    return {
        "total_estimate_min": total_min,
        "total_estimate_max": total_max,
        "verified_items": verified_count,
        "free_items": free_count,
        "unverified_items": unverified_count,
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
    """Inject verified price data into every day item in the itinerary.

    TRUTHFUL DATA ONLY:
    - If a POI has verified price data → inject it directly
    - If a POI lacks verified price data → mark as "待核实" with guidance
      for the user to look up on Amap/Ctrip themselves.
    - No fabricated estimates are ever injected.

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
    unverified_count = 0

    for day in data.get("days", []):
        for item in day.get("items", []):
            poi_name = item.get("poi", "")
            if not poi_name:
                continue

            matched = _find_attraction(poi_name, lookup)
            if matched:
                price = matched.get("price_range")
                price_verifiable = matched.get("price_verifiable", False)

                if price is not None and price_verifiable:
                    # Verified price — inject directly
                    item["price_range"] = price
                    item["price_source"] = matched.get("price_source", "") or "已核实"
                    item["price_updated_at"] = matched.get("price_updated_at", "") or ""
                    item["booking_url"] = build_booking_url(
                        poi_name,
                        city=city,
                        amap_id=matched.get("amap_id"),
                    )
                    item["price_verifiable"] = True
                    enriched_count += 1
                else:
                    # Price not verified — do NOT fabricate
                    # Show guidance for user to look up themselves
                    item["price_range"] = None
                    item["price_source"] = "价格未核实，建议自行查询"
                    item["price_updated_at"] = ""
                    item["booking_url"] = build_booking_url(poi_name, city=city)
                    item["query_links"] = build_query_links(poi_name, city=city)
                    item["price_verifiable"] = False
                    unverified_count += 1
            else:
                # No match in KB — cannot provide any price
                item["price_range"] = None
                item["price_source"] = "价格待核实"
                item["price_updated_at"] = ""
                item["booking_url"] = build_booking_url(poi_name, city=city)
                item["query_links"] = build_query_links(poi_name, city=city)
                item["price_verifiable"] = False
                unverified_count += 1

    # Compute aggregate summary
    data["price_summary"] = compute_price_summary(data, user_budget)

    logger.info(
        f"Price enrichment: {enriched_count} verified, "
        f"{unverified_count} need user lookup"
    )

    return data


# ── Runtime price enrichment ────────────────────────────────


async def enrich_prices_runtime(
    data: Dict[str, Any],
    attractions: List[Dict[str, Any]],
    user_budget: str = "",
    max_runtime_queries: int = 10,
) -> Dict[str, Any]:
    """Enrich prices with BOTH static KB AND runtime API queries.

    This is the PREFERRED enrichment method for production. It:
    1. First applies static enrichment (fast, from local KB)
    2. Then queries unverified items via runtime external APIs
    3. Updates items that received runtime price data
    4. Recomputes the price summary

    Args:
        data: The LLM-generated itinerary dict (mutated in-place).
        attractions: List of attraction dicts from the KB.
        user_budget: User's budget level for comparison.
        max_runtime_queries: Max number of runtime queries (to avoid abuse).

    Returns:
        The same dict (mutated) with price fields enriched.
    """
    if not data:
        return data

    # Step 1: Static enrichment first (fast)
    enrich_prices(data, attractions, user_budget)

    # Step 2: Collect items that still need runtime price queries
    items_to_query = []
    item_refs = []  # (day_idx, item_idx) for updating results

    for day_idx, day in enumerate(data.get("days", [])):
        for item_idx, item in enumerate(day.get("items", [])):
            if not item.get("poi"):
                continue
            if item.get("price_verifiable", False):
                continue  # Already verified, skip
            # Check if we should try runtime query
            pr = item.get("price_range")
            if pr is not None and item.get("price_verifiable", False):
                continue
            items_to_query.append(item["poi"])
            item_refs.append((day_idx, item_idx))

    if not items_to_query:
        logger.info("All prices verified from static KB, no runtime queries needed")
        return data

    # Limit the number of runtime queries to avoid slow responses
    if len(items_to_query) > max_runtime_queries:
        logger.info(
            f"Limiting runtime queries from {len(items_to_query)} to {max_runtime_queries}"
        )
        items_to_query = items_to_query[:max_runtime_queries]
        item_refs = item_refs[:max_runtime_queries]

    # Step 3: Run runtime queries concurrently
    city = (data.get("trip") or {}).get("city", "")

    try:
        from app.services.price_query_service import query_price_runtime

        tasks = [
            query_price_runtime(poi_name, city=city)
            for poi_name in items_to_query
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        runtime_hit = 0
        for i, (result, (day_idx, item_idx)) in enumerate(zip(results, item_refs)):
            if isinstance(result, Exception):
                logger.debug(f"Runtime query failed: {result}")
                continue

            item = data["days"][day_idx]["items"][item_idx]

            if result.get("price_verifiable", False) and result.get("price_range"):
                # Runtime query found a verified price
                item["price_range"] = result["price_range"]
                item["price_source"] = result.get("price_source", "Bing搜索")
                item["price_updated_at"] = result.get("price_updated_at", "")
                item["price_verifiable"] = True
                if result.get("booking_url"):
                    item["booking_url"] = result["booking_url"]
                if result.get("query_links"):
                    item["query_links"] = result["query_links"]
                runtime_hit += 1
            else:
                # Runtime query didn't find a price — keep the fallback links
                if result.get("booking_url"):
                    item["booking_url"] = result["booking_url"]
                if result.get("query_links"):
                    item["query_links"] = result["query_links"]

        logger.info(
            f"Runtime price query: {runtime_hit}/{len(items_to_query)} verified"
        )

    except Exception as e:
        logger.warning(f"Runtime price query failed (non-fatal): {e}")

    # Step 4: Recompute price summary with updated data
    data["price_summary"] = compute_price_summary(data, user_budget)

    return data

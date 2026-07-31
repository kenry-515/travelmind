"""
TravelMind Agent — Runtime Price Query Service

Runs external API queries at request time (not batch pre-fetch) to get
real-time ticket prices for attractions that are missing from the static
knowledge base.

Strategy:
  1. Try Bing search (cn.bing.com is accessible from China)
  2. Try Trip.com Open API (when API key available)
  3. Fall back to direct-link generation for user self-service
  4. Cache results for 7 days to avoid repeated queries

This service is the key architecture shift from "batch pre-fetch" to
"runtime on-demand query" — making it feasible to cover all Chinese
attractions without manual data entry.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────

_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "price_cache"
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_BING_TIMEOUT = 8  # seconds per query
_BING_SEM = asyncio.Semaphore(3)  # max 3 concurrent Bing requests

# ── Price pattern matching ──────────────────────────────────

# Patterns that indicate ticket prices in search results
_PRICE_PATTERNS = [
    # "门票XX元" or "门票XX-XX元"
    re.compile(r"门票\s*(\d+)\s*[-~到至]\s*(\d+)\s*元"),
    re.compile(r"门票\s*(\d+)\s*元"),
    # "票价XX元"
    re.compile(r"票价\s*(\d+)\s*[-~到至]\s*(\d+)\s*元"),
    re.compile(r"票价\s*(\d+)\s*元"),
    # "XX元/人"
    re.compile(r"(\d+)\s*[-~到至]\s*(\d+)\s*元\s*/\s*人"),
    re.compile(r"(\d+)\s*元\s*/\s*人"),
    # "XX元起"
    re.compile(r"(\d+)\s*元\s*起"),
    # "成人票XX元"
    re.compile(r"成人票\s*(\d+)\s*[-~到至]\s*(\d+)\s*元"),
    re.compile(r"成人票\s*(\d+)\s*元"),
    # "免费开放" / "免票"
    re.compile(r"(免费开放|免票|免费入园|免费景点|不收取门票)"),
]


def _extract_price(text: str) -> Optional[Dict[str, Any]]:
    """Extract price range from search result text.

    Returns a dict with min/max or None if no price found.
    """
    if not text:
        return None

    # Check for free indicators first
    for pattern in _PRICE_PATTERNS[-1:]:  # free patterns
        if pattern.search(text):
            return {"min": 0, "max": 0, "confidence": 0.8}

    # Check for numeric prices
    for pattern in _PRICE_PATTERNS[:-1]:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            if len(groups) == 2 and groups[1] is not None:
                pmin = int(groups[0])
                pmax = int(groups[1])
                if pmin <= pmax:
                    return {"min": pmin, "max": pmax, "confidence": 0.6}
            elif len(groups) >= 1 and groups[0] is not None:
                price = int(groups[0])
                return {"min": price, "max": price, "confidence": 0.7}

    return None


# ── Cache management ────────────────────────────────────────


def _cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "price_queries.json"


def _load_cache() -> Dict[str, Any]:
    path = _cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    try:
        _cache_path().write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except IOError as e:
        logger.warning(f"Failed to save price cache: {e}")


def _get_cached(poi_name: str, city: str) -> Optional[Dict[str, Any]]:
    """Get cached price result if still valid."""
    cache = _load_cache()
    key = f"{city}|{poi_name}"
    entry = cache.get(key)
    if not entry:
        return None
    ts = entry.get("timestamp", 0)
    if time.time() - ts > _CACHE_TTL_SECONDS:
        return None
    return entry.get("data")


def _set_cached(poi_name: str, city: str, data: Dict[str, Any]) -> None:
    """Cache a price result with timestamp."""
    cache = _load_cache()
    key = f"{city}|{poi_name}"
    cache[key] = {
        "timestamp": time.time(),
        "data": data,
    }
    _save_cache(cache)


# ── Bing search price query ────────────────────────────────

# Common headers to mimic a real browser
_BING_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def _query_bing_price(
    client: httpx.AsyncClient,
    poi_name: str,
    city: str = "",
) -> Optional[Dict[str, Any]]:
    """Query Bing search for attraction ticket price.

    Uses cn.bing.com which is accessible from China. The search
    results page often contains ticket price information in the
    description snippets.
    """
    async with _BING_SEM:
        search_term = f"{city} {poi_name} 门票价格".strip() if city else f"{poi_name} 门票价格"
        encoded = quote(search_term)
        url = f"https://cn.bing.com/search?q={encoded}"

        try:
            resp = await client.get(
                url,
                headers=_BING_HEADERS,
                follow_redirects=True,
                timeout=_BING_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.debug(f"Bing query failed ({resp.status_code}): {poi_name}")
                return None

            html = resp.text

            # Extract text snippets between tags
            text_snippets = re.findall(
                r'<li[^>]*class="b_algo"[^>]*>.*?<p[^>]*>(.*?)</p>',
                html,
                re.DOTALL,
            )
            if not text_snippets:
                # Fallback: try to find any text with price patterns
                text_snippets = re.findall(
                    r'<div[^>]*class="b_caption"[^>]*>.*?<p>(.*?)</p>',
                    html,
                    re.DOTALL,
                )

            # Clean HTML tags from snippets
            for snippet in text_snippets:
                clean = re.sub(r"<[^>]+>", "", snippet).strip()
                price = _extract_price(clean)
                if price:
                    return {
                        "price_range": {
                            "min": price["min"],
                            "max": price["max"],
                        },
                        "price_source": f"Bing搜索({poi_name}门票价¥{price['min']}-{price['max']})",
                        "price_updated_at": date.today().isoformat(),
                        "price_verifiable": True,
                        "query_source": "bing",
                    }

            # Also check full HTML for price patterns
            price = _extract_price(html)
            if price:
                return {
                    "price_range": {
                        "min": price["min"],
                        "max": price["max"],
                    },
                    "price_source": f"Bing搜索(页面票价¥{price['min']}-{price['max']})",
                    "price_updated_at": date.today().isoformat(),
                    "price_verifiable": True,
                    "query_source": "bing",
                }

            return None

        except Exception as e:
            logger.debug(f"Bing query error for {poi_name}: {e}")
            return None


# ── Trip.com API (placeholder for when key available) ──────

_TRIP_API_KEY = os.environ.get("TRIP_API_KEY", "")
_TRIP_API_BASE = "https://open.trip.com"


async def _query_trip_api(
    client: httpx.AsyncClient,
    poi_name: str,
    city: str = "",
) -> Optional[Dict[str, Any]]:
    """Query Trip.com Open API for attraction price.

    Requires API key from https://open.trip.com/ttd
    This is a placeholder — full implementation after registration.
    """
    if not _TRIP_API_KEY:
        return None

    try:
        search_term = f"{city} {poi_name}" if city else poi_name
        url = f"{_TRIP_API_BASE}/v2/search/attractions"
        headers = {
            "Authorization": f"Bearer {_TRIP_API_KEY}",
            "Content-Type": "application/json",
        }
        params = {"keyword": search_term, "language": "zh-CN"}

        resp = await client.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        attractions = data.get("data", {}).get("attractions", [])
        if not attractions:
            return None

        # Take the first match
        attr = attractions[0]
        ticket = attr.get("ticket", {})
        min_price = ticket.get("min_price", 0)
        max_price = ticket.get("max_price", min_price)

        if min_price > 0:
            return {
                "price_range": {"min": min_price, "max": max_price},
                "price_source": "Trip.com API",
                "price_updated_at": date.today().isoformat(),
                "price_verifiable": True,
                "query_source": "trip_api",
            }
        elif ticket.get("free", False):
            return {
                "price_range": {"min": 0, "max": 0},
                "price_source": "Trip.com API(免费景点)",
                "price_updated_at": date.today().isoformat(),
                "price_verifiable": True,
                "query_source": "trip_api",
            }

        return None

    except Exception as e:
        logger.debug(f"Trip API error for {poi_name}: {e}")
        return None


# ── Search direct link generation ─────────────────────────


def generate_query_links(poi_name: str, city: str = "") -> Dict[str, str]:
    """Generate direct search/deeplink URLs for user self-service.

    When we cannot fetch a price, we provide links for the user to
    check themselves on major travel platforms.
    """
    search_term = f"{poi_name}"
    if city:
        search_term = f"{city} {poi_name}"
    encoded = quote(search_term)

    return {
        "ctrip": f"https://piao.ctrip.com/search?q={encoded}",
        "fliggy": f"https://s.alitrip.com/search_union.htm?keyword={encoded}",
        "amap": f"https://uri.amap.com/search?keyword={encoded}",
        "baidu": f"https://www.baidu.com/s?wd={encoded}+门票价格",
        "bing": f"https://cn.bing.com/search?q={encoded}+门票",
    }


def build_best_booking_url(
    poi_name: str,
    city: str = "",
    amap_id: Optional[str] = None,
) -> str:
    """Build the best available booking/price-check URL.

    Priority: amap POI detail > Ctrip search > Amap search.
    """
    if amap_id:
        return f"https://uri.amap.com/detail?poiid={amap_id}"

    links = generate_query_links(poi_name, city)
    return links["ctrip"]


# ── Main runtime query ─────────────────────────────────────


async def query_price_runtime(
    poi_name: str,
    city: str = "",
    amap_id: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Query ticket price at runtime from external APIs.

    This is the MAIN entry point for runtime price queries.
    It implements a cascading strategy:

    1. Check local cache (7-day TTL)
    2. Try Trip.com API (if key available)
    3. Try Bing search
    4. Generate fallback links for user self-service

    Args:
        poi_name: The attraction name.
        city: The city name (improves search accuracy).
        amap_id: Amap POI ID for deep links.
        use_cache: Whether to use local cache.

    Returns:
        A dict with price data and fallback links. Always returns
        a usable result — never leaves the caller without guidance.
    """
    # 1. Check cache
    if use_cache:
        cached = _get_cached(poi_name, city)
        if cached is not None:
            cached["cached"] = True
            return cached

    # 2. Try online sources
    async with httpx.AsyncClient(timeout=15) as client:
        # 2a. Try Trip.com API
        result = await _query_trip_api(client, poi_name, city)
        if result:
            result["booking_url"] = build_best_booking_url(poi_name, city, amap_id)
            result["query_links"] = generate_query_links(poi_name, city)
            result["cached"] = False
            _set_cached(poi_name, city, result)
            return result

        # 2b. Try Bing search
        result = await _query_bing_price(client, poi_name, city)
        if result:
            result["booking_url"] = build_best_booking_url(poi_name, city, amap_id)
            result["query_links"] = generate_query_links(poi_name, city)
            result["cached"] = False
            _set_cached(poi_name, city, result)
            return result

    # 3. No price found — return guidance for user self-service
    fallback = {
        "price_range": None,
        "price_source": "价格未核实，建议自行查询",
        "price_updated_at": "",
        "price_verifiable": False,
        "booking_url": build_best_booking_url(poi_name, city, amap_id),
        "query_links": generate_query_links(poi_name, city),
        "cached": False,
        "query_source": "fallback",
    }

    # Cache the negative result too to avoid repeated queries
    _set_cached(poi_name, city, fallback)
    return fallback


# ── Batch async query ───────────────────────────────────────


async def batch_query_prices(
    items: List[Tuple[str, str, Optional[str]]],
    max_concurrent: int = 5,
) -> List[Dict[str, Any]]:
    """Query prices for multiple POIs concurrently.

    Args:
        items: List of (poi_name, city, amap_id) tuples.
        max_concurrent: Maximum concurrent queries.

    Returns:
        List of result dicts in the same order.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _query_one(item):
        async with sem:
            return await query_price_runtime(*item)

    tasks = [_query_one(item) for item in items]
    return await asyncio.gather(*tasks)


# ── Cache management commands ──────────────────────────────


def clear_price_cache() -> int:
    """Clear all cached price queries. Returns number of entries cleared."""
    cache = _load_cache()
    count = len(cache)
    path = _cache_path()
    if path.exists():
        path.unlink()
    logger.info(f"Cleared {count} cached price queries")
    return count


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the price cache."""
    cache = _load_cache()
    now = time.time()
    active = 0
    expired = 0
    for entry in cache.values():
        ts = entry.get("timestamp", 0)
        if now - ts > _CACHE_TTL_SECONDS:
            expired += 1
        else:
            active += 1
    return {
        "total_entries": len(cache),
        "active_entries": active,
        "expired_entries": expired,
        "cache_file": str(_cache_path()),
    }
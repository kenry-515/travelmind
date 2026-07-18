"""
TravelMind Agent — Amap POI Enricher

Uses Amap (高德地图) POI Search API to:
  1. Verify coordinates and add address/photo for existing Wikidata attractions
  2. Supplement cities that have too few attractions (成都/广州/厦门/大理)
  3. Deduplicate by name similarity and coordinate proximity

Amap free tier: 5000 calls/day, 30 QPS. We stay well under that.

Input:  data/wikipedia_enriched.json
Output: data/amap_enriched.json

Usage:
  cd backend
  python scripts/enrich_amap.py
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "wikipedia_enriched.json"
OUTPUT_FILE = DATA_DIR / "amap_enriched.json"

# Amap API
AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"
AMAP_AROUND_URL = "https://restapi.amap.com/v3/place/around"

# POI types for tourist attractions (Amap classification)
# 110000 = scenic spots, 110100 = famous scenery, 110200 = park squares,
# 140000 = museum, 080000 = entertainment
TOURIST_TYPES = "110000|110100|110200|140000"

# Search keywords for supplementing low-count cities
SUPPLEMENT_KEYWORDS = [
    "旅游景点", "公园", "博物馆", "古镇", "寺庙",
    "网红打卡", "历史遗址", "自然风光", "夜市",
]

# Cities that need supplementation (from data-strategy.md)
TARGET_COUNTS = {
    "重庆": 50,
    "成都": 50,
    "广州": 30,
    "北京": 50,
    "上海": 40,
    "西安": 30,
    "杭州": 30,
    "长沙": 25,
    "厦门": 25,
    "大理": 20,
    # ── Phase 6 expansion cities ──
    "三亚": 30,
    "桂林": 30,
    "苏州": 30,
    "张家界": 25,
    "丽江": 25,
}

USER_AGENT = "TravelMindAgent/0.1"

# Concurrency / rate limiting
MAX_CONCURRENT = 3   # be polite to Amap
DELAY_BETWEEN = 0.35  # ~3 req/s — well under 30 QPS limit
MAX_RETRIES = 2

# Dedup: attractions within DEDUP_RADIUS_M metres are considered duplicates
DEDUP_RADIUS_M = 500


# ── Helpers ──────────────────────────────────────────────


def _load_settings():
    """Load Amap API key and optional sign key from project config."""
    try:
        from app.config.settings import settings
        return settings.AMAP_API_KEY, getattr(settings, "AMAP_SIGN_KEY", "")
    except ImportError:
        import os
        api_key = os.getenv("AMAP_API_KEY", "")
        sign_key = os.getenv("AMAP_SIGN_KEY", "")
        # If still empty, try loading from .env via pydantic-settings
        if not api_key:
            try:
                from pydantic_settings import BaseSettings
                class _AmapEnv(BaseSettings):
                    AMAP_API_KEY: str = ""
                    AMAP_SIGN_KEY: str = ""
                    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True, "extra": "ignore"}
                _e = _AmapEnv()
                api_key = _e.AMAP_API_KEY
                sign_key = _e.AMAP_SIGN_KEY
            except ImportError:
                pass
        return api_key, sign_key


def _amap_sign(params: Dict[str, Any], sign_key: str) -> str:
    """Compute Amap digital signature (MD5).

    Algorithm: sort params by key → concat as k1=v1&k2=v2...
    → append sign_key → MD5 hash.

    Args:
        params: API request parameters (without sig).
        sign_key: The 数字签名私钥 from Amap console.

    Returns:
        32-character lowercase MD5 hex digest.
    """
    # Sort by key and build query string
    sorted_keys = sorted(params.keys())
    raw = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    raw += sign_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in metres between two (lat, lon) points."""
    R = 6371000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize_name(name: str) -> str:
    """Normalize a place name for fuzzy dedup comparison."""
    n = name.strip()
    # Remove common suffixes
    for suffix in ["风景区", "景区", "公园", "旅游区", "游览区"]:
        if n.endswith(suffix) and len(n) > len(suffix) + 1:
            n = n[:-len(suffix)]
    # Remove brackets and their content
    n = re.sub(r"[（(][^)）]*[)）]", "", n)
    return n.strip()


def _coords_match(lat1, lon1, lat2, lon2, radius_m=DEDUP_RADIUS_M):
    """Check if two coordinate pairs are within radius_m of each other."""
    if not all([lat1, lon1, lat2, lon2]):
        return False
    return haversine(lat1, lon1, lat2, lon2) <= radius_m


def _parse_amap_poi(poi: Dict[str, Any], city: str) -> Dict[str, Any]:
    """Convert an Amap POI result into our standard attraction format."""
    location = poi.get("location", "")
    lon_str, lat_str = ("", "")
    if location and "," in location:
        lon_str, lat_str = location.split(",", 1)

    photos = poi.get("photos", [])
    photo_url = ""
    if photos and isinstance(photos, list):
        photo_url = photos[0].get("url", "")

    return {
        "name": poi.get("name", "").strip(),
        "city": city,
        "lat": float(lat_str) if lat_str else None,
        "lon": float(lon_str) if lon_str else None,
        "address": poi.get("address", ""),
        "amap_id": poi.get("id", ""),
        "amap_type": poi.get("type", ""),
        "amap_typecode": poi.get("typecode", ""),
        "photo_url": photo_url,
        "source": "amap",
    }


# ── Amap API client ─────────────────────────────────────


async def amap_search(
    client: httpx.AsyncClient,
    api_key: str,
    keywords: str,
    city: str,
    types: str = TOURIST_TYPES,
    city_limit: bool = True,
    offset: int = 20,
    page: int = 1,
    sign_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Call Amap text search API with retries and optional digital signing."""
    params = {
        "key": api_key,
        "keywords": keywords,
        "types": types,
        "city": city,
        "citylimit": "true" if city_limit else "false",
        "offset": str(offset),
        "page": str(page),
        "extensions": "all",
        "output": "JSON",
    }

    # Add digital signature if sign_key is provided
    if sign_key:
        params["sig"] = _amap_sign(params, sign_key)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.get(
                AMAP_SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code == 429:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "1":
                logger.debug(f"  Amap API error: {data.get('info')} for '{keywords}' in {city}")
                return None
            return data
        except Exception as e:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.debug(f"  Amap request failed: {e}")
    return None


async def search_attraction_by_name(
    client: httpx.AsyncClient,
    api_key: str,
    name: str,
    city: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    sign_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Search Amap for a specific attraction by name + city.
    If coordinates are provided, prefer the result closest to them.
    """
    result = await amap_search(client, api_key, name, city, offset=5, sign_key=sign_key)
    if not result:
        return None

    pois = result.get("pois", [])
    if not pois:
        return None

    if lat and lon:
        # Pick the POI closest to our known coordinates
        best_poi = None
        best_dist = float("inf")
        for poi in pois:
            loc = poi.get("location", "")
            if "," in loc:
                p_lon, p_lat = loc.split(",", 1)
                try:
                    dist = haversine(lat, lon, float(p_lat), float(p_lon))
                    if dist < best_dist:
                        best_dist = dist
                        best_poi = poi
                except (ValueError, TypeError):
                    continue
        if best_poi:
            return _parse_amap_poi(best_poi, city)

    # No coords to compare — return first result
    return _parse_amap_poi(pois[0], city)


# ── Supplemental search for low-count cities ───────────


async def supplement_city(
    client: httpx.AsyncClient,
    api_key: str,
    city: str,
    target_count: int,
    current_count: int,
    existing_names: set,
    sign_key: str = "",
) -> List[Dict[str, Any]]:
    """Search Amap for additional attractions in a city to reach target count."""
    needed = max(0, target_count - current_count)
    if needed <= 0:
        return []

    logger.info(f"  Supplementing {city}: need {needed} more (have {current_count}, target {target_count})")
    new_places: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for keyword in SUPPLEMENT_KEYWORDS:
        if len(new_places) >= needed:
            break

        for page in range(1, 4):  # max 3 pages per keyword = 60 results
            if len(new_places) >= needed:
                break

            result = await amap_search(
                client, api_key, keyword, city,
                types=TOURIST_TYPES, city_limit=True, offset=25, page=page,
                sign_key=sign_key,
            )
            if not result:
                break

            pois = result.get("pois", [])
            if not pois:
                break

            for poi in pois:
                if len(new_places) >= needed:
                    break
                parsed = _parse_amap_poi(poi, city)
                pid = parsed.get("amap_id")
                if pid and pid in seen_ids:
                    continue
                if pid:
                    seen_ids.add(pid)

                # Skip if name is too generic or empty
                pname = parsed.get("name", "")
                if not pname or len(pname) < 2:
                    continue

                # Skip if it looks like a duplicate of existing
                norm = normalize_name(pname)
                if norm in existing_names:
                    continue

                new_places.append(parsed)
                existing_names.add(norm)

            await asyncio.sleep(DELAY_BETWEEN)

        if result and len(result.get("pois", [])) < 25:
            # Last page was short — no more results for this keyword
            continue

    logger.info(f"    Found {len(new_places)} supplemental places for {city}")
    return new_places


# ── Main Enrichment Logic ──────────────────────────────


async def enrich_one(
    client: httpx.AsyncClient,
    api_key: str,
    attraction: Dict[str, Any],
    index: int,
    total: int,
    sign_key: str = "",
) -> Dict[str, Any]:
    """Enrich a single attraction with Amap data (address, verified coords, photo)."""
    result = dict(attraction)
    # Default new fields
    result.setdefault("address", None)
    result.setdefault("amap_id", None)
    result.setdefault("amap_type", None)
    result.setdefault("amap_typecode", None)
    result.setdefault("amap_photo_url", None)
    result.setdefault("amap_verified", False)
    result.setdefault("source", attraction.get("source", "wikidata"))

    name = attraction.get("name", "")
    city = attraction.get("city", "")
    lat = attraction.get("lat")
    lon = attraction.get("lon")

    if not name or not city:
        return result

    amap_data = await search_attraction_by_name(client, api_key, name, city, lat, lon, sign_key=sign_key)

    if amap_data:
        result["address"] = amap_data.get("address") or result.get("address")
        result["amap_id"] = amap_data.get("amap_id") or result.get("amap_id")
        result["amap_type"] = amap_data.get("amap_type") or result.get("amap_type")
        result["amap_typecode"] = amap_data.get("amap_typecode") or result.get("amap_typecode")
        result["amap_photo_url"] = amap_data.get("photo_url") or result.get("amap_photo_url")
        result["amap_verified"] = True

        # Use Amap coordinates if ours are missing or Amap result is very close
        if (not result.get("lat") or not result.get("lon")) and amap_data.get("lat"):
            result["lat"] = amap_data["lat"]
            result["lon"] = amap_data["lon"]
        if result.get("source") == "wikidata":
            result["source"] = "wikidata+amap"

    # Progress
    if (index + 1) % 25 == 0 or index == total - 1:
        logger.info(
            f"  Progress: {index + 1}/{total} "
            f"({(index + 1) * 100 // total}%)"
        )

    await asyncio.sleep(DELAY_BETWEEN)
    return result


async def main():
    """Main entry point."""
    api_key, sign_key = _load_settings()
    if not api_key:
        logger.error(
            "AMAP_API_KEY is not set. Set it in backend/.env to enable Amap enrichment.\n"
            "Get a free key at https://console.amap.com/dev/key/app"
        )
        return

    if sign_key:
        logger.info("Amap digital signing enabled (AMAP_SIGN_KEY configured)")

    if not INPUT_FILE.exists():
        logger.error(
            f"Input file not found: {INPUT_FILE}\n"
            "Run fetch_wikidata.py and enrich_wikipedia.py first."
        )
        return

    # Load input
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "attractions" not in data:
        logger.error(f"Invalid input format in {INPUT_FILE}")
        return

    attractions = data["attractions"]
    total = len(attractions)
    logger.info(f"Loaded {total} attractions from {INPUT_FILE}")
    logger.info(f"Enriching with Amap POI data ({MAX_CONCURRENT} concurrent)...")

    # Phase 1: Verify and enrich existing attractions
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def bounded_enrich(attraction, idx):
        async with semaphore:
            return await enrich_one(client, api_key, attraction, idx, total, sign_key=sign_key)

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        enriched = await asyncio.gather(*[
            bounded_enrich(att, i) for i, att in enumerate(attractions)
        ])

    # Stats after phase 1
    verified = sum(1 for a in enriched if a.get("amap_verified"))
    with_addr = sum(1 for a in enriched if a.get("address"))
    logger.info(f"Phase 1 complete: {verified}/{total} verified on Amap, "
                f"{with_addr}/{total} have address")

    # Phase 2: Supplement low-count cities
    logger.info("Phase 2: Supplementing low-count cities...")
    city_counts: Dict[str, int] = {}
    for a in enriched:
        city_counts[a.get("city", "")] = city_counts.get(a.get("city", ""), 0) + 1

    # Build set of existing names for dedup
    existing_names: Dict[str, set] = {}  # city -> set of normalized names
    for a in enriched:
        city = a.get("city", "")
        if city not in existing_names:
            existing_names[city] = set()
        existing_names[city].add(normalize_name(a.get("name", "")))

    all_attractions = list(enriched)
    total_new = 0

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for city, target in sorted(TARGET_COUNTS.items()):
            current = city_counts.get(city, 0)
            names = existing_names.get(city, set())
            new_places = await supplement_city(
                client, api_key, city, target, current, names,
                sign_key=sign_key,
            )
            if new_places:
                all_attractions.extend(new_places)
                total_new += len(new_places)
                city_counts[city] = current + len(new_places)

    # Final stats
    final_total = len(all_attractions)
    logger.info(f"Phase 2 complete: added {total_new} new places")
    logger.info(f"Final total: {final_total} attractions")

    # Print per-city breakdown
    city_final: Dict[str, int] = {}
    for a in all_attractions:
        city_final[a.get("city", "")] = city_final.get(a.get("city", ""), 0) + 1
    for city, target in sorted(TARGET_COUNTS.items()):
        count = city_final.get(city, 0)
        gap = "✓" if count >= target else f"({target - count} short)"
        logger.info(f"  {city}: {count}/{target} {gap}")

    # Save
    output = {
        "source": "Wikidata + Wikipedia + Amap",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": final_total,
        "amap_verified": verified,
        "amap_new": total_new,
        "attractions": all_attractions,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Done! Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

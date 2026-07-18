"""
TravelMind Agent — Wikidata SPARQL Data Fetcher

Queries Wikidata for tourist attractions across 10 Chinese cities.
Uses the public SPARQL endpoint (no API key required, CC0 data).

Output: data/wikidata_attractions.json
  [{name, name_en, lat, lon, city, wiki_article, wiki_pageid, instance_of}, ...]

Rate limit: sequential queries with 1s delay between cities (no authentication
required, but we don't want to hammer the public endpoint).

Usage:
  cd backend
  python scripts/fetch_wikidata.py
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "TravelMindAgent/0.1 (https://github.com/travelmind; travelmind@example.com)"

# 10 target cities from data strategy
CITIES = [
    {"name": "重庆", "wd_id": "Q11725"},
    {"name": "成都", "wd_id": "Q30038"},
    {"name": "广州", "wd_id": "Q133313"},
    {"name": "北京", "wd_id": "Q956"},
    {"name": "上海", "wd_id": "Q8686"},
    {"name": "西安", "wd_id": "Q5826"},
    {"name": "杭州", "wd_id": "Q4970"},
    {"name": "长沙", "wd_id": "Q174091"},
    {"name": "厦门", "wd_id": "Q69067"},
    {"name": "大理", "wd_id": "Q1200627"},   # Dali Bai Autonomous Prefecture
]

# Output path (relative to project root)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "wikidata_attractions.json"

# Maximum results per city
MAX_PER_CITY = 80


# ── SPARQL Query Builder ─────────────────────────────────

def build_sparql(city_wd_id: str) -> str:
    """Build a SPARQL query to find tourist attractions in a city.

    Uses P131* (located in or within) to catch attractions in districts
    of the city. Gets raw coordinate strings — parsing happens in Python.
    """
    return f"""
    SELECT DISTINCT ?item ?itemLabel ?itemLabel_en ?coord ?instanceLabel
                    ?wiki_article ?wp_en
    WHERE {{
      # Target attraction types — includes Chinese classifications
      VALUES ?instance {{
        wd:Q570116    # tourist attraction
        wd:Q10860115  # 5A scenic spot (China classification)
        wd:Q16963344  # 4A scenic spot
        wd:Q358       # heritage site / cultural heritage
        wd:Q11747760  # national park
        wd:Q1435282   # museum
        wd:Q9259      # World Heritage Site
        wd:Q1146415   # park
        wd:Q1566172   # Major Historical and Cultural Site Protected at the National Level (全国重点文物保护单位)
      }}

      ?item wdt:P31/wdt:P279* ?instance .

      # Located in city or its districts (transitive)
      ?item wdt:P131* wd:{city_wd_id} .

      # Labels
      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "zh,en" .
      }}

      # Raw coordinate string — parse in Python
      OPTIONAL {{ ?item wdt:P625 ?coord . }}

      # Wikipedia article (Chinese preferred)
      OPTIONAL {{
        ?wiki_article schema:about ?item ;
                      schema:isPartOf <https://zh.wikipedia.org/> .
      }}
      # English Wikipedia (fallback)
      OPTIONAL {{
        ?wp_en schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
      }}
    }}
    LIMIT {MAX_PER_CITY}
    """


# ── API Call ─────────────────────────────────────────────

async def query_wikidata(city: Dict[str, str]) -> List[Dict[str, Any]]:
    """Execute a SPARQL query for one city and parse results.

    First tries the main query with P31 type filters. If that returns 0
    results, falls back to a broader query without type filtering.
    """
    query = build_sparql(city["wd_id"])
    logger.info(f"Querying Wikidata for {city['name']} ({city['wd_id']})...")

    raw_results = await _execute_query(query)

    # Fallback: if main query returned 0, try broader query without type filter.
    # Requires coordinates and excludes the city entity itself (P131* zero-step).
    if not raw_results:
        logger.info(f"  No results with type filter; trying broader query for {city['name']}...")
        broad_query = f"""
        SELECT DISTINCT ?item ?itemLabel ?itemLabel_en ?coord ?instanceLabel
                        ?wiki_article ?wp_en
        WHERE {{
          ?item wdt:P131* wd:{city['wd_id']} .
          # Exclude the city entity itself
          FILTER(?item != wd:{city['wd_id']})
          # Require coordinates — without them the attraction is unusable
          ?item wdt:P625 ?coord .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en" . }}
          OPTIONAL {{
            ?wiki_article schema:about ?item ;
                          schema:isPartOf <https://zh.wikipedia.org/> .
          }}
          OPTIONAL {{
            ?wp_en schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> .
          }}
        }}
        LIMIT {MAX_PER_CITY}
        """
        raw_results = await _execute_query(broad_query)

    # Stamp city name on results
    for r in raw_results:
        r["city"] = city["name"]

    # Deduplicate again across city
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in raw_results:
        key = (r["name"], r["city"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(f"  {city['name']}: {len(unique)} attractions found")
    return unique


async def _execute_query(query: str, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Execute a single SPARQL query with retries. Returns parsed results."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                response = await client.get(
                    SPARQL_ENDPOINT,
                    params={"format": "json", "query": query},
                    headers={"User-Agent": USER_AGENT},
                )
                response.raise_for_status()
                data = response.json()
                return _parse_bindings(data)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"  Attempt {attempt + 1} failed, retrying in {wait}s: {e}")
                await asyncio.sleep(wait)
    logger.error(f"  All {max_retries + 1} attempts failed: {last_error}")
    return []


def _parse_bindings(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Wikidata SPARQL JSON response into a list of attraction dicts."""
    results: List[Dict[str, Any]] = []
    for binding in data.get("results", {}).get("bindings", []):
        name = binding.get("itemLabel", {}).get("value", "")
        if not name:
            continue

        # Parse coordinates from Wikidata Point format: "Point(lon lat)"
        lat, lon = None, None
        coord_raw = binding.get("coord", {}).get("value", "")
        if coord_raw:
            try:
                stripped = coord_raw.replace("Point(", "").replace(")", "").strip()
                parts = stripped.split()
                if len(parts) == 2:
                    lon_val, lat_val = float(parts[0]), float(parts[1])
                    if -90 <= lat_val <= 90 and -180 <= lon_val <= 180:
                        lat, lon = lat_val, lon_val
            except (ValueError, IndexError):
                pass

        wiki_url = binding.get("wiki_article", {}).get("value", "")
        wiki_en_url = binding.get("wp_en", {}).get("value", "")

        item_id = binding.get("item", {}).get("value", "")
        wikidata_id = item_id.rsplit("/", 1)[-1] if item_id else ""

        results.append({
            "name": name,
            "name_en": binding.get("itemLabel_en", {}).get("value", ""),
            "lat": lat,
            "lon": lon,
            "city": "",  # filled in by caller
            "wiki_article": wiki_url,
            "wiki_article_en": wiki_en_url,
            "wikidata_id": wikidata_id,
            "instance_of": binding.get("instanceLabel", {}).get("value", ""),
        })

    # Deduplicate by wikidata_id (fallback to name)
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in results:
        key = r["wikidata_id"] or r["name"]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


# ── Main ─────────────────────────────────────────────────

async def main():
    """Fetch attractions from all 10 cities and save to JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_results: List[Dict[str, Any]] = []
    total = 0

    for city in CITIES:
        try:
            results = await query_wikidata(city)
            all_results.extend(results)
            total += len(results)
        except Exception as e:
            logger.error(f"Failed to fetch {city['name']}: {e}")
            continue
        # Be polite to the public endpoint
        if city != CITIES[-1]:
            time.sleep(1.0)

    # Save
    output = {
        "source": "Wikidata SPARQL (CC0)",
        "query_date": time.strftime("%Y-%m-%d"),
        "total": total,
        "cities": [c["name"] for c in CITIES],
        "attractions": all_results,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Done! {total} total attractions saved to {OUTPUT_FILE}")

    # Per-city breakdown
    from collections import Counter
    city_counts = Counter(r["city"] for r in all_results)
    for city in CITIES:
        count = city_counts.get(city["name"], 0)
        status = "✅" if count >= 20 else "⚠️" if count >= 10 else "❌"
        logger.info(f"  {status} {city['name']}: {count} places")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

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

# 15 target cities: original 10 + 5 added in Phase 6 data expansion
# NOTE: use prefecture-level entities that actually hold P131* links —
# Q-IDs verified 2026-07-18 after Wikidata's Chinese-city reorganization
# (older "city" entities like Q30038/Q133313/Q69067/Q1200627 are now empty).
CITIES = [
    {"name": "重庆", "wd_id": "Q11725"},
    {"name": "成都", "wd_id": "Q30002"},
    {"name": "广州", "wd_id": "Q16572"},
    {"name": "北京", "wd_id": "Q956"},
    {"name": "上海", "wd_id": "Q8686"},
    {"name": "西安", "wd_id": "Q5826"},
    {"name": "杭州", "wd_id": "Q4970"},
    {"name": "长沙", "wd_id": "Q174091"},
    {"name": "厦门", "wd_id": "Q68744"},
    {"name": "大理", "wd_id": "Q999156"},
    # ── Phase 6 expansion (Q-IDs verified via wbsearchentities 2026-07-18) ──
    {"name": "三亚", "wd_id": "Q319804"},
    {"name": "桂林", "wd_id": "Q189633"},
    {"name": "苏州", "wd_id": "Q42622"},
    {"name": "张家界", "wd_id": "Q197379"},
    {"name": "丽江", "wd_id": "Q205914"},
]

# Output path (relative to project root)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "wikidata_attractions.json"

# Maximum results per city (raised 80 → 120 in Phase 6 for densification)
MAX_PER_CITY = 120


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


# ── Proxy detection ──────────────────────────────────────

def _detect_proxy() -> Optional[str]:
    """Read the Windows system proxy from the registry.

    httpx trust_env does not reliably pick up the registry proxy on
    Windows (we verified: explicit proxy= works, trust_env=True fails),
    so read it ourselves. Returns e.g. 'http://127.0.0.1:34131' or None.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
        winreg.CloseKey(key)
        if not enabled or not server:
            return None
        if "=" in server:  # per-protocol form: "http=h:1;https=h:2"
            parts = dict(p.split("=", 1) for p in server.split(";") if "=" in p)
            server = parts.get("https") or parts.get("http", "")
        server = server.strip()
        return f"http://{server}" if server else None
    except Exception:
        return None


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
    """Execute a single SPARQL query with retries. Returns parsed results.

    Wikidata is blocked by the GFW, so a VPN is required. Try direct
    connection first (works with VPN in TUN/global mode), then fall back
    to the system proxy (works with VPN in system-proxy mode).
    """
    last_error = None
    proxy = _detect_proxy()
    for attempt in range(max_retries + 1):
        # Proxy first (Wikidata is GFW-blocked; direct always fails in CN),
        # direct only as fallback (covers VPN TUN mode without system proxy).
        use_proxy = attempt % 2 == 0 and proxy is not None
        try:
            async with httpx.AsyncClient(
                timeout=120.0, trust_env=False,
                proxy=proxy if use_proxy else None,
            ) as client:
                response = await client.get(
                    SPARQL_ENDPOINT,
                    params={"format": "json", "query": query},
                    headers={"User-Agent": USER_AGENT},
                )
                response.raise_for_status()
                data = response.json()
                if use_proxy:
                    logger.info("  (via system proxy)")
                return _parse_bindings(data)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    f"  Attempt {attempt + 1} failed "
                    f"({'proxy' if use_proxy else 'direct'}), retrying in {wait}s: {e!r}"
                )
                await asyncio.sleep(wait)
    logger.error(f"  All {max_retries + 1} attempts failed: {last_error!r}")
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
    """Fetch attractions and save to JSON.

    CLI: `python scripts/fetch_wikidata.py [城市名 ...]` — fetch only the
    given cities. Results are MERGED into the output file: a city's old
    entries are replaced only when the fresh fetch returned >0 for it,
    so flaky WDQS responses never wipe previously-good data.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    only = set(sys.argv[1:])
    cities = [c for c in CITIES if not only or c["name"] in only]
    if not cities:
        logger.error(f"No matching cities for args: {sorted(only)}")
        return
    if only:
        logger.info(f"Subset run: {[c['name'] for c in cities]}")

    all_results: List[Dict[str, Any]] = []
    fetched_ok: set = set()

    for city in cities:
        try:
            results = await query_wikidata(city)
            all_results.extend(results)
            if results:
                fetched_ok.add(city["name"])
        except Exception as e:
            logger.error(f"Failed to fetch {city['name']}: {e}")
            continue
        # Be polite to the public endpoint
        if city != cities[-1]:
            time.sleep(1.0)

    # ── Merge with existing file ─────────────────────────
    # Fetched-and-nonempty cities are replaced; everything else is kept.
    merged: List[Dict[str, Any]] = []
    seen: set = set()

    def _key(a: Dict[str, Any]):
        return (a.get("wikidata_id") or a.get("name", ""), a.get("city", ""))

    for a in all_results:
        k = _key(a)
        if k not in seen:
            seen.add(k)
            merged.append(a)

    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        kept = 0
        for a in old.get("attractions", []):
            if a.get("city") in fetched_ok:
                continue  # replaced by fresh results
            k = _key(a)
            if k not in seen:
                seen.add(k)
                merged.append(a)
                kept += 1
        logger.info(f"Merged: {len(all_results)} fresh + {kept} kept from previous run")

    total = len(merged)

    # Save
    output = {
        "source": "Wikidata SPARQL (CC0)",
        "query_date": time.strftime("%Y-%m-%d"),
        "total": total,
        "cities": sorted({a.get("city", "") for a in merged}),
        "attractions": merged,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Done! {total} total attractions saved to {OUTPUT_FILE}")

    # Per-city breakdown
    from collections import Counter
    city_counts = Counter(r["city"] for r in merged)
    for city in CITIES:
        count = city_counts.get(city["name"], 0)
        status = "✅" if count >= 20 else "⚠️" if count >= 10 else "❌"
        logger.info(f"  {status} {city['name']}: {count} places")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

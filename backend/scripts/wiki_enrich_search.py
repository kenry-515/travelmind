"""
Wikipedia Enrichment Phase 2 - Use search API for better matching
=================================================================
For POIs that weren't found by direct title lookup, use Wikipedia's
search API to find related articles, then fetch extracts.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

PROXY = "http://127.0.0.1:34131"
WIKI_UA = "TravelMindAgent/1.0 (https://github.com/travelmind; travelmind@example.com)"
WIKI_HEADERS = {
    "User-Agent": WIKI_UA,
    "Accept": "application/json",
}

REAL_TEMPLATE_PATTERNS = [
    "主要特点包括",
    "具有重要的",
    "特色包括",
    "见证了当地的历史变迁",
    "具有重要的历史文化价值",
    "适合深度游览和文化探索",
    "适合文化体验和祈福参拜",
]


def is_template_desc(desc: str) -> bool:
    if not desc or len(desc) < 30:
        return True
    marker_count = sum(1 for p in REAL_TEMPLATE_PATTERNS if p in desc)
    if marker_count >= 2:
        return True
    if desc.count("适合") >= 3:
        return True
    return False


async def search_wiki(
    client: httpx.AsyncClient,
    query: str,
    city: str = "",
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Search Wikipedia for articles matching query."""
    # Add city context to improve matching
    search_query = f"{query} {city}" if city else query
    search_query = search_query.strip()

    try:
        r = await client.get(
            "https://zh.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": search_query,
                "format": "json",
                "srlimit": limit,
                "srprop": "snippet",
            },
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("query", {}).get("search", [])
    except Exception:
        pass
    return []


async def fetch_wiki_extract(
    client: httpx.AsyncClient,
    title: str,
) -> Optional[Dict[str, Any]]:
    """Fetch extract, coordinates, thumbnail for a Wikipedia title."""
    try:
        r = await client.get(
            "https://zh.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": title,
                "prop": "extracts|coordinates|pageimages|info",
                "exintro": 1,
                "explaintext": 1,
                "piprop": "thumbnail",
                "pithumbsize": 400,
                "inprop": "url",
                "format": "json",
                "redirects": 1,
            },
        )
        if r.status_code == 200:
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid == "-1":
                    return None
                extract = page.get("extract", "")
                if not extract or len(extract) < 30:
                    return None
                coords_list = page.get("coordinates", [])
                coords = coords_list[0] if coords_list else None
                return {
                    "extract": extract.strip(),
                    "lat": coords.get("lat") if coords else None,
                    "lon": coords.get("lon") if coords else None,
                    "thumbnail": page.get("thumbnail", {}).get("source", ""),
                    "wiki_url": page.get("fullurl", ""),
                    "wiki_title": page.get("title", title),
                }
    except Exception:
        pass
    return None


def is_relevant_match(poi_name: str, wiki_title: str, snippet: str) -> bool:
    """Check if a Wikipedia search result is relevant to the POI."""
    # Exact title match
    if poi_name == wiki_title:
        return True
    # POI name is substring of wiki title or vice versa
    if poi_name in wiki_title or wiki_title in poi_name:
        return True
    # Check snippet for POI name
    if poi_name in snippet:
        return True
    # Check for disambiguation pages (skip them)
    if "消歧义" in wiki_title or "消歧義" in wiki_title:
        return False
    return False


async def enrich_with_search():
    """Enrich POIs using Wikipedia search API."""
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    total = len(attractions)
    print(f"📂 Loading {total} attractions")

    # Find candidates still needing enrichment (skip those already enriched)
    candidates = []
    for i, attr in enumerate(attractions):
        desc = attr.get("description", "") or ""
        is_template = is_template_desc(desc)
        is_short = len(desc) < 80
        already_enriched = attr.get("description_source") == "wikipedia_zh"

        # Only process attractions (not restaurants/hotels - they rarely have wiki pages)
        category = attr.get("category", "")
        tags_str = " ".join(attr.get("tags", []) or [])
        is_attraction = (
            category == "attractions"
            or "景点" in tags_str
            or not any(kw in tags_str for kw in ["美食", "餐厅", "酒店", "住宿"])
        )

        if (is_template or is_short) and not already_enriched and is_attraction:
            candidates.append((i, attr))

    print(f"🎯 Found {len(candidates)} attraction candidates for search-based enrichment")

    if not candidates:
        print("Nothing to enrich.")
        return

    stats = {
        "enriched": 0,
        "not_found": 0,
        "errors": 0,
        "desc_replaced": 0,
    }

    # Limit to 400 to keep runtime reasonable
    to_process = candidates[:400]
    print(f"🔄 Processing {len(to_process)} candidates")

    client = httpx.AsyncClient(
        proxy=PROXY,
        headers=WIKI_HEADERS,
        timeout=15.0,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
    )

    sem = asyncio.Semaphore(3)

    async def process_one(idx: int, attr: Dict[str, Any]):
        async with sem:
            name = attr.get("name", "")
            city = attr.get("city", "")

            try:
                # First try direct lookup
                wiki_data = await fetch_wiki_extract(client, name)

                # If not found, try search
                if wiki_data is None:
                    search_results = await search_wiki(client, name, city, limit=3)
                    for result in search_results:
                        wiki_title = result.get("title", "")
                        snippet = result.get("snippet", "")
                        # Remove HTML tags from snippet
                        snippet = re.sub(r"<[^>]+>", "", snippet)

                        if is_relevant_match(name, wiki_title, snippet):
                            wiki_data = await fetch_wiki_extract(client, wiki_title)
                            if wiki_data:
                                break

                if wiki_data is None:
                    stats["not_found"] += 1
                    return

                # Update description
                extract = wiki_data.get("extract", "")
                old_desc = attr.get("description", "") or ""

                if extract and (is_template_desc(old_desc) or len(extract) > len(old_desc)):
                    if len(extract) > 500:
                        extract = extract[:497] + "..."
                    attr["description"] = extract
                    attr["description_source"] = "wikipedia_zh"
                    attr["description_quality"] = "wikipedia"
                    stats["desc_replaced"] += 1

                # Update coordinates
                lat = wiki_data.get("lat")
                lon = wiki_data.get("lon")
                if lat and lon and not attr.get("lat"):
                    attr["lat"] = lat
                    attr["lon"] = lon

                # Update thumbnail
                thumbnail = wiki_data.get("thumbnail", "")
                if thumbnail and not attr.get("thumbnail_url"):
                    attr["thumbnail_url"] = thumbnail

                # Update wiki link
                wiki_url = wiki_data.get("wiki_url", "")
                if wiki_url and not attr.get("wiki_article"):
                    attr["wiki_article"] = wiki_url
                    attr["wiki_article_en"] = ""

                # Update data quality
                dq = attr.get("data_quality", {}) or {}
                dq["reliability"] = "high"
                dq["wikipedia_verified"] = True
                attr["data_quality"] = dq

                stats["enriched"] += 1

            except Exception:
                stats["errors"] += 1

    # Process in chunks
    chunk_size = 50
    total_to_process = len(to_process)

    for chunk_start in range(0, total_to_process, chunk_size):
        chunk = to_process[chunk_start:chunk_start + chunk_size]
        tasks = [process_one(idx, attr) for idx, attr in chunk]
        await asyncio.gather(*tasks)

        progress = min(chunk_start + chunk_size, total_to_process)
        print(
            f"  Progress: {progress}/{total_to_process} "
            f"({progress * 100 // total_to_process}%) - "
            f"Enriched: {stats['enriched']}, "
            f"Not found: {stats['not_found']}, "
            f"Errors: {stats['errors']}"
        )
        await asyncio.sleep(0.5)

    await client.aclose()

    # Save
    data["wikipedia_search_enriched"] = True
    data["enrich_date"] = datetime.now().strftime("%Y-%m-%d")

    print(f"\n💾 Saving enriched data...")
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("📊 Wikipedia Search Enrichment Report (Phase 2)")
    print("=" * 70)
    print(f"  Candidates: {len(candidates)}")
    print(f"  Processed: {total_to_process}")
    print(f"  Successfully enriched: {stats['enriched']}")
    print(f"  Not found: {stats['not_found']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Descriptions replaced: {stats['desc_replaced']}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(enrich_with_search())

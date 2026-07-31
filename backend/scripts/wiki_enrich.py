"""
Wikipedia Description Enrichment
================================
Use Wikipedia REST API to replace template-like descriptions with real ones.
Also enriches coordinates, thumbnails, and Wikipedia article links.

Requires proxy on 127.0.0.1:34131 for Wikipedia access.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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

# Real template patterns (actual AI-generated junk)
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
    """Check if a description is a low-quality AI template."""
    if not desc or len(desc) < 30:
        return True
    marker_count = sum(1 for p in REAL_TEMPLATE_PATTERNS if p in desc)
    if marker_count >= 2:
        return True
    if desc.count("适合") >= 3:
        return True
    return False


async def fetch_wiki_data(
    client: httpx.AsyncClient,
    title: str,
    retries: int = 2,
) -> Optional[Dict[str, Any]]:
    """Fetch Wikipedia data for a title.

    Returns dict with: extract, coordinates, thumbnail, wiki_url
    """
    # Clean title for Wikipedia search
    clean_title = title.strip()
    # Remove common suffixes
    clean_title = re.sub(r"\(.*?\)$", "", clean_title).strip()

    for attempt in range(retries + 1):
        try:
            # Use Action API to get extract + coordinates + thumbnail in one call
            r = await client.get(
                "https://zh.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": clean_title,
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

                # Handle redirects
                if "redirects" in data.get("query", {}):
                    redirects = data["query"]["redirects"]
                    if redirects:
                        clean_title = redirects[0].get("to", clean_title)

                for pid, page in pages.items():
                    if pid == "-1":
                        return None  # Not found

                    extract = page.get("extract", "")
                    if not extract or len(extract) < 30:
                        return None

                    coords_list = page.get("coordinates", [])
                    coords = coords_list[0] if coords_list else None

                    thumbnail = page.get("thumbnail", {}).get("source", "")

                    wiki_url = page.get("fullurl", "")

                    return {
                        "extract": extract.strip(),
                        "lat": coords.get("lat") if coords else None,
                        "lon": coords.get("lon") if coords else None,
                        "thumbnail": thumbnail,
                        "wiki_url": wiki_url,
                        "wiki_title": page.get("title", clean_title),
                    }
            elif r.status_code == 429:
                # Rate limited, wait longer
                await asyncio.sleep(2)
                continue
            else:
                return None
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None

    return None


async def enrich_attractions():
    """Enrich attractions with Wikipedia data."""
    # Load data
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    total = len(attractions)
    print(f"📂 Loading {total} attractions")

    # Identify candidates for enrichment
    candidates = []
    for i, attr in enumerate(attractions):
        desc = attr.get("description", "") or ""
        is_template = is_template_desc(desc)
        is_short = len(desc) < 80
        has_wiki = bool(attr.get("wiki_article"))
        no_coords = not (attr.get("lat") and attr.get("lon"))

        # Prioritize: template descriptions first, then short ones
        if is_template or (is_short and not has_wiki):
            candidates.append((i, attr, "template" if is_template else "short"))
        elif not has_wiki and no_coords:
            # Also enrich those missing wiki link and coords
            candidates.append((i, attr, "missing_meta"))

    print(f"🎯 Found {len(candidates)} candidates for enrichment")
    print(f"   - Template descriptions: {sum(1 for _,_,r in candidates if r == 'template')}")
    print(f"   - Short descriptions: {sum(1 for _,_,r in candidates if r == 'short')}")
    print(f"   - Missing metadata: {sum(1 for _,_,r in candidates if r == 'missing_meta')}")

    if not candidates:
        print("Nothing to enrich.")
        return

    # Process in batches with rate limiting
    stats = {
        "enriched": 0,
        "not_found": 0,
        "errors": 0,
        "desc_replaced": 0,
        "coords_added": 0,
        "thumbnail_added": 0,
        "wiki_link_added": 0,
    }

    # Limit to first 600 to avoid taking too long
    # (focus on template + short descriptions first)
    priority_candidates = [c for c in candidates if c[2] in ("template", "short")]
    other_candidates = [c for c in candidates if c[2] == "missing_meta"]

    # Process priority first (up to 500), then others (up to 200)
    to_process = priority_candidates[:500] + other_candidates[:200]
    print(f"\n🔄 Processing {len(to_process)} candidates (of {len(candidates)} total)")

    # Configure client with proxy
    client = httpx.AsyncClient(
        proxy=PROXY,
        headers=WIKI_HEADERS,
        timeout=15.0,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
    )

    sem = asyncio.Semaphore(3)  # Limit concurrent requests

    async def process_one(idx: int, attr: Dict[str, Any], reason: str):
        async with sem:
            name = attr.get("name", "")
            try:
                wiki_data = await fetch_wiki_data(client, name)
                if wiki_data is None:
                    stats["not_found"] += 1
                    return

                # Update description (only if wiki extract is better)
                extract = wiki_data.get("extract", "")
                old_desc = attr.get("description", "") or ""

                if extract and (is_template_desc(old_desc) or len(extract) > len(old_desc)):
                    # Truncate very long extracts
                    if len(extract) > 500:
                        extract = extract[:497] + "..."
                    attr["description"] = extract
                    attr["description_source"] = "wikipedia_zh"
                    attr["description_quality"] = "wikipedia"
                    stats["desc_replaced"] += 1

                # Update coordinates if missing
                lat = wiki_data.get("lat")
                lon = wiki_data.get("lon")
                if lat and lon and not attr.get("lat"):
                    attr["lat"] = lat
                    attr["lon"] = lon
                    stats["coords_added"] += 1

                # Update thumbnail if missing
                thumbnail = wiki_data.get("thumbnail", "")
                if thumbnail and not attr.get("thumbnail_url"):
                    attr["thumbnail_url"] = thumbnail
                    stats["thumbnail_added"] += 1

                # Update wiki link if missing
                wiki_url = wiki_data.get("wiki_url", "")
                if wiki_url and not attr.get("wiki_article"):
                    attr["wiki_article"] = wiki_url
                    attr["wiki_article_en"] = ""
                    stats["wiki_link_added"] += 1

                # Update data quality
                dq = attr.get("data_quality", {}) or {}
                dq["reliability"] = "high" if dq.get("reliability") != "high" else "high"
                dq["wikipedia_verified"] = True
                attr["data_quality"] = dq

                stats["enriched"] += 1

            except Exception as e:
                stats["errors"] += 1

    # Process in chunks with progress reporting
    chunk_size = 50
    total_to_process = len(to_process)

    for chunk_start in range(0, total_to_process, chunk_size):
        chunk = to_process[chunk_start:chunk_start + chunk_size]
        tasks = [process_one(idx, attr, reason) for idx, attr, reason in chunk]
        await asyncio.gather(*tasks)

        progress = min(chunk_start + chunk_size, total_to_process)
        print(
            f"  Progress: {progress}/{total_to_process} "
            f"({progress * 100 // total_to_process}%) - "
            f"Enriched: {stats['enriched']}, "
            f"Not found: {stats['not_found']}, "
            f"Errors: {stats['errors']}"
        )

        # Small delay between chunks to be nice to Wikipedia
        await asyncio.sleep(0.5)

    await client.aclose()

    # Update data
    data["attractions"] = attractions
    data["wikipedia_enriched"] = True
    data["enrich_date"] = datetime.now().strftime("%Y-%m-%d")
    data["wiki_enrichment_summary"] = {
        "candidates_total": len(candidates),
        "processed": total_to_process,
        "enriched": stats["enriched"],
        "not_found": stats["not_found"],
        "errors": stats["errors"],
        "descriptions_replaced": stats["desc_replaced"],
        "coordinates_added": stats["coords_added"],
        "thumbnails_added": stats["thumbnail_added"],
        "wiki_links_added": stats["wiki_link_added"],
    }

    # Save
    print(f"\n💾 Saving enriched data...")
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Report
    print("\n" + "=" * 70)
    print("📊 Wikipedia Enrichment Report")
    print("=" * 70)
    print(f"  Total attractions: {total}")
    print(f"  Candidates found: {len(candidates)}")
    print(f"  Processed: {total_to_process}")
    print(f"  Successfully enriched: {stats['enriched']}")
    print(f"  Not found on Wikipedia: {stats['not_found']}")
    print(f"  Errors: {stats['errors']}")
    print()
    print(f"  📝 Descriptions replaced: {stats['desc_replaced']}")
    print(f"  📍 Coordinates added: {stats['coords_added']}")
    print(f"  🖼️  Thumbnails added: {stats['thumbnail_added']}")
    print(f"  🔗 Wiki links added: {stats['wiki_link_added']}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(enrich_attractions())

"""
TravelMind Agent — Wikipedia Enricher

Fetches Chinese (zh) Wikipedia extracts for each attraction from the
Wikidata results. Uses the public Wikipedia REST API — no key required.

Input:  data/wikidata_attractions.json
Output: data/wikipedia_enriched.json

For each attraction with a Wikipedia article:
  - Fetch the Chinese page extract (short summary)
  - If Chinese not available, fall back to English
  - Add description, pageid, thumbnail URL, full URL

Rate limit: 200ms delay between requests (no key required, be polite).

Usage:
  cd backend
  python scripts/enrich_wikipedia.py
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

USER_AGENT = "TravelMindAgent/0.1 (https://github.com/travelmind; travelmind@example.com)"

# Wikipedia REST API — routed through wikimedia.org because zh.wikipedia.org
# and en.wikipedia.org domains are subject to TLS interference (GFW).
# wikimedia.org resolves to a different CDN edge that is reachable.
# The Host header tells Wikimedia which language wiki to serve.
WIKI_API_BASE = "https://wikimedia.org/api/rest_v1/page/summary/{title}"
WIKI_HOSTS = {
    "zh": "zh.wikipedia.org",
    "en": "en.wikipedia.org",
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "wikidata_attractions.json"
OUTPUT_FILE = DATA_DIR / "wikipedia_enriched.json"

# Concurrency — keep it low for the public API
MAX_CONCURRENT = 4
DELAY_BETWEEN = 0.5  # seconds between requests per worker (max ~8 req/s with 4 workers)
MAX_RETRIES = 2      # retries per request for transient errors


# ── Helpers ──────────────────────────────────────────────

def extract_title_from_url(url: str) -> Optional[str]:
    """Extract the Wikipedia page title from a URL like
    https://zh.wikipedia.org/wiki/长江三峡
    """
    if not url:
        return None
    # URL format: https://lang.wikipedia.org/wiki/Title
    parts = url.rstrip("/").split("/wiki/")
    if len(parts) == 2:
        return parts[1]
    return None


async def fetch_summary(
    client: httpx.AsyncClient,
    title: str,
    lang: str = "zh",
) -> Optional[Dict[str, Any]]:
    """Fetch a Wikipedia page summary via the REST API with retries.

    Uses wikimedia.org as the entry point (not blocked by GFW) and sets
    the Host header to route to the correct language Wikipedia.
    """
    url = WIKI_API_BASE.format(title=title)
    host = WIKI_HOSTS.get(lang, "en.wikipedia.org")

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Host": host,
                },
            )
            if response.status_code == 404:
                return None  # don't retry 404s
            if response.status_code in (429, 503):
                # Rate limited or temporarily unavailable — retry with backoff
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
            response.raise_for_status()
            return response.json()
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    if last_error:
        logger.debug(f"  Failed to fetch {lang}:{title} — {last_error}")
    return None


# ── Main Enrichment Logic ────────────────────────────────

async def enrich_one(
    client: httpx.AsyncClient,
    attraction: Dict[str, Any],
    index: int,
    total: int,
) -> Dict[str, Any]:
    """Enrich a single attraction with Wikipedia data."""
    result = dict(attraction)  # copy
    result.setdefault("description", None)
    result.setdefault("thumbnail_url", None)
    result.setdefault("full_url", None)
    result.setdefault("description_source", None)

    wiki_url = attraction.get("wiki_article", "")
    title = extract_title_from_url(wiki_url)

    if not title:
        return result

    # Try Chinese first
    summary = await fetch_summary(client, title, "zh")

    # Fall back to English
    if not summary:
        en_url = attraction.get("wiki_article_en", "")
        en_title = extract_title_from_url(en_url)
        if en_title:
            summary = await fetch_summary(client, en_title, "en")
            if summary:
                result["description_source"] = "wikipedia_en"
        else:
            # Try English with same title
            summary = await fetch_summary(client, title, "en")
            if summary:
                result["description_source"] = "wikipedia_en"
    else:
        result["description_source"] = "wikipedia_zh"

    if summary:
        result["description"] = summary.get("extract", "")
        # Thumbnail
        thumbnail = summary.get("thumbnail")
        if thumbnail:
            result["thumbnail_url"] = thumbnail.get("source", "")
        # Full URL
        result["full_url"] = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
        # Page ID if missing from Wikidata
        if not result.get("wiki_pageid"):
            result["wiki_pageid"] = str(summary.get("pageid", ""))

    # Progress
    if (index + 1) % 20 == 0 or index == total - 1:
        logger.info(
            f"  Progress: {index + 1}/{total} "
            f"({(index + 1) * 100 // total}%)"
        )

    # Be polite
    await asyncio.sleep(DELAY_BETWEEN)

    return result


def _detect_proxy() -> Optional[str]:
    """Read the Windows system proxy from the registry.

    httpx trust_env does not reliably pick up the registry proxy on
    Windows (verified), so read it ourselves.
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


async def _make_shared_client() -> httpx.AsyncClient:
    """Create the shared HTTP client, probing direct vs system proxy.

    Wikipedia/Wikimedia is GFW-blocked, so a VPN is required. Try direct
    connection first (works with VPN in TUN/global mode), then the system
    proxy (works with VPN in system-proxy mode).
    """
    proxy = _detect_proxy()
    # Proxy first (GFW-blocked in CN), direct only as fallback.
    for candidate in (proxy, None):
        probe = httpx.AsyncClient(timeout=60.0, trust_env=False, proxy=candidate)
        try:
            response = await probe.get(
                "https://wikimedia.org/", headers={"User-Agent": USER_AGENT}
            )
            if response.status_code < 500:
                mode = "system proxy" if candidate else "direct"
                logger.info(f"Wikipedia client: {mode} connection OK")
                # Return a FRESH client — the probe client has already sent
                # a request and httpx forbids re-entering it with `async with`.
                return httpx.AsyncClient(timeout=60.0, trust_env=False, proxy=candidate)
        except Exception:
            pass
        finally:
            await probe.aclose()
    logger.warning(
        "Wikipedia unreachable both direct and via proxy — "
        "proceeding with direct connection (expect failures)"
    )
    return httpx.AsyncClient(timeout=60.0, trust_env=False)


async def main():
    """Main entry point: read Wikidata JSON, enrich with Wikipedia, save."""
    if not INPUT_FILE.exists():
        logger.error(
            f"Input file not found: {INPUT_FILE}\n"
            "Run fetch_wikidata.py first to generate the input data."
        )
        return

    # Load input with validation
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "attractions" not in data:
        logger.error(f"Invalid input format in {INPUT_FILE}: expected dict with 'attractions' key")
        return

    attractions = data["attractions"]
    total = len(attractions)
    logger.info(f"Loaded {total} attractions from {INPUT_FILE}")
    logger.info(f"Enriching with Wikipedia (Chinese preferred, max {MAX_CONCURRENT} concurrent)...")

    # Process with bounded concurrency using a semaphore + shared client
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def bounded_enrich(attraction, idx):
        async with semaphore:
            return await enrich_one(shared_client, attraction, idx, total)

    async with await _make_shared_client() as shared_client:
        tasks = [bounded_enrich(att, i) for i, att in enumerate(attractions)]
        enriched = await asyncio.gather(*tasks)

    # Stats
    with_desc = sum(1 for a in enriched if a.get("description"))
    with_zh = sum(
        1 for a in enriched
        if a.get("description_source") == "wikipedia_zh"
    )
    with_en = sum(
        1 for a in enriched
        if a.get("description_source") == "wikipedia_en"
    )
    no_desc = total - with_desc

    # Save
    output = {
        "source": "Wikidata + Wikipedia (CC BY-SA)",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": total,
        "with_description": with_desc,
        "with_description_zh": with_zh,
        "with_description_en": with_en,
        "without_description": no_desc,
        "attractions": enriched,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Done! Saved to {OUTPUT_FILE}")
    logger.info(f"  With description: {with_desc}/{total} "
                 f"(ZH: {with_zh}, EN: {with_en})")
    logger.info(f"  Without description: {no_desc}")


if __name__ == "__main__":
    asyncio.run(main())

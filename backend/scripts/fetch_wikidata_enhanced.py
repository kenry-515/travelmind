"""
TravelMind Agent — Wikidata Price & High-Quality Data Fetcher

Enhances attractions with:
  1. Ticket prices (P1764 fee, P2320 entrance fee)
  2. English names
  3. Wikipedia page IDs
  4. Instance classification
  5. Inception/creation dates
  6. Notable people associated

Uses public Wikidata SPARQL endpoint — no API key required.

Output: data/wikidata_attractions.json (updated)
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "wikidata_attractions.json"

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "TravelMindAgent/0.1 (research project)"

# Cities with their Wikidata Q-IDs
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
    {"name": "三亚", "wd_id": "Q319804"},
    {"name": "桂林", "wd_id": "Q189633"},
    {"name": "苏州", "wd_id": "Q42622"},
    {"name": "张家界", "wd_id": "Q197379"},
    {"name": "丽江", "wd_id": "Q205914"},
]


def build_enhanced_sparql(city_wd_id: str) -> str:
    """Build SPARQL query with price and quality data."""
    return f"""
    SELECT DISTINCT
        ?item ?itemLabel ?itemLabelEn ?coord ?instanceLabel
        ?fee ?inception ?wikiArticle ?pageId
        ?associatedPersonLabel
    WHERE {{
      ?item wdt:P131* wd:{city_wd_id} .
      ?item (wdt:P31/wdt:P279*) ?instance .
      OPTIONAL {{
        ?item wdt:P625 ?coord .
      }}
      OPTIONAL {{
        ?item wdt:P1764 ?fee .
      }}
      OPTIONAL {{
        ?item wdt:P2320 ?entranceFee .
        BIND(?entranceFee AS ?fee)
      }}
      OPTIONAL {{
        ?item wdt:P571 ?inception .
      }}
      OPTIONAL {{
        ?item wdt:P31 ?instanceOf .
        ?instanceOf rdfs:label ?instanceLabel .
        FILTER(LANG(?instanceLabel) = "zh")
      }}
      OPTIONAL {{
        ?item wdt:P921 ?wikiArticle .
        ?wikiArticle rdfs:label ?wikiLabel .
        FILTER(CONTAINS(STR(?wikiArticle), "zh.wikipedia.org"))
      }}
      OPTIONAL {{
        ?item wdt:P40 ?associatedPerson .
        ?associatedPerson rdfs:label ?associatedPersonLabel .
        FILTER(LANG(?associatedPersonLabel) = "zh")
      }}
      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "zh,en" .
        ?item rdfs:label ?itemLabel .
      }}
      OPTIONAL {{
        ?item rdfs:label ?itemLabelEn .
        FILTER(LANG(?itemLabelEn) = "en")
      }}
      FILTER(EXISTS {{
        ?item (wdt:P31/wdt:P279*) ?type .
        ?type wdt:P279* wd:Q221916 .
      }} || EXISTS {{
        ?item wdt:P1435 ?series .
      }} || EXISTS {{
        ?item wdt:P1436 ?route .
      }} || EXISTS {{
        ?item wdt:P1464 ?water .
      }})
    }}
    """


async def fetch_city_enhanced(
    client: httpx.AsyncClient,
    city_name: str,
    city_wd_id: str,
) -> List[Dict[str, Any]]:
    """Fetch enhanced data for one city."""
    query = build_enhanced_sparql(city_wd_id)

    for attempt in range(3):
        try:
            resp = await client.post(
                SPARQL_ENDPOINT,
                data={"query": query, "format": "json"},
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/sparql-results+json",
                },
                timeout=30,
            )
            if resp.status_code == 429:
                wait = 3 ** attempt
                logger.info(f"  Rate limited for {city_name}, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            bindings = data.get("results", {}).get("bindings", [])
            logger.info(f"  {city_name}: fetched {len(bindings)} items with enhanced data")
            return parse_sparql_results(bindings, city_name)
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(f"  {city_name} failed: {e}")
    return []


def parse_sparql_results(bindings: List[Dict], city: str) -> List[Dict[str, Any]]:
    """Parse SPARQL results into attraction dicts."""
    results = []
    seen_ids = set()

    for row in bindings:
        item_id = row.get("item", {}).get("value", "")
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        wd_id = item_id.split("/")[-1]
        name = row.get("itemLabel", {}).get("value", "")
        name_en = row.get("itemLabelEn", {}).get("value", "")

        # Parse coordinates
        coord_str = row.get("coord", {}).get("value", "")
        lat = lon = None
        if coord_str:
            # Handle Wikidata coordinate format: "Point(lat lon)" or "lat, lon"
            m = re.match(r"Point\(([-\d.]+)\s+([-\d.]+)\)", coord_str)
            if m:
                lat = float(m.group(1))
                lon = float(m.group(2))
            elif "," in coord_str:
                parts = coord_str.split(",")
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())

        # Parse price
        fee_node = row.get("fee", {})
        fee_value = ""
        if fee_node:
            fee_value = fee_node.get("value", "")
            # Handle various literal types
            if fee_value and fee_node.get("datatype") == "http://www.w3.org/2001/XMLSchema#decimal":
                try:
                    fee_value = str(int(float(fee_value)))
                except (ValueError, TypeError):
                    pass

        # Parse Wikipedia article
        wiki_article = row.get("wikiArticle", {}).get("value", "")
        wiki_label = row.get("wikiLabel", {}).get("value", "")

        results.append({
            "name": name,
            "name_en": name_en or "",
            "wikidata_id": wd_id,
            "city": city,
            "lat": lat,
            "lon": lon,
            "fee": fee_value,
            "wiki_article": wiki_article or "",
            "wiki_pageid": wiki_label or "",
            "source": "wikidata-enhanced",
        })

    return results


async def main():
    """Main: fetch enhanced Wikidata data for all cities."""
    logger.info("Fetching enhanced Wikidata data (prices + quality)...")

    timeout = httpx.Timeout(60.0, connect=15.0)
    all_attractions = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, city_info in enumerate(CITIES):
            logger.info(f"[{i+1}/{len(CITIES)}] Processing {city_info['name']}...")

            items = await fetch_city_enhanced(client, city_info["name"], city_info["wd_id"])
            all_attractions.extend(items)

            # Be polite to Wikidata — 1s between cities
            await asyncio.sleep(1)

    # Deduplicate by wikidata_id
    seen = {}
    for a in all_attractions:
        if a["wikidata_id"] not in seen:
            seen[a["wikidata_id"]] = a

    results = list(seen.values())
    results.sort(key=lambda x: (x["city"], x["name"]))

    # Price coverage stats
    has_fee = sum(1 for a in results if a.get("fee"))
    logger.info(f"\n完成! 共 {len(results)} 个景点, {has_fee} 个有票价数据")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"已保存到 {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
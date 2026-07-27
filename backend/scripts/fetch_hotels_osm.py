"""
TravelMind Agent — OSM Hotel POI Fetcher（住宿采集）

用 OpenStreetMap Overpass API（ODbL，无需 Key）采集住宿 POI：
tourism=hotel / guest_house / hostel。

背景（用户 2026-07-26："吃住都没有推荐"）：KB 酒店/民宿 POI 为 0，
行程无法给住宿建议。OSM 真实节点（带 osm_id 可追溯），rating 一律
null，popularity_score 统一中性值 4。

输出契约与 merge_indoor_pois.py 兼容（顶层 indoor_pois 键）。

用法：
  cd backend
  python scripts/fetch_hotels_osm.py                  # 全部 30 城
  python scripts/fetch_hotels_osm.py --cities 厦门,重庆
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.services.name_normalizer import normalize_poi_name
from fetch_indoor_osm import OVERPASS_URL, USER_AGENT, _get_name, _load_kb  # noqa: E402
from fetch_food_osm import OVERPASS_URLS, _city_bbox_tight  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "hotels_osm.json"

TARGET_PER_CITY = 6
DELAY_BETWEEN = 1.2
MAX_RETRIES = 3

_TOURISM_TAG_TO_LABEL = {
    "hotel": "酒店",
    "guest_house": "民宿",
    "hostel": "青旅",
}

# 无辨识度泛称与连锁（住宿建议要有辨识度；连锁中端品牌保留——用户要的就是靠谱住宿）
GENERIC_NAMES = {"酒店", "宾馆", "旅馆", "住宿", "客栈", "民宿", "招待所"}


def _build_query(bbox: str) -> str:
    return (
        "[out:json][timeout:50];\n"
        "(\n"
        f'  node["tourism"~"^(hotel|guest_house|hostel)$"]["name"]({bbox});\n'
        f'  way["tourism"~"^(hotel|guest_house|hostel)$"]["name"]({bbox});\n'
        ");\n"
        "out center tags 60;"
    )


async def fetch_city(
    client: httpx.AsyncClient, city: str, bbox: str
) -> List[Dict[str, Any]]:
    query = _build_query(bbox)
    data: Optional[Dict[str, Any]] = None
    for attempt in range(MAX_RETRIES):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            r = await client.post(
                url,
                content=f"data={httpx.QueryParams({'data': query})['data']}",
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if r.status_code != 200 and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(6 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(6 * (attempt + 1))
            else:
                logger.error(f"  {city}: Overpass 请求失败: {e}")
                return []

    results: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for el in (data or {}).get("elements", []):
        tags = el.get("tags", {})
        name = _get_name(tags)
        if not name or len(name) < 2 or name in GENERIC_NAMES:
            continue
        label = _TOURISM_TAG_TO_LABEL.get(tags.get("tourism", ""), "酒店")

        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        norm = normalize_poi_name(name)
        if norm in seen:
            continue
        seen.add(norm)

        results.append({
            "name": name,
            "city": city,
            "lat": lat,
            "lon": lon,
            "address": tags.get("addr:full") or tags.get("addr:street") or "",
            "osm_id": f"{el.get('type')}/{el.get('id')}",
            "osm_verified": True,
            "source": "osm-overpass",
            "tags": ["住宿", label],
            "suitable_for": "住宿",
            "best_time": "全年",
            "price_level": "适中",
            "popularity_score": 4,
            "rating": None,
            "comment_count": 0,
            "ai_enriched": False,
            "indoor_type": "住宿",
        })
        if len(results) >= TARGET_PER_CITY:
            break

    logger.info(f"  {city}: {len(results)} 条住宿 POI")
    return results


async def main(cities: Optional[List[str]] = None) -> None:
    attractions = _load_kb()
    if cities is None:
        cities = sorted({a.get("city", "") for a in attractions if a.get("city")})

    kb_names: Dict[str, Set[str]] = {}
    for a in attractions:
        c, n = a.get("city", ""), normalize_poi_name(a.get("name", ""))
        if c and n:
            kb_names.setdefault(c, set()).add(n)

    all_pois: List[Dict[str, Any]] = []
    city_stats: Dict[str, int] = {}

    async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
        for city in cities:
            bbox = _city_bbox_tight(attractions, city)
            if not bbox:
                logger.warning(f"  {city}: KB 无坐标，跳过")
                continue
            pois = await fetch_city(client, city, bbox)
            existing = kb_names.get(city, set())
            deduped = [p for p in pois if normalize_poi_name(p["name"]) not in existing]
            all_pois.extend(deduped)
            city_stats[city] = len(deduped)
            await asyncio.sleep(DELAY_BETWEEN)

    output = {
        "source": "OpenStreetMap Overpass API (ODbL)",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(all_pois),
        "indoor_pois": all_pois,  # 与 merge_indoor_pois.py 输入契约兼容
        "city_stats": city_stats,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"\n共 {len(all_pois)} 条住宿 POI，已保存 {OUTPUT_FILE}")
    logger.info("Next: python scripts/merge_indoor_pois.py --input data/hotels_osm.json")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="从 OSM Overpass 采集住宿 POI")
    parser.add_argument("--cities", type=str, default="")
    args = parser.parse_args()
    city_list = [c.strip() for c in args.cities.split(",") if c.strip()] or None
    asyncio.run(main(cities=city_list))

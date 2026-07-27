"""
TravelMind Agent — OSM Indoor POI Fetcher

用 OpenStreetMap Overpass API（ODbL，无需 Key）采集室内场所：
博物馆/美术馆、购物中心/百货、剧院、图书馆、水族馆。
解决 Wikidata/Wikipedia 被 GFW 阻断、高德 Key 缺失时的室内 POI 数据来源问题。

数据全部来自 OSM 真实节点（带 osm_id 可追溯），严禁任何合成字段：
OSM 没有评分数据，rating 一律为 null，popularity_score 统一给中性值 4。

城市范围：从 attractions.json 中该城市现有 POI 的坐标推导 bbox（外扩 0.15°），
无需调用地理编码 API。

用法：
  cd backend
  python scripts/fetch_indoor_osm.py                    # 低覆盖城市（读 indoor_coverage_report.json）
  python scripts/fetch_indoor_osm.py --cities 武汉,郑州  # 指定城市
"""

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.name_normalizer import normalize_poi_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
COVERAGE_REPORT_FILE = DATA_DIR / "indoor_coverage_report.json"
OUTPUT_FILE = DATA_DIR / "indoor_osm.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "TravelMindAgent/0.2 (travel planning research)"

# OSM tag → 室内类别（tags 与 itinerary_contract._TAG_INDOOR_KW 对齐）
OSM_TAG_MAP = {
    'node["tourism"="museum"]': "博物馆",
    'way["tourism"="museum"]': "博物馆",
    'node["shop"="mall"]': "购物中心",
    'way["shop"="mall"]': "购物中心",
    'node["shop"="department_store"]': "购物中心",
    'way["shop"="department_store"]': "购物中心",
    'node["amenity"="theatre"]': "剧院",
    'way["amenity"="theatre"]': "剧院",
    'node["amenity"="library"]': "图书馆",
    'way["amenity"="library"]': "图书馆",
    'node["tourism"="aquarium"]': "海洋馆",
    'way["tourism"="aquarium"]': "海洋馆",
}

_CATEGORY_TAGS: Dict[str, List[str]] = {
    "博物馆": ["博物馆", "文化", "室内"],
    "购物中心": ["购物", "商场", "室内"],
    "剧院": ["剧院", "演出", "室内"],
    "图书馆": ["图书馆", "文化", "室内"],
    "海洋馆": ["海洋馆", "亲子", "室内"],
}

TARGET_PER_CITY = 20
BBOX_PAD = 0.15  # 城市 bbox 外扩度数（约 ±15km）
DELAY_BETWEEN = 1.0  # Overpass 公共实例限速
MAX_RETRIES = 2

# OSM shop=mall 标签里常混入超市/药房等，对旅行推荐无价值
NOISE_KEYWORDS = ("超市", "便利店", "菜场", "大药房", "营业厅", "菜市场")

# 纯类目泛称（无辨识度）与校园内部设施，对游客无价值
GENERIC_NAMES = {"图书馆", "博物馆", "美术馆", "剧院", "购物中心", "商场", "海洋馆"}
CAMPUS_RE = re.compile(r"(大学|学院|校区).{0,8}图书馆$")


def _load_target_cities() -> List[str]:
    if COVERAGE_REPORT_FILE.exists():
        with open(COVERAGE_REPORT_FILE, "r", encoding="utf-8") as f:
            report = json.load(f)
        cities = [c["city"] for c in report.get("low_coverage_cities", [])]
        if cities:
            return cities
    return ["武汉", "郑州", "长沙"]


def _load_kb() -> List[Dict[str, Any]]:
    with open(ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["attractions"]


def _city_bbox(attractions: List[Dict[str, Any]], city: str) -> Optional[str]:
    """Derive an Overpass bbox (south,west,north,east) from KB coordinates.

    Clamped to ≤0.8° span around the median — outliers (如郑州的少林寺
    远在登封) would otherwise blow the bbox up to 100km and Overpass
    times out on the whole query.
    """
    lats, lons = [], []
    for a in attractions:
        if a.get("city") != city:
            continue
        lat, lon = a.get("lat"), a.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            lats.append(lat)
            lons.append(lon)
    if not lats:
        return None
    lats.sort()
    lons.sort()
    mid_lat = lats[len(lats) // 2]
    mid_lon = lons[len(lons) // 2]
    half = 0.4  # ≈44km 半径，覆盖主城区
    s, n = mid_lat - half, mid_lat + half
    w, e = mid_lon - half, mid_lon + half
    return f"{s:.4f},{w:.4f},{n:.4f},{e:.4f}"


def _build_query(bbox: str) -> str:
    selectors = "\n".join(f"  {sel}({bbox});" for sel in OSM_TAG_MAP)
    return f"[out:json][timeout:60];\n(\n{selectors}\n);\nout center tags 200;"


def _classify(tags: Dict[str, str]) -> Optional[str]:
    if tags.get("tourism") == "museum":
        return "博物馆"
    if tags.get("shop") in ("mall", "department_store"):
        return "购物中心"
    if tags.get("amenity") == "theatre":
        return "剧院"
    if tags.get("amenity") == "library":
        return "图书馆"
    if tags.get("tourism") == "aquarium":
        return "海洋馆"
    return None


def _get_name(tags: Dict[str, str]) -> str:
    """Prefer Chinese name, fall back to default name; '' if none."""
    for key in ("name:zh", "name:zh-Hans", "name"):
        v = tags.get(key, "").strip()
        if v:
            return v
    return ""


async def fetch_city(
    client: httpx.AsyncClient, city: str, bbox: str
) -> List[Dict[str, Any]]:
    """Fetch indoor POIs for one city from Overpass."""
    query = _build_query(bbox)
    data: Optional[Dict[str, Any]] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = await client.post(
                OVERPASS_URL,
                content=f"data={httpx.QueryParams({'data': query})['data']}",
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if r.status_code in (429, 504) and attempt < MAX_RETRIES:
                await asyncio.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(5 * (attempt + 1))
            else:
                logger.error(f"  {city}: Overpass 请求失败: {e}")
                return []

    results: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for el in (data or {}).get("elements", []):
        tags = el.get("tags", {})
        name = _get_name(tags)
        if not name or len(name) < 2:
            continue
        if any(kw in name for kw in NOISE_KEYWORDS):
            continue
        if name in GENERIC_NAMES or CAMPUS_RE.search(name):
            continue
        category = _classify(tags)
        if not category:
            continue

        # 坐标：node 直接给，way 用 center
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
            "tags": list(_CATEGORY_TAGS[category]),
            "suitable_for": "雨天备选、室内休闲",
            "best_time": "全年",
            "price_level": "适中",
            # OSM 无评分数据——诚实留空；popularity 给中性值避免挤压头部景点
            "popularity_score": 4,
            "rating": None,
            "comment_count": 0,
            "ai_enriched": False,
            "indoor_type": category,
        })
        if len(results) >= TARGET_PER_CITY:
            break

    logger.info(f"  {city}: {len(results)} 条室内 POI")
    return results


async def main(cities: Optional[List[str]] = None) -> None:
    if cities is None:
        cities = _load_target_cities()

    attractions = _load_kb()
    kb_names: Dict[str, Set[str]] = {}
    for a in attractions:
        c = a.get("city", "")
        n = normalize_poi_name(a.get("name", ""))
        if c and n:
            kb_names.setdefault(c, set()).add(n)

    all_pois: List[Dict[str, Any]] = []
    city_stats: Dict[str, int] = {}

    async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
        for city in cities:
            bbox = _city_bbox(attractions, city)
            if not bbox:
                logger.warning(f"  {city}: KB 无坐标，无法推导 bbox，跳过")
                city_stats[city] = 0
                continue
            pois = await fetch_city(client, city, bbox)
            # 与 KB 去重
            existing = kb_names.get(city, set())
            deduped = [p for p in pois
                       if normalize_poi_name(p["name"]) not in existing]
            skipped = len(pois) - len(deduped)
            if skipped:
                logger.info(f"  {city}: 跳过 {skipped} 条 KB 已存在")
            all_pois.extend(deduped)
            city_stats[city] = len(deduped)
            await asyncio.sleep(DELAY_BETWEEN)

    output = {
        "source": "OpenStreetMap Overpass API (ODbL)",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(all_pois),
        "cities_covered": len([c for c, n in city_stats.items() if n > 0]),
        "indoor_pois": all_pois,
        "city_stats": city_stats,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"\n共 {len(all_pois)} 条，已保存 {OUTPUT_FILE}")
    for city, n in sorted(city_stats.items(), key=lambda x: -x[1]):
        logger.info(f"  {city}: {n}")
    logger.info("Next: python scripts/merge_indoor_pois.py --input data/indoor_osm.json")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="从 OSM Overpass 采集室内 POI")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔城市列表，默认读 indoor_coverage_report.json")
    args = parser.parse_args()
    city_list = [c.strip() for c in args.cities.split(",") if c.strip()] or None
    asyncio.run(main(cities=city_list))

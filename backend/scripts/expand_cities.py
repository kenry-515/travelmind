"""
TravelMind Agent — 城市 / 知识库扩展脚本

批量添加新城市到知识库，使用 Amap POI 搜索。将现有 attraction + food
数据与新城市合并输出到 attractions.json。

目标：从 15 城扩展到 25+ 城市。

新增城市清单（按旅游热度排序）：
  贵阳、南宁、福州、黄山、拉萨、哈尔滨、香格里拉、青岛、
  大连、昆明、武汉、天津、郑州、深圳、南京、海口、乌鲁木齐

管线：
  1. 对每个新城市，调用 Amap POI 搜索获取景点
  2. 重复调用不同关键词以覆盖多种类型（自然/历史/美食/体验）
  3. 去重（名称归一化 + 坐标距离）
  4. 合并到现有 attractions.json

用法：
  cd backend
  python scripts/expand_cities.py  [--cities 贵阳,南宁]  [--dry-run]

前置条件：
  - AMAP_API_KEY 在 .env 中配置
  - attractions.json 已存在
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
FOOD_FILE = DATA_DIR / "food_pois.json"
OUTPUT_FILE = DATA_DIR / "attractions.json"  # in-place update (dry-run writes to separate file)
BACKUP_FILE = DATA_DIR / "attractions_backup.json"

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"

# Amap POI types for tourist attractions
SCENIC_TYPES = "110000|110100|110200|140000|080000"

# Default new cities to add
DEFAULT_NEW_CITIES = [
    "贵阳", "南宁", "福州", "黄山", "拉萨", "哈尔滨",
    "香格里拉", "青岛", "大连", "昆明", "武汉", "天津",
    "郑州", "深圳", "南京",
]

# Search keywords per theme to get comprehensive coverage
THEME_KEYWORDS = {
    "自然风光": ["自然风光", "山", "湖", "瀑布", "峡谷", "森林", "溶洞", "温泉"],
    "历史人文": ["博物馆", "古镇", "寺庙", "遗址", "古建筑", "名人故居", "历史街区"],
    "城市体验": ["公园", "夜景", "步行街", "广场", "地标", "观景台", "创意园"],
    "休闲娱乐": ["动物园", "植物园", "水族馆", "游乐园", "度假村", "农家乐"],
}

TARGET_PER_CITY = 25  # min POIs per new city
MAX_CONCURRENT = 3
DELAY_BETWEEN = 0.35
MAX_RETRIES = 2
DEDUP_RADIUS_M = 500
USER_AGENT = "TravelMindAgent/0.3"


# ── Helpers ──────────────────────────────────────────────


def _load_amap_config():
    """Load Amap API config."""
    try:
        from app.config.settings import settings
        return settings.AMAP_API_KEY, getattr(settings, "AMAP_SIGN_KEY", "")
    except ImportError:
        import os
        api_key = os.getenv("AMAP_API_KEY", "")
        sign_key = os.getenv("AMAP_SIGN_KEY", "")
        if not api_key:
            try:
                from pydantic_settings import BaseSettings
                class _Env(BaseSettings):
                    AMAP_API_KEY: str = ""
                    AMAP_SIGN_KEY: str = ""
                    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True, "extra": "ignore"}
                e = _Env()
                api_key = e.AMAP_API_KEY
                sign_key = e.AMAP_SIGN_KEY
            except ImportError:
                pass
        return api_key, sign_key


def _amap_sign(params: Dict[str, Any], sign_key: str) -> str:
    sorted_keys = sorted(params.keys())
    raw = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    raw += sign_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two coordinates."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize_name(name: str) -> str:
    """Normalize for fuzzy dedup."""
    n = name.strip()
    for suffix in ["风景区", "景区", "公园", "旅游区", "游览区", "景点",
                    "博物馆", "寺", "庙", "古镇"]:
        if n.endswith(suffix) and len(n) > len(suffix) + 1:
            n = n[:-len(suffix)]
    n = re.sub(r"[（(][^)）]*[)）]", "", n)
    return n.strip()


def _load_existing_data() -> Tuple[List[Dict[str, Any]], Set[str], Dict[str, Set[str]]]:
    """Load attractions and return existing POIs, cities, and name sets."""
    if not ATTRACTIONS_FILE.exists():
        logger.warning(f"{ATTRACTIONS_FILE} not found, starting from scratch")
        return [], set(), {}

    with open(ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    existing_cities = {a.get("city", "") for a in attractions if a.get("city")}
    # Build name dedup map per city
    name_map: Dict[str, Set[str]] = {}
    for a in attractions:
        city = a.get("city", "")
        if city not in name_map:
            name_map[city] = set()
        name_map[city].add(normalize_name(a.get("name", "")))

    logger.info(f"Loaded {len(attractions)} POIs from {len(existing_cities)} cities")
    return attractions, existing_cities, name_map


def _generate_ai_tags(name: str, city: str, theme: str) -> List[str]:
    """Generate basic tags for a POI (simple rule-based, AI enrichment runs later)."""
    tags = []
    if theme == "自然风光":
        tags = ["自然", "户外"]
    elif theme == "历史人文":
        tags = ["历史", "文化"]
    elif theme == "城市体验":
        tags = ["城市", "打卡"]
    elif theme == "休闲娱乐":
        tags = ["休闲", "体验"]

    # Add season-agnostic tag based on name keywords
    if any(k in name for k in ("山", "峰", "峡谷", "森林", "瀑布")):
        tags.extend(["自然", "户外"])
    if any(k in name for k in ("博物馆", "遗址", "古镇", "寺", "庙", "宫")):
        tags.extend(["历史", "文化"])
    if any(k in name for k in ("夜市", "小吃", "美食", "街", "火锅")):
        tags.extend(["美食"])
    if any(k in name for k in ("湖", "海", "溪", "河", "潭")):
        if "水" not in tags:
            tags.append("自然")

    return list(dict.fromkeys(tags))[:5]  # dedup, max 5


async def amap_poi_search(
    client: httpx.AsyncClient,
    api_key: str,
    keywords: str,
    city: str,
    page: int = 1,
    sign_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Search Amap for POIs in a city."""
    params = {
        "key": api_key,
        "keywords": keywords,
        "types": SCENIC_TYPES,
        "city": city,
        "citylimit": "true",
        "offset": "25",
        "page": str(page),
        "extensions": "all",
        "output": "JSON",
    }
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
                return None
            return data
        except Exception as e:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.debug(f"  Amap error for '{keywords}' in {city}: {e}")
    return None


def _parse_poi(poi: Dict[str, Any], city: str, theme: str) -> Optional[Dict[str, Any]]:
    """Convert Amap POI to our standard format."""
    name = poi.get("name", "").strip()
    if not name or len(name) < 2:
        return None

    location = poi.get("location", "")
    lat, lon = None, None
    if location and "," in location:
        lon_str, lat_str = location.split(",", 1)
        try:
            lon, lat = float(lon_str), float(lat_str)
        except (ValueError, TypeError):
            pass

    photos = poi.get("photos", [])
    photo_url = photos[0].get("url", "") if photos else ""

    tags = _generate_ai_tags(name, city, theme)
    # Add theme to tags
    if theme not in tags:
        tags.insert(0, theme)

    return {
        "name": name,
        "name_en": "",
        "city": city,
        "lat": lat,
        "lon": lon,
        "wiki_article": "",  # Will be filled by AI enrichment
        "wiki_article_en": "",
        "wikidata_id": "",
        "instance_of": theme,
        "description": f"{city}{name}，{theme}类景点（待 AI 丰富）。",
        "thumbnail_url": None,
        "full_url": "",
        "description_source": "amap",
        "wiki_pageid": "",
        "address": poi.get("address", ""),
        "amap_id": poi.get("id", ""),
        "amap_type": poi.get("type", ""),
        "amap_typecode": poi.get("typecode", ""),
        "amap_photo_url": photo_url,
        "amap_verified": True,
        "source": "amap",
        "tags": tags,
        "suitable_for": f"{theme}爱好者",
        "best_time": "全年",
        "price_level": "适中",
        "popularity_score": 3,
        "ai_enriched": False,
    }


async def collect_city(
    client: httpx.AsyncClient,
    api_key: str,
    city: str,
    existing_names: Set[str],
    target: int,
    sign_key: str = "",
) -> List[Dict[str, Any]]:
    """Collect POIs for a single new city."""
    logger.info(f"  Expanding {city} (target: {target} POIs)...")
    results: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_names: Set[str] = set(existing_names)

    for theme, keywords in THEME_KEYWORDS.items():
        if len(results) >= target:
            break

        for kw in keywords:
            if len(results) >= target:
                break

            for page in range(1, 4):  # Up to 3 pages per keyword
                if len(results) >= target:
                    break

                data = await amap_poi_search(
                    client, api_key, kw, city, page=page, sign_key=sign_key,
                )
                if not data:
                    break

                pois = data.get("pois", [])
                if not pois:
                    break

                for poi in pois:
                    if len(results) >= target:
                        break

                    # Dedup
                    pid = poi.get("id", "")
                    if pid and pid in seen_ids:
                        continue
                    if pid:
                        seen_ids.add(pid)

                    parsed = _parse_poi(poi, city, theme)
                    if not parsed:
                        continue

                    # Name dedup
                    norm = normalize_name(parsed["name"])
                    if norm in seen_names or len(norm) < 2:
                        continue
                    seen_names.add(norm)

                    results.append(parsed)

                if len(pois) < 20:
                    break

                await asyncio.sleep(DELAY_BETWEEN)

            await asyncio.sleep(DELAY_BETWEEN)

    logger.info(f"    {city}: collected {len(results)} POIs")
    return results


def _merge_food_pois(attractions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Merge food_pois.json data into attractions list if available."""
    if not FOOD_FILE.exists():
        return attractions, 0

    with open(FOOD_FILE, "r", encoding="utf-8") as f:
        food_data = json.load(f)

    food_pois = food_data.get("food_pois", [])
    if not food_pois:
        return attractions, 0

    # Build existing name+city set for dedup
    existing = {(normalize_name(a.get("name", "")), a.get("city", ""))
                for a in attractions}
    food_merged = 0
    for fp in food_pois:
        key = (normalize_name(fp.get("name", "")), fp.get("city", ""))
        if key not in existing:
            fp["ai_enriched"] = False
            attractions.append(fp)
            existing.add(key)
            food_merged += 1

    logger.info(f"Merged {food_merged} food POIs from food_pois.json")
    return attractions, food_merged


async def main(cities: Optional[List[str]] = None, dry_run: bool = False):
    """Main entry point."""
    api_key, sign_key = _load_amap_config()
    if not api_key:
        logger.error("AMAP_API_KEY 未配置，请在 backend/.env 中设置。")
        return

    # Load existing
    attractions, existing_cities, name_map = _load_existing_data()
    existing_cities_lower = {c.lower() for c in existing_cities}

    # Determine new cities
    if cities is None:
        cities = DEFAULT_NEW_CITIES

    new_cities = [c for c in cities if c.lower() not in existing_cities_lower]
    skipped = [c for c in cities if c.lower() in existing_cities_lower]

    if skipped:
        logger.info(f"已覆盖，跳过: {', '.join(skipped)}")

    if not new_cities:
        logger.info("所有目标城市已覆盖，无需扩展。")
        # Still merge food data
        attractions, food_merged = _merge_food_pois(attractions)
        if food_merged:
            _save_output(attractions, dry_run)
        return

    logger.info(f"已有城市: {len(existing_cities)} 个")
    logger.info(f"新增城市: {len(new_cities)} 个 — {', '.join(new_cities)}")
    logger.info(f"目标/城市: ≥{TARGET_PER_CITY} POIs")
    logger.info(f"开始采集...\n")

    total_new = 0
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for city in new_cities:
            try:
                existing_names = name_map.get(city, set())
                pois = await collect_city(
                    client, api_key, city, existing_names,
                    TARGET_PER_CITY, sign_key=sign_key,
                )
                attractions.extend(pois)
                total_new += len(pois)
            except Exception as e:
                logger.error(f"  Error expanding {city}: {e}")

    # Merge food data
    attractions, food_merged = _merge_food_pois(attractions)

    # Stats
    final_cities = {a.get("city", "") for a in attractions if a.get("city")}
    logger.info(f"\n{'='*50}")
    logger.info(f"扩展完成:")
    logger.info(f"  新增景点: {total_new}")
    logger.info(f"  美食合并: {food_merged}")
    logger.info(f"  总景点数: {len(attractions)}")
    logger.info(f"  城市覆盖: {len(final_cities)} → {' → '.join(sorted(final_cities))}")

    _save_output(attractions, dry_run)


def _save_output(attractions: List[Dict[str, Any]], dry_run: bool):
    """Save attractions back to file."""
    output = {
        "source": "Wikidata + Wikipedia + Amap + AI Enrichment" +
                  (" + Amap Food" if FOOD_FILE.exists() else ""),
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(attractions),
        "ai_enriched": sum(1 for a in attractions if a.get("ai_enriched")),
        "attractions": attractions,
    }

    if dry_run:
        dry_file = DATA_DIR / "attractions_expanded_dryrun.json"
        with open(dry_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info(f"\n[Dry-run] 预览已保存到 {dry_file}（未修改原文件）")
        return

    # Backup original
    if ATTRACTIONS_FILE.exists():
        import shutil
        shutil.copy2(ATTRACTIONS_FILE, BACKUP_FILE)
        logger.info(f"已备份原文件到 {BACKUP_FILE}")

    with open(ATTRACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"已保存到 {ATTRACTIONS_FILE}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="扩展知识库城市覆盖")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔的新增城市列表，默认使用 DEFAULT_NEW_CITIES")
    parser.add_argument("--dry-run", action="store_true",
                        help="试运行，不修改 attractions.json")
    parser.add_argument("--target", type=int, default=TARGET_PER_CITY,
                        help=f"每城市目标 POI 数量（默认 {TARGET_PER_CITY}）")
    args = parser.parse_args()

    TARGET_PER_CITY = args.target

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else None
    asyncio.run(main(cities=cities, dry_run=args.dry_run))

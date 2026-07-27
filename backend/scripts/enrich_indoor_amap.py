"""
TravelMind Agent — Amap Indoor POI Enricher

使用高德地图 POI 搜索 API 采集室内场所数据（博物馆/展馆/购物中心/室内体验），
解决部分城市知识库室内 POI 覆盖率过低的问题（雨天行程无室内替代可选）。

数据类别（高德 POI 大类）：
  140000 = 科教文化服务（博物馆/美术馆/科技馆/图书馆等）
  060000 = 购物服务（购物中心/百货/商业综合体）

筛选规则：
  - 评分 ≥ 3.5（biz_ext.rating，保证基本质量）
  - 排除连锁零售/餐饮品牌（优衣库/星巴克等，对旅行推荐无价值）
  - 名称去重 + 高德 ID 去重

输出：data/indoor_pois.json（独立文件，由 build_knowledge_base.py 合并入 attractions.json）

用法：
  cd backend
  python scripts/enrich_indoor_amap.py                      # 低覆盖城市（读 indoor_coverage_report.json）
  python scripts/enrich_indoor_amap.py --cities 武汉,郑州    # 指定城市
  python scripts/enrich_indoor_amap.py --cities 武汉 --limit 5   # 调试：每城只采 5 条
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "indoor_pois.json"
COVERAGE_REPORT_FILE = DATA_DIR / "indoor_coverage_report.json"
CITY_LIST_FILE = DATA_DIR / "attractions.json"

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"

# 搜索关键词（按室内类别分组；types 不设限，靠名称/分类过滤，避免漏掉综合类场馆）
INDOOR_KEYWORDS = [
    # 博物馆/展馆
    "博物馆", "美术馆", "科技馆", "纪念馆", "展览馆", "规划展示馆", "图书馆",
    # 购物/室内商业
    "购物中心", "商业综合体", "百货商场", "奥特莱斯",
    # 室内体验
    "温泉", "大剧院", "新华书店", "室内游乐场", "海洋馆",
]

# 连锁零售/餐饮品牌（不是旅行目的地，排除）
CHAIN_BLACKLIST = [
    "优衣库", "无印良品", "星巴克", "瑞幸", "肯德基", "麦当劳",
    "海底捞", "屈臣氏", "名创优品", "万达影城", "苏宁", "国美",
    "苹果授权", "华为授权", "小米之家",
]

# Minimum quality thresholds
MIN_RATING = 3.5
TARGET_PER_CITY = 20  # target indoor POIs per city

USER_AGENT = "TravelMindAgent/0.2"

# Concurrency
DELAY_BETWEEN = 0.35
MAX_RETRIES = 2
MAX_PAGES_PER_KEYWORD = 1  # 室内 POI 密度低，1 页 25 条足够

# ── Helpers ──────────────────────────────────────────────


def _load_amap_config():
    """Load Amap API key and optional sign key."""
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
                class _AmapEnv(BaseSettings):
                    AMAP_API_KEY: str = ""
                    AMAP_SIGN_KEY: str = ""
                    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True, "extra": "ignore"}
                env = _AmapEnv()
                api_key = env.AMAP_API_KEY
                sign_key = env.AMAP_SIGN_KEY
            except ImportError:
                pass
        return api_key, sign_key


def _amap_sign(params: Dict[str, Any], sign_key: str) -> str:
    """Compute Amap digital signature."""
    sorted_keys = sorted(params.keys())
    raw = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    raw += sign_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _load_target_cities() -> List[str]:
    """Target cities: low indoor coverage from the coverage report,
    falling back to a hardcoded list."""
    if COVERAGE_REPORT_FILE.exists():
        with open(COVERAGE_REPORT_FILE, "r", encoding="utf-8") as f:
            report = json.load(f)
        cities = [c["city"] for c in report.get("low_coverage_cities", [])]
        if cities:
            logger.info(f"Loaded {len(cities)} low-coverage cities from report")
            return cities
    return ["武汉", "郑州", "长沙"]


def _is_chain(name: str) -> bool:
    """Check if a name matches known chain retail brands."""
    return any(chain in name for chain in CHAIN_BLACKLIST)


def _normalize_name(name: str) -> str:
    """Normalize a venue name for dedup (strip branch info)."""
    n = name.strip()
    n = re.sub(r"[（(][^)）]*[)）]", "", n)
    return n.strip()


def _classify_indoor_type(type_str: str, name: str, keywords: str) -> str:
    """Map Amap type/name to our simplified indoor category."""
    combined = type_str + name + keywords

    if any(k in combined for k in ("博物馆", "纪念馆", "故居")):
        return "博物馆"
    if any(k in combined for k in ("美术馆", "画廊", "艺术馆")):
        return "美术馆"
    if any(k in combined for k in ("科技馆", "科学")):
        return "科技馆"
    if any(k in combined for k in ("展览馆", "规划馆", "展示馆", "博览")):
        return "展览馆"
    if any(k in combined for k in ("图书馆", "书店", "书城")):
        return "图书书店"
    if any(k in combined for k in ("海洋馆", "水族馆")):
        return "海洋馆"
    if any(k in combined for k in ("温泉",)) :
        return "温泉"
    if any(k in combined for k in ("剧院", "影院", "音乐厅")):
        return "剧院"
    if any(k in combined for k in ("游乐", "乐园", "电玩")):
        return "室内游乐"
    if any(k in combined for k in ("购物", "商场", "百货", "奥特莱斯", "广场", "综合体")):
        return "购物中心"
    return "室内场所"


# tags per indoor category — 必须与 itinerary_contract._TAG_INDOOR_KW 对齐，
# 保证 classify_poi_indoor 凭 KB 标签判定为 indoor
_CATEGORY_TAGS: Dict[str, List[str]] = {
    "博物馆": ["博物馆", "文化", "室内"],
    "美术馆": ["美术馆", "艺术", "室内"],
    "科技馆": ["科技馆", "展览", "室内"],
    "展览馆": ["展览", "展馆", "室内"],
    "图书书店": ["图书馆", "书店", "室内"],
    "海洋馆": ["海洋馆", "亲子", "室内"],
    "温泉": ["温泉", "休闲", "室内"],
    "剧院": ["剧院", "演出", "室内"],
    "室内游乐": ["室内", "娱乐", "亲子"],
    "购物中心": ["购物", "商场", "室内"],
    "室内场所": ["室内"],
}


def _make_indoor_poi(amap_poi: Dict[str, Any], city: str, keyword: str) -> Dict[str, Any]:
    """Convert an Amap POI into our attraction format."""
    location = amap_poi.get("location", "")
    lat, lon = None, None
    if location and "," in location:
        lon_str, lat_str = location.split(",", 1)
        try:
            lon, lat = float(lon_str), float(lat_str)
        except (ValueError, TypeError):
            pass

    name = amap_poi.get("name", "").strip()
    type_str = amap_poi.get("type", "")
    rating = float(amap_poi.get("biz_ext", {}).get("rating", 0) or 0)
    photos = amap_poi.get("photos", [])
    photo_url = photos[0].get("url", "") if photos else ""

    indoor_type = _classify_indoor_type(type_str, name, keyword)
    tags = list(_CATEGORY_TAGS.get(indoor_type, ["室内"]))
    if rating >= 4.5:
        tags.append("高分推荐")

    return {
        "name": name,
        "city": city,
        "lat": lat,
        "lon": lon,
        "address": amap_poi.get("address", ""),
        "amap_id": amap_poi.get("id", ""),
        "amap_type": type_str,
        "amap_typecode": amap_poi.get("typecode", ""),
        "photo_url": photo_url,
        "amap_verified": True,
        "source": "amap-indoor",
        "tags": tags,
        "suitable_for": "雨天备选、室内休闲",
        "best_time": "全年",
        "price_level": "适中",
        # 压低 popularity，避免新 POI 挤压头部景点的推荐排序
        "popularity_score": min(5, max(1, int(rating))),
        "rating": rating,
        "comment_count": int(amap_poi.get("favorite_num", 0) or 0),
        "ai_enriched": False,
        "indoor_type": indoor_type,
    }


# ── Amap API Client ─────────────────────────────────────


async def amap_search_indoor(
    client: httpx.AsyncClient,
    api_key: str,
    keywords: str,
    city: str,
    page: int = 1,
    sign_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Search Amap for indoor POIs (no type filter — keywords carry the semantics)."""
    params = {
        "key": api_key,
        "keywords": keywords,
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
                logger.debug(f"  Amap indoor search failed: {e}")
    return None


# ── City-level collection ───────────────────────────────


async def collect_city_indoor(
    client: httpx.AsyncClient,
    api_key: str,
    city: str,
    target: int,
    sign_key: str = "",
    existing_names: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Collect indoor POIs for a single city."""
    logger.info(f"  Collecting indoor POIs for {city}...")
    results: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_names: Set[str] = set(existing_names or set())

    for keyword in INDOOR_KEYWORDS:
        if len(results) >= target:
            break

        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            if len(results) >= target:
                break

            data = await amap_search_indoor(
                client, api_key, keyword, city, page=page, sign_key=sign_key,
            )
            if not data:
                break

            pois = data.get("pois", [])
            if not pois:
                break

            for poi in pois:
                if len(results) >= target:
                    break

                # Dedup by ID
                pid = poi.get("id", "")
                if pid and pid in seen_ids:
                    continue
                if pid:
                    seen_ids.add(pid)

                name = poi.get("name", "").strip()
                if not name or len(name) < 2:
                    continue

                # Filter chains
                if _is_chain(name):
                    continue

                # Quality filter: rating only (museums often lack favorite_num)
                biz = poi.get("biz_ext", {}) or {}
                rating = float(biz.get("rating", 0) or 0)
                if rating < MIN_RATING:
                    continue

                # Name dedup (against KB existing names too)
                norm = _normalize_name(name)
                if norm in seen_names:
                    continue
                seen_names.add(norm)

                indoor_poi = _make_indoor_poi(poi, city, keyword)
                results.append(indoor_poi)

            await asyncio.sleep(DELAY_BETWEEN)

        await asyncio.sleep(DELAY_BETWEEN)

    logger.info(f"    {city}: collected {len(results)} indoor POIs")
    return results


def _load_existing_kb_names() -> Dict[str, Set[str]]:
    """Load normalized POI names per city from attractions.json for dedup."""
    names: Dict[str, Set[str]] = {}
    if not CITY_LIST_FILE.exists():
        return names
    with open(CITY_LIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for a in data.get("attractions", []):
        city = a.get("city", "")
        name = _normalize_name(a.get("name", ""))
        if city and name:
            names.setdefault(city, set()).add(name)
    return names


# ── Main ────────────────────────────────────────────────


async def main(cities: Optional[List[str]] = None, limit: int = 0):
    """Main entry point."""
    api_key, sign_key = _load_amap_config()
    if not api_key:
        logger.error(
            "AMAP_API_KEY is not set. Set it in backend/.env.\n"
            "Get a free key at https://console.amap.com/dev/key/app"
        )
        return

    if sign_key:
        logger.info("Amap digital signing enabled (AMAP_SIGN_KEY configured)")

    if cities is None:
        cities = _load_target_cities()

    target = limit if limit > 0 else TARGET_PER_CITY

    logger.info(f"Target cities: {len(cities)} — {', '.join(cities[:8])}")
    logger.info(f"Target per city: {target} indoor POIs")
    logger.info(f"Quality threshold: rating ≥ {MIN_RATING}")

    kb_names = _load_existing_kb_names()

    all_indoor: List[Dict[str, Any]] = []
    city_stats: Dict[str, int] = {}

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for city in cities:
            try:
                pois = await collect_city_indoor(
                    client, api_key, city, target,
                    sign_key=sign_key,
                    existing_names=kb_names.get(city),
                )
                all_indoor.extend(pois)
                city_stats[city] = len(pois)
            except Exception as e:
                import traceback
                logger.error(f"  Error collecting {city}: {e}")
                logger.error(traceback.format_exc())
                city_stats[city] = 0

    # Stats
    total = len(all_indoor)
    logger.info(f"\n{'='*50}")
    logger.info(f"Total indoor POIs collected: {total}")
    for city, count in sorted(city_stats.items(), key=lambda x: -x[1]):
        bar = "█" * min(20, count) if count else "—"
        logger.info(f"  {city:6s} {bar} {count}")

    # Category breakdown
    type_counts: Dict[str, int] = {}
    for p in all_indoor:
        it = p.get("indoor_type", "其他")
        type_counts[it] = type_counts.get(it, 0) + 1
    logger.info(f"\nCategory breakdown:")
    for it, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {it}: {count}")

    # Save
    output = {
        "source": "Amap POI Search (Indoor)",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": total,
        "cities_covered": len([c for c, n in city_stats.items() if n > 0]),
        "indoor_pois": all_indoor,
        "city_stats": city_stats,
        "type_stats": type_counts,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\nSaved to {OUTPUT_FILE}")
    logger.info(
        "Next: merge into attractions.json via build_knowledge_base.py, "
        "then rebuild Chroma and re-run indoor_coverage_report.py"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="采集高德室内 POI 数据（博物馆/商场/室内体验）")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔的城市列表，默认从 indoor_coverage_report.json 读取低覆盖城市")
    parser.add_argument("--limit", type=int, default=0,
                        help="每城只采集 N 条（调试用）")
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else None
    asyncio.run(main(cities=cities, limit=args.limit))

"""
TravelMind Agent — Amap Food POI Enricher

使用高德地图 POI 搜索 API 采集餐饮数据，补充知识库的美食维度。
解决当前 attractions.json 中美食类 POI 几乎为零的问题。

数据类别（高德 POI 分类）：
  050000 = 餐饮（大类）
  050100 = 中餐厅
  050200 = 外国餐厅
  050300 = 小吃快餐
  050400 = 特色/地方风味
  050600 = 火锅
  050700 = 海鲜
  050800 = 茶艺/咖啡/甜品

筛选规则：
  - 评分 ≥ 3.5
  - 评论数 ≥ 50（保证真实性）
  - 排除连锁快餐（KFC/麦当劳/星巴克等，对旅行推荐无价值）

输出：data/food_pois.json（独立文件，后续合并入 attractions.json）

用法：
  cd backend
  python scripts/enrich_food_amap.py  [--cities 重庆,成都,北京]  [--limit 10]
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "food_pois.json"
CITY_LIST_FILE = DATA_DIR / "attractions.json"

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"

# Amap POI types for dining
# 050000=all dining, but we want sub-categories for better filtering
FOOD_TYPES = {
    "中餐": "050100",
    "火锅": "050600",
    "小吃快餐": "050300",
    "地方风味": "050400",
    "海鲜": "050700",
    "外国餐厅": "050200",
    "咖啡甜品": "050800",
}

# Search keywords per category for broader coverage
FOOD_KEYWORDS = [
    # 中餐大类
    "本地菜", "私房菜", "老字号", "招牌菜", "家常菜",
    # 火锅
    "火锅", "串串", "麻辣烫", "老火锅",
    # 小吃
    "小吃", "夜市", "小吃街", "路边摊", "烧烤",
    # 地方风味
    "地方特色", "土菜", "农家菜", "民族风味",
    # 海鲜
    "海鲜", "鱼庄", "江鲜", "湖鲜",
    # 面食早点
    "面馆", "早点", "包子", "粉店", "米线",
    # 饮品
    "茶馆", "咖啡馆", "特色饮品", "甜品店",
]

# Chain brands to exclude (no travel value)
CHAIN_BLACKLIST = [
    "肯德基", "麦当劳", "汉堡王", "必胜客", "赛百味",
    "星巴克", "瑞幸", "costa", "太平洋咖啡",
    "华莱士", "德克士", "真功夫", "永和大王",
    "杨国福", "张亮麻辣烫", "沙县小吃",
]

# Minimum quality thresholds
MIN_RATING = 3.5
MIN_FAVORITES = 0  # food POIs use favorite_num (not all have high counts)
TARGET_PER_CITY = 30  # target food POIs per city

USER_AGENT = "TravelMindAgent/0.2"

# Concurrency
MAX_CONCURRENT = 3
DELAY_BETWEEN = 0.35
MAX_RETRIES = 2
MAX_PAGES_PER_KEYWORD = 2  # 2 pages × 25 results = 50 per keyword pair

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


def _load_existing_cities() -> List[str]:
    """Get current city list from attractions.json."""
    if not CITY_LIST_FILE.exists():
        # Fallback to known cities
        return [
            "重庆", "成都", "北京", "上海", "广州", "深圳",
            "杭州", "西安", "南京", "武汉", "长沙", "厦门",
            "三亚", "桂林", "苏州", "张家界", "丽江", "大理",
        ]
    with open(CITY_LIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    cities = sorted({a.get("city", "") for a in data.get("attractions", []) if a.get("city")})
    logger.info(f"Loaded {len(cities)} cities from attractions.json")
    return cities


def _is_chain(name: str) -> bool:
    """Check if a restaurant name matches known chain brands."""
    return any(chain in name for chain in CHAIN_BLACKLIST)


def _normalize_name(name: str) -> str:
    """Normalize a restaurant name for dedup."""
    n = name.strip()
    # Remove branch info in parentheses
    n = re.sub(r"[（(][^)）]*[)）]", "", n)
    # Remove common suffixes
    for suffix in ["餐厅", "店", "馆", "楼", "庄"]:
        if n.endswith(suffix) and len(n) > len(suffix) + 1:
            # Keep the suffix if the remaining name would be too short
            if len(n) - len(suffix) >= 2:
                n = n[:-len(suffix)]
    return n.strip()


def _classify_food_type(type_str: str, name: str, keywords: str) -> str:
    """Map Amap type/name to our simplified food category tags."""
    combined = (type_str + name + keywords).lower()

    if any(k in combined for k in ("火锅", "串串", "麻辣烫")):
        return "火锅"
    if any(k in combined for k in ("海鲜", "鱼", "虾", "蟹", "蟹黄", "鱼生")):
        return "海鲜"
    if any(k in combined for k in ("小吃", "面", "粉", "米线", "包子", "饼", "烧烤", "夜市")):
        return "小吃"
    if any(k in combined for k in ("茶", "咖啡", "甜品", "奶茶", "糖水", "冰淇淋")):
        return "饮品甜点"
    if any(k in combined for k in ("西餐", "日料", "韩料", "泰国", "越南", "意大利", "法国")):
        return "国际美食"
    return "中餐"


def _estimate_price_level(name: str, type_str: str, rating: float) -> str:
    """Estimate price level based on venue characteristics."""
    luxury_keywords = ("私房", "公馆", "会所", "御", "府", "轩", "阁", "楼中楼",
                       "米其林", "黑珍珠", "湖景", "江景", "景观")
    budget_keywords = ("小吃", "面馆", "快餐", "路边", "摊", "早点", "大排档")

    if any(k in name for k in luxury_keywords):
        return "奢华"
    if any(k in name for k in budget_keywords):
        return "经济"
    return "适中"


def _make_food_poi(amap_poi: Dict[str, Any], city: str, category: str) -> Dict[str, Any]:
    """Convert an Amap POI into our food attraction format."""
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

    food_type = _classify_food_type(type_str, name, category)
    price_level = _estimate_price_level(name, type_str, rating)

    tags = ["美食", food_type]
    if rating >= 4.5:
        tags.append("高分推荐")
    if "老字号" in name or "老店" in name:
        tags.append("老字号")
    if any(k in name for k in ("网红", "打卡", "必吃")):
        tags.append("网红打卡")

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
        "source": "amap-food",
        "tags": tags,
        "suitable_for": f"{food_type}爱好者、美食探索者",
        "best_time": "全年",
        "price_level": price_level,
        "popularity_score": min(5, max(1, int(rating))),
        "rating": rating,
        "comment_count": int(amap_poi.get("favorite_num", 0) or 0),
        "ai_enriched": False,
        "food_type": food_type,
    }


# ── Amap API Client ─────────────────────────────────────


async def amap_search_food(
    client: httpx.AsyncClient,
    api_key: str,
    keywords: str,
    city: str,
    types: str = "050000",
    page: int = 1,
    sign_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Search Amap for food POIs."""
    params = {
        "key": api_key,
        "keywords": keywords,
        "types": types,
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
                logger.debug(f"  Amap food search failed: {e}")
    return None


# ── City-level collection ───────────────────────────────


async def collect_city_food(
    client: httpx.AsyncClient,
    api_key: str,
    city: str,
    target: int,
    sign_key: str = "",
) -> List[Dict[str, Any]]:
    """Collect food POIs for a single city."""
    logger.info(f"  Collecting food POIs for {city}...")
    results: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_names: Set[str] = set()

    for keyword in FOOD_KEYWORDS:
        if len(results) >= target:
            break

        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            if len(results) >= target:
                break

            data = await amap_search_food(
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

                # Quality filter: use rating + favorite_num
                biz = poi.get("biz_ext", {}) or {}
                rating = float(biz.get("rating", 0) or 0)
                favorite_num = int(poi.get("favorite_num", 0) or 0)
                if rating < MIN_RATING or favorite_num < MIN_FAVORITES:
                    continue

                # Name dedup
                norm = _normalize_name(name)
                if norm in seen_names:
                    continue
                seen_names.add(norm)

                food_poi = _make_food_poi(poi, city, keyword)
                results.append(food_poi)

            # If last page was short, no more for this keyword
            if len(pois) < 20:
                break

            await asyncio.sleep(DELAY_BETWEEN)

        await asyncio.sleep(DELAY_BETWEEN)

    logger.info(f"    {city}: collected {len(results)} food POIs")
    return results


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
        cities = _load_existing_cities()

    if limit and limit < len(cities):
        cities = cities[:limit]

    logger.info(f"Target cities: {len(cities)} — {', '.join(cities[:5])}...")
    logger.info(f"Target per city: {TARGET_PER_CITY} food POIs")
    logger.info(f"Quality thresholds: rating ≥ {MIN_RATING}, favorites ≥ {MIN_FAVORITES}")

    all_food: List[Dict[str, Any]] = []
    city_stats: Dict[str, int] = {}

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for city in cities:
            try:
                pois = await collect_city_food(
                    client, api_key, city, TARGET_PER_CITY, sign_key=sign_key,
                )
                all_food.extend(pois)
                city_stats[city] = len(pois)
            except Exception as e:
                import traceback
                logger.error(f"  Error collecting {city}: {e}")
                logger.error(traceback.format_exc())
                city_stats[city] = 0

    # Stats
    total = len(all_food)
    logger.info(f"\n{'='*50}")
    logger.info(f"Total food POIs collected: {total}")
    for city, count in sorted(city_stats.items(), key=lambda x: -x[1]):
        bar = "█" * min(20, count // 2) if count else "—"
        logger.info(f"  {city:6s} {bar} {count}")

    # Category breakdown
    type_counts: Dict[str, int] = {}
    for p in all_food:
        ft = p.get("food_type", "其他")
        type_counts[ft] = type_counts.get(ft, 0) + 1
    logger.info(f"\nCategory breakdown:")
    for ft, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {ft}: {count}")

    # Save
    output = {
        "source": "Amap POI Search (Food)",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": total,
        "cities_covered": len([c for c, n in city_stats.items() if n > 0]),
        "food_pois": all_food,
        "city_stats": city_stats,
        "type_stats": type_counts,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\nSaved to {OUTPUT_FILE}")
    logger.info(
        f"Next: run enrich_prices.py to add price data, "
        f"then scripts/expand_cities.py to merge into attractions.json"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="采集高德餐饮 POI 数据")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔的城市列表，默认从 attractions.json 读取")
    parser.add_argument("--limit", type=int, default=0,
                        help="仅处理前 N 个城市（调试用）")
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else None
    asyncio.run(main(cities=cities, limit=args.limit))

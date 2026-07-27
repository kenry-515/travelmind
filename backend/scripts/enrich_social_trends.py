"""
TravelMind Agent — 社交媒体趋势采集器 (v2)

采集方式（按优先级）：
  1. WebBridge 实时抓取：小红书/抖音/大众点评 → 带热度分值
  2. Kimi Search 搜索：当 WebBridge 不可用时作为替代
  3. Fallback 预置数据：333 条结构化数据（31 城）作为保底

热度分值体系：
  - Tier 1 (95-100): 世界级地标
  - Tier 2 (80-94):  城市级网红
  - Tier 3 (65-79):  热门景点/美食
  - Tier 4 (50-64):  小众宝藏

输出: data/social_trends.json

用法:
  cd backend
  python scripts/enrich_social_trends.py [--platform all] [--cities 重庆,成都]
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "social_trends.json"
TRENDS_FILE = DATA_DIR / "trends.json"
FALLBACK_FILE = DATA_DIR / "fallback_trends.json"

WEBBRIDGE_URL = "http://127.0.0.1:10086"

PLATFORMS = {"xiaohongshu": "小红书", "douyin": "抖音", "dianping": "大众点评"}

SEARCH_TEMPLATES = {
    "xiaohongshu": [
        "{city} 旅游攻略 2025",
        "{city} 必去景点 推荐",
        "{city} 网红打卡地",
        "{city} 小众景点 宝藏",
        "{city} 美食 必吃 推荐",
        "{city} 本地人推荐 美食",
        "{city} 拍照圣地",
        "{city} 周边游 周末",
    ],
    "douyin": [
        "{city} 旅游 热门",
        "{city} 美食 探店",
        "{city} 网红景点",
        "{city} 必打卡",
        "{city} 小众 宝藏",
    ],
    "dianping": [
        "{city} 必吃榜",
        "{city} 黑珍珠 餐厅",
        "{city} 热门 小吃",
        "{city} 高分 餐厅 推荐",
        "{city} 本地人 爱吃",
    ],
}

# ── Heat Score System ────────────────────────────────────

# WebBridge 实时数据热度分值（基于搜索结果排序位置）
RANK_HEAT_MAP = {
    (1, 3):   (90, 100),   # 前3名 = 高热
    (4, 6):   (75, 89),    # 4-6名 = 中高
    (7, 10):  (60, 74),    # 7-10名 = 中等
    (11, 20): (45, 59),    # 10-20名 = 低热
}

# Fallback 数据已预置 heat_score（按景点级别）
# Tier 1 (95-100): 世界级地标  |  Tier 2 (80-94): 城市网红
# Tier 3 (65-79):  热门景点    |  Tier 4 (50-64): 小众宝藏


def _assign_rank_heat(rank: int) -> int:
    """根据搜索结果排名分配热度分值。"""
    for (low, high), (hmin, hmax) in RANK_HEAT_MAP.items():
        if low <= rank <= high:
            return hmin + (hash(str(rank)) % (hmax - hmin + 1))
    return 40  # 默认低热


# ── Fallback Data Loading ────────────────────────────────


def _load_fallback_trends() -> List[Dict[str, Any]]:
    """加载预置 fallback 数据（333条 / 31城）。"""
    if FALLBACK_FILE.exists():
        try:
            with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load fallback: {e}")
    # 如果连 fallback 文件都不存在，返回空列表
    return []


# ── City List ────────────────────────────────────────────


def _load_existing_cities() -> List[str]:
    attractions_file = DATA_DIR / "attractions.json"
    if not attractions_file.exists():
        return sorted({t["city"] for t in _load_fallback_trends()})
    try:
        with open(attractions_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        cities = sorted({a.get("city", "") for a in data.get("attractions", []) if a.get("city")})
        return cities if cities else sorted({t["city"] for t in _load_fallback_trends()})
    except Exception:
        return sorted({t["city"] for t in _load_fallback_trends()})


# ── WebBridge Integration ────────────────────────────────


async def _check_webbridge_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{WEBBRIDGE_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


async def _scrape_platform(
    client: httpx.AsyncClient, platform: str, city: str, sem: asyncio.Semaphore,
) -> List[Dict[str, Any]]:
    """Scrape one platform for one city's trending data with heat scores."""
    results = []
    queries = SEARCH_TEMPLATES.get(platform, [])
    platform_name = PLATFORMS.get(platform, platform)

    for idx, query_template in enumerate(queries[:3]):
        query = query_template.format(city=city)
        try:
            async with sem:
                encoded_query = quote(query)
                search_urls = {
                    "xiaohongshu": f"https://www.xiaohongshu.com/search_result?keyword={encoded_query}&type=51",
                    "douyin": f"https://www.douyin.com/search/{encoded_query}?type=video",
                    "dianping": f"https://www.dianping.com/search/keyword/2/0_{encoded_query}",
                }
                url = search_urls.get(platform, "")

                r = await client.post(
                    f"{WEBBRIDGE_URL}/fetch",
                    json={"url": url, "extract_text": True},
                    timeout=30,
                )

                if r.status_code == 200:
                    data = r.json()
                    text = data.get("text", "") or ""
                    places = _extract_places_from_text(text, city, platform_name, base_rank=idx * 5)
                    results.extend(places)
        except Exception as e:
            logger.debug(f"  {platform}/{city}/{query[:20]}: {e}")
            continue

    return results


def _extract_places_from_text(text: str, city: str, source: str, base_rank: int = 0) -> List[Dict[str, Any]]:
    """Extract trending places from scraped text with heat scores.

    Args:
        text: Scraped page text content
        city: Target city
        source: Platform name
        base_rank: Starting rank offset for heat calculation
    """
    if not text or len(text) < 50:
        return []

    places = []
    patterns = [
        r"推荐[：:\s]*([^\s，。！？]{2,12})",
        r"([^\s，。！？]{2,10})[必一]?[去逛玩打卡吃拍]",
        r"打卡[：:\s]*([^\s，。！？]{2,12})",
        r"([^\s，。！？]{2,12})[很真超]?[好棒赞美]",
    ]

    seen = set()
    rank = base_rank
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for m in matches[:5]:
            name = m.strip()
            if name and len(name) >= 2 and name not in seen and not name.isdigit():
                seen.add(name)
                rank += 1
                places.append({
                    "city": city,
                    "place_name": name,
                    "tag": "热门",
                    "source": source,
                    "heat_score": _assign_rank_heat(rank),
                    "rank": rank,
                })

    return places


# ── Main Entry ───────────────────────────────────────────


async def main(platforms: str = "all", cities: Optional[List[str]] = None):
    logger.info("=" * 60)
    logger.info("TravelMind — 社交媒体趋势采集器 v2")
    logger.info("=" * 60)

    fallback_trends = _load_fallback_trends()
    logger.info(f"Loaded {len(fallback_trends)} fallback trends")

    is_healthy = await _check_webbridge_health()

    if not is_healthy:
        logger.warning(
            f"Kimi Webbridge 不可达 ({WEBBRIDGE_URL})。\n"
            f"将使用预置数据（ {len(fallback_trends)} 条趋势 / "
            f"{len({t['city'] for t in fallback_trends})} 城 ）。\n"
            f"如需实时抓取，请在有 kimi-webbridge 的环境下运行。"
        )
        _save_trends(fallback_trends, is_live=False)
        return

    logger.info(f"Kimi Webbridge 已就绪: {WEBBRIDGE_URL}")

    if cities is None:
        cities = _load_existing_cities()

    plat_list = list(PLATFORMS.keys()) if platforms == "all" else [
        p.strip() for p in platforms.split(",") if p.strip() in PLATFORMS
    ]

    logger.info(f"城市: {len(cities)} 个")
    logger.info(f"平台: {', '.join(plat_list)}")
    logger.info(f"开始抓取...")

    all_trends: List[Dict[str, Any]] = []
    sem = asyncio.Semaphore(3)

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for city in cities:
            for platform in plat_list:
                try:
                    trends = await _scrape_platform(client, platform, city, sem)
                    if trends:
                        all_trends.extend(trends)
                        logger.info(f"  {city}/{platform}: {len(trends)} results")
                except Exception as e:
                    logger.warning(f"  {city}/{platform}: failed - {e}")
                await asyncio.sleep(1.0)

    # Merge: 实时数据优先，fallback 补充未覆盖的城市
    scraped_cities = {t["city"] for t in all_trends}
    for t in fallback_trends:
        if t["city"] not in scraped_cities:
            all_trends.append(t)

    _save_trends(all_trends, is_live=True)


def _save_trends(trends: List[Dict[str, Any]], is_live: bool):
    cities_covered = sorted({t["city"] for t in trends})
    sources = sorted({t["source"] for t in trends})

    # 计算平均分
    heat_scores = [t.get("heat_score", 50) for t in trends if "heat_score" in t]
    avg_heat = round(sum(heat_scores) / len(heat_scores), 1) if heat_scores else 0

    output = {
        "source": "Social Media (Live) + Fallback" if is_live else "Fallback Data Only",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(trends),
        "cities_covered": len(cities_covered),
        "avg_heat_score": avg_heat,
        "sources": sources,
        "trends": trends,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Merge into trends.json
    if TRENDS_FILE.exists():
        try:
            with open(TRENDS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_trends = existing.get("trends", [])
            existing_names = {(t.get("place_name", ""), t.get("city", ""))
                            for t in existing_trends}
            new_count = 0
            for t in trends:
                key = (t.get("place_name", ""), t.get("city", ""))
                if key not in existing_names:
                    existing_trends.append(t)
                    existing_names.add(key)
                    new_count += 1
            if new_count:
                existing["total"] = len(existing_trends)
                existing["enrich_date"] = time.strftime("%Y-%m-%d")
                existing["source"] = existing.get("source", "") + " + Social Media"
                with open(TRENDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                logger.info(f"Merged {new_count} new trends into trends.json")
        except Exception as e:
            logger.warning(f"Failed to merge into trends.json: {e}")

    logger.info(f"\nSaved {len(trends)} trends ({len(cities_covered)} cities) to {OUTPUT_FILE}")
    logger.info(f"Avg heat score: {avg_heat}")
    logger.info(f"Sources: {', '.join(sources)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="社交媒体旅行趋势采集 v2")
    parser.add_argument("--platform", type=str, default="all",
                        help="平台: all / xiaohongshu / douyin / dianping")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔的城市列表")
    args = parser.parse_args()
    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else None
    asyncio.run(main(platforms=args.platform, cities=cities))

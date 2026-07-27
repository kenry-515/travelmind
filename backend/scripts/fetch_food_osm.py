"""
TravelMind Agent — OSM Food POI Fetcher（细分美食品类采集）

用 OpenStreetMap Overpass API（ODbL，无需 Key）采集细分美食品类 POI：
小吃/面馆/早点/烧烤/火锅/海鲜/饮品甜点/国际美食。

背景（f08 根因）：高德采集把菜系信息压平成「中餐」（上海 29/30），
知识库在评测词表下的美食多样性上限只有 3 类。OSM 的名称/菜系标签
保留了细分信息，可补小吃/生煎/面馆等品类。

数据全部来自 OSM 真实节点（带 osm_id 可追溯），严禁任何合成字段：
OSM 没有评分数据，rating 一律为 null，popularity_score 统一给中性值 4。

输出契约与 merge_indoor_pois.py 兼容（顶层 indoor_pois 键）。

用法：
  cd backend
  python scripts/fetch_food_osm.py                  # 默认上海
  python scripts/fetch_food_osm.py --cities 上海,广州
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.services.name_normalizer import normalize_poi_name
from fetch_indoor_osm import (  # noqa: E402  复用同目录采集脚本的工具函数
    OVERPASS_URL,
    USER_AGENT,
    _city_bbox,
    _get_name,
    _load_kb,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "food_osm.json"

# 公共实例对大 bbox 正则查询容易 504，准备镜像端点轮换
OVERPASS_URLS = [
    OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
]

TARGET_PER_CITY = 40
BBOX_HALF = 0.25  # ≈27km 半径：覆盖主城区，避免上海全域正则扫描超时
DELAY_BETWEEN = 1.0
MAX_RETRIES = 2

# 细分品类规则：(类型, 名称关键词, OSM cuisine 值)
# 类型词表与评测 food_tags 对齐
FOOD_TYPE_RULES = [
    ("早点", ("早点", "早餐", "豆浆", "油条"), ("breakfast",)),
    ("小吃", ("生煎", "小笼", "汤包", "锅贴", "馄饨", "包子", "点心",
              "糕团", "年糕", "煎饼", "小吃", "粥"),
     ("dumpling", "snack", "snack_bar")),
    ("面馆", ("面馆", "拉面", "拌面", "烩面", "刀削面", "米粉", "米线", "面庄"),
     ("noodle", "noodles", "ramen")),
    ("烧烤", ("烧烤", "烤串", "烤肉"), ("bbq", "barbecue")),
    ("火锅", ("火锅", "串串", "麻辣烫"), ("hotpot",)),
    ("海鲜", ("海鲜", "龙虾", "水产", "生蚝"),
     ("seafood",)),
    ("饮品甜点", ("咖啡", "奶茶", "甜品", "糖水", "冰室", "烘焙", "蛋糕", "茶饮"),
     ("coffee", "coffee_shop", "dessert", "cake", "ice_cream", "tea")),
    ("国际美食", ("西餐", "日料", "寿司", "韩国", "泰国", "越南",
                  "意大利", "牛排", "披萨", "汉堡"),
     ("japanese", "sushi", "korean", "thai", "vietnamese",
      "italian", "pizza", "burger", "western")),
]

# 连锁品牌（food_local_ratio 扣分项）与无旅行价值的节点，直接跳过
CHAIN_KEYWORDS = (
    "肯德基", "麦当劳", "星巴克", "汉堡王", "必胜客", "瑞幸", "库迪",
    "全家", "罗森", "711", "7-Eleven", "蜜雪冰城", "KFC", "McDonald",
    "沙县小吃", "兰州拉面", "兰州牛肉", "黄焖鸡",
    "味千", "康师傅", "永和豆浆", "吉祥馄饨", "海底捞", "Costa",
    "达美乐", "85度C", "Lavazza", "Gloria Jean", "Hooters",
    "沃歌斯", "Wagas", "赛百味", "德克士",
    "萨莉亚", "CoCo壹番屋", "上岛咖啡", "太平洋咖啡",
)
GENERIC_NAMES = {"餐厅", "饭店", "小吃", "面馆", "美食", "食堂", "快餐店"}
# 规范化（去空白/小写）后的纯泛称，无辨识度
GENERIC_CANON = {
    "火锅餐厅", "hotpot火锅", "hotpot", "包子店", "美食小吃", "小吃店",
    "海鲜餐厅", "烧烤店", "咖啡店",
}
# 名称里的 Unicode 格式控制符（OSM 数据偶发 LRM/RLM 等不可见字符）
_FORMAT_CHARS_RE = re.compile(r"[‎‏‪-‮﻿]")


def _clean_name(name: str) -> str:
    return _FORMAT_CHARS_RE.sub("", name).strip()


_NAME_RE = "|".join(kw for _t, kws, _c in FOOD_TYPE_RULES for kw in kws)
_CUISINE_RE = "|".join(v for _t, _k, vals in FOOD_TYPE_RULES for v in vals)


def _city_bbox_tight(attractions: List[Dict[str, Any]], city: str) -> Optional[str]:
    """比室内采集更紧的 bbox（±0.25°），餐饮正则查询才不会打满 Overpass。"""
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
    s, n = mid_lat - BBOX_HALF, mid_lat + BBOX_HALF
    w, e = mid_lon - BBOX_HALF, mid_lon + BBOX_HALF
    return f"{s:.4f},{w:.4f},{n:.4f},{e:.4f}"


def _build_query(bbox: str) -> str:
    amenity = "^(restaurant|fast_food|cafe|food_court)$"
    return (
        "[out:json][timeout:50];\n"
        "(\n"
        f'  node["amenity"~"{amenity}"]["name"~"{_NAME_RE}"]({bbox});\n'
        f'  way["amenity"~"{amenity}"]["name"~"{_NAME_RE}"]({bbox});\n'
        f'  node["amenity"~"{amenity}"]["cuisine"~"{_CUISINE_RE}",i]({bbox});\n'
        f'  way["amenity"~"{amenity}"]["cuisine"~"{_CUISINE_RE}",i]({bbox});\n'
        ");\n"
        "out center tags 300;"
    )


def _classify_food(name: str, cuisine: str) -> Optional[str]:
    """按名称 + OSM cuisine 标签推导细分品类；无细分信息返回 None。"""
    cuisine_set = {c.strip().lower() for c in re.split(r"[;,]", cuisine or "") if c.strip()}
    for type_tag, name_kws, cuisine_vals in FOOD_TYPE_RULES:
        if any(kw in name for kw in name_kws):
            return type_tag
        if cuisine_set & set(cuisine_vals):
            return type_tag
    return None


def _price_level(type_tag: str) -> str:
    """诚实的价格档启发式：小吃/早点/面馆按经济档，其余适中。"""
    return "经济" if type_tag in ("小吃", "早点", "面馆") else "适中"


async def fetch_city(
    client: httpx.AsyncClient, city: str, bbox: str
) -> List[Dict[str, Any]]:
    query = _build_query(bbox)
    data: Optional[Dict[str, Any]] = None
    for attempt in range(MAX_RETRIES + 1):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]  # 504/429 轮换镜像
        try:
            r = await client.post(
                url,
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
        name = _clean_name(_get_name(tags))
        if not name or len(name) < 2:
            continue
        if any(kw in name for kw in CHAIN_KEYWORDS):
            continue
        if name in GENERIC_NAMES:
            continue
        canon = re.sub(r"\s+", "", name).lower()
        if canon in GENERIC_CANON:
            continue
        type_tag = _classify_food(name, tags.get("cuisine", ""))
        if not type_tag:
            continue

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
            "tags": ["美食", type_tag],
            "suitable_for": "美食探索、本地味道",
            "best_time": "全年",
            "price_level": _price_level(type_tag),
            # OSM 无评分数据——诚实留空；popularity 给中性值避免挤压头部
            "popularity_score": 4,
            "rating": None,
            "comment_count": 0,
            "ai_enriched": False,
            "food_type": type_tag,
        })
        if len(results) >= TARGET_PER_CITY:
            break

    logger.info(f"  {city}: {len(results)} 条细分美食 POI")
    return results


async def main(cities: Optional[List[str]] = None) -> None:
    if cities is None:
        cities = ["上海"]

    attractions = _load_kb()
    kb_names: Dict[str, Set[str]] = {}
    for a in attractions:
        c = a.get("city", "")
        n = normalize_poi_name(a.get("name", ""))
        if c and n:
            kb_names.setdefault(c, set()).add(n)

    all_pois: List[Dict[str, Any]] = []
    city_stats: Dict[str, int] = {}
    type_stats: Dict[str, int] = {}

    async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
        for city in cities:
            bbox = _city_bbox_tight(attractions, city)
            if not bbox:
                logger.warning(f"  {city}: KB 无坐标，无法推导 bbox，跳过")
                city_stats[city] = 0
                continue
            pois = await fetch_city(client, city, bbox)
            existing = kb_names.get(city, set())
            deduped = [p for p in pois
                       if normalize_poi_name(p["name"]) not in existing]
            skipped = len(pois) - len(deduped)
            if skipped:
                logger.info(f"  {city}: 跳过 {skipped} 条 KB 已存在")
            all_pois.extend(deduped)
            city_stats[city] = len(deduped)
            for p in deduped:
                type_stats[p["food_type"]] = type_stats.get(p["food_type"], 0) + 1
            await asyncio.sleep(DELAY_BETWEEN)

    output = {
        "source": "OpenStreetMap Overpass API (ODbL)",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(all_pois),
        "cities_covered": len([c for c, n in city_stats.items() if n > 0]),
        "indoor_pois": all_pois,  # 与 merge_indoor_pois.py 输入契约兼容
        "city_stats": city_stats,
        "type_stats": type_stats,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"\n共 {len(all_pois)} 条，已保存 {OUTPUT_FILE}")
    for city, n in sorted(city_stats.items(), key=lambda x: -x[1]):
        logger.info(f"  {city}: {n}")
    logger.info(f"  品类分布: {type_stats}")
    logger.info("Next: python scripts/merge_indoor_pois.py --input data/food_osm.json")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="从 OSM Overpass 采集细分美食 POI")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔城市列表，默认上海")
    args = parser.parse_args()
    city_list = [c.strip() for c in args.cities.split(",") if c.strip()] or None
    asyncio.run(main(cities=city_list))

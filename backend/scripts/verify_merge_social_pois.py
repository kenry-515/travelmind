"""
TravelMind Agent — Social POI Verifier & Merger

把 data/social_poi_candidates.json（WebSearch 社交热议候选）逐条用
OSM Overpass 验证：只有在该城市 bbox 内找到同名真实地物的候选才合并进
attractions.json（带 osm_id 可追溯）；找不到的一律不合并并输出报告。

🔴 数据完整性：社交来源只提供"名字 + 热度信号"，坐标/存在性以 OSM 为准。

用法：
  cd backend
  python scripts/verify_merge_social_pois.py [--dry-run]
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.name_normalizer import normalize_poi_name
from fetch_indoor_osm import _city_bbox, _classify, _get_name

# 纯类目泛称——永远不作为有效 POI 候选（2026-07-25 二度污染复盘：
# OSM way/98842742 的名字就叫"博物馆"，等值匹配也会放行）
_GENERIC_REJECT = {"博物馆", "美术馆", "图书馆", "剧院", "购物中心", "商场", "海洋馆", "科技馆"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
CANDIDATES_FILE = DATA_DIR / "social_poi_candidates.json"
REPORT_FILE = DATA_DIR / "social_poi_verify_report.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# 公共实例 504 高发，镜像轮换（2026-07-26：主实例连续 504 曾导致全城静默全拒）
OVERPASS_URLS = [
    OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
USER_AGENT = "TravelMindAgent/0.2 (travel planning research)"
DELAY_BETWEEN = 2.0  # Overpass 公共实例限速（串行城市）
MAX_RETRIES = 4


class OverpassUnavailable(RuntimeError):
    """Overpass 连续重试后仍不可用——必须中止运行，不得当作'未找到'。"""

_CATEGORY_TAGS: Dict[str, List[str]] = {
    "博物馆": ["博物馆", "文化", "室内"],
    "美术馆": ["美术馆", "艺术", "室内"],
    "科技馆": ["科技馆", "展览", "室内"],
    "购物中心": ["购物", "商场", "室内"],
    "剧院": ["剧院", "演出", "室内"],
    "图书馆": ["图书馆", "文化", "室内"],
    "海洋馆": ["海洋馆", "亲子", "室内"],
    "室内其他": ["室内"],
}


async def _verify_city(
    client: httpx.AsyncClient,
    city: str,
    names: List[str],
    bbox: str,
) -> Dict[str, Dict[str, Any]]:
    """Query Overpass for candidate names within the city bbox.

    Returns {matched_name: {lat, lon, osm_id, osm_name, category}}.
    """
    clauses = "\n".join(f'  nwr["name"~"{n}"]({bbox});' for n in names)
    query = f"[out:json][timeout:60];\n(\n{clauses}\n);\nout center tags 100;"
    data: Optional[Dict[str, Any]] = None
    for attempt in range(MAX_RETRIES):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]  # 504/429 轮换镜像
        try:
            r = await client.post(
                url,
                content="data=" + httpx.QueryParams({"data": query})["data"],
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": USER_AGENT,
                },
            )
            if r.status_code != 200:
                logger.warning(f"  {city}: HTTP {r.status_code}，重试 {attempt + 1}")
                await asyncio.sleep(15 * (attempt + 1))
                continue
            data = r.json()
            break
        except Exception as e:
            logger.warning(f"  {city}: 请求异常 {e}，重试 {attempt + 1}")
            await asyncio.sleep(15 * (attempt + 1))
    if not data:
        # 🔴 数据完整性：查询失败 ≠ 未找到。把外部服务故障落成"全城拒绝"
        # 会写出灾难性假阴性报告（2026-07-26 实测：主实例 504 期间 143 条全拒）。
        raise OverpassUnavailable(f"{city}: Overpass {MAX_RETRIES} 次重试均失败")

    matched: Dict[str, Dict[str, Any]] = {}
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        osm_name = _get_name(tags)
        if not osm_name:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        # 与候选名匹配：标准化后相等，或候选名（≥4 字符）⊆ OSM 名。
        # 反向（OSM 名 ⊆ 候选名）会把标题片段误判通过——
        # 如"武汉博物馆" ⊂ "不妨去武汉博物馆"；短泛称（如"博物馆"）
        # 禁止子串匹配（2026-07-25 数据污染事件复盘）。
        for cand in names:
            if cand in matched:
                continue
            norm_c = normalize_poi_name(cand)
            norm_o = normalize_poi_name(osm_name)
            if norm_c and (norm_c == norm_o or (len(norm_c) >= 4 and norm_c in norm_o)):
                matched[cand] = {
                    "lat": lat,
                    "lon": lon,
                    "osm_id": f"{el.get('type')}/{el.get('id')}",
                    "osm_name": osm_name,
                    "osm_category": _classify(tags),
                }
    return matched


def _city_bbox_wide(attractions: List[Dict[str, Any]], city: str, half: float = 0.8) -> Optional[str]:
    """二轮宽 bbox（±0.8° ≈ 88km）：覆盖远郊地物
    （如国家海洋博物馆距天津市区约 40km，首轮 ±0.4° 盖不到）。"""
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
    mid_lat, mid_lon = lats[len(lats) // 2], lons[len(lons) // 2]
    return (
        f"{mid_lat - half:.4f},{mid_lon - half:.4f},"
        f"{mid_lat + half:.4f},{mid_lon + half:.4f}"
    )


async def main(dry_run: bool = False, only_cities: Optional[List[str]] = None) -> None:
    with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
        candidates = json.load(f)["candidates"]
    with open(ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
        kb = json.load(f)
    attractions = kb["attractions"]

    existing = {
        (normalize_poi_name(a.get("name", "")), a.get("city", ""))
        for a in attractions
    }

    # 按城市分组
    by_city: Dict[str, List[Dict[str, Any]]] = {}
    for c in candidates:
        by_city.setdefault(c["city"], []).append(c)
    if only_cities:
        by_city = {c: items for c, items in by_city.items() if c in set(only_cities)}

    merged: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    query_failed: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
        for city, items in by_city.items():
            bbox = _city_bbox(attractions, city)
            if not bbox:
                logger.warning(f"{city}: 无 bbox，全部跳过")
                rejected.extend({**c, "reason": "no bbox"} for c in items)
                continue
            names = [
                c["name"] for c in items
                if normalize_poi_name(c["name"]) not in _GENERIC_REJECT
            ]
            if not names:
                continue
            try:
                matched = await _verify_city(client, city, names, bbox)
                # 二轮：未命中者用宽 bbox 再试（远郊地物，首轮 ±0.4° 盖不到）
                remaining = [n for n in names if n not in matched]
                if remaining:
                    wide = _city_bbox_wide(attractions, city)
                    if wide and wide != bbox:
                        await asyncio.sleep(DELAY_BETWEEN)
                        matched.update(await _verify_city(client, city, remaining, wide))
            except OverpassUnavailable as e:
                # 单城查询失败：跳过该城、继续其他城市，报告标 query_failed
                # （脚本幂等，已合并的下一轮会判 "KB 已存在"，直接重跑即可补齐）
                logger.error(f"{city}: {e}，本城跳过（重跑可补齐）")
                query_failed.extend({**c, "reason": "OSM 查询失败（需重跑）"} for c in items)
                continue
            logger.info(f"{city}: {len(matched)}/{len(names)} 条通过 OSM 验证")

            for c in items:
                if normalize_poi_name(c["name"]) in _GENERIC_REJECT:
                    rejected.append({**c, "reason": "纯类目泛称拒收"})
                    continue
                m = matched.get(c["name"])
                if not m:
                    rejected.append({**c, "reason": "OSM 未找到同名地物"})
                    continue
                key = (normalize_poi_name(c["name"]), city)
                if key in existing:
                    rejected.append({**c, "reason": "KB 已存在"})
                    continue
                category = c.get("category") or m.get("osm_category") or "室内其他"
                entry = {
                    "name": c["name"],
                    "city": city,
                    "lat": m["lat"],
                    "lon": m["lon"],
                    "address": "",
                    "osm_id": m["osm_id"],
                    "osm_verified": True,
                    "source": "web-social+osm-overpass",
                    "source_url": c.get("source_url", ""),
                    "tags": list(_CATEGORY_TAGS.get(category, ["室内"])),
                    "suitable_for": "雨天备选、室内休闲",
                    "best_time": "全年",
                    "price_level": "适中",
                    "popularity_score": 6,
                    "rating": None,
                    "comment_count": 0,
                    "ai_enriched": False,
                    "indoor_type": category,
                }
                attractions.append(entry)
                existing.add(key)
                merged.append(entry)
            await asyncio.sleep(DELAY_BETWEEN)

    logger.info(f"\n合并 {len(merged)} 条，拒绝 {len(rejected)} 条，查询失败 {len(query_failed)} 条")
    for r in rejected:
        logger.info(f"  ✗ {r['city']} {r['name']} — {r['reason']}")

    # 报告按城市增量更新（分块重跑时保留历史城市的去向记录）
    old: Dict[str, Any] = {}
    if REPORT_FILE.exists():
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
    processed = set(by_city.keys())
    merged_items = [m for m in old.get("merged", []) if m.get("city") not in processed]
    merged_items += [{"city": m["city"], "name": m["name"], "osm_id": m["osm_id"]} for m in merged]
    rejected_items = [r for r in old.get("rejected", []) if r.get("city") not in processed]
    rejected_items += rejected
    failed_items = [r for r in old.get("query_failed", []) if r.get("city") not in processed]
    failed_items += query_failed

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "date": time.strftime("%Y-%m-%d"),
            "merged": merged_items,
            "rejected": rejected_items,
            "query_failed": failed_items,
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"验证报告: {REPORT_FILE}")

    if dry_run:
        logger.info("dry-run，不写 attractions.json")
        return

    kb["total"] = len(attractions)
    with open(ATTRACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    logger.info(f"已写回 {ATTRACTIONS_FILE}，总数 {len(attractions)}")
    logger.info("Next: python scripts/build_knowledge_base.py 重建 Chroma")
    if query_failed:
        logger.warning(f"{len(query_failed)} 条候选因 Overpass 故障未验证——脚本幂等，直接重跑即可补齐")
        sys.exit(2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OSM 验证并合并社交 POI 候选")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cities", type=str, default="",
                        help="只处理这些城市（逗号分隔），默认全部——分块补跑用")
    args = parser.parse_args()
    city_list = [c.strip() for c in args.cities.split(",") if c.strip()] or None
    try:
        asyncio.run(main(dry_run=args.dry_run, only_cities=city_list))
    except OverpassUnavailable as e:
        logger.error(f"验证中止（未写入任何文件，稍后重跑）: {e}")
        sys.exit(1)

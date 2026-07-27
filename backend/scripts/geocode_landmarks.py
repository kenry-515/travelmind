"""
TravelMind Agent — Landmark Geocoding Script (Phase 12.12)

Uses OpenStreetMap Nominatim (free, no API key) to geocode famous Chinese
landmarks that are missing from the KB.

Usage:
    cd backend
    python -X utf8 scripts/geocode_landmarks.py --output data/landmarks_supplement.json

Rate limit: Nominatim allows ~1 req/sec for bulk use. This script includes
a 1.2s delay between requests to be respectful.
"""

import argparse
import json
import logging
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Famous Chinese Landmarks missing from KB ────────────────────
# Each entry: (common_name, city, hint for search)
MISSING_LANDMARKS: List[Tuple[str, str, str]] = [
    # === 重庆 ===
    ("洪崖洞", "重庆", "洪崖洞民俗风貌区"),
    ("磁器口古镇", "重庆", "磁器口"),
    ("长江索道", "重庆", "重庆长江索道"),
    ("南山一棵树观景台", "重庆", "南山一棵树"),
    ("朝天门广场", "重庆", "重庆朝天门"),
    ("鹅岭公园", "重庆", "重庆鹅岭公园"),
    ("李子坝轻轨站", "重庆", "李子坝"),
    ("大足石刻", "重庆", "大足石刻"),
    ("武隆天生三桥", "重庆", "武隆天生三桥"),
    ("山城步道", "重庆", "重庆山城步道"),
    ("观音桥步行街", "重庆", "重庆观音桥"),
    # === 成都 ===
    ("宽窄巷子", "成都", "成都宽窄巷子"),
    ("锦里古街", "成都", "成都锦里"),
    ("武侯祠博物馆", "成都", "成都武侯祠"),
    ("大熊猫繁育研究基地", "成都", "成都大熊猫基地"),
    ("都江堰景区", "成都", "都江堰"),
    ("太古里", "成都", "成都太古里"),
    ("九眼桥", "成都", "成都九眼桥"),
    ("文殊院", "成都", "成都文殊院"),
    ("青羊宫", "成都", "成都青羊宫"),
    # === 北京 ===
    ("天安门广场", "北京", "天安门"),
    ("颐和园", "北京", "北京颐和园"),
    ("南锣鼓巷", "北京", "南锣鼓巷"),
    ("798艺术区", "北京", "798艺术区"),
    ("水立方", "北京", "水立方"),
    ("什刹海", "北京", "什刹海"),
    ("雍和宫", "北京", "雍和宫"),
    ("圆明园", "北京", "北京圆明园"),
    ("北海公园", "北京", "北海公园"),
    ("恭王府", "北京", "恭王府"),
    # === 西安 ===
    ("秦始皇兵马俑博物馆", "西安", "兵马俑"),
    ("西安城墙", "西安", "西安城墙"),
    ("小雁塔", "西安", "小雁塔"),
    ("陕西历史博物馆", "西安", "陕西历史博物馆"),
    ("回民街", "西安", "回民街"),
    ("大唐不夜城", "西安", "大唐不夜城"),
    ("西安碑林", "西安", "碑林博物馆"),
    # === 上海 ===
    ("东方明珠广播电视塔", "上海", "东方明珠"),
    ("南京路步行街", "上海", "南京路"),
    ("田子坊", "上海", "田子坊"),
    ("新天地", "上海", "新天地"),
    ("陆家嘴", "上海", "陆家嘴"),
    ("城隍庙", "上海", "上海城隍庙"),
    ("静安寺", "上海", "静安寺"),
    # === 杭州 ===
    ("灵隐寺", "杭州", "杭州灵隐寺"),
    ("雷峰塔", "杭州", "雷峰塔"),
    ("西溪国家湿地公园", "杭州", "西溪湿地"),
    ("宋城", "杭州", "宋城"),
    ("三潭印月", "杭州", "三潭印月"),
    ("九溪烟树", "杭州", "九溪烟树"),
    ("龙井村", "杭州", "龙井村"),
    ("河坊街", "杭州", "河坊街"),
    # === 南京 ===
    ("中山陵", "南京", "南京中山陵"),
    ("夫子庙", "南京", "南京夫子庙"),
    ("南京总统府", "南京", "总统府"),
    ("明孝陵", "南京", "明孝陵"),
    ("秦淮河", "南京", "秦淮河"),
    ("鸡鸣寺", "南京", "鸡鸣寺"),
    ("玄武湖公园", "南京", "玄武湖"),
    ("南京博物院", "南京", "南京博物院"),
    ("老门东", "南京", "老门东"),
    ("美龄宫", "南京", "美龄宫"),
    # === 武汉 ===
    ("黄鹤楼", "武汉", "黄鹤楼"),
    ("户部巷", "武汉", "户部巷"),
    ("武汉长江大桥", "武汉", "长江大桥"),
    ("归元寺", "武汉", "归元寺"),
    ("武汉大学", "武汉", "武汉大学"),
    ("湖北省博物馆", "武汉", "湖北省博物馆"),
    ("楚河汉街", "武汉", "楚河汉街"),
    # === 长沙 ===
    ("橘子洲", "长沙", "橘子洲"),
    ("太平街", "长沙", "太平街"),
    ("湖南省博物馆", "长沙", "湖南省博物馆"),
    ("五一广场", "长沙", "五一广场"),
    ("梅溪湖", "长沙", "梅溪湖"),
    # === 广州 ===
    ("北京路步行街", "广州", "北京路"),
    ("珠江夜游", "广州", "珠江夜游"),
    ("中山纪念堂", "广州", "中山纪念堂"),
    ("越秀公园", "广州", "越秀公园"),
    ("上下九步行街", "广州", "上下九"),
    # === 苏州 ===
    ("虎丘", "苏州", "虎丘"),
    ("狮子林", "苏州", "狮子林"),
    ("留园", "苏州", "留园"),
    ("寒山寺", "苏州", "寒山寺"),
    ("平江路", "苏州", "平江路"),
    ("山塘街", "苏州", "山塘街"),
    ("金鸡湖", "苏州", "金鸡湖"),
    # === 桂林 ===
    ("阳朔西街", "桂林", "阳朔西街"),
    ("两江四湖", "桂林", "两江四湖"),
    ("龙脊梯田", "桂林", "龙脊梯田"),
    ("银子岩", "桂林", "银子岩"),
    ("遇龙河", "桂林", "遇龙河"),
    # === 厦门 ===
    ("南普陀寺", "厦门", "南普陀寺"),
    ("环岛路", "厦门", "环岛路"),
    ("中山路步行街", "厦门", "中山路"),
    ("沙坡尾", "厦门", "沙坡尾"),
    # === 丽江 ===
    ("束河古镇", "丽江", "束河古镇"),
    ("拉市海", "丽江", "拉市海"),
    ("虎跳峡", "丽江", "虎跳峡"),
    ("四方街", "丽江", "四方街"),
    # === 大理 ===
    ("崇圣寺三塔", "大理", "崇圣寺三塔"),
    ("双廊古镇", "大理", "双廊"),
    ("喜洲古镇", "大理", "喜洲"),
    ("蝴蝶泉", "大理", "蝴蝶泉"),
]


def geocode_nominatim(query: str, city: str) -> Optional[Tuple[float, float]]:
    """
    Geocode a POI using OSM Nominatim API.
    Returns (lat, lon) or None if not found.
    """
    # Add city context for better results within China
    full_query = f"{query}, {city}, China"
    params = urllib.parse.urlencode({
        "q": full_query,
        "format": "json",
        "limit": 1,
        "accept-language": "zh",
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "TravelMindAgent/1.0 (KB enrichment; contact@travelmind.ai)"
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode("utf-8"))
            if results:
                r = results[0]
                lat = float(r["lat"])
                lon = float(r["lon"])
                display = r.get("display_name", "")
                logger.info(f"  ✓ {query} → ({lat:.4f}, {lon:.4f}) — {display[:80]}")
                return (lat, lon)
            else:
                logger.warning(f"  ✗ {query} — no results from Nominatim")
                return None
    except Exception as e:
        logger.error(f"  ✗ {query} — {e}")
        return None


def create_poi_entry(
    name: str,
    city: str,
    lat: float,
    lon: float,
    tags_hint: str = "",
) -> Dict[str, Any]:
    """Create a minimal POI entry for the KB supplement."""
    return {
        "name": name,
        "name_en": "",
        "name_normalized": name,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "city": city,
        "wiki_article": "",
        "wikidata_id": "",
        "instance_of": "landmark",
        "description": f"{city}{name} — 知名地标，坐标由 OSM Nominatim 提供。",
        "thumbnail_url": None,
        "full_url": "",
        "description_source": "osm_nominatim",
        "wiki_pageid": "",
        "address": "",
        "amap_id": "",
        "amap_type": "",
        "amap_typecode": "",
        "amap_photo_url": "",
        "amap_verified": False,
        "source": "osm_nominatim",
        "tags": ["地标", "热门"],
        "suitable_for": "游客",
        "best_time": "全年",
        "price_level": "未知",
        "popularity_score": 9,
        "ai_enriched": False,
        "price_range": {"min": 0, "max": 0},
        "price_source": "",
        "price_updated_at": "",
    }


def main():
    parser = argparse.ArgumentParser(description="Geocode missing landmarks via OSM Nominatim")
    parser.add_argument("--output", default="data/landmarks_supplement.json",
                        help="Output JSON file path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making API calls")
    parser.add_argument("--start", type=int, default=0,
                        help="Start from landmark index N")
    args = parser.parse_args()

    landmarks = MISSING_LANDMARKS[args.start:]
    output_path = Path(args.output)

    existing = {}
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            existing = {e["name"]: e for e in existing_data.get("landmarks", [])}

    new_entries = []
    skipped = 0
    total = len(landmarks)

    for i, (name, city, hint) in enumerate(landmarks):
        idx = args.start + i
        logger.info(f"[{idx+1}/{total+args.start}] {city} — {name}")

        if name in existing:
            logger.info(f"  → already in supplement, skipping")
            skipped += 1
            new_entries.append(existing[name])
            continue

        if args.dry_run:
            new_entries.append(create_poi_entry(name, city, 0.0, 0.0, hint))
            logger.info(f"  → [dry-run] would query: {hint}, {city}, China")
        else:
            coords = geocode_nominatim(hint, city)
            if coords:
                new_entries.append(create_poi_entry(name, city, coords[0], coords[1], hint))
            else:
                # Try alternative query
                time.sleep(1.5)
                logger.info(f"  → retrying with shorter query: {name}")
                coords = geocode_nominatim(name, city)
                if coords:
                    new_entries.append(create_poi_entry(name, city, coords[0], coords[1], hint))
                else:
                    logger.warning(f"  → FAILED: {name} — could not geocode")
                    skipped += 1

            time.sleep(1.2)  # Rate limiting

    # Prepare output
    output = {
        "source": "OpenStreetMap Nominatim (free geocoding)",
        "description": "Famous Chinese landmarks supplement — coordinates from OSM/Nominatim",
        "created_date": time.strftime("%Y-%m-%d"),
        "total": len(new_entries),
        "landmarks": new_entries,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"Done: {len(new_entries)} entries written to {output_path}")
    logger.info(f"Skipped/Failed: {skipped}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()

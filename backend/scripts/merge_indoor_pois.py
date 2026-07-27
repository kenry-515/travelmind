"""
TravelMind Agent — Indoor POI Merger

把 data/indoor_pois.json（enrich_indoor_amap.py 采集的高德室内 POI）
合并进 data/attractions.json，按「标准化名称 + 城市」去重。
纯本地文件操作，无 LLM、无外部 API。

用法：
  cd backend
  python scripts/merge_indoor_pois.py [--dry-run]
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.name_normalizer import normalize_poi_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
INDOOR_FILE = DATA_DIR / "indoor_pois.json"


def main(dry_run: bool = False, input_file: Optional[Path] = None) -> None:
    indoor_file = input_file or INDOOR_FILE
    if not indoor_file.exists():
        logger.error(f"{indoor_file} 不存在，先运行采集脚本")
        return

    with open(ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
        kb = json.load(f)
    attractions = kb["attractions"]

    with open(indoor_file, "r", encoding="utf-8") as f:
        indoor_data = json.load(f)
    indoor_pois = indoor_data.get("indoor_pois", [])
    if not indoor_pois:
        logger.warning(f"{indoor_file} 为空，无需合并")
        return

    existing = {
        (normalize_poi_name(a.get("name", "")), a.get("city", ""))
        for a in attractions
    }
    merged = 0
    for p in indoor_pois:
        key = (normalize_poi_name(p.get("name", "")), p.get("city", ""))
        if key not in existing:
            p["ai_enriched"] = False
            attractions.append(p)
            existing.add(key)
            merged += 1

    logger.info(f"合并 {merged} 条室内 POI（跳过 {len(indoor_pois) - merged} 条重复）")
    logger.info(f"总数: {len(attractions) - merged} → {len(attractions)}")

    if dry_run:
        logger.info("dry-run，不写文件")
        return

    output = {
        "source": kb.get("source", "") + " + Indoor",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(attractions),
        "ai_enriched": sum(1 for a in attractions if a.get("ai_enriched")),
        "attractions": attractions,
    }
    with open(ATTRACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"已写回 {ATTRACTIONS_FILE}")
    logger.info("Next: python scripts/build_knowledge_base.py 重建 Chroma 向量库")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="合并室内 POI 到 attractions.json")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    parser.add_argument("--input", type=str, default="",
                        help="输入文件（默认 data/indoor_pois.json），如 data/indoor_osm.json")
    args = parser.parse_args()
    input_path = Path(args.input) if args.input else None
    if input_path and not input_path.is_absolute():
        input_path = Path(__file__).resolve().parent.parent / args.input
    main(dry_run=args.dry_run, input_file=input_path)

"""
TravelMind Agent — 知识库构建单入口（获取→清洗→验证→入库→运营）

把分散的数据管线脚本编排成一条命令：

  [1] coverage     室内覆盖率统计（indoor_coverage_report.py）
  [2] fetch-osm    OSM 室内 POI 采集（fetch_indoor_osm.py，低覆盖城市）
  [3] merge        合并 OSM 采集结果（merge_indoor_pois.py）
  [4] fetch-food-osm  OSM 细分美食采集（fetch_food_osm.py，Phase 12.22）
  [5] merge-food   合并美食采集结果（merge_indoor_pois.py --input food_osm.json）
  [6] verify-social 社交候选 OSM 验证合并（verify_merge_social_pois.py，
                   需先准备好 data/social_poi_candidates.json）
  [7] normalize    补齐 name_normalized 字段（内联，保证 100% 覆盖）
  [8] rebuild      Chroma 向量库重建（build_knowledge_base.py）
  [9] quality      数据质量报告（data_quality_report.py）

用法：
  cd backend
  python scripts/build_kb.py                      # 全管线
  python scripts/build_kb.py --skip fetch-osm     # 跳过采集（仅合并+重建）
  python scripts/build_kb.py --only normalize,rebuild,quality
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
DATA_DIR = BACKEND_DIR / "data"

# 阶段定义：(名称, 脚本/内联, 前置条件文件, 说明)
STAGES = [
    ("coverage", "indoor_coverage_report.py", None, "室内覆盖率统计"),
    ("fetch-osm", "fetch_indoor_osm.py", None, "OSM 室内 POI 采集（低覆盖城市）"),
    ("merge", "merge_indoor_pois.py --input data/indoor_osm.json",
     DATA_DIR / "indoor_osm.json", "合并 OSM 采集结果"),
    ("fetch-food-osm", "fetch_food_osm.py", None,
     "OSM 细分美食 POI 采集（默认上海，--cities 可扩展）"),
    ("merge-food", "merge_indoor_pois.py --input data/food_osm.json",
     DATA_DIR / "food_osm.json", "合并 OSM 美食采集结果"),
    ("verify-social", "verify_merge_social_pois.py",
     DATA_DIR / "social_poi_candidates.json", "社交候选验证合并"),
    ("normalize", None, None, "补齐 name_normalized（内联）"),
    ("rebuild", "build_knowledge_base.py", None, "Chroma 向量库重建"),
    ("quality", "data_quality_report.py", None, "数据质量报告"),
]


def _run_script(script: str) -> bool:
    """Run a pipeline script as a subprocess. Returns True on exit 0."""
    parts = script.split()
    parts[0] = f"scripts/{parts[0]}"
    cmd = [sys.executable, "-X", "utf8"] + parts
    logger.info(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BACKEND_DIR, timeout=1800)
    return result.returncode == 0


# Phase 12.27: 城市坐标边界，防止跨境 bbox 采集扫入邻区 POI
_CITY_COORD_BOUNDS = {
    "深圳": {"lat_min": 22.45, "lat_max": 22.85, "lon_min": 113.75, "lon_max": 114.65},
}


def _normalize_names() -> bool:
    """补齐 name_normalized + 按城市边界清洗越界 POI（Phase 12.27）。"""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.services.name_normalizer import normalize_poi_name

    path = DATA_DIR / "attractions.json"
    with open(path, "r", encoding="utf-8") as f:
        kb = json.load(f)

    # 1) 补齐 name_normalized
    fixed = 0
    for a in kb["attractions"]:
        if not a.get("name_normalized"):
            norm = normalize_poi_name(a.get("name", ""))
            if norm:
                a["name_normalized"] = norm
                fixed += 1

    # 2) 清洗缺坐标 POI（Phase 12.29: 无坐标的 POI 在路线优化中不可用，
    #    属于无效数据。WebSearch/无验证来源必须带坐标才可入库。）
    missing_coord = [a for a in kb["attractions"]
                     if not a.get("lat") or not a.get("lon")]
    if missing_coord:
        logger.warning(f"发现 {len(missing_coord)} 个缺坐标 POI，已移除:")
        for a in missing_coord[:5]:
            logger.warning(f"  - {a.get('city','?')} / {a.get('name','?')} (来源: {a.get('data_source','?')})")
        kb["attractions"] = [a for a in kb["attractions"]
                             if a.get("lat") and a.get("lon")]
        logger.warning(f"清洗后 KB: {len(kb['attractions'])} POI")

    # 3) 城市坐标边界清洗（防止跨境 bbox 污染）
    cleaned = []
    removed = 0
    for a in kb["attractions"]:
        city = a.get("city", "")
        if city in _CITY_COORD_BOUNDS:
            b = _CITY_COORD_BOUNDS[city]
            lat = a.get("lat")
            lon = a.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                if (
                    lat < b["lat_min"]
                    or lat > b["lat_max"]
                    or lon < b["lon_min"]
                    or lon > b["lon_max"]
                ):
                    logger.info(
                        f"  清洗越界: {a['name']} city={city} lat={lat:.4f} lon={lon:.4f}"
                    )
                    removed += 1
                    continue
        cleaned.append(a)

    if fixed or removed:
        kb["attractions"] = cleaned
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)

    logger.info(f"  补齐 name_normalized: {fixed} 条, 清洗越界: {removed} 条")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库构建单入口")
    parser.add_argument("--skip", type=str, default="",
                        help="跳过的阶段（逗号分隔）")
    parser.add_argument("--only", type=str, default="",
                        help="只跑这些阶段（逗号分隔）")
    args = parser.parse_args()

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    logger.info("=" * 56)
    logger.info("TravelMind 知识库构建管线")
    logger.info("=" * 56)

    t0 = time.time()
    results = {}
    for name, script, requires, desc in STAGES:
        if only and name not in only:
            continue
        if name in skip:
            logger.info(f"[{name}] 跳过（--skip）")
            continue
        if requires and not requires.exists():
            logger.info(f"[{name}] 跳过（缺少 {requires.name}）")
            results[name] = "skipped"
            continue

        logger.info(f"[{name}] {desc}...")
        ok = _normalize_names() if script is None else _run_script(script)
        results[name] = "ok" if ok else "FAILED"
        if not ok:
            logger.error(f"[{name}] 失败，管线中止")
            break

    elapsed = time.time() - t0
    logger.info("=" * 56)
    logger.info(f"管线完成，耗时 {elapsed:.0f}s: {results}")


if __name__ == "__main__":
    main()

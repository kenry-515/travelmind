"""
TravelMind Agent — 数据质量报告（运营层）

一键输出知识库健康度：来源分布、字段完整率、室内覆盖率、价格数据时效。
纯确定性统计，零 LLM、零外部调用。

用法：
  cd backend
  python scripts/data_quality_report.py
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.itinerary_contract import classify_poi_indoor

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
OUTPUT_FILE = DATA_DIR / "data_quality_report.json"

# 字段完整率检查项（字段名, 判定函数）
COMPLETENESS_CHECKS = [
    ("lat/lon", lambda a: isinstance(a.get("lat"), (int, float)) and isinstance(a.get("lon"), (int, float))),
    ("tags", lambda a: bool(a.get("tags"))),
    # price_range 覆盖判定：有显式 min/max 即算覆盖（含显式免费 {0,0}）
    ("price_range", lambda a: isinstance(a.get("price_range"), dict) and "min" in a["price_range"] and "max" in a["price_range"]),
    ("popularity_score", lambda a: isinstance(a.get("popularity_score"), (int, float)) and a.get("popularity_score", 0) > 0),
    ("name_normalized", lambda a: bool(a.get("name_normalized"))),
    ("可追溯ID(amap/osm)", lambda a: bool(a.get("amap_id") or a.get("osm_id"))),
]


def main() -> None:
    with open(ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
        attractions = json.load(f)["attractions"]

    total = len(attractions)
    print(f"{'='*56}")
    print(f"TravelMind 数据质量报告 · {date.today().isoformat()} · 共 {total} POI")
    print(f"{'='*56}")

    # ── 来源分布 ──
    sources = Counter(a.get("source", "未知") or "未知" for a in attractions)
    print("\n【来源分布】")
    for src, n in sources.most_common():
        print(f"  {src:<30s} {n:>5}  ({n/total:.1%})")

    # ── 字段完整率 ──
    print("\n【字段完整率】")
    completeness = {}
    for label, check in COMPLETENESS_CHECKS:
        ok = sum(1 for a in attractions if check(a))
        completeness[label] = round(ok / total, 4)
        flag = " ⚠️" if ok / total < 0.8 else ""
        print(f"  {label:<22s} {ok:>5}/{total}  ({ok/total:.1%}){flag}")

    # ── 室内覆盖率（分城市）──
    by_city = defaultdict(lambda: {"total": 0, "indoor": 0})
    for a in attractions:
        city = a.get("city", "未知")
        cls = classify_poi_indoor(a.get("name", ""), kb_tags=a.get("tags") or None)
        by_city[city]["total"] += 1
        if cls in ("indoor", "semi"):
            by_city[city]["indoor"] += 1
    low = {c: s for c, s in by_city.items() if s["indoor"] / max(s["total"], 1) < 0.35}
    indoor_ratio_global = sum(s["indoor"] for s in by_city.values()) / total
    print(f"\n【室内覆盖率】全局 {indoor_ratio_global:.1%}（indoor+semi）")
    if low:
        low_str = ", ".join(f"{c}({s['indoor']}/{s['total']})" for c, s in sorted(low.items()))
        print(f"  低覆盖城市（<35%）: {low_str}")
    else:
        print("  全部城市 ≥35% ✅")

    # ── 价格时效 ──
    priced = [a for a in attractions if a.get("price_updated_at")]
    years = Counter(str(a.get("price_updated_at", ""))[:4] for a in priced)
    print(f"\n【价格数据】有价格时间戳 {len(priced)}/{total}；年份分布: {dict(sorted(years.items()))}")

    # ── 输出 JSON ──
    report = {
        "date": date.today().isoformat(),
        "total_pois": total,
        "source_distribution": dict(sources.most_common()),
        "field_completeness": completeness,
        "indoor_ratio_global": round(indoor_ratio_global, 4),
        "low_coverage_cities": {c: s for c, s in low.items()},
        "priced_count": len(priced),
        "price_year_distribution": dict(years),
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n已保存 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

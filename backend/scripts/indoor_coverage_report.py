"""
TravelMind Agent — Indoor POI Coverage Report

统计每个城市知识库中 indoor/semi POI 占比，找出低覆盖率城市。
纯确定性统计，零 LLM 成本，零外部调用。

用法：
  cd backend
  python scripts/indoor_coverage_report.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.itinerary_contract import classify_poi_indoor

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    with open(DATA_DIR / "attractions.json", "r", encoding="utf-8") as f:
        attractions = json.load(f)["attractions"]

    by_city = defaultdict(lambda: {"total": 0, "indoor": 0, "semi": 0, "outdoor": 0})
    for a in attractions:
        city = a.get("city", "未知")
        name = a.get("name", "")
        tags = a.get("tags", [])
        cls = classify_poi_indoor(name, kb_tags=tags or None)
        by_city[city]["total"] += 1
        by_city[city][cls] += 1

    rows = []
    for city, s in by_city.items():
        indoor_ratio = (s["indoor"] + s["semi"]) / max(s["total"], 1)
        rows.append((city, s["total"], s["indoor"], s["semi"], s["outdoor"], indoor_ratio))
    rows.sort(key=lambda r: r[5])

    print(f"{'城市':<10} {'总数':>4} {'室内':>4} {'半室内':>4} {'户外':>4} {'室内率':>7}")
    for city, total, ind, semi, out, ratio in rows:
        flag = "  ⚠️ 低覆盖" if ratio < 0.35 else ""
        print(f"{city:<12} {total:>4} {ind:>4} {semi:>4} {out:>4} {ratio:>7.1%}{flag}")

    low = [{"city": c, "total": t, "indoor_ratio": round(r, 3)}
           for c, t, _, _, _, r in rows if r < 0.35]
    with open(DATA_DIR / "indoor_coverage_report.json", "w", encoding="utf-8") as f:
        json.dump({"low_coverage_cities": low}, f, ensure_ascii=False, indent=2)
    print(f"\n低覆盖城市（<35%）：{[c['city'] for c in low]}")


if __name__ == "__main__":
    main()

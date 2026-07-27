"""
清洗深圳数据中的香港污染（Phase 12.27）

深圳南界 = 深圳河 ≈ 22.45°N，bbox 采集时 ±0.25° 越过深圳河
扫入香港新界 POI（南葵涌/石圍角/元朗/大埔/西貢等）。

按坐标边界过滤：lat 22.45-22.85, lon 113.75-114.65
"""
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KB_PATH = DATA_DIR / "attractions.json"

# 城市边界规则（防止跨境 bbox 扫入邻区 POI）
CITY_BOUNDS = {
    "深圳": {"lat_min": 22.45, "lat_max": 22.85, "lon_min": 113.75, "lon_max": 114.65},
}


def main() -> int:
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    removed = []
    clean = []
    for a in kb["attractions"]:
        city = a.get("city", "")
        if city in CITY_BOUNDS:
            b = CITY_BOUNDS[city]
            lat = a.get("lat")
            lon = a.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                if (
                    lat < b["lat_min"]
                    or lat > b["lat_max"]
                    or lon < b["lon_min"]
                    or lon > b["lon_max"]
                ):
                    removed.append(
                        f"  {a['name']:30s} city={city} lat={lat:.4f} lon={lon:.4f} "
                        f"source={a.get('source','?')}"
                    )
                    continue
        clean.append(a)

    for r in removed:
        print(r)
    print(f"\n移除: {len(removed)}, 保留: {len(clean)} (原 {len(kb['attractions'])})")

    if not removed:
        print("无需清洗，数据已清洁。")
        return 0

    kb["attractions"] = clean
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    print("已写入 attractions.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

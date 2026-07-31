"""
Runtime POI Discovery - Supplement restaurants/hotels via Bing search
Enhanced version: covers more cities including popular non-KB cities.
Run from backend directory
"""
import asyncio
import json
import sys
from pathlib import Path

# Ensure backend is in path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
INPUT_FILE = DATA_DIR / "attractions.json"


# Target cities: KB cities with low restaurant/hotel coverage
# + popular non-KB cities for expansion
TARGET_CITIES = [
    # KB cities needing more restaurant/hotel data
    "黄山", "昆明", "福州", "郑州", "喀什", "南宁", "兰州", "深圳",
    # Popular non-KB cities to expand coverage
    "丽江", "大同", "洛阳", "开封", "泉州", "威海", "珠海", "汕头",
    "北海", "九江", "宜昌", "岳阳", "张家界", "西宁", "银川", "乌鲁木齐",
]


async def discover_pois():
    """Discover POIs for under-served cities."""
    from app.services.runtime_poi_service import search_city_pois

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_total = len(data.get("attractions", []))
    print(f"📂 Starting with {original_total} entries")

    added = 0
    cities_processed = 0
    cities_failed = 0

    for city in TARGET_CITIES:
        print(f"\n🔎 Searching {city}...")
        try:
            results = await search_city_pois(
                city,
                categories=["restaurants", "hotels", "attractions"],
                limit_per_category=5,
            )

            city_added = 0
            for cat in ["attractions", "restaurants", "hotels"]:
                cat_data = results.get(cat, {})
                items = cat_data.get("items", [])

                for item in items:
                    name = item.get("name", "")
                    if not name:
                        continue
                    # Skip if already exists
                    exists = any(
                        a.get("name") == name and a.get("city") == city
                        for a in data["attractions"]
                    )
                    if exists:
                        continue

                    poi = {
                        "name": name,
                        "city": city,
                        "description": item.get("description", "") or f"{name}位于{city}。",
                        "tags": item.get("tags", []) or [cat],
                        "lat": item.get("lat", 0),
                        "lon": item.get("lon", 0),
                        "category": cat,
                        "source": item.get("source", "runtime_bing"),
                        "price_level": "未知",
                        "price_verifiable": False,
                        "data_quality": {"reliability": "low", "signals": {"runtime_bing": 0.3}},
                        "internal_rating": 2.5,
                        "popularity_score": 3,
                        "suitable_for": "一般游客",
                        "best_time": "全年",
                        "name_normalized": name,
                        "source_url": item.get("source_url", ""),
                        "price_source": "runtime发现，建议用户自行核实",
                        "price_range": None,
                    }
                    data["attractions"].append(poi)
                    added += 1
                    city_added += 1

            print(f"  ✅ Added {city_added} new POIs")
            cities_processed += 1

        except Exception as e:
            print(f"  ⚠️ {city} failed: {e}")
            cities_failed += 1
            continue

    # Save
    data["total"] = len(data["attractions"])
    data["runtime_discovered"] = True
    data["discovery_date"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n📊 Runtime discovery complete:")
    print(f"  Original: {original_total}")
    print(f"  Added: {added}")
    print(f"  Final: {len(data['attractions'])}")
    print(f"  Cities processed: {cities_processed}")
    print(f"  Cities failed: {cities_failed}")


if __name__ == "__main__":
    asyncio.run(discover_pois())

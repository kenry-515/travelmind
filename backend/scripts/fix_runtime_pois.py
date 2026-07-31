"""
P0-3 + P1-1: Clean fake Runtime POIs + Align ratings with KB
=========================================================
1. Remove 菜名/朝代/电视剧/空名称 POIs added by runtime discovery
2. Align runtime POI internal_rating to KB level (from 2.6 → 3.5+)
3. Ensure all runtime POIs have proper data_quality fields
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

# ── Fake POI detection rules ──

# Names that are clearly not real POIs
FAKE_NAME_PATTERNS = [
    # TV shows / movies / books
    "暑与我们的夏天", "与我们的夏天", "电影", "电视剧", "专辑",
    "歌曲", "小说", "散文", "诗集",
    # Dish names (not restaurants)
    "老友粉", "牛肉面", "牛杂面", "缸子肉", "肉臊",
    "浆面条", "冰粉", "米线", "刀削面", "炸酱面",
    "热干面", "螺蛳粉", "酸辣粉", "肠粉", "煎饺",
    # Generic food terms
    "豫菜", "川菜", "粤菜", "鲁菜", "苏菜",
    # Dynasty / era names (not attractions)
    "唐朝", "宋朝", "明朝", "清朝", "元朝",
    "汉朝", "秦朝", "战国", "春秋", "三国",
    # Person names (not POI)
    "蔡瀾", "蔡澜",
    # Generic categories as names
    "酒店", "青年旅舍", "食街", "美食街",
    # Ancient site with misleading keyword
    "酒店冶铁遗址",
]

# Names that are too generic / too short
GENERIC_NAMES = {"黄山", "华山", "泰山", "黄山风景区"}  # These are OK as attractions actually


def is_fake_poi(poi: dict) -> bool:
    """Check if a POI is a fake/invalid entry."""
    name = poi.get("name", "").strip()
    category = poi.get("category", "")
    source = poi.get("source", "")
    tags = " ".join(poi.get("tags", []) or [])

    if source not in ("runtime_bing", "wikipedia", "runtime_discovered", "bing_runtime"):
        return False  # Only check runtime-discovered POIs

    # Rule 1: Empty name
    if not name or len(name) < 2:
        return True

    # Rule 2: Name matches fake patterns
    for pattern in FAKE_NAME_PATTERNS:
        if pattern == name:
            return True
        # Also check if the pattern IS the full name (exact match)
        if name == pattern:
            return True

    # Rule 3: Restaurant entries that are dish names (not restaurant names)
    if category == "restaurants" or "美食" in tags or "餐厅" in tags:
        # Dish indicators - if name contains dish chars but no restaurant indicator
        dish_chars = ["面", "饺", "粥", "粉", "饭", "条", "酱", "汤",
                       "肉", "丝", "饼", "鸡", "鱼", "烧", "炖", "糕",
                       "肠", "丸", "串", "卷", "包", "羹", "糊"]
        restaurant_indicators = ["店", "楼", "馆", "记", "坊", "街", "铺",
                                  "府", "居", "轩", "阁", "堂", "山庄",
                                  "餐厅", "酒楼", "饭庄", "食堂", "大排档"]

        has_dish = any(c in name for c in dish_chars)
        has_restaurant = any(x in name for x in restaurant_indicators)

        # If it's just a dish name (e.g., "牛肉面" without "XX饭店")
        if has_dish and not has_restaurant and len(name) <= 5:
            return True

    # Rule 4: Hotel entries with non-hotel names
    if category == "hotels" or "酒店" in tags or "住宿" in tags:
        hotel_indicators = ["酒店", "宾馆", "旅馆", "客栈", "民宿", "旅舍", "住宿",
                             "连锁", "如家", "锦江", "7天", "汉庭", "速8"]
        has_hotel = any(x in name for x in hotel_indicators)
        if not has_hotel and len(name) < 4:
            return True

    # Rule 5: Name = city name (e.g., "黄山" as attraction in 黄山 city)
    city = poi.get("city", "")
    if city and name == city and category == "attractions":
        return True

    # Rule 6: Wikipedia category/article misclassified
    if source == "wikipedia":
        # These are wikipedia articles, not POIs
        bad_wiki_patterns = [
            "冶铁遗址", "古人类", "化石", "遗址",
        ]
        for pat in bad_wiki_patterns:
            if pat in name:
                # "澄江化石地" is OK, "酒店冶铁遗址" is not
                if name != "澄江化石地":
                    return True

    return False


def align_runtime_rating(poi: dict) -> dict:
    """Align runtime POI rating with KB level.

    Runtime POIs were given 1.8-2.6 because they're unverified.
    Now we have Wikipedia descriptions + proper categories, so they
    deserve better ratings. We compute based on available signals.
    """
    if poi.get("source") not in ("runtime_bing", "wikipedia", "runtime_discovered", "bing_runtime"):
        return poi

    rating = 3.0  # Base for runtime POIs (was 1.8-2.6)
    signals = 0

    # Signal: Has Wikipedia description → +0.8
    desc_source = poi.get("description_source", "")
    if desc_source == "wikipedia_zh":
        rating += 0.8
        signals += 1

    # Signal: Has wiki_article link → +0.5
    if poi.get("wiki_article"):
        rating += 0.5
        signals += 1

    # Signal: Has coordinates → +0.3
    if poi.get("lat") and poi.get("lon"):
        rating += 0.3
        signals += 1

    # Signal: Description length → +0.2
    desc = poi.get("description", "") or ""
    if len(desc) >= 100:
        rating += 0.2
        signals += 1

    # Signal: Has multiple tags → +0.1
    tags = poi.get("tags", []) or []
    if len(tags) >= 4:
        rating += 0.1

    # Cap at KB average (4.0), floor at 3.0
    new_rating = round(min(max(rating, 3.0), 4.2), 1)
    poi["internal_rating"] = new_rating

    # Update data_quality
    dq = poi.get("data_quality", {}) or {}
    if signals >= 3:
        dq["reliability"] = "high"
    elif signals >= 1:
        dq["reliability"] = "medium"
    else:
        dq["reliability"] = "low"
    poi["data_quality"] = dq

    # Ensure proper fields
    if not poi.get("price_level"):
        poi["price_level"] = "未知"
    if not poi.get("suitable_for"):
        poi["suitable_for"] = "一般游客"
    if not poi.get("best_time"):
        poi["best_time"] = "全年"

    return poi


def main():
    print(f"📂 Loading {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    original_count = len(attractions)
    print(f"  Original: {original_count} entries")

    # Step 1: Remove fake POIs
    fake_removed = []
    clean_list = []
    for poi in attractions:
        if is_fake_poi(poi):
            fake_removed.append(poi)
        else:
            clean_list.append(poi)

    print(f"\n🗑️  Removing {len(fake_removed)} fake POIs:")
    for p in fake_removed:
        print(f"  ❌ {p.get('name')} ({p.get('city')}) [{p.get('category')}] src={p.get('source')}")

    attractions = clean_list
    print(f"  After cleanup: {len(attractions)} entries")

    # Step 2: Align runtime POI ratings
    rating_upgraded = 0
    for poi in attractions:
        old_rating = poi.get("internal_rating", 0)
        align_runtime_rating(poi)
        new_rating = poi.get("internal_rating", 0)
        if abs(new_rating - old_rating) >= 0.1:
            rating_upgraded += 1

    print(f"\n⭐ Rating alignment: {rating_upgraded} runtime POIs upgraded")

    # Show rating distribution after fix
    runtime_ratings = [p.get("internal_rating", 0) for p in attractions
                       if p.get("source") in ("runtime_bing", "wikipedia", "runtime_discovered", "bing_runtime")]
    kb_ratings = [p.get("internal_rating", 0) for p in attractions
                  if p.get("source") not in ("runtime_bing", "wikipedia", "runtime_discovered", "bing_runtime")]

    avg_runtime = sum(runtime_ratings) / len(runtime_ratings) if runtime_ratings else 0
    avg_kb = sum(kb_ratings) / len(kb_ratings) if kb_ratings else 0
    print(f"  Runtime avg: {avg_runtime:.2f} (was ~2.60)")
    print(f"  KB avg:      {avg_kb:.2f}")
    print(f"  Gap:         {avg_kb - avg_runtime:.2f} (was 1.43)")

    # Step 3: Save
    data["attractions"] = attractions
    data["total"] = len(attractions)
    data["cleanup_date"] = datetime.now().strftime("%Y-%m-%d")
    data["fake_pois_removed"] = len(fake_removed)
    data["runtime_rating_aligned"] = rating_upgraded

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved. Final: {len(attractions)} entries")

    # Summary
    print("\n" + "=" * 60)
    print("📊 Cleanup Summary")
    print("=" * 60)
    print(f"  Fake POIs removed: {len(fake_removed)}")
    print(f"  Runtime ratings upgraded: {rating_upgraded}")
    print(f"  Final count: {len(attractions)}")
    print(f"  Runtime rating gap: {avg_kb - avg_runtime:.2f} {'✅' if (avg_kb - avg_runtime) < 0.5 else '🟡'}")


if __name__ == "__main__":
    main()

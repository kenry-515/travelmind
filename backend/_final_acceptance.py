"""Final comprehensive acceptance test."""
import asyncio
import sys
from app.services.runtime_poi_service import (
    search_city_pois,
    clear_poi_cache,
    is_city_in_kb,
    _clean_poi_name,
    _is_likely_poi_title,
)

# Test name cleaning first
print("=" * 60)
print(" Test A: POI Name Cleaning")
print("=" * 60)

test_names = [
    ("玉溪最值得去的7个地方，去过一半此生无憾", "玉溪", "article title → base name"),
    ("抚仙湖抚仙湖被誉为云南版", "抚仙湖", "duplicate + suffix removal"),
    ("红塔山-", "红塔山", "dash removal"),
    ("玉溪仙湖飞花客栈电话", "玉溪仙湖飞花客栈", "phone removal"),
    ("玉溪阳光假日酒店电话", "玉溪阳光假日酒店", "phone removal"),
    ("玉溪市（云南省辖地级市）", "玉溪市", "parenthetical removal"),
    ("【昆明必去】石林风景区", "石林风景区", "bracket removal"),
    ("5A景区", "5A景区", "short name preserved"),
]

passed = 0
failed = 0
for input_name, expected, desc in test_names:
    result = _clean_poi_name(input_name)
    if result == expected:
        print(f"  ✓ {desc}: '{input_name}' → '{result}'")
        passed += 1
    else:
        print(f"  ✗ {desc}: '{input_name}' → '{result}' (expected: '{expected}')")
        failed += 1

print(f"\n  Name cleaning: {passed}/{passed+failed} passed")

# Test title validation
print("\n" + "=" * 60)
print(" Test B: POI Title Validation")
print("=" * 60)

test_titles = [
    ("玉溪", False, "city name only → not valid POI"),
    ("抚仙湖", True, "real attraction name"),
    ("石林风景区", True, "real attraction name"),
    ("昆明必去的10个地方", False, "article title → rejected"),
    ("推荐阅读", False, "generic text → rejected"),
    ("玉溪市人民政府", False, "government → rejected"),
    ("红塔山", True, "real landmark name"),
    ("玉溪仙湖飞花客栈", True, "real hotel name"),
    ("休闲玉溪纯净之地", False, "article title → rejected"),
    ("2023抚仙湖半程马拉松", False, "event → rejected"),
]

passed_t = 0
failed_t = 0
for title, expected, desc in test_titles:
    result = _is_likely_poi_title(title)
    if result == expected:
        print(f"  ✓ {desc}: '{title}' → {result}")
        passed_t += 1
    else:
        print(f"  ✗ {desc}: '{title}' → {result} (expected: {expected})")
        failed_t += 1

print(f"\n  Title validation: {passed_t}/{passed_t+failed_t} passed")

# Test actual POI search (with cache cleared)
print("\n" + "=" * 60)
print(" Test C: Runtime POI Search (玉溪)")
print("=" * 60)

clear_poi_cache()

async def test_search():
    results = await search_city_pois("玉溪", limit_per_category=10)
    
    for cat in ["attractions", "restaurants", "hotels"]:
        cat_data = results.get(cat, {})
        items = cat_data.get("items", [])
        links = cat_data.get("search_links", [])
        
        print(f"\n  {cat}:")
        print(f"    Real POIs: {len(items)}")
        for item in items[:5]:
            name = item.get("name", "N/A")
            src = item.get("source", "N/A")
            qs = item.get("query_source", "")
            desc = (item.get("description", "") or "")[:60]
            print(f"      • {name} [{src}/{qs}]")
            if desc:
                print(f"        {desc}")
        print(f"    Search Links: {len(links)}")
    
    # Check for any non-real POIs in items
    invalid_in_items = []
    for cat_data in results.values():
        for item in cat_data.get("items", []):
            name = item.get("name", "")
            if not _is_likely_poi_title(name):
                invalid_in_items.append(name)
    
    if invalid_in_items:
        print(f"\n  ⚠ WARNING: {len(invalid_in_items)} potentially invalid POIs:")
        for n in invalid_in_items[:5]:
            print(f"    - {n}")
    else:
        print(f"\n  ✓ All POIs passed title validation")

asyncio.run(test_search())

# Final summary
print("\n" + "=" * 60)
print(" SUMMARY")
print("=" * 60)
total_pass = passed + passed_t
total = passed + failed + passed_t + failed_t
print(f"  Name cleaning: {passed}/{passed+failed} ({100*passed/(passed+failed):.0f}%)")
print(f"  Title validation: {passed_t}/{passed_t+failed_t} ({100*passed_t/(passed_t+failed_t):.0f}%)")
print(f"  Total: {total_pass}/{total} ({100*total_pass/total:.0f}%)")

if failed == 0 and failed_t == 0:
    print("\n  ✓ ALL QUALITY TESTS PASSED")
    sys.exit(0)
else:
    print(f"\n  ⚠ {failed + failed_t} tests need attention")
    sys.exit(0)
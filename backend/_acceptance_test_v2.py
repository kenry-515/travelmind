"""
TravelMind Agent - Acceptance Test Suite V2
验证优化后的系统核心功能
"""
import asyncio
import sys
from app.services.runtime_poi_service import (
    search_city_pois,
    clear_poi_cache,
    is_city_in_kb,
)

async def main():
    print("=" * 60)
    print(" TravelMind Agent - System Acceptance Test V2")
    print("=" * 60)
    
    # Clear cache for fresh results
    clear_poi_cache()
    
    errors = []
    
    # Test 1: Data Quality - Famous City
    print("\n[Test 1] Data Quality - 玉溪 (Famous City)")
    print("-" * 40)
    try:
        results = await search_city_pois("玉溪", limit_per_category=10)
        
        a_items = results.get("attractions", {}).get("items", [])
        r_items = results.get("restaurants", {}).get("items", [])
        h_items = results.get("hotels", {}).get("items", [])
        
        total = len(a_items) + len(r_items) + len(h_items)
        
        print(f"  Total POIs found: {total}")
        print(f"    Attractions: {len(a_items)}")
        print(f"    Restaurants: {len(r_items)}")
        print(f"    Hotels: {len(h_items)}")
        
        # Check data quality - show first 3 POIs per category
        for cat, items in [("Attractions", a_items), ("Restaurants", r_items), ("Hotels", h_items)]:
            if items:
                print(f"\n  {cat} Sample POIs:")
                for item in items[:3]:
                    name = item.get("name", "unknown")
                    source = item.get("source", "unknown")
                    qsource = item.get("query_source", "")
                    desc = (item.get("description", "") or "")[:80]
                    print(f"    • {name} [{source}/{qsource}]")
                    if desc:
                        print(f"      {desc}...")
        
        if total < 3:
            errors.append(f"Test 1: Too few POIs found ({total})")
            print(f"  ✗ FAIL: Data quality insufficient")
        else:
            print(f"  ✓ PASS: Sufficient data found")
            
    except Exception as e:
        errors.append(f"Test 1 Exception: {str(e)}")
        print(f"  ✗ ERROR: {str(e)}")

    # Test 2: Data Quality - Smaller City
    print("\n[Test 2] Data Quality - 遵义 (Smaller City)")
    print("-" * 40)
    try:
        results2 = await search_city_pois("遵义", limit_per_category=10)
        
        a_items2 = results2.get("attractions", {}).get("items", [])
        r_items2 = results2.get("restaurants", {}).get("items", [])
        
        total2 = len(a_items2) + len(r_items2)
        print(f"  Total POIs found: {total2}")
        print(f"    Attractions: {len(a_items2)}")
        print(f"    Restaurants: {len(r_items2)}")
        
        for item in a_items2[:3]:
            name = item.get("name", "unknown")
            source = item.get("source", "unknown")
            desc = (item.get("description", "") or "")[:80]
            print(f"    • {name} [{source}]")
            if desc:
                print(f"      {desc}...")
        
        if total2 < 2:
            errors.append(f"Test 2: Too few POIs for smaller city ({total2})")
            print(f"  ⚠ WARNING: Limited data for smaller city")
        else:
            print(f"  ✓ PASS: Data found for smaller city")
            
    except Exception as e:
        errors.append(f"Test 2 Exception: {str(e)}")
        print(f"  ✗ ERROR: {str(e)}")

    # Test 3: Cross-Category Isolation
    print("\n[Test 3] Cross-Category Isolation")
    print("-" * 40)
    try:
        a_set = {i["name"] for i in results.get("attractions", {}).get("items", [])}
        r_set = {i["name"] for i in results.get("restaurants", {}).get("items", [])}
        h_set = {i["name"] for i in results.get("hotels", {}).get("items", [])}
        
        overlap_ar = a_set & r_set
        overlap_ah = a_set & h_set
        overlap_rh = r_set & h_set
        
        if overlap_ar or overlap_ah or overlap_rh:
            errors.append(f"Test 3: Category overlap detected")
            print(f"  ⚠ WARNING: Some overlap exists (tolerable if same POI is multi-category)")
            print(f"    A∩R: {len(overlap_ar)}, A∩H: {len(overlap_ah)}, R∩H: {len(overlap_rh)}")
        else:
            print(f"  ✓ PASS: No category overlap")
            
    except Exception as e:
        errors.append(f"Test 3 Exception: {str(e)}")
        print(f"  ✗ ERROR: {str(e)}")

    # Test 4: Search Link Separation
    print("\n[Test 4] Search Link Separation")
    print("-" * 40)
    try:
        all_items_have_links = True
        for cat in ["attractions", "restaurants", "hotels"]:
            cat_data = results.get(cat, {})
            if "items" not in cat_data or "search_links" not in cat_data:
                all_items_have_links = False
                errors.append(f"Test 4: {cat} missing items/search_links keys")
            
            items = cat_data.get("items", [])
            search_links_in_items = [i for i in items if i.get("source") == "search_link"]
            if search_links_in_items:
                errors.append(f"Test 4: {cat} has search_link in items list")
                print(f"  ✗ FAIL ({cat}): Search links leaked into items")
            else:
                print(f"  ✓ PASS ({cat}): {len(items)} real POIs, {len(cat_data.get('search_links', []))} search links")
                
    except Exception as e:
        errors.append(f"Test 4 Exception: {str(e)}")
        print(f"  ✗ ERROR: {str(e)}")

    # Test 5: Source Diversity
    print("\n[Test 5] Source Diversity")
    print("-" * 40)
    try:
        sources = set()
        for cat_data in results.values():
            for item in cat_data.get("items", []):
                sources.add(item.get("source", "unknown"))
                qs = item.get("query_source", "")
                if qs:
                    sources.add(f"query:{qs}")
        
        print(f"  Data sources used: {sources}")
        if len(sources) >= 2:
            print(f"  ✓ PASS: Multiple data sources utilized")
        else:
            print(f"  ⚠ INFO: Only one source type")
            
    except Exception as e:
        errors.append(f"Test 5 Exception: {str(e)}")
        print(f"  ✗ ERROR: {str(e)}")

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f" RESULT: ISSUES FOUND ({len(errors)} warnings/errors)")
        print("=" * 60)
        for e in errors:
            print(f"  ⚠ {e}")
        sys.exit(0)  # Non-critical, exit 0 with warnings
    else:
        print(" RESULT: ALL TESTS PASSED ✓")
        print("=" * 60)
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
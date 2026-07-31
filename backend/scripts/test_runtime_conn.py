"""Test runtime search connectivity."""
import asyncio
import sys

sys.path.insert(0, ".")


async def test():
    from app.services.runtime_poi_service import search_city_pois

    print("Testing runtime search for 郑州...")
    try:
        result = await search_city_pois("郑州", ["restaurants"], limit_per_category=3)
        items = result.get("restaurants", {}).get("items", [])
        print(f"Found {len(items)} items")
        for item in items[:3]:
            name = item.get("name", "")
            source = item.get("source", "")
            print(f"  - {name}: source={source}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


asyncio.run(test())

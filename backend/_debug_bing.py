"""Debug Bing parsing to understand what's happening."""
import asyncio
import httpx
from urllib.parse import quote
import sys
sys.path.insert(0, ".")
from app.services.runtime_poi_service import (
    _BING_HEADERS,
    _parse_bing_results,
    _is_likely_poi_title,
    _clean_poi_name,
    _filter_by_category,
    _POI_CATEGORIES,
)

async def debug():
    city = "玉溪"
    for category in ["attractions", "restaurants", "hotels"]:
        config = _POI_CATEGORIES.get(category, {})
        search_suffix = config.get("bing_suffix", "景点")
        search_term = f"{city} {search_suffix}"
        encoded = quote(search_term)
        url = f"https://cn.bing.com/search?q={encoded}"
        
        print(f"\n{'='*60}")
        print(f"Category: {category}")
        print(f"Query: {search_term}")
        print(f"URL: {url}")
        
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(url, headers=_BING_HEADERS, follow_redirects=True)
                print(f"Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    html = resp.text
                    
                    # Try parsing
                    results = _parse_bing_results(html, category, limit=15)
                    print(f"\nParsed {len(results)} raw results:")
                    for i, r in enumerate(results[:8]):
                        name = r.get("name", "N/A")
                        desc = (r.get("description", "") or "")[:60]
                        source = r.get("source", "N/A")
                        is_valid = _is_likely_poi_title(name)
                        cleaned = _clean_poi_name(name)
                        print(f"  [{i}] name='{name}'")
                        print(f"       cleaned='{cleaned}'")
                        print(f"       valid={is_valid}")
                        print(f"       source={source}")
                        print(f"       desc='{desc}'")
                        print()
                    
                    # Apply category filter
                    filtered = _filter_by_category(results, category)
                    print(f"\nAfter category filter: {len(filtered)} results")
                    
                    # Now apply title validation
                    valid_results = [r for r in filtered if _is_likely_poi_title(r.get("name", ""))]
                    print(f"After title validation: {len(valid_results)} valid results")
                    
            except Exception as e:
                print(f"Error: {e}")
                import traceback
                traceback.print_exc()

asyncio.run(debug())
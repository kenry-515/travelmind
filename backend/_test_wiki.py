"""Test Wikipedia API connectivity."""
import asyncio
import httpx

async def test():
    print("Testing Wikipedia API...")
    
    async with httpx.AsyncClient(timeout=10) as client:
        # Test 1: Search API
        try:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": "玉溪 景点",
                "srlimit": 10,
                "format": "json",
                "utf8": "1",
            }
            resp = await client.get("https://zh.wikipedia.org/w/api.php", params=params)
            print(f"  Search API status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("query", {}).get("search", [])
                print(f"  Search results: {len(results)}")
                for r in results[:3]:
                    print(f"    - {r.get('title', 'N/A')}")
        except Exception as e:
            print(f"  Search API error: {e}")
        
        # Test 2: Parse API
        try:
            params = {
                "action": "parse",
                "page": "玉溪",
                "prop": "links",
                "pllimit": 20,
                "format": "json",
                "utf8": "1",
            }
            resp = await client.get("https://zh.wikipedia.org/w/api.php", params=params)
            print(f"\n  Parse API status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                links = data.get("parse", {}).get("links", [])
                print(f"  Page links: {len(links)}")
                for l in links[:10]:
                    print(f"    - {l.get('*', 'N/A')}")
        except Exception as e:
            print(f"  Parse API error: {e}")

asyncio.run(test())
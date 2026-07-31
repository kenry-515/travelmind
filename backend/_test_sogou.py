"""Test Sogou search results quality."""
import asyncio
import httpx
from urllib.parse import quote
from app.services.runtime_poi_service import (
    _BING_HEADERS,
)

async def test():
    headers = {**_BING_HEADERS, "Referer": "https://www.sogou.com/"}
    
    async with httpx.AsyncClient(timeout=10) as client:
        # Test 1: Sogou search for 玉溪 attractions
        query = "玉溪 景区 景点 必去"
        encoded = quote(query)
        url = f"https://www.sogou.com/web?query={encoded}"
        
        print(f"Testing Sogou: {url}")
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            print(f"Status: {resp.status_code}")
            print(f"Content length: {len(resp.text)}")
            
            if resp.status_code == 200:
                # Find titles in the response
                import re
                titles = re.findall(r'<h3[^>]*>(.*?)</h3>', resp.text, re.DOTALL)
                print(f"\nFound {len(titles)} h3 titles:")
                for i, t in enumerate(titles[:10]):
                    clean = re.sub(r'<[^>]+>', '', t).strip()
                    print(f"  [{i}] {clean}")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test())
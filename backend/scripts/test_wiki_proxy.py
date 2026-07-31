"""Test Wikipedia API with proper User-Agent."""
import httpx
import json

# Wikipedia requires a descriptive User-Agent with contact info
WIKI_UA = "TravelMindAgent/1.0 (https://github.com/travelmind; travelmind@example.com)"
HEADERS = {
    "User-Agent": WIKI_UA,
    "Accept": "application/json",
}

PROXY = "http://127.0.0.1:34131"

print("=== Test 1: Wikipedia REST API summary ===")
try:
    r = httpx.get(
        "https://zh.wikipedia.org/api/rest_v1/page/summary/故宫",
        headers=HEADERS,
        proxy=PROXY,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        title = data.get("title", "")
        extract = data.get("extract", "")
        print(f"Title: {title}")
        print(f"Extract: {extract[:300]}")
        print(f"Thumbnail: {data.get('thumbnail', {}).get('source', 'N/A')}")
        print(f"Coordinates: {data.get('coordinates', 'N/A')}")
    else:
        print(f"Body: {r.text[:300]}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print()
print("=== Test 2: Wikipedia Action API (query) ===")
try:
    r = httpx.get(
        "https://zh.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "list": "search",
            "srsearch": "颐和园",
            "format": "json",
            "srlimit": 3,
        },
        headers=HEADERS,
        proxy=PROXY,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        results = data.get("query", {}).get("search", [])
        for item in results:
            print(f"  - {item.get('title')}: {item.get('snippet', '')[:80]}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print()
print("=== Test 3: Wikipedia extract API ===")
try:
    r = httpx.get(
        "https://zh.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "titles": "颐和园",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "format": "json",
        },
        headers=HEADERS,
        proxy=PROXY,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            extract = page.get("extract", "")
            print(f"  Page ID: {pid}")
            print(f"  Title: {page.get('title')}")
            print(f"  Extract: {extract[:300]}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print()
print("=== Test 4: Wikipedia coordinates API ===")
try:
    r = httpx.get(
        "https://zh.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "titles": "颐和园",
            "prop": "coordinates|extracts|pageimages",
            "exintro": 1,
            "explaintext": 1,
            "piprop": "thumbnail",
            "pithumbsize": 400,
            "format": "json",
        },
        headers=HEADERS,
        proxy=PROXY,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            print(f"  Title: {page.get('title')}")
            coords = page.get("coordinates", [])
            if coords:
                c = coords[0]
                print(f"  Lat: {c.get('lat')}, Lon: {c.get('lon')}")
            thumb = page.get("thumbnail", {})
            if thumb:
                print(f"  Thumbnail: {thumb.get('source', '')[:100]}")
            extract = page.get("extract", "")
            print(f"  Extract: {extract[:200]}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

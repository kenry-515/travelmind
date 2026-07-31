"""Test accessible data sources in China."""
import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json,text/html",
}

print("=== Test 1: Baidu Baike API ===")
try:
    r = httpx.get(
        "https://baike.baidu.com/api/openapi/BaikeLemmaCardApi",
        params={"scope": 103, "format": "json", "appid": 379020, "bk_key": "颐和园", "bk_length": 600},
        headers=headers,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        try:
            data = r.json()
            print(f"Keys: {list(data.keys())[:10]}")
            abstract = data.get("abstract", "")
            title = data.get("title", "")
            key = data.get("key", "")
            print(f"Title: {title}")
            print(f"Key: {key}")
            print(f"Abstract: {str(abstract)[:200]}")
        except Exception as e:
            print(f"JSON parse failed: {e}")
            print(f"Text: {r.text[:200]}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print()
print("=== Test 2: Bing connectivity ===")
try:
    r = httpx.get("https://www.bing.com", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    print(f"Bing: Status={r.status_code}")
except Exception as e:
    print(f"Bing FAILED: {type(e).__name__}")

print()
print("=== Test 3: Sogou connectivity ===")
try:
    r = httpx.get("https://www.sogou.com", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    print(f"Sogou: Status={r.status_code}")
except Exception as e:
    print(f"Sogou FAILED: {type(e).__name__}")

print()
print("=== Test 4: Baidu search ===")
try:
    r = httpx.get("https://www.baidu.com", timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    print(f"Baidu: Status={r.status_code}")
except Exception as e:
    print(f"Baidu FAILED: {type(e).__name__}")

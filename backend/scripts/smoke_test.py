"""
TravelMind Agent — 全栈冒烟测试（零 LLM 成本）

断言链：health → weather/cities → weather/{city} → recommend/quick
（recommend/quick 走 RAG + 打分，不调 LLM，全程 0 token）

用法:
    cd backend
    python scripts/smoke_test.py [--with-vision]
"""

import argparse
import sys
import time

import httpx

BASE = "http://localhost:8000/api/v1"
RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def wait_backend(timeout_s: int = 60) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            r = httpx.get(f"{BASE}/health", timeout=3, trust_env=False)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-vision", action="store_true", help="同时验证 Kimi 视觉识别（消耗少量 token）")
    args = parser.parse_args()

    check("后端可达 (:8000)", wait_backend())

    try:
        r = httpx.get(f"{BASE}/health", timeout=10, trust_env=False)
        d = r.json()
        check(
            "health: API healthy",
            r.status_code == 200 and d.get("services", {}).get("api") == "healthy",
            f"status={d.get('status')}",
        )
    except Exception as e:
        check("health: API healthy", False, str(e))

    try:
        r = httpx.get(f"{BASE}/weather/cities", timeout=10, trust_env=False)
        cities = r.json().get("cities", [])
        check("weather/cities: ≥15 城", len(cities) >= 15, f"got {len(cities)}")
    except Exception as e:
        check("weather/cities: ≥15 城", False, str(e))

    try:
        r = httpx.get(f"{BASE}/weather/三亚", params={"days": 3}, timeout=15, trust_env=False)
        d = r.json()
        check(
            "weather/三亚: 预报+评分",
            r.status_code == 200 and len(d.get("daily", [])) == 3 and d.get("overall_score") is not None,
            f"score={d.get('overall_score')}",
        )
    except Exception as e:
        check("weather/三亚: 预报+评分", False, str(e))

    try:
        r = httpx.post(
            f"{BASE}/recommend/quick",
            json={"city": "三亚", "tags": ["海滩"], "budget": "适中", "travel_month": 0, "top_k": 5},
            timeout=30,
            trust_env=False,
        )
        d = r.json()
        places = d.get("places", [])
        nameless = [p for p in places if not p.get("name")]
        check(
            "recommend/quick: RAG 推荐（0 token）",
            r.status_code == 200 and len(places) >= 3 and not nameless,
            f"{len(places)} places, top={places[0]['name'] if places else '?'}",
        )
    except Exception as e:
        check("recommend/quick: RAG 推荐（0 token）", False, str(e))

    if args.with_vision:
        try:
            import base64
            import io
            from PIL import Image

            img = Image.new("RGB", (64, 64), (70, 130, 180))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            r = httpx.post(
                f"{BASE}/image/analyze",
                files={"image": ("smoke.png", buf.getvalue(), "image/png")},
                timeout=90,
                trust_env=False,
            )
            d = r.json()
            check(
                "image/analyze: Kimi 视觉",
                r.status_code == 200 and isinstance(d.get("tags"), list),
                f"tags={d.get('tags')}",
            )
        except Exception as e:
            check("image/analyze: Kimi 视觉", False, str(e))

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n===== 冒烟: {passed}/{len(RESULTS)} 通过 =====")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

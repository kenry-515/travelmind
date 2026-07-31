"""
Gap Analysis - What are we missing? (Fixed version)
Correctly initializes RAG before calling retrieve.
"""
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Step 0: Initialize RAG FIRST!
from app.rag import init_rag_from_data

DATA_FILE = BACKEND_DIR / "data" / "attractions.json"
TAGS_FILE = BACKEND_DIR / "data" / "tags.json"

rag_ok = init_rag_from_data(DATA_FILE, TAGS_FILE)
print(f"RAG initialization: {'✅ OK' if rag_ok else '❌ FAILED'}")


async def diagnose_rag():
    """Diagnose RAG retrieval quality."""
    from app.rag.retriever import retrieve

    test_queries = [
        # Common user patterns
        {"destination": "成都", "preferences": ["亲子", "熊猫"], "query": "成都亲子熊猫游"},
        {"destination": "北京", "preferences": ["历史", "儿童"], "query": "北京带孩子历史文化"},
        {"destination": "上海", "preferences": ["迪士尼", "购物"], "query": "上海迪士尼购物"},
        {"destination": "丽江", "preferences": ["浪漫", "慢节奏"], "query": "丽江浪漫休闲"},
        {"destination": "厦门", "preferences": ["海边", "文艺"], "query": "厦门鼓浪屿文艺"},
        {"destination": "重庆", "preferences": ["火锅", "小吃"], "query": "重庆火锅美食"},
        {"destination": "广州", "preferences": ["早茶", "粤菜"], "query": "广州美食早茶"},
        # Non-KB city
        {"destination": "玉溪", "preferences": ["抚仙湖"], "query": "玉溪抚仙湖"},
        {"destination": "张家界", "preferences": ["自然风光", "玻璃栈道"], "query": "张家界奇峰玻璃栈道"},
        # Cultural/historical
        {"destination": "拉萨", "preferences": ["藏传佛教"], "query": "拉萨布达拉宫"},
        {"destination": "西安", "preferences": ["兵马俑", "历史"], "query": "西安兵马俑华清池"},
        # Just city + tag (most common pattern)
        {"destination": "杭州", "preferences": ["西湖", "乌镇"], "query": "杭州西湖乌镇"},
    ]

    print("\n" + "=" * 80)
    print("🔍 DIAGNOSIS 1: RAG Retrieval Quality")
    print("=" * 80)

    results_summary = []
    for test in test_queries:
        try:
            results = await retrieve(test, test["query"], top_k=8)
            dest = test["destination"]
            pref = test["preferences"]
            print(f"\n📝 {test['query']}")
            print(f"   Dest: {dest}, Prefs: {pref}")
            print(f"   Results: {len(results)}")

            matches_dest = 0
            matches_pref = 0
            for r in results:
                meta = r.get("metadata", {}) or {}
                r_dest = meta.get("city", "")
                # Tags in Chroma metadata are comma-separated strings
                raw_tags = meta.get("tags", "") or r.get("tags", []) or ""
                if isinstance(raw_tags, str):
                    r_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                else:
                    r_tags = list(raw_tags) if raw_tags else []
                r_tags_str = " ".join(r_tags)
                r_name = meta.get("name", "") or r.get("name", "")
                r_score = r.get("relevance_score", r.get("score", "?"))
                r_source = r.get("source", meta.get("source", "kb"))

                dest_match = (r_dest == dest) or (dest in r_dest)
                pref_match = any(p in r_tags_str for p in pref) or any(p in r_name for p in pref)

                if dest_match:
                    matches_dest += 1
                if pref_match:
                    matches_pref += 1

                print(f"     {'✅' if dest_match else '❌'}{'⭐' if pref_match else '·'} {r_name[:25]:<25} | city={r_dest:<6} | src={r_source} | score={r_score}")

            recall_dest = matches_dest / len(results) * 100 if results else 0
            recall_pref = matches_pref / len(results) * 100 if results else 0
            results_summary.append({
                "query": test["query"],
                "dest_recall": recall_dest,
                "pref_recall": recall_pref,
                "count": len(results),
            })
            empty_flag = "🔴 NO RESULTS" if len(results) == 0 else ""
            print(f"   📊 City: {matches_dest}/{len(results)} ({recall_dest:.0f}%), Pref: {matches_pref}/{len(results)} ({recall_pref:.0f}%) {empty_flag}")

        except Exception as e:
            print(f"\n❌ Query '{test['query']}' FAILED: {type(e).__name__}: {e}")
            results_summary.append({"query": test["query"], "error": str(e)})

    print("\n" + "=" * 80)
    print("📊 RAG Quality Summary")
    print("=" * 80)
    ok_results = [r for r in results_summary if "error" not in r]
    non_empty = [r for r in ok_results if r["count"] > 0]
    errors = sum(1 for r in results_summary if "error" in r)
    empty_count = sum(1 for r in ok_results if r["count"] == 0)

    avg_dest = sum(r["dest_recall"] for r in non_empty) / max(1, len(non_empty))
    avg_pref = sum(r["pref_recall"] for r in non_empty) / max(1, len(non_empty))

    print(f"  Queries with 0 results: {empty_count}/{len(results_summary)}  {'🔴 CRITICAL' if empty_count > 3 else '🟡' if empty_count > 0 else '✅'}")
    print(f"  Avg city recall (non-empty): {avg_dest:.1f}%  {'🔴' if avg_dest < 80 else '🟡' if avg_dest < 90 else '✅'}")
    print(f"  Avg pref recall (non-empty): {avg_pref:.1f}%  {'🔴' if avg_pref < 50 else '🟡' if avg_pref < 70 else '✅'}")
    print(f"  Errors: {errors}")
    if empty_count > 0 or errors > 0:
        print(f"\n  🔴 PROBLEM QUERIES:")
        for r in results_summary:
            if "error" in r:
                print(f"    ❌ {r['query']}: ERROR")
            elif r["count"] == 0:
                print(f"    ⚠️  {r['query']}: 0 results returned")
            elif r["dest_recall"] < 70 or r["pref_recall"] < 40:
                print(f"    ⚠️  {r['query']}: dest={r['dest_recall']:.0f}%, pref={r['pref_recall']:.0f}%")


def diagnose_runtime_quality():
    """Diagnosis 2: Runtime-discovered POI quality."""
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSIS 2: Runtime-Discovered POI Quality")
    print("=" * 80)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    attractions = data.get("attractions", [])

    runtime_pois = [a for a in attractions if a.get("source") in ("runtime_bing", "wikipedia")]
    kb_pois = [a for a in attractions if a.get("source") not in ("runtime_bing", "wikipedia")]

    print(f"\n  Runtime-discovered: {len(runtime_pois)}")
    print(f"  KB: {len(kb_pois)}")

    # Quality heuristics
    suspicious_names = []
    fake_food = []  # restaurants that are actually generic terms not a real restaurant
    fake_hotel = []
    for p in runtime_pois:
        name = p.get("name", "")
        category = p.get("category", "")
        tags = " ".join(p.get("tags", []) or [])

        # Suspicious patterns - movie/book/album/tv show titles, generic concepts
        fake_indicators = [
            "与我们的夏天", "电影", "电视剧", "专辑", "歌曲", "小说", "散文", "诗集",
            "冶铁遗址", "古人类", "化石", "遗址", "文化", "历史", "传说", "战役",
        ]
        if (len(name) < 3 or any(x in name for x in fake_indicators)) and "遗址" not in tags and "博物馆" not in name:
            suspicious_names.append((name, p.get("city", ""), category))

        # Restaurants with generic names (dish names not restaurant names)
        if category == "restaurants":
            # Dishes: 浆面条、肉臊、过桥米线 etc are DISH names not RESTAURANT names
            dish_indicators = ["面", "饺", "粥", "粉", "饭", "条", "酱", "汤", "肉", "丝", "饼", "鸡", "鱼", "烧", "炖", "糕"]
            if (len(name) <= 4 and any(x in name for x in dish_indicators) and not any(x in name for x in ["店", "楼", "馆", "记", "坊", "街", "铺"])):
                fake_food.append((name, p.get("city", "")))

        # Hotels with suspicious names
        if category == "hotels":
            if len(name) <= 2 or "酒店" not in name and "宾馆" not in name and "旅馆" not in name and "客栈" not in name and "民宿" not in name:
                fake_hotel.append((name, p.get("city", "")))

    print(f"\n  Suspicious names (movie/book/generic): {len(suspicious_names)}")
    if suspicious_names:
        print(f"  ❌ Examples:")
        for n, c, cat in suspicious_names[:10]:
            print(f"     {n} ({c}) [{cat}]")

    print(f"\n  Fake restaurants (dish names, not real eateries): {len(fake_food)}")
    if fake_food:
        print(f"  ❌ Examples:")
        for n, c in fake_food[:10]:
            print(f"     {n} ({c}) - THIS IS A DISH, NOT A RESTAURANT")

    print(f"\n  Fake hotels (not hotel names): {len(fake_hotel)}")
    if fake_hotel:
        print(f"  ❌ Examples:")
        for n, c in fake_hotel[:10]:
            print(f"     {n} ({c})")

    # Rating gap
    runtime_ratings = [p.get("internal_rating", 0) for p in runtime_pois]
    kb_ratings = [p.get("internal_rating", 0) for p in kb_pois]
    avg_runtime = sum(runtime_ratings) / len(runtime_ratings) if runtime_ratings else 0
    avg_kb = sum(kb_ratings) / len(kb_ratings) if kb_ratings else 0

    print(f"\n  Avg rating: Runtime={avg_runtime:.2f}, KB={avg_kb:.2f}, Gap={avg_kb-avg_runtime:.2f}")
    if avg_kb - avg_runtime > 0.8:
        print(f"  🔴 RATING GAP: Runtime POIs have significantly lower ratings.")
        print(f"     When sorted by rating, runtime data is buried below KB.")
        print(f"     Hybrid architecture effectively DOESN'T USE runtime data!")

    runtime_high = sum(1 for p in runtime_pois if p.get("data_quality", {}).get("reliability") == "high")
    kb_high = sum(1 for p in kb_pois if p.get("data_quality", {}).get("reliability") == "high")
    print(f"  High reliability - Runtime: {runtime_high}/{len(runtime_pois)} ({runtime_high/len(runtime_pois)*100:.1f}%), KB: {kb_high}/{len(kb_pois)} ({kb_high/len(kb_pois)*100:.1f}%)")

    return len(suspicious_names) + len(fake_food) + len(fake_hotel)


def diagnose_duplicates_ambiguity():
    """Diagnosis 3: Duplicates and name ambiguity."""
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSIS 3: Duplicates & Name Ambiguity")
    print("=" * 80)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    attractions = data.get("attractions", [])
    from collections import defaultdict

    # Exact duplicates
    seen = {}
    duplicates = []
    for i, a in enumerate(attractions):
        key = (a.get("name", ""), a.get("city", ""))
        if key in seen:
            duplicates.append((i, seen[key], a.get("name", ""), a.get("city", "")))
        else:
            seen[key] = i
    print(f"\n  Exact duplicates (name+city): {len(duplicates)}  {'✅' if len(duplicates) == 0 else '🔴'}")

    # Ambiguity
    name_map = defaultdict(set)
    for a in attractions:
        name_map[a.get("name", "")].add(a.get("city", ""))

    ambiguous = {n: list(cs) for n, cs in name_map.items() if len(cs) >= 2 and len(n) > 0}

    # Classify ambiguous names: legit (common names) vs suspicious
    legit_names = ["故宫", "西湖", "东湖", "中山公园", "人民公园", "鼓楼", "钟楼", "文庙", "城隍庙", "清真寺",
                   "动物园", "植物园", "图书馆", "博物馆", "白云山", "天鹅湖", "荷花池"]
    legit_ambiguous = {}
    suspicious_ambiguous = {}
    for n, cs in ambiguous.items():
        if any(legit in n for legit in legit_names) or len(cs) <= 2:
            legit_ambiguous[n] = cs
        else:
            suspicious_ambiguous[n] = cs

    print(f"  Ambiguous names (>=2 cities): {len(ambiguous)}")
    print(f"    Legit (common names / only 2 cities): {len(legit_ambiguous)}")
    print(f"    Suspicious (>2 cities, not common name): {len(suspicious_ambiguous)}")
    if suspicious_ambiguous:
        print(f"  🔴 Top suspicious:")
        for n, cs in list(suspicious_ambiguous.items())[:10]:
            print(f"     {n}: {cs}")

    # Chain names (Manner, 锦江之星, 如家, etc are CHAINS with 100s of locations - different POIs are valid)
    chain_count = sum(1 for n in suspicious_ambiguous if any(x in n for x in ["Manner", "锦江", "如家", "7天", "汉庭", "沃尔玛", "无印", "百盛", "国美", "新世界", "星巴克", "瑞幸"]))
    if chain_count > 0:
        print(f"  ℹ️  {chain_count} are actually CHAIN STORES (different locations = valid POIs, just same name)")


async def diagnose_hybrid_workflow():
    """Diagnosis 4: Hybrid workflow for non-KB cities."""
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSIS 4: Hybrid Workflow - Non-KB Cities")
    print("=" * 80)

    from app.services.runtime_poi_service import get_hybrid_poi_pool, is_city_in_kb

    test_cases = [
        # City in KB (should have good data)
        ("成都", True, ["火锅", "熊猫"]),
        # Recently added via runtime (is_in_kb=True now)
        ("张家界", True, ["玻璃栈道", "奇峰"]),
        ("洛阳", True, ["牡丹", "龙门"]),
        # NOT in KB
        ("玉溪", False, ["抚仙湖", "度假"]),
        ("岳阳", True, ["岳阳楼", "洞庭湖"]),
    ]

    issues = 0
    for city, expect_kb, keywords in test_cases:
        in_kb = is_city_in_kb(city)
        expect_str = "KB" if expect_kb else "Non-KB"
        kb_status = "⚠️ MISMATCH" if in_kb != expect_kb else ""
        print(f"\n  🏙️  {city} [{expect_str}] - in_kb={in_kb}{kb_status}")

        result = await get_hybrid_poi_pool(
            city,
            categories=["attractions", "restaurants", "hotels"],
            limit_per_category=5,
        )

        for cat in ["attractions", "restaurants", "hotels"]:
            cat_data = result.get(cat, {})
            items = cat_data.get("items", [])
            links = cat_data.get("search_links", [])
            kb_count = sum(1 for i in items if i.get("source") == "kb")
            rt_count = len(items) - kb_count
            only_fallback = (len(items) == 0 and len(links) > 0)

            status = "⚠️" if only_fallback else "🟡" if len(items) < 3 else ""
            print(f"    {cat}: {len(items)} POIs (KB={kb_count}, RT={rt_count}), {len(links)} links {status}")

            if items:
                # Check if any item has rating - missing rating means it won't sort well
                ratings = [i.get("internal_rating") for i in items if i.get("internal_rating")]
                no_rating = len(items) - len(ratings)
                if no_rating > 0:
                    print(f"      ⚠️  {no_rating}/{len(items)} items MISSING internal_rating - won't sort properly!")
                    issues += 1

                # Check keyword relevance
                kw_matches = 0
                for i in items:
                    text = (i.get("name", "") + " " + " ".join(i.get("tags", []) or []) + " " + i.get("description", ""))
                    if any(kw in text for kw in keywords):
                        kw_matches += 1
                if len(items) > 0 and kw_matches / len(items) < 0.4:
                    print(f"      ⚠️  Low keyword relevance: only {kw_matches}/{len(items)} match {keywords}")
                    issues += 1

            if only_fallback:
                print(f"      🔴 NO POIs - only links! User must self-service search on 携程/飞猪.")
                issues += 1
            elif len(items) < 3:
                print(f"      🟡 Only {len(items)} POIs - not enough for trip planning (need 5+)")
                issues += 1

    if issues > 0:
        print(f"\n  🔴 {issues} total issues in hybrid workflow.")
    return issues


async def diagnose_price_quality():
    """Diagnosis 5: Price impact on planning quality."""
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSIS 5: Price Quality & Planning Impact")
    print("=" * 80)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    attractions = data.get("attractions", [])

    total = len(attractions)
    verified = sum(1 for a in attractions if a.get("price_verifiable"))
    free = sum(1 for a in attractions if a.get("price_level") == "免费")
    unknown = sum(1 for a in attractions if a.get("price_level") == "未知")
    paid_unverified = total - verified - free - unknown

    print(f"\n  Total: {total}")
    print(f"  Verified price: {verified} ({verified/total*100:.1f}%)")
    print(f"  Free: {free} ({free/total*100:.1f}%)")
    print(f"  Paid unverified: {paid_unverified} ({paid_unverified/total*100:.1f}%)")
    print(f"  Unknown: {unknown} ({unknown/total*100:.1f}%)")

    # Impact: itinerary planner can't compute budget
    print(f"\n  🔴 Impact: ~{90 - verified}% items have NO VERIFIABLE PRICE")
    print(f"     → Itinerary budget estimate = wrong guess (uses generic price_level)")
    print(f"     → User can't check: '门票XX元是否正确？'")
    print(f"     → Differentiating 10元 vs 200元 attractions = IMPOSSIBLE without price")


async def main():
    await diagnose_rag()
    bad_runtime_count = diagnose_runtime_quality()
    diagnose_duplicates_ambiguity()
    hybrid_issues = await diagnose_hybrid_workflow()
    await diagnose_price_quality()

    print("\n" + "=" * 80)
    print("🎯 CRITICAL ISSUES SUMMARY")
    print("=" * 80)

    print("\n  Let's see what these diagnostics revealed...")


if __name__ == "__main__":
    asyncio.run(main())

"""
Deep diagnosis of 7 failing gap_analysis queries.
Clears cache first, then runs retrieve with detailed output.
"""
import sys, asyncio, json
from pathlib import Path
sys.path.insert(0, '.')

from app.rag import init_rag_from_data
from app.services.cache_service import reset_cache

# Clear all caches
reset_cache()
print("✓ Cache cleared")

ok = init_rag_from_data(Path('data/attractions.json'), Path('data/tags.json'))
print(f"✓ RAG initialized: {ok}")

from app.rag.retriever import retrieve

# The 7 failing queries from gap_analysis
failed_queries = [
    {"destination": "北京", "tags": ["历史", "儿童"], "query": "北京带孩子历史文化"},
    {"destination": "丽江", "tags": ["浪漫", "慢节奏"], "query": "丽江浪漫休闲"},
    {"destination": "重庆", "tags": ["火锅", "小吃"], "query": "重庆火锅美食"},
    {"destination": "广州", "tags": ["早茶", "粤菜"], "query": "广州美食早茶"},
    {"destination": "张家界", "tags": ["自然风光", "玻璃栈道"], "query": "张家界奇峰玻璃栈道"},
    {"destination": "拉萨", "tags": ["藏传佛教"], "query": "拉萨布达拉宫"},
    {"destination": "杭州", "tags": ["西湖", "乌镇"], "query": "杭州西湖乌镇"},
]

async def diagnose():
    for t in failed_queries:
        print(f"\n{'='*80}")
        print(f"QUERY: {t['query']}")
        print(f"  Dest: {t['destination']}, Prefs: {t['tags']}")
        print(f"{'='*80}")

        results = await retrieve(
            user_profile={"destination": t["destination"], "tags": t["tags"]},
            query=t["query"],
            top_k=10,
        )

        if not results:
            print("  ❌ NO RESULTS AT ALL")
            continue

        # Analyze each result
        pref_hit_count = 0
        for i, r in enumerate(results):
            meta = r.get("metadata", {})
            name = meta.get("name", "?")
            city = meta.get("city", "?")
            tags_str = meta.get("tags", "")
            tags_list = [x.strip() for x in tags_str.split(",") if x.strip()] if tags_str else []
            desc = (meta.get("description", "") or "")[:100]
            score = r.get("relevance_score", 0)
            breakdown = r.get("_score_breakdown", {})

            # Check which preferences matched (using expanded tags like production code)
            from app.rag.retriever import _expand_tags
            expanded_prefs = _expand_tags(t["tags"])
            matched_prefs = []
            for pref in expanded_prefs:
                if pref.lower() in tags_str.lower():
                    matched_prefs.append(f"tag:{pref}")
                elif pref.lower() in name.lower():
                    matched_prefs.append(f"name:{pref}")
                elif pref.lower() in desc.lower():
                    matched_prefs.append(f"desc:{pref}")

            is_pref_match = len(matched_prefs) > 0
            if is_pref_match:
                pref_hit_count += 1

            # Show top 5 with full breakdown
            if i < 5:
                flag = "⭐" if is_pref_match else "·"
                print(f"  {flag} [{score:.3f}] {name} ({city})")
                print(f"     tags: {tags_str[:80]}")
                if matched_prefs:
                    print(f"     MATCHES: {matched_prefs}")
                print(f"     sim={breakdown.get('similarity',0):.3f} tag={breakdown.get('tag_match',0):.3f} kw={breakdown.get('keyword_hit',0):.3f} pop={breakdown.get('popularity',0):.3f}")
                if desc:
                    print(f"     desc: {desc}...")

        pref_rate = pref_hit_count / len(results) * 100
        print(f"\n  PREF RECALL: {pref_hit_count}/{len(results)} ({pref_rate:.0f}%)")

        # Check if KB has relevant data for this city
        with open('data/attractions.json', 'r', encoding='utf-8') as f:
            kb = json.load(f)
        city_pois = [a for a in kb.get("attractions", []) if a.get("city") == t["destination"]]

        # Search for prefs in city's POIs
        city_tags_all = set()
        city_names = set()
        for a in city_pois:
            for tag in (a.get("tags") or []):
                city_tags_all.add(tag)
            city_names.add(a.get("name", ""))

        print(f"  KB has {len(city_pois)} POIs in {t['destination']}")
        print(f"  KB tags containing prefs: ", end="")
        for pref in t["tags"]:
            matching_tags = [tag for tag in city_tags_all if pref.lower() in tag.lower()]
            matching_names = [n for n in city_names if pref.lower() in n.lower()]
            print(f"\n    '{pref}': tags={matching_tags[:5]}, name_contains={matching_names[:3]}", end="")
        print()

asyncio.run(diagnose())

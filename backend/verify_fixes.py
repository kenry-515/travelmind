"""Quick verification of tag loading and RAG initialization."""
import sys
sys.path.insert(0, '.')

# Test 1: Tag loading from tags.json
print("=" * 60)
print("🔍 Test 1: 标签动态加载")
print("=" * 60)

from app.agents.profile_agent import VALID_TAGS

print(f"  加载的有效标签数: {len(VALID_TAGS)}")
print(f"  前10个标签: {list(VALID_TAGS)[:10]}...")

# Check previously missing tags
test_tags = ['文化', '海滩', '海边', '历史', '火锅', '小吃', '登山']
for tag in test_tags:
    if tag in VALID_TAGS:
        print(f"  ✅ '{tag}' - 有效")
    else:
        print(f"  ❌ '{tag}' - 无效（将被移除）")

# Test 2: RAG initialization
print("\n" + "=" * 60)
print("🔍 Test 2: RAG 初始化")
print("=" * 60)

from pathlib import Path
from app.rag import init_rag_from_data

attractions_path = Path(__file__).parent / "data" / "attractions.json"
rag_ok = init_rag_from_data(attractions_path)

print(f"  RAG 初始化: {'✅ 成功' if rag_ok else '❌ 失败'}")

if rag_ok:
    # Test RAG retrieval (async)
    import asyncio
    from app.rag.retriever import retrieve
    
    async def test_rag():
        test_profile = {
            "destination": "成都",
            "tags": ["美食", "火锅", "小吃"],
            "budget_level": "舒适",
            "travel_style": "休闲",
            "travel_month": 7
        }
        
        results = await retrieve(test_profile, top_k=5)
        print(f"\n  RAG 检索测试 (成都 美食/火锅/小吃):")
        for i, r in enumerate(results[:5]):
            print(f"    {i+1}. {r.get('name', 'N/A')} (score: {r.get('score', 0):.3f})")
        
        # Check if new POIs are in results
        new_pois = ['宽窄巷子', '锦里古街', '武侯祠博物馆', '都江堰水利工程']
        result_names = [r.get('name', '') for r in results]
        print(f"\n  新增 POI 命中检查:")
        for poi in new_pois:
            if any(poi in name for name in result_names):
                print(f"    ✅ {poi} - 已被 RAG 召回")
            else:
                print(f"    ⚠️  {poi} - 未在 Top 5 中出现")
    
    asyncio.run(test_rag())

print("\n" + "=" * 60)
print("✅ 验证完成")
print("=" * 60)

"""Verify new POI retrieval after knowledge base rebuild."""
import sys
sys.path.insert(0, '.')

from pathlib import Path
import asyncio

# Initialize RAG properly
attractions_path = Path("data/attractions.json")
from app.rag import init_rag_from_data
success = init_rag_from_data(attractions_path)
print(f"RAG 初始化: {'✅ 成功' if success else '❌ 失败'}")

# Test retrieval
from app.rag.retriever import retrieve

async def test():
    # Test 1: 成都美食 - should now include new POIs
    test_profile = {
        "destination": "成都",
        "tags": ["美食", "火锅", "小吃"],
        "budget_level": "舒适",
        "travel_style": "休闲",
        "travel_month": 7
    }
    
    results = await retrieve(test_profile, top_k=10)
    print(f"\n🍜 成都 美食/火锅/小吃 Top 10:")
    for i, r in enumerate(results[:10]):
        name = r.get('metadata', {}).get('name', r.get('name', 'N/A'))
        print(f"    {i+1}. {name} (score: {r.get('score', r.get('relevance_score', 0)):.3f})")
    
    # Check new POIs
    new_pois = ['宽窄巷子', '锦里古街', '武侯祠博物馆', '都江堰水利工程', '春熙路']
    result_names = [r.get('metadata', {}).get('name', '') for r in results]
    print(f"\n  新增标志性 POI 检查:")
    for poi in new_pois:
        if any(poi in name for name in result_names):
            print(f"    ✅ {poi} - 已被 RAG 召回")
        else:
            print(f"    ⚠️  {poi} - 未在 Top 10 中出现")
    
    # Test 2: 北京历史 - should include new POIs
    test_profile2 = {
        "destination": "北京",
        "tags": ["历史", "文化", "博物馆"],
        "budget_level": "舒适",
        "travel_style": "深度",
        "travel_month": 7
    }
    
    results2 = await retrieve(test_profile2, top_k=5)
    print(f"\n🏯 北京 历史/文化/博物馆 Top 5:")
    for i, r in enumerate(results2[:5]):
        name = r.get('metadata', {}).get('name', r.get('name', 'N/A'))
        print(f"    {i+1}. {name} (score: {r.get('score', r.get('relevance_score', 0)):.3f})")
    
    # Check new Beijing POIs
    bj_pois = ['颐和园', '南锣鼓巷', '北京国子监']
    result_names2 = [r.get('metadata', {}).get('name', '') for r in results2]
    print(f"\n  北京新增 POI 检查:")
    for poi in bj_pois:
        if any(poi in name for name in result_names2):
            print(f"    ✅ {poi} - 已被 RAG 召回")
        else:
            print(f"    ⚠️  {poi} - 未在 Top 5 中出现")

asyncio.run(test())

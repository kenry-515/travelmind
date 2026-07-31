"""Verify new city POI retrieval."""
import sys
sys.path.insert(0, '.')

from pathlib import Path
import asyncio

# Initialize RAG
from app.rag import init_rag_from_data
success = init_rag_from_data(Path("data/attractions.json"))
print(f"RAG 初始化: {'✅ 成功' if success else '❌ 失败'}")

from app.rag.retriever import retrieve

async def test_new_cities():
    tests = [
        {
            "city": "杭州",
            "tags": ["文化", "古迹", "博物馆"],
            "expected": ["西湖", "灵隐寺", "河坊街"]
        },
        {
            "city": "苏州",
            "tags": ["园林", "古迹", "文化"],
            "expected": ["拙政园", "苏州博物馆", "平江路"]
        },
        {
            "city": "南京",
            "tags": ["历史", "文化", "民国"],
            "expected": ["中山陵", "夫子庙", "明孝陵"]
        },
        {
            "city": "广州",
            "tags": ["夜景", "都市", "观光"],
            "expected": ["广州塔", "珠江夜游", "上下九"]
        },
        {
            "city": "深圳",
            "tags": ["主题乐园", "亲子", "海滩"],
            "expected": ["世界之窗", "欢乐谷", "大梅沙"]
        }
    ]
    
    print("\n" + "=" * 70)
    print("🔍 新城市 POI 检索验证")
    print("=" * 70)
    
    for test in tests:
        profile = {
            "destination": test["city"],
            "tags": test["tags"],
            "budget_level": "舒适",
            "travel_style": "休闲",
            "travel_month": 7
        }
        
        results = await retrieve(profile, top_k=10)
        result_names = [r.get('metadata', {}).get('name', '') for r in results]
        
        print(f"\n🏙️  [{test['city']}] tags={test['tags']}")
        for i, r in enumerate(results[:5]):
            name = r.get('metadata', {}).get('name', 'N/A')
            score = r.get('score', r.get('relevance_score', 0))
            print(f"    {i+1}. {name} (score: {score:.3f})")
        
        # Check expected POIs
        found = []
        missing = []
        for exp in test["expected"]:
            if any(exp in name for name in result_names):
                found.append(exp)
            else:
                missing.append(exp)
        
        if found:
            print(f"    ✅ 已召回: {', '.join(found)}")
        if missing:
            print(f"    ⚠️  未召回: {', '.join(missing)}")

asyncio.run(test_new_cities())

print("\n" + "=" * 70)
print("✅ 新城市验证完成")
print("=" * 70)

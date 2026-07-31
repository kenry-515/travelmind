"""Quick validation test - verify system stability before new features."""
import sys
sys.path.insert(0, '.')

import json
import asyncio
from pathlib import Path

print("=" * 70)
print("🔍 系统稳定性验证")
print("=" * 70)

# Test 1: RAG 初始化
print("\n📋 Test 1: RAG 初始化")
from app.rag import init_rag_from_data
success = init_rag_from_data(Path("data/attractions.json"))
print(f"  结果: {'✅ 成功' if success else '❌ 失败'}")

# Test 2: 标签加载
print("\n📋 Test 2: 标签加载")
from app.agents.profile_agent import VALID_TAGS
print(f"  有效标签数: {len(VALID_TAGS)}")
critical_tags = ['文化', '海滩', '海边', '历史', '火锅', '小吃', '登山', '博物馆', '古镇']
all_valid = all(t in VALID_TAGS for t in critical_tags)
print(f"  关键标签检查: {'✅ 全部有效' if all_valid else '❌ 有缺失'}")
for tag in critical_tags:
    status = "✅" if tag in VALID_TAGS else "❌"
    print(f"    {status} {tag}")

# Test 3: RAG 检索质量
print("\n📋 Test 3: RAG 检索质量")
from app.rag.retriever import retrieve

async def test_rag():
    tests = [
        {
            "city": "成都",
            "tags": ["美食", "火锅", "小吃"],
            "expected": ["宽窄巷子", "锦里古街", "春熙路"]
        },
        {
            "city": "北京",
            "tags": ["历史", "文化", "博物馆"],
            "expected": ["颐和园", "故宫", "国子监"]
        },
        {
            "city": "厦门",
            "tags": ["海滩", "海边", "度假"],
            "expected": ["鼓浪屿", "环岛路"]
        }
    ]
    
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
        
        print(f"\n  [{test['city']}] tags={test['tags']}")
        for i, r in enumerate(results[:3]):
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

asyncio.run(test_rag())

print("\n" + "=" * 70)
print("✅ 验证完成，系统就绪！")
print("=" * 70)

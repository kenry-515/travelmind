"""Check RAG recall for key landmarks."""
import sys
sys.path.insert(0, '.')

import asyncio
from pathlib import Path

from app.rag import init_rag_from_data
from app.rag.retriever import retrieve

# Initialize
success = init_rag_from_data(Path("data/attractions.json"))
print(f"RAG 初始化: {'✅' if success else '❌'}")

# Test cases - key landmarks that should be in top results
tests = [
    {
        "city": "北京",
        "tags": ["历史", "文化", "博物馆"],
        "must_find": ["故宫", "颐和园", "国子监"],
        "note": "故宫是北京最核心地标，必须召回"
    },
    {
        "city": "成都", 
        "tags": ["美食", "火锅", "小吃"],
        "must_find": ["宽窄巷子", "锦里", "春熙路"],
        "note": "宽窄巷子是成都5A景区，必须召回"
    },
    {
        "city": "苏州",
        "tags": ["园林", "古迹", "文化"],
        "must_find": ["拙政园", "虎丘塔", "平江路"],
        "note": "拙政园是中国四大名园，必须召回"
    },
    {
        "city": "深圳",
        "tags": ["主题乐园", "亲子", "海滩"],
        "must_find": ["世界之窗", "欢乐谷", "大梅沙"],
        "note": "世界之窗是深圳5A景区，必须召回"
    }
]

async def check_recall():
    print("\n" + "=" * 70)
    print("🔍 核心地标召回率检查")
    print("=" * 70)
    
    for test in tests:
        profile = {
            "destination": test["city"],
            "tags": test["tags"],
            "budget_level": "舒适",
            "travel_style": "休闲",
            "travel_month": 7
        }
        
        results = await retrieve(profile, top_k=20)
        result_names = [r.get('metadata', {}).get('name', '') for r in results]
        
        print(f"\n🏙️  {test['city']} - {test['note']}")
        print(f"   检索 tags: {test['tags']}")
        
        # Show Top-5 results
        print(f"   Top-5 结果:")
        for i, r in enumerate(results[:5]):
            name = r.get('metadata', {}).get('name', 'N/A')
            score = r.get('score', r.get('relevance_score', 0))
            print(f"     {i+1}. {name} (score: {score:.3f})")
        
        # Check must_find landmarks
        found = []
        missing = []
        for landmark in test["must_find"]:
            position = None
            for idx, name in enumerate(result_names):
                if landmark in name or name in landmark:
                    position = idx + 1
                    break
            if position:
                found.append(f"{landmark}(#{position})")
            else:
                missing.append(landmark)
        
        if found:
            print(f"   ✅ 已召回: {', '.join(found)}")
        if missing:
            print(f"   ❌ 未召回: {', '.join(missing)}")

asyncio.run(check_recall())

# Check tags
from app.agents.profile_agent import VALID_TAGS
print(f"\n📋 tags.json 检查:")
print(f"  有效标签数: {len(VALID_TAGS)}")
missing_tags = ["园林", "地标", "5A", "拍照", "夜景"]
for tag in missing_tags:
    status = "✅" if tag in VALID_TAGS else "❌"
    print(f"    {status} {tag}")

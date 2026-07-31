"""
直接测试retrieve函数的城市过滤
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

import asyncio
import json
from pathlib import Path

async def test_retrieve():
    from app.rag import init_rag_from_data
    from app.rag.retriever import retrieve
    
    # 初始化
    data_dir = Path(__file__).resolve().parent.parent / "data"
    init_rag_from_data(str(data_dir / "attractions.json"))
    
    print("="*60)
    print("测试retrieve函数")
    print("="*60)
    
    # 测试1: 北京
    print("\n1. retrieve(北京, 亲子家庭):")
    user_profile = {
        "destination": "北京",
        "tags": ["亲子", "家庭"],
        "budget_level": "中等",
        "days": 3,
        "travel_style": "休闲",
        "companions": "带娃家庭",
        "constraints": [],
    }
    
    results = await retrieve(user_profile, query="北京 亲子 家庭", top_k=5)
    print(f"  结果数: {len(results)}")
    cities = set()
    for r in results:
        city = r.get("metadata", {}).get("city", "") or r.get("city", "")
        name = r.get("metadata", {}).get("name", "") or r.get("name", "")
        score = r.get("relevance_score", 0)
        cities.add(city)
        print(f"  - {name} ({city}) score={score:.3f}")
    print(f"  返回城市: {cities}")
    
    # 测试2: 上海
    print("\n2. retrieve(上海, 美食):")
    user_profile2 = {
        "destination": "上海",
        "tags": ["美食", "小吃"],
        "budget_level": "中等",
        "days": 3,
        "travel_style": "休闲",
        "companions": "闺蜜",
        "constraints": [],
    }
    
    results2 = await retrieve(user_profile2, query="上海 美食 小吃", top_k=5)
    print(f"  结果数: {len(results2)}")
    cities2 = set()
    for r in results2:
        city = r.get("metadata", {}).get("city", "") or r.get("city", "")
        name = r.get("metadata", {}).get("name", "") or r.get("name", "")
        score = r.get("relevance_score", 0)
        cities2.add(city)
        print(f"  - {name} ({city}) score={score:.3f}")
    print(f"  返回城市: {cities2}")
    
    # 测试3: 检查原始Chroma结果 vs 重排序结果
    print("\n3. 检查metadata结构:")
    if results:
        r0 = results[0]
        print(f"  键: {list(r0.keys())}")
        meta = r0.get("metadata", {})
        print(f"  metadata.city: {meta.get('city', 'N/A')}")
        print(f"  metadata.name: {meta.get('name', 'N/A')}")
        print(f"  city (top level): {r0.get('city', 'N/A')}")
        print(f"  name (top level): {r0.get('name', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(test_retrieve())
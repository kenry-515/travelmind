"""
直接测试Chroma城市过滤
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

import asyncio
import json
from pathlib import Path

async def test_chroma_filter():
    from app.rag import init_rag_from_data
    from app.rag.embedding import get_embedding_provider
    from app.rag.vector_store import get_vector_store
    
    # 初始化
    data_dir = Path(__file__).resolve().parent.parent / "data"
    init_rag_from_data(str(data_dir / "attractions.json"))
    
    store = get_vector_store()
    provider = get_embedding_provider()
    
    print("="*60)
    print("测试Chroma城市过滤")
    print("="*60)
    
    # 测试1: 不带过滤的搜索
    print("\n1. 无过滤搜索 (query='北京家庭亲子'):")
    query_vec = provider.embed_query("北京 家庭 亲子")
    results_no_filter = store.search(query_vec, top_k=5)
    cities_no_filter = set()
    for r in results_no_filter:
        city = r.get("metadata", {}).get("city", "")
        name = r.get("metadata", {}).get("name", "")
        cities_no_filter.add(city)
        print(f"  - {name} ({city})")
    print(f"  返回城市: {cities_no_filter}")
    
    # 测试2: 带过滤的搜索
    print("\n2. 带过滤搜索 (where={'city': '北京'}):")
    results_with_filter = store.search(query_vec, top_k=5, where={"city": "北京"})
    cities_with_filter = set()
    for r in results_with_filter:
        city = r.get("metadata", {}).get("city", "")
        name = r.get("metadata", {}).get("name", "")
        cities_with_filter.add(city)
        print(f"  - {name} ({city})")
    print(f"  返回城市: {cities_with_filter}")
    
    # 测试3: 检查Chroma中实际存储的城市元数据
    print("\n3. 检查Chroma中的城市元数据 (直接get):")
    beijing_data = store._collection.get(where={"city": "北京"}, limit=5)
    if beijing_data and beijing_data.get("metadatas"):
        for i, meta in enumerate(beijing_data["metadatas"][:3]):
            print(f"  [{i}] name={meta.get('name', '')}, city='{meta.get('city', '')}'")
            print(f"      city字段类型: {type(meta.get('city', ''))}")
    else:
        print("  无数据")
    
    # 测试4: 检查"上海"过滤
    print("\n4. 带过滤搜索 (where={'city': '上海'}):")
    query_vec2 = provider.embed_query("上海 美食 小吃")
    results_sh = store.search(query_vec2, top_k=5, where={"city": "上海"})
    cities_sh = set()
    for r in results_sh:
        city = r.get("metadata", {}).get("city", "")
        name = r.get("metadata", {}).get("name", "")
        cities_sh.add(city)
        print(f"  - {name} ({city})")
    print(f"  返回城市: {cities_sh}")
    
    print("\n" + "="*60)
    print("结论:")
    if cities_with_filter == {"北京"}:
        print("  ✓ Chroma城市过滤正常工作")
    else:
        print(f"  ✗ Chroma过滤失效！返回了: {cities_with_filter}")
        print("  可能原因:")
        print("    1. 元数据中的city字段格式不匹配")
        print("    2. Chroma版本问题")
        print("    3. 索引未重建")

if __name__ == "__main__":
    asyncio.run(test_chroma_filter())
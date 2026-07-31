"""Rebuild Chroma index with correct embedding dimensions."""
import sys
sys.path.insert(0, '.')

import json
import shutil
from pathlib import Path

# Step 1: Clear existing Chroma data (correct path)
chroma_dir = Path("chroma_data")
if chroma_dir.exists():
    print(f"🗑️  清除旧 Chroma 数据: {chroma_dir}")
    shutil.rmtree(chroma_dir)
    print("   ✅ 已清除")
else:
    print("ℹ️  无旧 Chroma 数据需要清除")

# Also try alternative paths
alt_paths = [
    Path("data/chroma_db"),
    Path("backend/chroma_data"),
    Path.home() / ".chroma"
]
for p in alt_paths:
    if p.exists():
        print(f"🗑️  发现额外 Chroma 数据: {p}")
        shutil.rmtree(p)

# Step 2: Re-initialize RAG
print("\n🔧 重新初始化 RAG 系统...")
from app.rag import init_rag_from_data

attractions_path = Path("data/attractions.json")
success = init_rag_from_data(attractions_path)

if success:
    print("✅ RAG 重建成功！")
    
    # Step 3: Verify with a test query
    print("\n🔍 验证 RAG 检索...")
    import asyncio
    from app.rag.retriever import retrieve
    
    async def test():
        # Test with new POIs
        test_profile = {
            "destination": "成都",
            "tags": ["美食", "火锅", "小吃"],
            "budget_level": "舒适",
            "travel_style": "休闲",
            "travel_month": 7
        }
        
        results = await retrieve(test_profile, top_k=10)
        print(f"\n  成都 美食/火锅/小吃 Top 10:")
        for i, r in enumerate(results[:10]):
            print(f"    {i+1}. {r.get('name', 'N/A')} (score: {r.get('score', 0):.3f})")
        
        # Check new POIs
        new_pois = ['宽窄巷子', '锦里古街', '武侯祠博物馆', '都江堰水利工程', '春熙路']
        result_names = [r.get('name', '') for r in results]
        print(f"\n  新增标志性 POI 检查:")
        for poi in new_pois:
            if any(poi in name for name in result_names):
                print(f"    ✅ {poi} - 已被 RAG 召回")
            else:
                print(f"    ⚠️  {poi} - 未在 Top 10 中出现")
    
    asyncio.run(test())
else:
    print("❌ RAG 重建失败")

"""Debug RAG retrieval issue."""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from app.rag import init_rag_from_data
from app.rag.vector_store import get_vector_store
import asyncio

# Initialize
attractions_path = Path("data/attractions.json")
success = init_rag_from_data(attractions_path)

print(f"RAG 初始化: {'成功' if success else '失败'}")

# Check vector store
store = get_vector_store()
print(f"\nChroma 存储状态:")
print(f"  连接状态: {store.is_connected}")

if store.is_connected:
    count = store._collection.count()
    print(f"  文档数量: {count}")
    
    # Get a sample to verify data
    try:
        results = store._collection.peek(limit=3)
        print(f"  样本数据:")
        for i, (doc_id, doc, meta) in enumerate(zip(
            results['ids'][:3], 
            results['documents'][:3], 
            results['metadatas'][:3]
        )):
            print(f"    [{i}] ID: {doc_id[:30]}...")
            print(f"        文档: {doc[:80]}...")
            print(f"        城市: {meta.get('city', 'N/A')}")
    except Exception as e:
        print(f"  读取样本失败: {e}")

# Test raw search
print(f"\n🔍 直接 Chroma 检索测试:")
try:
    from app.rag.embedding import get_embedding_provider
    
    provider = get_embedding_provider()
    query = "成都 美食 火锅 小吃"
    
    # Get embeddings
    query_embedding = provider.embed(query)
    print(f"  查询向量维度: {len(query_embedding)}")
    
    # Search
    results = store._collection.query(
        query_embeddings=[query_embedding],
        n_results=10,
        where={"city": "成都"}
    )
    
    print(f"  检索结果数: {len(results['ids'][0])}")
    for i, (id, doc, distance) in enumerate(zip(
        results['ids'][0][:5],
        results['documents'][0][:5],
        results['distances'][0][:5] if 'distances' in results else []
    )):
        print(f"    {i+1}. {doc[:60]}... (distance: {distance:.3f})")
        
except Exception as e:
    print(f"  检索错误: {e}")
    import traceback
    traceback.print_exc()

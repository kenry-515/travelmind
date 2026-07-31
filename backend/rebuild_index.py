"""Rebuild Chroma vector index for attractions."""
import sys
sys.path.insert(0, '.')

from app.rag.retriever import AttractionRetriever
import json

# Load attractions
with open('data/attractions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

attractions = data['attractions']

print(f"📊 准备重新构建索引，共 {len(attractions)} 个景点...")

# Initialize retriever
retriever = AttractionRetriever()

# Clear existing collection and rebuild
try:
    # Try to reset if collection exists
    retriever.collection = retriever.client.get_or_create_collection(
        name="attractions",
        metadata={"hnsw:space": "cosine"}
    )
except Exception as e:
    print(f"Warning: {e}")

# Add all attractions in batches
batch_size = 100
for i in range(0, len(attractions), batch_size):
    batch = attractions[i:i+batch_size]
    
    ids = []
    documents = []
    metadatas = []
    
    for a in batch:
        aid = a.get('amap_id') or a.get('wikidata_id') or f"poi_{hash(a['name'] + a['city'])}"
        ids.append(str(aid))
        
        # Create document with rich text for better embedding
        doc = f"{a['name']}。{a.get('description', '')}"
        documents.append(doc)
        
        # Metadata
        meta = {
            'name': a['name'],
            'city': a['city'],
            'tags': ','.join(a.get('tags', [])),
            'lat': a.get('lat', 0),
            'lon': a.get('lon', 0),
            'popularity_score': a.get('popularity_score', 0),
            'price_level': a.get('price_level', ''),
            'suitable_for': a.get('suitable_for', ''),
            'best_time': a.get('best_time', '')
        }
        metadatas.append(meta)
    
    # Add to Chroma
    retriever.collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    
    print(f"  已添加 {i+len(batch)} / {len(attractions)}")

print(f"\n✅ 索引重建完成！")
print(f"   总景点数: {retriever.collection.count()}")

# Quick test
test_queries = [
    ("北京", "历史 故宫 长城"),
    ("成都", "美食 火锅 小吃"),
    ("厦门", "海滩 海边 度假"),
]

for city, query in test_queries:
    results = retriever.search(query, city=city, top_k=3)
    print(f"\n🔍 测试查询: [{city}] {query}")
    for r in results:
        print(f"  - {r['name']} (score: {r['score']:.3f})")

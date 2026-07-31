"""RAG Quality Diagnostic - analyze why Top1 scores are low."""
import sys
import json
sys.path.insert(0, '.')

# Test queries and their expected results
test_queries = [
    {
        "query": "北京亲子历史文化游",
        "city": "北京",
        "tags": ["亲子", "历史", "文化", "博物馆", "古迹"],
        "expected_pois": ["颐和园", "故宫", "长城", "博物馆"],
    },
    {
        "query": "成都美食火锅之旅",
        "city": "成都",
        "tags": ["美食", "火锅", "小吃", "餐厅"],
        "expected_pois": ["宽窄巷子", "锦里", "火锅", "小吃"],
    },
    {
        "query": "西安历史文化游",
        "city": "西安",
        "tags": ["历史", "文化", "古迹", "博物馆"],
        "expected_pois": ["兵马俑", "大雁塔", "古城墙"],
    },
]

async def diagnose_rag():
    """Run RAG quality diagnosis."""
    from app.rag import init_rag_from_data
    from app.rag.retriever import retrieve
    from pathlib import Path
    
    # Initialize RAG
    print("🔧 初始化 RAG 系统...")
    try:
        data_path = Path(__file__).parent / "data" / "attractions.json"
        success = init_rag_from_data(data_path)
        if success:
            print("   ✅ RAG 已初始化")
        else:
            print("   ❌ RAG 初始化失败")
            return
    except Exception as e:
        print(f"   ❌ RAG 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("=" * 70)
    print("🔍 RAG 检索质量诊断")
    print("=" * 70)
    
    for test in test_queries:
        query = test["query"]
        city = test["city"]
        tags = test["tags"]
        expected = test["expected_pois"]
        
        print(f"\n📋 查询: {query} (城市: {city})")
        print(f"   标签: {tags}")
        print(f"   期望POI: {expected}")
        print("-" * 50)
        
        profile = {
            "tags": tags,
            "destination": city,
            "budget_level": "适中",
            "travel_style": "文化深度",
            "travel_month": 7,
        }
        
        try:
            results = await retrieve(profile, top_k=10)
        except Exception as e:
            print(f"   ❌ 检索失败: {e}")
            continue
        
        if not results:
            print(f"   ❌ 无结果")
            continue
        
        # Analyze results
        print(f"   找到 {len(results)} 条结果:\n")
        
        for i, item in enumerate(results[:10]):
            meta = item.get("metadata", {})
            score = item.get("relevance_score", 0)
            name = meta.get("name", item.get("document", "?")[:30])
            item_city = meta.get("city", "?")
            tags = meta.get("tags", "")
            
            # Check score breakdown
            breakdown = item.get("_score_breakdown", {})
            
            # Check if expected POI is in results
            is_expected = any(kw in name for kw in expected)
            
            marker = "⭐" if is_expected else "  "
            print(f"   {marker} #{i+1} | 得分: {score:.4f} | {name} ({item_city})")
            print(f"      标签: {tags[:60]}")
            if breakdown:
                sim = breakdown.get("similarity", 0)
                tag = breakdown.get("tag_match", 0)
                kw = breakdown.get("keyword_hit", 0)
                print(f"      分解: sim={sim:.3f} tag={tag:.3f} kw={kw:.3f}")
            print()
        
        # Calculate metrics
        top1_score = results[0].get("relevance_score", 0) if results else 0
        top5_expected = sum(1 for r in results[:5] 
                          if any(kw in r.get("metadata", {}).get("name", "") for kw in expected))
        
        print(f"   📊 指标:")
        print(f"      Top1 得分: {top1_score:.4f}")
        print(f"      Top5 期望POI: {top5_expected}/{len(expected)}")
        print(f"      Top1 名称: {results[0].get('metadata', {}).get('name', '?')}")
        
        # Identify issues
        issues = []
        if top1_score < 0.3:
            issues.append("Top1 得分过低 (<0.3)")
        if top5_expected < 2:
            issues.append("期望POI召回不足")
        if results[0].get("metadata", {}).get("city") != city:
            issues.append("Top1 城市不匹配")
        
        if issues:
            print(f"   ⚠️  问题: {', '.join(issues)}")
        else:
            print(f"   ✅ 质量良好")

if __name__ == "__main__":
    import asyncio
    asyncio.run(diagnose_rag())

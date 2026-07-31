"""Verify issues found by advisor - deep analysis of test output."""
import json
import sys
sys.path.insert(0, '.')

# Load the test results
with open('reports/comprehensive_test_results.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

print("=" * 70)
print("🔍 深度问题分析 - AdvisorTool 验证")
print("=" * 70)

# Issue 1: RAG initialization
print("\n⚠️  问题 1: RAG 初始化状态")
print("-" * 50)
print("日志显示: 'RAG not initialized: Embedding provider not initialized'")
print("影响: 新添加的 23 个 POI 数据可能未被实际使用")
print("需要检查 test_comprehensive.py 是否正确初始化了 RAG")

# Issue 2: 重复 POI 问题
print("\n⚠️  问题 2: 跨天重复 POI")
print("-" * 50)
# Let's check the actual itinerary for duplicates
import asyncio
from app.agents.orchestrator import run_travel_workflow

# Quick test for one city
async def check_duplicates():
    result = await run_travel_workflow("重庆4天网红打卡游")
    itinerary = result.get("itinerary", {})
    days = itinerary.get("days", [])
    
    all_pois = []
    seen_pois = {}
    duplicates = []
    
    for day in days:
        for item in day.get("items", []):
            poi = item.get("poi", "")
            if poi:
                day_num = day.get("day", "?")
                if poi in seen_pois:
                    duplicates.append({
                        "poi": poi,
                        "first_day": seen_pois[poi],
                        "duplicate_day": day_num
                    })
                else:
                    seen_pois[poi] = day_num
                all_pois.append(poi)
    
    print(f"\n  重庆行程重复检查:")
    print(f"    总 POI 数: {len(all_pois)}")
    print(f"    唯一 POI 数: {len(seen_pois)}")
    print(f"    重复 POI 数: {len(duplicates)}")
    
    if duplicates:
        for d in duplicates:
            print(f"      - {d['poi']}: Day {d['first_day']} 和 Day {d['duplicate_day']}")
    
    return duplicates

# Issue 3: Tag validation
print("\n⚠️  问题 3: 标签验证")
print("-" * 50)
print("日志显示: 'Removed unknown tags: {文化, 海滩}'")
print("影响: 用户偏好标签被丢弃，RAG 检索质量下降")

# Check tag vocabulary
with open('data/tags.json', 'r', encoding='utf-8') as f:
    tags_data = json.load(f)

allowed_tags = set(tags_data.get('allowed_tags', []))
missing_tags = ['文化', '海滩', '海边', '历史']
for tag in missing_tags:
    if tag in allowed_tags:
        print(f"  ✅ '{tag}' 存在于标签库")
    else:
        print(f"  ❌ '{tag}' 不在标签库中 - 需要添加!")

# Issue 4: Test assertion quality
print("\n⚠️  问题 4: 测试断言质量")
print("-" * 50)
print("同义词匹配过于宽松，可能掩盖真实问题")
print("建议: 精确匹配得满分，同义词匹配只得部分分")

# Run duplicate check
print("\n" + "=" * 70)
print("🔬 运行重复 POI 检测...")
print("=" * 70)

asyncio.run(check_duplicates())

print("\n" + "=" * 70)
print("📋 修复优先级建议")
print("=" * 70)
print("""
1. 🔴 紧急: 修复 RAG 初始化问题
   - 确保 test_comprehensive.py 调用 init_rag_from_data()
   - 验证新 POI 数据确实被向量索引包含

2. 🔴 紧急: 添加跨天去重逻辑
   - 在 planning_agent.py 中检查重复 POI
   - 标记或移除重复景点

3. 🟡 重要: 修复标签丢失
   - 在 tags.json 中补充缺失标签
   - 检查标签验证逻辑

4. 🟡 重要: 改进测试断言
   - 精确匹配 > 同义词匹配
   - 添加行程合理性检查
""")

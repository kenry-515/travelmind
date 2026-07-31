"""Test long itinerary stability - Lijiang 5 days."""
import sys
sys.path.insert(0, '.')

import json
import asyncio
from pathlib import Path

print("=" * 70)
print("🧪 长天数行程稳定性测试 - 丽江5天")
print("=" * 70)

# Initialize RAG
from app.rag import init_rag_from_data
success = init_rag_from_data(Path("data/attractions.json"))
print(f"RAG 初始化: {'✅ 成功' if success else '❌ 失败'}")

async def test_long_itinerary():
    from app.agents.orchestrator import run_travel_workflow
    
    user_input = "丽江5天深度游，喜欢历史文化和自然风光，预算适中"
    
    print(f"\n📋 测试场景: {user_input}")
    print("\n⏳ 生成行程中（长天数行程，使用增强稳定性模式）...")
    
    try:
        state = await run_travel_workflow(user_input)
        itinerary = state.get("itinerary", {})
        
        if itinerary:
            days = itinerary.get("days", [])
            print(f"\n✅ 行程生成成功！共 {len(days)} 天")
            
            for day in days:
                day_num = day.get("day", "?")
                theme = day.get("theme", "")
                items = day.get("items", [])
                print(f"\n  Day {day_num}: {theme}")
                print(f"    项目数: {len(items)}")
                
                # Check new fields
                has_time_slot = any(item.get("time_slot") for item in items)
                has_transport = any(item.get("transportation") for item in items)
                has_cost = any(item.get("estimated_cost") for item in items)
                
                print(f"    time_slot: {'✅' if has_time_slot else '⚠️'}")
                print(f"    transportation: {'✅' if has_transport else '⚠️'}")
                print(f"    estimated_cost: {'✅' if has_cost else '⚠️'}")
            
            # Save result
            output_path = Path("reports/long_itinerary_test.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(itinerary, f, ensure_ascii=False, indent=2)
            print(f"\n💾 完整结果已保存: {output_path}")
            
            return True
        else:
            print("\n❌ 行程生成失败")
            if state.get("error"):
                print(f"   错误: {state['error']}")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

success = asyncio.run(test_long_itinerary())

print(f"\n{'=' * 70}")
if success:
    print("✅ 长天数行程测试通过")
else:
    print("⚠️  长天数行程测试未通过（可能需要重试）")
print("=" * 70)

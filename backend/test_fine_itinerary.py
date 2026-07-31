"""Test fine itinerary generation with new fields."""
import sys
sys.path.insert(0, '.')

import json
import asyncio
from pathlib import Path

print("=" * 70)
print("🧪 精细行程生成测试")
print("=" * 70)

# Initialize RAG
from app.rag import init_rag_from_data
success = init_rag_from_data(Path("data/attractions.json"))
print(f"RAG 初始化: {'✅ 成功' if success else '❌ 失败'}")

async def test_fine_itinerary():
    """Test itinerary generation with new fine-grained fields."""
    from app.agents.orchestrator import run_travel_workflow
    
    # Test input (natural language)
    user_input = "杭州2天文化园林游，必须去西湖和灵隐寺，预算舒适型，情侣出行"
    
    print(f"\n📋 测试场景:")
    print(f"  输入: {user_input}")
    
    print("\n⏳ 生成行程中...")
    
    try:
        state = await run_travel_workflow(user_input)
        
        itinerary = state.get("itinerary", {})
        
        if itinerary:
            print("\n✅ 行程生成成功！")
            
            # Check new fields
            days = itinerary.get("days", [])
            print(f"\n📊 检查新增字段:")
            
            has_time_slot = False
            has_transportation = False
            has_estimated_cost = False
            total_items = 0
            
            for day in days:
                items = day.get("items", [])
                for item in items:
                    total_items += 1
                    if item.get("time_slot"):
                        has_time_slot = True
                    if item.get("transportation"):
                        has_transportation = True
                    if item.get("estimated_cost"):
                        has_estimated_cost = True
            
            print(f"  总项目数: {total_items}")
            print(f"  time_slot: {'✅ 已生成' if has_time_slot else '⚠️  未生成'}")
            print(f"  transportation: {'✅ 已生成' if has_transportation else '⚠️  未生成'}")
            print(f"  estimated_cost: {'✅ 已生成' if has_estimated_cost else '⚠️  未生成'}")
            
            # Show sample items with new fields
            print(f"\n📝 示例项目（含新字段）:")
            for day in days[:1]:  # Only show first day
                items = day.get("items", [])
                for item in items[:3]:  # Only show first 3 items
                    print(f"\n  [{item.get('time')}] {item.get('poi')}")
                    print(f"    note: {item.get('note', '')[:50]}")
                    if item.get("time_slot"):
                        print(f"    time_slot: {item['time_slot']}")
                    if item.get("transportation"):
                        print(f"    transportation: {item['transportation']}")
                    if item.get("estimated_cost"):
                        cost = item['estimated_cost']
                        print(f"    estimated_cost: ticket={cost.get('ticket')}, transport={cost.get('transport')}, total={cost.get('total')}")
            
            # Save result
            output_path = Path("reports/fine_itinerary_test.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(itinerary, f, ensure_ascii=False, indent=2)
            print(f"\n💾 完整结果已保存: {output_path}")
            
            return True
        else:
            print(f"\n❌ 行程生成失败: 未获取到行程数据")
            if state.get("error"):
                print(f"   错误信息: {state['error']}")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

# Run test
success = asyncio.run(test_fine_itinerary())

print(f"\n{'=' * 70}")
if success:
    print("✅ 精细行程测试完成")
else:
    print("⚠️  精细行程测试未通过（可能需要重试）")
print("=" * 70)

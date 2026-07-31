"""Quick test script to verify itinerary generation works correctly."""
import asyncio
import json
import sys
sys.path.insert(0, '.')

async def test_itinerary():
    """Test a real itinerary generation flow."""
    from app.agents.orchestrator import run_travel_workflow
    
    # Test case: 北京3天亲子游
    user_input = "我想带孩子去北京玩3天，喜欢历史文化，预算中等"
    
    print(f"🧪 测试输入: {user_input}")
    print("-" * 60)
    
    try:
        result = await run_travel_workflow(user_input)
        
        if result.get("error"):
            print(f"❌ 执行出错: {result['error']}")
            return
        
        # 检查行程
        itinerary = result.get("itinerary", {})
        if not itinerary:
            print("❌ 行程为空")
            return
        
        days = itinerary.get("days", [])
        print(f"📅 行程天数: {len(days)}")
        
        trip = itinerary.get("trip", {})
        print(f"🏷️ 行程标题: {trip.get('title', 'N/A')}")
        
        # 检查每天的POI数量
        total_items = 0
        for day in days:
            day_num = day.get("day", "?")
            items = day.get("items", [])
            attractions = [it for it in items if it.get("type") == "attraction" or it.get("poi")]
            total_items += len(attractions)
            print(f"  Day {day_num}: {len(items)} items ({len(attractions)} attractions)")
            
            # 显示前3个POI
            for it in attractions[:3]:
                poi_name = it.get("poi", "") or it.get("name", "")
                if poi_name:
                    print(f"    - {poi_name}")
        
        print(f"\n📊 统计:")
        print(f"  总景点数: {total_items}")
        print(f"  平均每天: {total_items/len(days):.1f} 个景点")
        
        # 检查餐厅推荐
        all_items = []
        for day in days:
            all_items.extend(day.get("items", []))
        
        restaurants = [it for it in all_items 
                      if it.get("type") in ["meal", "restaurant"] or
                      any(tag in str(it.get("tags", [])) for tag in ["美食", "餐厅"])]
        print(f"  餐厅/美食推荐: {len(restaurants)} 个")
        
        # 检查tips
        tips = itinerary.get("tips", [])
        print(f"  实用提示: {len(tips)} 条")
        for tip in tips[:2]:
            print(f"    - {tip}")
        
        # 检查checklist
        checklist = itinerary.get("checklist", [])
        print(f"  行李清单: {len(checklist)} 项")
        
        print("\n" + "=" * 60)
        
        # 判断是否成功
        success = (
            len(days) >= 2 and 
            total_items >= 4 and 
            all(len([it for it in d.get("items", []) if it.get("type") == "attraction" or it.get("poi")]) >= 2 for d in days)
        )
        
        if success:
            print("✅ 测试通过！行程生成质量良好。")
        else:
            print("⚠️  测试部分通过，仍有改进空间。")
            if any(len([it for it in d.get("items", []) if it.get("type") == "attraction" or it.get("poi")]) < 2 for d in days):
                print("   - 某些天数POI不足2个")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_itinerary())

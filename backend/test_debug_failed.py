"""Debug failed test cases."""
import sys
import asyncio
sys.path.insert(0, '.')

async def debug_test():
    from app.agents.orchestrator import run_travel_workflow
    
    # Test Chengdu
    print("=" * 60)
    print("🔍 测试: 成都4天美食之旅")
    print("=" * 60)
    
    try:
        result = await run_travel_workflow('成都4天美食之旅，喜欢吃火锅和小吃，预算中等')
        
        if result.get("error"):
            print(f"❌ 错误: {result['error']}")
            return
        
        itinerary = result.get('itinerary', {})
        days = itinerary.get('days', [])
        
        if not days:
            print("❌ 行程为空")
            return
        
        print(f"✅ 成功! 天数: {len(days)}")
        print()
        
        for day in days:
            day_num = day.get('day', '?')
            eat = day.get('eat', '')
            print(f"Day {day_num}:")
            if eat:
                print(f"  eat: {eat[:100]}...")
            
            items = day.get('items', [])
            for item in items:
                poi = item.get('poi', '') or item.get('name', '')
                item_type = item.get('type', '')
                note = item.get('note', '')
                print(f"  - {poi} (type={item_type})")
                if note:
                    print(f"    note: {note[:80]}...")
            print()
        
        # Check tips
        tips = itinerary.get('tips', [])
        if tips:
            print("Tips:")
            for tip in tips:
                print(f"  - {tip[:100]}...")
    
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_test())

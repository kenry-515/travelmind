"""Full integration test - test multiple scenarios via API."""
import asyncio
import sys
import json
sys.path.insert(0, '.')

test_cases = [
    {
        "name": "北京3天亲子游",
        "input": "我想带孩子去北京玩3天，喜欢历史文化，预算中等",
        "check": {"min_days": 3, "min_items_per_day": 2}
    },
    {
        "name": "成都4天美食之旅",
        "input": "成都4天美食之旅，喜欢吃火锅和小吃，预算中等",
        "check": {"min_days": 4, "min_items_per_day": 2}
    },
    {
        "name": "西安2天历史游",
        "input": "西安2天历史文化游，看兵马俑和古城墙",
        "check": {"min_days": 2, "min_items_per_day": 2}
    },
]

async def run_tests():
    from app.agents.orchestrator import run_travel_workflow
    
    results = []
    
    for case in test_cases:
        print(f"\n{'='*60}")
        print(f"🧪 测试: {case['name']}")
        print(f"   输入: {case['input']}")
        print("-" * 60)
        
        try:
            result = await run_travel_workflow(case['input'])
            
            if result.get("error"):
                print(f"❌ 失败: {result['error']}")
                results.append({"name": case['name'], "status": "FAILED", "error": result['error']})
                continue
            
            itinerary = result.get("itinerary", {})
            days = itinerary.get("days", [])
            trip = itinerary.get("trip", {})
            
            # Validate
            issues = []
            if len(days) < case['check']['min_days']:
                issues.append(f"天数不足: {len(days)} < {case['check']['min_days']}")
            
            for day in days:
                items = day.get("items", [])
                attractions = [it for it in items if it.get("type") == "attraction" or it.get("poi")]
                if len(attractions) < case['check']['min_items_per_day']:
                    issues.append(f"Day {day.get('day')} POI不足: {len(attractions)}")
            
            status = "PASSED" if not issues else "PARTIAL"
            
            print(f"📅 行程天数: {len(days)}")
            print(f"🏷️  标题: {trip.get('title', 'N/A')}")
            
            total_attractions = 0
            for day in days:
                items = day.get("items", [])
                attractions = [it for it in items if it.get("type") == "attraction" or it.get("poi")]
                total_attractions += len(attractions)
                # Show POI names
                poi_names = [it.get("poi", "") for it in items if it.get("poi")]
                print(f"   Day {day.get('day')}: {len(attractions)} 景点 - {', '.join(poi_names[:4])}")
            
            print(f"📊 总景点: {total_attractions}, 平均: {total_attractions/len(days):.1f}/天")
            
            if issues:
                print(f"⚠️  问题: {', '.join(issues)}")
            else:
                print(f"✅ 测试通过!")
            
            results.append({
                "name": case['name'],
                "status": status,
                "days": len(days),
                "total_attractions": total_attractions,
                "issues": issues
            })
            
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            results.append({"name": case['name'], "status": "ERROR", "error": str(e)})
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 测试汇总")
    print(f"{'='*60}")
    
    passed = sum(1 for r in results if r['status'] == 'PASSED')
    partial = sum(1 for r in results if r['status'] == 'PARTIAL')
    failed = sum(1 for r in results if r['status'] in ('FAILED', 'ERROR'))
    
    for r in results:
        icon = {"PASSED": "✅", "PARTIAL": "⚠️", "FAILED": "❌", "ERROR": "❌"}.get(r['status'], "❓")
        print(f"  {icon} {r['name']}: {r['status']}")
        if r.get('issues'):
            for issue in r['issues']:
                print(f"     - {issue}")
    
    print(f"\n通过率: {passed}/{len(results)} ({passed*100/len(results):.0f}%)")
    print(f"部分通过: {partial}")
    print(f"失败: {failed}")

if __name__ == "__main__":
    asyncio.run(run_tests())

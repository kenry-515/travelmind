"""Full scenario evaluation test with detailed reporting."""
import sys
import json
import time
import asyncio
sys.path.insert(0, '.')

# Phase 3.2: Keyword synonym map for must_have validation
# Maps user-facing keywords to related terms that may appear in POI names
_KEYWORD_SYNONYM_MAP = {
    "美食": ["美食", "火锅", "小吃", "餐厅", "酒楼", "菜馆", "饭店", "烧烤", "咖啡", "特色", "小吃", "吃"],
    "历史": ["历史", "博物馆", "古迹", "遗址", "古城", "古建筑", "文物", "兵马俑", "故宫", "长城", "城墙", "寺庙", "祠堂"],
    "购物": ["购物", "商场", "商业街", "步行街", "商圈", "商店", "购物中心", "购物", "逛街"],
    "海滩": ["海滩", "海边", "海滨", "沙滩", "海岛", "海岸", "海景", "环岛"],
    "海边": ["海边", "海滩", "海滨", "沙滩", "海岛", "海岸", "海景", "环岛"],
    "古镇": ["古镇", "古城", "古村", "古镇", "历史文化", "古街"],
    "火锅": ["火锅", "川菜", "麻辣", "串串", "汤锅"],
    "故宫": ["故宫", "紫禁城", "故宫博物院"],
    "博物馆": ["博物馆", "博物院", "纪念馆", "美术馆"],
    "兵马俑": ["兵马俑", "秦始皇", "秦陵"],
}

def _has_keyword_match(keyword: str, text: str) -> bool:
    """Check if a keyword or its synonyms appear in the text."""
    # Direct match first
    if keyword in text:
        return True
    # Check synonyms
    synonyms = _KEYWORD_SYNONYM_MAP.get(keyword, [])
    for syn in synonyms:
        if syn in text:
            return True
    return False

async def run_comprehensive_test():
    """Run comprehensive end-to-end test."""
    # Phase 4.5: Initialize RAG before testing to ensure POI data is used
    from pathlib import Path
    from app.rag import init_rag_from_data
    
    attractions_path = Path(__file__).parent / "data" / "attractions.json"
    print("🔧 初始化 RAG 系统...")
    rag_ok = init_rag_from_data(attractions_path)
    if rag_ok:
        print("✅ RAG 初始化成功")
    else:
        print("⚠️  RAG 初始化失败，行程将基于 LLM 自身知识生成")
    
    from app.agents.orchestrator import run_travel_workflow
    
    # Extended test cases
    test_cases = [
        {
            "name": "北京3天亲子历史游",
            "input": "我想带孩子去北京玩3天，喜欢历史文化，预算中等",
            "check": {"min_days": 3, "min_items_per_day": 2, "must_have": ["故宫", "博物馆"]}
        },
        {
            "name": "成都4天美食之旅",
            "input": "成都4天美食之旅，喜欢吃火锅和小吃，预算中等",
            "check": {"min_days": 4, "min_items_per_day": 2, "must_have": ["美食"]}
        },
        {
            "name": "西安2天历史游",
            "input": "西安2天历史文化游，看兵马俑和古城墙",
            "check": {"min_days": 2, "min_items_per_day": 2, "must_have": ["兵马俑", "历史"]}
        },
        {
            "name": "上海3天购物休闲游",
            "input": "上海3天购物休闲游，喜欢逛街和打卡",
            "check": {"min_days": 3, "min_items_per_day": 2, "must_have": ["购物"]}
        },
        {
            "name": "丽江5天深度游",
            "input": "丽江5天深度游，喜欢古镇和自然风光，预算中等",
            "check": {"min_days": 5, "min_items_per_day": 2, "must_have": ["古镇"]}
        },
        {
            "name": "厦门3天海边度假",
            "input": "厦门3天海边度假，喜欢海滩和美食",
            "check": {"min_days": 3, "min_items_per_day": 2, "must_have": ["海滩", "海边"]}
        },
        {
            "name": "重庆4天网红打卡游",
            "input": "重庆4天网红打卡游，喜欢拍照和火锅",
            "check": {"min_days": 4, "min_items_per_day": 2, "must_have": ["火锅"]}
        },
    ]
    
    results = {
        "summary": {
            "total": 0,
            "passed": 0,
            "partial": 0,
            "failed": 0,
        },
        "details": [],
        "quality_metrics": {
            "avg_days": 0,
            "avg_items_per_day": 0,
            "restaurant_coverage": 0,
            "tip_coverage": 0,
        }
    }
    
    print("=" * 80)
    print("🔍 TravelMind Agent - 综合质量测试")
    print("=" * 80)
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    total_items = 0
    total_days = 0
    restaurants_found = 0
    tips_found = 0
    
    for i, case in enumerate(test_cases):
        print(f"\n{'='*80}")
        print(f"[{i+1}/{len(test_cases)}] 📋 {case['name']}")
        print(f"   输入: {case['input']}")
        print("-" * 80)
        
        try:
            start_time = time.time()
            result = await run_travel_workflow(case['input'])
            elapsed = time.time() - start_time
            
            if result.get("error"):
                print(f"❌ 失败: {result['error']}")
                results["summary"]["failed"] += 1
                results["details"].append({
                    "name": case['name'],
                    "status": "FAILED",
                    "error": result['error'],
                    "time": f"{elapsed:.1f}s"
                })
                continue
            
            itinerary = result.get("itinerary", {})
            days = itinerary.get("days", [])
            trip = itinerary.get("trip", {})
            
            if not days:
                print(f"❌ 行程为空")
                results["summary"]["failed"] += 1
                results["details"].append({
                    "name": case['name'],
                    "status": "FAILED",
                    "error": "空行程",
                    "time": f"{elapsed:.1f}s"
                })
                continue
            
            # Validate
            issues = []
            if len(days) < case['check']['min_days']:
                issues.append(f"天数不足({len(days)} < {case['check']['min_days']})")
            
            days_items = []
            for day in days:
                items = day.get("items", [])
                # Count all items with poi name (valid items)
                valid_items = [it for it in items if it.get("poi")]
                days_items.append(len(valid_items))
                if len(valid_items) < case['check']['min_items_per_day']:
                    issues.append(f"Day {day.get('day')} POI不足({len(valid_items)} < {case['check']['min_items_per_day']})")
            
            # Check must_have keywords with tiered scoring
            all_poi_text = ""
            poi_names = []
            for day in days:
                for it in day.get("items", []):
                    poi = it.get("poi", "")
                    all_poi_text += poi + it.get("name", "") + " "
                    if poi:
                        poi_names.append(poi)
                day_note = day.get("note", "") or ""
                day_eat = day.get("eat", "") or ""
                all_poi_text += day_note + " " + day_eat + " "
            
            # Tiered scoring: exact match = full, synonym = partial
            keyword_scores = []
            missing_keywords = []
            for kw in case['check']['must_have']:
                # Check if keyword appears in POI NAMES (exact match)
                exact_match = any(kw in name for name in poi_names)
                # Check if keyword appears anywhere (including synonyms)
                any_match = _has_keyword_match(kw, all_poi_text)
                
                if exact_match:
                    keyword_scores.append((kw, 1.0, "exact"))  # Full credit
                elif any_match:
                    keyword_scores.append((kw, 0.5, "synonym"))  # Partial credit
                    # Only report as missing if no match at all
                else:
                    keyword_scores.append((kw, 0.0, "missing"))
                    missing_keywords.append(kw)
            
            # Calculate keyword coverage score
            if keyword_scores:
                coverage = sum(s for _, s, _ in keyword_scores) / len(keyword_scores)
                if coverage < 0.5:  # Less than half covered
                    if missing_keywords:
                        issues.append(f"缺少关键POI: {', '.join(missing_keywords)}")
                    # Also note if only synonyms matched
                    partial_matches = [k for k, s, t in keyword_scores if t == "synonym"]
                    if partial_matches:
                        issues.append(f"仅同义词匹配: {', '.join(partial_matches)}")
            
            # Count restaurants - using day.eat field and item content
            restaurant_count = 0
            
            # Method 1: Check day.eat fields
            for day in days:
                eat_text = day.get("eat", "")
                if eat_text and any(kw in eat_text for kw in ["餐", "吃", "火锅", "美食", "小吃", "餐厅"]):
                    restaurant_count += 1
            
            # Method 2: Check items for food-related POIs (keywords in name/note)
            food_keywords = ["餐", "火锅", "小吃", "美食", "餐厅", "酒楼", "菜馆",
                            "饭店", "烧烤", "咖啡", "酒吧", "甜点", "小吃", "吃"]
            for day in days:
                for item in day.get("items", []):
                    poi_name = item.get("poi", "") or ""
                    note = item.get("note", "") or ""
                    if any(kw in poi_name for kw in food_keywords):
                        restaurant_count += 1
            
            # Use max of both methods
            restaurant_items_count = max(restaurant_count, 0)
            
            # Count tips
            tips = itinerary.get("tips", [])
            
            # Check for duplicate POIs across days (new check)
            all_poi_days = {}
            duplicate_pois = []
            for day in days:
                day_num = day.get("day", "?")
                for item in day.get("items", []):
                    poi = item.get("poi", "")
                    if not poi:
                        continue
                    # Skip allowed duplicate types
                    tags_str = str(item.get("tags", ""))
                    if any(t in tags_str for t in ["火锅", "小吃", "美食", "餐厅", "酒店", "住宿", "民宿"]):
                        continue
                    
                    if poi in all_poi_days:
                        all_poi_days[poi].append(day_num)
                    else:
                        all_poi_days[poi] = [day_num]
            
            # Find actual duplicates
            for poi, day_list in all_poi_days.items():
                if len(day_list) > 1:
                    duplicate_pois.append(f"{poi}(Day{day_list[0]},{day_list[1]})")
            
            if duplicate_pois:
                issues.append(f"跨天重复POI: {len(duplicate_pois)}个 - {', '.join(duplicate_pois[:3])}")
            
            # Check for itinerary quality issues
            # 1. Day item count consistency
            items_per_day = [len([it for it in day.get("items", []) if it.get("poi")]) for day in days]
            if items_per_day and max(items_per_day) - min(items_per_day) > 3:
                issues.append(f"景点数量不均衡: 最多{max(items_per_day)} vs 最少{min(items_per_day)}")
            
            # 2. Check for extreme POI concentration (all items in one area)
            # Basic heuristic: if too many items contain the same location keyword
            location_groups = {}
            for day in days:
                for item in day.get("items", []):
                    poi = item.get("poi", "")
                    for area in ["外滩", "故宫", "西湖", "外滩", "南京路"]:
                        if area in poi:
                            location_groups[area] = location_groups.get(area, 0) + 1
            
            # 3. Check trip title quality
            title = trip.get("title", "")
            if not title or len(title) < 5:
                issues.append("行程标题过短或缺失")
            
            # Status
            if not issues:
                status = "PASSED"
                results["summary"]["passed"] += 1
            elif len(issues) <= 1:
                status = "PARTIAL"
                results["summary"]["partial"] += 1
            else:
                status = "FAILED"
                results["summary"]["failed"] += 1
            
            # Print results
            print(f"✅ 行程生成成功 ({elapsed:.1f}s)")
            print(f"📅 标题: {trip.get('title', 'N/A')}")
            print(f"📊 天数: {len(days)}")
            
            for day in days:
                valid_items = [it for it in day.get("items", []) if it.get("poi")]
                poi_names = [it.get("poi", "") for it in day.get("items", []) if it.get("poi")]
                print(f"   Day {day.get('day')}: {len(valid_items)} 景点 - {', '.join(poi_names[:4])}")
            
            print(f"🍜 餐厅/美食: {restaurant_items_count} 个")
            print(f"💡 实用提示: {len(tips)} 条")
            
            if issues:
                print(f"⚠️  问题: {'; '.join(issues)}")
            else:
                print(f"✅ 所有检查通过!")
            
            # Accumulate metrics
            total_days += len(days)
            total_items += sum(days_items)
            restaurants_found += restaurant_items_count
            tips_found += len(tips)
            
            results["details"].append({
                "name": case['name'],
                "status": status,
                "days": len(days),
                "items_per_day": days_items,
                "total_items": sum(days_items),
                "restaurants": restaurant_items_count,
                "tips": len(tips),
                "time": f"{elapsed:.1f}s",
                "issues": issues
            })
            
        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            results["summary"]["failed"] += 1
            results["details"].append({
                "name": case['name'],
                "status": "ERROR",
                "error": str(e)
            })
    
    # Calculate final metrics
    n = len(test_cases)
    results["summary"]["total"] = n
    
    if total_days > 0:
        results["quality_metrics"]["avg_days"] = round(total_days / n, 1)
        results["quality_metrics"]["avg_items_per_day"] = round(total_items / total_days, 1)
    
    results["quality_metrics"]["restaurant_coverage"] = round(restaurants_found / n, 1)
    results["quality_metrics"]["tip_coverage"] = round(tips_found / n, 1)
    
    # Print final summary
    print(f"\n{'='*80}")
    print("📊 综合测试结果")
    print("=" * 80)
    
    s = results["summary"]
    total = s["total"]
    
    print(f"\n📈 通过情况:")
    print(f"   ✅ 完全通过: {s['passed']}/{total} ({s['passed']*100/total:.0f}%)")
    print(f"   ⚠️  部分通过: {s['partial']}/{total}")
    print(f"   ❌ 失败: {s['failed']}/{total}")
    
    qm = results["quality_metrics"]
    print(f"\n📊 质量指标:")
    print(f"   平均行程天数: {qm['avg_days']} 天")
    print(f"   平均每天景点: {qm['avg_items_per_day']} 个")
    print(f"   平均餐厅覆盖: {qm['restaurant_coverage']} 个/行程")
    print(f"   平均提示数量: {qm['tip_coverage']} 条/行程")
    
    # Print detail table
    print(f"\n📋 详细结果:")
    print(f"{'─'*80}")
    print(f"{'测试场景':<20} {'状态':<10} {'天数':<6} {'景点':<6} {'餐厅':<6} {'耗时':<8} {'问题'}")
    print(f"{'─'*80}")
    
    for d in results["details"]:
        status_icon = {"PASSED": "✅", "PARTIAL": "⚠️", "FAILED": "❌", "ERROR": "❌"}.get(d['status'], "❓")
        issues_str = "; ".join(d.get('issues', [d.get('error', '')]) or [])
        days_str = str(d.get('days', '-'))
        items_str = str(d.get('total_items', '-'))
        rest_str = str(d.get('restaurants', '-'))
        time_str = d.get('time', '-')
        
        print(f"{d['name']:<18} {status_icon} {d['status']:<8} {days_str:<6} {items_str:<6} {rest_str:<6} {time_str:<8} {issues_str[:30]}")
    
    print(f"{'─'*80}")
    print(f"\n⏰ 结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Overall verdict
    pass_rate = s['passed'] * 100 / total if total > 0 else 0
    if pass_rate >= 90:
        verdict = "🏆 优秀 - 可以进入下一阶段优化"
    elif pass_rate >= 70:
        verdict = "👍 良好 - 需要继续改进"
    else:
        verdict = "⚠️ 需改进 - 核心问题尚未解决"
    
    print(f"\n{verdict}")
    
    # Save results
    output_file = "reports/comprehensive_test_results.json"
    import os
    os.makedirs("reports", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📄 详细报告已保存: {output_file}")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_test())

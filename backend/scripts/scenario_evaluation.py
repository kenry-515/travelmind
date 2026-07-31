"""
TravelMindAgent 生产级质量诊断框架
=====================================

核心思路：用 20 个真实用户场景端到端测试，从结果倒推差距。
不是组件级测试，而是用户视角的"这个行程我愿意用吗？"

使用方法：
  python scripts/scenario_evaluation.py

输出：
  1. 每个场景的评分 (0-100)
  2. 影响质量的 Top 5 问题
  3. 优先级修复建议
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 真实用户场景定义 ──

@dataclass
class Scenario:
    """真实用户场景"""
    id: str
    city: str
    days: int
    purpose: str          # 旅行目的
    style: str            # 旅行风格
    budget: str           # 预算
    group: str            # 同行人
    season: str           # 季节
    expected_pois: List[str] = field(default_factory=list)  # 期望出现的POI
    min_restaurants: int = 2  # 最少需要的餐厅数
    min_hotels: int = 1      # 最少需要的酒店数

# 20个覆盖不同维度的真实场景
SCENARIOS = [
    # ── 热门城市 · 经典场景 ──
    Scenario("BJ_FAMILY_3D", "北京", 3, "亲子游", "休闲", "中等", "带娃家庭", "春季",
             expected_pois=["故宫", "长城", "动物园", "颐和园", "天坛"],
             min_restaurants=3, min_hotels=2),
    
    Scenario("CD_COUPLE_4D", "成都", 4, "情侣旅行", "休闲", "中等", "情侣", "秋季",
             expected_pois=["大熊猫基地", "宽窄巷子", "锦里", "都江堰"],
             min_restaurants=4, min_hotels=2),
    
    Scenario("XA_HISTORY_3D", "西安", 3, "历史文化", "深度", "经济", "背包客", "春季",
             expected_pois=["兵马俑", "大雁塔", "华清池", "回民街"],
             min_restaurants=3, min_hotels=1),
    
    Scenario("SH_FOODIE_3D", "上海", 3, "美食探索", "休闲", "奢华", "闺蜜", "全年",
             expected_pois=["外滩", "豫园", "田子坊"],
             min_restaurants=5, min_hotels=2),
    
    # ── 热门城市 · 特殊场景 ──
    Scenario("CQ_HOTPOT_3D", "重庆", 3, "火锅美食", "休闲", "经济", "朋友", "秋季",
             expected_pois=["洪崖洞", "解放碑", "磁器口"],
             min_restaurants=5, min_hotels=1),
    
    Scenario("GZ_MOTHER_5D", "广州", 5, "带父母", "休闲", "中等", "家庭", "冬季",
             expected_pois=["陈家祠", "沙面", "长隆"],
             min_restaurants=6, min_hotels=2),
    
    # ── 自然风景 · 热门 ──
    Scenario("ZJJ_MOUNTAIN_3D", "张家界", 3, "自然风光", "徒步", "经济", "背包客", "秋季",
             expected_pois=["天门山", "玻璃栈道", "金鞭溪"],
             min_restaurants=2, min_hotels=2),
    
    Scenario("LSK_NATURE_4D", "九寨沟", 4, "自然风光", "休闲", "中等", "情侣", "秋季",
             expected_pois=["九寨沟", "黄龙", "藏寨"],
             min_restaurants=2, min_hotels=2),
    
    # ── 小众城市 · 冷启动测试 ──
    Scenario("ZY_UNKNOWN_2D", "遵义", 2, "红色旅游", "深度", "经济", "独行", "春季",
             expected_pois=["遵义会议会址", "赤水"],
             min_restaurants=1, min_hotels=1),
    
    Scenario("NN_UNKNOWN_3D", "南宁", 3, "休闲度假", "休闲", "中等", "家庭", "冬季",
             expected_pois=["青秀山", "德天瀑布"],
             min_restaurants=2, min_hotels=1),
    
    # ── 特殊人群 ──
    Scenario("DL_ELDERLY_5D", "大理", 5, "带老人", "休闲", "中等", "家庭", "春季",
             expected_pois=["洱海", "苍山", "古城"],
             min_restaurants=4, min_hotels=2),
    
    Scenario("SC_WEDDING_7D", "三亚", 7, "蜜月旅行", "度假", "奢华", "情侣", "冬季",
             expected_pois=["亚龙湾", "蜈支洲岛", "天涯海角"],
             min_restaurants=5, min_hotels=3),
    
    # ── 文化深度游 ──
    Scenario("LZ_BUDDHISM_5D", "拉萨", 5, "藏传佛教", "深度", "中等", "独行", "夏季",
             expected_pois=["布达拉宫", "大昭寺", "纳木错"],
             min_restaurants=2, min_hotels=2),
    
    Scenario("HZ_ANCIENT_3D", "杭州", 3, "古镇文化", "休闲", "中等", "朋友", "春季",
             expected_pois=["西湖", "乌镇", "灵隐寺"],
             min_restaurants=4, min_hotels=1),
    
    # ── 美食专项 ──
    Scenario("KM_FOOD_3D", "昆明", 3, "云南美食", "休闲", "经济", "闺蜜", "全年",
             expected_pois=["滇池", "石林", "民族村"],
             min_restaurants=3, min_hotels=1),
    
    Scenario("CS_FOOD_2D", "长沙", 2, "湘菜美食", "休闲", "经济", "朋友", "秋季",
             expected_pois=["橘子洲", "岳麓山"],
             min_restaurants=4, min_hotels=1),
    
    # ── 周边短途 ──
    Scenario("NB_WEEKEND_2D", "宁波", 2, "周末休闲", "休闲", "经济", "家庭", "春季",
             expected_pois=["天一阁", "老外滩"],
             min_restaurants=2, min_hotels=1),
    
    Scenario("FX_WEEKEND_2D", "福州", 2, "周末休闲", "休闲", "经济", "独行", "秋季",
             expected_pois=["三坊七巷", "鼓山"],
             min_restaurants=2, min_hotels=1),
    
    # ── 高难度场景 ──
    Scenario("SH_MUSEUM_4D", "上海", 4, "博物馆深度游", "深度", "中等", "独行", "全年",
             expected_pois=["故宫博物院", "上海博物馆", "科技馆"],
             min_restaurants=3, min_hotels=2),
    
    Scenario("CD_CHILD_4D", "成都", 4, "带娃科普", "休闲", "中等", "家庭", "春季",
             expected_pois=["熊猫基地", "科技馆", "海洋馆"],
             min_restaurants=3, min_hotels=2),
]


class ScenarioEvaluator:
    """场景评估器"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self._rag_initialized = False
        self._planner_initialized = False
    
    async def initialize(self):
        """初始化所有服务"""
        if self._rag_initialized:
            return
        
        print("🔄 初始化系统...")
        
        # 初始化RAG
        from app.rag import init_rag_from_data
        
        data_dir = Path(__file__).resolve().parent.parent / "data"
        success = init_rag_from_data(str(data_dir / "attractions.json"))
        if not success:
            raise RuntimeError("RAG初始化失败")
        self._rag_initialized = True
        
        # 获取retrieve函数
        from app.rag.retriever import retrieve
        self._retrieve = retrieve
        
        print("  ✓ RAG 初始化完成")
    
    async def evaluate_scenario(self, scenario: Scenario) -> Dict[str, Any]:
        """评估单个场景"""
        result = {
            "id": scenario.id,
            "city": scenario.city,
            "days": scenario.days,
            "total_score": 0,
            "dimensions": {},
            "issues": [],
            "recommendations_preview": [],
            "itinerary_preview": None,
        }
        
        try:
            # ── Step 1: 构建用户画像 ──
            profile = self._build_profile(scenario)
            
            # ── Step 2: RAG 推荐 ──
            query = self._build_query(scenario)
            
            # 构建user_profile
            user_profile = {
                "destination": scenario.city,
                "tags": scenario.expected_pois[:3],
                "budget_level": scenario.budget,
                "days": scenario.days,
                "travel_style": scenario.style,
                "companions": scenario.group,
                "constraints": [],
            }
            
            rag_results = await self._retrieve(
                user_profile=user_profile,
                query=query,
                top_k=30,
            )
            
            # ── Step 3: 评估推荐质量 ──
            rag_score, rag_issues = self._evaluate_rag(rag_results, scenario)
            result["dimensions"]["rag_quality"] = rag_score
            result["recommendations_preview"] = [
                {"name": (r.get("metadata", {}).get("name", "") or r.get("name", "")), 
                 "score": r.get("relevance_score", 0)}
                for r in rag_results[:5]
            ]
            result["issues"].extend(rag_issues)
            
            # ── Step 4: 行程生成 (如果有LLM key) ──
            if self._has_llm():
                itinerary = await self._generate_itinerary(profile, rag_results)
                if itinerary:
                    itin_score, itin_issues = self._evaluate_itinerary(itinerary, scenario)
                    result["dimensions"]["itinerary_quality"] = itin_score
                    result["itinerary_preview"] = self._summarize_itinerary(itinerary)
                    result["issues"].extend(itin_issues)
                else:
                    result["dimensions"]["itinerary_quality"] = 0
                    result["issues"].append("行程生成失败")
            else:
                result["dimensions"]["itinerary_quality"] = 50  # 占位分
                result["issues"].append("跳过行程评估 (无LLM key)")
            
            # ── Step 5: 数据覆盖度评估 ──
            coverage_score, coverage_issues = self._evaluate_coverage(scenario)
            result["dimensions"]["data_coverage"] = coverage_score
            result["issues"].extend(coverage_issues)
            
            # ── 总分计算 ──
            dims = result["dimensions"]
            result["total_score"] = round(
                dims.get("rag_quality", 0) * 0.4 +
                dims.get("itinerary_quality", 0) * 0.3 +
                dims.get("data_coverage", 0) * 0.3,
                1
            )
            
        except Exception as e:
            result["issues"].append(f"评估异常: {str(e)}")
            result["total_score"] = 0
        
        return result
    
    def _build_profile(self, scenario: Scenario) -> Dict[str, Any]:
        """构建用户画像"""
        return {
            "destination": scenario.city,
            "days": scenario.days,
            "travel_style": scenario.style,
            "budget_level": scenario.budget,
            "group": scenario.group,
            "season": scenario.season,
            "purpose": scenario.purpose,
            "preferred_tags": scenario.expected_pois[:3],
        }
    
    def _build_query(self, scenario: Scenario) -> str:
        """构建查询"""
        keywords = "、".join(scenario.expected_pois[:3])
        return f"{scenario.city}{scenario.purpose} {keywords}"
    
    def _evaluate_rag(self, results: List[Dict], scenario: Scenario) -> tuple:
        """评估RAG推荐质量
        
        注意: retrieve()返回的结果结构是:
        {
            "id": "...",
            "document": "...",
            "metadata": {"city": "...", "name": "...", "tags": "...", ...},
            "score": 0.85,
            "relevance_score": 0.75,
            "_score_breakdown": {...}
        }
        城市和名称在metadata里，不在顶层。
        """
        score = 100
        issues = []
        
        if not results:
            return 0, ["RAG返回空结果"]
        
        # 辅助函数：安全获取字段
        def get_city(r):
            meta = r.get("metadata", {})
            return meta.get("city", "") or r.get("city", "")
        
        def get_name(r):
            meta = r.get("metadata", {})
            return meta.get("name", "") or r.get("name", "")
        
        def get_tags(r):
            meta = r.get("metadata", {})
            return meta.get("tags", "") or r.get("tags", "")
        
        # 检查1: 是否全部是目标城市
        non_city = [r for r in results if get_city(r) != scenario.city]
        if non_city:
            penalty = len(non_city) / len(results) * 40
            score -= penalty
            issues.append(f"{len(non_city)}个非{scenario.city}的结果")
        
        # 检查2: 是否包含期望的POI
        result_names = [get_name(r) for r in results]
        matched_expected = [p for p in scenario.expected_pois 
                          if any(p in name for name in result_names)]
        match_rate = len(matched_expected) / len(scenario.expected_pois) if scenario.expected_pois else 1.0
        score -= (1 - match_rate) * 30
        if match_rate < 0.5:
            issues.append(f"仅{len(matched_expected)}/{len(scenario.expected_pois)}个期望POI被推荐")
        
        # 检查3: 评分分布是否合理
        top_score = results[0].get("relevance_score", 0) if results else 0
        if top_score < 0.3:
            score -= 20
            issues.append(f"Top1评分过低 ({top_score:.2f})")
        
        # 检查4: 是否有餐厅/酒店
        restaurant_count = sum(1 for r in results 
                            if "餐厅" in get_tags(r) or "美食" in get_tags(r) or "restaurant" in get_tags(r).lower())
        hotel_count = sum(1 for r in results 
                        if "酒店" in get_tags(r) or "hotel" in get_tags(r).lower())
        
        if restaurant_count < scenario.min_restaurants:
            score -= 10
            issues.append(f"餐厅推荐不足: {restaurant_count} < {scenario.min_restaurants}")
        
        return max(0, min(100, score)), issues
    
    def _evaluate_itinerary(self, itinerary: Dict, scenario: Scenario) -> tuple:
        """评估行程质量"""
        score = 100
        issues = []
        
        if not itinerary:
            return 0, ["行程为空"]
        
        days = itinerary.get("days", [])
        if len(days) < scenario.days:
            score -= 30
            issues.append(f"行程天数不足: {len(days)} < {scenario.days}")
        
        # Check if trip exists
        if not itinerary.get("trip"):
            score -= 20
            issues.append("行程缺少trip信息")
        
        # Check daily POI count (using items, not pois)
        for i, day in enumerate(days):
            items = day.get("items", [])
            # Count only attraction items (not transport, meals, etc.)
            visit_items = [it for it in items if it.get("type") == "attraction" or it.get("poi")]
            if len(visit_items) < 2:
                score -= 5
                issues.append(f"第{i+1}天POI过少: {len(visit_items)}个")
        
        # Check for restaurant recommendations (check across all items)
        all_items = []
        for day in days:
            all_items.extend(day.get("items", []))
        
        # Restaurants are typically in items with type "meal" or tags containing "美食/餐厅"
        restaurant_count = sum(1 for it in all_items 
                            if it.get("type") in ["meal", "restaurant"] or 
                            any(tag in str(it.get("tags", [])) for tag in ["美食", "餐厅", "restaurant"]))
        if restaurant_count < scenario.min_restaurants:
            score -= 15
            issues.append(f"餐厅推荐不足: {restaurant_count} < {scenario.min_restaurants}")
        
        # Check for hotels
        hotel_count = sum(1 for it in all_items 
                         if it.get("type") in ["hotel", "stay", "住宿"] or
                         "酒店" in str(it.get("poi", "")) or 
                         any(tag in str(it.get("tags", [])) for tag in ["酒店", "住宿"]))
        if hotel_count < scenario.min_hotels:
            score -= 10
            issues.append(f"酒店推荐不足: {hotel_count} < {scenario.min_hotels}")
        
        return max(0, min(100, score)), issues
    
    def _evaluate_coverage(self, scenario: Scenario) -> tuple:
        """评估数据覆盖度"""
        score = 100
        issues = []
        
        # 检查景点数据量
        attractions_file = Path(__file__).resolve().parent.parent / "data" / "attractions.json"
        with open(attractions_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        city_pois = [p for p in data.get("attractions", []) 
                    if p.get("city") == scenario.city]
        
        total = len(city_pois)
        restaurants = sum(1 for p in city_pois 
                        if p.get("category", "") in ["餐厅", "restaurant", "restaurants"])
        hotels = sum(1 for p in city_pois 
                   if p.get("category", "") in ["酒店", "hotel", "hotels"])
        
        # 基础分
        if total < 10:
            score -= 40
            issues.append(f"{scenario.city} POI数据极少: 仅{total}条")
        elif total < 30:
            score -= 20
            issues.append(f"{scenario.city} POI数据偏少: {total}条")
        
        # 餐厅覆盖
        if restaurants < scenario.min_restaurants:
            score -= 15
            issues.append(f"{scenario.city} 餐厅不足: {restaurants} < {scenario.min_restaurants}")
        
        # 酒店覆盖
        if hotels < scenario.min_hotels:
            score -= 10
            issues.append(f"{scenario.city} 酒店不足: {hotels} < {scenario.min_hotels}")
        
        # 期望POI是否存在于KB中
        kb_names = [p.get("name", "") for p in city_pois]
        missing_pois = [p for p in scenario.expected_pois 
                       if not any(p in name for name in kb_names)]
        if missing_pois:
            score -= len(missing_pois) * 5
            issues.append(f"{scenario.city} 缺少POI: {', '.join(missing_pois[:5])}")
        
        return max(0, min(100, score)), issues
    
    def _build_query(self, scenario: Scenario) -> str:
        """构建查询字符串"""
        purpose = scenario.purpose
        city = scenario.city
        expected = " ".join(scenario.expected_pois[:3])
        return f"{city} {purpose} {expected}"
    
    def _has_llm(self) -> bool:
        """检查是否有LLM配置"""
        try:
            from app.config import settings
            return bool(settings.DEEPSEEK_API_KEY)
        except:
            return False
    
    async def _generate_itinerary(self, profile: Dict, recommendations: List) -> Optional[Dict]:
        """生成行程"""
        try:
            from app.agents.planning_agent import generate_itinerary
            from app.services.weather_service import get_weather_forecast
            
            weather = None
            try:
                weather_forecast = await get_weather_forecast(profile.get("destination", ""))
                # Convert WeatherForecast object to dict
                if weather_forecast and hasattr(weather_forecast, 'to_dict'):
                    weather = weather_forecast.to_dict()
            except:
                pass
            
            return await generate_itinerary(profile, recommendations, weather)
        except Exception as e:
            print(f"  ⚠️  行程生成失败: {e}")
            return None
    
    def _summarize_itinerary(self, itinerary: Dict) -> Dict:
        """简化行程预览"""
        days = itinerary.get("days", [])
        summary = {
            "trip_title": (itinerary.get("trip") or {}).get("title", ""),
            "days_count": len(days),
            "daily_pois": [],
        }
        for day in days[:3]:  # 只显示前3天
            day_num = day.get("day", 0)
            items = day.get("items", [])
            # Extract POI names from items (field is "poi", not "name")
            pois = [it.get("poi", "") or it.get("name", "") for it in items]
            # Filter out empty strings
            pois = [p for p in pois if p]
            summary["daily_pois"].append({
                "day": day_num,
                "pois": pois[:4],
            })
        return summary


async def run_evaluation():
    """运行评估"""
    evaluator = ScenarioEvaluator()
    await evaluator.initialize()
    
    print("\n" + "=" * 80)
    print("🎯 场景评估开始")
    print("=" * 80)
    print(f"共 {len(SCENARIOS)} 个场景待评估\n")
    
    # 评估所有场景
    for i, scenario in enumerate(SCENARIOS):
        print(f"\n📋 [{i+1}/{len(SCENARIOS)}] 评估: {scenario.id} - {scenario.city}")
        
        result = await evaluator.evaluate_scenario(scenario)
        evaluator.results.append(result)
        
        # 实时打印
        print(f"   总分: {result['total_score']}/100")
        for dim, score in result['dimensions'].items():
            print(f"   - {dim}: {score}/100")
        
        if result['issues']:
            print(f"   问题 ({len(result['issues'])}):")
            for issue in result['issues'][:3]:
                print(f"     ⚠️  {issue}")
    
    # ── 生成汇总报告 ──
    print_summary(evaluator.results)
    
    # ── 保存结果 ──
    output_dir = Path(__file__).resolve().parent.parent / "reports"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "scenario_evaluation_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_scenarios": len(evaluator.results),
            "average_score": round(
                sum(r['total_score'] for r in evaluator.results) / len(evaluator.results), 1
            ),
            "results": evaluator.results,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 详细报告已保存: {output_file}")


def print_summary(results: List[Dict]):
    """打印汇总"""
    print("\n" + "=" * 80)
    print("📊 评估汇总")
    print("=" * 80)
    
    if not results:
        return
    
    # 平均分
    avg = sum(r['total_score'] for r in results) / len(results)
    
    # 排序
    sorted_by_score = sorted(results, key=lambda x: x['total_score'])
    
    print(f"\n总场景数: {len(results)}")
    print(f"平均得分: {avg:.1f}/100")
    print(f"最高分: {sorted_by_score[-1]['total_score']} ({sorted_by_score[-1]['id']})")
    print(f"最低分: {sorted_by_score[0]['total_score']} ({sorted_by_score[0]['id']})")
    
    # 各维度平均分
    dims = {}
    for r in results:
        for dim, score in r['dimensions'].items():
            if dim not in dims:
                dims[dim] = []
            dims[dim].append(score)
    
    print(f"\n各维度平均分:")
    for dim, scores in sorted(dims.items()):
        avg_dim = sum(scores) / len(scores)
        print(f"  {dim}: {avg_dim:.1f}/100")
    
    # Top 5 问题
    all_issues = []
    for r in results:
        for issue in r['issues']:
            all_issues.append({
                "scenario": r['id'],
                "issue": issue,
            })
    
    # 去重统计
    issue_counts = {}
    for item in all_issues:
        issue = item['issue']
        # 简化问题描述
        key = issue[:30]
        if key not in issue_counts:
            issue_counts[key] = {"count": 0, "scenarios": set()}
        issue_counts[key]["count"] += 1
        issue_counts[key]["scenarios"].add(item['scenario'])
    
    sorted_issues = sorted(issue_counts.items(), key=lambda x: -x[1]['count'])
    
    print(f"\n🔥 高频问题 Top 10:")
    for key, data in sorted_issues[:10]:
        print(f"  [{data['count']}次] {key}...")
        print(f"    影响场景: {', '.join(sorted(data['scenarios'])[:5])}")
    
    # 修复优先级建议
    print(f"\n" + "=" * 80)
    print("🎯 修复优先级建议")
    print("=" * 80)
    
    print("""
    P0 (立即修复):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. RAG非目标城市结果问题 → 加强城市过滤
    2. 核心城市数据不足 → 补充热门城市POI
    3. 期望POI缺失 → 按场景需求补充特定POI
    
    P1 (尽快修复):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    4. 餐厅覆盖不足 → 聚焦热门城市补充
    5. 行程生成质量 → 优化Prompt和约束
    
    P2 (持续优化):
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    6. 酒店数据补充
    7. 小众城市扩展
    8. 特殊场景优化
    """)


if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(run_evaluation())
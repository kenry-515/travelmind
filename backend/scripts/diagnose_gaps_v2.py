"""
诊断当前系统的遗漏点：餐厅覆盖、行为日志、A/B测试
"""
import json
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

def main():
    print("=" * 80)
    print("诊断：餐厅/酒店覆盖 + 用户行为日志 + A/B测试基础设施")
    print("=" * 80)

    # 1. 餐厅/酒店覆盖分析
    print("\n## 1. 餐厅/酒店覆盖分析")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    city_stats = defaultdict(lambda: {"景点": 0, "餐厅": 0, "酒店": 0, "其他": 0})

    for poi in attractions:
        city = poi.get("city", "未知")
        category = poi.get("category", "其他")

        # 统计各类型数量
        if category in ["景点", "attraction", "attractions"]:
            city_stats[city]["景点"] += 1
        elif category in ["餐厅", "restaurant", "restaurants"]:
            city_stats[city]["餐厅"] += 1
        elif category in ["酒店", "hotel", "hotels"]:
            city_stats[city]["酒店"] += 1
        else:
            city_stats[city]["其他"] += 1

    # 找出餐厅/酒店覆盖不足的城市
    low_coverage = []
    for city, stats in sorted(city_stats.items(), key=lambda x: -sum(x[1].values()))[:30]:
        total = sum(stats.values())
        restaurant_ratio = stats["餐厅"] / total if total > 0 else 0
        hotel_ratio = stats["酒店"] / total if total > 0 else 0

        if restaurant_ratio < 0.15 or hotel_ratio < 0.05:
            low_coverage.append((city, stats, restaurant_ratio, hotel_ratio))

    print(f"总POI数: {len(attractions)}")
    print(f"覆盖城市数: {len(city_stats)}")

    print(f"\n餐厅/酒店覆盖不足的城市 (前10):")
    for city, stats, rr, hr in low_coverage[:10]:
        print(f"  {city}: 景点={stats['景点']}, 餐厅={stats['餐厅']}({rr:.1%}), 酒店={stats['酒店']}({hr:.1%})")

    # 2. 用户行为日志分析
    print("\n## 2. 用户行为日志基础设施")
    print("已有表结构:")
    print("  ✓ Favorite (收藏)")
    print("  ✓ RecommendationHistory (推荐历史)")
    print("  ✓ Feedback (反馈)")
    print("  ✓ Itinerary (行程)")
    print("\n缺失能力:")
    print("  ✗ 点击记录表 (POI点击/详情查看)")
    print("  ✗ 搜索日志表 (查询词/结果点击)")
    print("  ✗ 行为追踪服务 (埋点/采集/聚合)")
    print("  ✗ 用户行为分析服务 (偏好挖掘/冷启动优化)")

    # 3. A/B测试框架分析
    print("\n## 3. A/B测试基础设施")
    print("已有能力:")
    print("  ✓ 用户表 (User)")
    print("  ✓ 推荐历史表 (RecommendationHistory.scores_detail)")
    print("\n缺失能力:")
    print("  ✗ 实验分组表 (ExperimentGroup)")
    print("  ✗ 分流逻辑 (用户分组算法)")
    print("  ✗ 指标收集服务 (转化率/满意度)")
    print("  ✗ 实验对比服务 (统计显著性检验)")

    # 4. 最大的遗漏诊断
    print("\n" + "=" * 80)
    print("## 核心遗漏诊断")
    print("=" * 80)
    print("""
    【遗漏1】没有用户行为闭环
    - 当前只有"收藏"和"反馈"两个显性行为
    - 缺少隐性行为数据：点击、浏览时长、详情展开、地图查看
    - 结果：无法量化推荐质量，无法进行个性化优化

    【遗漏2】A/B测试基础设施为零
    - 当前无法验证评分权重调整的实际效果
    - 无法量化不同算法策略的用户满意度差异
    - 结果：每次优化都是"盲改"，没有数据支撑

    【遗漏3】餐厅/酒店数据冷启动问题
    - 郑州/南宁等城市的餐厅占比<15%，酒店<5%
    - 用户在这些城市的美食推荐体验会显著下降
    - 结果：冷启动城市用户流失风险高
    """)

    print("\n推荐优先级:")
    print("  P0: 用户行为日志系统 → 为后续优化提供数据基础")
    print("  P1: A/B测试框架 → 验证算法改进效果")
    print("  P2: 餐厅/酒店数据补充 → 改善冷启动城市体验")

if __name__ == "__main__":
    main()
"""
基于场景评估结果的修复计划
====================================

核心发现：
1. 3个城市完全无数据 (九寨沟/遵义/宁波)
2. 所有行程生成失败 (WeatherForecast兼容性问题)
3. RAG评分普遍偏低 (Top1评分0.14-0.28)
4. 餐厅推荐严重不足 (多数城市餐厅数<2)

修复优先级：
P0: 补充缺失城市数据
P1: 修复行程生成WeatherForecast问题
P2: 优化RAG检索质量
P3: 补充餐厅/酒店数据
"""

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

def main():
    print("="*80)
    print("TravelMindAgent 生产级质量修复计划")
    print("="*80)
    
    # 加载数据
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    attractions = data.get("attractions", [])
    
    # 统计当前状态
    city_counts = {}
    restaurant_counts = {}
    for poi in attractions:
        city = poi.get("city", "")
        cat = poi.get("category", "")
        if city not in city_counts:
            city_counts[city] = 0
            restaurant_counts[city] = 0
        city_counts[city] += 1
        if cat in ["餐厅", "restaurant", "restaurants"]:
            restaurant_counts[city] += 1
    
    # 分析问题
    print("\n📊 当前状态:")
    print(f"  总POI数: {len(attractions)}")
    print(f"  覆盖城市: {len(city_counts)}")
    
    # P0问题
    missing_cities = ["九寨沟", "遵义", "宁波", "九江", "喀什"]
    print(f"\n🔴 P0: 缺失城市数据")
    for city in missing_cities:
        count = city_counts.get(city, 0)
        print(f"  {city}: {count}条POI {'✗ 无数据' if count == 0 else '✓ 有数据'}")
    
    # P1问题
    print(f"\n🔴 P1: 行程生成WeatherForecast兼容问题")
    print(f"  错误: 'WeatherForecast' object has no attribute 'get'")
    print(f"  影响: 所有场景的行程生成为0分")
    
    # P2问题
    print(f"\n🟡 P2: RAG检索质量问题")
    print(f"  Top1评分范围: 0.14-0.28 (理想>0.5)")
    print(f"  原因: 查询词太短/标签匹配权重不足")
    
    # P3问题
    print(f"\n🟡 P3: 餐厅/酒店覆盖不足")
    low_restaurants = [(c, restaurant_counts.get(c, 0)) 
                       for c in city_counts 
                       if restaurant_counts.get(c, 0) < 3]
    low_restaurants.sort(key=lambda x: x[1])
    print(f"  餐厅<3的城市 ({len(low_restaurants)}个):")
    for city, count in low_restaurants[:10]:
        print(f"    {city}: {count}家餐厅")
    
    # 修复计划
    print(f"\n{'='*80}")
    print(f"📋 修复执行计划")
    print(f"{'='*80}")
    
    print(f"""
Step 1: [P0] 补充缺失城市POI
  - 九寨沟: 添加5-8个核心景点 (九寨沟景区/黄龙/藏寨)
  - 遵义: 添加3-5个核心景点 (遵义会议会址/赤水丹霞)
  - 宁波: 添加3-5个核心景点 (天一阁/老外滩/东钱湖)
  - 九江: 添加3-5个核心景点 (庐山/鄱阳湖)
  - 喀什: 添加3-5个核心景点 (喀什古城/香妃园)

Step 2: [P1] 修复WeatherForecast兼容问题
  - 修改planning_agent.py中对weather参数的处理
  - 兼容dict和WeatherForecast对象两种格式

Step 3: [P2] 优化RAG检索
  - 改进查询构建：添加城市名+偏好标签+关键词
  - 调整评分权重：增加语义相似度权重

Step 4: [P3] 补充餐厅数据
  - 昆明: 餐厅从7家增至15家
  - 福州: 餐厅从6家增至15家
  - 南宁: 餐厅补充至10家
  - 拉萨: 餐厅补充至8家

Step 5: 验证
  - 重新运行scenario_evaluation.py
  - 目标: 平均分从46.2提升至75+
""")
    
    print(f"推荐执行顺序: P0 → P1 → P2 → P3")
    print(f"每步完成后立即验证，确保质量提升")

if __name__ == "__main__":
    main()
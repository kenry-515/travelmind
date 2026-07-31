"""
诊断Chroma城市过滤问题
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

import json
from pathlib import Path

def main():
    # 检查attractions.json中城市字段
    data_path = Path(__file__).resolve().parent.parent / "data" / "attractions.json"
    
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    attractions = data.get("attractions", [])
    
    # 检查城市字段格式
    city_samples = set()
    for poi in attractions[:100]:
        city = poi.get("city", "")
        city_samples.add(city)
    
    print("前100条POI的城市字段:")
    print(sorted(city_samples))
    
    # 检查是否有空城市
    empty_city = [p for p in attractions if not p.get("city")]
    print(f"\n城市为空的POI: {len(empty_city)}")
    if empty_city:
        for p in empty_city[:5]:
            print(f"  - {p.get('name', '')}: city='{p.get('city', '')}'")
    
    # 检查特殊字符
    special_cities = [p.get("city", "") for p in attractions 
                     if p.get("city", "") and (p.get("city", "") != p.get("city", "").strip())]
    print(f"\n城市字段含前后空格: {len(special_cities)}")
    if special_cities:
        print(f"  样本: {special_cities[:5]}")
    
    # 检查中英文混合
    mixed_cities = set()
    for poi in attractions:
        city = poi.get("city", "")
        if city and any(c.isalpha() for c in city) and any('\u4e00' <= c <= '\u9fff' for c in city):
            mixed_cities.add(city)
    print(f"\n中英混合城市名: {len(mixed_cities)}")
    if mixed_cities:
        print(f"  {sorted(mixed_cities)[:10]}")
    
    # 检查实际存在的唯一城市
    unique_cities = set(p.get("city", "") for p in attractions if p.get("city"))
    print(f"\n总唯一城市数: {len(unique_cities)}")
    print(f"城市列表: {sorted(unique_cities)}")
    
    # 检查具体城市的POI数量
    city_counts = {}
    for poi in attractions:
        city = poi.get("city", "")
        if city:
            city_counts[city] = city_counts.get(city, 0) + 1
    
    print(f"\n各城市POI数 (Top 20):")
    for city, count in sorted(city_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {city}: {count}")
    
    # 结论
    print("\n" + "="*60)
    print("诊断结论:")
    print("="*60)
    
    # 构建Chroma过滤的测试
    print("\nChroma过滤测试 - 用 city='北京' 过滤:")
    print(f"  条件: where = {{'city': '北京'}}")
    
    beijing_pois = [p for p in attractions if p.get("city") == "北京"]
    print(f"  attractions.json中北京POI: {len(beijing_pois)}")
    
    # 检查是否有"北京 " (带空格)的情况
    beijing_with_space = [p for p in attractions if p.get("city", "").strip() == "北京" and p.get("city") != "北京"]
    print(f"  '北京 ' (带空格): {len(beijing_with_space)}")

if __name__ == "__main__":
    main()
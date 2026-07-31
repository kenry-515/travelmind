"""
P3: 补充餐厅数据
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

# 需要补充的餐厅数据
NEW_RESTAURANTS = [
    # ── 昆明 ──
    {
        "name": "过桥米线博物馆",
        "name_normalized": "过桥米线博物馆",
        "city": "昆明",
        "category": "餐厅",
        "tags": ["美食", "中餐", "特色"],
        "description": "过桥米线博物馆是昆明著名的过桥米线品牌，提供正宗的云南过桥米线，汤鲜味美。",
        "price_range": {"min": 30, "max": 80},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 25.04,
        "lon": 102.71,
        "popularity_score": 75,
    },
    {
        "name": "建新园过桥米线",
        "name_normalized": "建新园过桥米线",
        "city": "昆明",
        "category": "餐厅",
        "tags": ["美食", "中餐", "老字号"],
        "description": "建新园是昆明百年老字号过桥米线店，创建于1906年，以传统过桥米线闻名。",
        "price_range": {"min": 25, "max": 60},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 25.04,
        "lon": 102.71,
        "popularity_score": 70,
    },
    {
        "name": "老滇过桥米线",
        "name_normalized": "老滇过桥米线",
        "city": "昆明",
        "category": "餐厅",
        "tags": ["美食", "中餐", "特色"],
        "description": "老滇过桥米线是昆明本地知名的过桥米线品牌，提供地道的云南风味。",
        "price_range": {"min": 30, "max": 80},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 25.04,
        "lon": 102.71,
        "popularity_score": 65,
    },
    {
        "name": "云味集·云南菜",
        "name_normalized": "云味集·云南菜",
        "city": "昆明",
        "category": "餐厅",
        "tags": ["美食", "中餐", "特色"],
        "description": "云味集是昆明的云南菜馆，提供野生菌、汽锅鸡等云南特色菜肴。",
        "price_range": {"min": 80, "max": 200},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 25.04,
        "lon": 102.71,
        "popularity_score": 70,
    },
    
    # ── 福州 ──
    {
        "name": "聚春园",
        "name_normalized": "聚春园",
        "city": "福州",
        "category": "餐厅",
        "tags": ["美食", "中餐", "老字号"],
        "description": "聚春园是福州著名的百年老字号闽菜馆，创建于1902年，以佛跳墙闻名。",
        "price_range": {"min": 100, "max": 300},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 26.07,
        "lon": 119.30,
        "popularity_score": 75,
    },
    {
        "name": "安泰楼",
        "name_normalized": "安泰楼",
        "city": "福州",
        "category": "餐厅",
        "tags": ["美食", "中餐", "老字号"],
        "description": "安泰楼是福州的老字号闽菜馆，提供正宗的福州菜如醉糟鸡、荔枝肉等。",
        "price_range": {"min": 80, "max": 200},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 26.07,
        "lon": 119.30,
        "popularity_score": 70,
    },
    {
        "name": "文儒坊小吃",
        "name_normalized": "文儒坊小吃",
        "city": "福州",
        "category": "餐厅",
        "tags": ["美食", "小吃", "特色"],
        "description": "文儒坊小吃是福州的小吃聚集地，提供鱼丸、肉燕、锅边糊等福州传统小吃。",
        "price_range": {"min": 15, "max": 50},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 26.07,
        "lon": 119.30,
        "popularity_score": 65,
    },
    {
        "name": "连江海鲜酒楼",
        "name_normalized": "连江海鲜酒楼",
        "city": "福州",
        "category": "餐厅",
        "tags": ["美食", "海鲜", "中餐"],
        "description": "连江海鲜酒楼是福州知名的海鲜餐厅，提供新鲜的海鲜料理。",
        "price_range": {"min": 100, "max": 300},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 26.07,
        "lon": 119.30,
        "popularity_score": 65,
    },
    
    # ── 南宁 ──
    {
        "name": "复记老友粉",
        "name_normalized": "复记老友粉",
        "city": "南宁",
        "category": "餐厅",
        "tags": ["美食", "小吃", "特色"],
        "description": "复记老友粉是南宁著名的老友粉品牌，以酸辣开胃的老友粉闻名。",
        "price_range": {"min": 15, "max": 30},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 22.81,
        "lon": 108.37,
        "popularity_score": 70,
    },
    {
        "name": "粉之都",
        "name_normalized": "粉之都",
        "city": "南宁",
        "category": "餐厅",
        "tags": ["美食", "小吃", "特色"],
        "description": "粉之都南宁知名的连锁粉店，提供老友粉、螺蛳粉等南宁特色米粉。",
        "price_range": {"min": 15, "max": 30},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 22.81,
        "lon": 108.37,
        "popularity_score": 65,
    },
    {
        "name": "邕江鱼府",
        "name_normalized": "邕江鱼府",
        "city": "南宁",
        "category": "餐厅",
        "tags": ["美食", "中餐", "特色"],
        "description": "邕江鱼府是南宁知名的河鲜餐厅，提供邕江野生鱼等特色菜肴。",
        "price_range": {"min": 80, "max": 200},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 22.81,
        "lon": 108.37,
        "popularity_score": 65,
    },
    {
        "name": "柠檬鸭",
        "name_normalized": "柠檬鸭",
        "city": "南宁",
        "category": "餐厅",
        "tags": ["美食", "中餐", "特色"],
        "description": "柠檬鸭是南宁的特色菜肴，以柠檬和鸭子为主料，酸甜可口。",
        "price_range": {"min": 60, "max": 150},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 22.81,
        "lon": 108.37,
        "popularity_score": 65,
    },
    
    # ── 拉萨 ──
    {
        "name": "玛吉阿米",
        "name_normalized": "玛吉阿米",
        "city": "拉萨",
        "category": "餐厅",
        "tags": ["美食", "藏餐", "特色"],
        "description": "玛吉阿米是拉萨著名的藏餐厅，提供正宗的藏式菜肴，如牦牛肉、青稞饼等。",
        "price_range": {"min": 80, "max": 200},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者,文化爱好者",
        "lat": 29.65,
        "lon": 91.13,
        "popularity_score": 80,
    },
    {
        "name": "八廓街藏餐",
        "name_normalized": "八廓街藏餐",
        "city": "拉萨",
        "category": "餐厅",
        "tags": ["美食", "藏餐", "特色"],
        "description": "八廓街藏餐是拉萨八廓街地区的特色藏餐厅，提供地道的藏式风味。",
        "price_range": {"min": 60, "max": 150},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 29.65,
        "lon": 91.13,
        "popularity_score": 70,
    },
    {
        "name": "雪域老灶火锅",
        "name_normalized": "雪域老灶火锅",
        "city": "拉萨",
        "category": "餐厅",
        "tags": ["美食", "火锅", "中餐"],
        "description": "雪域老灶火锅是拉萨的特色火锅店，提供高原特色火锅。",
        "price_range": {"min": 80, "max": 200},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "冬季",
        "suitable_for": "美食爱好者",
        "lat": 29.65,
        "lon": 91.13,
        "popularity_score": 65,
    },
]


def main():
    print(f"📂 Loading {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    attractions = data.get("attractions", [])
    
    # 检查是否已存在相同POI
    existing_names = set()
    for poi in attractions:
        key = f"{poi.get('city', '')}|{poi.get('name', '')}"
        existing_names.add(key)
    
    # 添加新POI
    added = []
    skipped = []
    for new_poi in NEW_RESTAURANTS:
        key = f"{new_poi['city']}|{new_poi['name']}"
        if key in existing_names:
            skipped.append(new_poi)
        else:
            attractions.append(new_poi)
            existing_names.add(key)
            added.append(new_poi)
    
    print(f"\n📊 统计:")
    print(f"  原有POI: {len(data.get('attractions', []))}")
    print(f"  新增餐厅: {len(added)}")
    print(f"  跳过重复: {len(skipped)}")
    
    # 验证城市餐厅覆盖
    city_restaurants = {}
    for poi in attractions:
        city = poi.get("city", "")
        cat = poi.get("category", "")
        if cat in ["餐厅", "restaurant", "restaurants"]:
            city_restaurants[city] = city_restaurants.get(city, 0) + 1
    
    target_cities = ["昆明", "福州", "南宁", "拉萨"]
    print(f"\n✅ 目标城市餐厅数:")
    for city in target_cities:
        count = city_restaurants.get(city, 0)
        print(f"  {city}: {count}家餐厅")
    
    # 保存
    data["attractions"] = attractions
    data["total"] = len(attractions)
    if "last_updated" in data:
        data["last_updated"] = datetime.now().isoformat()
    
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 已保存: {len(attractions)} 条POI")


if __name__ == "__main__":
    main()
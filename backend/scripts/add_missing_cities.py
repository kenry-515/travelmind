"""
P0: 补充缺失城市核心POI数据
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

# 需要补充的城市POI数据
NEW_POIS = [
    # ── 九寨沟 ──
    {
        "name": "九寨沟风景名胜区",
        "name_normalized": "九寨沟风景名胜区",
        "city": "九寨沟",
        "category": "景点",
        "tags": ["自然", "徒步", "摄影", "世界遗产", "5A", "景点"],
        "description": "九寨沟风景名胜区位于四川省阿坝藏族羌族自治州九寨沟县漳扎镇，是长江水系嘉陵江源头的一条支沟，海拔2000-4000米。九寨沟以翠海、叠瀑、彩林、雪峰、藏情、蓝冰六绝驰名中外，是世界自然遗产。主要景点包括树正寨、荷叶寨、则查洼寨等九个藏族村寨。",
        "price_range": {"min": 190, "max": 190},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "秋季",
        "suitable_for": "自然爱好者,摄影爱好者,徒步爱好者",
        "lat": 33.26,
        "lon": 103.92,
        "popularity_score": 95,
    },
    {
        "name": "黄龙风景名胜区",
        "name_normalized": "黄龙风景名胜区",
        "city": "九寨沟",
        "category": "景点",
        "tags": ["自然", "徒步", "摄影", "世界遗产", "5A", "景点"],
        "description": "黄龙风景名胜区位于四川省松潘县境内，是中国唯一的保护完好的高原湿地。黄龙以彩池、雪山、峡谷、森林四绝著称，以其神奇的钙化景观闻名于世，被誉为人间瑶池。主要景点有黄龙寺、五彩池、争艳池等。",
        "price_range": {"min": 190, "max": 190},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "秋季",
        "suitable_for": "自然爱好者,摄影爱好者,徒步爱好者",
        "lat": 32.78,
        "lon": 103.82,
        "popularity_score": 90,
    },
    {
        "name": "树正寨",
        "name_normalized": "树正寨",
        "city": "九寨沟",
        "category": "景点",
        "tags": ["民俗", "文化", "古镇", "景点"],
        "description": "树正寨是九寨沟九个藏族村寨中最大的一个，位于九寨沟风景区内。寨中保存有大量传统的藏族建筑，游客可以在这里体验藏族文化，观看藏戏表演。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "文化体验者,民俗爱好者",
        "lat": 33.26,
        "lon": 103.92,
        "popularity_score": 70,
    },
    {
        "name": "五花海",
        "name_normalized": "五花海",
        "city": "九寨沟",
        "category": "景点",
        "tags": ["自然", "摄影", "景点"],
        "description": "五花海位于九寨沟的中心位置，是九寨沟最美的海子之一。湖水色彩斑斓，在阳光的照射下呈现出蓝、绿、黄、红等多种颜色，因此得名五花海。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "秋季",
        "suitable_for": "摄影爱好者,自然爱好者",
        "lat": 33.26,
        "lon": 103.92,
        "popularity_score": 85,
    },
    {
        "name": "珍珠滩瀑布",
        "name_normalized": "珍珠滩瀑布",
        "city": "九寨沟",
        "category": "景点",
        "tags": ["自然", "摄影", "景点"],
        "description": "珍珠滩瀑布是九寨沟内最大的瀑布，落差21米，宽162米。瀑布从珍珠滩上飞流而下，水声震天，气势磅礴，是九寨沟的标志性景观之一。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "夏季",
        "suitable_for": "摄影爱好者,自然爱好者",
        "lat": 33.26,
        "lon": 103.92,
        "popularity_score": 80,
    },
    
    # ── 遵义 ──
    {
        "name": "遵义会议会址",
        "name_normalized": "遵义会议会址",
        "city": "遵义",
        "category": "景点",
        "tags": ["历史", "红色旅游", "博物馆", "景点"],
        "description": "遵义会议会址位于贵州省遵义市红花岗区子尹路96号，是一幢中西合璧的两层楼房。1935年1月15日至17日，中共中央政治局扩大会议在此召开，确立了以毛泽东为核心的新的党中央的正确领导。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "历史爱好者,红色旅游爱好者",
        "lat": 27.73,
        "lon": 106.93,
        "popularity_score": 85,
    },
    {
        "name": "赤水丹霞旅游区",
        "name_normalized": "赤水丹霞旅游区",
        "city": "遵义",
        "category": "景点",
        "tags": ["自然", "徒步", "摄影", "世界遗产", "景点"],
        "description": "赤水丹霞旅游区位于贵州省赤水市，是世界自然遗产中国丹霞的重要组成部分。赤水丹霞以红色丹霞地貌为特征，拥有赤水大瀑布、燕子岩、佛光岩等著名景点。",
        "price_range": {"min": 120, "max": 120},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "秋季",
        "suitable_for": "自然爱好者,徒步爱好者,摄影爱好者",
        "lat": 28.59,
        "lon": 105.69,
        "popularity_score": 75,
    },
    {
        "name": "遵义市博物馆",
        "name_normalized": "遵义市博物馆",
        "city": "遵义",
        "category": "景点",
        "tags": ["历史", "文化", "博物馆", "景点"],
        "description": "遵义市博物馆位于遵义市新蒲新区，是一座综合性博物馆，收藏有大量历史文物，展示了遵义的历史文化和红色文化。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "历史爱好者,文化爱好者",
        "lat": 27.73,
        "lon": 106.93,
        "popularity_score": 60,
    },
    {
        "name": "娄山关",
        "name_normalized": "娄山关",
        "city": "遵义",
        "category": "景点",
        "tags": ["历史", "自然", "景点"],
        "description": "娄山关位于遵义市北部，是大娄山脉的主峰，海拔1444米。这里是红军长征途中的重要战场，1935年2月，红军在此取得了娄山关大捷。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "春季",
        "suitable_for": "历史爱好者,自然爱好者",
        "lat": 27.98,
        "lon": 106.94,
        "popularity_score": 65,
    },
    
    # ── 宁波 ──
    {
        "name": "天一阁",
        "name_normalized": "天一阁",
        "city": "宁波",
        "category": "景点",
        "tags": ["历史", "文化", "博物馆", "文艺", "景点"],
        "description": "天一阁位于浙江省宁波市海曙区月湖畔，始建于明嘉靖四十年(1561年)，是中国现存最早的私家藏书楼，也是亚洲现有最古老的图书馆。天一阁以藏书丰富、建筑独特而闻名于世。",
        "price_range": {"min": 30, "max": 30},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "历史爱好者,文化爱好者,文艺青年",
        "lat": 29.87,
        "lon": 121.55,
        "popularity_score": 85,
    },
    {
        "name": "老外滩",
        "name_normalized": "老外滩",
        "city": "宁波",
        "category": "景点",
        "tags": ["夜景", "历史", "美食", "打卡", "景点"],
        "description": "宁波老外滩位于宁波市江北区，是中国最早开埠通商口岸之一，已有170多年历史。老外滩保留了大量欧式建筑，现已成为宁波的时尚地标和夜生活中心。",
        "price_range": {"min": 0, "max": 0},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者,夜生活爱好者,摄影爱好者",
        "lat": 29.89,
        "lon": 121.55,
        "popularity_score": 80,
    },
    {
        "name": "东钱湖旅游度假区",
        "name_normalized": "东钱湖旅游度假区",
        "city": "宁波",
        "category": "景点",
        "tags": ["自然", "休闲", "摄影", "景点"],
        "description": "东钱湖位于宁波市东南部，是浙江省最大的天然湖泊之一。东钱湖以西子风韵、太湖气魄著称，拥有小普陀、陶公岛、南宋石刻公园等著名景点。",
        "price_range": {"min": 30, "max": 30},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "春秋季",
        "suitable_for": "休闲爱好者,摄影爱好者,家庭游客",
        "lat": 29.73,
        "lon": 121.67,
        "popularity_score": 75,
    },
    {
        "name": "溪口风景区",
        "name_normalized": "溪口风景区",
        "city": "宁波",
        "category": "景点",
        "tags": ["历史", "自然", "古镇", "景点"],
        "description": "溪口风景区位于宁波市奉化区，是蒋介石的故里，也是国家级风景名胜区。溪口以剡溪之水得名，主要景点包括溪口镇、雪窦山、滕头村等。",
        "price_range": {"min": 120, "max": 120},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "春秋季",
        "suitable_for": "历史爱好者,自然爱好者",
        "lat": 29.71,
        "lon": 121.27,
        "popularity_score": 70,
    },
    
    # ── 宁波餐厅 ──
    {
        "name": "缸鸭狗",
        "name_normalized": "缸鸭狗",
        "city": "宁波",
        "category": "餐厅",
        "tags": ["美食", "老字号", "中餐"],
        "description": "缸鸭狗是宁波著名的老字号汤圆店，创建于1926年，以猪油汤圆闻名。除了汤圆，还提供宁波传统小吃如龙凤金团、豆腐酒酿汤团等。",
        "price_range": {"min": 30, "max": 60},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 29.87,
        "lon": 121.55,
        "popularity_score": 75,
    },
    {
        "name": "赵大有糕饼店",
        "name_normalized": "赵大有糕饼店",
        "city": "宁波",
        "category": "餐厅",
        "tags": ["美食", "老字号", "小吃"],
        "description": "赵大有是宁波著名的糕饼老字号，创建于1852年，以龙凤金团、椒盐蛋糕等传统糕点闻名。",
        "price_range": {"min": 20, "max": 50},
        "price_source": "official",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 29.87,
        "lon": 121.55,
        "popularity_score": 65,
    },
    
    # ── 九寨沟餐厅 ──
    {
        "name": "藏家宴",
        "name_normalized": "藏家宴",
        "city": "九寨沟",
        "category": "餐厅",
        "tags": ["美食", "藏餐", "特色"],
        "description": "藏家宴是九寨沟地区著名的藏餐馆，提供正宗的藏族风味菜肴，如牦牛肉、青稞饼、酥油茶等。",
        "price_range": {"min": 80, "max": 150},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者,文化爱好者",
        "lat": 33.26,
        "lon": 103.92,
        "popularity_score": 70,
    },
    {
        "name": "九寨人家",
        "name_normalized": "九寨人家",
        "city": "九寨沟",
        "category": "餐厅",
        "tags": ["美食", "中餐", "川菜"],
        "description": "九寨人家是九寨沟地区的特色中餐厅，以川菜为主，同时提供本地特色菜肴。",
        "price_range": {"min": 60, "max": 120},
        "price_source": "estimated",
        "price_updated_at": "2024-01-01",
        "best_time": "全年",
        "suitable_for": "美食爱好者",
        "lat": 33.26,
        "lon": 103.92,
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
    for new_poi in NEW_POIS:
        key = f"{new_poi['city']}|{new_poi['name']}"
        if key in existing_names:
            skipped.append(new_poi)
        else:
            attractions.append(new_poi)
            existing_names.add(key)
            added.append(new_poi)
    
    print(f"\n📊 统计:")
    print(f"  原有POI: {len(data.get('attractions', []))}")
    print(f"  新增POI: {len(added)}")
    print(f"  跳过重复: {len(skipped)}")
    
    # 验证城市覆盖
    new_data = data.copy()
    new_data["attractions"] = attractions
    new_data["total"] = len(attractions)
    if "last_updated" in new_data:
        new_data["last_updated"] = datetime.now().isoformat()
    
    # 保存
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 已保存: {len(attractions)} 条POI")
    
    # 验证缺失城市
    city_counts = {}
    for poi in attractions:
        city = poi.get("city", "")
        city_counts[city] = city_counts.get(city, 0) + 1
    
    print(f"\n✅ 验证:")
    for city in ["九寨沟", "遵义", "宁波"]:
        count = city_counts.get(city, 0)
        status = "✓" if count > 0 else "✗"
        print(f"  {city}: {count}条POI {status}")


if __name__ == "__main__":
    main()
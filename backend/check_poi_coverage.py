"""Check POI data coverage for test cities."""
import json
import sys
sys.path.insert(0, '.')

# Load attractions data
with open('data/attractions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

attractions = data.get('attractions', [])

# Check coverage for test cities
cities_to_check = ['北京', '成都', '西安', '上海', '丽江', '厦门', '重庆']

# Key attractions that should exist
must_have_pois = {
    '北京': ['故宫', '长城', '颐和园', '天坛', '圆明园', '鸟巢', '水立方', '南锣鼓巷'],
    '成都': ['宽窄巷子', '锦里', '大熊猫', '杜甫草堂', '武侯祠', '都江堰', '太古里', '春熙路'],
    '西安': ['兵马俑', '大雁塔', '古城墙', '华清池', '回民街', '大唐不夜城'],
    '上海': ['外滩', '东方明珠', '南京路', '豫园', '迪士尼', '世博会', '田子坊'],
    '丽江': ['丽江古城', '束河古镇', '玉龙雪山', '泸沽湖', '黑龙潭', '木府'],
    '厦门': ['鼓浪屿', '南普陀寺', '厦门大学', '曾厝垵', '环岛路', '土楼'],
    '重庆': ['洪崖洞', '解放碑', '长江索道', '磁器口', '武隆', '李子坝', '观音桥']
}

# Check
print("=" * 70)
print("📊 POI 数据覆盖检查")
print("=" * 70)

for city in cities_to_check:
    city_pois = [a for a in attractions if a.get('city') == city]
    print(f"\n📍 {city}: {len(city_pois)} 个景点")
    
    # Check must-have POIs
    missing = []
    for must_have in must_have_pois.get(city, []):
        found = any(must_have in a.get('name', '') for a in city_pois)
        status = "✅" if found else "❌"
        if not found:
            missing.append(must_have)
        print(f"  {status} {must_have}")
    
    if missing:
        print(f"\n  ⚠️  缺少 {len(missing)} 个标志性POI: {', '.join(missing)}")
    else:
        print(f"\n  ✅ 所有标志性POI都已存在")

# Also check categories
print("\n" + "=" * 70)
print("📈 标签分布统计")
print("=" * 70)

# Check tag distribution for food/shopping/history
target_tags = ['美食', '火锅', '小吃', '购物', '商场', '历史', '博物馆', '海滩', '海边']

for tag in target_tags:
    count = sum(1 for a in attractions if tag in str(a.get('tags', '')))
    print(f"  {tag}: {count} 个景点")

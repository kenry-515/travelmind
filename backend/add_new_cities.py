"""Add POI data for 5 new cities."""
import json
from pathlib import Path

# Load current data
with open('data/attractions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

existing_names = {(a['name'], a['city']) for a in data['attractions']}

# New POIs for 5 cities
new_pois = [
    # ========== 杭州 ==========
    {
        "name": "西湖",
        "lat": 30.2459, "lon": 120.1486, "city": "杭州",
        "description": "西湖是中国十大风景名胜之一，以秀丽的湖光山色和众多的名胜古迹闻名，三面环山，面积约6.39平方公里。",
        "tags": ["自然", "湖景", "文化", "古迹", "5A", "世界遗产", "休闲", "观光"],
        "suitable_for": "休闲度假、文化体验、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 10
    },
    {
        "name": "灵隐寺",
        "lat": 30.2412, "lon": 120.0989, "city": "杭州",
        "description": "灵隐寺是杭州最早的名刹，创建于东晋咸和元年，距今已有1700多年历史，是中国佛教禅宗十大古刹之一。",
        "tags": ["寺庙", "宗教", "文化", "古迹", "古建筑", "历史"],
        "suitable_for": "宗教信仰者、文化爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "千岛湖",
        "lat": 29.6088, "lon": 119.0463, "city": "杭州",
        "description": "千岛湖是世界上岛屿最多的湖，拥有1078座岛屿，是国家一级水源保护区，以自然风光优美著称。",
        "tags": ["自然", "湖泊", "岛屿", "度假", "户外", "5A", "观光"],
        "suitable_for": "休闲度假、户外运动、摄影爱好者",
        "best_time": "春季、夏季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "宋城",
        "lat": 30.1967, "lon": 120.1025, "city": "杭州",
        "description": "宋城是中国最大的宋文化主题公园，以南宋文化为主题，提供《宋城千古情》大型演出，被誉为'给我一天，还你千年'。",
        "tags": ["主题乐园", "演出", "文化", "历史", "亲子", "5A"],
        "suitable_for": "家庭出游、文化体验、娱乐体验",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "西溪湿地",
        "lat": 30.2667, "lon": 120.0778, "city": "杭州",
        "description": "西溪湿地是国内第一个国家湿地公园，以湿地生态系统为特色，是鸟类的重要栖息地，也是《非诚勿扰》取景地。",
        "tags": ["自然", "湿地", "生态", "观鸟", "休闲", "4A"],
        "suitable_for": "自然爱好者、生态摄影、休闲",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 8
    },
    {
        "name": "京杭大运河（杭州段）",
        "lat": 30.2468, "lon": 120.1486, "city": "杭州",
        "description": "京杭大运河是世界上最长的人工河，杭州段沿线有拱宸桥、小河直街等历史文化街区，2014年入选世界文化遗产。",
        "tags": ["文化", "历史", "运河", "古迹", "世界遗产", "夜景"],
        "suitable_for": "文化爱好者、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "河坊街",
        "lat": 30.2431, "lon": 120.1683, "city": "杭州",
        "description": "河坊街是杭州最著名的历史文化街区之一，保留了南宋时期的风貌，有'杭州的清明上河图'之称。",
        "tags": ["古街", "文化", "民俗", "美食", "小吃", "购物"],
        "suitable_for": "文化爱好者、美食爱好者、购物",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    # ========== 苏州 ==========
    {
        "name": "拙政园",
        "lat": 31.3258, "lon": 120.6296, "city": "苏州",
        "description": "拙政园是中国四大名园之首，始建于明正德年间，以水景见长，是江南园林的典范。",
        "tags": ["园林", "古迹", "文化", "历史", "世界遗产", "5A"],
        "suitable_for": "文化爱好者、摄影爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 10
    },
    {
        "name": "苏州博物馆",
        "lat": 31.3267, "lon": 120.6283, "city": "苏州",
        "description": "苏州博物馆由贝聿铭设计，以'中而新，苏而新'为设计理念，是中国地方历史艺术类博物馆。",
        "tags": ["博物馆", "文化", "建筑", "艺术", "历史"],
        "suitable_for": "文化爱好者、建筑爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    {
        "name": "虎丘塔",
        "lat": 31.3433, "lon": 120.5839, "city": "苏州",
        "description": "虎丘塔是中国的'比萨斜塔'，有2500多年历史，是世界上第二斜塔，也是苏州的标志性建筑。",
        "tags": ["古塔", "古迹", "历史", "文化", "倾斜", "5A"],
        "suitable_for": "文化爱好者、摄影爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "周庄古镇",
        "lat": 31.1119, "lon": 120.8397, "city": "苏州",
        "description": "周庄古镇是典型的江南水乡，有'中国第一水乡'之称，以小桥流水、白墙黛瓦闻名。",
        "tags": ["古镇", "水乡", "民俗", "文化", "5A", "休闲"],
        "suitable_for": "文化爱好者、休闲度假、摄影",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "金鸡湖",
        "lat": 31.3167, "lon": 120.7103, "city": "苏州",
        "description": "金鸡湖是中国最大的城市内湖，位于苏州工业园区，以现代城市景观和自然湖景融合著称。",
        "tags": ["湖泊", "现代", "休闲", "夜景", "观光"],
        "suitable_for": "休闲、摄影、都市观光",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "寒山寺",
        "lat": 31.3097, "lon": 120.5675, "city": "苏州",
        "description": "寒山寺始建于南朝萧梁代天监年间，以'夜半钟声到客船'闻名，是苏州著名的佛教圣地。",
        "tags": ["寺庙", "宗教", "古迹", "文化", "历史"],
        "suitable_for": "宗教信仰者、文化爱好者",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 8
    },
    {
        "name": "平江路",
        "lat": 31.3183, "lon": 120.6306, "city": "苏州",
        "description": "平江路是苏州保存最完整的历史街区，有800多年历史，以水巷小桥、粉墙黛瓦闻名。",
        "tags": ["古街", "文化", "民俗", "历史", "世界遗产"],
        "suitable_for": "文化爱好者、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    # ========== 南京 ==========
    {
        "name": "中山陵",
        "lat": 32.0621, "lon": 118.8279, "city": "南京",
        "description": "中山陵是孙中山先生的陵墓，位于紫金山南麓，是中国近代建筑的杰出代表，有'中国近代建筑第一陵'之称。",
        "tags": ["陵墓", "历史", "文化", "建筑", "5A", "民国"],
        "suitable_for": "历史爱好者、文化爱好者",
        "best_time": "春季、秋季",
        "price_level": "免费",
        "popularity_score": 10
    },
    {
        "name": "夫子庙秦淮河",
        "lat": 32.0255, "lon": 118.7903, "city": "南京",
        "description": "夫子庙秦淮河是中国最大的传统古街市，集庙宇、园林、街市为一体，是南京的文化中心。",
        "tags": ["古街", "文化", "民俗", "夜景", "5A", "历史", "美食"],
        "suitable_for": "文化爱好者、美食爱好者、休闲",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    {
        "name": "明孝陵",
        "lat": 32.0583, "lon": 118.8297, "city": "南京",
        "description": "明孝陵是明太祖朱元璋与其皇后的合葬陵墓，是中国现存规模最大、保存最完整的古代帝王陵墓之一。",
        "tags": ["陵墓", "历史", "古迹", "世界遗产", "5A", "明代"],
        "suitable_for": "历史爱好者、文化爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "南京博物院",
        "lat": 32.0453, "lon": 118.8119, "city": "南京",
        "description": "南京博物院是中国三大博物馆之一，藏品跨越旧石器时代至近现代，是中华文明的瑰宝。",
        "tags": ["博物馆", "文化", "历史", "文物", "艺术"],
        "suitable_for": "文化爱好者、历史爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "玄武湖",
        "lat": 32.0675, "lon": 118.7903, "city": "南京",
        "description": "玄武湖是中国现存的历史最悠久的皇家园林湖泊之一，已有1500多年历史，是南京的'城中明珠'。",
        "tags": ["湖泊", "园林", "历史", "文化", "休闲", "4A"],
        "suitable_for": "休闲、散步、摄影",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "总统府",
        "lat": 32.0483, "lon": 118.7953, "city": "南京",
        "description": "南京总统府是中国近代史上重要的历史遗址，曾是中华民国临时大总统孙中山的办公地点。",
        "tags": ["历史", "建筑", "民国", "文化", "4A"],
        "suitable_for": "历史爱好者、文化爱好者",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 8
    },
    # ========== 广州 ==========
    {
        "name": "广州塔（小蛮腰）",
        "lat": 23.1066, "lon": 113.3239, "city": "广州",
        "description": "广州塔又名小蛮腰，是世界第三高塔，高600米，集观光、旅游、娱乐、广播于一体。",
        "tags": ["地标", "现代建筑", "观景", "夜景", "5A", "都市"],
        "suitable_for": "摄影爱好者、都市观光",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 10
    },
    {
        "name": "长隆欢乐世界",
        "lat": 22.9900, "lon": 113.3353, "city": "广州",
        "description": "长隆欢乐世界是国内最具影响力的主题乐园之一，以大型游乐设施和主题活动闻名。",
        "tags": ["主题乐园", "娱乐", "亲子", "家庭", "5A"],
        "suitable_for": "家庭出游、亲子活动、娱乐",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "沙面岛",
        "lat": 23.1089, "lon": 113.2389, "city": "广州",
        "description": "沙面岛是广州市著名的历史文化街区，曾是租界区，保存有150多座欧式建筑，有'万国建筑博览'之称。",
        "tags": ["历史", "建筑", "文化", "欧式", "休闲", "摄影"],
        "suitable_for": "文化爱好者、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "珠江夜游",
        "lat": 23.1181, "lon": 113.3403, "city": "广州",
        "description": "珠江夜游是广州的特色旅游项目，乘坐游船欣赏两岸璀璨的夜景和地标建筑。",
        "tags": ["夜景", "游船", "都市", "休闲", "观光"],
        "suitable_for": "情侣、家庭、都市观光",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 8
    },
    {
        "name": "陈家祠",
        "lat": 23.1267, "lon": 113.2447, "city": "广州",
        "description": "陈家祠是广东现存规模最大、装饰最精美的宗祠建筑，被誉为'岭南建筑艺术的明珠'。",
        "tags": ["建筑", "文化", "民俗", "历史", "4A"],
        "suitable_for": "文化爱好者、建筑爱好者",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 8
    },
    {
        "name": "上下九步行街",
        "lat": 23.1253, "lon": 113.2406, "city": "广州",
        "description": "上下九步行街是广州著名的商业步行街，汇集了众多老字号美食和传统商铺，是品尝广州美食的好去处。",
        "tags": ["商业街", "美食", "小吃", "购物", "文化"],
        "suitable_for": "美食爱好者、购物爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "白云山",
        "lat": 23.1850, "lon": 113.3367, "city": "广州",
        "description": "白云山是广州著名的风景名胜区，有'羊城第一秀'之称，主峰摩星岭海拔382米。",
        "tags": ["自然", "登山", "户外", "观光", "5A"],
        "suitable_for": "户外运动爱好者、自然爱好者",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 7
    },
    # ========== 深圳 ==========
    {
        "name": "世界之窗",
        "lat": 22.5353, "lon": 113.9741, "city": "深圳",
        "description": "世界之窗是中国最大的文化旅游主题公园之一，以弘扬世界文化为宗旨，汇集了130处世界奇观。",
        "tags": ["主题乐园", "文化", "观光", "亲子", "5A"],
        "suitable_for": "家庭出游、文化观光",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "欢乐谷",
        "lat": 22.6175, "lon": 113.9747, "city": "深圳",
        "description": "深圳欢乐谷是国内最具影响力的主题乐园之一，以大型游乐设施和丰富的主题活动闻名。",
        "tags": ["主题乐园", "娱乐", "刺激", "亲子", "5A"],
        "suitable_for": "家庭出游、年轻人、娱乐",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "大梅沙海滨公园",
        "lat": 22.5919, "lon": 114.3233, "city": "深圳",
        "description": "大梅沙海滨公园是深圳最大的免费海滨浴场，拥有1800米的金色沙滩，是夏季避暑胜地。",
        "tags": ["海滩", "海滨", "沙滩", "度假", "免费", "4A"],
        "suitable_for": "家庭出游、海滩爱好者",
        "best_time": "夏季",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "东部华侨城",
        "lat": 22.6144, "lon": 114.2919, "city": "深圳",
        "description": "东部华侨城是集休闲度假、观光旅游、户外运动、科普教育于一体的大型综合性旅游区。",
        "tags": ["度假", "自然", "户外", "休闲", "5A"],
        "suitable_for": "家庭出游、休闲度假",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 8
    },
    {
        "name": "深圳湾公园",
        "lat": 22.5239, "lon": 113.9369, "city": "深圳",
        "description": "深圳湾公园是深圳湾畔的大型海滨公园，可远眺香港，是深圳市民休闲的好去处。",
        "tags": ["海滨", "公园", "休闲", "夜景", "观光"],
        "suitable_for": "休闲、散步、观鸟",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 7
    },
    {
        "name": "莲花山公园",
        "lat": 22.5567, "lon": 114.1539, "city": "深圳",
        "description": "莲花山公园是深圳中心区的大型城市公园，山顶有邓小平雕像，可俯瞰深圳中心区全貌。",
        "tags": ["公园", "观光", "休闲", "都市"],
        "suitable_for": "休闲、观光、摄影",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 7
    },
    {
        "name": "大鹏所城",
        "lat": 22.5989, "lon": 114.5589, "city": "深圳",
        "description": "大鹏所城始建于明洪武二十七年，是明清两代的军事要塞，保存完好，是深圳的历史文化瑰宝。",
        "tags": ["古城", "历史", "军事", "古迹", "文化"],
        "suitable_for": "历史爱好者、文化爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 7
    },
]

# Add new POIs
added = 0
skipped = 0
for poi in new_pois:
    key = (poi['name'], poi['city'])
    if key not in existing_names:
        data['attractions'].append(poi)
        existing_names.add(key)
        added += 1
        print(f"✅ 添加: {poi['name']} ({poi['city']})")
    else:
        skipped += 1
        print(f"⏭️  跳过(已存在): {poi['name']} ({poi['city']})")

# Update data
data['total'] = len(data['attractions'])

# Save
with open('data/attractions.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n📊 统计:")
print(f"  新增 POI: {added} 个")
print(f"  跳过重复: {skipped} 个")
print(f"  总数: {len(data['attractions'])} 个")

# City breakdown
city_counts = {}
for a in data['attractions']:
    city = a['city']
    city_counts[city] = city_counts.get(city, 0) + 1

print(f"\n🗺️ 各城市 POI 数量:")
new_cities = ['杭州', '苏州', '南京', '广州', '深圳']
for city in new_cities:
    count = city_counts.get(city, 0)
    print(f"  {city}: {count} 个")

"""Add missing iconic POIs to attractions.json."""
import json
import sys
sys.path.insert(0, '.')

# Load current data
with open('data/attractions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

attractions = data['attractions']
existing_names = {a['name'] for a in attractions}

# Missing iconic POIs to add
missing_pois = [
    # 北京 - 颐和园, 水立方, 南锣鼓巷
    {
        "name": "颐和园",
        "lat": 39.9999,
        "lon": 116.2755,
        "city": "北京",
        "description": "颐和园是中国清朝时期的皇家园林，世界文化遗产，以昆明湖、万寿山为基址，是保存最完整的皇家园林，被誉为'皇家园林博物馆'。",
        "tags": ["历史", "皇家", "园林", "世界遗产", "5A", "博物馆", "古建筑"],
        "suitable_for": "历史爱好者、摄影爱好者、文化体验",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 10
    },
    {
        "name": "水立方（国家游泳中心）",
        "lat": 39.9929,
        "lon": 116.3904,
        "city": "北京",
        "description": "国家游泳中心（水立方）是2008年北京奥运会的主游泳馆，以独特的泡沫结构设计闻名，是集游泳、跳水、花样游泳等多功能于一体的水上运动中心。",
        "tags": ["体育", "水上运动", "亲子", "家庭", "现代建筑", "奥林匹克"],
        "suitable_for": "家庭出游、亲子活动、体育爱好者",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 7
    },
    {
        "name": "南锣鼓巷",
        "lat": 39.9369,
        "lon": 116.4024,
        "city": "北京",
        "description": "南锣鼓巷是北京保存最完整的胡同片区之一，全长约780米，是北京四合院的精华所在，现为著名的商业街和旅游景点。",
        "tags": ["胡同", "古镇", "历史", "文化", "小吃", "购物", "文艺", "网红打卡"],
        "suitable_for": "文化爱好者、摄影爱好者、美食爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    # 成都 - 宽窄巷子, 锦里, 武侯祠, 都江堰
    {
        "name": "宽窄巷子",
        "lat": 30.6733,
        "lon": 104.0617,
        "city": "成都",
        "description": "宽窄巷子是成都三大历史文化保护区之一，由宽巷子、窄巷子和井巷子组成，是老成都生活的活化石，现为集美食、文化、旅游于一体的商业街。",
        "tags": ["古镇", "历史", "文化", "美食", "小吃", "火锅", "网红打卡", "摄影"],
        "suitable_for": "美食爱好者、文化爱好者、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 10
    },
    {
        "name": "锦里古街",
        "lat": 30.6466,
        "lon": 104.0419,
        "city": "成都",
        "description": "锦里古街是成都最具历史气息的商业街之一，以三国文化、川西民俗文化为特色，有'西蜀第一街'之称。",
        "tags": ["古镇", "历史", "三国文化", "美食", "小吃", "民俗", "网红打卡"],
        "suitable_for": "文化爱好者、美食爱好者、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    {
        "name": "武侯祠博物馆",
        "lat": 30.6436,
        "lon": 104.0429,
        "city": "成都",
        "description": "武侯祠是中国唯一的君臣合祀祠庙，是纪念诸葛亮和刘备的著名三国遗迹，现为全国重点文物保护单位。",
        "tags": ["历史", "三国文化", "博物馆", "古迹", "古建筑", "文化"],
        "suitable_for": "历史爱好者、三国文化爱好者、文物爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 8
    },
    {
        "name": "都江堰水利工程",
        "lat": 30.9999,
        "lon": 103.6111,
        "city": "成都",
        "description": "都江堰是战国时期秦国李冰父子主持修建的大型水利工程，世界文化遗产，至今仍在使用，被誉为'世界水利文化的鼻祖'。",
        "tags": ["历史", "世界遗产", "水利工程", "文化", "古迹", "5A"],
        "suitable_for": "历史爱好者、文化爱好者、科普爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    # 西安 - 古城墙, 回民街
    {
        "name": "西安城墙",
        "lat": 34.2616,
        "lon": 108.9486,
        "city": "西安",
        "description": "西安城墙是中国现存规模最大、保存最完整的古代城垣，明代修筑，周长13.74公里，是西安的标志性建筑。",
        "tags": ["历史", "古城墙", "明代", "古迹", "古建筑", "摄影", "5A"],
        "suitable_for": "历史爱好者、摄影爱好者、文化体验",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 10
    },
    {
        "name": "回民街",
        "lat": 34.2673,
        "lon": 108.9398,
        "city": "西安",
        "description": "回民街是西安著名的美食文化街区，以回族风味小吃闻名，有泡馍、肉夹馍、biangbiang面等特色美食。",
        "tags": ["美食", "小吃", "回族文化", "民俗", "美食街", "网红打卡"],
        "suitable_for": "美食爱好者、文化爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    # 上海 - 东方明珠, 南京路, 世博会, 田子坊
    {
        "name": "东方明珠广播电视塔",
        "lat": 31.2397,
        "lon": 121.4998,
        "city": "上海",
        "description": "东方明珠塔是上海标志性建筑，高468米，是亚洲第一、世界第三高塔，可360度俯瞰上海城市风光。",
        "tags": ["地标", "现代建筑", "观景", "摄影", "夜景", "都市", "5A"],
        "suitable_for": "摄影爱好者、都市观光、情侣",
        "best_time": "全年",
        "price_level": "付费",
        "popularity_score": 10
    },
    {
        "name": "南京路步行街",
        "lat": 31.2334,
        "lon": 121.4852,
        "city": "上海",
        "description": "南京路是上海最著名的商业街，有'中华商业第一街'之称，汇集了众多百年老字号和国际品牌。",
        "tags": ["购物", "商业街", "老字号", "都市", "网红打卡", "夜生活"],
        "suitable_for": "购物爱好者、都市观光",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    {
        "name": "上海世博园",
        "lat": 31.1899,
        "lon": 121.4911,
        "city": "上海",
        "description": "上海世博园是2010年上海世博会的举办场地，现保留有中国馆、世博轴等标志性建筑，是集会展、文化、休闲于一体的综合性园区。",
        "tags": ["现代建筑", "文化", "展览", "公园", "亲子", "家庭"],
        "suitable_for": "家庭出游、文化爱好者、现代建筑爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 7
    },
    {
        "name": "田子坊",
        "lat": 31.2111,
        "lon": 121.4675,
        "city": "上海",
        "description": "田子坊是由上海石库门建筑群改建而成的创意街区，汇集了艺术工作室、创意店铺和特色餐厅，是上海的'798'。",
        "tags": ["文艺", "创意园", "艺术", "打卡", "网红", "小众", "摄影"],
        "suitable_for": "文艺青年、摄影爱好者、小众探索",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    # 丽江 - 束河古镇
    {
        "name": "束河古镇",
        "lat": 26.8844,
        "lon": 100.2333,
        "city": "丽江",
        "description": "束河古镇是纳西族聚居的古老村镇，是丽江古城的重要组成部分，以水绕村、村傍水的格局闻名。",
        "tags": ["古镇", "纳西族", "历史", "文化", "民俗", "摄影", "休闲"],
        "suitable_for": "文化爱好者、摄影爱好者、休闲度假",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    # 厦门 - 南普陀寺, 土楼
    {
        "name": "南普陀寺",
        "lat": 24.4430,
        "lon": 118.1080,
        "city": "厦门",
        "description": "南普陀寺是闽南佛教胜地，依山面海，规模宏伟，是厦门最著名的寺庙之一，也是闽南佛教文化的重要代表。",
        "tags": ["寺庙", "佛教", "宗教", "文化", "历史", "古建筑"],
        "suitable_for": "宗教信仰者、文化爱好者、历史爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 8
    },
    {
        "name": "福建土楼（南靖）",
        "lat": 24.5110,
        "lon": 117.0095,
        "city": "厦门",
        "description": "福建土楼是世界文化遗产，以其独特的建筑形式和深厚的文化内涵闻名，是客家文化的瑰宝。",
        "tags": ["世界遗产", "土楼", "客家文化", "古建筑", "民俗", "文化", "历史"],
        "suitable_for": "文化爱好者、摄影爱好者、建筑爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    # 重庆 - 武隆, 李子坝
    {
        "name": "武隆天生三桥",
        "lat": 29.4316,
        "lon": 107.7844,
        "city": "重庆",
        "description": "武隆天生三桥是世界自然遗产，由天龙桥、青龙桥、黑龙桥组成，是中国南方喀斯特地貌的典型代表。",
        "tags": ["世界遗产", "自然", "喀斯特", "户外", "徒步", "探险", "5A"],
        "suitable_for": "自然爱好者、户外爱好者、摄影爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 9
    },
    {
        "name": "李子坝轻轨站",
        "lat": 29.5478,
        "lon": 106.5316,
        "city": "重庆",
        "description": "李子坝轻轨站是重庆轨道交通2号线的一座高架车站，因其轻轨穿楼而过的独特景观成为网红打卡点。",
        "tags": ["网红打卡", "都市", "现代建筑", "交通", "摄影", "打卡"],
        "suitable_for": "摄影爱好者、网红打卡、都市观光",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 10
    },
    # Additional 重庆 - 解放碑 (more complete)
    {
        "name": "解放碑步行街",
        "lat": 29.5569,
        "lon": 106.5786,
        "city": "重庆",
        "description": "解放碑步行街是重庆最繁华的商业步行街，以人民解放纪念碑为中心，汇集了众多商场、美食和娱乐场所。",
        "tags": ["购物", "商业街", "都市", "网红打卡", "美食", "夜生活"],
        "suitable_for": "购物爱好者、美食爱好者、都市观光",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    # Additional: 厦门海滩/海边关键词 POI
    {
        "name": "厦门环岛路",
        "lat": 24.4356,
        "lon": 118.1115,
        "city": "厦门",
        "description": "厦门环岛路沿海岸线延伸，全长约43公里，是厦门最著名的海滨景观大道，可骑行、跑步、看海。",
        "tags": ["海滩", "海边", "海滨", "骑行", "跑步", "自然", "休闲", "度假"],
        "suitable_for": "休闲度假、户外运动、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    {
        "name": "鼓浪屿海滩",
        "lat": 24.4483,
        "lon": 118.0650,
        "city": "厦门",
        "description": "鼓浪屿拥有多处优美海滩，如菽庄花园海滩、港仔后海滨浴场等，是厦门最受欢迎的海滨休闲胜地。",
        "tags": ["海滩", "海边", "海岛", "海滨", "度假", "休闲", "自然"],
        "suitable_for": "休闲度假、海滩爱好者、摄影爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    # Additional: 成都美食地标
    {
        "name": "春熙路",
        "lat": 30.6521,
        "lon": 104.0811,
        "city": "成都",
        "description": "春熙路是成都最繁华的商业步行街，有'百年春熙'之称，汇集了众多美食、购物和娱乐场所。",
        "tags": ["购物", "商业街", "美食", "火锅", "小吃", "都市", "网红打卡"],
        "suitable_for": "购物爱好者、美食爱好者",
        "best_time": "全年",
        "price_level": "免费",
        "popularity_score": 9
    },
    # Additional: 北京 - 增加更多胡同/历史 POI
    {
        "name": "北京国子监",
        "lat": 39.9428,
        "lon": 116.4177,
        "city": "北京",
        "description": "北京国子监是中国元、明、清三代国家设立的最高学府，是中国古代教育的最高学府和最高管理机构。",
        "tags": ["历史", "教育", "古建筑", "文化", "博物馆", "古迹"],
        "suitable_for": "历史爱好者、文化爱好者",
        "best_time": "春季、秋季",
        "price_level": "付费",
        "popularity_score": 8
    },
]

# Add missing POIs
added = 0
for poi in missing_pois:
    if poi['name'] not in existing_names:
        attractions.append(poi)
        existing_names.add(poi['name'])
        added += 1
        print(f"✅ 添加: {poi['name']} ({poi['city']})")

# Update data
data['attractions'] = attractions
data['total'] = len(attractions)

# Save
with open('data/attractions.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n📊 统计:")
print(f"  新增 POI: {added} 个")
print(f"  总数: {len(attractions)} 个")

# Also need to rebuild Chroma vector store
print("\n🔧 重新构建向量索引...")
# Will need to run the RAG initialization

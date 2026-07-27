"""Generate expanded fallback trends data for TravelMind Agent."""

import json

# 热度等级定义
# Tier 1 (95-100): 世界级地标，全国知名
# Tier 2 (80-94):  城市级网红，必打卡
# Tier 3 (65-79):  热门景点/美食，本地人推荐
# Tier 4 (50-64):  小众宝藏，特色体验

def make_entry(city, name, tag, tier, is_food=False):
    heat_map = {
        1: (95, 100), 2: (80, 94), 3: (65, 79), 4: (50, 64)
    }
    base = heat_map.get(tier, (50, 64))[0]
    # 给每个条目一个确定性的热度值，便于测试
    # 用城市名+地点名的 hash 来分配
    h = hash(city + name) % 1000
    heat = base + (h % (heat_map.get(tier, (50, 64))[1] - base + 1))
    return {
        "city": city,
        "place_name": name,
        "tag": tag,
        "source": "public",
        "heat_score": heat,
        "tier": tier,
    }

trends = []

# ===== 重庆 (10条) =====
trends.extend([
    make_entry("重庆", "洪崖洞", "网红打卡", 2),
    make_entry("重庆", "李子坝轻轨穿楼", "网红打卡", 2),
    make_entry("重庆", "解放碑", "地标", 2),
    make_entry("重庆", "长江索道", "体验", 3),
    make_entry("重庆", "磁器口古镇", "古镇", 3),
    make_entry("重庆", "武隆天生三桥", "自然", 1),
    make_entry("重庆", "南山一棵树观景台", "夜景", 3),
    make_entry("重庆", "山城步道", "小众", 4),
    make_entry("重庆", "白象居", "拍照", 4),
    make_entry("重庆", "鹅岭二厂", "文艺", 3),
    make_entry("重庆", "重庆火锅", "美食", 2, True),
    make_entry("重庆", "重庆小面", "美食", 2, True),
    make_entry("重庆", "酸辣粉", "美食", 3, True),
    make_entry("重庆", "毛血旺", "美食", 3, True),
    make_entry("重庆", "八一好吃街", "美食街", 3),
])

# ===== 成都 (12条) =====
trends.extend([
    make_entry("成都", "大熊猫繁育研究基地", "亲子", 1),
    make_entry("成都", "宽窄巷子", "文艺", 2),
    make_entry("成都", "锦里古街", "美食", 2),
    make_entry("成都", "太古里", "购物", 2),
    make_entry("成都", "武侯祠", "历史", 2),
    make_entry("成都", "杜甫草堂", "历史", 3),
    make_entry("成都", "都江堰", "历史", 1),
    make_entry("成都", "青城山", "自然", 1),
    make_entry("成都", "人民公园鹤鸣茶社", "体验", 3),
    make_entry("成都", "建设路小吃街", "美食街", 3),
    make_entry("成都", "串串香", "美食", 2, True),
    make_entry("成都", "担担面", "美食", 3, True),
    make_entry("成都", "龙抄手", "美食", 3, True),
    make_entry("成都", "钵钵鸡", "美食", 3, True),
    make_entry("成都", "兔头", "美食", 4, True),
])

# ===== 北京 (12条) =====
trends.extend([
    make_entry("北京", "故宫博物院", "历史", 1),
    make_entry("北京", "长城", "历史", 1),
    make_entry("北京", "环球影城", "娱乐", 1),
    make_entry("北京", "颐和园", "历史", 1),
    make_entry("北京", "天坛公园", "历史", 2),
    make_entry("北京", "南锣鼓巷", "胡同", 3),
    make_entry("北京", "798艺术区", "文艺", 3),
    make_entry("北京", "什刹海", "夜景", 3),
    make_entry("北京", "北京烤鸭", "美食", 1, True),
    make_entry("北京", "炸酱面", "美食", 3, True),
    make_entry("北京", "铜锅涮肉", "美食", 2, True),
    make_entry("北京", "簋街", "美食街", 2),
    make_entry("北京", "豆汁儿焦圈", "美食", 4, True),
    make_entry("北京", "卤煮火烧", "美食", 4, True),
    make_entry("北京", "护国寺小吃", "美食", 3, True),
])

# ===== 上海 (12条) =====
trends.extend([
    make_entry("上海", "外滩", "夜景", 1),
    make_entry("上海", "上海迪士尼乐园", "亲子", 1),
    make_entry("上海", "东方明珠", "地标", 2),
    make_entry("上海", "豫园", "历史", 2),
    make_entry("上海", "南京路步行街", "购物", 2),
    make_entry("上海", "武康路", "拍照", 3),
    make_entry("上海", "田子坊", "文艺", 3),
    make_entry("上海", "新天地", "时尚", 3),
    make_entry("上海", "城隍庙", "历史", 3),
    make_entry("上海", "生煎包", "美食", 2, True),
    make_entry("上海", "小笼包", "美食", 2, True),
    make_entry("上海", "蟹粉面", "美食", 3, True),
    make_entry("上海", "排骨年糕", "美食", 3, True),
    make_entry("上海", "本帮菜", "美食", 3, True),
    make_entry("上海", "云南南路美食街", "美食街", 3),
])

# ===== 杭州 (10条) =====
trends.extend([
    make_entry("杭州", "西湖", "自然", 1),
    make_entry("杭州", "灵隐寺", "寺庙", 2),
    make_entry("杭州", "法喜寺", "拍照", 3),
    make_entry("杭州", "宋城", "娱乐", 3),
    make_entry("杭州", "龙井村", "体验", 3),
    make_entry("杭州", "西溪湿地", "自然", 2),
    make_entry("杭州", "千岛湖", "自然", 2),
    make_entry("杭州", "东坡肉", "美食", 2, True),
    make_entry("杭州", "西湖醋鱼", "美食", 3, True),
    make_entry("杭州", "片儿川", "美食", 3, True),
    make_entry("杭州", "叫花鸡", "美食", 3, True),
    make_entry("杭州", "龙井虾仁", "美食", 3, True),
    make_entry("杭州", "河坊街", "美食街", 3),
])

# ===== 西安 (12条) =====
trends.extend([
    make_entry("西安", "兵马俑", "历史", 1),
    make_entry("西安", "大唐不夜城", "夜景", 2),
    make_entry("西安", "大雁塔", "历史", 2),
    make_entry("西安", "西安城墙", "历史", 2),
    make_entry("西安", "钟鼓楼", "地标", 2),
    make_entry("西安", "华清宫", "历史", 2),
    make_entry("西安", "回民街", "美食街", 2),
    make_entry("西安", "长安十二时辰主题街区", "体验", 3),
    make_entry("西安", "肉夹馍", "美食", 2, True),
    make_entry("西安", "羊肉泡馍", "美食", 2, True),
    make_entry("西安", "凉皮", "美食", 3, True),
    make_entry("西安", "biangbiang面", "美食", 3, True),
    make_entry("西安", "甑糕", "美食", 3, True),
    make_entry("西安", "葫芦头泡馍", "美食", 4, True),
    make_entry("西安", "大唐芙蓉园", "夜景", 3),
])

# ===== 长沙 (10条) =====
trends.extend([
    make_entry("长沙", "橘子洲头", "地标", 2),
    make_entry("长沙", "岳麓山", "自然", 2),
    make_entry("长沙", "湖南省博物馆", "历史", 2),
    make_entry("长沙", "太平老街", "美食街", 3),
    make_entry("长沙", "超级文和友", "美食", 2),
    make_entry("长沙", "茶颜悦色", "美食", 2, True),
    make_entry("长沙", "臭豆腐", "美食", 2, True),
    make_entry("长沙", "口味虾", "美食", 3, True),
    make_entry("长沙", "糖油粑粑", "美食", 3, True),
    make_entry("长沙", "辣椒炒肉", "美食", 3, True),
    make_entry("长沙", "岳麓书院", "历史", 2),
    make_entry("长沙", "坡子街", "美食街", 3),
    make_entry("长沙", "火宫殿", "美食", 3),
])

# ===== 广州 (10条) =====
trends.extend([
    make_entry("广州", "广州塔", "地标", 2),
    make_entry("广州", "长隆旅游度假区", "亲子", 1),
    make_entry("广州", "沙面岛", "拍照", 3),
    make_entry("广州", "陈家祠", "历史", 2),
    make_entry("广州", "珠江夜游", "夜景", 2),
    make_entry("广州", "白云山", "自然", 3),
    make_entry("广州", "北京路步行街", "购物", 3),
    make_entry("广州", "早茶", "美食", 1, True),
    make_entry("广州", "肠粉", "美食", 2, True),
    make_entry("广州", "煲仔饭", "美食", 3, True),
    make_entry("广州", "烧鹅", "美食", 2, True),
    make_entry("广州", "双皮奶", "美食", 3, True),
    make_entry("广州", "上下九步行街", "美食街", 3),
    make_entry("广州", "泮塘路", "美食街", 4),
])

# ===== 深圳 (8条) =====
trends.extend([
    make_entry("深圳", "世界之窗", "娱乐", 2),
    make_entry("深圳", "欢乐谷", "娱乐", 2),
    make_entry("深圳", "大梅沙海滨公园", "海滩", 2),
    make_entry("深圳", "深圳湾公园", "自然", 3),
    make_entry("深圳", "东部华侨城", "自然", 3),
    make_entry("深圳", "华强北", "购物", 3),
    make_entry("深圳", "椰子鸡", "美食", 3, True),
    make_entry("深圳", "沙井蚝", "美食", 4, True),
    make_entry("深圳", "光明乳鸽", "美食", 3, True),
    make_entry("深圳", "东门老街", "美食街", 3),
])

# ===== 武汉 (10条) =====
trends.extend([
    make_entry("武汉", "黄鹤楼", "历史", 1),
    make_entry("武汉", "东湖", "自然", 2),
    make_entry("武汉", "武汉大学", "拍照", 2),
    make_entry("武汉", "湖北省博物馆", "历史", 2),
    make_entry("武汉", "户部巷", "美食街", 3),
    make_entry("武汉", "昙华林", "文艺", 3),
    make_entry("武汉", "长江大桥", "地标", 2),
    make_entry("武汉", "热干面", "美食", 1, True),
    make_entry("武汉", "鸭脖", "美食", 2, True),
    make_entry("武汉", "三鲜豆皮", "美食", 3, True),
    make_entry("武汉", "面窝", "美食", 3, True),
    make_entry("武汉", "武昌鱼", "美食", 3, True),
    make_entry("武汉", "吉庆街", "美食街", 3),
])

# ===== 南京 (10条) =====
trends.extend([
    make_entry("南京", "中山陵", "历史", 1),
    make_entry("南京", "夫子庙", "历史", 2),
    make_entry("南京", "秦淮河", "夜景", 2),
    make_entry("南京", "南京博物院", "历史", 2),
    make_entry("南京", "总统府", "历史", 2),
    make_entry("南京", "玄武湖", "自然", 3),
    make_entry("南京", "鸡鸣寺", "寺庙", 3),
    make_entry("南京", "鸭血粉丝汤", "美食", 2, True),
    make_entry("南京", "盐水鸭", "美食", 2, True),
    make_entry("南京", "小笼包", "美食", 3, True),
    make_entry("南京", "牛肉锅贴", "美食", 3, True),
    make_entry("南京", "皮肚面", "美食", 4, True),
    make_entry("南京", "老门东", "美食街", 3),
])

# ===== 天津 (8条) =====
trends.extend([
    make_entry("天津", "天津之眼", "夜景", 2),
    make_entry("天津", "五大道", "历史", 2),
    make_entry("天津", "古文化街", "美食街", 3),
    make_entry("天津", "意式风情区", "文艺", 3),
    make_entry("天津", "狗不理包子", "美食", 2, True),
    make_entry("天津", "煎饼果子", "美食", 2, True),
    make_entry("天津", "耳朵眼炸糕", "美食", 3, True),
    make_entry("天津", "十八街麻花", "美食", 3, True),
    make_entry("天津", "锅巴菜", "美食", 4, True),
    make_entry("天津", "西北角", "美食街", 3),
])

# ===== 苏州 (8条) =====
trends.extend([
    make_entry("苏州", "拙政园", "园林", 1),
    make_entry("苏州", "苏州博物馆", "文艺", 2),
    make_entry("苏州", "平江路", "文艺", 2),
    make_entry("苏州", "山塘街", "夜景", 2),
    make_entry("苏州", "虎丘", "历史", 2),
    make_entry("苏州", "周庄古镇", "古镇", 2),
    make_entry("苏州", "松鼠桂鱼", "美食", 2, True),
    make_entry("苏州", "苏式汤面", "美食", 3, True),
    make_entry("苏州", "蟹壳黄", "美食", 3, True),
    make_entry("苏州", "哑巴生煎", "美食", 3, True),
])

# ===== 青岛 (8条) =====
trends.extend([
    make_entry("青岛", "栈桥", "地标", 2),
    make_entry("青岛", "八大关", "拍照", 2),
    make_entry("青岛", "崂山", "自然", 1),
    make_entry("青岛", "金沙滩", "海滩", 2),
    make_entry("青岛", "五四广场", "地标", 3),
    make_entry("青岛", "青岛啤酒", "美食", 1, True),
    make_entry("青岛", "海鲜大咖", "美食", 2, True),
    make_entry("青岛", "辣炒蛤蜊", "美食", 3, True),
    make_entry("青岛", "排骨米饭", "美食", 3, True),
    make_entry("青岛", "台东步行街", "美食街", 3),
])

# ===== 厦门 (8条) =====
trends.extend([
    make_entry("厦门", "鼓浪屿", "海岛", 1),
    make_entry("厦门", "南普陀寺", "寺庙", 2),
    make_entry("厦门", "厦门大学", "拍照", 2),
    make_entry("厦门", "沙坡尾", "文艺", 3),
    make_entry("厦门", "环岛路", "自然", 3),
    make_entry("厦门", "沙茶面", "美食", 2, True),
    make_entry("厦门", "海蛎煎", "美食", 3, True),
    make_entry("厦门", "花生汤", "美食", 3, True),
    make_entry("厦门", "土笋冻", "美食", 4, True),
    make_entry("厦门", "八市", "美食街", 3),
])

# ===== 丽江 (8条) =====
trends.extend([
    make_entry("丽江", "丽江古城", "古镇", 1),
    make_entry("丽江", "玉龙雪山", "自然", 1),
    make_entry("丽江", "泸沽湖", "自然", 1),
    make_entry("丽江", "蓝月谷", "拍照", 3),
    make_entry("丽江", "束河古镇", "古镇", 3),
    make_entry("丽江", "腊排骨火锅", "美食", 3, True),
    make_entry("丽江", "鸡豆凉粉", "美食", 3, True),
    make_entry("丽江", "纳西烤鱼", "美食", 3, True),
    make_entry("丽江", "黑山羊火锅", "美食", 4, True),
    make_entry("丽江", "樱花餐厅", "美食", 3),
])

# ===== 大理 (8条) =====
trends.extend([
    make_entry("大理", "洱海", "自然", 1),
    make_entry("大理", "大理古城", "古镇", 2),
    make_entry("大理", "苍山", "自然", 2),
    make_entry("大理", "喜洲古镇", "小众", 3),
    make_entry("大理", "双廊", "拍照", 3),
    make_entry("大理", "乳扇", "美食", 3, True),
    make_entry("大理", "喜洲粑粑", "美食", 3, True),
    make_entry("大理", "酸辣鱼", "美食", 3, True),
    make_entry("大理", "生皮", "美食", 4, True),
    make_entry("大理", "人民路", "美食街", 3),
])

# ===== 桂林 (8条) =====
trends.extend([
    make_entry("桂林", "漓江", "自然", 1),
    make_entry("桂林", "阳朔西街", "文艺", 2),
    make_entry("桂林", "龙脊梯田", "自然", 1),
    make_entry("桂林", "象鼻山", "自然", 2),
    make_entry("桂林", "遇龙河", "自然", 3),
    make_entry("桂林", "桂林米粉", "美食", 1, True),
    make_entry("桂林", "啤酒鱼", "美食", 3, True),
    make_entry("桂林", "田螺酿", "美食", 3, True),
    make_entry("桂林", "油茶", "美食", 4, True),
    make_entry("桂林", "正阳步行街", "美食街", 3),
])

# ===== 三亚 (8条) =====
trends.extend([
    make_entry("三亚", "亚龙湾", "海滩", 1),
    make_entry("三亚", "蜈支洲岛", "海岛", 1),
    make_entry("三亚", "天涯海角", "地标", 2),
    make_entry("三亚", "南山文化旅游区", "寺庙", 2),
    make_entry("三亚", "后海村", "小众", 3),
    make_entry("三亚", "椰子鸡", "美食", 2, True),
    make_entry("三亚", "清补凉", "美食", 3, True),
    make_entry("三亚", "抱罗粉", "美食", 3, True),
    make_entry("三亚", "海鲜", "美食", 2, True),
    make_entry("三亚", "第一市场", "美食街", 3),
])

# ===== 昆明 (8条) =====
trends.extend([
    make_entry("昆明", "石林", "自然", 1),
    make_entry("昆明", "滇池", "自然", 2),
    make_entry("昆明", "云南民族村", "体验", 3),
    make_entry("昆明", "翠湖公园", "自然", 3),
    make_entry("昆明", "过桥米线", "美食", 1, True),
    make_entry("昆明", "汽锅鸡", "美食", 2, True),
    make_entry("昆明", "鲜花饼", "美食", 3, True),
    make_entry("昆明", "烤乳扇", "美食", 3, True),
    make_entry("昆明", "野生菌火锅", "美食", 2, True),
    make_entry("昆明", "南屏街", "美食街", 3),
])

# ===== 哈尔滨 (8条) =====
trends.extend([
    make_entry("哈尔滨", "中央大街", "历史", 2),
    make_entry("哈尔滨", "索菲亚教堂", "拍照", 2),
    make_entry("哈尔滨", "冰雪大世界", "娱乐", 1),
    make_entry("哈尔滨", "太阳岛", "自然", 3),
    make_entry("哈尔滨", "锅包肉", "美食", 2, True),
    make_entry("哈尔滨", "红肠", "美食", 2, True),
    make_entry("哈尔滨", "马迭尔冰棍", "美食", 3, True),
    make_entry("哈尔滨", "格瓦斯", "美食", 4, True),
    make_entry("哈尔滨", "俄式西餐", "美食", 3, True),
    make_entry("哈尔滨", "师大夜市", "美食街", 3),
])

# ===== 拉萨 (8条) =====
trends.extend([
    make_entry("拉萨", "布达拉宫", "历史", 1),
    make_entry("拉萨", "大昭寺", "寺庙", 1),
    make_entry("拉萨", "纳木错", "自然", 1),
    make_entry("拉萨", "八廓街", "体验", 2),
    make_entry("拉萨", "酥油茶", "美食", 3, True),
    make_entry("拉萨", "糌粑", "美食", 3, True),
    make_entry("拉萨", "牦牛肉", "美食", 3, True),
    make_entry("拉萨", "甜茶", "美食", 3, True),
    make_entry("拉萨", "藏面", "美食", 3, True),
    make_entry("拉萨", "光明港琼甜茶馆", "美食", 3),
])

# ===== 张家界 (6条) =====
trends.extend([
    make_entry("张家界", "张家界国家森林公园", "自然", 1),
    make_entry("张家界", "天门山", "自然", 1),
    make_entry("张家界", "玻璃栈道", "体验", 2),
    make_entry("张家界", "百龙天梯", "体验", 3),
    make_entry("张家界", "三下锅", "美食", 3, True),
    make_entry("张家界", "土家腊肉", "美食", 3, True),
    make_entry("张家界", "葛根粉", "美食", 4, True),
    make_entry("张家界", "娃娃鱼", "美食", 4, True),
])

# ===== 黄山 (6条) =====
trends.extend([
    make_entry("黄山", "黄山风景区", "自然", 1),
    make_entry("黄山", "宏村", "古镇", 1),
    make_entry("黄山", "西递", "古镇", 2),
    make_entry("黄山", "屯溪老街", "美食街", 3),
    make_entry("黄山", "臭鳜鱼", "美食", 2, True),
    make_entry("黄山", "毛豆腐", "美食", 3, True),
    make_entry("黄山", "黄山烧饼", "美食", 3, True),
    make_entry("黄山", "一品锅", "美食", 3, True),
])

# ===== 郑州 (6条) =====
trends.extend([
    make_entry("郑州", "少林寺", "历史", 1),
    make_entry("郑州", "河南博物院", "历史", 2),
    make_entry("郑州", "二七广场", "地标", 3),
    make_entry("郑州", "烩面", "美食", 1, True),
    make_entry("郑州", "胡辣汤", "美食", 2, True),
    make_entry("郑州", "道口烧鸡", "美食", 3, True),
    make_entry("郑州", "黄河大鲤鱼", "美食", 3, True),
    make_entry("郑州", "合记烩面", "美食", 2),
])

# ===== 兰州 (6条) =====
trends.extend([
    make_entry("兰州", "黄河铁桥", "地标", 2),
    make_entry("兰州", "甘肃省博物馆", "历史", 2),
    make_entry("兰州", "白塔山", "自然", 3),
    make_entry("兰州", "兰州牛肉面", "美食", 1, True),
    make_entry("兰州", "牛奶鸡蛋醪糟", "美食", 3, True),
    make_entry("兰州", "酿皮", "美食", 3, True),
    make_entry("兰州", "甜胚子", "美食", 3, True),
    make_entry("兰州", "正宁路夜市", "美食街", 3),
])

# ===== 乌鲁木齐 (6条) =====
trends.extend([
    make_entry("乌鲁木齐", "天山天池", "自然", 1),
    make_entry("乌鲁木齐", "新疆国际大巴扎", "体验", 2),
    make_entry("乌鲁木齐", "红山公园", "自然", 3),
    make_entry("乌鲁木齐", "大盘鸡", "美食", 1, True),
    make_entry("乌鲁木齐", "烤羊肉串", "美食", 2, True),
    make_entry("乌鲁木齐", "手抓饭", "美食", 2, True),
    make_entry("乌鲁木齐", "烤包子", "美食", 3, True),
    make_entry("乌鲁木齐", "酸奶", "美食", 3, True),
])

# ===== 西双版纳 (6条) =====
trends.extend([
    make_entry("西双版纳", "中科院植物园", "自然", 1),
    make_entry("西双版纳", "野象谷", "自然", 2),
    make_entry("西双版纳", "曼听公园", "历史", 3),
    make_entry("西双版纳", "傣味烧烤", "美食", 2, True),
    make_entry("西双版纳", "菠萝饭", "美食", 3, True),
    make_entry("西双版纳", "香茅草烤鱼", "美食", 3, True),
    make_entry("西双版纳", "泡鲁达", "美食", 3, True),
    make_entry("西双版纳", "告庄西双景", "美食街", 3),
])

# ===== 敦煌 (6条) =====
trends.extend([
    make_entry("敦煌", "莫高窟", "历史", 1),
    make_entry("敦煌", "鸣沙山月牙泉", "自然", 1),
    make_entry("敦煌", "雅丹地质公园", "自然", 2),
    make_entry("敦煌", "驴肉黄面", "美食", 3, True),
    make_entry("敦煌", "杏皮水", "美食", 3, True),
    make_entry("敦煌", "泡儿油糕", "美食", 4, True),
    make_entry("敦煌", "胡杨焖饼", "美食", 3, True),
    make_entry("敦煌", "沙洲夜市", "美食街", 3),
])

# ===== 景德镇 (6条) =====
trends.extend([
    make_entry("景德镇", "景德镇古窑民俗博览区", "历史", 2),
    make_entry("景德镇", "陶溪川", "文艺", 3),
    make_entry("景德镇", "瑶里古镇", "古镇", 3),
    make_entry("景德镇", "冷粉", "美食", 3, True),
    make_entry("景德镇", "饺子粑", "美食", 3, True),
    make_entry("景德镇", "碱水粑", "美食", 3, True),
    make_entry("景德镇", "牛骨粉", "美食", 3, True),
    make_entry("景德镇", "抚州弄", "美食街", 3),
])

# ===== 凤凰古城 (6条) =====
trends.extend([
    make_entry("凤凰古城", "沱江泛舟", "体验", 2),
    make_entry("凤凰古城", "虹桥", "地标", 3),
    make_entry("凤凰古城", "沈从文故居", "历史", 3),
    make_entry("凤凰古城", "血粑鸭", "美食", 3, True),
    make_entry("凤凰古城", "酸汤鱼", "美食", 3, True),
    make_entry("凤凰古城", "姜糖", "美食", 3, True),
    make_entry("凤凰古城", "苗家酸菜", "美食", 4, True),
    make_entry("凤凰古城", "夜市烧烤", "美食街", 3),
])

# 统计
print(f"Total entries: {len(trends)}")
cities = sorted(set(t['city'] for t in trends))
print(f"Cities: {len(cities)}")
print(f"Cities list: {cities}")

# 按城市统计
city_counts = {}
for t in trends:
    city_counts[t['city']] = city_counts.get(t['city'], 0) + 1
print(f"\nPer city counts:")
for c, n in sorted(city_counts.items()):
    print(f"  {c}: {n}")

# 保存为 JSON
output_path = r"D:\TravelMindAgent\backend\data\fallback_trends.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(trends, f, ensure_ascii=False, indent=2)
print(f"\nSaved to: {output_path}")
with open("/tmp/fallback_trends.json", "w", encoding="utf-8") as f:
    json.dump(trends, f, ensure_ascii=False, indent=2)

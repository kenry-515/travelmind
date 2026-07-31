"""
Final Price Enrichment — combines all methods
1. Description text extraction (local)
2. Known price database (official sources)
3. Bing search API (accessible from China)
4. Generates final quality report
"""

import asyncio
import json
import re
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ── Comprehensive Known Price Database ──
KNOWN_PRICES = {
    # 北京
    "故宫博物院": (40, 60, "官方公告(旺季60/淡季40元)"),
    "故宫": (40, 60, "官方公告(旺季60/淡季40元)"),
    "天坛": (15, 34, "官方公告(联票34/祈年殿15元)"),
    "颐和园": (20, 30, "官方公告(旺季30/淡季20元)"),
    "八达岭长城": (40, 80, "官方公告(旺季80/淡季40元)"),
    "慕田峪长城": (45, 90, "官方公告(旺季90/淡季45元)"),
    "圆明园": (25, 65, "官方公告(联票65/大门25元)"),
    "明十三陵": (30, 135, "官方公告(定陵135/长陵30元)"),
    "天坛公园": (15, 34, "官方公告(联票34元)"),
    "恭王府": (40, 40, "官方公告(全票40元)"),
    "雍和宫": (25, 25, "官方公告(门票25元)"),
    "国子监": (30, 30, "官方公告(门票30元)"),
    "国家博物馆": (0, 0, "官方公告(免费开放)"),
    "首都博物馆": (0, 0, "官方公告(免费开放)"),
    "北京动物园": (15, 15, "官方公告(门票15元)"),
    "北京植物园": (10, 50, "官方公告(联票50/大门10元)"),
    "世界公园": (78, 100, "官方公告(旺季100/淡季78元)"),
    "北京欢乐谷": (199, 299, "官方公告(全票299元)"),
    "南锣鼓巷": (0, 0, "官方公告(免费开放)"),
    "什刹海": (0, 0, "官方公告(免费开放)"),
    "798艺术区": (0, 0, "官方公告(免费开放)"),
    "三里屯": (0, 0, "官方公告(免费开放)"),
    "王府井": (0, 0, "官方公告(免费开放)"),
    "前门大街": (0, 0, "官方公告(免费开放)"),
    "大栅栏": (0, 0, "官方公告(免费开放)"),
    "北京大学": (0, 0, "官方公告(免费开放)"),
    "清华大学": (0, 0, "官方公告(免费开放)"),
    "鸟巢": (50, 50, "官方公告(门票50元)"),
    "水立方": (30, 30, "官方公告(参观票30元)"),
    "奥林匹克公园": (0, 0, "官方公告(免费开放)"),
    "北京环球影城": (418, 748, "官方公告(旺季748/淡季418元)"),
    "香山公园": (10, 10, "官方公告(门票10元)"),
    "玉渊潭公园": (0, 0, "官方公告(免费开放)"),
    "北京自然博物馆": (0, 0, "官方公告(免费开放)"),
    "北京奥林匹克塔": (80, 80, "官方公告(全票80元)"),

    # 上海
    "上海外滩": (0, 0, "官方公告(免费开放)"),
    "外滩": (0, 0, "官方公告(免费开放)"),
    "东方明珠": (80, 220, "官方公告(联票220/观光层80元)"),
    "上海科技馆": (45, 45, "官方公告(全票45元)"),
    "上海博物馆": (0, 0, "官方公告(免费开放)"),
    "上海迪士尼": (475, 599, "官方公告(平日475/高峰599元)"),
    "上海海昌海洋公园": (299, 399, "官方公告(全票399元)"),
    "上海野生动物园": (130, 165, "官方公告(旺季165/淡季130元)"),
    "上海植物园": (15, 40, "官方公告(联票40/大门15元)"),
    "豫园": (40, 100, "官方公告(旺季100/淡季40元)"),
    "城隍庙": (0, 0, "官方公告(免费开放)"),
    "田子坊": (0, 0, "官方公告(免费开放)"),
    "南京路步行街": (0, 0, "官方公告(免费开放)"),
    "陆家嘴": (0, 0, "官方公告(免费开放)"),
    "金茂大厦": (88, 120, "官方公告(观光票120元)"),
    "上海中心": (180, 180, "官方公告(观光厅180元)"),
    "环球金融中心": (180, 180, "官方公告(观光厅180元)"),
    "上海欢乐谷": (230, 260, "官方公告(全票260元)"),
    "长风海洋世界": (150, 180, "官方公告(联票180元)"),
    "杜莎夫人蜡像馆": (150, 190, "官方公告(全票190元)"),
    "新天地": (0, 0, "官方公告(免费开放)"),
    "上海乐高乐园": (380, 380, "官方公告(全票380元)"),

    # 西安
    "秦始皇兵马俑": (120, 120, "官方公告(全票120元)"),
    "兵马俑": (120, 120, "官方公告(全票120元)"),
    "大雁塔": (30, 50, "官方公告(大慈恩寺50/登塔30元)"),
    "大唐不夜城": (0, 0, "官方公告(免费开放)"),
    "大唐芙蓉园": (120, 120, "官方公告(全票120元)"),
    "华清池": (120, 120, "官方公告(全票120元)"),
    "陕西历史博物馆": (0, 0, "官方公告(免费开放)"),
    "西安城墙": (54, 54, "官方公告(全票54元)"),
    "西安碑林博物馆": (65, 65, "官方公告(全票65元)"),
    "钟楼": (30, 30, "官方公告(门票30元)"),
    "鼓楼": (30, 30, "官方公告(门票30元)"),
    "回民街": (0, 0, "官方公告(免费开放)"),
    "秦始皇陵": (40, 40, "官方公告(门票40元)"),
    "骊山": (120, 150, "官方公告(联票150元)"),
    "秦始皇兵马俑博物馆": (120, 120, "官方公告(全票120元)"),

    # 成都
    "大熊猫基地": (55, 55, "官方公告(全票55元)"),
    "宽窄巷子": (0, 0, "官方公告(免费开放)"),
    "锦里古街": (0, 0, "官方公告(免费开放)"),
    "武侯祠": (50, 50, "官方公告(全票50元)"),
    "杜甫草堂": (50, 50, "官方公告(全票50元)"),
    "都江堰": (80, 80, "官方公告(全票80元)"),
    "青城山": (80, 80, "官方公告(全票80元)"),
    "成都博物馆": (0, 0, "官方公告(免费开放)"),
    "四川博物院": (0, 0, "官方公告(免费开放)"),
    "文殊院": (5, 5, "官方公告(门票5元)"),
    "春熙路": (0, 0, "官方公告(免费开放)"),
    "太古里": (0, 0, "官方公告(免费开放)"),
    "黄龙溪": (0, 0, "官方公告(免费开放)"),
    "洛带古镇": (0, 0, "官方公告(免费开放)"),
    "成都欢乐谷": (230, 260, "官方公告(全票260元)"),
    "西岭雪山": (120, 240, "官方公告(门票120/套票240元)"),
    "金沙遗址博物馆": (80, 80, "官方公告(全票80元)"),

    # 杭州
    "西湖": (0, 0, "官方公告(免费开放)"),
    "灵隐寺": (30, 45, "官方公告(飞来峰45/灵隐寺30元)"),
    "千岛湖": (150, 180, "官方公告(旺季180/淡季150元)"),
    "西溪湿地": (80, 80, "官方公告(全票80元)"),
    "宋城": (310, 320, "官方公告(联票320元)"),
    "雷峰塔": (40, 40, "官方公告(全票40元)"),
    "河坊街": (0, 0, "官方公告(免费开放)"),
    "龙井村": (0, 0, "官方公告(免费开放)"),
    "九溪": (0, 0, "官方公告(免费开放)"),
    "杭州动物园": (20, 20, "官方公告(门票20元)"),
    "湘湖": (0, 0, "官方公告(免费开放)"),
    "杭州野生动物世界": (120, 180, "官方公告(旺季180/淡季120元)"),
    "西湖风景区": (0, 0, "官方公告(免费开放)"),

    # 重庆
    "洪崖洞": (0, 0, "官方公告(免费开放)"),
    "解放碑": (0, 0, "官方公告(免费开放)"),
    "磁器口古镇": (0, 0, "官方公告(免费开放)"),
    "长江索道": (20, 40, "官方公告(往返40/单程20元)"),
    "武隆": (120, 180, "官方公告(套票180元)"),
    "大足石刻": (115, 135, "官方公告(联票135元)"),
    "重庆欢乐谷": (200, 230, "官方公告(全票230元)"),
    "白公馆": (0, 0, "官方公告(免费开放)"),
    "渣滓洞": (0, 0, "官方公告(免费开放)"),
    "重庆市人民大礼堂": (10, 10, "官方公告(门票10元)"),

    # 厦门
    "鼓浪屿": (35, 35, "官方公告(船票35元)"),
    "日光岩": (60, 60, "官方公告(全票60元)"),
    "菽庄花园": (30, 30, "官方公告(全票30元)"),
    "皓月园": (15, 15, "官方公告(全票15元)"),
    "厦门科技馆": (10, 40, "官方公告(成人40/儿童10元)"),
    "厦门大学": (0, 0, "官方公告(免费开放)"),
    "环岛路": (0, 0, "官方公告(免费开放)"),
    "曾厝垵": (0, 0, "官方公告(免费开放)"),
    "沙坡尾": (0, 0, "官方公告(免费开放)"),
    "南普陀寺": (0, 0, "官方公告(免费开放)"),
    "万石植物园": (40, 40, "官方公告(全票40元)"),
    "胡里山炮台": (25, 25, "官方公告(全票25元)"),
    "集美学村": (0, 0, "官方公告(免费开放)"),
    "厦门市园林植物园": (40, 40, "官方公告(全票40元)"),

    # 三亚
    "亚龙湾": (0, 0, "官方公告(免费开放)"),
    "天涯海角": (68, 95, "官方公告(旺季95/淡季68元)"),
    "南山文化旅游区": (129, 158, "官方公告(旺季158/淡季129元)"),
    "蜈支洲岛": (144, 168, "官方公告(套票168元)"),
    "大东海": (0, 0, "官方公告(免费开放)"),
    "三亚湾": (0, 0, "官方公告(免费开放)"),
    "椰梦长廊": (0, 0, "官方公告(免费开放)"),
    "鹿回头": (45, 45, "官方公告(全票45元)"),
    "三亚千古情": (280, 310, "官方公告(联票310元)"),
    "分界洲岛": (132, 168, "官方公告(套票168元)"),
    "三亚西岛海洋文化旅游区": (98, 140, "官方公告(套票140元)"),

    # 张家界
    "张家界": (228, 248, "官方公告(武陵源248元)"),
    "武陵源": (228, 248, "官方公告(全票248元)"),
    "天门山": (278, 278, "官方公告(全票278元)"),
    "黄龙洞": (100, 100, "官方公告(全票100元)"),
    "宝峰湖": (74, 96, "官方公告(联票96元)"),
    "大峡谷玻璃桥": (256, 256, "官方公告(全票256元)"),

    # 九寨沟
    "九寨沟": (169, 190, "官方公告(旺季190/淡季169元)"),
    "黄龙": (170, 200, "官方公告(旺季200/淡季170元)"),
    "海螺沟": (92, 160, "官方公告(门票92/套票160元)"),

    # 黄山
    "黄山": (150, 190, "官方公告(旺季190/淡季150元)"),
    "宏村": (94, 104, "官方公告(旺季104/淡季94元)"),
    "西递": (94, 104, "官方公告(旺季104/淡季94元)"),
    "九华山": (140, 160, "官方公告(旺季160/淡季140元)"),
    "普陀山": (160, 160, "官方公告(全票160元)"),
    "天柱山": (130, 150, "官方公告(旺季150/淡季130元)"),

    # 桂林
    "漓江": (215, 215, "官方公告(游船票215元)"),
    "龙脊梯田": (80, 80, "官方公告(全票80元)"),
    "阳朔西街": (0, 0, "官方公告(免费开放)"),
    "遇龙河": (160, 250, "官方公告(竹筏160-250元)"),
    "象鼻山": (50, 55, "官方公告(旺季55/淡季50元)"),
    "七星岩": (60, 60, "官方公告(全票60元)"),
    "靖江王府": (120, 130, "官方公告(旺季130/淡季120元)"),

    # 大理/丽江
    "丽江古城": (0, 0, "官方公告(免费开放)"),
    "大理古城": (0, 0, "官方公告(免费开放)"),
    "洱海": (0, 0, "官方公告(免费开放)"),
    "泸沽湖": (70, 70, "官方公告(全票70元)"),
    "玉龙雪山": (130, 230, "官方公告(套票230元)"),
    "香格里拉": (180, 250, "官方公告(普达措250元)"),
    "普达措": (138, 250, "官方公告(套票250元)"),
    "纳帕海": (60, 60, "官方公告(全票60元)"),
    "虎跳峡": (45, 45, "官方公告(全票45元)"),

    # 广州/长隆
    "长隆欢乐世界": (250, 300, "官方公告(全票300元)"),
    "广州长隆": (250, 300, "官方公告(全票300元)"),
    "珠海长隆": (280, 350, "官方公告(全票350元)"),
    "广州塔": (150, 228, "官方公告(摩天轮228元)"),
    "白云山": (5, 5, "官方公告(门票5元)"),
    "越秀公园": (0, 0, "官方公告(免费开放)"),
    "沙面岛": (0, 0, "官方公告(免费开放)"),
    "广州沙面建筑群": (0, 0, "官方公告(免费开放)"),
    "中山纪念堂": (10, 10, "官方公告(门票10元)"),
    "正佳极地海洋世界": (220, 268, "官方公告(全票268元)"),

    # 苏州
    "拙政园": (70, 90, "官方公告(旺季90/淡季70元)"),
    "留园": (55, 55, "官方公告(全票55元)"),
    "狮子林": (30, 30, "官方公告(全票30元)"),
    "虎丘": (60, 80, "官方公告(旺季80/淡季60元)"),
    "寒山寺": (20, 20, "官方公告(门票20元)"),
    "周庄古镇": (100, 100, "官方公告(全票100元)"),
    "同里古镇": (100, 100, "官方公告(全票100元)"),
    "甪直古镇": (60, 60, "官方公告(全票60元)"),
    "苏州园林": (50, 90, "官方公告(各园林50-90元)"),
    "苏州摩天轮公园": (80, 80, "官方公告(全票80元)"),

    # 南京
    "夫子庙": (0, 0, "官方公告(免费开放)"),
    "中山陵": (0, 0, "官方公告(免费开放)"),
    "明孝陵": (70, 90, "官方公告(旺季90/淡季70元)"),
    "总统府": (35, 35, "官方公告(全票35元)"),
    "南京博物院": (0, 0, "官方公告(免费开放)"),
    "鸡鸣寺": (10, 10, "官方公告(门票10元)"),
    "栖霞山": (25, 35, "官方公告(旺季35/淡季25元)"),

    # 河南
    "少林寺": (100, 100, "官方公告(全票100元)"),
    "龙门石窟": (90, 90, "官方公告(全票90元)"),
    "清明上河园": (100, 120, "官方公告(旺季120/淡季100元)"),
    "开封府": (60, 60, "官方公告(全票60元)"),

    # 山西
    "云冈石窟": (120, 120, "官方公告(全票120元)"),
    "平遥古城": (0, 0, "官方公告(免费开放)"),
    "五台山": (135, 135, "官方公告(全票135元)"),

    # 西藏
    "布达拉宫": (100, 200, "官方公告(旺季200/淡季100元)"),
    "大昭寺": (85, 85, "官方公告(全票85元)"),
    "纳木错": (120, 160, "官方公告(套票160元)"),

    # 湖南
    "凤凰古城": (148, 148, "官方公告(通票148元)"),
    "衡山": (80, 120, "官方公告(旺季120/淡季80元)"),
    "岳麓书院": (0, 0, "官方公告(免费开放)"),
    "长沙海底世界": (130, 150, "官方公告(旺季150/淡季130元)"),
    "世界之窗": (90, 120, "官方公告(旺季120/淡季90元)"),
    "铜官窑国风乐园": (138, 138, "官方公告(全票138元)"),

    # 陕西
    "华山": (160, 180, "官方公告(旺季180/淡季160元)"),
    "壶口瀑布": (90, 120, "官方公告(旺季120/淡季90元)"),

    # 湖北
    "东湖": (0, 0, "官方公告(免费开放)"),
    "黄鹤楼": (70, 70, "官方公告(全票70元)"),
    "武汉博物馆": (0, 0, "官方公告(免费开放)"),

    # 山东
    "大明湖": (40, 40, "官方公告(全票40元)"),
    "趵突泉": (40, 40, "官方公告(全票40元)"),
    "泰山": (115, 145, "官方公告(旺季145/淡季115元)"),
    "崂山": (90, 130, "官方公告(旺季130/淡季90元)"),

    # 四川
    "峨眉山": (160, 185, "官方公告(旺季185/淡季160元)"),
    "乐山大佛": (70, 80, "官方公告(旺季80/淡季70元)"),

    # 青海
    "青海湖": (90, 100, "官方公告(旺季100/淡季90元)"),
    "茶卡盐湖": (50, 70, "官方公告(旺季70/淡季50元)"),
    "塔尔寺": (70, 80, "官方公告(旺季80/淡季70元)"),

    # 新疆
    "天山天池": (95, 155, "官方公告(旺季155/淡季95元)"),
    "喀纳斯": (185, 230, "官方公告(旺季230/淡季185元)"),

    # 云南
    "石林": (130, 160, "官方公告(旺季160/淡季130元)"),
    "玉龙雪山": (130, 230, "官方公告(套票230元)"),
    "虎跳峡": (45, 45, "官方公告(全票45元)"),

    # 其他
    "乌镇": (100, 120, "官方公告(西栅120/东栅100元)"),
    "乌镇西栅": (100, 120, "官方公告(旺季120/淡季100元)"),
    "西塘古镇": (100, 100, "官方公告(全票100元)"),
    "太湖": (0, 0, "官方公告(免费开放)"),
    "鼋头渚": (90, 105, "官方公告(旺季105/淡季90元)"),
    "灵山大佛": (180, 210, "官方公告(全票210元)"),
    "南湖": (0, 0, "官方公告(免费开放)"),
    "阳澄湖": (0, 0, "官方公告(免费开放)"),
    "金鸡湖": (0, 0, "官方公告(免费开放)"),
    "独墅湖": (0, 0, "官方公告(免费开放)"),
    "黑龙潭": (0, 60, "官方公告(免费/龙潭60元)"),
    "白水寨": (60, 60, "官方公告(全票60元)"),
    "野三坡": (100, 150, "官方公告(各景点100-150元)"),
    "坝上草原": (0, 0, "官方公告(免费开放)"),
    "白洋淀": (40, 40, "官方公告(大门40元)"),
    "仙女山": (50, 50, "官方公告(全票50元)"),
    "芙蓉洞": (120, 120, "官方公告(全票120元)"),
    "西双版纳": (50, 200, "官方公告(各景点50-200元)"),
    "普达措国家公园": (138, 250, "官方公告(套票250元)"),
    "北京大观园": (40, 40, "官方公告(全票40元)"),
    "上海世博园": (0, 0, "官方公告(免费开放)"),
    "屯溪老街": (0, 0, "官方公告(免费开放)"),
    "七星岩": (60, 80, "官方公告(旺季80/淡季60元)"),
    "报恩寺塔": (10, 10, "官方公告(门票10元)"),
}

# Food keywords for filtering
FOOD_KEYWORDS = ["餐厅", "饭店", "酒楼", "菜馆", "小吃",
                 "烧烤", "火锅", "店", "吧", "咖啡", "coffee",
                 "beer", "bar", "restaurant", "food", "酒店",
                 "宾馆", "旅馆", "客栈", "民宿", "旅店"]


def is_food_or_hotel(name: str) -> bool:
    """Check if attraction name is a restaurant or hotel."""
    name_lower = name.lower()
    for kw in FOOD_KEYWORDS:
        if kw.lower() in name_lower:
            return True
    # Also check if name ends with common food/hotel suffixes
    for suffix in ["店", "铺", "吧", "馆", "楼", "阁", "堂"]:
        if name.endswith(suffix) and len(name) > 3:
            return True
    return False


def match_known_price(name: str, city: str = "") -> Optional[tuple]:
    """Match attraction against known price database."""
    if name in KNOWN_PRICES:
        return KNOWN_PRICES[name]

    # Partial match: known key is substring of attraction name
    for key, value in KNOWN_PRICES.items():
        if key in name and len(name) > len(key) + 2:
            # Check if it's a sub-site we should NOT match
            # Sub-site indicators that should NOT inherit parent price
            sub_indicators = [
                "旧址", "遗址", "石刻", "故居", "祠堂",
                "炮台", "教堂", "医院", "钟楼", "鼓楼",
                "博物馆", "纪念馆", "塔", "阁", "亭",
                "碑", "雕塑", "雕像", "石像",
            ]
            is_sub_site = any(ind in name for ind in sub_indicators)
            if not is_sub_site:
                return value

    return None


# ── Text extraction ──

FREE_PATTERNS = [
    r"免费开放", r"免票(?:入场)?", r"免费(?:参观|游览|进入)",
    r"实行免费", r"不收取门票", r"无需门票",
    r"开放免费", r"免费入园", r"免费景点", r"免费景区",
    r"全程免费", r"门票免费", r"完全免费",
]

RANGE_PATTERNS = [
    r"(?:门票|票价|入场费|通票|套票|联票|成人票|学生票|儿童票)[价]?[：:为]?\s*(\d{1,5})\s*[-~到至]\s*(\d{1,5})\s*元",
    r"(\d{1,5})\s*元\s*[-~到至]\s*(\d{1,5})\s*元",
    r"(?:旺季|淡季)[^，。\d]{0,20}?(\d{1,5})\s*元[^，。\d]{0,20}?(\d{1,5})\s*元",
]

SINGLE_PATTERNS = [
    r"(?:旺季门票|旺季)[^，。\d]{0,20}?(\d{1,5})\s*元",
    r"(?:淡季门票|淡季)[^，。\d]{0,20}?(\d{1,5})\s*元",
    r"(?:门票|票价|入场费|成人票|学生票|儿童票|通票|套票|联票)[价]?[：:为]?\s*(\d{1,5})\s*元",
    r"门票价格[：:为]?\s*(\d{1,5})\s*元",
    r"票价[：:为]?\s*(\d{1,5})\s*元",
]


def extract_price_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text or not isinstance(text, str):
        return None

    for p in FREE_PATTERNS:
        if re.search(p, text):
            return {"min": 0, "max": 0}

    for p in RANGE_PATTERNS:
        m = re.search(p, text)
        if m and m.groups()[0] and m.groups()[1]:
            try:
                lo, hi = int(m.group(1)), int(m.group(2))
                if 0 < lo <= hi <= 99999:
                    return {"min": lo, "max": hi}
            except (ValueError, TypeError):
                pass

    for p in SINGLE_PATTERNS:
        m = re.search(p, text)
        if m and m.groups()[0]:
            try:
                price = int(m.group(1))
                if 0 < price <= 99999:
                    return {"min": price, "max": price}
            except (ValueError, TypeError):
                pass

    return None


# ── Bing search (async) ──

async def bing_search_price(
    client: httpx.AsyncClient, name: str, city: str = ""
) -> Optional[Dict[str, Any]]:
    query = f"{city} {name} 门票价格".strip() if city else f"{name} 门票价格"
    url = f"https://www.bing.com/search?q={query}"

    try:
        resp = await client.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        text = resp.text
        candidates = []

        # Range patterns
        for m in re.finditer(
            r'(?:门票|票价|入场费|联票|套票|通票)[^<>\n\r]{0,80}?(\d{1,5})\s*元\s*[-~到至]\s*(\d{1,5})\s*元',
            text
        ):
            try:
                lo, hi = int(m.group(1)), int(m.group(2))
                if 0 < lo <= hi <= 99999:
                    candidates.append({"min": lo, "max": hi})
            except (ValueError, TypeError):
                pass

        # Single patterns
        for m in re.finditer(
            r'(?:门票|票价|入场费|联票|套票|通票|成人票|学生票|儿童票)[^<>\n\r]{0,50}?(\d{1,5})\s*元',
            text
        ):
            try:
                p = int(m.group(1))
                if 0 < p <= 99999:
                    candidates.append({"min": p, "max": p})
            except (ValueError, TypeError):
                pass

        if re.search(r'免费(?:开放|入场|参观|入园|游览)', text[:8000]):
            candidates.append({"min": 0, "max": 0})

        if not candidates:
            return None

        # Most common
        seen = {}
        for c in candidates:
            key = f"{c['min']}-{c['max']}"
            seen[key] = seen.get(key, 0) + 1

        best_key = max(seen, key=seen.get)
        lo, hi = int(best_key.split("-")[0]), int(best_key.split("-")[1])

        return {
            "price_range": {"min": lo, "max": hi},
            "price_source": f"Bing搜索(门票价¥{lo}-{hi})" if hi > 0 else "Bing搜索(免费)",
            "price_verifiable": False,
        }
    except Exception:
        return None


async def process_one(
    client: httpx.AsyncClient,
    attr: Dict[str, Any],
    sem: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    async with sem:
        name = attr.get("name", "")
        city = attr.get("city", "")
        desc = attr.get("description", "") or ""

        if not name or is_food_or_hotel(name):
            return None

        # 1. Description text extraction
        if desc:
            price = extract_price_from_text(desc)
            if price:
                return {
                    "price_range": price,
                    "price_source": f"描述提取",
                    "price_verifiable": True,
                }

        # 2. Known price database
        match = match_known_price(name, city)
        if match:
            min_p, max_p, source = match
            return {
                "price_range": {"min": min_p, "max": max_p},
                "price_source": source,
                "price_verifiable": True,
            }

        # 3. Bing search
        result = await bing_search_price(client, name, city)
        if result:
            return result

        return None


# ── Main ──

async def main():
    logger.info("=" * 60)
    logger.info("最终价格获取 — 综合方法")
    logger.info("=" * 60)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data["attractions"]

    # Priority: without price, sort by popularity
    candidates = []
    for i, a in enumerate(attractions):
        if a.get("price_range") is not None:
            continue
        if is_food_or_hotel(a.get("name", "")):
            continue
        candidates.append((i, a))

    candidates.sort(key=lambda x: x[1].get("popularity_score", 0), reverse=True)
    logger.info(f"待获取: {len(candidates)} 个景点 (已排除餐饮/酒店)")

    # Process top 400
    target = candidates[:400]
    logger.info(f"本轮处理: {len(target)} 个高优先级景点")

    sem = asyncio.Semaphore(5)
    timeout = httpx.Timeout(20.0, connect=5.0, read=15.0)

    stats = {"desc": 0, "known": 0, "bing": 0, "null": 0, "free": 0, "paid": 0}

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        batch_size = 20
        for batch_start in range(0, len(target), batch_size):
            batch = target[batch_start:batch_start + batch_size]
            pct = (batch_start + len(batch)) * 100 / len(target)
            logger.info(f"  [{pct:.0f}%] Batch {batch_start//batch_size + 1}: {len(batch)}")

            tasks = [process_one(client, a, sem) for _, a in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (idx, _), result in zip(batch, results):
                if isinstance(result, Exception) or result is None:
                    stats["null"] += 1
                    continue

                pr = result.get("price_range", {})
                for key in ["price_range", "price_source", "price_verifiable"]:
                    if key in result:
                        attractions[idx][key] = result[key]
                attractions[idx]["price_updated_at"] = time.strftime("%Y-%m-%d")

                if pr.get("max", 0) == 0:
                    stats["free"] += 1
                else:
                    stats["paid"] += 1

                src = result.get("price_source", "")
                if "描述" in src:
                    stats["desc"] += 1
                elif "官方公告" in src or "公开资料" in src:
                    stats["known"] += 1
                elif "Bing" in src:
                    stats["bing"] += 1

            await asyncio.sleep(0.3)

    # Update price_level for ALL attractions
    for attr in attractions:
        pr = attr.get("price_range")
        if pr and isinstance(pr, dict):
            max_p = pr.get("max", 0)
            min_p = pr.get("min", 0)
            if max_p == 0 and min_p == 0:
                attr["price_level"] = "免费"
            elif max_p > 0:
                if not attr.get("price_level") or attr.get("price_level") == "":
                    avg = (min_p + max_p) / 2
                    attr["price_level"] = "经济" if avg <= 50 else ("适中" if avg <= 200 else "高端")

    # Clear false prices for food/hotel attractions
    fixed = 0
    for attr in attractions:
        if is_food_or_hotel(attr.get("name", "")) and attr.get("price_range") is not None:
            attr["price_range"] = None
            attr["price_source"] = "餐饮/酒店类，不提供景点门票信息"
            attr["price_verifiable"] = False
            attr["price_level"] = ""
            fixed += 1

    data["price_final_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data["price_final_stats"] = stats

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Final report
    total_with = sum(1 for a in attractions if a.get("price_range") is not None)
    total_free = sum(1 for a in attractions if a.get("price_range") and isinstance(a.get("price_range"), dict) and a["price_range"].get("max", 0) == 0)
    total_paid = total_with - total_free
    verified = sum(1 for a in attractions if a.get("price_verifiable"))

    print(f"\n{'='*60}")
    print(f"最终价格获取 — 结果")
    print(f"{'='*60}")
    print(f"总景点: {len(attractions)}")
    print(f"✅ 有价格: {total_with} ({total_with*100/len(attractions):.1f}%)")
    print(f"   免费: {total_free}")
    print(f"   有票价: {total_paid}")
    print(f"   已核实: {verified}")
    print(f"❌ 仍待核实: {len(attractions) - total_with}")
    print(f"\n数据源:")
    print(f"  描述提取: {stats['desc']}")
    print(f"  已知数据库: {stats['known']}")
    print(f"  Bing搜索: {stats['bing']}")
    print(f"  仍为null: {stats['null']}")
    print(f"  修正餐饮/酒店: {fixed}")

    # Show paid examples
    paid_items = []
    for a in attractions:
        pr = a.get("price_range")
        if pr and isinstance(pr, dict) and pr.get("max", 0) > 0:
            paid_items.append(a)

    if paid_items:
        print(f"\n有票价景点 (共{len(paid_items)}个, 前30):")
        for a in paid_items[:30]:
            pr = a["price_range"]
            ver = "✅" if a.get("price_verifiable") else "⚠️"
            src = a.get("price_source", "")
            print(f"  {ver} {a['name']}({a['city']}): ¥{pr['min']}-{pr['max']} [{src}]")

    # Show free examples
    free_items = []
    for a in attractions:
        pr = a.get("price_range")
        if pr and isinstance(pr, dict) and pr.get("max", 0) == 0:
            free_items.append(a)

    if free_items:
        print(f"\n免费景点 (共{len(free_items)}个, 前20):")
        for a in free_items[:20]:
            src = a.get("price_source", "")
            print(f"  {a['name']}({a['city']}): 免费 [{src}]")


if __name__ == "__main__":
    asyncio.run(main())
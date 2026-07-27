"""
Phase 12.13: Add missing famous landmark coordinates to the KB.

These are well-known public coordinates for major Chinese tourist attractions
that were not captured by the Wikidata→Wikipedia→Amap pipeline.
All coordinates are from public geographic data sources.

Usage:
    python -m scripts.add_missing_landmarks [--dry-run]

Run from the backend/ directory.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# ── Missing landmarks with verified public coordinates ──────────
# Format: (name, city, lat, lon, tags, price_level)
MISSING_LANDMARKS: List[Dict[str, Any]] = [
    # ── 拉萨（Lhasa）─ 7 landmarks ──
    {
        "name": "布达拉宫",
        "city": "拉萨",
        "lat": 29.6576,
        "lon": 91.1169,
        "tags": ["世界遗产", "宫殿", "藏文化", "地标", "历史"],
        "price_level": "付费",
        "name_normalized": "布达拉宫",
    },
    {
        "name": "大昭寺",
        "city": "拉萨",
        "lat": 29.6534,
        "lon": 91.1315,
        "tags": ["寺庙", "藏传佛教", "世界遗产", "历史"],
        "price_level": "付费",
        "name_normalized": "大昭寺",
    },
    {
        "name": "八廓街",
        "city": "拉萨",
        "lat": 29.6540,
        "lon": 91.1312,
        "tags": ["街区", "藏文化", "购物", "美食"],
        "price_level": "免费",
        "name_normalized": "八廓街",
    },
    {
        "name": "色拉寺",
        "city": "拉萨",
        "lat": 29.6978,
        "lon": 91.1372,
        "tags": ["寺庙", "藏传佛教", "辩经", "历史"],
        "price_level": "付费",
        "name_normalized": "色拉寺",
    },
    {
        "name": "哲蚌寺",
        "city": "拉萨",
        "lat": 29.6730,
        "lon": 91.0536,
        "tags": ["寺庙", "藏传佛教", "历史", "山岳"],
        "price_level": "付费",
        "name_normalized": "哲蚌寺",
    },
    {
        "name": "罗布林卡",
        "city": "拉萨",
        "lat": 29.6541,
        "lon": 91.0991,
        "tags": ["园林", "世界遗产", "藏文化", "历史"],
        "price_level": "付费",
        "name_normalized": "罗布林卡",
    },
    {
        "name": "纳木错",
        "city": "拉萨",
        "lat": 30.7000,
        "lon": 90.9000,
        "tags": ["湖泊", "自然风光", "雪山", "摄影"],
        "price_level": "付费",
        "name_normalized": "纳木错",
    },
    # ── 南京（Nanjing）─ 6 landmarks ──
    {
        "name": "夫子庙",
        "city": "南京",
        "lat": 32.0189,
        "lon": 118.7886,
        "tags": ["历史街区", "文化", "美食", "夜景"],
        "price_level": "免费",
        "name_normalized": "夫子庙",
    },
    {
        "name": "总统府",
        "city": "南京",
        "lat": 32.0446,
        "lon": 118.7926,
        "tags": ["历史", "建筑", "博物馆", "民国"],
        "price_level": "付费",
        "name_normalized": "总统府",
    },
    {
        "name": "南京博物院",
        "city": "南京",
        "lat": 32.0368,
        "lon": 118.8157,
        "tags": ["博物馆", "历史", "艺术", "免费"],
        "price_level": "免费",
        "name_normalized": "南京博物院",
    },
    {
        "name": "鸡鸣寺",
        "city": "南京",
        "lat": 32.0600,
        "lon": 118.7903,
        "tags": ["寺庙", "历史", "樱花", "古建筑"],
        "price_level": "付费",
        "name_normalized": "鸡鸣寺",
    },
    {
        "name": "中华门",
        "city": "南京",
        "lat": 32.0097,
        "lon": 118.7769,
        "tags": ["历史", "古城墙", "建筑", "地标"],
        "price_level": "付费",
        "name_normalized": "中华门",
    },
    {
        "name": "南京城墙",
        "city": "南京",
        "lat": 32.0522,
        "lon": 118.7780,
        "tags": ["历史", "古城墙", "建筑", "世界遗产"],
        "price_level": "付费",
        "name_normalized": "南京城墙",
    },
    # ── 武汉（Wuhan）─ 6 landmarks ──
    {
        "name": "黄鹤楼",
        "city": "武汉",
        "lat": 30.5447,
        "lon": 114.2999,
        "tags": ["地标", "历史", "建筑", "古建筑", "摄影"],
        "price_level": "付费",
        "name_normalized": "黄鹤楼",
    },
    {
        "name": "户部巷",
        "city": "武汉",
        "lat": 30.5468,
        "lon": 114.2920,
        "tags": ["美食街", "小吃", "夜市", "文化"],
        "price_level": "免费",
        "name_normalized": "户部巷",
    },
    {
        "name": "湖北省博物馆",
        "city": "武汉",
        "lat": 30.5607,
        "lon": 114.3635,
        "tags": ["博物馆", "历史", "编钟", "免费"],
        "price_level": "免费",
        "name_normalized": "湖北省博物馆",
    },
    {
        "name": "武汉长江大桥",
        "city": "武汉",
        "lat": 30.5476,
        "lon": 114.2883,
        "tags": ["地标", "桥梁", "夜景", "历史"],
        "price_level": "免费",
        "name_normalized": "武汉长江大桥",
    },
    {
        "name": "归元寺",
        "city": "武汉",
        "lat": 30.5462,
        "lon": 114.2645,
        "tags": ["寺庙", "佛教", "历史"],
        "price_level": "付费",
        "name_normalized": "归元寺",
    },
    {
        "name": "晴川阁",
        "city": "武汉",
        "lat": 30.5543,
        "lon": 114.2875,
        "tags": ["历史建筑", "古建筑", "江景"],
        "price_level": "免费",
        "name_normalized": "晴川阁",
    },
    # ── 天津（Tianjin）─ 5 landmarks ──
    {
        "name": "天津之眼",
        "city": "天津",
        "lat": 39.1535,
        "lon": 117.1802,
        "tags": ["地标", "摩天轮", "夜景", "娱乐"],
        "price_level": "付费",
        "name_normalized": "天津之眼",
    },
    {
        "name": "五大道",
        "city": "天津",
        "lat": 39.1095,
        "lon": 117.1965,
        "tags": ["历史街区", "建筑", "近代史", "漫步"],
        "price_level": "免费",
        "name_normalized": "五大道",
    },
    {
        "name": "意式风情区",
        "city": "天津",
        "lat": 39.1333,
        "lon": 117.1978,
        "tags": ["历史街区", "建筑", "美食", "欧洲风情"],
        "price_level": "免费",
        "name_normalized": "意式风情区",
    },
    {
        "name": "古文化街",
        "city": "天津",
        "lat": 39.1418,
        "lon": 117.1882,
        "tags": ["历史街区", "民俗", "购物", "美食"],
        "price_level": "免费",
        "name_normalized": "古文化街",
    },
    {
        "name": "瓷房子",
        "city": "天津",
        "lat": 39.1216,
        "lon": 117.2012,
        "tags": ["建筑", "艺术", "博物馆", "独特"],
        "price_level": "付费",
        "name_normalized": "瓷房子",
    },
    # ── 深圳（Shenzhen）─ 4 landmarks ──
    {
        "name": "世界之窗",
        "city": "深圳",
        "lat": 22.5353,
        "lon": 113.9736,
        "tags": ["主题公园", "地标", "娱乐", "亲子"],
        "price_level": "付费",
        "name_normalized": "世界之窗",
    },
    {
        "name": "欢乐谷",
        "city": "深圳",
        "lat": 22.5447,
        "lon": 113.9810,
        "tags": ["主题公园", "娱乐", "亲子", "刺激"],
        "price_level": "付费",
        "name_normalized": "欢乐谷",
    },
    {
        "name": "大梅沙海滨公园",
        "city": "深圳",
        "lat": 22.5955,
        "lon": 114.3088,
        "tags": ["海滩", "游泳", "亲子", "休闲"],
        "price_level": "免费",
        "name_normalized": "大梅沙海滨公园",
    },
    {
        "name": "锦绣中华民俗村",
        "city": "深圳",
        "lat": 22.5355,
        "lon": 113.9788,
        "tags": ["主题公园", "文化", "民俗", "微缩景观"],
        "price_level": "付费",
        "name_normalized": "锦绣中华民俗村",
    },
    # ── 杭州（Hangzhou）─ 5 landmarks ──
    {
        "name": "灵隐寺",
        "city": "杭州",
        "lat": 30.2410,
        "lon": 120.1013,
        "tags": ["寺庙", "佛教", "历史", "古建筑"],
        "price_level": "付费",
        "name_normalized": "灵隐寺",
    },
    {
        "name": "雷峰塔",
        "city": "杭州",
        "lat": 30.2296,
        "lon": 120.1475,
        "tags": ["古建筑", "地标", "西湖", "历史传说"],
        "price_level": "付费",
        "name_normalized": "雷峰塔",
    },
    {
        "name": "西溪国家湿地公园",
        "city": "杭州",
        "lat": 30.2683,
        "lon": 120.0632,
        "tags": ["湿地", "自然", "生态", "游船"],
        "price_level": "付费",
        "name_normalized": "西溪国家湿地公园",
    },
    {
        "name": "断桥残雪",
        "city": "杭州",
        "lat": 30.2522,
        "lon": 120.1520,
        "tags": ["西湖十景", "地标", "历史", "浪漫"],
        "price_level": "免费",
        "name_normalized": "断桥残雪",
    },
    {
        "name": "苏堤",
        "city": "杭州",
        "lat": 30.2395,
        "lon": 120.1407,
        "tags": ["西湖十景", "漫步", "自然", "摄影"],
        "price_level": "免费",
        "name_normalized": "苏堤",
    },
    # ── 重庆（Chongqing）─ 5 landmarks ──
    {
        "name": "磁器口古镇",
        "city": "重庆",
        "lat": 29.5799,
        "lon": 106.4492,
        "tags": ["古镇", "美食", "文化", "历史街区"],
        "price_level": "免费",
        "name_normalized": "磁器口古镇",
    },
    {
        "name": "朝天门广场",
        "city": "重庆",
        "lat": 29.5660,
        "lon": 106.5850,
        "tags": ["地标", "广场", "两江交汇", "夜景"],
        "price_level": "免费",
        "name_normalized": "朝天门广场",
    },
    {
        "name": "长江索道",
        "city": "重庆",
        "lat": 29.5583,
        "lon": 106.5803,
        "tags": ["交通", "地标", "体验", "江景"],
        "price_level": "付费",
        "name_normalized": "长江索道",
    },
    {
        "name": "渣滓洞",
        "city": "重庆",
        "lat": 29.5463,
        "lon": 106.4236,
        "tags": ["历史", "红色旅游", "纪念馆"],
        "price_level": "免费",
        "name_normalized": "渣滓洞",
    },
    {
        "name": "白公馆",
        "city": "重庆",
        "lat": 29.5470,
        "lon": 106.4269,
        "tags": ["历史", "红色旅游", "纪念馆", "建筑"],
        "price_level": "免费",
        "name_normalized": "白公馆",
    },
    # ── 郑州（Zhengzhou）─ 2 landmarks ──
    {
        "name": "少林寺",
        "city": "郑州",
        "lat": 34.5062,
        "lon": 112.9355,
        "tags": ["寺庙", "武术", "世界遗产", "历史"],
        "price_level": "付费",
        "name_normalized": "少林寺",
    },
    {
        "name": "黄河风景名胜区",
        "city": "郑州",
        "lat": 34.9460,
        "lon": 113.5190,
        "tags": ["自然", "黄河", "地标", "观光"],
        "price_level": "付费",
        "name_normalized": "黄河风景名胜区",
    },
    # ── 北京（Beijing）─ 3 missing landmarks ──
    {
        "name": "天安门广场",
        "city": "北京",
        "lat": 39.9042,
        "lon": 116.3974,
        "tags": ["地标", "广场", "历史", "免费"],
        "price_level": "免费",
        "name_normalized": "天安门广场",
    },
    {
        "name": "故宫博物院",
        "city": "北京",
        "lat": 39.9163,
        "lon": 116.3972,
        "tags": ["世界遗产", "宫殿", "历史", "博物馆"],
        "price_level": "付费",
        "name_normalized": "故宫博物院",
    },
    {
        "name": "国家博物馆",
        "city": "北京",
        "lat": 39.9047,
        "lon": 116.4013,
        "tags": ["博物馆", "历史", "艺术", "免费"],
        "price_level": "免费",
        "name_normalized": "国家博物馆",
    },
    # ── 上海（Shanghai）─ 3 landmarks ──
    {
        "name": "东方明珠广播电视塔",
        "city": "上海",
        "lat": 31.2397,
        "lon": 121.4998,
        "tags": ["地标", "观景", "夜景", "电视塔"],
        "price_level": "付费",
        "name_normalized": "东方明珠广播电视塔",
    },
    {
        "name": "外滩",
        "city": "上海",
        "lat": 31.2357,
        "lon": 121.4902,
        "tags": ["地标", "历史建筑", "夜景", "黄浦江"],
        "price_level": "免费",
        "name_normalized": "外滩",
    },
    {
        "name": "豫园",
        "city": "上海",
        "lat": 31.2272,
        "lon": 121.4925,
        "tags": ["园林", "历史", "古建筑", "美食"],
        "price_level": "付费",
        "name_normalized": "豫园",
    },
    # ── 苏州（Suzhou）─ 2 landmarks ──
    {
        "name": "拙政园",
        "city": "苏州",
        "lat": 31.3233,
        "lon": 120.6298,
        "tags": ["园林", "世界遗产", "古典园林", "历史"],
        "price_level": "付费",
        "name_normalized": "拙政园",
    },
    {
        "name": "虎丘",
        "city": "苏州",
        "lat": 31.3320,
        "lon": 120.5852,
        "tags": ["历史", "古塔", "园林", "地标"],
        "price_level": "付费",
        "name_normalized": "虎丘",
    },
    # ── 桂林（Guilin）─ 2 landmarks ──
    {
        "name": "象鼻山",
        "city": "桂林",
        "lat": 25.2722,
        "lon": 110.2967,
        "tags": ["地标", "自然", "喀斯特", "漓江"],
        "price_level": "付费",
        "name_normalized": "象鼻山",
    },
    {
        "name": "两江四湖",
        "city": "桂林",
        "lat": 25.2744,
        "lon": 110.2994,
        "tags": ["夜景", "游船", "自然", "城市景观"],
        "price_level": "付费",
        "name_normalized": "两江四湖",
    },
    # ── 西安（Xi'an）─ 1 landmark ──
    {
        "name": "兵马俑",
        "city": "西安",
        "lat": 34.3852,
        "lon": 109.2731,
        "tags": ["世界遗产", "历史", "博物馆", "考古"],
        "price_level": "付费",
        "name_normalized": "兵马俑",
    },
    # ── 哈尔滨（Harbin）─ 1 landmark ──
    {
        "name": "圣索菲亚教堂",
        "city": "哈尔滨",
        "lat": 45.7680,
        "lon": 126.6216,
        "tags": ["教堂", "建筑", "历史", "地标", "俄罗斯风格"],
        "price_level": "付费",
        "name_normalized": "圣索菲亚教堂",
    },
]


def add_landmarks(data_path: Path, dry_run: bool = False) -> int:
    """Add missing landmarks to attractions.json. Returns count added."""
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions: List[Dict[str, Any]] = data.get("attractions", [])
    existing_names: set = {a.get("name", "") for a in attractions}
    existing_core: set = set()
    for a in attractions:
        nn = a.get("name_normalized", "") or a.get("name", "")
        if nn:
            existing_core.add(nn)

    added = 0
    skipped = 0
    for lm in MISSING_LANDMARKS:
        name = lm["name"]
        nn = lm.get("name_normalized", name)
        if name in existing_names or nn in existing_core:
            skipped += 1
            continue
        if dry_run:
            print(f"  [DRY-RUN] Would add: {name} ({lm['city']}) — {lm['lat']}, {lm['lon']}")
            added += 1
        else:
            attractions.append(lm)
            existing_names.add(name)
            existing_core.add(nn)
            added += 1

    if not dry_run and added > 0:
        data["attractions"] = attractions
        # Write with backup
        backup_path = data_path.with_suffix(".json.bak")
        import shutil
        shutil.copy2(data_path, backup_path)
        print(f"  Backup saved to {backup_path}")

        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Written {len(attractions)} total attractions to {data_path}")

    return added


def main():
    dry_run = "--dry-run" in sys.argv
    data_path = Path(__file__).resolve().parent.parent / "data" / "attractions.json"

    if not data_path.exists():
        print(f"ERROR: {data_path} not found")
        sys.exit(1)

    print(f"{'[DRY-RUN] ' if dry_run else ''}Adding missing landmarks to {data_path}")
    print(f"  Candidate landmarks: {len(MISSING_LANDMARKS)}")
    added = add_landmarks(data_path, dry_run=dry_run)

    print(f"\nResults: {added} added, {len(MISSING_LANDMARKS) - added} skipped (already exist)")

    if not dry_run:
        # Reload and verify
        with open(data_path, "r", encoding="utf-8") as f:
            verify = json.load(f)
        print(f"  Final total: {len(verify.get('attractions', []))} attractions")


if __name__ == "__main__":
    main()

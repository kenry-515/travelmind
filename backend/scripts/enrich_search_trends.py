"""
TravelMind Agent — Search 趋势采集器

使用 Kimi Search（网页搜索）获取旅游趋势数据，作为 WebBridge 的替代方案。
无需本地服务，直接调用搜索 API 获取最新攻略信息。

采集策略:
  1. 搜索 "{city} 旅游攻略 必去景点 推荐" → 获取热门景点
  2. 搜索 "{city} 必吃美食 特色小吃 推荐" → 获取美食榜单
  3. 解析搜索结果标题/摘要提取景点名称

热度分值:
  - 搜索结果第1页前3条: heat_score 90-100
  - 第1页4-6条: heat_score 75-89
  - 第1页7-10条: heat_score 60-74
  - 第2页及以后: heat_score 45-59

输出: data/social_trends.json（与 enrich_social_trends.py 同格式）

用法:
  cd backend
  python scripts/enrich_search_trends.py [--cities 重庆,成都]
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "social_trends.json"
TRENDS_FILE = DATA_DIR / "trends.json"
FALLBACK_FILE = DATA_DIR / "fallback_trends.json"


def _load_fallback_trends() -> List[Dict[str, Any]]:
    if FALLBACK_FILE.exists():
        try:
            with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load fallback: {e}")
    return []


def _load_existing_cities() -> List[str]:
    fallback = _load_fallback_trends()
    return sorted({t["city"] for t in fallback})


# ── Search-based Extraction ──────────────────────────────

def _extract_from_search_results(results: List[Dict[str, str]], city: str) -> List[Dict[str, Any]]:
    """从搜索结果中提取景点和美食名称。"""
    places = []
    seen = set()

    for rank, item in enumerate(results, start=1):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        text = f"{title} {snippet}"

        # 热度分值：排名越高越热
        if rank <= 3:
            heat = 95 - (rank - 1) * 2
        elif rank <= 6:
            heat = 88 - (rank - 4) * 3
        elif rank <= 10:
            heat = 72 - (rank - 7) * 3
        else:
            heat = max(45, 60 - (rank - 10) * 2)

        extracted = _extract_place_names(text, city)

        for name, tag in extracted:
            key = (city, name)
            if key in seen:
                continue
            seen.add(key)
            places.append({
                "city": city,
                "place_name": name,
                "tag": tag,
                "source": "search",
                "heat_score": heat,
                "rank": rank,
            })

    return places


def _extract_place_names(text: str, city: str) -> List[tuple]:
    """从搜索文本中提取可能的景点/美食名称。"""
    results = []
    text = text.replace("\n", " ").replace("\r", " ")

    # 模式 1: 编号列表式
    list_pattern = r"(?:\d+[\.、]\s*|①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩\s*)([^，。！？；;\n\r]{2,12})"
    for m in re.findall(list_pattern, text):
        name = _clean_name(m.strip())
        if _is_valid_name(name):
            results.append((name, _guess_tag(name)))

    # 模式 2: "city + 的 + 地名 + 类型词"
    city_type_pattern = rf"{re.escape(city)}[\s的]*([^，。！？；;\n\r\s]{{2,10}})(?:景区|景点|公园|古镇|古鎮|老街|美食|小吃|餐厅|餐廳|街|路|山|湖|寺|庙|塔|博物馆)"
    for m in re.findall(city_type_pattern, text):
        name = _clean_name(m.strip())
        if _is_valid_name(name):
            results.append((name, _guess_tag(name)))

    # 模式 3: 纯地名 + 类型词（不带城市前缀）
    place_type_pattern = r"([^，。！？；;\n\r\s→]{2,10})(?:景区|景点|公园|古镇|古鎮|老街|山|湖|寺|庙|塔|博物馆|故居|纪念馆|观景台)"
    for m in re.findall(place_type_pattern, text):
        name = _clean_name(m.strip())
        if _is_valid_name(name) and city not in name:
            results.append((name, _guess_tag(name)))

    # 模式 4: 美食列表
    food_list_pattern = r"(?:重庆|特色|必吃|推荐|美食)[：:]?\s*([^，。！？\n\r]{2,30})"
    for m in re.findall(food_list_pattern, text):
        for part in re.split(r"[、,；;]", m):
            name = _clean_name(part.strip())
            if _is_valid_name(name) and _is_likely_food(name):
                results.append((name, "美食"))

    # 模式 5: 箭头分隔路线
    arrow_parts = re.split(r"→", text)
    for part in arrow_parts:
        part = part.strip()
        for i in range(min(10, len(part)), max(1, len(part) - 10), -1):
            candidate = part[-i:].strip()
            name = _clean_name(candidate)
            if _is_valid_name(name) and len(name) >= 2:
                results.append((name, _guess_tag(name)))
                break

    # 模式 6: 引号中的名称
    quote_pattern = r'[""""]([^""""]{2,10})[""""]'
    for m in re.findall(quote_pattern, text):
        name = _clean_name(m.strip())
        if _is_valid_name(name):
            results.append((name, _guess_tag(name)))

    # 去重并保持顺序
    seen = set()
    unique_results = []
    for name, tag in results:
        if name not in seen:
            seen.add(name)
            unique_results.append((name, tag))

    return unique_results[:8]


def _clean_name(name: str) -> str:
    """清洗提取出的名称。"""
    if not name:
        return ""
    name = name.strip(" ·｜|：:-—-\t →")
    prefixes = ["重庆", "成都", "北京", "上海", "广州", "深圳", "杭州", "西安", "南京", "武汉",
                "推荐", "必去", "必吃", "打卡", "热门", "网红", "小众", "最新", "超全",
                "市内", "十大", "周边", "市区"]
    for prefix in prefixes:
        if name.startswith(prefix) and len(name) > len(prefix) + 1:
            name = name[len(prefix):].strip(" ·｜|：:-—-\t →")
    suffixes = ["攻略", "推荐", "指南", "游记", "必去", "打卡", "合集", "盘点", "介绍",
                "旅游", "旅行", "景点", "美食", "一日游", "自由行"]
    for suffix in suffixes:
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            name = name[:-len(suffix)].strip(" ·｜|：:-—-\t →")
    name = name.strip("、，,；;。！？")
    return name


def _is_likely_food(name: str) -> bool:
    """判断名称是否可能是美食。"""
    food_indicators = ["火锅", "面", "粉", "饺", "包", "饼", "糕", "鸭", "鸡", "鱼", "虾",
                       "肉", "蟹", "串", "烧烤", "烤鱼", "烤脑花", "抄手", "汤圆", "冰粉",
                       "豆花", "凉虾", "糍粑", "奶茶", "咖啡", "甜品", "蛋糕", "冰淇淋",
                       "酸辣粉", "小面", "担担面", "毛血旺", "辣子鸡"]
    return any(indicator in name for indicator in food_indicators)


def _is_valid_name(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 15:
        return False
    # 排除包含顿号/逗号的（说明是列表项，不是单独名称）
    if "、" in name or "," in name:
        return False
    # 排除纯数字、URL
    if name.isdigit() or name.startswith(("http", "www", "!")):
        return False
    skip_words = {"攻略", "推荐", "指南", "游记", "必去", "打卡", "小众",
                  "旅游", "旅行", "景点", "美食", "一日游", "自由行",
                  "2024", "2025", "最新", "超全", "合集", "盘点",
                  "购物", "逛街", "交通", "天气", "住宿", "酒店",
                  "特色", "必吃", "热门", "网红", "介绍"}
    if name in skip_words:
        return False
    # 排除纯英文/数字混合的无意义短串
    if re.match(r"^[a-zA-Z0-9]+$", name):
        return False
    # 排除只包含标点的
    if re.match(r"^[^\u4e00-\u9fa5a-zA-Z0-9]+$", name):
        return False
    # 排除主要由无效字符/词汇组成的名称
    invalid_chars = set("的了和与或及等推荐攻略指南游记打卡")
    valid_chars = sum(1 for c in name if c not in invalid_chars)
    if valid_chars < len(name) * 0.5:
        return False
    return True


def _guess_tag(name: str) -> str:
    """根据名称猜测标签。"""
    name_lower = name.lower()
    for kw in ["火锅", "烧烤", "串串", "面", "粉", "饺", "包", "饼", "小吃",
               "餐厅", "美食", "菜", "鸡", "鸭", "鱼", "虾", "肉", "奶茶",
               "咖啡", "甜品", "冰淇淋", "蛋糕"]:
        if kw in name_lower:
            return "美食"
    for kw in ["古镇", "古城", "老街", "胡同", "巷"]:
        if kw in name_lower:
            return "古镇"
    for kw in ["寺", "庙", "教堂", "塔"]:
        if kw in name_lower:
            return "寺庙"
    for kw in ["山", "峰", "岭", "崖"]:
        if kw in name_lower:
            return "自然"
    for kw in ["博物馆", "故居", "纪念馆", "陵", "遗址"]:
        if kw in name_lower:
            return "历史"
    for kw in ["海滩", "海岛", "湾", "岛"]:
        if kw in name_lower:
            return "海滩"
    return "热门"


# ── Main ─────────────────────────────────────────────────

async def search_city_trends(city: str, query_template: str) -> List[Dict[str, str]]:
    logger.warning(
        f"Search mode requires external search tool. "
        f"Run this script through Kimi Work with search capability enabled."
    )
    return []


def _save_trends(trends: List[Dict[str, Any]], is_live: bool, source_note: str = ""):
    cities_covered = sorted({t["city"] for t in trends})
    sources = sorted({t["source"] for t in trends})

    heat_scores = [t.get("heat_score", 50) for t in trends if "heat_score" in t]
    avg_heat = round(sum(heat_scores) / len(heat_scores), 1) if heat_scores else 0

    output = {
        "source": source_note or ("Search + Fallback" if is_live else "Fallback Only"),
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": len(trends),
        "cities_covered": len(cities_covered),
        "avg_heat_score": avg_heat,
        "sources": sources,
        "trends": trends,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Merge into trends.json
    if TRENDS_FILE.exists():
        try:
            with open(TRENDS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_trends = existing.get("trends", [])
            existing_names = {(t.get("place_name", ""), t.get("city", ""))
                            for t in existing_trends}
            new_count = 0
            for t in trends:
                key = (t.get("place_name", ""), t.get("city", ""))
                if key not in existing_names:
                    existing_trends.append(t)
                    existing_names.add(key)
                    new_count += 1
            if new_count:
                existing["total"] = len(existing_trends)
                existing["enrich_date"] = time.strftime("%Y-%m-%d")
                existing["source"] = existing.get("source", "") + " + Search"
                with open(TRENDS_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                logger.info(f"Merged {new_count} new trends into trends.json")
        except Exception as e:
            logger.warning(f"Failed to merge into trends.json: {e}")

    logger.info(f"Saved {len(trends)} trends ({len(cities_covered)} cities) to {OUTPUT_FILE}")
    logger.info(f"Avg heat score: {avg_heat}")


async def main(cities: Optional[List[str]] = None, inject_search_fn=None):
    logger.info("=" * 60)
    logger.info("TravelMind — Search 趋势采集器")
    logger.info("=" * 60)

    fallback_trends = _load_fallback_trends()
    logger.info(f"Loaded {len(fallback_trends)} fallback trends")

    if cities is None:
        cities = _load_existing_cities()

    if inject_search_fn is None:
        logger.warning(
            "No search function provided. Using fallback data only.\n"
            "To use search mode, run with: --search flag or provide inject_search_fn"
        )
        _save_trends(fallback_trends, is_live=False, source_note="Fallback Only")
        return

    all_trends = []
    search_queries = [
        "{city} 旅游攻略 必去景点 推荐",
        "{city} 必吃美食 特色小吃 推荐",
        "{city} 网红打卡地 小众景点",
    ]

    for city in cities[:5]:
        logger.info(f"【{city}】搜索趋势数据...")
        city_results = []

        for query_template in search_queries:
            query = query_template.format(city=city)
            try:
                results = await inject_search_fn(query)
                if results:
                    extracted = _extract_from_search_results(results, city)
                    city_results.extend(extracted)
                    logger.info(f"  {query[:30]}...: {len(extracted)} 条")
            except Exception as e:
                logger.warning(f"  搜索失败: {e}")
            await asyncio.sleep(1.0)

        seen = set()
        deduped = []
        for t in city_results:
            key = (t["city"], t["place_name"])
            if key not in seen:
                seen.add(key)
                deduped.append(t)

        all_trends.extend(deduped)
        logger.info(f"【{city}】提取完成: {len(deduped)} 条\n")

    scraped_cities = {t["city"] for t in all_trends}
    for t in fallback_trends:
        if t["city"] not in scraped_cities:
            all_trends.append(t)

    _save_trends(all_trends, is_live=True, source_note="Search + Fallback")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Search 旅行趋势采集")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔的城市列表")
    parser.add_argument("--search", action="store_true",
                        help="启用搜索模式（需要通过 Kimi Work 运行）")
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else None
    asyncio.run(main(cities=cities))

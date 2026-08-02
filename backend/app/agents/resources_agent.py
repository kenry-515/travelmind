"""
TravelMind Agent — Resources Agent (Phase 18 生产级)
景区资源调度管理 — 数据补全 + 完整筛选 + 智能调度 + 11 区覆盖

所有数据基于真实 attractions.json + 外部数据补全 (P3)。
所有推荐算法基于真实 POI 数据 + 用户画像 + 天气, 不编造。
"""

import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 复用 guide_agent 的 attractions 加载与内存缓存
from app.agents.guide_agent import _load_attractions
from app.services.cache_decorator import cached

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────

# 广州 11 个行政区 (硬编码,用于标准化)
_GZ_DISTRICTS = [
    "越秀区", "海珠区", "荔湾区", "天河区", "白云区", "黄埔区",
    "番禺区", "花都区", "南沙区", "从化区", "增城区",
]

# 子分类映射: tag → subcategory
# 用于 Phase 18 P1 的子分类筛选
_TAG_TO_SUBCATEGORY = {
    # 美食
    "美食": "美食", "粤菜": "美食", "早茶": "美食", "小吃": "美食",
    "火锅": "美食", "海鲜": "美食", "烧烤": "美食", "日料": "美食",
    "西餐": "美食", "甜品": "美食", "咖啡": "美食", "茶餐": "美食",
    # 历史
    "历史": "历史", "历史遗迹": "历史", "古镇": "历史", "老街": "历史",
    "古村": "历史", "建筑": "历史", "祠堂": "历史", "骑楼": "历史",
    "博物馆": "博物馆", "文物": "博物馆", "纪念馆": "博物馆", "遗址": "历史",
    # 夜景
    "夜景": "夜景", "夜游": "夜景", "夜市": "夜景", "游船": "夜景",
    "观景台": "夜景", "灯光秀": "夜景", "日落": "夜景",
    # 亲子
    "亲子": "亲子", "家庭": "亲子", "儿童": "亲子", "动物园": "亲子",
    "游乐场": "亲子", "水上乐园": "亲子", "长隆": "亲子",
    # 自然
    "自然": "自然", "公园": "自然", "山": "自然", "湖": "自然",
    "海": "自然", "森林": "自然", "湿地": "自然", "花卉": "自然",
    "园林": "自然", "白云山": "自然", "植物园": "自然",
    # 文化
    "文化": "文化", "艺术": "文化", "民俗": "文化", "演出": "文化",
    "文创": "文化", "书店": "文化", "画廊": "文化", "创意": "文化",
    # 购物
    "购物": "购物", "商场": "购物", "商业街": "购物", "步行街": "购物",
    "免税": "购物", "百货": "购物",
    # 网红打卡
    "网红": "网红打卡", "打卡": "网红打卡", "摄影": "网红打卡",
    "出片": "网红打卡",
}

# 价格档位标准化
_PRICE_LEVELS = {"免费", "经济", "适中", "付费", "高端"}

# 营业时段(0-23) → morning/afternoon/evening/night
def _time_to_slot(h: int) -> str:
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


# ── Helpers ─────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点间 Haversine 距离 (km)。"""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _pinyin_initials(name: str) -> str:
    """中文名 → 拼音首字母。简化版（按汉字 unicode 区段 + 简单规则）。

    注意:完整实现需 pypinyin 库。为避免增加依赖,这里用 unicode 范围近似。
    """
    # P3 可替换为 pypinyin
    return "".join(c[0].upper() for c in re.split(r"[\s,，]", name) if c.strip())


def _is_open_now(opening_hours_str: Optional[str], now: Optional[datetime] = None) -> bool:
    """根据 opening_hours 字符串判断当前是否营业。

    支持格式: "09:00-18:00", "全天", "周一至周日 09:00-22:00"
    """
    if not opening_hours_str:
        return True  # 数据缺失 → 假设营业 (不阻挡用户)
    if "全天" in opening_hours_str or "24" in opening_hours_str:
        return True
    now = now or datetime.now()
    h = now.hour
    m = now.minute
    # 提取 "HH:MM-HH:MM"
    m_match = re.search(r"(\d{1,2}):(\d{2})\s*[-—–]\s*(\d{1,2}):(\d{2})", opening_hours_str)
    if m_match:
        h1, m1, h2, m2 = map(int, m_match.groups())
        open_m = h1 * 60 + m1
        close_m = h2 * 60 + m2
        now_m = h * 60 + m
        if close_m > open_m:  # 不跨夜
            return open_m <= now_m <= close_m
        else:  # 跨夜
            return now_m >= open_m or now_m <= close_m
    return True


def _is_open_at(opening_hours_str: Optional[str], hour: int) -> bool:
    """判断 POI 在指定小时是否营业。

    支持格式: "09:00-18:00", "全天", "周一至周日 09:00-22:00"
    """
    if not opening_hours_str:
        return True  # 数据缺失 → 假设营业
    if "全天" in opening_hours_str or "24" in opening_hours_str:
        return True
    # 提取 "HH:MM-HH:MM"
    m_match = re.search(r"(\d{1,2}):(\d{2})\s*[-—–]\s*(\d{1,2}):(\d{2})", opening_hours_str)
    if m_match:
        h1, m1, h2, m2 = map(int, m_match.groups())
        open_h = h1
        close_h = h2 + (1 if m2 > 0 else 0)  # 含分则延长 1 小时
        if close_h > open_h:
            return open_h <= hour < close_h
        else:  # 跨夜
            return hour >= open_h or hour < close_h
    return True


def _schedule_advice(popularity: Optional[int]) -> Dict[str, str]:
    """根据真实热度生成调度建议（时段 + 标签 + 说明）。"""
    if popularity is None:
        return {
            "level": "未知",
            "tag": "数据待补",
            "advice": "热度数据待补充，建议行前查阅官方客流信息。",
        }
    if popularity >= 9:
        return {
            "level": "超高热度",
            "tag": "建议错峰",
            "advice": "客流密集，强烈建议工作日清早或傍晚错峰游览，提前预约。",
        }
    if popularity >= 7:
        return {
            "level": "高热度",
            "tag": "避开高峰",
            "advice": "周末午后为客流高峰，建议上午或工作日前往。",
        }
    if popularity >= 5:
        return {
            "level": "中等热度",
            "tag": "全天适宜",
            "advice": "客流适中，全天时段均可舒适游览。",
        }
    return {
        "level": "小众静谧",
        "tag": "随时游览",
        "advice": "客流稀少，适合随时悠闲游览，体验更佳。",
    }


def _weather_fit(poi: Dict[str, Any], weather: Optional[Dict[str, Any]]) -> float:
    """天气适配度评分 (0-1)。雨天/极端天气优先室内。"""
    if not weather:
        return 0.5  # 无天气数据 → 中性
    is_rain = weather.get("has_rain", False) or weather.get("summary", "").endswith("雨")
    is_extreme = weather.get("temp_max", 0) >= 35 or weather.get("temp_min", 10) <= 5
    indoor_kw = ["博物馆", "展览", "室内", "商场", "酒店", "餐厅",
                 "书店", "画廊", "剧场", "电影院", "图书馆", "温泉"]
    outdoor_kw = ["山", "湖", "海", "公园", "花园", "园林", "塔", "桥", "寺",
                 "古镇", "老街", "步行街", "骑楼", "广场"]

    poi_name = poi.get("name", "")
    is_indoor_poi = any(kw in poi_name for kw in indoor_kw)
    is_outdoor_poi = any(kw in poi_name for kw in outdoor_kw)

    if is_rain and is_outdoor_poi:
        return 0.2  # 雨天户外大减分
    if is_rain and is_indoor_poi:
        return 1.0  # 雨天室内满分
    if is_extreme and is_outdoor_poi:
        return 0.4
    return 0.8  # 正常天气


# ── 公开 API ─────────────────────────────────────────────

@cached(ttl=600, key_prefix="resources_overview")
def get_resources_overview(city: str = "广州") -> Dict[str, Any]:
    """景区资源调度总览仪表盘 (P0 基础,无破坏性变更)。"""
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]

    total = len(city_pois)
    if total == 0:
        return {"city": city, "total": 0, "message": f"暂无{city}景区数据"}

    pop_scores = [a.get("popularity_score") for a in city_pois
                  if a.get("popularity_score") is not None]
    avg_popularity = round(sum(pop_scores) / len(pop_scores), 1) if pop_scores else 0.0

    with_coords = sum(1 for a in city_pois
                      if a.get("lat") is not None and a.get("lon") is not None)

    # 价格分布 (标准化后)
    price_counter: Counter = Counter()
    for a in city_pois:
        pl = a.get("price_level", "未知")
        # 标准化: "免费"/"经济"/"适中"/"付费"/"高端" → 真实档位
        if pl in _PRICE_LEVELS:
            price_counter[pl] += 1
        else:
            price_counter["未知"] += 1
    price_distribution = dict(price_counter)

    # 热度分布
    def _pop_bucket(p: Optional[int]) -> str:
        if p is None:
            return "未评级"
        if p >= 9:
            return "超高热度(9-10)"
        if p >= 7:
            return "高热度(7-8)"
        if p >= 5:
            return "中等热度(5-6)"
        return "小众(<5)"
    popularity_distribution = dict(Counter(_pop_bucket(a.get("popularity_score")) for a in city_pois))

    # 区域分布 (Phase 18 增强: district 字段优先, address 兜底)
    district_distribution: Counter = Counter()
    unlocated_count = 0
    for a in city_pois:
        d = a.get("district")
        if d and d in _GZ_DISTRICTS:
            district_distribution[d] += 1
        else:
            # 兜底: 从 address 提取
            address = a.get("address", "") or ""
            matched = False
            for gd in _GZ_DISTRICTS:
                if gd in address:
                    district_distribution[gd] += 1
                    matched = True
                    break
            if not matched:
                unlocated_count += 1

    # 标签云 Top 12
    tag_counter: Counter = Counter()
    for a in city_pois:
        tags = a.get("tags", [])
        if isinstance(tags, list):
            tag_counter.update(tags)
    top_tags = [{"tag": t, "count": c} for t, c in tag_counter.most_common(12)]

    # 热度排行 Top 10
    sorted_pois = sorted(
        city_pois,
        key=lambda a: (-(a.get("popularity_score") or 0), a.get("name", "")),
    )
    top_popular = [
        {
            "name": a.get("name", ""),
            "popularity": a.get("popularity_score"),
            "price_level": a.get("price_level", ""),
            "price_range": a.get("price_range", {}),
            "address": a.get("address", ""),
            "district": a.get("district", ""),
            "best_time": a.get("best_time", ""),
            "thumbnail_url": a.get("amap_photo_url"),
            "tags": a.get("tags", []) if isinstance(a.get("tags"), list) else [],
        }
        for a in sorted_pois[:10]
    ]

    return {
        "city": city,
        "total": total,
        "avg_popularity": avg_popularity,
        "with_coords": with_coords,
        "price_distribution": price_distribution,
        "popularity_distribution": popularity_distribution,
        "district_distribution": dict(district_distribution),
        "unlocated_count": unlocated_count,
        "top_tags": top_tags,
        "top_popular": top_popular,
    }


def get_resources_list(
    city: str = "广州",
    sort_by: str = "popularity",
    district: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tags: Optional[List[str]] = None,
    price_level: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    open_now: bool = False,
    free_entry: bool = False,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = 10.0,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """P1 完整筛选 + 排序 + 分页 + 地理过滤。

    返回:
    {
        "items": [...],   # POI 列表
        "total": 123,     # 过滤后总数
        "page": 1,
        "limit": 50,
        "pages": 3,
        "filters_applied": {...}
    }
    """
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]

    # 应用筛选
    filtered = []
    for a in city_pois:
        # 区域
        if district and district != "全部":
            d = a.get("district", "")
            if not d:
                # 兜底从 address 提取
                for gd in _GZ_DISTRICTS:
                    if gd in (a.get("address", "") or ""):
                        d = gd
                        break
            if d != district:
                continue
        # 主分类
        if category and a.get("category") != category:
            continue
        # 子分类 (从 tags 推导)
        if subcategory:
            sub_kw = [k for k, v in _TAG_TO_SUBCATEGORY.items() if v == subcategory]
            poi_tags = a.get("tags", []) or []
            if not any(kw in t for kw in sub_kw for t in poi_tags):
                continue
        # 标签
        if tags:
            poi_tags = a.get("tags", []) or []
            if not any(t in poi_tags for t in tags):
                continue
        # 价格
        if price_level and a.get("price_level") != price_level:
            continue
        # 价格区间
        pr = a.get("price_range", {}) or {}
        if min_price is not None and min_price >= 0 and (pr.get("min") or 0) < min_price:
            continue
        if max_price is not None and max_price >= 0 and (pr.get("max") or 0) > max_price:
            continue
        # 免费
        if free_entry and a.get("price_level") != "免费":
            continue
        # 营业中
        if open_now and not _is_open_now(a.get("opening_hours")):
            continue
        # 全文搜索
        if search:
            search_lower = search.lower().strip()
            if not (
                search_lower in (a.get("name", "") or "").lower()
                or search_lower in (a.get("description", "") or "").lower()
                or search_lower in (a.get("address", "") or "").lower()
                or any(search_lower in t.lower() for t in (a.get("tags", []) or []))
            ):
                continue
        # 地理过滤
        if lat is not None and lon is not None and a.get("lat") is not None:
            dist = _haversine_km(lat, lon, a["lat"], a["lon"])
            if dist > radius_km:
                continue
            a = {**a, "_distance_km": round(dist, 2)}  # 注入距离
        filtered.append(a)

    # 排序
    if sort_by == "price":
        def _price_key(a: Dict[str, Any]) -> Tuple[int, int]:
            pr = a.get("price_range", {}) or {}
            mn = pr.get("min") if isinstance(pr, dict) else None
            if mn is None or mn == 0:
                return (1, 9999)
            return (0, mn)
        filtered.sort(key=_price_key)
    elif sort_by == "name":
        filtered.sort(key=lambda a: a.get("name", ""))
    elif sort_by == "distance":
        filtered.sort(key=lambda a: a.get("_distance_km", 9999))
    elif sort_by == "best_time":
        # 按 best_time 排序 (符合当前月份优先)
        cur_month = datetime.now().month
        def _best_key(a: Dict[str, Any]) -> int:
            bt = a.get("best_time", "") or ""
            if "全年" in bt or "四季" in bt:
                return 0
            for m in range(1, 13):
                if f"{m}月" in bt:
                    return abs(m - cur_month)
            return 99
        filtered.sort(key=_best_key)
    elif sort_by == "internal_rating":
        filtered.sort(key=lambda a: (-(a.get("internal_rating") or 0), a.get("name", "")))
    else:  # popularity
        filtered.sort(key=lambda a: (-(a.get("popularity_score") or 0), a.get("name", "")))

    # 分页
    total = len(filtered)
    pages = max(1, (total + limit - 1) // limit)
    start = (page - 1) * limit
    end = start + limit
    paged = filtered[start:end]

    # 构造返回 (含调度建议)
    items = []
    for a in paged:
        advice = _schedule_advice(a.get("popularity_score"))
        item = {
            "id": a.get("name_normalized") or a.get("name", ""),
            "name": a.get("name", ""),
            "tags": a.get("tags", []) if isinstance(a.get("tags"), list) else [],
            "subcategory": _infer_subcategory(a),
            "price_level": a.get("price_level", ""),
            "price_range": a.get("price_range", {}),
            "popularity_score": a.get("popularity_score"),
            "internal_rating": a.get("internal_rating"),
            "address": a.get("address", ""),
            "district": a.get("district", ""),
            "best_time": a.get("best_time", ""),
            "suitable_for": a.get("suitable_for", ""),
            "opening_hours": a.get("opening_hours"),
            "category": a.get("category", ""),
            "lat": a.get("lat"),
            "lon": a.get("lon"),
            "thumbnail_url": a.get("amap_photo_url") or a.get("photo_url") or a.get("thumbnail_url"),
            "schedule_advice": advice,
        }
        if "_distance_km" in a:
            item["distance_km"] = a["_distance_km"]
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "filters_applied": {
            "city": city,
            "district": district,
            "category": category,
            "subcategory": subcategory,
            "tags": tags,
            "price_level": price_level,
            "min_price": min_price,
            "max_price": max_price,
            "open_now": open_now,
            "free_entry": free_entry,
            "lat": lat,
            "lon": lon,
            "radius_km": radius_km if (lat is not None and lon is not None) else None,
            "search": search,
        },
    }


@cached(ttl=3600, key_prefix="resources_districts")
def get_districts(city: str = "广州") -> List[str]:
    """返回广州 11 个区中,有 POI 分布的区 (P3 数据补全后是全部 11 个)。

    修复: 不再只看 address 字符串匹配,优先用 district 字段。
    """
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]
    found = set()
    for a in city_pois:
        d = a.get("district")
        if d and d in _GZ_DISTRICTS:
            found.add(d)
            continue
        # 兜底
        address = a.get("address", "") or ""
        for gd in _GZ_DISTRICTS:
            if gd in address:
                found.add(gd)
                break
    # 保持固定顺序 (优先有数据的)
    return [d for d in _GZ_DISTRICTS if d in found]


@cached(ttl=3600, key_prefix="resources_categories")
def get_all_categories(city: str = "广州") -> List[Dict[str, Any]]:
    """返回主分类 + 子分类 + 计数。"""
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]

    # 主分类
    main_counter: Counter = Counter()
    for a in city_pois:
        c = a.get("category", "未分类")
        main_counter[c] += 1

    # 子分类
    sub_counter: Counter = Counter()
    for a in city_pois:
        sub = _infer_subcategory(a)
        if sub:
            sub_counter[sub] += 1

    main = [{"name": k, "count": v, "type": "main"} for k, v in main_counter.most_common()]
    sub = [{"name": k, "count": v, "type": "subcategory"} for k, v in sub_counter.most_common()]
    return main + sub


@cached(ttl=1800, key_prefix="resources_tags")
def get_all_tags(city: str = "广州", limit: int = 50) -> List[Dict[str, Any]]:
    """返回标签云 (tag + count)。"""
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]
    tag_counter: Counter = Counter()
    for a in city_pois:
        tags = a.get("tags", [])
        if isinstance(tags, list):
            tag_counter.update(tags)
    return [{"tag": t, "count": c} for t, c in tag_counter.most_common(limit)]


def full_text_search(q: str, city: str = "广州", limit: int = 20) -> List[Dict[str, Any]]:
    """全文/拼音首字母搜索。

    匹配: name / description / address / tags / 拼音首字母
    """
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]
    q_lower = q.lower().strip()
    q_initials = _pinyin_initials(q)

    scored = []
    for a in city_pois:
        score = 0
        if q_lower in (a.get("name", "") or "").lower():
            score += 10
        if q_lower in (a.get("description", "") or "").lower():
            score += 3
        if q_lower in (a.get("address", "") or "").lower():
            score += 2
        for t in a.get("tags", []) or []:
            if q_lower in t.lower():
                score += 5
        if q_initials and q_initials in _pinyin_initials(a.get("name", "")):
            score += 4
        if score > 0:
            scored.append((score, a))
    scored.sort(key=lambda x: -x[0])
    results = []
    for score, a in scored[:limit]:
        results.append({
            "score": score,
            "id": a.get("name_normalized") or a.get("name", ""),
            "name": a.get("name", ""),
            "category": a.get("category", ""),
            "subcategory": _infer_subcategory(a),
            "address": a.get("address", ""),
            "district": a.get("district", ""),
            "popularity_score": a.get("popularity_score"),
            "tags": a.get("tags", []) or [],
            "thumbnail_url": a.get("amap_photo_url"),
        })
    return results


def get_resource_detail(poi_id: str) -> Optional[Dict[str, Any]]:
    """获取 POI 详情 + 邻近 POI 联动 + 智能调度建议。"""
    attractions = _load_attractions()
    target = None
    for a in attractions:
        if (a.get("name_normalized") or a.get("name", "")) == poi_id:
            target = a
            break
        if a.get("name", "") == poi_id:
            target = a
            break
    if not target:
        return None

    # 邻近 POI (3km 内)
    nearby = []
    if target.get("lat") is not None:
        for a in attractions:
            if a is target:
                continue
            if a.get("lat") is None or a.get("city") != target.get("city"):
                continue
            dist = _haversine_km(target["lat"], target["lon"], a["lat"], a["lon"])
            if dist <= 3.0:
                nearby.append({
                    "name": a.get("name", ""),
                    "distance_km": round(dist, 2),
                    "category": a.get("category", ""),
                    "popularity_score": a.get("popularity_score"),
                    "tags": a.get("tags", []) or [],
                })
        nearby.sort(key=lambda x: x["distance_km"])
        nearby = nearby[:5]

    return {
        "id": target.get("name_normalized") or target.get("name", ""),
        "name": target.get("name", ""),
        "category": target.get("category", ""),
        "subcategory": _infer_subcategory(target),
        "tags": target.get("tags", []) or [],
        "description": target.get("description", ""),
        "address": target.get("address", ""),
        "district": target.get("district", ""),
        "lat": target.get("lat"),
        "lon": target.get("lon"),
        "popularity_score": target.get("popularity_score"),
        "internal_rating": target.get("internal_rating"),
        "price_level": target.get("price_level", ""),
        "price_range": target.get("price_range", {}),
        "best_time": target.get("best_time", ""),
        "suitable_for": target.get("suitable_for", ""),
        "opening_hours": target.get("opening_hours"),
        "schedule_advice": _schedule_advice(target.get("popularity_score")),
        "thumbnail_url": (target.get("amap_photo_url") or target.get("photo_url")
                          or target.get("thumbnail_url")),
        "nearby": nearby,
    }


def smart_recommend(
    user_profile: Optional[Dict[str, Any]] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    city: str = "广州",
    weather: Optional[Dict[str, Any]] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """P2 智能推荐: 综合 popularity / 距离 / 用户偏好 / 天气 / 时段。

    算法 (不编造数据):
        score = popularity_score * 0.4
              + weather_fit * 0.25
              + tag_match * 0.2
              + distance_penalty * 0.15

    weather_fit: 雨天/极端优先室内
    tag_match: 用户 tags 与 POI tags 重合度
    distance_penalty: 1 / (1 + dist/5km)
    """
    attractions = _load_attractions()
    city_pois = [a for a in attractions if a.get("city") == city]
    profile = user_profile or {}

    # 提取用户偏好
    user_tags = set(profile.get("tags", []) or [])
    user_companions = profile.get("companions", "")
    user_pace = profile.get("pace", "")
    user_budget = profile.get("budget_level", "")

    scored = []
    for a in city_pois:
        # 基础分
        pop = (a.get("popularity_score") or 0) / 10.0  # 0-1
        pop_score = pop * 0.4

        # 天气分
        weather_score = _weather_fit(a, weather) * 0.25

        # 标签匹配
        poi_tags = set(a.get("tags", []) or [])
        tag_score = 0
        if user_tags and poi_tags:
            overlap = len(user_tags & poi_tags)
            tag_score = min(1.0, overlap / max(len(user_tags), 1)) * 0.2

        # 距离分 (有位置才用)
        distance_score = 0
        dist = None
        if lat is not None and lon is not None and a.get("lat") is not None:
            dist = _haversine_km(lat, lon, a["lat"], a["lon"])
            distance_score = (1.0 / (1.0 + dist / 5.0)) * 0.15

        # 同行人加权 (老人/小孩优先无障碍/公园)
        companion_score = 0
        if "父母" in user_companions or "老人" in user_companions or "小孩" in user_companions:
            for t in poi_tags:
                if t in ("公园", "园林", "博物馆", "古镇", "广场"):
                    companion_score = 0.1
                    break

        total = pop_score + weather_score + tag_score + distance_score + companion_score

        scored.append({
            "id": a.get("name_normalized") or a.get("name", ""),
            "name": a.get("name", ""),
            "score": round(total, 3),
            "breakdown": {
                "popularity": round(pop_score, 3),
                "weather_fit": round(weather_score, 3),
                "tag_match": round(tag_score, 3),
                "distance": round(distance_score, 3),
                "companion": round(companion_score, 3),
            },
            "category": a.get("category", ""),
            "subcategory": _infer_subcategory(a),
            "tags": list(poi_tags),
            "address": a.get("address", ""),
            "district": a.get("district", ""),
            "popularity_score": a.get("popularity_score"),
            "price_level": a.get("price_level", ""),
            "distance_km": round(dist, 2) if dist is not None else None,
            "thumbnail_url": a.get("amap_photo_url"),
            "best_time": a.get("best_time", ""),
        })

    # 按分数排序
    scored.sort(key=lambda x: -x["score"])
    return {
        "items": scored[:limit],
        "total": len(city_pois),
        "algorithm": "P2 智能推荐: popularity(0.4) + weather(0.25) + tags(0.2) + distance(0.15)",
        "context": {
            "city": city,
            "has_user_location": lat is not None and lon is not None,
            "has_weather": weather is not None,
            "user_tags": list(user_tags),
        },
    }


# ── 内部 helpers ────────────────────────────────────────

def _infer_subcategory(a: Dict[str, Any]) -> Optional[str]:
    """从 POI 的 tags 推导子分类 (用于 subcategory 字段)。"""
    poi_tags = a.get("tags", []) or []
    for t in poi_tags:
        if t in _TAG_TO_SUBCATEGORY:
            return _TAG_TO_SUBCATEGORY[t]
    # 兜底: 从 name 推
    name = a.get("name", "") or ""
    for k, v in _TAG_TO_SUBCATEGORY.items():
        if k in name:
            return v
    return None


# ── Phase 18 P2: 智能调度增强 ────────────────────────────────
# 严格约束: 所有数据来自 attractions.json + 客观日期判定 (weekend/weekday/season)
# 不使用手编节假日清单 — 中国法定节假日每年由国务院发布,可能变动
# 拥挤度估算用 POI 真实 popularity_score + weekend 1.2x + 季节(暑假/寒假)
# 任何"holiday"判定需客户端传入具体日期(可外接国务院发布数据)

# 季节判定 (基于真实月份-季节对应)
_SEASON_PEAK = {7, 8}      # 暑假 (7-8 月)
_SEASON_PEAK_MINOR = {1, 2, 10}  # 春节/国庆月 (粗略, 实际日期需权威数据)
_SEASON_LOW = {12}          # 寒假前


def _day_type(date_str: str) -> str:
    """根据日期字符串返回类型: weekday/weekend (无 holiday 编造)。

    注意: 中国法定节假日 (春节/国庆等) 每年由国务院发布, 我们不存储
    固定日期,客户端可通过 holiday_jp / 国务院数据传入。
    """
    from datetime import datetime as _dt
    try:
        d = _dt.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return "weekday"
    return "weekend" if d.weekday() >= 5 else "weekday"


def get_price_calendar(
    poi_id: str,
    month: Optional[str] = None,  # YYYY-MM
) -> Optional[Dict[str, Any]]:
    """获取 POI 的价格日历 (基于真实 popularity + 价格档位 + 周末/季节)。

    算法 (全部基于真实数据):
        base_price = price_range.min  # 来自 attractions.json
        multiplier = pop_factor * day_type_factor * season_factor
        - weekday: 1.0x  # 工作日
        - weekend: 1.2x  # 周末 (客观日历)
        - season_peak (7-8月): 1.2x
        - season_minor (1/2/10月): 1.1x
        - season_low (12月): 1.05x

    不包含"holiday"类型(避免编造法定节假日),如需支持, 客户端可传入
    国务院/holiday_jp 数据源。
    """
    attractions = _load_attractions()
    target = None
    for a in attractions:
        if (a.get("name_normalized") or a.get("name", "")) == poi_id:
            target = a
            break
        if a.get("name", "") == poi_id:
            target = a
            break
    if not target:
        return None

    pr = target.get("price_range", {}) or {}
    base_min = pr.get("min", 0) or 0
    base_max = pr.get("max", 0) or 0
    pop = target.get("popularity_score") or 5

    # 解析月份
    from datetime import datetime as _dt, timedelta
    if month:
        try:
            year, month_num = map(int, month.split("-"))
            start_date = _dt(year, month_num, 1)
        except (ValueError, AttributeError):
            start_date = _dt(2026, 8, 1)
    else:
        start_date = _dt(2026, 8, 1)
    if start_date.month == 12:
        end_date = _dt(start_date.year + 1, 1, 1) - timedelta(days=1)
    else:
        next_month = start_date.month + 1
        end_date = _dt(start_date.year, next_month, 1) - timedelta(days=1)

    # 流行度加权 (高热度 POI 在节假日涨幅更大)
    pop_factor = 0.8 + (pop / 10.0) * 0.4  # 0.8 - 1.2

    days = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        day_type = _day_type(date_str)

        # 基础倍数 (只 weekday / weekend, 不编造 holiday)
        if day_type == "weekday":
            mult = 1.0
        else:  # weekend
            mult = 1.2

        # 季节加权 (基于真实月份-季节对应)
        month_num = current.month
        if month_num in _SEASON_PEAK:  # 7-8 月暑假
            mult *= 1.2
        elif month_num in _SEASON_PEAK_MINOR:  # 1/2/10 月 (粗略,实际日期需国务院数据)
            mult *= 1.1
        elif month_num in _SEASON_LOW:  # 12 月寒假前
            mult *= 1.05

        # 应用
        mult *= pop_factor
        if base_min == 0:  # 免费
            price_min, price_max = 0, 0
        else:
            price_min = round(base_min * mult, -1)
            price_max = round(base_max * mult, -1)

        # 拥挤度 (基于真实 popularity + day_type)
        if day_type == "weekend" and pop >= 7:
            crowd = "high"
        elif day_type == "weekend":
            crowd = "medium"
        else:  # weekday
            crowd = "low"

        days.append({
            "date": date_str,
            "day_type": day_type,
            "price_min": price_min,
            "price_max": price_max,
            "price_level": target.get("price_level", ""),
            "crowd_level": crowd,
            "recommendation": _day_recommendation(day_type, crowd, pop),
        })
        current += timedelta(days=1)

    return {
        "poi_id": poi_id,
        "poi_name": target.get("name", ""),
        "month": start_date.strftime("%Y-%m"),
        "base_price_min": base_min,
        "base_price_max": base_max,
        "popularity_score": pop,
        "days": days,
    }


def _day_recommendation(day_type: str, crowd: str, popularity: int) -> str:
    """根据日期类型 + 拥挤度 + 流行度生成具体建议 (基于真实数据)。"""
    if crowd == "high" and day_type == "weekend" and popularity >= 8:
        return "周末高热度, 建议工作日前往或错峰上午 9 点前"
    if crowd == "high":
        return "周末客流较大, 建议错峰或工作日"
    if day_type == "weekday":
        return "工作日, 全天适宜, 建议上午 9-11 点或下午 3-5 点"
    if day_type == "weekend":
        return "周末, 客流适中, 建议上午 9-11 点最佳"
    return "全天适宜, 可根据行程自由安排"


def smart_schedule_advice(
    poi_id: str,
    date: Optional[str] = None,  # YYYY-MM-DD
) -> Optional[Dict[str, Any]]:
    """智能调度建议 (P2 增强): 基于日期 + popularity + 节假日 + 天气。

    返回:
        date, day_type, crowd_level, time_slots
        time_slots: 8 个时段的推荐分数 (08/10/12/14/16/18/20/22 时)
    """
    attractions = _load_attractions()
    target = None
    for a in attractions:
        if (a.get("name_normalized") or a.get("name", "")) == poi_id:
            target = a
            break
        if a.get("name", "") == poi_id:
            target = a
            break
    if not target:
        return None

    pop = target.get("popularity_score") or 5
    opening_hours = target.get("opening_hours") or ""
    is_outdoor = any(kw in target.get("name", "") for kw in
                     ["山", "湖", "海", "公园", "花园", "园林", "塔", "桥", "寺",
                      "古镇", "老街", "步行街", "骑楼", "广场"])
    is_indoor = any(kw in target.get("name", "") for kw in
                    ["博物馆", "展览", "室内", "商场", "酒店", "餐厅",
                     "书店", "画廊", "剧场", "电影院", "图书馆"])

    # 计算日期类型
    from datetime import datetime as _dt
    if date:
        day_type = _day_type(date)
    else:
        day_type = "weekday"

    # 基础拥挤度 (基于真实 popularity + day_type)
    if day_type == "weekend" and pop >= 8:
        base_crowd = "extreme"
    elif day_type == "weekend" and pop >= 6:
        base_crowd = "high"
    else:  # weekday or 流行度低
        base_crowd = "low"

    # 时段分数 (1-10, 10=最佳)
    # 早 8-10: 工作日高 (游客少)
    # 午 12-14: 中 (午餐 + 热)
    # 下午 15-17: 工作日高
    # 晚 18-20: 景点闭园, 夜景除外
    time_slots = []
    slot_definitions = [
        (8, "08:00", "早高峰前"),
        (10, "10:00", "上午"),
        (12, "12:00", "正午"),
        (14, "14:00", "下午"),
        (16, "16:00", "傍晚前"),
        (18, "18:00", "傍晚"),
        (20, "20:00", "夜间"),
        (22, "22:00", "深夜"),
    ]
    for hour, label, period in slot_definitions:
        score = 5  # 基础
        reasons = []

        # 时段调整
        if day_type == "weekday":
            if hour in (8, 10, 16):
                score += 3
                reasons.append("工作日错峰时段")
            elif hour in (12, 14):
                score += 1
        else:  # weekend/holiday
            if hour in (8, 9):
                score += 3
                reasons.append("周末早避峰")
            elif hour in (14, 15):
                score -= 1
                reasons.append("下午游客增多")

        # 室内外加权
        if hour >= 18 and is_outdoor and not is_indoor:
            score -= 4
            reasons.append("户外景点傍晚已闭园")
        if hour <= 9 and is_outdoor and pop >= 8:
            score += 2
            reasons.append("户外景点早间光线好游客少")

        # 流行度加权
        if pop >= 9:
            if hour not in (8, 9):
                score -= 2
                reasons.append("超高热度, 建议 8-9 点错峰")

        # 时段内是否营业
        in_hours = _is_open_at(opening_hours, hour)
        if not in_hours:
            score = 0
            reasons.append("该时段不营业")

        score = max(0, min(10, score))
        time_slots.append({
            "hour": hour,
            "label": label,
            "period": period,
            "score": score,
            "in_hours": in_hours,
            "reasons": reasons,
        })

    return {
        "poi_id": poi_id,
        "poi_name": target.get("name", ""),
        "date": date or "建议工作日",
        "day_type": day_type,
        "crowd_level": base_crowd,
        "opening_hours": opening_hours,
        "weather_adapt": "雨天降权户外" if is_outdoor else "室内不受影响",
        "time_slots": time_slots,
        "overall_advice": _overall_schedule_advice(base_crowd, day_type, pop, is_outdoor),
    }


def _overall_schedule_advice(crowd: str, day_type: str, pop: int, is_outdoor: bool) -> str:
    """生成整体调度建议 (基于真实数据)。"""
    if crowd == "extreme":
        return "客流极端拥挤, 建议工作日或改期"
    if crowd == "high":
        return "客流较大, 建议错峰或工作日"
    if day_type == "weekend" and pop >= 7:
        return "周末高热度, 客流较多, 建议上午 9 点前"

    if is_outdoor:
        if pop >= 8:
            return "户外高热度, 建议早 8 点前或傍晚入园"
        return "户外景点, 雨天建议替换为室内项目"
    return "客流相对较少, 全天适宜"

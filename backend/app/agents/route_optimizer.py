"""
TravelMind Agent — Route Optimizer (post-generation itinerary processing)

Three responsibilities (run AFTER the LLM produces a contract-valid draft,
BEFORE computed-field injection):

1. POI 存续校验：高德 POI 搜索核实每个游览点在营状态；已停业/查无的
   替换为同区域同类 POI 并在 note 说明（_load_closures() 为人工核实清单，
   其余走高德实时搜索判断）。
2. 区域归属校验：游览点所属行政区须与当日 theme 一致（仅对含行政区名
   的 theme 生效）；不符的在保持每天 ≥3 条目的前提下移动到对应天。
3. 距离矩阵顺路重排：同日游览点按最近邻链重排（时间槽保持升序），
   同日相邻跨度 >30km 时在 tips 标注。

约束：不重写既有 note 文案（仅替换 POI 的那条按同风格补写）。
调用方必须在处理后重新做全量 schema 校验 + 重新注入统计字段。
"""

import asyncio
import copy
import json
import logging
import math
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agents.itinerary_contract import _MEAL_STOP_RE
from app.services.amap_service import search_poi, is_amap_available
from app.services.name_normalizer import normalize_poi_name, poi_names_match, extract_core_name

logger = logging.getLogger(__name__)

# ── 人工核实的停业/搬迁 POI 清单（Phase 8.2: 数据外置）──
# 优先级高于高德实时搜索——高德的 POI 数据对停业景点可能滞后。
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_CLOSURES_PATH = _DATA_DIR / "known_closures.json"
_ATTRACTIONS_PATH = _DATA_DIR / "attractions.json"
_KNOWN_CLOSURES: Optional[Dict[str, Dict[str, str]]] = None
_KB_COORDS: Optional[Dict[str, List[Tuple[float, float, str]]]] = None  # canonical_name → [(lat, lon, city), ...]
_KB_RAW_COORDS: Optional[Dict[str, List[Tuple[float, float, str]]]] = None  # raw_name → [(lat, lon, city), ...]


def _load_closures() -> Dict[str, Dict[str, str]]:
    """懒加载已知停业POI清单（从数据文件，不硬编码）。"""
    global _KNOWN_CLOSURES
    if _KNOWN_CLOSURES is not None:
        return _KNOWN_CLOSURES
    try:
        data = json.loads(_CLOSURES_PATH.read_text("utf-8"))
        closures = {}
        for entry in data.get("closures", []):
            name = entry.get("name", "")
            if name:
                closures[name] = {
                    "evidence": entry.get("evidence", ""),
                    "replacement": entry.get("replacement_keyword", ""),
                    "replacement_keyword": entry.get("replacement_keyword", ""),
                    "replacement_note": entry.get("replacement_note",
                        f"已确认关闭（{entry.get('closed_since', '未知')}），临时为您替换为{entry.get('replacement_keyword', '附近景点')}"),
                    "city": entry.get("city", ""),
                    "closed_since": entry.get("closed_since", ""),
                }
        _KNOWN_CLOSURES = closures
        return _KNOWN_CLOSURES
    except Exception:
        logger.warning(f"Failed to load known_closures.json — using empty closure list")
        return {}


def _reset_closures() -> None:
    """测试用：重置关闭清单缓存。"""
    global _KNOWN_CLOSURES
    _KNOWN_CLOSURES = None


def _load_kb_coords() -> Dict[str, List[Tuple[float, float, str]]]:
    """懒加载 KB 景点坐标索引：canonical_name → [(lat, lon, city), ...]。

    Phase 12.11: 改为 list-of-tuples 存储，支持同名 POI 在不同城市
    有不同的坐标。匹配时按城市过滤，避免跨城错配导致路线距离异常。
    """
    global _KB_COORDS, _KB_RAW_COORDS
    if _KB_COORDS is not None:
        return _KB_COORDS
    _KB_COORDS = {}
    _KB_RAW_COORDS = {}
    try:
        data = json.loads(_ATTRACTIONS_PATH.read_text("utf-8"))
        for a in data.get("attractions", []):
            name = a.get("name", "")
            lat = a.get("lat")
            lon = a.get("lon")
            city = a.get("city", "")
            if name and lat is not None and lon is not None:
                canonical = normalize_poi_name(name)
                entry = (float(lat), float(lon), city)

                # Canonical name index (Phase 12.12: also add raw name as key)
                for key in (canonical, name):
                    if key not in _KB_COORDS:
                        _KB_COORDS[key] = []
                    if entry not in _KB_COORDS[key]:
                        _KB_COORDS[key].append(entry)

                # Raw name index (Phase 12.12: also add normalized name as key)
                for key in (name, canonical):
                    if key not in _KB_RAW_COORDS:
                        _KB_RAW_COORDS[key] = []
                    if entry not in _KB_RAW_COORDS[key]:
                        _KB_RAW_COORDS[key].append(entry)

        total_entries = sum(len(v) for v in _KB_COORDS.values())
        raw_entries = sum(len(v) for v in _KB_RAW_COORDS.values())
        logger.debug(
            f"Loaded {len(_KB_COORDS)} canonical + {len(_KB_RAW_COORDS)} raw "
            f"names ({total_entries} entries) from KB for geo-proximity fallback"
        )
    except Exception:
        logger.warning("Failed to load KB coordinates")
    return _KB_COORDS


def _reset_kb_coords() -> None:
    """测试用：重置 KB 坐标缓存。"""
    global _KB_COORDS, _KB_RAW_COORDS
    _KB_COORDS = None
    _KB_RAW_COORDS = None


# 向后兼容别名
def _get_known_closures() -> Dict[str, Dict[str, str]]:
    return _load_closures()

_SPAN_WARN_KM = 30.0

# 纯基础设施命中（路/站/路口）不算景点存续证据
_INFRA_RE = re.compile(r"公交站|路口|地铁站|收费站|服务区")

# ── 天气自适应规划（Phase 11.2）──────────────────────────
# 偏室内活动 POI 关键词（与 itinerary_contract._INDOOR_RE 保持一致）
_INDOOR_RE = re.compile(
    r"博物馆|古镇|室内|文创|商场|酒店|午餐|晚餐|早餐|小吃|休息|午休|"
    r"寺|庙|会馆|购物|书店|剧院|餐厅|美术|图书|温泉|溶洞|茶|咖啡|手作|展馆"
)
_RAIN_WORDS = ("雨", "雷", "雪", "雹")


def _ensure_weather_dict(weather) -> Dict[str, Any]:
    """Convert WeatherForecast object to dict if needed.
    
    Handles both dict format and WeatherForecast object format.
    """
    if weather is None:
        return {}
    if hasattr(weather, 'to_dict'):
        return weather.to_dict()
    if isinstance(weather, dict):
        return weather
    return {}


def _optimize_weather_fit(
    days: List[Dict[str, Any]],
    weather: Dict[str, Any],
    city: str,
) -> List[str]:
    """天气自适应日程优化：检测户外密集日与雨天冲突，生成调整建议。

    对每一天分析室内/户外 POI 比例，结合天气预报的 travel_score、
    降水、天气描述，产出面向用户的 actionable tips：
      - 雷暴日 → 强制建议全室内
      - 雨天 + 户外密集 → 建议备雨具/调整景点 + 尝试推荐与晴天对调
      - 晴好 + 户外多 → 正面鼓励
      - 极端温度 → 防暑/防寒提醒

    Returns:
        天气相关的 tips 列表（供 optimize_itinerary 追加到 result["tips"]）。
    """
    tips: List[str] = []
    weather = _ensure_weather_dict(weather)
    daily_forecast = weather.get("daily", [])
    if not daily_forecast:
        return tips

    # ── 逐日分析 ──
    day_analysis: List[Dict[str, Any]] = []
    for i, day in enumerate(days):
        if i >= len(daily_forecast):
            break
        fc = daily_forecast[i]
        if not isinstance(fc, dict):
            continue

        items = [
            it for it in day.get("items", [])
            if isinstance(it, dict) and _is_visit(it.get("poi", ""))
        ]
        indoor = sum(1 for it in items if _INDOOR_RE.search(it.get("poi", "")))
        outdoor = len(items) - indoor

        desc = fc.get("weather_desc", "")
        precip = fc.get("precipitation", 0)
        travel_score = fc.get("travel_score", 1.0)
        temp_max = fc.get("temp_max", 25)
        temp_min = fc.get("temp_min", 15)
        weather_code = fc.get("weather_code", 0)

        is_rainy = any(w in desc for w in _RAIN_WORDS) or precip > 0.5
        is_storm = any(w in desc for w in ("雷", "雹")) or weather_code in (95, 96, 99)

        day_analysis.append({
            "index": i,
            "day_num": day.get("day", i + 1),
            "indoor": indoor,
            "outdoor": outdoor,
            "travel_score": travel_score,
            "is_rainy": is_rainy,
            "is_storm": is_storm,
            "desc": desc,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "precip": precip,
        })

    if not day_analysis:
        return tips

    # ── 雨天/雷暴冲突检测 ──
    for ds in day_analysis:
        if ds["is_storm"]:
            tips.append(
                f"⛈️ 第{ds['day_num']}天预报{ds['desc']}，"
                f"强烈建议全部安排室内活动，避免户外游览"
            )
        elif ds["is_rainy"] and ds["outdoor"] > ds["indoor"] and ds["outdoor"] > 0:
            tips.append(
                f"🌧️ 第{ds['day_num']}天预报{ds['desc']}，"
                f"有{ds['outdoor']}个户外项目，建议准备雨具并备选室内景点"
            )
            # 尝试推荐与晴天对调
            for other in day_analysis:
                if other["index"] == ds["index"]:
                    continue
                if not other["is_rainy"] and other["travel_score"] >= 0.7:
                    if other["outdoor"] <= other["indoor"]:
                        tips.append(
                            f"💡 第{ds['day_num']}天户外密集，可考虑与"
                            f"第{other['day_num']}天（{other['desc']}）对调行程"
                        )
                        break

    # ── 晴好天气正面提示 ──
    for ds in day_analysis:
        if not ds["is_rainy"] and ds["travel_score"] >= 0.85 and ds["outdoor"] >= 2:
            tips.append(
                f"☀️ 第{ds['day_num']}天{ds['desc']}，"
                f"非常适合户外游览，建议早起出发充分利用好天气"
            )

    # ── 极端温度提醒 ──
    for ds in day_analysis:
        if ds["temp_max"] > 35:
            tips.append(
                f"🔥 第{ds['day_num']}天最高{ds['temp_max']}°C，"
                f"建议避开12:00-15:00户外活动，备足饮水"
            )
        elif ds["temp_max"] > 32:
            tips.append(
                f"🌡️ 第{ds['day_num']}天{ds['temp_max']}°C，注意防晒补水"
            )
        if ds["temp_min"] < 5:
            tips.append(
                f"🧊 第{ds['day_num']}天最低{ds['temp_min']}°C，注意保暖防寒"
            )

    return tips


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── City center coordinates (Phase 12.9) ──────────────────
# Geometric centroids from KB POI data, used to validate
# nocity search results are within reasonable distance.
# Format: lat, lon (same order as _haversine_km parameters)
_NOCITY_MAX_DISTANCE_KM = 200

_CITY_CENTERS: Dict[str, Tuple[float, float]] = {
    "三亚": (18.2715, 109.5289),
    "上海": (31.1955, 121.4374),
    "大理": (25.8011, 99.9932),
    "北京": (39.9522, 116.3791),
    "南京": (32.0646, 118.8171),
    "南宁": (22.7895, 108.3813),
    "厦门": (24.4631, 118.0888),
    "哈尔滨": (45.7921, 126.5549),
    "丽江": (26.8916, 100.2803),
    "大连": (38.8893, 121.6079),
    "天津": (39.0755, 117.1865),
    "广州": (23.1251, 113.3182),
    "张家界": (29.1773, 110.5148),
    "成都": (30.6631, 103.8023),
    "拉萨": (29.6963, 91.1132),
    "昆明": (24.8661, 102.8002),
    "杭州": (30.1659, 119.998),
    "桂林": (25.1737, 110.3735),
    "武汉": (30.5747, 114.3238),
    "深圳": (22.5511, 114.047),
    "福州": (26.0924, 119.3),
    "苏州": (31.289, 120.6598),
    "西安": (34.2342, 108.9265),
    "贵阳": (26.6251, 106.6297),
    "郑州": (34.7672, 113.6357),
    "重庆": (29.7633, 106.856),
    "长沙": (28.1634, 113.0057),
    "青岛": (36.0631, 120.3752),
    "香格里拉": (27.8302, 99.6928),
    "黄山": (29.7143, 118.3229),
}


def _search_name(poi: str) -> str:
    """提取用于高德搜索的查询名：去括号补充说明，保留核心名。

    与 NameNormalizer.normalize 的区别：
    - _search_name 轻量处理，只去括号，不过度剥离后缀（保持搜索召回）
    - normalize_poi_name 全量归一化，用于名称比较
    """
    return re.split(r"[（(]", poi)[0].strip()


def _is_visit(poi: str) -> bool:
    return not _MEAL_STOP_RE.search(poi)


def _matches(query: str, hit_name: str) -> bool:
    """使用 NameNormalizer 做名称匹配（替代旧 _name_matches）。"""
    return poi_names_match(query, hit_name)


# ── Backward-compatible aliases (Phase 11.1) ───────────────
# Old function names are kept as aliases to avoid breaking imports.
# _normalize keeps old behavior (simple clean for comparison keys);
# new code should use normalize_poi_name from name_normalizer for full canonicalization.
_base_name = _search_name
_name_matches = _matches


def _core_name(name: str, suffixes: tuple = ()) -> str:
    """Backward-compatible core name extraction (accepts 'suffixes' kwarg).

    Delegates to extract_core_name with optional custom suffix list.
    """
    suf_list = list(suffixes) if suffixes else None
    return extract_core_name(name, suffixes=suf_list)


def _normalize(name: str) -> str:
    """Backward-compatible simple normalization (matches original behavior).

    This is intentionally simpler than normalize_poi_name — use normalize_poi_name
    for full canonicalization in new code.
    """
    return re.sub(r"[（）()·\s]", "", name).replace("贰", "二")


def _char_overlap_ratio(a: str, b: str) -> float:
    """Calculate Chinese character overlap ratio between two strings.

    Used as a fallback when exact name matching fails — Amap often uses
    a slightly different name format (e.g., "洪崖洞民俗风貌区" vs "洪崖洞").
    """
    # Extract only Chinese characters (U+4E00-U+9FFF)
    chars_a = set(re.findall(r'[一-鿿]', a))
    chars_b = set(re.findall(r'[一-鿿]', b))
    if not chars_a or not chars_b:
        return 0.0
    overlap = chars_a & chars_b
    # Jaccard-like: overlap / min(len(a), len(b)) — favors shorter name matching
    return len(overlap) / min(len(chars_a), len(chars_b))


async def _lookup(poi: str, city: str, known_lat: Optional[float] = None, known_lon: Optional[float] = None) -> Dict[str, Any]:
    """核实一个游览点：存续状态 + 行政区 + 坐标。

    Phase 12.11: When Amap is unavailable, falls back to KB coordinate
    matching. KB-matched POIs get status "kb_verified" instead of "unknown",
    and KB coordinates are used directly for route calculation.

    状态判定（保守原则）：
    - ok:      有 Amap 名称匹配的命中（坐标/区县可信）
    - ok_geo:  名称不匹配但存在 ≤500m 内的地理邻近命中
    - ok_fuzzy: 名称不完全匹配但字符重叠率 ≥50%
    - kb_verified: Amap 不可用，KB 坐标匹配成功（Phase 12.11）
    - unknown: 搜索失败或无匹配命中——保留原 POI 并提示人工确认
    """
    base = _search_name(poi)
    core = normalize_poi_name(poi)

    # ── Phase 12.11: KB-only mode when Amap is unavailable ──
    if not is_amap_available():
        coords = _load_kb_coords()
        raw_coords = _KB_RAW_COORDS or {}

        def _city_filter(entries):
            """Prefer same-city match; return best entry."""
            if not entries:
                return None
            # Exact city match
            match = next(
                (e for e in entries if e[2] == city or city in e[2] or e[2] in city),
                None,
            )
            if match:
                return match
            # Same-city entries only — no cross-city fallback (Phase 12.11)
            # Cross-city matches produce 1000+ km routes and are worse than
            # leaving the POI unknown (which skips it in route calc).
            return None

        # 1. Canonical name exact match (city-filtered)
        candidates = coords.get(core, [])
        kb_coord = _city_filter(candidates)

        # 2. Search_name canonical match
        if kb_coord is None:
            candidates = coords.get(normalize_poi_name(base), [])
            kb_coord = _city_filter(candidates)

        # 3. Raw name substring + character overlap matching (city-filtered)
        # Phase 12.12: Collect ALL candidates instead of breaking on first.
        # Prefer landmark entries over food/restaurant entries, because
        # restaurant names often contain landmark names as location suffixes
        # (e.g., "聂发财重庆江湖菜(解放碑店)" vs actual "解放碑").
        # Also use character overlap for non-contiguous substring matches.
        if kb_coord is None:
            candidates: List[Tuple[float, Tuple, str]] = []  # (score, (lat,lon,city), raw_name)
            seen = set()
            for raw_name, entries in raw_coords.items():
                # 3a. Substring match (contiguous)
                if base in raw_name or raw_name in base or core in raw_name:
                    city_entry = _city_filter(entries)
                    if city_entry and city_entry not in seen:
                        seen.add(city_entry)
                        # Score: prefer shorter raw_name (landmarks are shorter than
                        # restaurant names), penalize food keywords
                        raw_len = len(raw_name)
                        is_food = bool(_MEAL_STOP_RE.search(raw_name))
                        score = 100.0 - raw_len - (50.0 if is_food else 0.0)
                        candidates.append((score, city_entry, raw_name))
                        continue

                # 3b. Non-contiguous character overlap (≥50%, min 2 chars)
                overlap = _char_overlap_ratio(poi, raw_name)
                if overlap >= 0.50 and len(set(re.findall(r'[一-鿿]', poi)) & set(re.findall(r'[一-鿿]', raw_name))) >= 2:
                    city_entry = _city_filter(entries)
                    if city_entry and city_entry not in seen:
                        seen.add(city_entry)
                        is_food = bool(_MEAL_STOP_RE.search(raw_name))
                        score = overlap * 100.0 - (30.0 if is_food else 0.0)
                        candidates.append((score, city_entry, raw_name))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_score, kb_coord, best_raw = candidates[0]
                logger.debug(
                    f"KB raw match: '{poi}' (score={best_score:.0f}) → "
                    f"'{best_raw}' in {kb_coord[2]}"
                )

        if kb_coord is not None:
            return {
                "status": "kb_verified",
                "hit": {
                    "name": poi,
                    "adname": kb_coord[2] or city,
                    "lat": kb_coord[0],
                    "lon": kb_coord[1],
                },
                "adname": kb_coord[2] or city,
                "lat": kb_coord[0],
                "lon": kb_coord[1],
            }
        return {"status": "unknown", "hit": None, "adname": "", "lat": None, "lon": None}

    # ── Multi-pass search strategy ──────────────────────────
    # Each pass tries a progressively relaxed query. We stop at the
    # first pass that yields a credible match.
    search_attempts = [
        # Pass 1: Current behavior — search_name in target city
        (base, city, "exact_city"),
        # Pass 2: Core name in target city (more aggressive stripping)
        (core, city, "core_city"),
        # Pass 3: Search_name without city limit (cross-city, for POIs near borders)
        (base, "", "exact_nocity"),
        # Pass 4: Core name without city limit
        (core, "", "core_nocity"),
    ]

    all_hits: List[Tuple[Dict[str, Any], str]] = []  # (hit, strategy)
    seen_names: set = set()

    for search_term, search_city, strategy in search_attempts:
        if not search_term or len(search_term) < 2:
            continue
        # Skip duplicate searches
        dedup_key = f"{search_term}|{search_city}"
        if dedup_key in seen_names:
            continue
        seen_names.add(dedup_key)

        hits = await search_poi(search_term, search_city, limit=5)
        for h in hits:
            if _INFRA_RE.search(h["name"]):
                continue
            hit_key = h["name"]
            if hit_key not in {x[0]["name"] for x in all_hits}:
                all_hits.append((h, strategy))

    # ── Match scoring: try strict first, then relaxed ──────
    best_non_infra: Optional[Dict[str, Any]] = None
    best_strategy = ""

    for h, strategy in all_hits:
        if best_non_infra is None:
            best_non_infra = h
            best_strategy = strategy

        # Exact match using NameNormalizer (canonical containment)
        if await _matches(base, h["name"]) or await _matches(core, h["name"]):
            logger.debug(f"POI verified '{poi}' → Amap '{h['name']}' (strategy={strategy})")
            return {
                "status": "ok",
                "hit": h,
                "adname": h.get("adname", ""),
                "lat": h.get("lat"),
                "lon": h.get("lon"),
            }

    # ── Character overlap fallback (Phase 12.8) ─────────────
    # When exact/containment matching fails, use Chinese character
    # overlap ratio. Threshold: ≥50% overlap with the best non-infra hit.
    #
    # Phase 12.9: For nocity strategies, validate that the matched POI
    # coordinates are within _NOCITY_MAX_DISTANCE_KM of the expected city
    # center. This prevents cross-city false positives from inflating
    # daily route distances to 1000+ km.
    city_center = _CITY_CENTERS.get(city)
    if best_non_infra is not None:
        for h, strategy in all_hits:
            overlap = _char_overlap_ratio(poi, h["name"])
            if overlap >= 0.50:
                # Geo-distance check for nocity strategies
                if "nocity" in strategy and city_center is not None:
                    hlat = h.get("lat")
                    hlon = h.get("lon")
                    if hlat is not None and hlon is not None:
                        dist = _haversine_km(
                            city_center[0], city_center[1], float(hlat), float(hlon)
                        )
                        if dist > _NOCITY_MAX_DISTANCE_KM:
                            logger.debug(
                                f"POI '{poi}' fuzzy-matched '{h['name']}' "
                                f"but rejected: {dist:.0f}km from {city} "
                                f"(strategy={strategy}, max={_NOCITY_MAX_DISTANCE_KM}km)"
                            )
                            continue  # skip this cross-city false positive
                        logger.debug(
                            f"POI '{poi}' fuzzy-matched '{h['name']}' "
                            f"with nocity, distance ok: {dist:.0f}km from {city}"
                        )
                logger.info(
                    f"POI fuzzy-matched '{poi}' → Amap '{h['name']}' "
                    f"(overlap={overlap:.0%}, strategy={strategy})"
                )
                return {
                    "status": "ok_fuzzy",
                    "hit": h,
                    "adname": h.get("adname", ""),
                    "lat": h.get("lat"),
                    "lon": h.get("lon"),
                }

    # ── Geo-proximity fallback ──────────────────────────────
    if known_lat is not None and known_lon is not None and best_non_infra is not None:
        hlat = best_non_infra.get("lat")
        hlon = best_non_infra.get("lon")
        if hlat is not None and hlon is not None:
            dist = _haversine_km(known_lat, known_lon, float(hlat), float(hlon))
            if dist <= 0.5:  # 500m
                logger.info(
                    f"Geo-matched '{base}' to Amap '{best_non_infra['name']}' "
                    f"(dist={dist*1000:.0f}m)"
                )
                return {
                    "status": "ok_geo",
                    "hit": best_non_infra,
                    "adname": best_non_infra.get("adname", ""),
                    "lat": best_non_infra.get("lat"),
                    "lon": best_non_infra.get("lon"),
                }

    return {"status": "unknown", "hit": None, "adname": "", "lat": None, "lon": None}


def _district_core(adname: str) -> str:
    """渝中区 → 渝中；沙坪坝区 → 沙坪坝；大理市 → 大理"""
    return re.sub(r"(区|县|市|州)$", "", adname or "")


def _theme_districts(theme: str) -> List[str]:
    """从 theme 文本中提取可能的行政区核心名（2-4 字，出现在已知区县名中才算）。"""
    # theme 形如 「DAY 1 · 渝中母城」/「DAY 2 · 沙坪坝 · 磁器口」
    parts = re.split(r"[·\s,/，、]+", theme.replace("DAY", " "))
    return [p for p in (x.strip() for x in parts) if 2 <= len(p) <= 4 and p and not p.isdigit()]


# ── 跨天地理再平衡（Phase 12.21）──────────────────────────

_GEO_REBALANCE_MAX_KM = 200.0  # 与评测 route_ok 阈值一致


def _rebalance_days_geographically(
    days: List[Dict[str, Any]],
    lookups: Dict[str, Dict[str, Any]],
    tips: Optional[List[str]] = None,
    max_km: float = _GEO_REBALANCE_MAX_KM,
) -> int:
    """把"混入远郊日的近郊/市区点"移回地理上属于它的那天。

    背景（q08 桂林 250km 根因）：KB-only 模式下 Step 3 区域归位失效
    （KB 无区县字段，所有 adname 全城同名），而 Step 4 最近邻重排只做
    同天内排序，无法把地理上互不相干的 POI 拆到不同天。

    策略（保证收敛）：每轮找出链长最长的一天，在其游览点中挑选
    "迁移代价最小"（插入他天后他天链长最短）的候选，仅当
    max(源天新链长, 目标天新链长) 严格小于当前最大链长时才执行移动，
    因此全局最大链长单调下降、不会震荡。返回移动的条目数。
    """
    def _chain(day: Dict[str, Any]) -> float:
        pts = []
        for it in day.get("items", []):
            if not _is_visit(it.get("poi", "")):
                continue
            info = lookups.get(it["poi"], {}) or {}
            if info.get("lat") and info.get("lon"):
                pts.append((info["lat"], info["lon"]))
        return sum(_haversine_km(*a, *b) for a, b in zip(pts, pts[1:]))

    def _chain_without(day: Dict[str, Any], skip_id: int) -> float:
        pts = []
        for it in day.get("items", []):
            if id(it) == skip_id or not _is_visit(it.get("poi", "")):
                continue
            info = lookups.get(it["poi"], {}) or {}
            if info.get("lat") and info.get("lon"):
                pts.append((info["lat"], info["lon"]))
        return sum(_haversine_km(*a, *b) for a, b in zip(pts, pts[1:]))

    def _best_insertion_chain(day: Dict[str, Any], item: Dict[str, Any]) -> float:
        """item 插入 day 后能达到的最短链长（遍历插入位置）。"""
        items = day.get("items", [])
        best = None
        for pos in range(len(items) + 1):
            items.insert(pos, item)
            length = _chain(day)
            items.remove(item)
            if best is None or length < best:
                best = length
        return best if best is not None else _chain(day)

    moved = 0
    for _ in range(len(days) * 4):  # 迭代上限兜底（理论上不会触达）
        km_by_day = [_chain(d) for d in days]
        if not km_by_day:
            break
        worst = max(range(len(days)), key=lambda i: km_by_day[i])
        current_max = km_by_day[worst]
        if current_max <= max_km:
            break
        src = days[worst]

        # 候选：源天里有坐标的游览点，按"迁移后目标天链长"升序
        candidates = []
        for item in src.get("items", []):
            if not _is_visit(item.get("poi", "")):
                continue
            info = lookups.get(item["poi"], {}) or {}
            if not (info.get("lat") and info.get("lon")):
                continue
            src_after = _chain_without(src, id(item))
            for dst_idx, dst_day in enumerate(days):
                if dst_idx == worst:
                    continue
                dst_after = _best_insertion_chain(dst_day, item)
                candidates.append((dst_after, src_after, item, dst_idx))
        candidates.sort(key=lambda x: x[0])

        accepted = False
        for dst_after, src_after, item, dst_idx in candidates:
            # 条目数保护：源天 ≥2、目标天 ≤8（与 Step 3 同族约束）
            if len(src["items"]) - 1 < 2 or len(days[dst_idx]["items"]) + 1 > 8:
                continue
            if max(src_after, dst_after) >= current_max - 0.1:
                continue  # 不改善全局最大链长，跳过
            src["items"].remove(item)
            dst_day = days[dst_idx]
            # 按最短链长位置插入
            best_pos, best_len = len(dst_day["items"]), None
            for pos in range(len(dst_day["items"]) + 1):
                dst_day["items"].insert(pos, item)
                length = _chain(dst_day)
                dst_day["items"].remove(item)
                if best_len is None or length < best_len:
                    best_len, best_pos = length, pos
            dst_day["items"].insert(best_pos, item)
            moved += 1
            accepted = True
            msg = (
                f"⚠️ 「{_search_name(item['poi'])}」与第 {src.get('day')} 天其他景点距离较远，"
                f"已调整到第 {dst_day.get('day')} 天，减少往返奔波"
            )
            if tips is not None:
                tips.append(msg)
            logger.info(
                f"Geo rebalance: {item['poi']} day{src.get('day')} → "
                f"day{dst_day.get('day')} (max {current_max:.0f}km → "
                f"{max(src_after, dst_after):.0f}km)"
            )
            break
        if not accepted:
            break  # 无可改善的移动（如所有远点彼此都远），保留原状
    return moved


async def optimize_itinerary(
    data: Dict[str, Any],
    city: str,
    weather: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """对 LLM 生成的行程草案做存续/归属/顺路处理。

    Args:
        data: LLM 生成的行程草案（contract-valid）。
        city: 目标城市。
        weather: 可选天气预报（WeatherForecast.to_dict()），用于天气自适应日程优化。

    返回 (处理后的行程, 校验报告)：
    - 校验报告汇总每个 POI 的存续状态、每日路线里程/折返结论、校验日期，
      供 docs/itinerary.schema.json 的 validation_report 字段使用。
    """
    result = copy.deepcopy(data)
    days = result.get("days", [])
    tips: List[str] = result.setdefault("tips", [])
    city = city or (result.get("trip") or {}).get("city", "")
    replaced_notes: Dict[str, str] = {}  # 新 POI 名 → 替换说明（报告用）
    
    # Normalize weather to dict format
    weather = _ensure_weather_dict(weather)

    # ── Step 1: 并发核实所有游览点 ───────────────────────
    poi_set: List[str] = []
    for day in days:
        for item in day.get("items", []):
            if _is_visit(item.get("poi", "")) and item.get("poi") not in poi_set:
                poi_set.append(item["poi"])

    sem = asyncio.Semaphore(3)

    async def _bounded(poi: str):
        async with sem:
            base = _search_name(poi)
            if base in _load_closures():
                return poi, {
                    "status": "closed",
                    "info": (_load_closures())[base],
                    "adname": "",
                    "lat": None,
                    "lon": None,
                }
            # Load KB coords for geo-proximity fallback
            coords = _load_kb_coords()
            canonical = normalize_poi_name(poi)
            entries = coords.get(canonical, [])
            # Prefer same-city entry, then first available
            city_entry = next((e for e in entries if e[2] == city or city in e[2] or e[2] in city), None)
            entry = city_entry or (entries[0] if entries else None)
            kb_lat, kb_lon = (entry[0], entry[1]) if entry else (None, None)
            info = await _lookup(poi, city, known_lat=kb_lat, known_lon=kb_lon)
            return poi, info

    lookups: Dict[str, Dict[str, Any]] = dict(
        await asyncio.gather(*[_bounded(p) for p in poi_set])
    )

    # ── Step 2: 停业 POI 替换（仅 _load_closures() 实证清单）──
    trip_poi_names: Set[str] = set()
    for day in days:
        for item in day.get("items", []):
            trip_poi_names.add(normalize_poi_name(_search_name(item.get("poi", ""))))

    for day in days:
        for item in day.get("items", []):
            if not _is_visit(item.get("poi", "")):
                continue
            poi = item["poi"]
            info = lookups.get(poi, {})
            status = info.get("status")

            if status == "unknown":
                if is_amap_available():
                    tips.append(
                        f"⚠️ 「{_search_name(poi)}」未能在高德地图核实到在营状态，"
                        f"高德数据覆盖有限，建议出行前再确认"
                    )
                else:
                    tips.append(
                        f"⚠️ 「{_search_name(poi)}」未在知识库中找到坐标，"
                        f"建议出行前通过地图 App 确认位置和营业状态"
                    )
                continue

            if status != "closed":
                continue

            closures = _load_closures()
            closure = closures[_search_name(poi)]
            alts = await search_poi(closure["replacement_keyword"], city, limit=5)
            replacement = None
            for a in alts:
                if not _INFRA_RE.search(a["name"]) and normalize_poi_name(a["name"]) not in trip_poi_names:
                    replacement = a
                    break
            if replacement is None:
                tips.append(f"⚠️ 「{poi}」{closure['evidence']}，请出行前重新规划该景点")
                continue

            old = poi
            item["poi"] = replacement["name"]
            # Phase 8.2: Enhanced replacement notification
            note = closure.get("replacement_note") or (
                f"原计划「{_search_name(old)}」{closure['evidence']}，"
                f"已替换为同在{replacement.get('adname', city)}的{replacement['name']}"
            )
            item["note"] = f"⚠️ {note}；建议预留 2 小时慢逛"
            replaced_notes[replacement["name"]] = (
                f"原计划「{_search_name(old)}」{closure['evidence']}，已核实替换"
            )
            trip_poi_names.add(normalize_poi_name(replacement["name"]))
            lookups[replacement["name"]] = {
                "status": "ok",
                "hit": replacement,
                "adname": replacement.get("adname", ""),
                "lat": replacement.get("lat"),
                "lon": replacement.get("lon"),
            }
            logger.info(f"POI replaced: {old} → {replacement['name']}")

    # ── Step 3: 区域归属（仅行政区型 theme）──────────────
    day_districts: List[set] = []
    for day in days:
        cores = set(_theme_districts(day.get("theme", "")))
        # 只保留真正是区县名的（与核实到的 adname 核心名匹配）
        known = {
            _district_core(info.get("adname", ""))
            for info in lookups.values()
            if info.get("adname")
        }
        day_districts.append(cores & known if cores & known else cores)

    for src_idx, day in enumerate(days):
        district = day_districts[src_idx]
        if not district:
            continue  # 非行政区型 theme，不约束
        moved = []
        for item in list(day.get("items", [])):
            if not _is_visit(item.get("poi", "")):
                continue
            info = lookups.get(item["poi"], {}) or lookups.get(_search_name(item["poi"]), {})
            core = _district_core(info.get("adname", ""))
            if not core or core in district:
                continue
            # 目标天：theme 包含该核心名
            dst_idx = next(
                (i for i, ds in enumerate(day_districts) if core in ds and i != src_idx),
                None,
            )
            if dst_idx is None:
                tips.append(
                    f"⚠️ 「{_search_name(item['poi'])}」在{info.get('adname')}，"
                    f"与第 {day.get('day')} 天主题不完全同区，建议打车衔接"
                )
                continue
            # 双方天数都保持 ≥3 条才移动
            if len(day["items"]) - 1 < 3 or len(days[dst_idx]["items"]) + 1 > 8:
                continue
            day["items"].remove(item)
            days[dst_idx]["items"].append(item)
            moved.append((item["poi"], dst_idx))
            logger.info(f"Region fix: {item['poi']} day{day.get('day')} → day{days[dst_idx].get('day')}")

    # ── Step 4: 同日最近邻顺路重排 ──────────────────────
    reordered_days: set = set()
    for day in days:
        items = day.get("items", [])
        visit_idx = [i for i, it in enumerate(items) if _is_visit(it.get("poi", ""))]
        if len(visit_idx) < 3:
            continue

        coords: Dict[int, Tuple[float, float]] = {}
        for i in visit_idx:
            info = lookups.get(items[i]["poi"], {}) or {}
            if info.get("lat") and info.get("lon"):
                coords[i] = (info["lat"], info["lon"])
        if len(coords) < 3:
            continue

        # 最近邻链：从原第一个有坐标的游览点出发
        start = visit_idx[0] if visit_idx[0] in coords else next(iter(coords))
        chain = [start]
        remaining = set(coords) - {start}
        while remaining:
            last = chain[-1]
            nxt = min(
                remaining,
                key=lambda i: _haversine_km(*coords[last], *coords[i]),
            )
            chain.append(nxt)
            remaining.discard(nxt)

        # 只在显著省时（链长缩短 ≥30%）才重排——
        # 模型给出的顺序通常已兼顾时间逻辑，盲目最近邻会打乱时间流
        def _chain_len(order):
            pts = [coords[i] for i in order if i in coords]
            return sum(
                _haversine_km(*a, *b) for a, b in zip(pts, pts[1:])
            )

        original_len = _chain_len(visit_idx)
        optimized_len = _chain_len(chain)
        # Phase 12.8: Lowered reorder threshold from 0.70 to 0.85 —
        # reorder if the optimized chain is ≥15% shorter (was ≥30%).
        # This catches more moderate backtracking without risking
        # unnecessary disruption of the LLM's time-logic ordering.
        if original_len <= 0 or optimized_len >= original_len * 0.85:
            continue

        # 只重排有坐标的游览点顺序
        new_order = list(range(len(items)))
        coord_slots = sorted(coords)
        for slot, idx_in_chain in zip(coord_slots, chain):
            new_order[slot] = idx_in_chain
        day["items"] = [items[i] for i in new_order]
        # Phase 12.17: 重排后将被移动游览点的时间槽按升序回填，
        # 保持当天时间线按钟点递增（否则前端时间轴会出现
        # 13:30 排在 12:00 之前的混乱展示）
        slot_times = sorted(
            t for s in coord_slots if (t := day["items"][s].get("time", ""))
        )
        for s, t in zip(coord_slots, slot_times):
            day["items"][s]["time"] = t
        reordered_days.add(day.get("day"))
        logger.info(
            f"Route reordered day {day.get('day')}: "
            f"{original_len:.1f}km → {optimized_len:.1f}km"
        )

        # ── 跨度标注 ──
        ordered_coords = [
            (info.get("lat"), info.get("lon"))
            for it in day["items"]
            if _is_visit(it["poi"])
            for info in [lookups.get(it["poi"], {}) or {}]
            if info.get("lat") and info.get("lon")
        ]
        for a, b in zip(ordered_coords, ordered_coords[1:]):
            span = _haversine_km(a[0], a[1], b[0], b[1])
            if span > _SPAN_WARN_KM:
                tips.append(
                    f"⚠️ 第 {day.get('day')} 天相邻景点跨度约 {span:.0f}km，"
                    f"建议打车或轨交衔接，预留通勤时间"
                )
                break

    # ── Step 4.6: 跨天地理再平衡（Phase 12.21）────────────
    # KB-only 模式下 Step 3 区域归位失效（adname 全城同名），
    # 单日链长可能超过 200km（q08 根因），这里做跨天拆分兜底。
    _rebalance_days_geographically(days, lookups, tips=tips)

    # tips 去重
    seen = set()
    deduped = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    result["tips"] = deduped[:6]  # 契约 maxItems 6

    # ── Step 4.5: 天气自适应日程优化（Phase 11.2）──────
    # 当天气数据可用时，检测户外密集日与雨天冲突并生成调整建议
    if weather and weather.get("daily") and len(weather["daily"]) >= len(days):
        try:
            weather_tips = _optimize_weather_fit(days, weather, city)
            for wt in weather_tips:
                if wt not in seen:
                    seen.add(wt)
                    deduped.append(wt)
            result["tips"] = deduped[:6]
        except Exception as e:
            logger.debug(f"Weather optimization skipped: {e}")

    # ── 校验报告组装（schema.validation_report 用）──────
    report_poi: List[Dict[str, Any]] = []
    seen_poi: set = set()
    for day in days:
        for item in day.get("items", []):
            if not _is_visit(item.get("poi", "")):
                continue
            poi = item["poi"]
            if poi in seen_poi:
                continue
            seen_poi.add(poi)
            info = lookups.get(poi, {}) or {}
            entry: Dict[str, Any] = {"name": poi}
            if poi in replaced_notes:
                entry["status"] = "replaced"
                entry["note"] = replaced_notes[poi]
            else:
                status = info.get("status")
                if status in ("ok", "ok_geo", "ok_fuzzy", "kb_verified"):
                    entry["status"] = "verified"
                elif status == "closed":
                    entry["status"] = "closed"
                    entry["note"] = "已确认停业/搬迁"
                else:
                    entry["status"] = "unknown"
                    if is_amap_available():
                        entry["note"] = "高德地图未核实到在营状态，建议出行前确认"
                    else:
                        entry["note"] = "知识库未找到坐标，建议出行前通过地图App确认"
            district = info.get("adname") or (
                lookups.get(_search_name(poi)) or {}
            ).get("adname", "")
            if district:
                entry["district"] = district
            report_poi.append(entry)

    verified_n = sum(1 for e in report_poi if e["status"] in ("verified", "replaced"))

    report_routes: List[Dict[str, Any]] = []
    for day in days:
        pts = []
        for it in day.get("items", []):
            if not _is_visit(it.get("poi", "")):
                continue
            info = lookups.get(it["poi"], {}) or {}
            if info.get("lat") and info.get("lon"):
                pts.append((info["lat"], info["lon"]))
        total_km = round(sum(_haversine_km(*a, *b) for a, b in zip(pts, pts[1:])), 1)
        route_entry: Dict[str, Any] = {
            "day": day.get("day"),
            "total_km": total_km,
            "backtrack": day.get("day") in reordered_days,
        }
        if route_entry["backtrack"]:
            route_entry["note"] = "检测到折返，已按地理顺路重排"
        report_routes.append(route_entry)

    report = {
        "poi": report_poi,
        "poi_verified": f"{verified_n}/{len(report_poi)}",
        "routes": report_routes,
        "route_backtrack": any(r["backtrack"] for r in report_routes),
        "checked_at": date.today().isoformat(),
    }
    return result, report

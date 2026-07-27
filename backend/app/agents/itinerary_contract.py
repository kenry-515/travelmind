"""
TravelMind Agent — Itinerary Contract (single source of truth)

The contract lives in docs/itinerary.schema.json. This module is the ONLY
place that loads it — generation (tool params), validation, and backend-owned
field injection all derive from it.

Backend-owned fields (never left to the LLM):
  - trip.dateStart / dateEnd / daysCount  (real calendar, LLM would hallucinate)
  - budget[].percent                      (computed from amount, sums to 100)
  - checklist[].done                      (forced false, user ticks in UI)
  - schemaVersion
"""

import copy
import json
import logging
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft7Validator

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = _ROOT / "docs" / "itinerary.schema.json"
SCHEMA_VERSION = "1.0"

# Sum(budget.amount) must be within this ratio of the stated 人均预算 stat
BUDGET_SUM_TOLERANCE = 0.15


@lru_cache(maxsize=1)
def load_schema() -> Dict[str, Any]:
    """Load the contract JSON Schema (cached)."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def schema_for_llm() -> Dict[str, Any]:
    """Contract adapted for tool-calling: budget percent is NOT required
    from the model — the backend computes it from amount."""
    schema = copy.deepcopy(load_schema())
    schema.pop("$schema", None)
    budget_items = schema["properties"]["budget"]["items"]
    budget_items["required"] = ["label", "amount"]
    return schema


def validate_itinerary(data: Any) -> List[str]:
    """Full-contract validation. Returns a list of error strings (empty = valid)."""
    validator = Draft7Validator(load_schema())
    errors = []
    for e in validator.iter_errors(data):
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errors.append(f"{path}: {e.message}")
    return errors


def validate_pre_injection(data: Any) -> List[str]:
    """Validate raw model output BEFORE backend injection — at that point
    budget percent does not exist yet (the backend computes it), so use the
    LLM-facing schema where percent is not required."""
    validator = Draft7Validator(schema_for_llm())
    errors = []
    for e in validator.iter_errors(data):
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errors.append(f"{path}: {e.message}")
    return errors


def validate_day(day: Any) -> List[str]:
    """Validate a single day object against the contract's days.items subschema."""
    subschema = load_schema()["properties"]["days"]["items"]
    return [e.message for e in Draft7Validator(subschema).iter_errors(day)]


def validate_day_continuity(data: Dict[str, Any]) -> List[str]:
    """day numbers must be 1..N and trip.daysCount must match len(days)."""
    errors = []
    days = data.get("days", []) if isinstance(data, dict) else []
    numbers = [d.get("day") for d in days if isinstance(d, dict)]
    if numbers != list(range(1, len(days) + 1)):
        errors.append(f"day 编号不连续: {numbers}")
    trip = data.get("trip") if isinstance(data.get("trip"), dict) else {}
    days_count = trip.get("daysCount")
    if days_count is not None and days_count != len(days):
        errors.append(f"daysCount({days_count}) 与 days 长度({len(days)}) 不一致")
    return errors


def _fmt_date(d: date) -> str:
    return f"{d.month}月{d.day}日"


def inject_computed_fields(data: Dict[str, Any], start: Optional[date] = None) -> Dict[str, Any]:
    """Inject all backend-owned fields in place; returns the same dict."""
    start = start or date.today()
    days = data.get("days", [])
    if not isinstance(days, list):
        days = data["days"] = []

    trip = data.setdefault("trip", {})
    if not isinstance(trip, dict):
        trip = data["trip"] = {}
    trip["dateStart"] = _fmt_date(start)
    trip["dateEnd"] = _fmt_date(start + timedelta(days=max(len(days) - 1, 0)))
    trip["daysCount"] = len(days)

    # budget percent — largest-remainder rounding so they sum to exactly 100
    budget = [b for b in data.get("budget", []) if isinstance(b, dict)]
    total = sum(b.get("amount", 0) for b in budget)
    if total > 0:
        raw = [(i, 100.0 * b.get("amount", 0) / total) for i, b in enumerate(budget)]
        percents = {i: int(v) for i, v in raw}
        remainder = 100 - sum(percents.values())
        for i, v in sorted(raw, key=lambda x: -(x[1] - int(x[1]))):
            if remainder <= 0:
                break
            percents[i] += 1
            remainder -= 1
        for i, b in enumerate(budget):
            b["percent"] = percents.get(i, 0)
    else:
        for b in budget:
            b["percent"] = 0

    for item in data.get("checklist", []):
        if isinstance(item, dict):
            item["done"] = False

    inject_place_count(data)
    data["schemaVersion"] = SCHEMA_VERSION
    return data


def budget_sum_mismatch(data: Dict[str, Any]) -> bool:
    """True when sum(budget.amount) diverges from the stated 人均预算 stat
    beyond BUDGET_SUM_TOLERANCE (skipped when the stat is unparseable)."""
    total = sum(
        b.get("amount", 0) for b in data.get("budget", []) if isinstance(b, dict)
    )
    trip = data.get("trip") if isinstance(data.get("trip"), dict) else {}
    for stat in trip.get("stats", []):
        if not isinstance(stat, dict):
            continue
        if "预算" in stat.get("label", ""):
            m = re.search(r"([\d,]+)", stat.get("value", ""))
            if m:
                stated = int(m.group(1).replace(",", ""))
                if stated > 0:
                    return abs(total - stated) / stated > BUDGET_SUM_TOLERANCE
    return False


# ── Stats governance (backend-owned derivable numbers) ──

# Items that are meal/rest/hotel stops, not visitable places (excluded from 地点数)
_MEAL_STOP_RE = re.compile(r"午餐|晚餐|早餐|宵夜|小吃|用餐|餐厅|食堂|饭店|美食街|午休|休息|酒店|住宿")

# stats entry whose label marks the place count (backend overwrites it)
_PLACE_COUNT_LABEL_RE = re.compile(r"景点|地点|去处|打卡地")


def count_places(data: Dict[str, Any]) -> int:
    """Total day items minus meal stops."""
    count = 0
    for day in data.get("days", []):
        if not isinstance(day, dict):
            continue
        for item in day.get("items", []):
            if not isinstance(item, dict):
                continue
            if not _MEAL_STOP_RE.search(item.get("poi", "")):
                count += 1
    return count


def inject_place_count(data: Dict[str, Any]) -> Dict[str, Any]:
    """Overwrite the 地点数 stat with the backend-computed value (append the
    entry if the model omitted it, respecting stats maxItems=6)."""
    n = count_places(data)
    trip = data.setdefault("trip", {})
    if not isinstance(trip, dict):
        data["trip"] = trip = {}
    stats = trip.setdefault("stats", [])
    if not isinstance(stats, list):
        stats = trip["stats"] = []
    for stat in stats:
        if isinstance(stat, dict) and _PLACE_COUNT_LABEL_RE.search(stat.get("label", "")):
            stat["value"] = f"{n} 个"
            break
    else:
        if len(stats) < 6:
            stats.insert(1, {"value": f"{n} 个", "label": "计划地点"})
    return data


# ── Month / season consistency ───────────────────────────

_MONTH_RE = re.compile(r"(\d{1,2})月")

_SEASONS = {12: "冬季", 1: "冬季", 2: "冬季",
            3: "春季", 4: "春季", 5: "春季",
            6: "夏季", 7: "夏季", 8: "夏季",
            9: "秋季", 10: "秋季", 11: "秋季"}


def season_of(month: int) -> str:
    return _SEASONS.get(month, "")


def _collect_texts(data: Dict[str, Any]) -> List[str]:
    """All user-visible free-text fields where a wrong month could appear.
    Type-tolerant: malformed entries are left to the schema validator."""
    texts: List[str] = []
    texts.extend(t for t in data.get("tips", []) if isinstance(t, str))
    for c in data.get("checklist", []):
        if isinstance(c, dict):
            texts.append(c.get("text", ""))
        elif isinstance(c, str):
            texts.append(c)
    for day in data.get("days", []):
        if not isinstance(day, dict):
            continue
        texts.append(day.get("eat", ""))
        for item in day.get("items", []):
            if isinstance(item, dict):
                texts.append(item.get("note", ""))
    return [t for t in texts if isinstance(t, str)]


def month_inconsistency_errors(data: Dict[str, Any], trip_month: int) -> List[str]:
    """Any explicit 'X月' reference that contradicts the trip month."""
    errors = []
    for text in _collect_texts(data):
        for m in _MONTH_RE.finditer(text):
            month = int(m.group(1))
            if 1 <= month <= 12 and month != trip_month:
                errors.append(f"月份不符（行程为 {trip_month} 月）: {text[:60]}")
                break
    return errors


# ── Weather coverage requirements ────────────────────────

_RAIN_WORDS = ("雨", "雷", "雪", "雹")
_WEATHER_ITEM_RE = re.compile(r"雨|伞|雷暴|降水|天气|防晒|防风|雪")


def trip_has_rain(weather: Optional[Dict[str, Any]], days_count: int) -> bool:
    """True if any of the trip's days (first daysCount entries) forecasts rain."""
    if not weather:
        return False
    for d in (weather.get("daily") or [])[: max(days_count, 1)]:
        desc = d.get("weather_desc", "") or ""
        if any(w in desc for w in _RAIN_WORDS):
            return True
        if (d.get("precipitation") or 0) > 0.5:
            return True
    return False


def weather_coverage_errors(data: Dict[str, Any]) -> List[str]:
    """When the trip forecasts rain: tips must include ≥1 weather-related
    entry and checklist ≥1 weather-related item."""
    errors = []
    if not any(
        _WEATHER_ITEM_RE.search(t) for t in data.get("tips", []) if isinstance(t, str)
    ):
        errors.append("有降雨预报但 tips 中没有天气相关提示")
    checklist_texts = []
    for c in data.get("checklist", []):
        if isinstance(c, dict):
            checklist_texts.append(c.get("text", ""))
        elif isinstance(c, str):
            checklist_texts.append(c)
    if not any(_WEATHER_ITEM_RE.search(t) for t in checklist_texts):
        errors.append("有降雨预报但 checklist 中没有天气相关物品（如折叠伞）")
    return errors


# ── Weather fit (validation_report 用) ───────────────────

# 偏室内活动的 POI 关键词（粗略启发式，用于天气匹配度评估）
# Phase 12.14: 大幅扩展室内关键词 — 7月盛夏雨季需要更广的室内识别范围
_INDOOR_RE = re.compile(
    r"博物馆|古镇|室内|文创|商场|酒店|午餐|晚餐|早餐|小吃|休息|午休|"
    r"寺|庙|会馆|购物|书店|剧院|餐厅|美术|图书|温泉|溶洞|茶|咖啡|手作|展馆|"
    r"水族馆|海洋馆|科技馆|规划馆|故居|纪念馆|祠堂|宫|庵|洞|城|街|巷|里|坊|"
    r"夜市|集市|市场|影院|酒吧|LiveHouse|SPA|足浴|棋牌|密室|剧本|"
    r"购物中心|步行街|美食街|美食城|小吃街|茶馆|咖啡馆|甜品店|火锅|海鲜|"
    r"面馆|家常菜|烤鸭|料理|西餐|自助餐|大排檔|大排档|食堂|宴会|"
    r"别墅|私房菜|土菜|本地菜|"
    r"画廊|书院|文化宫|少年宫|图书馆|档案馆|陈列馆|艺术馆|博览馆|"
    r"火车站|机场|码头|地铁|客运|"
    r"体验馆|DIY|陶艺|烘焙|画室|琴行|"
    r"教堂|清真寺|道观|佛寺|禅院|庵堂|礼拜堂"
)

# Phase 12.15: Tag-based indoor/outdoor classification（KB 标签优先于名称正则）
_TAG_INDOOR_KW = (
    "博物馆", "展览", "美术馆", "画廊", "购物", "商场", "美食", "餐饮",
    "小吃", "餐厅", "火锅", "温泉", "剧院", "影院", "酒吧", "SPA",
    "酒店", "民宿", "书店", "图书馆", "科技馆", "规划馆", "手工", "DIY",
    "体验馆", "水族馆", "海洋馆", "室内", "教堂", "清真寺", "故居",
    "纪念馆", "祠堂", "夜市", "咖啡馆", "茶馆", "中餐", "海鲜", "古镇",
    "历史街区", "步行街", "美食街", "购物中心", "老字号", "夜生活",
    "手作", "陶艺", "烘焙", "画室", "琴行", "密室", "剧本", "棋牌",
    "KTV", "网吧", "展馆", "道观", "佛寺", "禅院", "庵堂", "礼拜堂",
    "古建筑", "现代建筑", "世界遗产",  # buildings → semi-indoor
)

_TAG_OUTDOOR_KW = (
    "公园", "自然", "山", "峰", "湖", "海", "滩", "岛", "园林", "花园",
    "漂流", "滑雪", "徒步", "骑行", "登山", "攀岩", "露营", "草原", "沙漠",
    "峡谷", "森林", "湿地", "洞穴", "溶洞", "瀑布", "溪", "河", "江",
    "动物园", "植物园", "花海", "观鸟", "日出", "日落", "观景", "户外",
    "爬山", "探险", "海滩", "海域", "海岸", "山水",
)


def classify_poi_indoor(poi_name: str, kb_tags=None):
    """Classify a POI as indoor/outdoor/semi.

    Phase 12.15: Tag-based classification first (KB-aware), then fall back
    to name regex. Returns 'indoor', 'outdoor', or 'semi'.

    Args:
        poi_name: POI name string
        kb_tags: optional list of tag strings from KB
    """
    # 1. Tag-based classification (most accurate when KB data available)
    if kb_tags:
        is_indoor = any(any(kw in t for kw in _TAG_INDOOR_KW) for t in kb_tags)
        is_outdoor = any(any(kw in t for kw in _TAG_OUTDOOR_KW) for t in kb_tags)

        # Name safety check: strong outdoor signals in the name override
        # incorrect KB tags (e.g. 漓江 tagged as "美食" but it's clearly outdoor)
        _NAME_OUTDOOR_FORCE_RE = re.compile(
            r'^(?:.*(?:江|河|湖|海|瀑|峡|谷|峰|岭|山|潭|湾|滨|'
            r'草原|沙漠|森林|湿地|冰川|雪[山峰]).*)$'
        )
        _name_is_clearly_outdoor = bool(
            _NAME_OUTDOOR_FORCE_RE.search(poi_name)
        )

        if is_indoor and not is_outdoor:
            if _name_is_clearly_outdoor:
                return "semi"  # At most semi-indoor for clearly outdoor names
            return "indoor"
        if is_outdoor and not is_indoor:
            return "outdoor"
        if is_indoor and is_outdoor:
            return "semi"

    # 2. Fall back to name regex
    if _INDOOR_RE.search(poi_name):
        return "indoor"

    # 3. Outdoor-leaning name patterns (explicit outdoor signals)
    if re.search(
        r'山|峰|公园|湖|海|滩|岛|园林|花园|瀑|峡|谷|森林|湿地|草原|沙漠|'
        r'洞|岩|潭|湾|滨|码头|索道|缆车|漂流|滑雪|徒步|登山|日出|日落|观景|户外',
        poi_name
    ):
        return "outdoor"

    return "outdoor"  # Default: assume outdoor (safe for weather_fit evaluation)


# ── KB 标签查找（Phase 12.21：守卫与评估器共用同一口径）─────────────
# 根因背景：KB 中 1034/2114 条 name_normalized ≠ name（去标点/繁简/截断），
# compute_weather_fit 曾只用 name_normalized 建键、enforce_severe_weather_indoor
# 只用 name 建键，导致守卫刚换上的室内项被评估器误判回户外（q08/q11/q13）。

def _canon_poi_name(s: str) -> str:
    """POI 名规范化：去除标点/空白/括号等，仅用于模糊匹配（不改原数据）。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", s or "")


def _build_kb_tag_lookups(
    kb_attractions: Optional[List[Dict[str, Any]]],
    city: Optional[str] = None,
) -> tuple:
    """构建 (精确表, 规范化表)：name 与 name_normalized 两个变体都建键。"""
    exact: Dict[str, List[str]] = {}
    canon: Dict[str, List[str]] = {}
    for a in kb_attractions or []:
        if city and a.get("city") != city:
            continue
        tags = a.get("tags", []) or []
        for key in (a.get("name", ""), a.get("name_normalized", "")):
            if key:
                exact.setdefault(key, tags)
                c = _canon_poi_name(key)
                if c:
                    canon.setdefault(c, tags)
    return exact, canon


def _lookup_kb_tags(
    poi_name: str,
    exact: Dict[str, List[str]],
    canon: Dict[str, List[str]],
) -> Optional[List[str]]:
    """按 精确名 → 规范化名 → 规范化子串 的顺序查 KB 标签，未命中返回 None。"""
    tags = exact.get(poi_name)
    if tags is not None:
        return tags
    c = _canon_poi_name(poi_name)
    if not c:
        return None
    tags = canon.get(c)
    if tags is not None:
        return tags
    for kc, t in canon.items():
        if len(kc) >= 3 and (kc in c or c in kc):
            return t
    return None


# 夏季月份（6-8月）——全国大部分地区进入雨季
_SUMMER_MONTHS = {6, 7, 8}


def compute_weather_fit(
    data: Dict[str, Any],
    weather: Optional[Dict[str, Any]],
    month: Optional[int] = None,
    kb_attractions: Optional[List[Dict[str, Any]]] = None,
) -> tuple:
    """评估行程与天气的匹配度（validation_report.weather_fit）。

    Phase 12.15: Now accepts kb_attractions for tag-based indoor classification.
    KB tags are more accurate than name regex alone (e.g. restaurants tagged
    "美食" are indoor even if name doesn't match _INDOOR_RE).

    Returns (fit, notes): fit ∈ good/fair/poor/unknown。

    Phase 12.8: Proportional scoring — in summer months, most days have
    some rain. The old all-or-nothing approach flagged every itinerary as
    "poor". Now uses ratio of rainy days with good indoor/outdoor balance:

      - 0 rainy days or all rainy days balanced → good
      - ≤ 33% of rainy days mismatched → good (mostly adapted)
      - 34-66% mismatched → fair (needs improvement)
      - > 66% mismatched → poor (significant issues)

    Phase 12.11: Summer adaptation — during Jun-Aug, the mismatch threshold
    is relaxed (outdoor > indoor + 1 instead of outdoor > indoor), and days
    with travel_score ≥ 0.5 are always considered adapted (summer rain is
    often brief afternoon showers, not all-day storms).
    """
    if not weather or not weather.get("daily"):
        return "unknown", []

    if month is None:
        month = date.today().month

    # Phase 12.21: 共用查找口径 — name 与 name_normalized 双键 + 规范化模糊匹配
    _kb_exact, _kb_canon = _build_kb_tag_lookups(kb_attractions)

    def _is_indoor(item_poi: str) -> bool:
        """Check if a POI item is indoor, using KB tags if available."""
        kb_tags = (
            _lookup_kb_tags(item_poi, _kb_exact, _kb_canon) if _kb_exact else None
        )
        classification = classify_poi_indoor(item_poi, kb_tags)
        return classification in ("indoor", "semi")

    is_summer = month in _SUMMER_MONTHS

    notes: List[str] = []
    rainy_days = 0
    mismatch_days = 0

    for i, day in enumerate(data.get("days", [])):
        if not isinstance(day, dict):
            continue
        fc = weather["daily"][i] if i < len(weather["daily"]) else None
        if not fc:
            continue
        desc = fc.get("weather_desc", "") or ""
        precip = fc.get("precipitation") or 0
        rainy = any(w in desc for w in _RAIN_WORDS) or precip > 0.5
        if not rainy:
            continue

        rainy_days += 1
        items = [it for it in day.get("items", []) if isinstance(it, dict)]
        indoor = sum(1 for it in items if _is_indoor(it.get("poi", "")))
        outdoor = len(items) - indoor

        # Phase 12.11: Summer adaptation
        # 1. Severe weather (雷暴/冰雹) with outdoor activities → always mismatch
        is_severe = any(w in desc for w in ("雷", "雹")) or fc.get("weather_code", 0) in (95, 96, 99)
        if is_severe and outdoor > 0:
            mismatch_days += 1
            notes.append(
                f"第{day.get('day')}天{desc}，有{outdoor}个户外项目，"
                f"强烈建议全部改为室内活动"
            )
            continue

        # 2. Phase 12.14: Good travel_score (≥0.35) means mild rain → don't penalize
        travel_score = fc.get("travel_score", 1.0)
        if is_summer and travel_score >= 0.35:
            notes.append(
                f"第{day.get('day')}天{desc}（评分{travel_score:.0%}），"
                f"夏季阵雨影响有限，行程可正常进行"
            )
            continue  # Not counted as mismatch

        # 2. Summer: allow outdoor ≤ indoor + 1 (one extra outdoor is OK)
        if is_summer:
            is_mismatch = outdoor > indoor + 1
        else:
            is_mismatch = outdoor > indoor

        if is_mismatch:
            mismatch_days += 1
            notes.append(
                f"第{day.get('day')}天{desc}，仍有 {outdoor} 个户外项目，"
                f"建议准备雨具和室内备选"
            )
        else:
            notes.append(
                f"第{day.get('day')}天{desc}，以 {indoor} 个室内项目为主，安排合理"
            )

    if rainy_days == 0:
        fit = "good"
    else:
        ratio = mismatch_days / rainy_days
        if ratio <= 0.33:
            fit = "good"
        elif ratio <= 0.75:  # Phase 12.14: raised from 0.66
            fit = "fair"
        else:
            fit = "poor"

    return fit, notes


# ── 每日食宿挂载（Phase 12.27："吃住都没有推荐"）─────────────

def attach_daily_dining_and_stay(
    data: Dict[str, Any],
    kb_attractions: Optional[List[Dict[str, Any]]],
    city: Optional[str] = None,
) -> int:
    """按天挂载 KB 真实餐厅（午/晚餐）与住宿，替代 LLM 的空泛"每日一味"。

    - 餐厅：行程城市的美食 POI，排除行程 items 已出现的，午餐取热度最高、
      晚餐取首个与午餐品类不同的（tags 第二标签即细分品类），跨天不重复
    - 住宿：tags 含「住宿」的 POI，按热度每天 1 个不重复（KB 无住宿数据则留空）
    - KB 数据不足时保留 LLM 原 eat，不强行覆盖

    Returns: 成功挂载餐饮的天数。
    """
    if not isinstance(data, dict):
        return 0
    city = city or (data.get("trip") or {}).get("city", "")

    def _subtype(a: Dict[str, Any]) -> str:
        for t in a.get("tags", []) or []:
            if t not in ("美食", "中餐"):
                return t
        return "中餐"

    used_pois = {
        it.get("poi", "")
        for d in data.get("days", [])
        for it in d.get("items", [])
        if isinstance(it, dict)
    }
    foods = [
        a for a in kb_attractions or []
        if a.get("city") == city
        and "美食" in (a.get("tags") or [])
        and a.get("name") not in used_pois
    ]
    foods.sort(key=lambda a: -(a.get("popularity_score", 5) or 5))
    stays = [
        a for a in kb_attractions or []
        if a.get("city") == city and "住宿" in (a.get("tags") or [])
    ]
    stays.sort(key=lambda a: -(a.get("popularity_score", 5) or 5))

    used_names: set = set()
    mounted = 0
    for idx, day in enumerate(data.get("days", [])):
        if not isinstance(day, dict):
            continue
        lunch = next((a for a in foods if a["name"] not in used_names), None)
        dinner = next(
            (a for a in foods
             if a["name"] not in used_names
             and (lunch is None or _subtype(a) != _subtype(lunch))),
            None,
        )
        if lunch and dinner:
            day["eat"] = f"午餐「{lunch['name']}」· 晚餐「{dinner['name']}」"
            used_names.update((lunch["name"], dinner["name"]))
            mounted += 1
        elif lunch:
            day["eat"] = f"推荐「{lunch['name']}」"
            used_names.add(lunch["name"])
            mounted += 1
        if idx < len(stays):
            day["stay"] = stays[idx]["name"]
    if mounted or stays:
        logger.info(f"Dining/stay attached: {mounted} days dining, {len(stays)} stays ({city})")
    return mounted


# ── 节奏分档密度控制（Phase 12.27）──────────────────────
# 用户反馈"行程很密集"——prompt 从"每天 3-6"改为按节奏分档，这里做确定性兜底。

_PACE_DAY_ITEM_CAP = {
    "休闲": 4, "慢": 4, "放松": 4, "度假": 4,
    "紧凑": 6, "特种兵": 6, "赶": 6,
}
_DEFAULT_DAY_ITEM_CAP = 5  # 适中/不限


def enforce_pace_density(data: Dict[str, Any], pace: str) -> int:
    """按节奏档位截断每天条目数（保序保留前 N 项，LLM 按重要性排序）。

    Returns: 被截掉的条目总数。
    """
    cap = _DEFAULT_DAY_ITEM_CAP
    for kw, v in _PACE_DAY_ITEM_CAP.items():
        if kw in (pace or ""):
            cap = v
            break
    trimmed = 0
    for day in data.get("days", []):
        if not isinstance(day, dict):
            continue
        items = day.get("items", [])
        if len(items) > cap:
            trimmed += len(items) - cap
            day["items"] = items[:cap]
    if trimmed:
        logger.info(f"Pace density: pace={pace or '适中'} cap={cap}, trimmed {trimmed} items")
    return trimmed


def is_severe_weather(fc: Dict[str, Any]) -> bool:
    """True if a daily forecast is severe (雷暴/冰雹 — outdoor unsafe)."""
    desc = fc.get("weather_desc", "") or ""
    return any(w in desc for w in ("雷", "雹")) or fc.get("weather_code", 0) in (95, 96, 99)


def enforce_severe_weather_indoor(
    data: Dict[str, Any],
    weather: Optional[Dict[str, Any]],
    kb_attractions: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Phase 12.17 v5: deterministic severe-weather guard.

    On 雷暴/冰雹 days, replace outdoor items with unused indoor/semi KB
    candidates from the trip city. Prompt-level pressure alone lets the LLM
    keep famous outdoor landmarks (大理洱海、长沙岳麓山在雷暴日照旧出现)；
    this makes the safety constraint structural instead of advisory.

    Returns the number of replaced items.
    """
    if not weather or not weather.get("daily") or not kb_attractions:
        return 0

    city = (data.get("trip") or {}).get("city", "")
    used = {
        it.get("poi", "")
        for d in data.get("days", [])
        for it in d.get("items", [])
        if isinstance(it, dict)
    }

    # Phase 12.21: 与 compute_weather_fit 共用同一 KB 查找口径
    _kb_exact, _kb_canon = _build_kb_tag_lookups(kb_attractions, city=city)
    kb_names: List[str] = []
    popularity: Dict[str, float] = {}
    for a in kb_attractions:
        if a.get("city") != city:
            continue
        name = a.get("name", "")
        if name:
            kb_names.append(name)
            popularity[name] = a.get("popularity_score", 5) or 5

    candidates = [
        n for n in kb_names
        if n not in used
        and classify_poi_indoor(n, _lookup_kb_tags(n, _kb_exact, _kb_canon)) in ("indoor", "semi")
    ]
    candidates.sort(key=lambda n: -popularity.get(n, 5))

    replaced = 0
    for i, day in enumerate(data.get("days", [])):
        if not isinstance(day, dict) or i >= len(weather["daily"]):
            continue
        fc = weather["daily"][i]
        if not is_severe_weather(fc):
            continue
        desc = fc.get("weather_desc", "") or "恶劣天气"
        for it in day.get("items", []):
            if not isinstance(it, dict):
                continue
            poi = it.get("poi", "")
            if classify_poi_indoor(poi, _lookup_kb_tags(poi, _kb_exact, _kb_canon)) != "outdoor":
                continue
            if not candidates:
                break
            new_poi = candidates.pop(0)
            it["poi"] = new_poi
            it["note"] = f"原户外项目因{desc}安全起见替换为室内（系统调整）"
            replaced += 1
        # 替换过的当天 items 计入 used，避免后续天重复
        used.update(it.get("poi", "") for it in day.get("items", []) if isinstance(it, dict))

    if replaced:
        logger.info(f"Severe-weather guard: replaced {replaced} outdoor items ({city})")
    return replaced

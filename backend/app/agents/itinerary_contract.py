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

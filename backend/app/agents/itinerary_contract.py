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
    numbers = [d.get("day") for d in days]
    if numbers != list(range(1, len(days) + 1)):
        errors.append(f"day 编号不连续: {numbers}")
    days_count = (data.get("trip") or {}).get("daysCount")
    if days_count is not None and days_count != len(days):
        errors.append(f"daysCount({days_count}) 与 days 长度({len(days)}) 不一致")
    return errors


def _fmt_date(d: date) -> str:
    return f"{d.month}月{d.day}日"


def inject_computed_fields(data: Dict[str, Any], start: Optional[date] = None) -> Dict[str, Any]:
    """Inject all backend-owned fields in place; returns the same dict."""
    start = start or date.today()
    days = data.get("days", [])

    trip = data.setdefault("trip", {})
    trip["dateStart"] = _fmt_date(start)
    trip["dateEnd"] = _fmt_date(start + timedelta(days=max(len(days) - 1, 0)))
    trip["daysCount"] = len(days)

    # budget percent — largest-remainder rounding so they sum to exactly 100
    budget = data.get("budget", [])
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
        item["done"] = False

    data["schemaVersion"] = SCHEMA_VERSION
    return data


def budget_sum_mismatch(data: Dict[str, Any]) -> bool:
    """True when sum(budget.amount) diverges from the stated 人均预算 stat
    beyond BUDGET_SUM_TOLERANCE (skipped when the stat is unparseable)."""
    total = sum(b.get("amount", 0) for b in data.get("budget", []))
    for stat in (data.get("trip") or {}).get("stats", []):
        if "预算" in stat.get("label", ""):
            m = re.search(r"([\d,]+)", stat.get("value", ""))
            if m:
                stated = int(m.group(1).replace(",", ""))
                if stated > 0:
                    return abs(total - stated) / stated > BUDGET_SUM_TOLERANCE
    return False

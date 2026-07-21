"""
TravelMind Agent — 行程契约回归测试

固定输入真实生成一份行程（消耗少量 DeepSeek token），然后全量断言：
- schema 契约校验（docs/itinerary.schema.json）
- day 编号连续 / daysCount 一致
- stats 地点数 == 后端实统计（餐饮/休息/酒店停靠不计入）
- budget percent 和 = 100；amount 加总 ≈ stats 人均预算（≤15%）
- 月份与行程日期一致（无异常 "X月"）

用法:
    cd backend
    python scripts/contract_regression.py [user_input]
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.itinerary_contract import (  # noqa: E402
    budget_sum_mismatch,
    count_places,
    month_inconsistency_errors,
    validate_day_continuity,
    validate_itinerary,
)

DEFAULT_INPUT = "重庆3日游，喜欢夜景和美食，带父母"
RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    user_input = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    print(f"输入: {user_input}")

    r = httpx.post(
        "http://localhost:8000/api/v1/agent/plan",
        json={"user_input": user_input},
        timeout=300,
        trust_env=False,
    )
    if r.status_code != 200:
        print(f"❌ /agent/plan HTTP {r.status_code}")
        return 1
    resp = r.json()
    it = resp.get("itinerary") or {}

    if not check("生成成功（itinerary 非空）", bool(it), f"error={resp.get('error')}"):
        return 1

    trip = it.get("trip", {})
    print(f"标题: {trip.get('title')} | {trip.get('dateStart')} → {trip.get('dateEnd')}")

    errs = validate_itinerary(it) + validate_day_continuity(it)
    check("schema 全量校验", not errs, "; ".join(errs[:3]))

    n = count_places(it)
    stat = next((s for s in trip.get("stats", []) if "地点" in s.get("label", "") or "景点" in s.get("label", "")), None)
    stat_n = None
    if stat:
        m = re.search(r"(\d+)", stat.get("value", ""))
        stat_n = int(m.group(1)) if m else None
    check("stats 地点数 == 实统计", stat_n == n, f"stats={stat_n} vs 实际={n}")

    percents = [b.get("percent", 0) for b in it.get("budget", [])]
    check("budget percent 和 = 100", sum(percents) == 100, f"sum={sum(percents)}")
    check("budget 加总 ≈ 人均预算", not budget_sum_mismatch(it))

    month = date.today().month
    merrs = month_inconsistency_errors(it, month)
    check(f"月份一致（{month}月）", not merrs, "; ".join(merrs[:2]))

    days = it.get("days", [])
    check("天数与 daysCount 一致", trip.get("daysCount") == len(days))

    vr = it.get("validation_report")
    check(
        "validation_report 存在且结构完整",
        bool(vr)
        and isinstance(vr.get("poi"), list)
        and isinstance(vr.get("poi_verified"), str)
        and isinstance(vr.get("routes"), list)
        and vr.get("weather_fit") in ("good", "fair", "poor", "unknown"),
        f"poi_verified={vr.get('poi_verified') if vr else None}",
    )

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n===== 契约回归: {passed}/{len(RESULTS)} 通过 =====")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

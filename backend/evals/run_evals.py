"""
TravelMind Agent — 行程质量评测（约束通过率看板）

对 queries.json 中的每条 query 真实调用完整生成管线（走 LLM），
再用**确定性**打分器逐项判定（禁止 LLM 当评委）：

- Micro 通过率：所有 (query × 约束) 单元格的通过比例
- Macro/Final 通过率：单条 query 内全部约束通过才算该 query 通过

约束清单（全部复用 itinerary_contract 的确定性函数）：
  schema_valid / days_correct / stats_place_count / budget_consistent
  month_consistent / poi_verified / route_ok / weather_fit / weather_coverage

用法:
    cd backend
    python -X utf8 -m evals.run_evals [--limit N] [--out results/YYYY-MM-DD.json]

需后端服务在 :8000 运行（生成走真实管线）。
"""

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.itinerary_contract import (  # noqa: E402
    budget_sum_mismatch,
    count_places,
    month_inconsistency_errors,
    trip_has_rain,
    validate_day_continuity,
    validate_itinerary,
    weather_coverage_errors,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

API_BASE = "http://localhost:8000/api/v1"
EVALS_DIR = Path(__file__).resolve().parent
POI_VERIFIED_BAR = 0.5  # poi_verified 约束阈值：已核实比例 ≥ 50%


# ── 确定性打分器 ─────────────────────────────────────────

def score_query(itinerary: Dict[str, Any], expect: Dict[str, Any], weather: Any = None) -> Dict[str, Dict[str, Any]]:
    """对一份生成结果逐项打分。返回 {constraint: {"pass": bool, "detail": str}}。"""
    out: Dict[str, Dict[str, Any]] = {}
    if not itinerary:
        return {k: {"pass": False, "detail": "itinerary empty"} for k in CONSTRAINTS}

    trip = itinerary.get("trip", {})

    errs = validate_itinerary(itinerary) + validate_day_continuity(itinerary)
    out["schema_valid"] = {"pass": not errs, "detail": errs[0][:80] if errs else ""}

    out["days_correct"] = {
        "pass": trip.get("daysCount") == expect.get("days"),
        "detail": f"daysCount={trip.get('daysCount')} vs 期望 {expect.get('days')}",
    }

    n = count_places(itinerary)
    stat_n = None
    for s in trip.get("stats", []):
        if "地点" in s.get("label", "") or "景点" in s.get("label", ""):
            import re
            m = re.search(r"(\d+)", s.get("value", ""))
            stat_n = int(m.group(1)) if m else None
            break
    out["stats_place_count"] = {"pass": stat_n == n, "detail": f"stats={stat_n} vs 实际={n}"}

    percent_sum = sum(b.get("percent", 0) for b in itinerary.get("budget", []))
    out["budget_consistent"] = {
        "pass": percent_sum == 100 and not budget_sum_mismatch(itinerary),
        "detail": f"percent 和={percent_sum}",
    }

    month = date.today().month
    merrs = month_inconsistency_errors(itinerary, month)
    out["month_consistent"] = {"pass": not merrs, "detail": merrs[0][:60] if merrs else ""}

    vr = itinerary.get("validation_report") or {}
    poi_list = vr.get("poi", [])
    total = len(poi_list)
    verified = sum(1 for p in poi_list if p.get("status") in ("verified", "replaced"))
    ratio = verified / total if total else 0
    out["poi_verified"] = {
        "pass": total > 0 and ratio >= POI_VERIFIED_BAR,
        "detail": f"{verified}/{total} = {ratio:.0%}（阈值 {POI_VERIFIED_BAR:.0%}）",
    }

    out["route_ok"] = {
        "pass": vr.get("route_backtrack") is False,
        "detail": f"route_backtrack={vr.get('route_backtrack')}",
    }

    out["weather_fit"] = {
        "pass": vr.get("weather_fit") in ("good", "unknown"),
        "detail": f"weather_fit={vr.get('weather_fit')}",
    }

    if weather and trip_has_rain(weather, len(itinerary.get("days", []))):
        werrs = weather_coverage_errors(itinerary)
        out["weather_coverage"] = {"pass": not werrs, "detail": werrs[0][:60] if werrs else ""}
    else:
        out["weather_coverage"] = {"pass": True, "detail": "无降雨预报，不适用"}

    return out


CONSTRAINTS = [
    "schema_valid", "days_correct", "stats_place_count", "budget_consistent",
    "month_consistent", "poi_verified", "route_ok", "weather_fit", "weather_coverage",
]


# ── 主流程 ───────────────────────────────────────────────

def run(queries: List[Dict[str, Any]], limit: int = 0) -> Dict[str, Any]:
    if limit:
        queries = queries[:limit]

    per_query: List[Dict[str, Any]] = []
    for q in queries:
        logger.info(f"[{q['id']}] {q['input']}")
        entry: Dict[str, Any] = {"id": q["id"], "input": q["input"], "expect": q["expect"]}
        try:
            t0 = time.time()
            r = httpx.post(
                f"{API_BASE}/agent/plan",
                json={"user_input": q["input"]},
                timeout=300,
                trust_env=False,
            )
            entry["elapsed_s"] = round(time.time() - t0, 1)
            entry["http"] = r.status_code
            resp = r.json()
            itinerary = resp.get("itinerary") or {}
            entry["title"] = (itinerary.get("trip") or {}).get("title", "")
            entry["api_error"] = resp.get("error")
            entry["scores"] = score_query(itinerary, q["expect"], resp.get("weather"))
        except Exception as e:
            entry["scores"] = {k: {"pass": False, "detail": f"exception: {e}"} for k in CONSTRAINTS}
        entry["query_pass"] = all(s["pass"] for s in entry["scores"].values())
        per_query.append(entry)
        logger.info(
            f"  → {'PASS' if entry['query_pass'] else 'FAIL'} "
            f"({sum(s['pass'] for s in entry['scores'].values())}/{len(CONSTRAINTS)} 约束)"
        )

    # 汇总三级指标
    cells = sum(len(e["scores"]) for e in per_query)
    passed_cells = sum(1 for e in per_query for s in e["scores"].values() if s["pass"])
    query_pass = sum(1 for e in per_query if e["query_pass"])
    total = len(per_query)

    per_constraint = {}
    for c in CONSTRAINTS:
        ok = sum(1 for e in per_query if e["scores"].get(c, {}).get("pass"))
        per_constraint[c] = {"pass": ok, "total": total, "rate": round(ok / total, 3) if total else 0}

    return {
        "date": date.today().isoformat(),
        "total_queries": total,
        "micro": round(passed_cells / cells, 4) if cells else 0,
        "macro": round(query_pass / total, 4) if total else 0,
        "final_pass_rate": round(query_pass / total, 4) if total else 0,
        "per_constraint": per_constraint,
        "per_query": per_query,
    }


def print_summary(result: Dict[str, Any]) -> None:
    print("\n===== 三级指标 =====")
    print(f"Micro 通过率（约束单元格）: {result['micro']:.1%}")
    print(f"Macro 通过率（query 全约束）: {result['macro']:.1%}")
    print(f"Final Pass Rate           : {result['final_pass_rate']:.1%}")
    print("\n逐项约束通过率:")
    for c, s in result["per_constraint"].items():
        print(f"  {c:20s} {s['pass']}/{s['total']} = {s['rate']:.0%}")
    print("\n失败 query 明细:")
    for e in result["per_query"]:
        if not e["query_pass"]:
            fails = [k for k, s in e["scores"].items() if not s["pass"]]
            print(f"  [{e['id']}] {e['input'][:30]} — 失败约束: {', '.join(fails)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（调试用）")
    parser.add_argument("--out", type=str, default="", help="结果输出路径")
    args = parser.parse_args()

    queries_file = EVALS_DIR / "queries.json"
    with open(queries_file, "r", encoding="utf-8") as f:
        queries = json.load(f)["queries"]

    # 前置健康检查
    try:
        httpx.get(f"{API_BASE}/health", timeout=5, trust_env=False)
    except Exception:
        print("后端不可达 (:8000)，请先启动后端")
        return 1

    result = run(queries, args.limit)
    print_summary(result)

    out_path = args.out or str(EVALS_DIR / "results" / f"{date.today().isoformat()}.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

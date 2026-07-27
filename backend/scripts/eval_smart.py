"""
TravelMind Agent — 增量智能评测（Smart Eval v1.0）

Phase 12.28a：根据 git diff 推断受影响的 queries/约束，只重跑必要的
子集而非全量 63 条。自动与最新基线对比，输出 markdown 报告。零 LLM
评判（对比逻辑确定性）。

用法：
  cd backend
  python -X utf8 scripts/eval_smart.py                           # 自动检测改动
  python -X utf8 scripts/eval_smart.py --changed-files app/rag/  # 手动指定文件
  python -X utf8 scripts/eval_smart.py --full                     # 全量评测（退路）
  python -X utf8 scripts/eval_smart.py --report-only              # 仅对比报告（不跑评测）
"""

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.run_evals import _infer_affected as infer_affected, _filter_queries as filter_queries  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BACKEND_DIR = Path(__file__).resolve().parent.parent
EVALS_DIR = BACKEND_DIR / "evals"
SCRIPTS_DIR = BACKEND_DIR / "scripts"
API_BASE = "http://localhost:8000/api/v1"


def get_changed_files() -> List[str]:
    """Get changed files from git diff --name-only (staged + unstaged vs HEAD)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=BACKEND_DIR,
        )
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--staged", "HEAD"],
            capture_output=True, text=True, cwd=BACKEND_DIR,
        )
        # Also check untracked files in key dirs
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=BACKEND_DIR,
        )
        files = set()
        for r in (result, staged, untracked):
            if r.returncode == 0 and r.stdout.strip():
                files.update(r.stdout.strip().split("\n"))
        return sorted(files)
    except Exception as e:
        logger.warning(f"git diff 失败: {e}，回退到全量评测")
        return ["*"]  # trigger full eval


def load_latest_baseline() -> Optional[Dict[str, Any]]:
    """Load the most recent eval result as baseline."""
    results_dir = EVALS_DIR / "results"
    if not results_dir.exists():
        return None

    json_files = sorted(results_dir.glob("*.json"), reverse=True)
    for f in json_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if "version" in data and "micro" in data:
                    return data
        except Exception:
            continue
    return None


def compare_results(new_result: Dict, baseline: Optional[Dict]) -> Dict[str, Any]:
    """Compare new results against baseline. Zero-LLM deterministic."""
    comparison: Dict[str, Any] = {
        "new": {
            "micro": new_result.get("micro", 0),
            "macro": new_result.get("macro", 0),
            "total_queries": new_result.get("total_queries", 0),
        },
    }

    if baseline:
        comparison["baseline"] = {
            "micro": baseline.get("micro", 0),
            "macro": baseline.get("macro", 0),
            "total_queries": baseline.get("total_queries", 0),
            "date": baseline.get("date", "unknown"),
        }
        b = comparison["baseline"]
        n = comparison["new"]
        comparison["delta"] = {
            "micro": round(n["micro"] - b["micro"], 4),
            "macro": round(n["macro"] - b["macro"], 4),
        }

        # Per-constraint delta
        constraint_deltas = {}
        old_pc = baseline.get("per_constraint", {})
        new_pc = new_result.get("per_constraint", {})
        for c in sorted(set(list(old_pc.keys()) + list(new_pc.keys()))):
            old_rate = old_pc.get(c, {}).get("rate", 0)
            new_rate = new_pc.get(c, {}).get("rate", 0)
            if old_rate != new_rate:
                constraint_deltas[c] = {
                    "old": old_rate, "new": new_rate,
                    "delta": round(new_rate - old_rate, 3),
                }
        comparison["constraint_deltas"] = constraint_deltas

        # Degraded queries (passed before, fail now)
        degraded = []
        old_queries = {e["id"]: e.get("query_pass", False) for e in baseline.get("per_query", [])}
        for e in new_result.get("per_query", []):
            qid = e["id"]
            if qid in old_queries and old_queries[qid] and not e.get("query_pass", False):
                fails = [k for k, s in e.get("scores", {}).items()
                        if not s.get("pass") and not s.get("na")]
                degraded.append({"id": qid, "fails": fails, "input": e.get("input", "")[:80]})
        comparison["degraded_from_baseline"] = degraded

        # Improved queries (failed before, pass now)
        improved = []
        for e in new_result.get("per_query", []):
            qid = e["id"]
            if qid in old_queries and not old_queries[qid] and e.get("query_pass", False):
                improved.append({"id": qid, "input": e.get("input", "")[:80]})
        comparison["improved_from_baseline"] = improved

        # Verdict
        d = comparison["delta"]
        comparison["verdict"] = "ok" if d["macro"] >= 0 and d["micro"] >= -0.01 else "degraded"

    return comparison


def generate_report(comparison: Dict, new_result: Dict,
                    affected_constraints: Set[str], affected_categories: Set[str],
                    changed_files: List[str]) -> str:
    """Generate a markdown report."""
    lines = []
    lines.append("# Smart Eval Report")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Trigger:** {len(changed_files)} changed files")
    lines.append("")

    if changed_files:
        lines.append("## Changed Files")
        for f in changed_files[:15]:
            lines.append(f"- `{f}`")
        if len(changed_files) > 15:
            lines.append(f"- ... and {len(changed_files) - 15} more")
        lines.append("")

    if affected_constraints != {"*"} or affected_categories != {"*"}:
        lines.append("## Scope (incremental)")
        cats = sorted(affected_categories) if affected_categories != {"*"} else ["ALL"]
        lines.append(f"- Categories: {', '.join(cats)}")
        if affected_constraints != {"*"}:
            lines.append(f"- Constraints monitored: {len(affected_constraints)}")
        lines.append(f"- Queries run: {new_result.get('total_queries', '?')}")
    else:
        lines.append("## Scope (full)")
        lines.append(f"- All categories, all {new_result.get('total_queries', '?')} queries")
    lines.append("")

    lines.append("## Results")
    n = comparison.get("new", {})
    lines.append(f"- Micro: **{n.get('micro', 0):.1%}**")
    lines.append(f"- Macro: **{n.get('macro', 0):.1%}**")

    if "baseline" in comparison:
        b = comparison["baseline"]
        d = comparison.get("delta", {})
        lines.append("")
        lines.append("### vs Baseline")
        lines.append(f"- Baseline: {b.get('date', '?')} (Micro {b.get('micro', 0):.1%}, Macro {b.get('macro', 0):.1%})")
        lines.append(f"- Δ Micro: {d.get('micro', 0):+.1%}")
        lines.append(f"- Δ Macro: {d.get('macro', 0):+.1%}")

        cds = comparison.get("constraint_deltas", {})
        if cds:
            lines.append("")
            lines.append("### Constraint Changes")
            lines.append("| Constraint | Old | New | Δ |")
            lines.append("|---|---|---|---|")
            for c, v in sorted(cds.items()):
                direction = "🔺" if v["delta"] > 0 else ("🔻" if v["delta"] < 0 else "➖")
                lines.append(f"| {c} | {v['old']:.0%} | {v['new']:.0%} | {direction} {v['delta']:+.0%} |")

        degraded = comparison.get("degraded_from_baseline", [])
        if degraded:
            lines.append("")
            lines.append(f"### ⚠️ Degraded ({len(degraded)} queries)")
            for dq in degraded:
                lines.append(f"- **{dq['id']}**: {dq['input']} — fails: {', '.join(dq['fails'])}")

        improved = comparison.get("improved_from_baseline", [])
        if improved:
            lines.append("")
            lines.append(f"### ✅ Improved ({len(improved)} queries)")
            for iq in improved:
                lines.append(f"- **{iq['id']}**: {iq['input']}")

        verdict = comparison.get("verdict", "unknown")
        if verdict == "ok":
            lines.append("")
            lines.append("## ✅ 零劣化 — 可安全提交")
        else:
            lines.append("")
            lines.append("## ⚠️ 检测到劣化 — 需检查后再提交")

    lines.append("")
    return "\n".join(lines)


async def run_smart_eval(
    queries: List[Dict],
    out_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the eval pipeline (imports from run_evals)."""
    from evals.run_evals import (
        run_chat_query, run_food_query, run_image_tag_query,
        run_multi_city_query, run_plan_query,
        CONSTRAINTS,
    )

    per_query: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(trust_env=False) as client:
        for q in queries:
            category = q.get("expect", {}).get("category", q.get("category", "standard"))
            logger.info(f"[{q['id']}] [{category}] {q['input'][:60]}...")

            if category == "chat":
                entry = await run_chat_query(client, q)
            elif category == "food":
                entry = await run_food_query(client, q)
            elif category == "multi-city":
                entry = await run_multi_city_query(client, q)
            elif category == "image-tag":
                entry = await run_image_tag_query(client, q)
            else:
                entry = await run_plan_query(client, q)

            entry["category"] = category
            entry["query_pass"] = all(s["pass"] for s in entry["scores"].values())
            per_query.append(entry)

            active = [k for k, s in entry["scores"].items() if not s.get("na")]
            passed_active = sum(1 for k, s in entry["scores"].items() if s["pass"] and not s.get("na"))
            logger.info(f"  → {'PASS' if entry['query_pass'] else 'FAIL'} ({passed_active}/{len(active)})")

    cells = sum(len([s for s in e["scores"].values() if not s.get("na")]) for e in per_query)
    passed_cells = sum(1 for e in per_query for s in e["scores"].values() if s["pass"] and not s.get("na"))
    query_pass = sum(1 for e in per_query if e["query_pass"])
    total = len(per_query)

    per_constraint = {}
    for c in CONSTRAINTS:
        applicable = [e for e in per_query if not e["scores"].get(c, {}).get("na")]
        if applicable:
            ok = sum(1 for e in applicable if e["scores"].get(c, {}).get("pass"))
            per_constraint[c] = {"pass": ok, "total": len(applicable), "rate": round(ok / len(applicable), 3)}
        else:
            per_constraint[c] = {"pass": 0, "total": 0, "rate": 0}

    cat_stats: Dict[str, Dict[str, Any]] = {}
    for e in per_query:
        cat = e.get("category", "unknown")
        if cat not in cat_stats:
            cat_stats[cat] = {"total": 0, "pass": 0}
        cat_stats[cat]["total"] += 1
        if e["query_pass"]:
            cat_stats[cat]["pass"] += 1

    result = {
        "version": "3.0.0-smart",
        "date": date.today().isoformat(),
        "total_queries": total,
        "micro": round(passed_cells / cells, 4) if cells else 0,
        "macro": round(query_pass / total, 4) if total else 0,
        "final_pass_rate": round(query_pass / total, 4) if total else 0,
        "per_constraint": per_constraint,
        "per_category": cat_stats,
        "per_query": per_query,
    }

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已写入 {out_path}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="TravelMind Smart Eval — 增量智能评测")
    parser.add_argument("--changed-files", type=str, default="",
                        help="手动指定改动的文件（逗号分隔，相对 backend 路径）")
    parser.add_argument("--full", action="store_true", help="强制全量评测")
    parser.add_argument("--report-only", action="store_true", help="仅对比报告（不跑评测）")
    parser.add_argument("--out", type=str, default="", help="结果输出路径")
    args = parser.parse_args()

    # 加载 queries
    queries_file = EVALS_DIR / "queries.json"
    with open(queries_file, "r", encoding="utf-8") as f:
        all_queries = json.load(f)["queries"]

    # 推断 affected
    if args.changed_files:
        changed_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]
    elif args.full:
        changed_files = ["*"]
    else:
        changed_files = get_changed_files()

    if not changed_files:
        logger.info("无文件变更，跳过评测")
        return 0

    affected_constraints, affected_categories = infer_affected(changed_files)

    is_full = affected_constraints == {"*"} or affected_categories == {"*"}
    scope_label = "全量" if is_full else "增量"

    if is_full:
        target_queries = all_queries
    else:
        target_queries = filter_queries(all_queries, affected_categories)

    logger.info(f"变更文件: {len(changed_files)} 个")
    logger.info(f"受影响分类: {sorted(affected_categories) if affected_categories != {'*'} else ['ALL']}")
    logger.info(f"评测范围: {scope_label} ({len(target_queries)} queries)")

    if args.report_only:
        # Load latest result and compare
        latest = load_latest_baseline()
        if not latest:
            logger.error("无历史评测结果可对比")
            return 1
        # Load the most recent non-smart result
        results_dir = EVALS_DIR / "results"
        json_files = sorted(results_dir.glob("2026-*.json"), reverse=True)
        if len(json_files) >= 2:
            with open(json_files[1], "r", encoding="utf-8") as fp:
                baseline = json.load(fp)
        else:
            baseline = latest
        comparison = compare_results(latest, baseline)
        report = generate_report(comparison, latest, affected_constraints, affected_categories, changed_files)
        print(report)
        return 0

    # Health check
    try:
        httpx.get(f"{API_BASE}/health", timeout=5, trust_env=False)
    except Exception:
        print("后端不可达 (:8000)，请先启动后端")
        return 1

    # Run
    import asyncio
    out_path = args.out or str(EVALS_DIR / "results" / f"{date.today().isoformat()}-smart.json")
    new_result = asyncio.run(run_smart_eval(target_queries, out_path))

    # Compare with baseline
    baseline = load_latest_baseline()
    if baseline and baseline.get("date") != new_result.get("date"):
        comparison = compare_results(new_result, baseline)
    else:
        comparison = {"new": {"micro": new_result["micro"], "macro": new_result["macro"], "total_queries": new_result["total_queries"]}}

    report = generate_report(comparison, new_result, affected_constraints, affected_categories, changed_files)
    print("\n" + report)

    # Save report alongside results
    report_path = out_path.replace(".json", ".md") if out_path else str(EVALS_DIR / "results" / f"{date.today().isoformat()}-smart-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"报告已写入 {report_path}")

    # Exit code based on degradation
    if comparison.get("verdict") == "degraded":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

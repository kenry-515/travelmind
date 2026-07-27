"""
TravelMind Agent — 评测结果对比器

对比两份 eval 结果 JSON（基线 vs 新跑），输出：
  - 三级指标 delta（Micro / Macro / Final）
  - 逐项约束通过率 delta（只列变化项）
  - 同口径逐 query 差异（PASS↔fail 翻转清单）
  - 按分类通过率表

🔴 零 LLM 成本，纯 JSON 对比。

用法：
  cd backend
  python scripts/eval_compare.py <baseline.json> <new.json>
  python scripts/eval_compare.py evals/results/2026-07-25-phase12_19-v1.json evals/results/2026-07-26-phase12_20-v1.json
"""

import json
import sys
from pathlib import Path


def _load(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    old = _load(sys.argv[1])
    new = _load(sys.argv[2])

    print(f"基线: {Path(sys.argv[1]).name}")
    print(f"新跑: {Path(sys.argv[2]).name}")
    print()

    # ── 三级指标 ──
    print("【三级指标】")
    for key, label in (("micro", "Micro"), ("macro", "Macro"), ("final_pass_rate", "Final")):
        ov, nv = old.get(key), new.get(key)
        if ov is None or nv is None:
            continue
        ov_f = ov if isinstance(ov, float) else ov / 100 if ov > 1 else ov
        nv_f = nv if isinstance(nv, float) else nv / 100 if nv > 1 else nv
        delta = (nv_f - ov_f) * 100
        flag = "🔥" if delta > 0.5 else ("⚠️" if delta < -0.5 else "—")
        print(f"  {label:<8} {ov_f:.1%} → {nv_f:.1%}  ({delta:+.1f}pp) {flag}")

    # ── 逐项约束 ──
    oc, nc = old.get("per_constraint", {}), new.get("per_constraint", {})
    changes = []
    for k in sorted(set(oc) | set(nc)):
        o, n = oc.get(k), nc.get(k)
        if not o or not n:
            continue
        if o.get("rate") != n.get("rate") or o.get("pass") != n.get("pass"):
            changes.append((k, o, n))
    if changes:
        print("\n【约束变化项】")
        for k, o, n in changes:
            print(f"  {k:<22} {o.get('pass')}/{o.get('total')} → {n.get('pass')}/{n.get('total')}")
    else:
        print("\n【约束变化项】无")

    # ── 逐 query 翻转 ──
    om = {q["id"]: q for q in old.get("per_query", [])}
    nm = {q["id"]: q for q in new.get("per_query", [])}
    flips = []
    for qid in sorted(set(om) & set(nm)):
        for cname in om[qid].get("scores", {}):
            o_s = om[qid]["scores"].get(cname, {})
            n_s = nm[qid]["scores"].get(cname, {})
            ov, nv = o_s.get("pass"), n_s.get("pass")
            if ov != nv and not o_s.get("na") and not n_s.get("na"):
                flips.append((qid, cname, ov, nv, nm[qid].get("input", "")[:24]))
    if flips:
        print("\n【逐 query 翻转】")
        for qid, cname, ov, nv, text in flips:
            mark = "✅修复" if nv else "❌退步"
            print(f"  [{qid}] {cname}: {'PASS' if ov else 'fail'} → {'PASS' if nv else 'fail'} {mark}  {text}")
    else:
        print("\n【逐 query 翻转】无")

    # ── 按分类 ──
    print("\n【按分类】")
    cats = sorted({q.get("expect", {}).get("category", "?") for q in nm.values()})
    for cat in cats:
        oq = [q for q in om.values() if q.get("expect", {}).get("category") == cat]
        nq = [q for q in nm.values() if q.get("expect", {}).get("category") == cat]
        def _pass_rate(qs):
            if not qs:
                return "-"
            passed = sum(1 for q in qs if all(s.get("pass") or s.get("na") for s in q.get("scores", {}).values()))
            return f"{passed}/{len(qs)}"
        print(f"  {cat:<12} {_pass_rate(oq)} → {_pass_rate(nq)}")


if __name__ == "__main__":
    main()

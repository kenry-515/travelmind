"""
Dialog script regression — 3 conversation flows over HTTP (real backend).

Scenarios:
  S1 模糊输入 → 组合建议 → 收敛 → 生成 → 局部修改（diff 只在 days[i]）
  S2 精确输入 → 一轮确认 → 生成
  S3 修改分流：全局（预算砍半）/ 槽位（改成4天）/ 边界（第二天改去动物园）

Run:  python scripts/test_dialog_scripts.py
Requires the backend running on :8000.
"""

import json
import sys

import httpx

BASE = "http://localhost:8000/api/v1"
PASS, FAIL = "✅ PASS", "❌ FAIL"
results = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok))
    print(f"{PASS if ok else FAIL}  {name}" + (f" — {detail}" if detail else ""))
    return ok


def call(path: str, body: dict) -> dict:
    r = httpx.post(f"{BASE}{path}", json=body, timeout=240, trust_env=False)
    r.raise_for_status()
    return r.json()


def sys_path_insert():
    sys.path.insert(0, "D:/TravelMindAgent/backend")


# ── S1: 模糊输入全流程 ──────────────────────────────────

print("=== S1 模糊输入 → 组合 → 生成 → 局部修改 ===")
d = call("/dialog/message", {"text": "想带爸妈出去玩几天"})
sid = d["session_id"]
check("S1.1 模糊输入给组合建议", bool(d.get("suggestions")), str([s["label"] for s in (d.get("suggestions") or [])]))

d = call("/dialog/message", {"session_id": sid, "text": "重庆 3 天"})
check(
    "S1.2 组合点击后进入确认",
    d["stage"] == "confirming" and d["slots"]["city"] == "重庆" and d["slots"]["days"] == 3,
    f"stage={d['stage']} slots={d['slots']['city']}/{d['slots']['days']}",
)

d = call("/dialog/generate", {"session_id": sid})
it1 = d.get("itinerary") or {}
sys_path_insert()
from app.agents.itinerary_contract import validate_itinerary

check("S1.3 生成 delivered 且卡片全量过 schema", d["stage"] == "delivered" and not validate_itinerary(it1))

d = call("/dialog/message", {"session_id": sid, "text": "第二天太赶了"})
it2 = d.get("itinerary") or {}
diff_days = [
    i for i in range(len(it1.get("days", [])))
    if json.dumps(it1["days"][i], sort_keys=True, ensure_ascii=False)
    != json.dumps(it2.get("days", [])[i] if i < len(it2.get("days", [])) else None, sort_keys=True, ensure_ascii=False)
]
others_same = all(
    json.dumps(it1.get(k), sort_keys=True, ensure_ascii=False)
    == json.dumps(it2.get(k), sort_keys=True, ensure_ascii=False)
    for k in ("trip", "budget", "checklist")
)
check(
    "S1.4 局部修改 diff 只在 days[i]",
    diff_days == [1] and others_same,
    f"diff_days={diff_days}, others_same={others_same}",
)

# ── S2: 精确输入一轮确认 ────────────────────────────────

print("=== S2 精确输入 ===")
d = call("/dialog/message", {"text": "三亚3日游，喜欢海滩，带父母"})
check(
    "S2.1 一轮即确认且槽位正确",
    d["stage"] == "confirming" and d["slots"]["city"] == "三亚" and d["slots"]["days"] == 3,
    f"stage={d['stage']} city={d['slots']['city']} days={d['slots']['days']}",
)
d = call("/dialog/generate", {"session_id": d["session_id"]})
check("S2.2 生成 delivered", d["stage"] == "delivered" and bool(d.get("itinerary")))

# ── S3: 修改分流 ────────────────────────────────────────

print("=== S3 修改分流（全局/槽位/边界） ===")
d = call("/dialog/message", {"session_id": sid, "text": "预算砍半"})
check(
    "S3.1 预算砍半 → 槽位变更+回确认",
    d["stage"] == "confirming" and d["slots"]["budget_level"] == "经济",
    f"stage={d['stage']} budget={d['slots']['budget_level']}",
)

d = call("/dialog/message", {"session_id": sid, "text": "改成4天"})
check(
    "S3.2 改成4天 → days=4+回确认",
    d["stage"] == "confirming" and d["slots"]["days"] == 4,
    f"days={d['slots']['days']}",
)

# 边界用例（用户修正 1）：先回到 delivered
d = call("/dialog/generate", {"session_id": sid})
if d["stage"] != "delivered":
    check("S3.3 边界用例前置生成", False, f"stage={d['stage']}")
else:
    before = d.get("itinerary") or {}
    d = call("/dialog/message", {"session_id": sid, "text": "第二天改去动物园"})
    after = d.get("itinerary") or {}
    if not after:
        check("S3.3 「第二天改去动物园」→ local", False, "no itinerary returned")
    else:
        diff_days = [
            i for i in range(len(before.get("days", [])))
            if i >= len(after.get("days", []))
            or json.dumps(before["days"][i], sort_keys=True, ensure_ascii=False)
            != json.dumps(after["days"][i], sort_keys=True, ensure_ascii=False)
        ]
        check(
            "S3.3 「第二天改去动物园」→ local（非 slot_change）",
            diff_days == [1],
            f"diff_days={diff_days}",
        )

# ── 汇总 ────────────────────────────────────────────────

passed = sum(1 for _, ok in results if ok)
print(f"\n===== 对话脚本回归: {passed}/{len(results)} 通过 =====")
sys.exit(0 if passed == len(results) else 1)

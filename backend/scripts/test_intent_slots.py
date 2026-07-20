"""
Intent slot accuracy — 10-utterance corpus over the live dialog API.

Metric: 每条语料的全部断言通过记 1 分，目标准确率 ≥ 90%（≥9/10）。
含用户指定的边界用例「第二天改去动物园」（修改分流，非槽位提取）。

Run:  python scripts/test_intent_slots.py
Requires the backend running on :8000.
"""

import sys

import httpx

BASE = "http://localhost:8000/api/v1"

# (utterance, [(slot_path, expected)...], note)
CORPUS = [
    ("重庆3日游，喜欢夜景和美食", [("city", "重庆"), ("days", 3)], ""),
    ("想带爸妈出去玩几天", [("companions", "家庭")], ""),
    ("三亚5天，预算穷游", [("city", "三亚"), ("days", 5), ("budget_level", "经济")], ""),
    ("和女朋友去大理过周末", [("city", "大理"), ("companions", "情侣")], ""),
    ("西安4天历史文化之旅", [("city", "西安"), ("days", 4)], ""),
    ("成都看熊猫吃火锅，3天", [("city", "成都"), ("days", 3)], ""),
    ("桂林山水摄影5日游", [("city", "桂林"), ("days", 5)], ""),
    ("带5岁孩子去厦门玩2天", [("city", "厦门"), ("days", 2), ("companions", "亲子")], ""),
    ("苏州园林慢游，一个人", [("city", "苏州"), ("companions", "独自")], ""),
]

BOUNDARY_UTTERANCE = "第二天改去动物园"  # 边界：local 分流而非 slot_change


def msg(text: str, sid=None) -> dict:
    body = {"text": text}
    if sid:
        body["session_id"] = sid
    r = httpx.post(f"{BASE}/dialog/message", json=body, timeout=180, trust_env=False)
    r.raise_for_status()
    return r.json()


def main() -> int:
    passed = 0
    details = []

    for text, expects, note in CORPUS:
        d = msg(text)
        slots = d["slots"]
        failed = [f"{k}={slots.get(k)!r}(期望 {v!r})" for k, v in expects if slots.get(k) != v]
        ok = not failed
        passed += ok
        mark = "✅" if ok else "❌"
        details.append(f"{mark} 「{text}」" + (f" — 不符: {'; '.join(failed)}" if failed else ""))

    # 边界用例：需 delivered 态会话
    d = msg("重庆3日游，喜欢夜景和美食")
    sid = d["session_id"]
    if d["stage"] != "confirming":
        details.append("❌ 边界前置：精确输入未进入 confirming")
    else:
        g = httpx.post(f"{BASE}/dialog/generate", json={"session_id": sid}, timeout=240, trust_env=False).json()
        if g["stage"] != "delivered":
            details.append("❌ 边界前置：生成未进入 delivered")
        else:
            before = g.get("itinerary") or {}
            d = msg(BOUNDARY_UTTERANCE, sid)
            after = d.get("itinerary")
            slot_unchanged = d["slots"]["city"] == "重庆" and d["slots"]["days"] == 3
            if not after:
                ok = False
                details.append(f"❌ 「{BOUNDARY_UTTERANCE}」 — 未返回行程（可能被误判为整体/槽位变更）")
            else:
                import json as _json
                diff = [
                    i for i in range(len(before.get("days", [])))
                    if i >= len(after.get("days", []))
                    or _json.dumps(before["days"][i], sort_keys=True, ensure_ascii=False)
                    != _json.dumps(after["days"][i], sort_keys=True, ensure_ascii=False)
                ]
                ok = diff == [1] and slot_unchanged
                passed += ok
                details.append(
                    f"{'✅' if ok else '❌'} 「{BOUNDARY_UTTERANCE}」 — local 分流 diff_days={diff} 槽位未动={slot_unchanged}"
                )

    total = len(CORPUS) + 1
    acc = passed / total * 100
    print(f"===== 语料槽位/分流准确率: {passed}/{total} = {acc:.0f}%（目标 ≥90%）=====")
    for line in details:
        print(line)
    return 0 if passed >= 9 else 1


if __name__ == "__main__":
    sys.exit(main())

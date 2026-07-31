# -*- coding: utf-8 -*-
"""
真实端到端 UX 验证脚本
======================
不用硬编码 fixture，而是：
1. 调真实 RAG（attractions.json）检索景点
2. 调真实 LLM（DEEPSEEK）生成 itinerary
3. 同时拦截 LLM 原始输出（关闭 beautify），跑两次：
   - "原始" itinerary（不跑 beautify）
   - "修复后" itinerary（跑 beautify）
4. 用严格的 UX 质量检查器，找出真实存在的问题

UX 检查器覆盖：
- 重复时间点（如两个 12:00）
- 时间未升序
- 午餐→晚餐间 >5.5h 且无项目
- 餐厅被误判成 [住] / 酒店被误判成 [吃]
- day.eat 文本里出现的餐厅已存在于 items（双重渲染）
- note 没有任何前缀
- 餐厅/酒店出现在 items 末尾而不是按时间排序
"""

import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 初始化路径
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# 加载 .env
from dotenv import load_dotenv
load_dotenv(BACKEND / ".env")

import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# ── 真实场景（昨天 test_comprehensive.py 的 7 场景 + UX 审计）──
SCENARIOS = [
    {
        "id": "BJ_FAMILY_3D",
        "city": "北京",
        "days": 3,
        "profile": {
            "destination": "北京",
            "days": 3,
            "travel_style": "休闲",
            "budget_level": "中等",
            "group": "带娃家庭",
            "season": "春季",
            "purpose": "亲子历史游",
            "preferred_tags": ["故宫", "博物馆", "长城"],
        },
    },
    {
        "id": "CD_FOODIE_4D",
        "city": "成都",
        "days": 4,
        "profile": {
            "destination": "成都",
            "days": 4,
            "travel_style": "休闲",
            "budget_level": "中等",
            "group": "朋友",
            "season": "秋季",
            "purpose": "美食之旅",
            "preferred_tags": ["火锅", "小吃", "宽窄巷子"],
        },
    },
    {
        "id": "XA_HISTORY_2D",
        "city": "西安",
        "days": 2,
        "profile": {
            "destination": "西安",
            "days": 2,
            "travel_style": "深度",
            "budget_level": "中等",
            "group": "独行",
            "season": "春季",
            "purpose": "历史文化游",
            "preferred_tags": ["兵马俑", "古城墙", "历史"],
        },
    },
    {
        "id": "SH_SHOPPING_3D",
        "city": "上海",
        "days": 3,
        "profile": {
            "destination": "上海",
            "days": 3,
            "travel_style": "休闲",
            "budget_level": "中等",
            "group": "闺蜜",
            "season": "全年",
            "purpose": "购物休闲游",
            "preferred_tags": ["购物", "外滩", "打卡"],
        },
    },
    {
        "id": "LJ_DEEP_5D",
        "city": "丽江",
        "days": 5,
        "profile": {
            "destination": "丽江",
            "days": 5,
            "travel_style": "深度",
            "budget_level": "中等",
            "group": "情侣",
            "season": "秋季",
            "purpose": "深度游",
            "preferred_tags": ["古镇", "自然风光", "玉龙雪山"],
        },
    },
    {
        "id": "XM_BEACH_3D",
        "city": "厦门",
        "days": 3,
        "profile": {
            "destination": "厦门",
            "days": 3,
            "travel_style": "休闲",
            "budget_level": "中等",
            "group": "情侣",
            "season": "夏季",
            "purpose": "海边度假",
            "preferred_tags": ["海滩", "海边", "鼓浪屿"],
        },
    },
    {
        "id": "CQ_HOTPOT_4D",
        "city": "重庆",
        "days": 4,
        "profile": {
            "destination": "重庆",
            "days": 4,
            "travel_style": "休闲",
            "budget_level": "中等",
            "group": "朋友",
            "season": "秋季",
            "purpose": "网红打卡游",
            "preferred_tags": ["火锅", "洪崖洞", "拍照"],
        },
    },
]


# ── UX 质量检查器 ──
def _parse_time(t: Any) -> int:
    if not isinstance(t, str):
        return -1
    import re
    m = re.match(r"\s*(\d{1,2}):(\d{1,2})", t)
    if not m:
        return -1
    return int(m.group(1)) * 60 + int(m.group(2))


def audit_ux(itin: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回问题列表。空 = 通过。"""
    issues: List[Dict[str, Any]] = []
    if not itin or not itin.get("days"):
        return [{"type": "empty", "msg": "行程为空"}]

    import re
    for d_idx, day in enumerate(itin.get("days", [])):
        day_no = day.get("day", d_idx + 1)
        items = day.get("items", []) or []
        if not items:
            issues.append({"type": "no_items", "day": day_no, "msg": f"第{day_no}天无任何 items"})
            continue

        # 1. 重复时间点
        times = [it.get("time", "") for it in items]
        seen = {}
        for i, t in enumerate(times):
            seen.setdefault(t, []).append(i)
        for t, idxs in seen.items():
            if len(idxs) > 1 and t:
                pois = [items[i].get("poi", "") for i in idxs]
                issues.append({
                    "type": "dup_time", "day": day_no, "time": t,
                    "msg": f"第{day_no}天 {t} 重复 {len(idxs)} 次: {pois}",
                })

        # 2. 时间未升序
        minutes = [_parse_time(t) for t in times]
        if all(m >= 0 for m in minutes):
            for i in range(1, len(minutes)):
                if minutes[i] < minutes[i - 1]:
                    issues.append({
                        "type": "unsorted", "day": day_no,
                        "msg": f"第{day_no}天时间未升序: {times[i-1]} → {times[i]}",
                    })
                    break

        # 3. 餐厅/酒店排在末尾（最后 2 项是 [吃]/[住] 且时间早于前面）
        if len(items) >= 3:
            last_two = items[-2:]
            earlier = items[:-2]
            for last in last_two:
                last_note = last.get("note", "") or ""
                last_tm = _parse_time(last.get("time", ""))
                if "[吃]" in last_note or "[住]" in last_note:
                    # 检查 earlier 中是否有更晚的时间
                    if earlier:
                        max_earlier_tm = max(_parse_time(e.get("time", "")) for e in earlier)
                        if last_tm > 0 and last_tm < max_earlier_tm:
                            issues.append({
                                "type": "wrong_tail", "day": day_no,
                                "msg": f"第{day_no}天末尾出现 {last.get('time','')} 的 {last.get('poi','')}，比前面更早",
                            })

        # 4. 午餐→晚餐间隔 >5.5h 且中间无项目
        lunch_idx = None
        dinner_idx = None
        for i, it in enumerate(items):
            note = (it.get("note") or "")[:30]
            tm = _parse_time(it.get("time", ""))
            if lunch_idx is None and ("[吃]" in note or "午餐" in note) and 11 * 60 <= tm <= 13 * 60:
                lunch_idx = i
            elif lunch_idx is not None and dinner_idx is None and ("[吃]" in note or "晚餐" in note) and 17 * 60 <= tm <= 20 * 60:
                dinner_idx = i
                break
        if lunch_idx is not None and dinner_idx is not None and dinner_idx > lunch_idx:
            lunch_tm = _parse_time(items[lunch_idx].get("time", ""))
            dinner_tm = _parse_time(items[dinner_idx].get("time", ""))
            gap = dinner_tm - lunch_tm
            between = dinner_idx - lunch_idx - 1
            if gap >= 5 * 60 + 30 and between == 0:
                issues.append({
                    "type": "no_afternoon", "day": day_no,
                    "msg": f"第{day_no}天午餐 {items[lunch_idx].get('time','')} → 晚餐 {items[dinner_idx].get('time','')} 间隔 {gap//60}h{gap%60}m，中间无任何项目",
                })

        # 5. day.eat 文本中出现的餐厅已存在于 items（双重渲染风险）
        eat = day.get("eat", "") or ""
        if eat:
            for it in items:
                poi = (it.get("poi") or "").strip()
                note = it.get("note") or ""
                if "[吃]" in note and len(poi) >= 2 and poi in eat:
                    issues.append({
                        "type": "dup_eat", "day": day_no, "poi": poi,
                        "msg": f"第{day_no}天 day.eat 中已包含餐厅「{poi}」，但 items 也有 [吃] 卡片，前端会双重渲染",
                    })

        # 6. 餐厅被误判成 [住] / 酒店被误判成 [吃]
        for it in items:
            poi = it.get("poi", "") or ""
            note = it.get("note", "") or ""
            # 餐厅但被标 [住]
            food_keywords = ["火锅", "小吃", "菜馆", "餐厅", "面馆", "小笼", "馒头店", "菜系", "烧烤"]
            if "[住]" in note and any(k in poi for k in food_keywords):
                issues.append({
                    "type": "wrong_marker", "day": day_no, "poi": poi,
                    "msg": f"第{day_no}天 餐厅「{poi}」被误标为 [住]",
                })
            # 酒店但被标 [吃]：只有当 poi 整体是酒店名（以"酒店/宾馆/民宿"结尾或就是"XX饭店"无餐饮修饰）才算误判
            # 排除："忠顺饭店·特色家常菜(忠义店)" 这种实际是餐厅但名字带"饭店"的
            is_pure_hotel = bool(re.search(
                r"(酒店|宾馆|民宿|客栈|旅馆|青旅|大酒店|公寓酒店|酒店式公寓)$", poi
            )) or (poi.endswith("饭店") and not re.search(r"(菜|火锅|小吃|烧烤|面|粉)", poi))
            if "[吃]" in note and is_pure_hotel:
                issues.append({
                    "type": "wrong_marker", "day": day_no, "poi": poi,
                    "msg": f"第{day_no}天 酒店「{poi}」被误标为 [吃]",
                })

    return issues


# ── 拦截 LLM 原始输出 ──
async def run_scenario(scenario: Dict, with_beautify: bool) -> Tuple[Optional[Dict], List[Dict]]:
    """跑一个场景，返回 (itinerary, ux_issues)。

    走完整 RAG 流程：attractions.json → init_rag → retrieve → planning_agent.generate_itinerary
    """
    from app.rag import init_rag_from_data
    from app.rag.retriever import retrieve
    from app.agents import planning_agent
    from app.agents.itinerary_contract import beautify_and_sanitize_day_items

    # 1. 初始化 RAG（首次）
    if not hasattr(run_scenario, "_rag_inited"):
        data_path = BACKEND / "data" / "attractions.json"
        ok = init_rag_from_data(data_path)
        if not ok:
            return None, [{"type": "rag_init_failed"}]
        run_scenario._rag_inited = True

    # 2. RAG 检索（真实 retrieve）
    profile = scenario["profile"]
    user_profile = {
        "destination": profile["destination"],
        "tags": profile["preferred_tags"][:3],
        "budget_level": profile["budget_level"],
        "days": profile["days"],
        "travel_style": profile["travel_style"],
        "companions": profile["group"],
        "constraints": [],
    }
    query = f"{profile['destination']} {profile['purpose']} {' '.join(profile['preferred_tags'][:3])}"
    rag_results = await retrieve(user_profile=user_profile, query=query, top_k=30)
    if not rag_results:
        return None, [{"type": "rag_empty"}]
    print(f"  RAG 检索到 {len(rag_results)} 个候选（top1={(rag_results[0].get('metadata') or {}).get('name','')}）")

    # 3. monkey-patch beautify（按需禁用）
    original_beautify = planning_agent.beautify_and_sanitize_day_items
    if with_beautify:
        planning_agent.beautify_and_sanitize_day_items = original_beautify
    else:
        planning_agent.beautify_and_sanitize_day_items = lambda data: 0  # no-op

    try:
        # 4. 调真实 LLM 生成 itinerary
        from app.services.weather_service import get_weather_forecast
        weather = None
        try:
            wf = await get_weather_forecast(profile["destination"])
            if wf and hasattr(wf, "to_dict"):
                weather = wf.to_dict()
        except Exception as e:
            print(f"  (天气获取跳过: {e})")

        itin = await planning_agent.generate_itinerary(profile, rag_results, weather)
    finally:
        planning_agent.beautify_and_sanitize_day_items = original_beautify

    if not itin:
        return None, [{"type": "llm_failed"}]

    # 5. UX 检查
    issues = audit_ux(itin)
    return itin, issues


def print_itin_preview(itin: Dict, max_days: int = 2, label: str = ""):
    """打印 itinerary 预览，方便人眼检查。"""
    if not itin:
        print(f"  [{label}] (空)")
        return
    print(f"  [{label}] trip.title = {itin.get('trip', {}).get('title', '')}")
    for d_idx, day in enumerate((itin.get("days") or [])[:max_days]):
        day_no = day.get("day", d_idx + 1)
        print(f"  ── 第{day_no}天 ── eat={day.get('eat','')!r}  stay={day.get('stay','')!r}")
        for it in day.get("items", []):
            poi = (it.get("poi") or "").strip()
            note = (it.get("note") or "")[:60]
            print(f"    {it.get('time','???')}  {poi:<24}  {note}")


async def main():
    print("=" * 80)
    print("真实端到端 UX 验证 (RAG + DeepSeek LLM)")
    print("=" * 80)

    summary = []
    for sc in SCENARIOS:
        print(f"\n{'─' * 80}")
        print(f"场景: {sc['id']}  {sc['city']} {sc['days']}天  目的={sc['profile']['purpose']}")
        print(f"{'─' * 80}")

        # ── Run 1: 不跑 beautify（看 LLM 原始问题）──
        print(f"\n[A] 不启用 beautify（看 LLM 原始输出）...")
        itin_raw, issues_raw = await run_scenario(sc, with_beautify=False)
        if itin_raw is None:
            print(f"  ❌ 生成失败: {issues_raw}")
            summary.append({"id": sc["id"], "raw": None, "fixed": None, "raw_issues": issues_raw})
            continue
        print(f"  ✓ 生成成功 ({len(itin_raw.get('days', []))} 天)")
        print_itin_preview(itin_raw, max_days=2, label="RAW")
        print(f"  发现 UX 问题 {len(issues_raw)} 个:")
        for iss in issues_raw[:8]:
            print(f"    ⚠ {iss.get('type')}: {iss.get('msg','')}")

        # ── Run 2: 跑 beautify（看修复效果）──
        # 直接在 raw 上跑 beautify，避免重复调 LLM
        from app.agents.itinerary_contract import beautify_and_sanitize_day_items
        itin_fixed = copy.deepcopy(itin_raw)
        n = beautify_and_sanitize_day_items(itin_fixed)
        issues_fixed = audit_ux(itin_fixed)

        print(f"\n[B] 启用 beautify（应用 {n} 次修复）")
        print_itin_preview(itin_fixed, max_days=2, label="FIXED")
        print(f"  残留 UX 问题 {len(issues_fixed)} 个:")
        for iss in issues_fixed[:8]:
            print(f"    ⚠ {iss.get('type')}: {iss.get('msg','')}")

        summary.append({
            "id": sc["id"],
            "raw_issues": len(issues_raw) if itin_raw else issues_raw,
            "fixed_issues": len(issues_fixed),
            "raw_examples": issues_raw[:3],
            "fixed_examples": issues_fixed[:3],
        })

    # ── 总结 ──
    print(f"\n{'=' * 80}")
    print("端到端验证总结（真实 RAG + DeepSeek LLM + 完整后处理链）")
    print(f"{'=' * 80}")
    print(f"{'场景':<20} {'LLM状态':<10} {'原始UX问题':<12} {'修复后残留':<14} {'是否生产级':<10}")
    report_rows = []
    for s in summary:
        raw_issues = s.get("raw_issues", 0)
        if isinstance(raw_issues, list) and raw_issues and isinstance(raw_issues[0], dict):
            et = raw_issues[0].get("type", "")
            if et in ("llm_failed", "no_kb_data", "rag_empty", "rag_init_failed"):
                print(f"{s['id']:<20} {'❌失败':<10} {'N/A':<12} {'N/A':<14} {'❌ LLM生成失败':<10}")
                report_rows.append({**s, "status": "LLM_FAILED"})
                continue
        raw_n = len(raw_issues) if isinstance(raw_issues, list) else raw_issues
        fix_n = s.get("fixed_issues", 0)
        ok = "✓ 通过" if fix_n == 0 else f"✗ 残留 {fix_n}"
        print(f"{s['id']:<20} {'✓成功':<10} {raw_n:<12} {fix_n:<14} {ok:<10}")
        report_rows.append({**s, "status": "PASSED" if fix_n == 0 else "UX_RESIDUAL"})

    # 持久化报告
    report_path = BACKEND / "reports" / "e2e_ux_audit_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": len(report_rows),
                "passed": sum(1 for r in report_rows if r["status"] == "PASSED"),
                "llm_failed": sum(1 for r in report_rows if r["status"] == "LLM_FAILED"),
                "ux_residual": sum(1 for r in report_rows if r["status"] == "UX_RESIDUAL"),
            },
            "details": report_rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n报告已写入: {report_path}")

    # 如果有残留问题，详细打印
    any_residual = any(s.get("fixed_issues", 0) > 0 for s in summary)
    if any_residual:
        print(f"\n残留问题详情:")
        for s in summary:
            if s.get("fixed_issues", 0) > 0:
                print(f"  [{s['id']}]")
                for iss in s.get("fixed_examples", []):
                    print(f"    - {iss}")


if __name__ == "__main__":
    asyncio.run(main())

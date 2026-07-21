"""
TravelMind Agent — Dialog Manager (对话式规划的意图状态机)

纯 Python、无 LLM 依赖、可单测。职责：
- 槽位（intent slots）持有与确定性合并
- 阶段流转：collecting → confirming → generating → delivered
- 追问预算（≤3 轮）与默认填充
- 修改分流判定（规则优先；LLM 兜底在 API 层）

会话状态存内存（TTL 2h），需单 worker 运行，重启丢会话；
生产环境请替换为 Redis（见 README）。

用法见 backend/app/api/dialog.py。
"""

import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.services.session_store import get_session_store

# ── 常量 ────────────────────────────────────────────────

SESSION_TTL_SECONDS = 2 * 3600
MAX_FOLLOWUPS = 3

DEFAULT_SLOTS: Dict[str, Any] = {
    "city": None,          # 必需
    "days": None,          # 必需
    "date": "下周",
    "companions": "不限",
    "budget_level": "舒适",
    "tags": [],
    "pace": "休闲",
}

# KB 覆盖的 15 个城市（用于模糊输入的组合建议）
SUGGESTION_POOL = [
    ("重庆", "夜景/美食/山城"),
    ("成都", "美食/熊猫/慢生活"),
    ("三亚", "海滩/海岛/度假"),
    ("西安", "历史/博物馆/古迹"),
    ("桂林", "山水/自然/摄影"),
    ("苏州", "园林/古镇/文艺"),
]

_DAY_WORDS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}


# ── 会话存取（经 SessionStore 抽象，内存/Redis 可切换）──

async def get_session(session_id: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """取或建会话。返回 (session_id, state)。

    注意：返回的 state 是内存对象——修改后须用 save_session() 持久化
    （Redis 后端必须显式写回，内存后端为兼容语义也统一显式保存）。
    """
    store = get_session_store()
    if session_id:
        state = await store.get(session_id)
        if state is not None:
            await store.touch(session_id, SESSION_TTL_SECONDS)
            return session_id, state

    sid = session_id or f"dlg_{uuid.uuid4().hex[:12]}"
    state = {
        "stage": "collecting",
        "slots": dict(DEFAULT_SLOTS, tags=[]),
        "followups_used": 0,
        "itinerary": None,
        "queued": [],
        "touched": time.time(),
    }
    await store.set(sid, state, SESSION_TTL_SECONDS)
    return sid, state


async def save_session(session_id: str, state: Dict[str, Any]) -> None:
    """把内存中修改过的 state 显式写回存储（并重置 TTL）。"""
    state["touched"] = time.time()
    await get_session_store().set(session_id, state, SESSION_TTL_SECONDS)


# ── 槽位合并（确定性，非空才覆盖）──────────────────────

# 被 LLM 当成字符串输出的空值（"null"/"none"）及用户的"无所谓"表达
_NULLISH = {"", "null", "none", "未知", "不限", "随便", "都可以", "你定", "不知道", "还没想", "还没想好"}


def merge_slots(state: Dict[str, Any], extracted: Dict[str, Any]) -> List[str]:
    """把 extract_profile 的结果合并进槽位。返回变更的槽位名列表。"""
    slots = state["slots"]
    changed = []

    city = (extracted.get("destination") or "").strip()
    if city and city.lower() not in _NULLISH and city != slots["city"]:
        slots["city"] = city
        changed.append("city")

    days = extracted.get("days")
    if isinstance(days, int) and 1 <= days <= 14 and days != slots["days"]:
        slots["days"] = days
        changed.append("days")

    comp = (extracted.get("companions") or "").strip()
    if comp and comp.lower() not in _NULLISH and comp != slots["companions"]:
        slots["companions"] = comp
        changed.append("companions")

    budget = (extracted.get("budget_level") or "").strip()
    if budget and budget.lower() not in _NULLISH and budget != slots["budget_level"]:
        slots["budget_level"] = budget
        changed.append("budget_level")

    tags = extracted.get("tags") or []
    new_tags = [t for t in tags if t not in slots["tags"]]
    if new_tags:
        slots["tags"] = (slots["tags"] + new_tags)[:8]
        changed.append("tags")

    style = (extracted.get("travel_style") or "").strip()
    if style and style.lower() not in _NULLISH and style != slots["pace"]:
        slots["pace"] = style
        changed.append("pace")

    return changed


def apply_slot_override(state: Dict[str, Any], override: Dict[str, Any]) -> List[str]:
    """状态条手动编辑 → 强制覆盖。"""
    slots = state["slots"]
    changed = []
    for key, value in override.items():
        if key in slots and value is not None and value != slots[key]:
            slots[key] = value
            changed.append(key)
    return changed


# ── 阶段推进 ────────────────────────────────────────────

def required_missing(slots: Dict[str, Any]) -> List[str]:
    return [k for k in ("city", "days") if not slots.get(k)]


def combo_suggestions(state: Dict[str, Any]) -> List[Dict[str, str]]:
    """模糊输入 → 2-3 个「城市×天数」组合卡（不连环提问）。"""
    tags = state["slots"]["tags"]
    pool = SUGGESTION_POOL
    if tags:
        # 有标签时优先标签相关的城市
        def score(item):
            return int(any(t in item[1] for t in tags))
        pool = sorted(SUGGESTION_POOL, key=score, reverse=True)
    picked = pool[:3]
    days_hint = state["slots"].get("days")
    return [
        {
            "city": city,
            "days": str(days_hint or 3),
            "label": f"{city} {days_hint or 3} 天（{feat}）",
        }
        for city, feat in picked
    ]


def next_action(state: Dict[str, Any]) -> Dict[str, Any]:
    """决定下一步：追问（≤3）/ 组合建议 / 默认值填满 / 进入确认。"""
    slots = state["slots"]
    missing = required_missing(slots)

    if missing and state["followups_used"] < MAX_FOLLOWUPS:
        state["followups_used"] += 1
        if "city" in missing:
            # 目的地未定 → 先给 2-3 个组合建议（有标签时按标签排序），不连环提问
            return {
                "type": "suggest",
                "suggestions": combo_suggestions(state),
                "reply": "没问题～先帮你框个范围，挑一个，或者直接告诉我城市：",
            }
        question = "计划玩几天？"
        return {"type": "ask", "reply": question}

    # 追问预算耗尽或槽位齐全 → 默认值填满并明示
    filled = []
    if not slots["city"]:
        slots["city"] = "重庆"
        filled.append("城市=重庆")
    if not slots["days"]:
        slots["days"] = 3
        filled.append("天数=3")

    state["stage"] = "confirming"
    summary = build_summary(state)
    if filled:
        summary = f"先按默认值安排（{'，'.join(filled)}，可随时改）。\n" + summary
    return {"type": "confirm", "reply": summary, "confirm": True}


def build_summary(state: Dict[str, Any]) -> str:
    s = state["slots"]
    tags = "、".join(s["tags"]) if s["tags"] else "不限"
    return (
        f"明白了，我整理一下：{s['city']} · {s['days']} 天 · "
        f"{s['companions']}同行 · 偏好 {tags} · 预算{s['budget_level']} · "
        f"节奏{s['pace']} · {s['date']}出发。\n"
        f"没问题的话点「生成行程卡片」，要改哪项直接说。"
    )


def synthesize_input(slots: Dict[str, Any]) -> str:
    """槽位 → 生成管线的自然语言输入。"""
    parts = [f"{slots['city']}{slots['days']}日游"]
    comp = slots["companions"]
    if comp and comp != "不限":
        parts.append("家庭出游" if comp == "家庭" else f"{comp}同行")
    if slots["tags"]:
        parts.append("喜欢" + "、".join(slots["tags"][:4]))
    if slots["pace"] and slots["pace"] != "不限":
        parts.append(f"节奏{slots['pace']}")
    if slots["budget_level"]:
        parts.append(f"预算{slots['budget_level']}")
    return "，".join(parts)


# ── 修改分流（规则优先，见用户修正 1）────────────────────

_GLOBAL_RE = re.compile(r"整体|全部|全都|整个|所有|总体")
# 天数限定词：「第N天」/「第二天」汉字序数可裸用，纯数字必须带「第」
# （否则「改成4天」会被误判为天数限定——那是 slot_change）
_DAY_RE = re.compile(r"第\s*[一二两三四五12345]\s*天|[一二两三四五]天|首日|末天|最后一天")
_SLOT_DAYS_RE = re.compile(r"(?:改成|改为|换成|变成)?\s*(\d{1,2})\s*天")
_BUDGET_RE = re.compile(r"预算.*?(砍半|减半|提高|增加|提升|降低|减少|缩减)")
_CITY_CHANGE_RE = re.compile(r"(?:改去|换成|不去.+?了?去|改到)([\u4e00-\u9fa5]{2,4})")


def _day_index_of(text: str) -> Optional[int]:
    m = _DAY_RE.search(text)
    if not m:
        return None
    token = m.group(0)
    if token in ("首日",):
        return 0
    if token in ("末天", "最后一天"):
        return -1  # 由调用方按行程长度解析
    for w, n in _DAY_WORDS.items():
        if w in token:
            return n - 1
    return None


def classify_modification(text: str, itinerary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """修改请求分流（编排层判定，模型不猜）。

    优先级（用户修正 1）：
    1. 句含「第N天」且不含「整体/全部」→ local
    2. 无天数限定时，才判定 slot_change（改天数/预算/城市）
    3. 含「整体/全部」→ global
    4. 命中行程内具体 POI → local（所在天）
    5. 未命中 → unknown（API 层 LLM 兜底 / 反问）
    """
    # 显式改天数（"改成3天/改为三天"）→ slot_change，优先于天数限定判定
    m = re.search(r"(?:改成|改为|变成|换成)\s*([一二两三四五123456789]{1,2})\s*天", text)
    if m and not _GLOBAL_RE.search(text):
        token = m.group(1)
        days_val = _DAY_WORDS.get(token) or (int(token) if token.isdigit() else None)
        if days_val:
            return {
                "type": "slot_change",
                "slot_updates": {"days": days_val},
                "reason": "days-change",
            }

    day_idx = _day_index_of(text)
    has_global = bool(_GLOBAL_RE.search(text))

    if day_idx is not None and not has_global:
        if day_idx == -1 and itinerary and itinerary.get("days"):
            day_idx = len(itinerary["days"]) - 1
        return {"type": "local", "day_index": max(day_idx, 0), "reason": "day-qualifier"}

    if day_idx is None:
        m = _SLOT_DAYS_RE.search(text)
        if m and ("改" in text or "变" in text or text.strip().startswith(m.group(1) + "天")):
            return {
                "type": "slot_change",
                "slot_updates": {"days": int(m.group(1))},
                "reason": "days-change",
            }
        if _BUDGET_RE.search(text):
            level = "经济" if any(k in text for k in ("砍半", "减半", "降低", "减少", "缩减")) else "奢华"
            return {
                "type": "slot_change",
                "slot_updates": {"budget_level": level},
                "reason": "budget-change",
            }
        m = _CITY_CHANGE_RE.search(text)
        if m:
            return {
                "type": "slot_change",
                "slot_updates": {"city": m.group(1)},
                "reason": "city-change",
            }

    if has_global:
        return {"type": "global", "reason": "global-word"}

    # 行程内 POI 命中 → 所在天局部修改
    if itinerary:
        for i, day in enumerate(itinerary.get("days", [])):
            for item in day.get("items", []):
                poi = re.split(r"[（(]", item.get("poi", ""))[0].strip()
                if len(poi) >= 3 and poi in text:
                    return {"type": "local", "day_index": i, "reason": f"poi-hit:{poi}"}

    return {"type": "unknown", "reason": "no-rule-hit"}

"""
TravelMind Agent — Dialog Manager (对话式规划的意图状态机)

纯 Python、无 LLM 依赖、可单测。职责：
- 槽位（intent slots）持有与确定性合并
- 阶段流转：collecting → confirming → generating → delivered
- 追问预算（≤3 轮）与默认填充
- 修改分流判定（规则优先；LLM 兜底在 API 层）
- KB 城市覆盖校验（Phase 8.1 拒答机制）

会话状态存内存（TTL 2h），需单 worker 运行，重启丢会话；
生产环境请替换为 Redis（见 README）。

用法见 backend/app/api/dialog.py。
"""

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

# ── KB 城市覆盖检测（Phase 8.1 拒答机制）─────────────────

_kb_cities: Optional[Set[str]] = None
_KB_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "attractions.json"


def _get_kb_cities() -> Set[str]:
    """懒加载知识库覆盖的城市集合（从 attractions.json 提取）。"""
    global _kb_cities
    if _kb_cities is not None:
        return _kb_cities
    try:
        with open(_KB_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cities = {a.get("city", "") for a in data.get("attractions", []) if a.get("city")}
        _kb_cities = cities
        return _kb_cities
    except Exception:
        # 文件不可用时回退到 SUGGESTION_POOL 的城市
        return {c for c, _ in SUGGESTION_POOL}


def check_city_coverage(city: str) -> Tuple[bool, str]:
    """检测城市是否在 KB 覆盖范围内。

    Returns:
        (is_covered, reason) — is_covered=False 时 reason 是面向用户的提示。
    """
    if not city or not city.strip():
        return False, "未识别到目的地"
    kb = _get_kb_cities()
    if city in kb:
        return True, ""
    # 模糊匹配：城市名是否包含在任意 KB 城市中（或反向）
    for kb_city in kb:
        if city in kb_city or kb_city in city:
            return True, ""  # 如 "北京" 匹配 "北京"
    # 生成建议列表
    sorted_cities = sorted(kb)
    suggestions = "、".join(sorted_cities[:8])
    more = f"等{len(kb)}个城市" if len(kb) > 8 else ""
    return False, f"抱歉，「{city}」暂不在知识库覆盖范围内。当前支持：{suggestions}{more}。"


def _reset_kb_cities() -> None:
    """测试用：重置 KB 城市缓存。"""
    global _kb_cities
    _kb_cities = None

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

# ── 提取结果接地校验（Phase 12.25）─────────────────────
# 根因：extract_profile 对用户没说的信息返回"默认猜测"（如"我想去惠州玩"
# → days=3、tags=["休闲","自然"]），槽位看似收满，状态机直接推生成卡片。
# 规则：LLM 提取的槽位值必须在用户原文里有依据（字面或同义线索），否则丢弃。

_DAYS_CUE_RE = re.compile(
    r"\d{1,2}\s*天|[一二两三四五六七]天|日游|周末|小长假|五一|国庆|暑假|寒假|假期"
)
_COMPANIONS_CUE_RE = re.compile(
    r"爸妈|父母|孩子|娃|家人|家庭|朋友|闺蜜|情侣|对象|同事|同学|一个人|独自|自己"
)
_BUDGET_CUE_RE = re.compile(r"预算|穷游|经济|实惠|便宜|省钱|高端|奢华|豪华|贵")
_PACE_CUE_RE = re.compile(r"慢|休闲|放松|度假|紧凑|赶|特种兵|轻松|躺平")

# 标签同义线索（未列出的标签只接受原文字面命中——宁缺毋滥，
# 缺的偏好会在下一轮追问中自然补上）
_TAG_CUES: Dict[str, Tuple[str, ...]] = {
    "美食": ("美食", "吃", "火锅", "小吃", "烤", "粉", "面", "餐厅", "菜"),
    "夜景": ("夜景", "夜生活", "夜市", "夜游", "夜"),
    "自然": ("自然", "风景", "山水", "海景", "风光", "湖", "山", "海滩"),
    "海岛": ("海", "岛", "沙滩", "海边"),
    "历史": ("历史", "文化", "古迹", "博物馆", "古城", "老街", "文物"),
    "古镇": ("古镇", "古城", "老街", "古村落"),
    "博物馆": ("博物馆", "博物", "展馆", "展览"),
    "亲子": ("亲子", "孩子", "爸妈", "父母", "家人", "带娃"),
    "休闲": ("休闲", "慢", "放松", "度假", "躺"),
    "摄影": ("摄影", "拍照", "打卡", "出片", "拍"),
    "购物": ("购物", "买", "商场", "免税店", "逛街"),
    "网红打卡": ("打卡", "网红", "拍照"),
    "园林": ("园林", "园"),
    "寺庙": ("寺", "庙", "祈福", "烧香"),
    "温泉": ("温泉", "泡汤", "泡"),
    "演出": ("演出", "表演", "剧院", "话剧", "演唱会"),
}


def _tag_grounded(tag: str, text: str) -> bool:
    if tag and tag in text:
        return True
    cues = _TAG_CUES.get(tag)
    return bool(cues) and any(c in text for c in cues)


def ground_extraction(extracted: Dict[str, Any], text: str) -> Dict[str, Any]:
    """过滤 LLM 提取结果中没有原文依据的槽位值（接地校验）。

    只放行：城市（merge 阶段另有覆盖校验兜底）、有天数线索的天数、
    有同义/字面线索的标签、有线索的同行/预算/节奏。
    对话专用；/agent/plan 单发规划不受影响（那里需要 LLM 自由推断）。
    """
    text = text or ""
    out = dict(extracted)

    days = out.get("days")
    if isinstance(days, int) and not _DAYS_CUE_RE.search(text):
        out["days"] = None

    tags = out.get("tags") or []
    out["tags"] = [t for t in tags if _tag_grounded(t, text)]

    if out.get("companions") and not _COMPANIONS_CUE_RE.search(text):
        out["companions"] = None
    if out.get("budget_level") and not _BUDGET_CUE_RE.search(text):
        out["budget_level"] = None
    if out.get("travel_style") and not _PACE_CUE_RE.search(text):
        out["travel_style"] = None
    return out


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


# 放权语：用户明确"你定/随便"→ 停止追问，默认值明示后确认（Phase 12.25）
_DEFER_RE = re.compile(
    r"随便|你看着办|你看[着掐]办|都可以|听你的|你[来帮]定|不重要|无所谓|直接生成|直接出|赶紧生成"
)


def next_action(state: Dict[str, Any], text: str = "") -> Dict[str, Any]:
    """决定下一步：逐槽位追问（每槽位最多一次）/ 组合建议 / 默认值填满 / 确认 / 拒答。

    Phase 12.25 重构——意图明确前不推生成卡片：
    city → days → 偏好 逐槽位自然收敛，每轮只问一个问题、同一槽位
    最多问一次（state["asked"] 标记）；用户说放权语（"随便/你看着办"）
    才跳过剩余追问直接用默认值。修复"只说一句『那就去南宁吧』就被
    赶鸭子上架推出生成卡片"的缺陷（根因：旧版 required_missing 只查
    city/days，tags/预算/同行全部静默默认值）。
    """
    slots = state["slots"]
    asked: Dict[str, bool] = state.setdefault("asked", {})
    defer = bool(_DEFER_RE.search(text or ""))

    # Phase 8.1: 城市覆盖校验 — KB 外城市直接拒答（城市已知时优先处理）
    if slots.get("city"):
        covered, reason = check_city_coverage(slots["city"])
        if not covered:
            # 还有追问配额 → 提示后给建议，保留槽位等用户修正
            kb_cities = sorted(_get_kb_cities())
            suggestions = [
                {"city": c, "days": str(slots.get("days") or 3), "label": c}
                for c in kb_cities[:6]
            ]
            if state["followups_used"] < MAX_FOLLOWUPS:
                state["followups_used"] += 1
                return {
                    "type": "suggest",
                    "suggestions": suggestions,
                    "reply": reason,
                }
            # 追问预算已耗尽 → 拒答，不给硬生成
            return {
                "type": "refuse",
                "reason": reason,
                "suggestions": suggestions,
                "reply": reason,
            }

    # 目的地未定 → 组合建议（最多一次；再未定则默认值明示）
    if not slots["city"]:
        if not asked.get("city") and state["followups_used"] < MAX_FOLLOWUPS:
            state["followups_used"] += 1
            asked["city"] = True
            # 目的地未定 → 先给 2-3 个组合建议（有标签时按标签排序），不连环提问
            return {
                "type": "suggest",
                "suggestions": combo_suggestions(state),
                "reply": "没问题～先帮你框个范围，挑一个，或者直接告诉我城市：",
            }

    # 天数未定 → 问一次
    if (
        not defer
        and not slots["days"]
        and not asked.get("days")
        and state["followups_used"] < MAX_FOLLOWUPS
    ):
        state["followups_used"] += 1
        asked["days"] = True
        return {"type": "ask", "reply": "计划玩几天？"}

    # 偏好未收集 → 问一次（"慢慢聊"的核心一步，意图明确前不推卡片）
    if (
        not defer
        and not slots["tags"]
        and not asked.get("tags")
        and state["followups_used"] < MAX_FOLLOWUPS
    ):
        state["followups_used"] += 1
        asked["tags"] = True
        return {
            "type": "ask",
            "reply": "想怎么玩？比如美食、风景、历史文化、亲子……没特别偏好就说「随便」。",
        }

    # 追问完成（或被放权）→ 默认值填满并明示
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


# ── Phase 12.1: 自由对话意图分类 ─────────────────────────

# Keywords that suggest the user is asking a general travel question
# (not trying to fill slots or modify an itinerary)
_CHAT_PATTERNS = [
    # Question words
    re.compile(r"吗[？?]?$"),
    re.compile(r"怎么[样样]"),
    re.compile(r"如何"),
    re.compile(r"什么|啥|哪[些个]"),
    re.compile(r"有没[有有]"),
    re.compile(r"能不能|可以不可以|可不可以|能否"),
    re.compile(r"多[少久远长高]"),
    re.compile(r"为[什啥]么"),
    # Weather inquiries
    re.compile(r"天气|气温|下雨|刮风|温度|穿什么"),
    # Food/attraction inquiries
    re.compile(r"好吃|推荐.*[店菜食餐]|[店菜食餐].*推荐"),
    re.compile(r"好玩|值得去|必去|打卡"),
    # Travel tips
    re.compile(r"注意|建议|小贴士|攻略|怎么[去玩逛]"),
    # Casual chat
    re.compile(r"你好|谢谢|嗨|哈[喽罗]|再见|拜拜"),
    re.compile(r"讲[个下]|说[说下]|介绍|聊聊"),
    # Explicit chat intent (not slot filling)
    re.compile(r"聊[天聊]|随便|问问|打听"),
]

# Slot-filling keywords — if present, treat as slot fill even if chat-like
_SLOT_FILL_PATTERNS = [
    re.compile(r"(\d+)天"),
    re.compile(r"改成|改为|换成|变成"),
    re.compile(r"第[一二两三四五\d]天"),
    re.compile(r"预算"),
    re.compile(r"整体|全部|全都|整个|所有|重新"),
    re.compile(r"不去|换成|删[掉除]|加[上一个]"),
]


def classify_intent(text: str) -> str:
    """Classify user input as 'chat' (free conversation) or 'slot_fill'.

    Returns 'chat' when the user is asking a general travel question,
    not trying to set planning parameters or modify an itinerary.
    Returns 'slot_fill' when the input looks like parameter setting.
    """
    if not text or not text.strip():
        return "slot_fill"

    # Slot-fill takes priority — if user is clearly setting/modifying params
    for pat in _SLOT_FILL_PATTERNS:
        if pat.search(text):
            return "slot_fill"

    # Check chat patterns
    chat_hits = sum(1 for pat in _CHAT_PATTERNS if pat.search(text))

    # If 2+ chat patterns hit, or the text ends with a question mark
    if chat_hits >= 2:
        return "chat"
    if chat_hits >= 1 and (text.endswith("?") or text.endswith("？") or len(text) > 15):
        return "chat"

    # Short inputs with no clear patterns → slot fill (likely a preference)
    if len(text) <= 10 and chat_hits == 0:
        return "slot_fill"

    # Default: slot fill (planning is the primary use case)
    return "slot_fill"


# ── 单项确定性删除（Phase 12.27："想去掉不想去的行程"）────────

_REMOVE_TRIGGER_RE = re.compile(r"去掉|删[掉除]|不去|别去|不想去|不想要|取消")


def try_remove_item(itinerary: Optional[Dict[str, Any]], text: str):
    """delivered 态单项删除：用户点名"去掉 XX"→ 确定性从 day.items 移除。

    零 LLM。匹配规则：触发词 + 行程内 POI 名归一化后包含于文本（取最长匹配）。
    Returns:
        (poi, day_no)                删除成功
        ("__day_would_empty__", day_no, poi)  当天只剩这一项，删除会清空整天（未执行）
        None                          非删除请求或未匹配
    """
    if not itinerary or not text or not _REMOVE_TRIGGER_RE.search(text):
        return None

    from app.agents.route_optimizer import _core_name, _normalize

    norm_text = _normalize(text)
    best = None  # (variant_len, day, item, poi)
    for day in itinerary.get("days", []):
        if not isinstance(day, dict):
            continue
        for item in day.get("items", []):
            poi = item.get("poi", "") if isinstance(item, dict) else ""
            # 双变体匹配：规范化全名 + 核心名（"磁器口古镇"→"磁器口"）
            for variant in {_normalize(poi), _core_name(poi)}:
                if len(variant) >= 2 and variant in norm_text:
                    if best is None or len(variant) > best[0]:
                        best = (len(variant), day, item, poi)
    if not best:
        return None

    _, day, item, poi = best
    day_no = day.get("day")
    if len(day.get("items", [])) <= 1:
        return ("__day_would_empty__", day_no, poi)

    day["items"].remove(item)
    from app.agents.itinerary_contract import inject_computed_fields
    inject_computed_fields(itinerary)  # 重算地点数等统计
    return (poi, day_no)


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

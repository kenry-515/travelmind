"""
TravelMind Agent — Planning Agent

LLM-powered itinerary generator producing output that STRICTLY conforms to
docs/itinerary.schema.json (loaded via itinerary_contract — the single
source of truth). Rendering layers consume only contract-valid JSON.

- generate_itinerary: full plan from profile + ranked recommendations
  (+ optional weather forecast for weather-adaptive scheduling)
- regenerate_day: replace a single day based on user feedback, everything
  else untouched (数据结构支持局部重生成)

Failure policy: at most 2 retries; on final failure a structured error is
logged and {} is returned so the orchestrator can accumulate it.
"""

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

from app.services.llm_service import get_llm_provider

from app.agents.itinerary_contract import (
    budget_sum_mismatch,
    classify_poi_indoor,
    compute_weather_fit,
    attach_daily_dining_and_stay,
    enforce_pace_density,
    enforce_severe_weather_indoor,
    inject_computed_fields,
    month_inconsistency_errors,
    schema_for_llm,
    season_of,
    trip_has_rain,
    validate_day,
    validate_day_continuity,
    validate_itinerary,
    validate_pre_injection,
    weather_coverage_errors,
)
from app.agents.route_optimizer import optimize_itinerary
from app.config.settings import settings
from app.services.name_normalizer import normalize_poi_name

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # 2 retries → 3 attempts total; then structured failure

# Phase 8.1: Feasibility thresholds
MAX_PLACES_PER_DAY = 8  # Warn if more than 8 visit items per day


def _check_feasibility(
    profile: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check if the request is feasible given available data.

    Returns:
        Dict with keys: feasible (bool), warning (str|None), severity (str).
        Non-fatal warnings still allow generation; fatal blocks it.
    """
    days = profile.get("days", 1) or 1
    num_candidates = len(recommendations)

    # Not enough candidates for the number of days
    if num_candidates < days:
        return {
            "feasible": True,
            "warning": (
                f"可用景点较少（{num_candidates}个），{days}天行程可能不够充实。"
                f"建议缩短天数或扩大兴趣范围。"
            ),
            "severity": "warning",
        }

    # Way too many places requested per day
    user_tags = profile.get("tags", []) or []
    if days == 1 and num_candidates > MAX_PLACES_PER_DAY:
        # Check if user explicitly asked for excessive coverage
        return {
            "feasible": True,
            "warning": (
                f"一天内逛完 {num_candidates} 个景点不太现实，"
                f"行程将精选 {MAX_PLACES_PER_DAY} 个核心景点。"
            ),
            "severity": "warning",
        }

    return {"feasible": True, "warning": None, "severity": "info"}


# ── Tolerant JSON parsing ────────────────────────────────

def _extract_first_json_object(text: str) -> Optional[str]:
    """Extract the first balanced {...} block, respecting strings/escapes."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_json_tolerant(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON, falling back to the first balanced object on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    candidate = _extract_first_json_object(text)
    if candidate and candidate != text:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return None


# ── LLM client ───────────────────────────────────────────

async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    tool_schema: Dict[str, Any],
    tool_description: str,
) -> Optional[Dict[str, Any]]:
    """Single structured LLM call → tolerant-parsed JSON dict or None."""
    provider = await get_llm_provider()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        result = await provider.chat_structured(
            messages=messages,
            output_schema=tool_schema,
            temperature=0.5,
        )
        return result or None
    except Exception:
        return None


# ── Knowledge-base cache (for price enrichment) ────────────

_kb_attractions_cache: Optional[List[Dict[str, Any]]] = None


async def _get_kb_attractions() -> List[Dict[str, Any]]:
    """Load attractions from the data file (cached at module level)."""
    global _kb_attractions_cache
    if _kb_attractions_cache is None:
        from pathlib import Path
        data_path = Path(__file__).parent.parent.parent / "data" / "attractions.json"
        data = await asyncio.to_thread(lambda: json.loads(data_path.read_text("utf-8")))
        _kb_attractions_cache = data.get("attractions", [])
        logger.info(f"Loaded {len(_kb_attractions_cache)} attractions for price enrichment")
    return _kb_attractions_cache


# ── Prompt building ──────────────────────────────────────

def _format_places(places: List[Dict[str, Any]], limit: int = 15) -> str:
    """Render the ranked candidate list for the prompt.

    Phase 12.13: Mark KB-verified POIs with a ✓ so the LLM knows which
    names are system-verified and should be used verbatim.
    """
    lines = []
    for i, p in enumerate(places[:limit]):
        name = p.get("name", p.get("metadata", {}).get("name", f"景点{i+1}"))
        score = p.get("total_score", p.get("relevance_score", 0))
        tags_p = p.get("tags", []) or p.get("metadata", {}).get("tags", "")
        if isinstance(tags_p, str):
            tags_p = [t.strip() for t in tags_p.split(",") if t.strip()]
        suitable = p.get("suitable_for", "") or p.get("metadata", {}).get("suitable_for", "")
        best_time = p.get("best_time", "") or p.get("metadata", {}).get("best_time", "")

        # Phase 7: Use real price_range when available, fall back to price_level
        pr = p.get("price_range") or p.get("metadata", {}).get("price_range") or {}
        if isinstance(pr, dict) and (pr.get("max", 0) > 0 or pr.get("min", 0) > 0):
            if pr.get("min") == pr.get("max"):
                price = f"¥{pr['min']}"
            else:
                price = f"¥{pr.get('min', 0)}-{pr.get('max', 0)}"
        elif isinstance(pr, dict) and pr.get("max", 0) == 0 and pr.get("min", 0) == 0:
            price = "免费"
        else:
            # Fallback to legacy price_level label
            price = p.get("price_level", "") or p.get("metadata", {}).get("price_level", "")

        # Phase 12.13: KB-verified marker
        kb_verified = "✓" if (p.get("kb_verified") or p.get("metadata", {}).get("kb_verified") or name) else ""

        # Phase 12.15: Indoor/outdoor marker from tags or name
        classification = classify_poi_indoor(name, kb_tags=tags_p if isinstance(tags_p, list) else None)
        io_marker = {"indoor": "🏠室内", "semi": "🏛 semi", "outdoor": "☀️户外"}.get(classification, "")

        lines.append(
            f"{i + 1}. ✓ {name} [{io_marker}] "
            f"(标签: {', '.join(tags_p[:5])}; 适合: {suitable}; "
            f"最佳时间: {best_time}; 门票: {price}; 推荐分: {score:.2f})"
        )
    return "\n".join(lines)


def _format_weather(weather: Optional[Dict[str, Any]]) -> str:
    """Render the daily forecast block for weather-adaptive scheduling."""
    if not weather:
        return ""
    daily = weather.get("daily") or []
    if not daily:
        return ""
    lines = []
    has_high_temp = False
    has_rain = False
    for d in daily[:7]:
        tmax = d.get('temp_max', 30)
        tmin = d.get('temp_min', 20)
        precip = d.get('precipitation', 0)
        desc = d.get('weather_desc', '')
        # Phase 12.17: mark rainy days with 🌧️ so the LLM maps date→rain
        is_rainy = precip > 0.5 or any(w in desc for w in ["雨", "雷", "雪", "雹"])
        lines.append(
            f"- {d.get('date')}: {desc}, "
            f"{tmin}~{tmax}°C, "
            f"降水 {precip}mm" + (" 🌧️" if is_rainy else "")
        )
        if tmax >= 35:
            has_high_temp = True
        if precip > 5 or any(w in desc for w in ["雨", "雷", "暴雨", "阵雨"]):
            has_rain = True

    header = "\n【逐日天气】"
    constraints = []
    if has_high_temp and has_rain:
        constraints.append(
            "⚠️ 高温+降雨双重预警：白天户外活动必须安排在 10:00 前或 17:00 后，"
            "午后时段（12:00-16:00）严格安排室内/半室内项目（博物馆、商场、茶馆等），"
            "每个降雨日至少 2 个室内项目；户外项目数 ≤ 室内项目数 + 1；"
            "所有户外项目必须注明避暑措施（遮阳、饮水、空调休息点）"
        )
    elif has_high_temp:
        constraints.append(
            "⚠️ 高温预警（≥35°C）：户外活动限早晨/傍晚，午后强制安排室内项目，"
            "每天至少 2 个室内避暑场所（博物馆/购物中心/茶馆/咖啡馆/美食街）"
        )
    elif has_rain:
        constraints.append(
            "🌧️ 降雨日室内配额：每个降雨日至少安排 2 个室内/半室内项目"
            "（博物馆、购物中心、茶馆、美食街、餐厅等），"
            "户外项目数 ≤ 室内项目数 + 1。晴朗日优先户外与日出日落机位"
        )
    else:
        constraints.append(
            "晴朗日优先户外与日出日落机位"
        )

    return header + "（" + "；".join(constraints) + "）\n" + "\n".join(lines)


def _format_rainy_days(weather: Optional[Dict[str, Any]], days: int) -> str:
    """Phase 12.17: Explicit day-number → rain mapping.

    The LLM tends to treat rain constraints as an abstract quota and still
    schedules famous outdoor landmarks on rainy days. Naming the exact
    rainy day numbers makes the constraint concrete and actionable.
    """
    if not weather:
        return ""
    daily = weather.get("daily") or []
    rainy = []
    has_severe = False
    for i, d in enumerate(daily[: max(days, 1)]):
        desc = d.get("weather_desc", "") or ""
        precip = d.get("precipitation") or 0
        if any(w in desc for w in ("雨", "雷", "雪", "雹")) or precip > 0.5:
            if any(w in desc for w in ("雷", "雹")):
                has_severe = True
                rainy.append(f"第 {i + 1} 天（{d.get('date')}，{desc}）⚠️恶劣天气")
            else:
                rainy.append(f"第 {i + 1} 天（{d.get('date')}，{desc}）")
    if not rainy:
        return ""
    severe_rule = (
        "⚠️ 标注恶劣天气（雷暴/冰雹）的当天，items 必须 100% 为室内/半室内项目，"
        "一个户外项目都不允许（雷雨天户外活动有安全风险）；"
        if has_severe else ""
    )
    return (
        "\n【逐日降雨警示 — 必须遵守】"
        + "、".join(rainy)
        + " 预报有雨。"
        + severe_rule
        + "普通降雨日 items 以 🏠室内/🏛 semi 项目为主，户外项目不得多于 1 个。"
    )


_QUALITY_REQUIREMENTS = """【规划要求】
0.【POI 名称优先规则】推荐列表中带「✓」标记的景点名称已经过系统验证，
   请优先使用其准确的完整名称作为 items[].poi。如需使用不在列表中的景点，
   请从「更多已验证景点」中选取。不要随意修改已验证景点的名称。
   【poi 必须是真实场所】items[].poi 只能是真实存在的场所名称（景区、博物馆、
   商场、餐厅、街区等），禁止把菜品名（如「过桥米线」）、小吃名、活动名当作 poi；
   餐饮体验要么用推荐列表中的真实餐厅名，要么写入 eat「每日一味」，不要塞进 items。
1. 每天必须有明确区域主题：theme 写「DAY n · 区域名」（如「DAY 1 · 老城厢」），title 写当天主目的地
2. 同一天内的地点在地理上必须顺路，避免来回折返
3. 每天条目数按用户节奏分档：休闲/慢节奏 2-4 个（留白午休与机动时间），适中 3-5 个，
   紧凑/特种兵 4-6 个；time 用 24 小时制 HH:MM；note 必须是一句"为什么这个时间点去"的理由
   （人少/光线/场次/闭馆时间/预约时段等），禁止泛泛而谈
4. 需要提前预约购票的项目，必须在 poi 或 note 里写清（如「需提前在官方公众号预约」）
5. eat 写"每日一味"：具体餐厅 + 招牌菜（如「豫园『南翔馒头店』蟹粉小笼」）
6. budget 按 餐饮/门票/交通/购物 等分类输出 amount（元，整数），各项加总必须等于人均总预算，
   并在 stats 中给出「人均预算」一项；不需要输出 percent（后端计算）
7. checklist 给 3-12 条行前准备（实名证件/预约票/必备 App/装备），done 一律 false
8. tips 给 2-6 条实用提示，必须具体可执行（写清 App 名、价格、时间），禁止空泛建议
9. stats 给 2-6 项概览统计（天数/人均预算/预计日均步数等由你估算；
   地点数由系统统计，你填的数值会被后端覆盖为真实值）
10. 行程张弛有度；有老人小孩同行时控制步行强度
11.【天气自适应】高温日（≥35°C）午后 12:00-16:00 禁止排户外景点，每个高温日至少 2 个室内项目；
   降雨/雷暴日：户外项目数不得超过室内项目数（户外 ≤ 室内），每个降雨日至少 2 个室内/半室内项目；
   知名户外地标（山岳/湖泊/公园/岛屿类）在降雨日必须让位于室内替代项，不得因名气大而保留；
   tips 中必须包含当季天气应对建议（遮阳/雨具/室内备选方案）
12.【POI名称不可重复】不同天之间不得出现相同的poi名称。每个景点在全行程中只出现一次。
13.【标签大类多样性】景点应覆盖至少3个不同标签大类（自然/人文/美食/购物/娱乐/运动/艺术）。
14.【极端预算场景】预算极低时优先免费景点和路边摊，一天中至少一半以上免费活动。
15.【矛盾需求处理】有矛盾需求时优先安全可行性，tips中说明可能无法全部满足。
16.【特殊人群】老人/小孩/孕妇：无剧烈运动、少阶梯、有空调、近医疗设施。
17.【极寒/极热】冬季极寒户外不超60分钟；夏季酷暑午后仅排室内项目。
18.【到达日安排】如果用户提供到达时间，当天从到达时间开始安排：到达前写[行]出发/到达/办入住/休整；下午轻松活动不超过3个。凌晨/深夜到达(23-06点)当天只安排到达休息。长途旅行后第一个半天安排轻松活动。必须包含入住酒店环节。
19.【离开日安排】如果用户提供离开时间：活动在离开前2-3小时结束，最后写[行]前往机场/车站。轻量活动不超过3个，包含退房/寄存行李环节。
20.【三餐规则】每顿餐作为独立行程项，写真实餐厅名：早饭07-09点，午饭11:30-13:00，晚饭17:30-19:00。每餐写1-2道推荐菜。
21.【体力节奏】用户精力有限：每天最多4-6个活动(不含三餐休息)。每2-3活动后安排一段休息/自由活动。夏季12-15点安排1-2小时午休。剧烈活动(爬山/徒步)后有休息缓冲。
22.【项目类型标注】每个item的note开头标注类型标记：
   [景]景点游览 [吃]用餐/美食
   [休]休息/自由活动/午休
   [行]交通：飞机/高铁/火车/公交/自驾/打车（具体写明工具，如"[行]高铁前往成都"）
   [住]住宿：酒店/民宿/青旅（具体写明类型，如"[住]入住解放碑附近酒店"或"[住]住进特色民宿"）
   [到]到达/出发（如"[到]抵达重庆江北机场"）
23.【指定地点排入】用户提到的must_visit地方必须排进行程(如洪崖洞/解放碑)，放在最顺路的天和时间段，以[景]类型出现。
"""


# ── KB-aware POI catalog ──────────────────────────────────
# Phase 12.13: Build a compact catalog of KB-verified POI names for the
# target city, so the LLM can pick exact KB names instead of fabricating.

# Tag categorization for grouping KB POIs in the catalog
_TAG_CATEGORIES: Dict[str, str] = {
    "museum": "博物馆/展馆",
    "history": "历史遗迹",
    "temple": "寺庙/宗教",
    "park": "公园/自然",
    "nature": "自然风光",
    "mountain": "山岳",
    "lake": "湖泊/水域",
    "beach": "海滩/海岸",
    "garden": "园林/花园",
    "architecture": "建筑/街区",
    "landmark": "地标",
    "cultural": "文化/民俗",
    "shopping": "购物/商业",
    "food": "美食/餐饮",
    "hotel": "住宿",
    "entertainment": "娱乐",
    "art": "艺术/创意",
    "sport": "运动/户外",
    "science": "科技",
    "sightseeing": "观光",
    "hot_spring": "温泉",
    "island": "海岛",
}


def _classify_poi_tags(tags: List[str]) -> str:
    """Map POI tags to a simplified category for catalog grouping."""
    tags_lower = [t.lower() for t in tags]
    for key, label in _TAG_CATEGORIES.items():
        if any(key in t for t in tags_lower):
            return label
    # Check Chinese tags
    for t in tags:
        if any(kw in t for kw in ["寺", "庙", "宫", "殿", "塔", "教堂", "清真"]):
            return "寺庙/宗教"
        if any(kw in t for kw in ["园", "林", "植物", "花卉"]):
            return "园林/花园"
        if any(kw in t for kw in ["山", "峰", "岭", "岩"]):
            return "山岳"
        if any(kw in t for kw in ["湖", "河", "江", "海", "滩", "湾", "岛", "溪", "泉", "瀑"]):
            return "自然风光"
        if any(kw in t for kw in ["博", "纪念", "故居", "旧址", "遗址"]):
            return "博物馆/展馆"
        if any(kw in t for kw in ["街", "巷", "胡同", "广场", "建筑"]):
            return "建筑/街区"
        if any(kw in t for kw in ["吃", "美食", "餐厅", "火锅", "面", "茶", "咖啡"]):
            return "美食/餐饮"
        if any(kw in t for kw in ["购", "商场", "市场", "夜市"]):
            return "购物/商业"
    return "其他景点"


async def _build_kb_catalog(
    city: str,
    places: List[Dict[str, Any]],
) -> str:
    """Build a COMPACT KB-verified POI name hint for the target city.

    Phase 12.13 v2: Lighter approach — just a comma-separated name list
    of additional KB POIs (not already in the recommendation list), capped
    at ~500 chars. The goal is name awareness without overwhelming the LLM.

    Returns a compact line like:
        【更多{城市}已验证景点】name1, name2, name3, ...
    """
    # Collect names already in the recommendation list
    rec_names: Set[str] = set()
    for p in places:
        name = p.get("name", "") or p.get("metadata", {}).get("name", "")
        if name:
            rec_names.add(name)
            # Also add core name for dedup
            core = normalize_poi_name(name)
            if core and core != name:
                rec_names.add(core)

    # Collect additional KB POIs in the same city (not already in rec_names)
    extra_names: List[str] = []
    try:
        kb_all = await _get_kb_attractions()
        for a in kb_all:
            if a.get("city", "") != city:
                continue
            name = a.get("name", "")
            if not name or name in rec_names:
                continue
            core = normalize_poi_name(name)
            if core in rec_names:
                continue
            extra_names.append(name)
            rec_names.add(name)
            rec_names.add(core)
    except Exception:
        pass

    if not extra_names:
        return ""

    # Build compact comma-separated list, cap at ~500 chars
    lines = [f"【更多{city}已验证景点（供参考选用）】"]
    current_line = ""
    for name in extra_names:
        segment = f"、{name}"
        if len(current_line) + len(segment) > 120:
            lines.append(current_line)
            current_line = name
        else:
            current_line = current_line + segment if current_line else name
        if sum(len(l) for l in lines) + len(current_line) > 500:
            remaining = len(extra_names) - extra_names.index(name) - 1
            if remaining > 0:
                current_line += f" …等{remaining}个"
            break
    if current_line:
        lines.append(current_line)

    return "\n".join(lines)


def _build_extreme_guidance(
    profile: Dict[str, Any],
    places: List[Dict[str, Any]],
    days: int,
) -> str:
    """Phase 12.10: Build prompt guidance blocks for extreme/edge scenarios.

    Detects: non-standard destinations, large groups, extreme budget,
    self-drive/motorcycle trips, and POI-constrained (niche/low-coverage) cases.
    """
    blocks: List[str] = []

    # 1. Non-standard destination (e.g., 川西, 漠河, 川藏线)
    orig_dest = profile.get("original_destination", "")
    dest = profile.get("destination", "")
    if orig_dest and orig_dest != dest:
        blocks.append(
            f"\n【区域适配】用户原始目的地为「{orig_dest}」，系统以「{dest}」"
            f"作为最近的中心城市进行规划。请在 trip.title 和 trip.description 中"
            f"体现「{orig_dest}」而非「{dest}」，tips 中应包含该区域的旅行注意事项"
            f"（如高原反应、长途交通、边防证等）。行程中每天的 theme 和 items 应"
            f"聚焦「{orig_dest}」的实际景点和体验。"
        )

    # 2. Large group (10+ people)
    companions = profile.get("companions", "")
    constraints_text = str(profile.get("constraints", ""))
    if any(k in companions or k in constraints_text for k in ("团队", "团建", "集体")):
        blocks.append(
            "\n【大团出行】团队出行需注意：① 每天安排不超过 3 个主要景点，"
            "留出集合/转场时间；② 优先选择有团体接待能力的场所（大餐厅、大景区）；"
            "③ tips 中应包含团队协调建议（集合时间、分组行动等）；"
            "④ checklist 中应包含团队物资（对讲机、急救包、点名表等）。"
        )

    # 3. Extreme budget (≤500元 total)
    budget = profile.get("budget_level", "") or ""
    if "500" in constraints_text or "极度有限" in constraints_text or "穷游" in constraints_text:
        blocks.append(
            "\n【极简预算】用户预算极度有限——① 每天优先安排免费/低票价景点"
            "（公园、老街、免费博物馆、大学校园）；② 餐饮推荐平价小吃而非正餐餐厅；"
            "③ 交通优先步行+公共交通，避免打车/包车；"
            "④ budget.breakdown 中住宿控制在 50-80 元/晚（青旅/民宿床位），"
            "餐饮每天控制在 30-50 元；⑤ tips 中提供省钱攻略（如学生证优惠、"
            "免费日、公交卡等）。"
        )

    # 4. Self-drive / motorcycle trip
    user_input_lower = ""
    # Try to get raw input from constraints or tags
    for tag in profile.get("tags", []):
        user_input_lower += tag + " "
    user_input_lower += constraints_text
    if any(kw in user_input_lower for kw in ("自驾", "摩托车", "骑行", "摩旅", "房车")):
        blocks.append(
            "\n【自驾/摩托车旅行】这是一次公路旅行——① 每天的行程应沿路线方向"
            "线性推进，避免折返；② items 中应包括途中的加油站/休息区/观景台；"
            "③ tips 中必须包含路况提醒、天气对驾驶的影响、备选路线建议；"
            "④ checklist 中应包含车辆装备（备胎、修车工具、防晒、头盔等）；"
            "⑤ 每天驾驶距离建议控制在 200-400km 以内。"
        )

    # 5. POI-constrained (niche preferences, low coverage)
    num_places = len(places)
    if num_places < days * 3:
        blocks.append(
            f"\n【景点有限】当前可用推荐景点仅 {num_places} 个（{days} 天行程），"
            f"少于理想的每天 3 个。请：① 每天安排 2-3 个景点即可，注重深度体验"
            f"而非数量；② 为每天补充 1-2 个自由探索/休闲时段（逛老街、品茶、"
            f"夜市等无需具体POI的体验）；③ tips 中坦诚说明该目的地景点密度较低，"
            f"建议慢节奏深度游。"
        )

    # 6. Niche/小众 preference
    if "小众" in str(profile.get("tags", [])):
        blocks.append(
            "\n【小众偏好】用户偏好避开人群的小众体验——① 优先选取推荐列表中"
            "评论数较少或非头部的景点（这些往往更小众）；② 每天可安排 1 个"
            "「隐藏玩法」（如本地人才知道的观景点、小众咖啡馆、独立书店）；"
            "③ tips 中提供错峰建议（工作日、清晨/傍晚等低客流时段）。"
        )

    return "".join(blocks)


async def _build_planning_prompt(
    profile: Dict[str, Any],
    places: List[Dict[str, Any]],
    weather: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the user prompt for full-itinerary generation."""
    dest = profile.get("destination", "未知城市")
    days = profile.get("days", 3)
    budget = profile.get("budget_level", "") or profile.get("budget", "") or "中等"
    tags = profile.get("tags", []) or []
    companions = profile.get("companions", "") or "独自"
    style = profile.get("travel_style", "") or "休闲"
    constraints = profile.get("constraints", "") or "无特殊要求"

    start = date.today()
    end = start + timedelta(days=max(days - 1, 0))
    month = start.month
    season = season_of(month)
    date_block = (
        f"【行程日期与季节】{start.month}月{start.day}日 至 {end.month}月{end.day}日"
        f"（{month}月 · {season}）。tips、checklist、note 中凡涉及月份/季节的表述"
        f"必须与实际月份（{month}月）和{season}一致，禁止出现其他月份。"
    )

    # 同行人为父母/长辈时，主题命名避免「亲子」（亲子=带孩子）
    companions_text = f"{companions} {constraints}"
    naming_block = ""
    if any(k in companions_text for k in ("父母", "老人", "长辈", "爸妈")) or companions == "家庭":
        naming_block = (
            "\n【主题命名】同行人为父母/长辈：每日 theme 命名用「家庭休闲」「慢游」"
            "等风格，禁用「亲子」一词（亲子=带孩子）。"
        )

    rain_block = ""
    if weather and trip_has_rain(weather, days):
        # Phase 12.17: name concrete indoor substitutes from the candidate
        # list so the LLM has actionable options, not just abstract quotas.
        indoor_examples: List[str] = []
        for p in places:
            pname = p.get("name", "") or p.get("metadata", {}).get("name", "")
            if not pname:
                continue
            ptags = p.get("tags", []) or p.get("metadata", {}).get("tags", "")
            if isinstance(ptags, str):
                ptags = [t.strip() for t in ptags.split(",") if t.strip()]
            if classify_poi_indoor(pname, kb_tags=ptags or None) in ("indoor", "semi"):
                indoor_examples.append(pname)
            if len(indoor_examples) >= 6:
                break
        examples_text = (
            f"降雨日请优先从这些室内/半室内项目中选用：{'、'.join(indoor_examples)}。"
            if indoor_examples else ""
        )
        rain_block = (
            "\n【降雨日室内配额 — 必须遵守】预报有降雨："
            "① 每个降雨日至少安排 2 个室内/半室内项目（博物馆、购物中心、茶馆、美食街、餐厅等）；"
            "② 降雨日户外项目数必须 ≤ 室内项目数；"
            "③ 推荐列表中 ☀️户外 标记的知名地标（山岳/湖泊/公园/岛屿类）不得安排在降雨日，"
            "应移至晴朗日；行程全部为雨日时用室内替代项；"
            f"{examples_text}"
            "④ tips 至少 1 条与雨天/天气相关；"
            "⑤ checklist 至少 1 件天气相关物品（如折叠伞，写明实际月份）。"
        )

    # Phase 12.17: explicit day-number → rain mapping
    rain_days_block = _format_rainy_days(weather, days) if weather else ""

    # Phase 12.17 v3: verified indoor substitutes from the KB for this city.
    # Without real names at hand the LLM invents plausible-sounding venues
    # (poi_verified 回退的根因)；给它一份已验证清单直接选用。
    kb_indoor_block = ""
    if weather and trip_has_rain(weather, days):
        try:
            kb_all = await _get_kb_attractions()
            kb_indoor = []
            for a in kb_all:
                if a.get("city") == dest and classify_poi_indoor(a.get("name", ""), kb_tags=a.get("tags") or None) in ("indoor", "semi"):
                    kb_indoor.append(a)
            kb_indoor.sort(key=lambda x: x.get("popularity_score", 0), reverse=True)
            kb_names = [a["name"] for a in kb_indoor[:12] if a.get("name")]
            if kb_names:
                kb_indoor_block = (
                    "\n【雨天室内备选 — 全部经系统验证，降雨日优先从中选用】"
                    + "、".join(kb_names)
                )
        except Exception:
            kb_indoor_block = ""

    # Phase 12: Summer heat safety block (June-September)
    summer_block = ""
    if month in (6, 7, 8, 9):
        summer_block = (
            "\n【夏季高温安全约束】当前为{month}月盛夏——"
            "① 每天 12:00-16:00 时段禁止安排户外景点（如登山、广场、露天景区），"
            "必须替换为室内/半室内项目（博物馆、美术馆、商场、茶馆、餐厅）；"
            "② 户外项目只能安排在 08:00-11:00 或 17:00-19:00；"
            "③ 每天至少安排 2 个室内避暑休憩点（其中至少 1 个有空调）；"
            "④ tips 中必须包含高温避暑建议（遮阳帽、饮用水、藿香正气水等）；"
            "⑤ 若当天同时有降雨，室内项目数必须 ≥ 户外项目数。"
        ).format(month=month)

    # Phase 12.10: Extreme/edge scenario guidance blocks
    extreme_blocks = _build_extreme_guidance(profile, places, days)

    # Phase 14: Time-aware blocks (arrival/departure/must_visit)
    time_blocks = ""
    must_visit = profile.get("must_visit", []) or []
    if must_visit:
        time_blocks += f"\n【用户指定要去的地方（必须排进行程）】{'、'.join(must_visit)}"
    arrival = profile.get("arrival_time", "") or ""
    if arrival:
        time_blocks += f"\n【到达时间】{arrival}——那天从到达时间开始安排"
    departure = profile.get("departure_time", "") or ""
    if departure:
        time_blocks += f"\n【离开时间】{departure}——那天在离开时间前结束活动"
    if time_blocks:
        time_blocks += "\n"

    # Phase 12.13: KB-aware POI catalog — all verified names the LLM can use
    kb_catalog = await _build_kb_catalog(dest, places)

    return f"""请为以下旅行需求生成一份详细的 {days} 日行程规划（严格按 output 函数的 JSON 结构）：

【目的地】{dest}
【天数】{days} 天
【预算】{budget}
【同行人员】{companions}
【兴趣标签】{', '.join(tags) if tags else '不限'}
【旅行风格】{style}
【特殊要求】{constraints}

{date_block}{rain_block}{rain_days_block}{kb_indoor_block}{naming_block}{summer_block}{extreme_blocks}{time_blocks}

{kb_catalog}

【推荐景点 — 带 ✓ 的经系统验证，请优先选用其准确名称】
{_format_places(places)}
{_format_weather(weather)}

{_QUALITY_REQUIREMENTS}"""


_SYSTEM_PROMPT_FULL = """你是 TravelMind 高级旅行规划师。根据用户需求、推荐景点（带 ✓ 标记的经系统验证）和天气，
生成严格符合 output 函数 JSON 结构的行程。

【POI 名称规范】
推荐列表中带「✓」的景点名称已经过系统验证，请优先使用其准确名称作为 items[].poi。
如果某个你熟知的热门景点未出现在推荐列表中，说明系统暂未收录该景点数据，
请从推荐列表或「更多已验证景点」中选取最接近的替代。
eat（每日一味）可使用真实存在的餐厅名，不受此限制。

你必须调用 'output' 函数返回结构化结果，不要返回纯文本。"""


def _normalize_nested_json(data: Any) -> Any:
    """LLM 偶发把顶层字段（trip/days/budget/checklist/tips）输出成
    JSON 字符串而非对象——先把这些内嵌序列化展开，再走校验。"""
    if not isinstance(data, dict):
        return data
    for key in ("trip", "days", "budget", "checklist", "tips", "items"):
        val = data.get(key)
        if isinstance(val, str):
            try:
                data[key] = json.loads(val)
            except json.JSONDecodeError:
                pass
    return data


def _unwrap_tool_envelope(data: Any) -> Any:
    """模型偶发回显整个工具定义（{"name": "output", "parameters": {...}}）
    或 arguments 字符串——剥掉信封取真正的行程对象。"""
    if not isinstance(data, dict):
        return data
    if isinstance(data.get("parameters"), dict):
        data = data["parameters"]
    elif isinstance(data.get("parameters"), str):
        try:
            data = json.loads(data["parameters"])
        except json.JSONDecodeError:
            pass
    elif isinstance(data.get("arguments"), (dict, str)):
        args = data["arguments"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass
        if isinstance(args, dict):
            data = args
    return data


# ── Validation helper ────────────────────────────────────

def _full_validate(
    data: Dict[str, Any],
    trip_month: int,
    weather: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Pre-injection validation: LLM-facing schema (percent not yet present)
    + day continuity + budget-sum + month/season + weather coverage."""
    errors = validate_pre_injection(data)
    errors += validate_day_continuity(data)
    if budget_sum_mismatch(data):
        total = sum(b.get("amount", 0) for b in data.get("budget", []))
        errors.append(
            f"budget 加总({total}) 与 stats 人均预算偏差超过容忍度"
        )
    errors += month_inconsistency_errors(data, trip_month)
    if weather and trip_has_rain(weather, len(data.get("days", []))):
        errors += weather_coverage_errors(data)
    return errors


# ── Public API ───────────────────────────────────────────

async def generate_itinerary(
    profile: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
    weather: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a contract-valid itinerary from ranked recommendations.

    Returns:
        Contract-valid itinerary dict (with backend-injected fields),
        or {} on failure (after MAX_RETRIES retries).
    """
    if not recommendations:
        logger.warning("No recommendations to plan — returning empty itinerary")
        return {}

    if not settings.DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not configured — cannot generate itinerary")
        return {}

    # Phase 8.1: Feasibility check — warn if request is unrealistic
    feasibility = _check_feasibility(profile, recommendations)
    if feasibility.get("warning"):
        logger.warning(f"Feasibility warning: {feasibility['warning']}")

    days = profile.get("days", 3)
    trip_month = date.today().month
    top_n = min(len(recommendations), 30)
    places = recommendations[:top_n]
    prompt = await _build_planning_prompt(profile, places, weather)
    tool_schema = schema_for_llm()

    last_error: Any = None
    for attempt in range(MAX_RETRIES + 1):
        logger.info(
            f"Planning itinerary: {days}d from {len(places)} places"
            + (f" (attempt {attempt + 1})" if attempt else "")
        )
        cur_prompt = prompt + ("\n[Prev error: " + str(last_error)[:200] + "]" if attempt > 0 and last_error else "")
        try:
            data = await _call_llm(
                _SYSTEM_PROMPT_FULL, cur_prompt, tool_schema,
                f"Return the {days}-day itinerary as structured JSON.",
            )
            if not data:
                last_error = "empty/unparseable LLM response"
                logger.warning(f"Planning attempt {attempt + 1}: {last_error}")
                continue

            data = _normalize_nested_json(_unwrap_tool_envelope(data))
            errors = _full_validate(data, trip_month, weather)
            if errors:
                last_error = "; ".join(str(e)[:100] for e in errors[:3])
                logger.warning(
                    f"Planning attempt {attempt + 1}: {len(errors)} validation errors — "
                    f"first: {errors[0][:120]}"
                )
                continue

            # Phase 12.27: 节奏分档密度兜底（在路线优化前截断，保证统计一致）
            try:
                enforce_pace_density(data, profile.get("travel_style", "") or "")
            except Exception as e:
                logger.warning(f"Pace density enforcement failed (non-fatal): {e}")

            # B 阶段后处理：POI 存续 / 区域归属 / 顺路重排（非致命失败）
            route_report: Dict[str, Any] = {}
            try:
                data, route_report = await optimize_itinerary(
                    data, profile.get("destination", ""), weather=weather
                )
            except Exception as e:
                logger.warning(f"Route optimization failed (non-fatal): {e}")

            # Phase 12.17 v5: 恶劣天气确定性室内替换（雷暴/冰雹日户外→KB 室内）
            try:
                enforce_severe_weather_indoor(data, weather, await _get_kb_attractions())
            except Exception as e:
                logger.warning(f"Severe-weather guard failed (non-fatal): {e}")

            # Phase 12.27: 按天挂载 KB 真实餐厅与住宿（"吃住都没有推荐"修复）
            try:
                attach_daily_dining_and_stay(
                    data, await _get_kb_attractions(), profile.get("destination", "")
                )
            except Exception as e:
                logger.warning(f"Dining/stay attach failed (non-fatal): {e}")

            # Phase 7: Price enrichment from knowledge base (non-LLM, best-effort)
            try:
                from app.services.price_enricher import enrich_prices
                kb_attractions = await _get_kb_attractions()
                user_budget = profile.get("budget_level", "") or profile.get("budget", "")
                enrich_prices(data, kb_attractions, user_budget=user_budget)
            except Exception as e:
                logger.warning(f"Price enrichment failed (non-fatal): {e}")

            inject_computed_fields(data)

            # 校验报告：路线核实结论 + 天气匹配度（Phase 1 可视化）
            if route_report:
                # Phase 12.15: Pass KB for tag-based indoor classification
                kb_attrs = await _get_kb_attractions()
                fit, weather_notes = compute_weather_fit(data, weather, kb_attractions=kb_attrs)
                route_report["weather_fit"] = fit
                route_report["weather_notes"] = weather_notes
                data["validation_report"] = route_report

            # Post-injection sanity (percent/daysCount now present)
            errors = validate_itinerary(data) + validate_day_continuity(data)
            if errors:
                last_error = {"post_injection_errors": errors[:5]}
                logger.warning(
                    f"Planning attempt {attempt + 1}: post-injection errors — "
                    f"first: {errors[0][:150]}"
                )
                continue

            logger.info(
                f"Itinerary generated & validated: {data['trip']['daysCount']} days, "
                f"{sum(len(d['items']) for d in data['days'])} items"
            )
            return data

        except Exception as e:
            last_error = e
            logger.warning(f"Itinerary generation error (attempt {attempt + 1}): {e}")

    # Structured failure — orchestrator accumulates this in state["error"]
    logger.error(
        f"Itinerary generation failed after {MAX_RETRIES + 1} attempts: {last_error}"
    )
    return {}


async def regenerate_day(
    itinerary: Dict[str, Any],
    day_index: int,
    feedback: str,
    profile: Dict[str, Any],
    places: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Regenerate a single day based on user feedback; everything else untouched.

    Args:
        itinerary: the current contract-valid itinerary (not mutated).
        day_index: 0-based index into itinerary["days"].
        feedback: user feedback, e.g. "第二天太赶了".
        profile: user profile for context (destination/days/companions...).
        places: candidate attractions for the prompt.

    Returns:
        A NEW itinerary dict with only days[day_index] replaced, fully
        re-validated (contract + day continuity + daysCount).

    Raises:
        ValueError: bad day_index.
        RuntimeError: LLM/validation failed after retries (structured errors
            included in the message for the API layer to surface).
    """
    days = itinerary.get("days", [])
    if not 0 <= day_index < len(days):
        raise ValueError(f"day_index {day_index} 超出范围（共 {len(days)} 天）")

    import copy
    result = copy.deepcopy(itinerary)
    old_day = days[day_index]
    day_no = old_day.get("day", day_index + 1)
    city = (itinerary.get("trip") or {}).get("city", profile.get("destination", ""))

    others = "\n".join(
        f"- DAY {d.get('day')}: {d.get('theme', '')} / {d.get('title', '')}"
        for d in days if d is not old_day
    )
    user_prompt = f"""用户在调整一份 {city} {len(days)} 日行程的第 {day_no} 天，请只重新安排这一天。

【用户反馈】{feedback}

【该天当前安排】
{json.dumps(old_day, ensure_ascii=False)}

【其他天概览（保持不变，注意与它们衔接顺路）】
{others}

【可用景点】（按推荐度排序）
{_format_places(places)}

{_QUALITY_REQUIREMENTS}

只输出这一天的新安排（day 保持为 {day_no}），不要输出其他天。"""

    system_prompt = """你是 TravelMind 高级旅行规划师。只重新生成用户反馈的那一天行程，
严格按 output 函数的 JSON 结构输出单日对象。你必须调用 'output' 函数。"""

    day_schema = schema_for_llm()["properties"]["days"]["items"]

    last_error: Any = None
    for attempt in range(MAX_RETRIES + 1):
        logger.info(f"Regenerating day {day_no} (attempt {attempt + 1}): {feedback[:40]}")
        try:
            new_day = await _call_llm(
                system_prompt, user_prompt, day_schema,
                f"Return the regenerated day {day_no} as structured JSON.",
            )
            if not new_day:
                last_error = "empty/unparseable LLM response"
                continue

            new_day = _normalize_nested_json(_unwrap_tool_envelope(new_day))
            new_day["day"] = day_no  # enforce, model may drift
            errors = validate_day(new_day)
            if errors:
                last_error = {"day_errors": errors[:5]}
                logger.warning(f"Regen attempt {attempt + 1}: {errors[0][:120]}")
                continue

            result["days"][day_index] = new_day
            # Full-itinerary revalidation: contract + day numbering + daysCount
            errors = validate_itinerary(result) + validate_day_continuity(result)
            if errors:
                last_error = {"full_errors": errors[:5]}
                logger.warning(f"Regen attempt {attempt + 1}: full validation failed")
                continue

            logger.info(f"Day {day_no} regenerated & validated")
            return result

        except Exception as e:
            last_error = e
            logger.warning(f"Regen day {day_no} error (attempt {attempt + 1}): {e}")

    raise RuntimeError(
        f"第 {day_no} 天重生成失败（{MAX_RETRIES + 1} 次尝试）: {last_error}"
    )

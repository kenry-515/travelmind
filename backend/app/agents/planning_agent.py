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
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Set

from app.services.llm_json_utils import (
    extract_first_json_object,
    parse_json_tolerant,
    repair_json,
)
from app.services.llm_service import get_llm_provider

from app.agents.itinerary_contract import (
    beautify_and_sanitize_day_items,
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
from app.agents.time_aware_planner import (
    build_enhanced_planning_prompt,
    build_multi_day_time_schedules,
    build_time_aware_hint,
    build_time_slot_prompt_block,
    rerank_places_by_time,
    resolve_time_slot,
)
from app.config.settings import settings
from app.services.name_normalizer import normalize_poi_name

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # 2 retries → 3 attempts total; then structured failure
MAX_RETRIES_LONG = 4  # More retries for long itineraries (>=4 days)

# Phase 8.1: Feasibility thresholds
MAX_PLACES_PER_DAY = 8  # Warn if more than 8 visit items per day
LONG_ITINERARY_THRESHOLD = 4  # Days threshold for "long itinerary" special handling


# ── JSON Repair Utilities (Phase 14.1 → 16.6 提取为共享模块) ──
# 实现已迁移到 app.services.llm_json_utils，此处保留向后兼容别名，
# 供已有测试与外部引用继续可用。新代码请直接从 llm_json_utils 导入。
_repair_json = repair_json


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


# ── Tolerant JSON parsing (Phase 16.6: 提取为共享模块) ────
# 向后兼容别名；实现见 app.services.llm_json_utils
_extract_first_json_object = extract_first_json_object
_parse_json_tolerant = parse_json_tolerant


# ── LLM client ───────────────────────────────────────────

async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    tool_schema: Dict[str, Any],
    tool_description: str,
    temperature: float = 0.3,
    max_tokens: int = 3000,
) -> Optional[Dict[str, Any]]:
    """Single structured LLM call → tolerant-parsed JSON dict or None.
    
    Phase 14.1: Added fallback to chat + JSON repair when structured output fails.
    Phase 15.2: Added temperature parameter for stability control.
    """
    provider = await get_llm_provider()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    # 1. Try structured output first (preferred)
    try:
        result = await provider.chat_structured(
            messages=messages,
            output_schema=tool_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if result and isinstance(result, dict):
            return result
        logger.debug("Structured output returned non-dict or None, falling back to text + repair")
    except Exception as e:
        logger.debug(f"Structured output failed: {e}, falling back to text + repair")
    
    # 2. Fallback: try plain text + JSON repair
    try:
        # Add explicit instruction to return valid JSON
        repair_instruction = (
            "IMPORTANT: Return ONLY the raw JSON object, no markdown, no explanation, no code fences. "
            "The JSON must be valid and match the required schema."
        )
        enhanced_user_prompt = f"{user_prompt}\n\n{repair_instruction}"
        
        raw_text = await provider.chat(
            messages=messages,
            system_prompt=None,  # system prompt is already in messages
            temperature=temperature,
        )
        
        if not raw_text:
            logger.warning("Fallback chat returned empty response")
            return None
        
        repaired = _repair_json(raw_text)
        if repaired and isinstance(repaired, dict):
            logger.info("Successfully repaired JSON from text output")
            return repaired
        
        logger.warning("JSON repair failed on fallback text")
        return None
        
    except Exception as e:
        logger.error(f"Fallback chat + repair failed: {e}")
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
            # Fallback to legacy price_level label or truthful notice
            level = p.get("price_level", "") or p.get("metadata", {}).get("price_level", "")
            if level:
                price = level
            else:
                price = "价格待核实"

        # Phase 12.13: KB-verified marker
        kb_verified = p.get("kb_verified") or p.get("metadata", {}).get("kb_verified")
        runtime_verified = p.get("runtime_verified") or p.get("metadata", {}).get("runtime_verified")
        if kb_verified:
            verified_marker = "✓"  # KB-verified
        elif runtime_verified:
            verified_marker = "◆"  # Runtime-verified (lower confidence)
        else:
            verified_marker = "○"  # Unverified

        # Phase 12.15: Indoor/outdoor marker from tags or name
        classification = classify_poi_indoor(name, kb_tags=tags_p if isinstance(tags_p, list) else None)
        io_marker = {"indoor": "🏠室内", "semi": "🏛 semi", "outdoor": "☀️户外"}.get(classification, "")

        lines.append(
            f"{i + 1}. {verified_marker} {name} [{io_marker}] "
            f"(标签: {', '.join(tags_p[:5])}; 适合: {suitable}; "
            f"最佳时间: {best_time}; 门票: {price}; 推荐分: {score:.2f})"
        )
    return "\n".join(lines)


def _format_weather(weather: Optional[Dict[str, Any]]) -> str:
    """Render the daily forecast block for weather-adaptive scheduling.
    
    Handles both dict format and WeatherForecast object format.
    """
    if not weather:
        return ""
    
    # Handle WeatherForecast object
    if hasattr(weather, 'to_dict'):
        weather = weather.to_dict()
    
    daily = weather.get("daily") or []
    if not daily:
        return ""
    lines = []
    has_high_temp = False
    has_rain = False
    for d in daily[:7]:
        if hasattr(d, 'to_dict'):
            d = d.to_dict()
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
    
    Handles both dict format and WeatherForecast object format.
    """
    if not weather:
        return ""
    
    # Handle WeatherForecast object
    if hasattr(weather, 'to_dict'):
        weather = weather.to_dict()
    
    daily = weather.get("daily") or []
    rainy = []
    has_severe = False
    for i, d in enumerate(daily[: max(days, 1)]):
        if hasattr(d, 'to_dict'):
            d = d.to_dict()
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


_QUALITY_REQUIREMENTS = """【规划要求 — 分层约束】

═══ 强制约束层（违反将导致严重质量问题）═══

F1.【时间-内容一致性 — 最优先】每个item的time、poi、note必须严格对应时间段：
   · 07:00-12:00(上午) → 早餐/早茶、博物馆、景点游览、古镇、寺庙、自然公园
     严禁出现：晚餐/夜宵/酒吧/夜市/夜总会等夜间内容
   · 12:00-14:00(中午) → 午餐、短暂休息
   · 14:00-18:00(下午) → 博物馆、美术馆、购物中心、咖啡馆、室内活动
     严禁安排长时间户外暴晒活动(登山/沙漠/徒步)
   · 18:00-22:00(晚上) → 晚餐、夜景、夜市、游轮、酒吧、放松活动
     严禁出现：早餐/早茶/上午景点等日间内容
   · note内容必须与time一致：time=08:00时note不能写"晚餐推荐"

F2.【POI 名称规则】poi必须是真实存在的场所名称（景区/博物馆/商场/餐厅/街区），
   禁止将菜品名、活动名当作poi；餐饮内容写入eat字段
   整个行程中每个POI名称只能出现一次（严禁重复）

F3.【酒店安排】默认全程同一家酒店；仅在以下情况换酒店：
   (a)用户明确要求 (b)跨城市移动 (c)行程中说明原因
   stay字段必须包含具体酒店名称，如"西安钟楼亚朵S酒店"

F4.【三餐规则】每顿餐作为独立行程项，写真实餐厅名和推荐菜：
   早餐07:00-09:00，午餐11:30-13:00，晚餐17:30-19:00

F5.【天气自适应 — 强制】
   · 高温日(≥35°C)午后12:00-16:00禁止户外项目，至少2个室内项目
   · 降雨日：户外项目数≤室内项目数，至少2个室内项目
   · 知名户外地标在降雨日必须让位于室内替代项
   · tips中必须包含当季天气应对建议

F6.【到达/离开日安排】
   · 到达日：从到达时间开始安排，凌晨到达(23-06点)仅安排休息
   · 离开日：活动在离开前2-3小时结束，包含退房/寄存行李

F7.【体力节奏】
   · 每天最多4-6个活动(不含三餐休息)
   · 每2-3个活动后安排休息
   · 夏季12:00-15:00安排1-2小时午休
   · 有老人/小孩同行时减少步行强度

═══ 指导优化层（提升行程质量）═══

G1. 每天有明确区域主题：theme写「DAY n · 区域名」，同一天地点地理顺路
G2. 节奏分档：休闲2-4项，适中3-5项，紧凑4-6项
G3. 需要预约的项目在poi或note里注明
G4. eat字段：每天1-2家推荐餐厅和推荐菜
G5. budget按餐饮/门票/交通/购物分类，加总=人均总预算
G6. checklist: 3-12条目的地专属准备（结合天气/景点/文化特点）
G7. tips: 2-6条具体可执行的实用建议（含App名/价格/时间）
G8. 标签多样性：景点覆盖至少3个不同大类
G9. 特殊人群：老人/小孩/孕妇无剧烈运动、少阶梯
G10. 【项目类型标注】每个item的note开头标注：
    [景]景点 [吃]用餐 [休]休息 [行]交通 [住]住宿 [到]到达/出发
G11. 【精细字段】每个item额外输出：
    · time_slot: 根据time标注(morning/afternoon/evening/night)
    · transportation: 从上一地点到本地点的交通建议
    · estimated_cost: {ticket, transport, total}
G12. 指定地点(must_visit)必须排进最顺路的天和时间段"""


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
    # Normalize weather to dict format (handle WeatherForecast object)
    if weather is not None and hasattr(weather, 'to_dict'):
        weather = weather.to_dict()
    
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

{{_TIME_AWARE_HINT}}

{_QUALITY_REQUIREMENTS}"""


_SYSTEM_PROMPT_FULL = """你是 TravelMind 高级旅行规划师。根据用户需求、推荐景点和天气，
生成严格符合 output 函数 JSON 结构的行程。

【POI 名称规范】
推荐列表中带「✓」的景点名称已经过系统知识库验证，请优先使用其准确名称作为 items[].poi。
带「◆」的景点由实时 API 查询获取，也是真实存在的POI，请使用其名称。
带「○」的景点未经核实，请尽量避免使用。
eat（餐饮推荐）可使用真实存在的餐厅名，不受此限制。

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
    或 arguments 字符串——剥掉信封取真正的行程对象。
    
    Phase 14.1: Extended to handle more wrapper formats like {"stats": {...}}
    and {"output": {...}} from LLM structured output.
    """
    if not isinstance(data, dict):
        return data
    
    # 1. Handle known tool call envelopes
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
    
    # 2. Handle nested wrapper formats ({"stats": {...}}, {"output": {...}}, etc.)
    # The itinerary must have "trip" or "days" key at top level
    if isinstance(data, dict) and "trip" not in data and "days" not in data:
        # Look for a nested dict that contains the itinerary
        for key in ("stats", "output", "result", "data", "plan", "itinerary"):
            if key in data and isinstance(data[key], dict):
                nested = data[key]
                if "trip" in nested or "days" in nested:
                    return nested
    
    return data


# ── Time-content consistency validation ──────────────────────────

# Keywords that should NOT appear in certain time slots
_TIME_CONTENT_RULES: Dict[str, Dict[str, List[str]]] = {
    "morning": {
        "forbidden": ["晚餐", "夜宵", "酒吧", "夜市", "夜总会", "夜店", "深夜", "火锅"],
        "mandatory_hint": "上午时段应安排早餐/早茶、景点游览、博物馆、寺庙、古镇等日间活动",
    },
    "afternoon": {
        "forbidden": ["早餐", "早茶", "夜宵", "夜市", "酒吧"],
        "mandatory_hint": "下午时段应安排博物馆、美术馆、购物中心、咖啡馆等室内活动",
    },
    "evening": {
        "forbidden": ["早餐", "早茶", "晨光", "日出", "上午"],
        "mandatory_hint": "晚上时段应安排晚餐、夜景、夜市、游轮等放松活动",
    },
    "night": {
        "forbidden": ["早餐", "早茶", "日出", "晨练", "上午"],
        "mandatory_hint": "夜间时段应以休息为主",
    },
}


def _infer_time_slot(time_str: str) -> str:
    """Infer time slot from HH:MM string."""
    try:
        parts = time_str.strip().split(":")
        hour = int(parts[0])
    except (ValueError, IndexError):
        return "afternoon"
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "noon"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "evening"
    else:
        return "night"


def _validate_time_content_consistency(data: Dict[str, Any]) -> List[str]:
    """Validate that each item's time matches its content (poi/note).

    Returns a list of error messages for mismatched items.
    """
    errors: List[str] = []
    days = data.get("days", [])
    if not days:
        return errors

    for day_idx, day in enumerate(days, 1):
        items = day.get("items", [])
        for item_idx, item in enumerate(items):
            time_str = item.get("time", "")
            if not time_str:
                continue

            slot = _infer_time_slot(time_str)
            poi = (item.get("poi", "") or "").lower()
            note = (item.get("note", "") or "").lower()
            combined = f"{poi} {note}"

            rules = _TIME_CONTENT_RULES.get(slot, {})
            for kw in rules.get("forbidden", []):
                if kw in combined:
                    errors.append(
                        f"第{day_idx}天第{item_idx + 1}项({time_str}): "
                        f"时间-内容不一致 — {slot}时段出现禁止关键词'{kw}'"
                    )

    return errors


# ── Validation helper ────────────────────────────────────

def _full_validate(
    data: Dict[str, Any],
    trip_month: int,
    weather: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Pre-injection validation: LLM-facing schema (percent not yet present)
    + day continuity + budget-sum + month/season + weather coverage
    + time-content consistency."""
    errors = validate_pre_injection(data)
    errors += validate_day_continuity(data)
    errors += _validate_time_content_consistency(data)
    if budget_sum_mismatch(data):
        total = sum(b.get("amount", 0) for b in data.get("budget", []))
        errors.append(
            f"budget 加总({total}) 与 stats 人均预算偏差超过容忍度"
        )
    errors += month_inconsistency_errors(data, trip_month)
    if weather and trip_has_rain(weather, len(data.get("days", []))):
        errors += weather_coverage_errors(data)
    return errors


def _backfill_empty_days(
    data: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
    min_items_per_day: int = 2,
) -> int:
    """Backfill empty or sparse days with POIs from recommendations.
    
    Phase 14.2: Fixes the "第X天POI过少: 0个" issue by automatically
    adding POIs from the candidate pool to days with insufficient items.
    
    Returns the number of items added.
    """
    days = data.get("days", [])
    if not days:
        return 0
    
    # Extract POI names from recommendations pool
    poi_pool = []
    seen_names = set()
    for rec in recommendations:
        name = rec.get("name", "") or rec.get("metadata", {}).get("name", "")
        if name and name not in seen_names:
            poi_pool.append(rec)
            seen_names.add(name)
    
    if not poi_pool:
        return 0
    
    # Track what's already in the itinerary to avoid duplicates
    existing_poi_names = set()
    for day in days:
        for item in day.get("items", []):
            poi_name = item.get("poi", "") or item.get("name", "")
            if poi_name:
                existing_poi_names.add(poi_name)
    
    added_count = 0
    pool_idx = 0
    
    for day_idx, day in enumerate(days):
        items = day.get("items", [])
        
        # Count actual visit items (exclude "transport" or "meal" types if needed)
        visit_items = [i for i in items if i.get("type") == "attraction" or i.get("poi")]
        current_count = len(visit_items)
        
        if current_count < min_items_per_day:
            needed = min_items_per_day - current_count
            
            while needed > 0 and pool_idx < len(poi_pool):
                rec = poi_pool[pool_idx]
                pool_idx += 1
                
                rec_name = rec.get("name", "") or rec.get("metadata", {}).get("name", "")
                if not rec_name or rec_name in existing_poi_names:
                    continue
                
                # Create a proper item structure
                tags = rec.get("tags", []) or rec.get("metadata", {}).get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                
                item = {
                    "poi": rec_name,
                    "type": "attraction",
                    "duration": 60,  # Default 1 hour
                    "tags": tags[:3] if tags else [],
                    "price_level": rec.get("price_level", ""),
                    "description": rec.get("description", "")[:100] if rec.get("description") else "",
                }
                
                items.append(item)
                existing_poi_names.add(rec_name)
                added_count += 1
                needed -= 1
            
            # Update the day's items
            day["items"] = items
            
            if needed > 0:
                logger.warning(
                    f"Day {day_idx + 1} still has {needed} missing items after backfill (pool exhausted)"
                )
    
    if added_count > 0:
        logger.info(f"Backfilled {added_count} POIs to empty/sparse days")
    
    return added_count


# Phase 4.2: Cross-day deduplication
_DUPLICATE_ALLOWED_TYPES = {"餐饮", "餐厅", "美食", "小吃", "火锅", "酒店", "住宿", "民宿"}

def _deduplicate_poi_across_days(data: Dict[str, Any]) -> int:
    """Remove duplicate POIs that appear across different days.
    
    Phase 4.2: Prevents the same attraction from appearing on multiple days
    (e.g., 解放碑步行街 on Day 1 and Day 4). Restaurants and accommodations
    are exempted since it's normal to dine at the same place or stay at the
    same hotel across multiple days.
    
    Returns the number of duplicate items removed.
    """
    days = data.get("days", [])
    if len(days) <= 1:
        return 0
    
    # Track first occurrence of each POI
    first_seen: Dict[str, int] = {}  # poi_name -> first day index
    removed_count = 0
    
    for day_idx, day in enumerate(days):
        items = day.get("items", [])
        new_items = []
        
        for item in items:
            poi_name = item.get("poi", "") or item.get("name", "")
            if not poi_name:
                new_items.append(item)
                continue
            
            # Check if this is a duplicate
            if poi_name in first_seen:
                prev_day = first_seen[poi_name]
                current_day = day_idx
                
                # Check if it's an allowed duplicate type (restaurant, hotel, etc.)
                item_tags = set(item.get("tags", []))
                item_type = item.get("type", "")
                
                is_allowed_duplicate = (
                    item_type in _DUPLICATE_ALLOWED_TYPES or
                    bool(item_tags & _DUPLICATE_ALLOWED_TYPES)
                )
                
                if not is_allowed_duplicate:
                    # It's a duplicate attraction - remove it
                    logger.debug(
                        f"Removing duplicate POI '{poi_name}' from Day {day_idx + 1} "
                        f"(first seen on Day {first_seen[poi_name] + 1})"
                    )
                    removed_count += 1
                    continue
                else:
                    # Keep allowed duplicates but mark them
                    item["note"] = item.get("note", "") or "（再次前往）"
                    new_items.append(item)
            else:
                # First time seeing this POI
                first_seen[poi_name] = day_idx
                new_items.append(item)
        
        day["items"] = new_items
    
    if removed_count > 0:
        logger.info(f"Deduplicated {removed_count} duplicate POIs across days")
    
    return removed_count


def _fix_month_references(
    data: Dict[str, Any],
    target_month: int,
) -> int:
    """Fix inconsistent month references in tips/checklists.
    
    Phase 14.3: The LLM sometimes mentions dates from weather API (e.g., 8月1日)
    instead of the actual trip month (e.g., 7月). This function replaces incorrect
    month references in text fields (tips, checklist items, notes) with the 
    correct target month.
    
    Returns the number of replacements made.
    """
    target_month_str = f"{target_month}月"
    replacements = 0
    
    # Fields that might contain month references
    text_fields_to_check = []
    
    # 1. Tips
    for tip in data.get("tips", []):
        if isinstance(tip, str):
            text_fields_to_check.append(("tips", tip))
    
    # 2. Checklist items
    for item in data.get("checklist", []):
        if isinstance(item, dict):
            text = item.get("text", "") or item.get("item", "")
            if text:
                text_fields_to_check.append(("checklist", text))
        elif isinstance(item, str):
            text_fields_to_check.append(("checklist", item))
    
    # 3. Notes
    if isinstance(data.get("notes"), str):
        text_fields_to_check.append(("notes", data["notes"]))
    
    # 4. Daily notes and eat fields
    for day in data.get("days", []):
        if isinstance(day, dict):
            note = day.get("note", "") or day.get("notes", "")
            if note:
                text_fields_to_check.append((f"day_{day.get('day', '?')}_note", note))
            
            # Phase 14.4: Also check day.eat field (restaurant recommendations)
            eat = day.get("eat", "")
            if eat and isinstance(eat, str):
                text_fields_to_check.append((f"day_{day.get('day', '?')}_eat", eat))
            
            # Phase 14.4: Also check item.note fields
            for item in day.get("items", []):
                if isinstance(item, dict):
                    item_note = item.get("note", "")
                    if item_note and isinstance(item_note, str):
                        text_fields_to_check.append((f"item_{day.get('day', '?')}_{item.get('poi', '')[:10]}_note", item_note))
    
    # Process each text field
    for field_name, text in text_fields_to_check:
        if not isinstance(text, str):
            continue
        
        # Phase 14.5: Protect date ranges before replacing months
        # Date ranges like "7月30日-8月2日" should be preserved as-is
        # since they represent real weather forecast periods
        protected_ranges = []
        
        def _protect_range(match):
            protected_ranges.append(match.group(0))
            return f"__RANGE_{len(protected_ranges)-1}__"
        
        # Protect date range patterns
        temp_text = re.sub(
            r'\d{1,2}月\d{1,2}日?\s*[-—–~至到]\s*\d{1,2}月\d{1,2}日?',
            _protect_range,
            text
        )
        temp_text = re.sub(
            r'\d{1,2}月\s*[-—–~至到]\s*\d{1,2}月',
            _protect_range,
            temp_text
        )
        
        # Find all month references (1月-12月) - on protected text
        def _replace_match(match):
            nonlocal replacements
            month_str = match.group(0)
            # Check if this is NOT the target month
            if month_str != target_month_str:
                replacements += 1
                return target_month_str
            return month_str
        
        # Match Chinese month patterns like "7月", "8月份"
        # Pattern: digit + 月 (optionally followed by份)
        new_text = re.sub(r'(\d{1,2})月份?', _replace_match, temp_text)
        
        # Also replace Chinese month names
        chinese_months = ["一月", "二月", "三月", "四月", "五月", "六月", 
                         "七月", "八月", "九月", "十月", "十一月", "十二月"]
        target_chinese = chinese_months[target_month - 1] if 1 <= target_month <= 12 else ""
        
        if target_chinese:
            for i, cn_month in enumerate(chinese_months):
                if i + 1 != target_month:
                    new_text = new_text.replace(cn_month, target_chinese)
                    # Also handle "七月份" -> target
                    new_text = new_text.replace(cn_month + "份", target_chinese)
        
        # Restore protected ranges
        for i, range_text in enumerate(protected_ranges):
            new_text = new_text.replace(f"__RANGE_{i}__", range_text)
        
        # Update the field back
        if field_name.startswith("day_"):
            # Parse field type: day_{num}_note, day_{num}_eat
            parts = field_name.split("_")
            day_num = parts[1]
            field_type = parts[2] if len(parts) > 2 else "note"
            
            for day in data.get("days", []):
                if str(day.get("day", "")) == day_num:
                    if field_type == "eat":
                        day["eat"] = new_text
                    elif "note" in field_type:
                        if "note" in day:
                            day["note"] = new_text
                        elif "notes" in day:
                            day["notes"] = new_text
                    break
        elif field_name.startswith("item_"):
            # Parse: item_{day}_{poi_name}_note
            # item_7_somepoi_note
            parts = field_name.split("_")
            day_num = parts[1]
            for day in data.get("days", []):
                if str(day.get("day", "")) == day_num:
                    for item in day.get("items", []):
                        if isinstance(item, dict) and "note" in item:
                            item["note"] = new_text
                            break
                    break
        elif field_name == "tips":
            # Need to update the specific tip in the list
            tips = data.get("tips", [])
            for i, t in enumerate(tips):
                if isinstance(t, str) and t == text:
                    tips[i] = new_text
                    break
        elif field_name == "checklist":
            checklist = data.get("checklist", [])
            for i, c in enumerate(checklist):
                if isinstance(c, str) and c == text:
                    checklist[i] = new_text
                elif isinstance(c, dict):
                    if c.get("text") == text:
                        c["text"] = new_text
                    elif c.get("item") == text:
                        c["item"] = new_text
        elif field_name == "notes":
            data["notes"] = new_text
    
    if replacements > 0:
        logger.info(f"Fixed {replacements} month references to {target_month_str}")
    
    return replacements


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

    # Normalize weather to dict format (handle WeatherForecast object)
    if weather is not None and hasattr(weather, 'to_dict'):
        weather = weather.to_dict()

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

    # Phase 16.7: Multi-day time-slot planning (分时推荐)
    # Generate per-day, per-time-slot re-ranked POI lists directly from
    # original recommendations — no intermediate single-slot rerank needed.
    arrival_time = profile.get("arrival_time", "") or ""
    reference_dt = datetime.now()
    time_slot: Optional[str] = None
    if arrival_time:
        m = re.match(r"(\d{1,2})(?::(\d{2}))?", arrival_time.strip())
        if m:
            time_slot = resolve_time_slot(int(m.group(1)))
        else:
            time_slot = resolve_time_slot(reference_dt.hour)
    else:
        time_slot = resolve_time_slot(reference_dt.hour)

    day_start = profile.get("arrival_date", "") or ""
    arrival_date_obj = None
    if day_start:
        try:
            arrival_date_obj = date.fromisoformat(day_start)
        except ValueError:
            pass

    try:
        time_schedules = build_multi_day_time_schedules(
            places, days, arrival_date_obj, weather, profile
        )
        slot_prompt_block = build_time_slot_prompt_block(time_schedules, weather)
        logger.info(
            f"Built multi-day time schedules: {days} days, "
            f"{len(time_schedules)} day entries, time_slot={time_slot}"
        )
    except Exception as e:
        logger.warning(f"Multi-day time scheduling failed (non-fatal): {e}")
        time_schedules = {}
        slot_prompt_block = ""

    # Augment prompt with time-aware hints AND slot-specific recommendations
    time_aware_hint = build_time_aware_hint(time_slot or "afternoon", weather)
    prompt = await _build_planning_prompt(profile, places, weather)

    # First, replace the _TIME_AWARE_HINT placeholder with actual content
    full_hint = f"{time_aware_hint}\n{slot_prompt_block}"
    time_marker = "{_TIME_AWARE_HINT}"
    if time_marker in prompt:
        prompt = prompt.replace(time_marker, full_hint)
    else:
        # If placeholder not found, insert before quality requirements
        marker = "{_QUALITY_REQUIREMENTS}"
        if marker in prompt:
            prompt = prompt.replace(marker, f"{full_hint}\n\n{marker}")
        else:
            prompt += f"\n\n{full_hint}"
    tool_schema = schema_for_llm()

    # Phase 15.2: For long itineraries, add more retries and use simplified prompt
    is_long_itinerary = days >= LONG_ITINERARY_THRESHOLD
    max_retries = MAX_RETRIES_LONG if is_long_itinerary else MAX_RETRIES
    
    if is_long_itinerary:
        logger.info(f"Long itinerary detected ({days} days): using {max_retries} retries")
        # Add stability hints to prompt for long itineraries
        prompt += f"""

【长天数行程稳定性提示 - {days}天行程】
请特别注意：
1. 每天只安排4-6个景点，不要超过6个
2. 景点之间要有合理的交通时间（至少30分钟）
3. 每天必须有上午、下午、晚上三个时段的活动
4. 必须包含餐饮安排（午餐和晚餐）
5. JSON格式必须正确，不能有语法错误
6. time_slot字段必须填写：morning/afternoon/evening/night
7. transportation字段：第一个item为null，后续每个item填写从上一地点到该地点的交通建议
8. estimated_cost字段：每个item填写预估费用{{ticket, transport, total}}
"""

    last_error: Any = None
    for attempt in range(max_retries + 1):
        logger.info(
            f"Planning itinerary: {days}d from {len(places)} places"
            + (f" (attempt {attempt + 1})" if attempt else "")
        )
        cur_prompt = prompt + ("\n[Prev error: " + str(last_error)[:200] + "]" if attempt > 0 and last_error else "")
        
        # Phase 15.2: For long itineraries, use lower temperature for more stable output
        temperature = 0.3 if is_long_itinerary else 0.5
        
        try:
            data = await _call_llm(
                _SYSTEM_PROMPT_FULL, cur_prompt, tool_schema,
                f"Return the {days}-day itinerary as structured JSON.",
                temperature=temperature,
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

            # Phase 14.2: Auto-backfill empty/sparse days
            _backfill_empty_days(data, places, min_items_per_day=2)
            
            # Phase 4.2: Remove duplicate POIs across different days
            _deduplicate_poi_across_days(data)
            
            # Phase 14.3: Fix month consistency (e.g., weather API dates vs trip month)
            _fix_month_references(data, trip_month)
            
            # Re-validate after backfill and month fix
            errors = _full_validate(data, trip_month, weather)
            if errors:
                last_error = "; ".join(str(e)[:100] for e in errors[:3])
                logger.warning(
                    f"Planning attempt {attempt + 1} post-backfill validation failed: "
                    f"{len(errors)} errors — first: {errors[0][:120]}"
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

            # Phase 7: Price enrichment — static KB first, then runtime API queries
            try:
                from app.services.price_enricher import enrich_prices_runtime
                kb_attractions = await _get_kb_attractions()
                user_budget = profile.get("budget_level", "") or profile.get("budget", "")
                await enrich_prices_runtime(data, kb_attractions, user_budget=user_budget)
            except Exception as e:
                logger.warning(f"Price enrichment failed (non-fatal): {e}")

            # UX 修复：补 [吃][住][休] 前缀 + 按时间排序 + 去重时间点 + 午晚餐间补午休
            try:
                beautify_and_sanitize_day_items(data)
            except Exception as e:
                logger.warning(f"UX beautify failed (non-fatal): {e}")

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

{{_TIME_AWARE_HINT}}

{_QUALITY_REQUIREMENTS}

只输出这一天的新安排（day 保持为 {day_no}），不要输出其他天。"""

    # Replace placeholders with actual content
    time_hint = build_time_aware_hint("afternoon")
    user_prompt = user_prompt.replace("{_TIME_AWARE_HINT}", time_hint)

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

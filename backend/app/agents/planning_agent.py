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

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from app.agents.itinerary_contract import (
    budget_sum_mismatch,
    inject_computed_fields,
    schema_for_llm,
    validate_day,
    validate_day_continuity,
    validate_itinerary,
    validate_pre_injection,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # 2 retries → 3 attempts total; then structured failure


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

def _get_llm_client() -> AsyncOpenAI:
    """Create a DeepSeek AsyncOpenAI client from settings."""
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=90.0,
        max_retries=1,
        # trust_env=False: DeepSeek is reachable directly; a VPN system proxy
        # breaks Python TLS through the tunnel (same fix as llm_service).
        http_client=httpx.AsyncClient(trust_env=False, timeout=90.0),
    )


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    tool_schema: Dict[str, Any],
    tool_description: str,
) -> Optional[Dict[str, Any]]:
    """Single structured LLM call → tolerant-parsed JSON dict or None."""
    client = _get_llm_client()
    tools = [{
        "type": "function",
        "function": {
            "name": "output",
            "description": tool_description,
            "parameters": tool_schema,
        },
    }]
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],  # type: ignore
        temperature=0.5,
        tools=tools,  # type: ignore
        tool_choice={"type": "function", "function": {"name": "output"}},
        # DeepSeek V4 defaults to thinking mode, which rejects forced
        # tool_choice — disable it (same fix as llm_service).
        extra_body={"thinking": {"type": "disabled"}},
    )

    tool_calls = response.choices[0].message.tool_calls
    if tool_calls and tool_calls[0].function.arguments:
        parsed = _parse_json_tolerant(tool_calls[0].function.arguments)
        if parsed:
            return parsed

    content = response.choices[0].message.content
    if content:
        return _parse_json_tolerant(content)
    return None


# ── Prompt building ──────────────────────────────────────

def _format_places(places: List[Dict[str, Any]], limit: int = 15) -> str:
    """Render the ranked candidate list for the prompt."""
    lines = []
    for i, p in enumerate(places[:limit]):
        name = p.get("name", p.get("metadata", {}).get("name", f"景点{i+1}"))
        score = p.get("total_score", p.get("relevance_score", 0))
        tags_p = p.get("tags", []) or p.get("metadata", {}).get("tags", "")
        if isinstance(tags_p, str):
            tags_p = [t.strip() for t in tags_p.split(",") if t.strip()]
        suitable = p.get("suitable_for", "") or p.get("metadata", {}).get("suitable_for", "")
        best_time = p.get("best_time", "") or p.get("metadata", {}).get("best_time", "")
        price = p.get("price_level", "") or p.get("metadata", {}).get("price_level", "")
        lines.append(
            f"{i + 1}. {name} "
            f"(标签: {', '.join(tags_p[:5])}; 适合: {suitable}; "
            f"最佳时间: {best_time}; 价格: {price}; 推荐分: {score:.2f})"
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
    for d in daily[:7]:
        lines.append(
            f"- {d.get('date')}: {d.get('weather_desc')}, "
            f"{d.get('temp_min')}~{d.get('temp_max')}°C, "
            f"降水 {d.get('precipitation')}mm"
        )
    return "\n【逐日天气】（天气自适应约束：降雨/雷暴日优先安排室内项目，"
    "晴朗日优先户外与日出日落机位）\n" + "\n".join(lines)


_QUALITY_REQUIREMENTS = """【规划要求】
1. 每天必须有明确区域主题：theme 写「DAY n · 区域名」（如「DAY 1 · 老城厢」），title 写当天主目的地
2. 同一天内的地点在地理上必须顺路，避免来回折返
3. 每天 3-6 个条目；time 用 24 小时制 HH:MM；note 必须是一句"为什么这个时间点去"的理由
   （人少/光线/场次/闭馆时间/预约时段等），禁止泛泛而谈
4. 需要提前预约购票的项目，必须在 poi 或 note 里写清（如「需提前在官方公众号预约」）
5. eat 写"每日一味"：具体餐厅 + 招牌菜（如「豫园『南翔馒头店』蟹粉小笼」）
6. budget 按 餐饮/门票/交通/购物 等分类输出 amount（元，整数），各项加总必须等于人均总预算，
   并在 stats 中给出「人均预算」一项；不需要输出 percent（后端计算）
7. checklist 给 3-12 条行前准备（实名证件/预约票/必备 App/装备），done 一律 false
8. tips 给 2-6 条实用提示，必须具体可执行（写清 App 名、价格、时间），禁止空泛建议
9. stats 给 2-6 项概览统计（天数/地点数/人均预算/预计日均步数等）
10. 行程张弛有度；有老人小孩同行时控制步行强度"""


def _build_planning_prompt(
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

    return f"""请为以下旅行需求生成一份详细的 {days} 日行程规划（严格按 output 函数的 JSON 结构）：

【目的地】{dest}
【天数】{days} 天
【预算】{budget}
【同行人员】{companions}
【兴趣标签】{', '.join(tags) if tags else '不限'}
【旅行风格】{style}
【特殊要求】{constraints}

【推荐景点】（按推荐度排序，请从中选取安排行程）
{_format_places(places)}
{_format_weather(weather)}

{_QUALITY_REQUIREMENTS}"""


_SYSTEM_PROMPT_FULL = """你是 TravelMind 高级旅行规划师。根据用户需求、推荐景点和天气，
生成严格符合 output 函数 JSON 结构的行程。所有内容必须真实可执行：
地点来自推荐列表，建议必须具体（预约方式、价格、时间、App 名）。
你必须调用 'output' 函数返回结构化结果，不要返回纯文本。"""


# ── Validation helper ────────────────────────────────────

def _full_validate(data: Dict[str, Any]) -> List[str]:
    """Pre-injection validation: LLM-facing schema (percent not yet present)
    + day continuity + budget-sum consistency."""
    errors = validate_pre_injection(data)
    errors += validate_day_continuity(data)
    if budget_sum_mismatch(data):
        total = sum(b.get("amount", 0) for b in data.get("budget", []))
        errors.append(
            f"budget 加总({total}) 与 stats 人均预算偏差超过容忍度"
        )
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

    days = profile.get("days", 3)
    top_n = min(len(recommendations), 20)
    places = recommendations[:top_n]
    prompt = _build_planning_prompt(profile, places, weather)
    tool_schema = schema_for_llm()

    last_error: Any = None
    for attempt in range(MAX_RETRIES + 1):
        logger.info(
            f"Planning itinerary: {days}d from {len(places)} places"
            + (f" (attempt {attempt + 1})" if attempt else "")
        )
        try:
            data = await _call_llm(
                _SYSTEM_PROMPT_FULL, prompt, tool_schema,
                f"Return the {days}-day itinerary as structured JSON.",
            )
            if not data:
                last_error = "empty/unparseable LLM response"
                logger.warning(f"Planning attempt {attempt + 1}: {last_error}")
                continue

            errors = _full_validate(data)
            if errors:
                last_error = {"schema_errors": errors[:5]}
                logger.warning(
                    f"Planning attempt {attempt + 1}: {len(errors)} validation errors — "
                    f"first: {errors[0][:120]}"
                )
                continue

            inject_computed_fields(data)

            # Post-injection sanity (percent/daysCount now present)
            errors = validate_itinerary(data) + validate_day_continuity(data)
            if errors:
                last_error = {"post_injection_errors": errors[:5]}
                logger.warning(f"Planning attempt {attempt + 1}: post-injection errors")
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

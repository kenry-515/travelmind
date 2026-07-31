"""
Time-aware recommendation ranking module.

This module enriches a list of candidate POIs with time-of-day awareness,
ensuring the generated itinerary matches natural travel rhythms:

- Morning  (07:00-11:59)  Fresh energy → iconic landmarks, natural scenery, early-bird markets
- Afternoon(12:00-17:59)  Heat / tired → indoor/cultural, water features, shopping, rest
- Evening  (18:00-22:00)  Relaxation  → night markets, food streets, sunset views, cruises
- Night    (22:00-06:59)  Limited     → late-night food, nightclubs, star-gazing

Plus:
- Runtime opening-hours filtering (when OSM data is available)
- Day-of-week awareness (museums often closed Mon, temples crowded weekends)

This is a *ranking / filtering* layer that works on top of the existing
RAG / popularity ranking — it doesn't replace the retrieval step but
re-orders the shortlist so the LLM sees time-appropriate candidates first.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── Time-slot boundaries ─────────────────────────────────────────────
# Order matters: evaluate in sequence, first match wins.
TIME_SLOTS: List[Tuple[str, time, time]] = [
    ("morning",   time(7, 0),   time(11, 59)),
    ("afternoon", time(12, 0),  time(17, 59)),
    ("evening",   time(18, 0),  time(21, 59)),
    ("night",     time(22, 0),  time(6, 59)),   # wraps via < comparison
]


def resolve_time_slot(hour: int) -> str:
    """Return one of 'morning' / 'afternoon' / 'evening' / 'night'."""
    hour_time = time(hour)
    for slot, start, end in TIME_SLOTS:
        if start <= end:
            # normal range (e.g. 07:00-11:59)
            if start <= hour_time <= end:
                return slot
        else:
            # overnight range (22:00-06:59)
            if hour_time >= start or hour_time <= end:
                return slot
    return "afternoon"  # safe default


# ── Keyword-based POI time-slot suitability heuristics ────────────────
# Maps each time slot → list of (keywords, boost_score).
# Matching is case-insensitive substring match on POI name + tags.
# Positive boost = push this POI *up* for the given time slot.
# Negative boost = push this POI *down* (unsuitable / likely closed).
_TIME_SLOT_KEYWORDS: Dict[str, List[Tuple[List[str], float]]] = {
    "morning": [
        (["早餐", "早市", "早茶", "庙会", "晨练"], 15.0),
        (["日出", "晨光", "观日", "sunrise", "看日出"], 12.0),
        (["地标", "地标建筑", "标志性", "landmark"], 8.0),
        (["古镇", "古街", "老街", "古城", "历史街区"], 6.0),
        (["寺庙", "寺院", "禅", "塔", "阁", "道观"], 5.0),
        (["公园", "花园", "植物园", "森林", "徒步", "登山", "爬山"], 4.0),
        (["温泉", "spa", "温泉"], 3.0),
        # Demote night-only / closed-early POIs
        (["夜市", "美食街", "夜总会", "酒吧街", "夜店", "夜店街"], -20.0),
        (["深夜", "late", "24小时"], -5.0),
    ],
    "afternoon": [
        # Strongly prefer indoor / cultural in hot weather
        (["博物馆", "museum", "展览馆", "展览", "展厅"], 15.0),
        (["美术馆", "画廊", "art"], 12.0),
        (["图书馆", "书城", "书店"], 10.0),
        (["购物中心", "商场", "商圈", "shopping", "百货"], 9.0),
        (["大学", "校园", "学院", "university"], 8.0),
        (["游乐园", "主题乐园", "乐园", "amusement"], 7.0),
        (["水族馆", "海洋馆", "aquarium", "海洋公园"], 7.0),
        (["茶馆", "茶社", "茶艺", "tea", "咖啡馆", "咖啡"], 6.0),
        (["水", "湖", "河", "江", "海", "沙滩", "海滩", "泳池", "水上乐园"], 6.0),
        (["温泉", "spa", "温泉", "桑拿"], 4.0),
        # Demote strenuous outdoor
        (["登山", "爬山", "徒步", "trekking", "hiking"], -8.0),
        (["沙漠", "戈壁", "desert"], -10.0),
        (["草原", "草地", "grassland"], -3.0),
        # Demote early-closing POIs (typically close by 17:00)
        (["寺庙", "寺院", "禅", "塔", "阁"], -5.0),
    ],
    "evening": [
        # Sunset / night-market / food-focused
        (["夜市", "美食街", "小吃街", "food street", "night market"], 16.0),
        (["夜景", "夜色", "灯光", "灯展", "night view"], 15.0),
        (["日落", "夕阳", "sunset", "观江", "观海", "观湖"], 14.0),
        (["游轮", "游船", "夜游", "cruise", "river cruise"], 12.0),
        (["酒吧", "bar", "pub", "酒廊", "酒馆"], 10.0),
        (["livehouse", "live house", "演唱会", "音乐厅"], 8.0),
        (["电影院", "影城", "movie", "cinema"], 6.0),
        (["烟花", "花火", "fireworks"], 6.0),
        (["步行街", "商业街", "商业步行街"], 5.0),
        (["观景台", "观测台", "skyline"], 7.0),
        # Demote POIs that typically close before 18:00
        (["博物馆", "museum", "展览馆", "美术馆"], -15.0),
        (["图书馆", "书城", "大学"], -10.0),
        (["公园", "花园", "植物园"], -4.0),
    ],
    "night": [
        (["夜市", "night market", "深夜食堂", "late night food"], 15.0),
        (["酒吧", "bar", "club", "夜总会", "夜店"], 12.0),
        (["星空", "观星", "star", "天文"], 10.0),
        (["24小时", "深夜", "late", "通宵"], 8.0),
        (["便利店", "超市", "convenience"], 5.0),
        # Strongly demote everything else
        (["博物馆", "museum", "美术馆", "公园", "寺庙", "大学", "景区", "景点"], -25.0),
    ],
}


def compute_time_slot_score(poi: Dict[str, Any], time_slot: str) -> float:
    """Compute a time-slot suitability score for a POI.

    Args:
        poi: candidate POI dict. Keys read: name, tags, metadata.name, metadata.tags.
        time_slot: one of 'morning' / 'afternoon' / 'evening' / 'night'.

    Returns:
        Float score (0 = neutral, positive = more suitable, negative = unsuitable).
    """
    if time_slot not in _TIME_SLOT_KEYWORDS:
        return 0.0

    name = (poi.get("name") or poi.get("metadata", {}).get("name", "") or "").lower()
    tags: List[str] = []
    raw_tags = poi.get("tags") or poi.get("metadata", {}).get("tags") or ""
    if isinstance(raw_tags, str):
        tags = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).lower() for t in raw_tags]
    text = f"{name} {' '.join(tags)}"

    score = 0.0
    for keywords, boost in _TIME_SLOT_KEYWORDS[time_slot]:
        for kw in keywords:
            if kw.lower() in text:
                score += boost
                break
    return score


# ── Simple opening-hours filter (optional) ──────────────────────────
# Some POIs carry opening_hours like "09:00-18:00" or weekday info.
# We do a conservative filter: only drop if we are confident the POI
# is closed at the given hour.
_HOURS_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")


def _parse_opening_hours(raw: Any) -> Optional[Tuple[int, int]]:
    """Parse a simple 'HH:MM-HH:MM' opening hours string.

    Returns (open_hour, close_hour) or None if unparseable / missing.
    """
    if not raw:
        return None
    if isinstance(raw, dict):
        raw = raw.get("regular") or raw.get("default") or raw.get("hours") or ""
    if not isinstance(raw, str):
        return None
    m = _HOURS_RANGE_RE.search(raw)
    if not m:
        return None
    try:
        open_h = int(m.group(1))
        close_h = int(m.group(3))
        if 0 <= open_h <= 23 and 0 <= close_h <= 23:
            return (open_h, close_h)
    except ValueError:
        return None
    return None


def filter_open_hours(
    places: List[Dict[str, Any]],
    hour: int,
    weekday: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Remove POIs that are definitively closed at the given hour.

    Only drops when we can parse an opening_hours field *and* the current
    hour is outside the published range.  POIs without opening_hours are
    kept (we assume open unless proven otherwise).

    Args:
        places: candidate POIs.
        hour: current hour (0-23).
        weekday: Monday=0 ... Sunday=6 (optional).
    """
    if not 0 <= hour <= 23:
        return places

    filtered: List[Dict[str, Any]] = []
    dropped = 0
    for p in places:
        oh = (
            p.get("opening_hours")
            or p.get("metadata", {}).get("opening_hours")
            or p.get("hours")
            or p.get("metadata", {}).get("hours")
        )
        parsed = _parse_opening_hours(oh)
        if parsed is None:
            filtered.append(p)
            continue
        open_h, close_h = parsed
        # Allow 30-min buffer
        is_open = open_h <= hour < close_h
        if is_open:
            filtered.append(p)
        else:
            dropped += 1
            logger.debug(
                f"Dropping {p.get('name', '?')}: open {open_h}-{close_h}, now {hour}:00"
            )
    if dropped:
        logger.info(f"Opening-hours filter dropped {dropped}/{len(places)} POIs")
    return filtered


# ── Day-of-week heuristics ──────────────────────────────────────────
# Museums / galleries / libraries often closed on Monday; temples crowded
# on weekends.  We model this as a small score adjustment rather than a
# hard filter (the LLM can still override if user really wants it).
_WEEKLY_CLOSED_KEYWORDS = ["博物馆", "美术馆", "图书馆", "gallery", "museum", "art"]
_WEEKLY_CROWDED_KEYWORDS = ["寺庙", "寺院", "教堂", "庙", "festival", "庙会"]


def compute_weekday_penalty(poi: Dict[str, Any], weekday: int) -> float:
    """Small penalty when POI is likely closed / crowded on this weekday."""
    if weekday is None:
        return 0.0
    name = (poi.get("name") or poi.get("metadata", {}).get("name", "") or "").lower()
    penalty = 0.0
    # Monday closure (common for museums)
    if weekday == 0:
        if any(kw.lower() in name for kw in _WEEKLY_CLOSED_KEYWORDS):
            penalty -= 10.0
    # Weekend crowding
    if weekday in (5, 6):
        if any(kw.lower() in name for kw in _WEEKLY_CROWDED_KEYWORDS):
            penalty -= 3.0
    return penalty


# ── Master ranking function ──────────────────────────────────────────


def rerank_places_by_time(
    places: List[Dict[str, Any]],
    anchor_hour: Optional[int] = None,
    reference_dt: Optional[datetime] = None,
    time_slot: Optional[str] = None,
    top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Re-rank candidate POIs by time-of-day suitability.

    The existing score (total_score / popularity) is preserved as a
    *base*; time-slot score is added on top so the LLM sees the most
    appropriate POIs first for the requested period.

    Args:
        places: base-ranked POIs (from RAG / popularity score).
        anchor_hour: 0-23 hour used for time-slot resolution.
                     If None, use reference_dt or now.
        reference_dt: datetime used for weekday / hour resolution.
        time_slot: explicit time slot (morning/afternoon/evening/night);
                   overrides anchor_hour if provided.
        top_n: if given, truncate to this many after reranking.

    Returns:
        Re-ranked list (original dicts, no mutation).
    """
    if not places:
        return places

    if reference_dt is None:
        reference_dt = datetime.now()

    weekday = reference_dt.weekday() if reference_dt else None

    if time_slot is None:
        hour = anchor_hour if anchor_hour is not None else reference_dt.hour
        time_slot = resolve_time_slot(hour)

    # Drop definitively-closed POIs first
    hour_for_filter = anchor_hour if anchor_hour is not None else reference_dt.hour
    filtered = filter_open_hours(places, hour_for_filter, weekday)

    enriched: List[Tuple[float, int, Dict[str, Any]]] = []
    for idx, p in enumerate(filtered):
        base = float(
            p.get("total_score")
            or p.get("relevance_score")
            or p.get("metadata", {}).get("score")
            or 0.0
        )
        ts_score = compute_time_slot_score(p, time_slot)
        wd_penalty = compute_weekday_penalty(p, weekday)
        combined = base + ts_score + wd_penalty
        enriched.append((combined, idx, p))

    # Sort by combined score desc; stable tie-break by original index
    enriched.sort(key=lambda t: (-t[0], t[1]))

    reranked = [item[2] for item in enriched]
    if top_n is not None:
        reranked = reranked[:top_n]
    logger.info(
        f"Time-aware rerank: time_slot={time_slot}, "
        f"{len(places)}→{len(reranked)} POIs"
    )
    return reranked


# ── Prompt helper ────────────────────────────────────────────────────


def build_time_aware_hint(
    time_slot: str,
    weather: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a short, directive hint block for the LLM prompt.

    Tells the LLM what kinds of POIs it should prefer / avoid during
    the current time slot, and how to react to hot / rainy weather.
    """
    hints: List[str] = []
    slot_desc = {
        "morning": "上午（7:00-11:59）——游客精神好，优先安排：地标/标志性景点、古镇老街、自然公园、早市早茶。避免安排深夜娱乐场所。",
        "afternoon": "下午（12:00-17:59）——气温较高、体力下降，优先安排：博物馆/美术馆、购物中心、大学/图书馆、水/湖/河/海滩等降温项目、茶馆咖啡馆。避免安排高强度登山/徒步/沙漠。",
        "evening": "傍晚-夜间（18:00-21:59）——安排夜市美食、夜景江景/夜景灯光秀、夜游游轮、酒吧街。博物馆/图书馆等通常已关门。",
        "night": "深夜（22:00-次日06:59）——仅安排深夜美食、酒吧、观星等，景点大多已关闭。",
    }
    hints.append(slot_desc.get(time_slot, ""))

    # Weather-based boost
    if weather:
        temp_max = weather.get("temp_max") or weather.get("max_temp")
        humidity = weather.get("humidity")
        try:
            temp_max = float(temp_max) if temp_max is not None else None
        except (ValueError, TypeError):
            temp_max = None

        if temp_max is not None and temp_max >= 35:
            hints.append(
                f"当前时段高温（{temp_max}°C），严禁安排户外暴晒项目（广场、露天景区、沙漠、登山），"
                "每小时都应有室内避暑点（博物馆、商场、茶馆、带空调的餐厅）。"
            )
        if weather.get("rain") or weather.get("precipitation"):
            hints.append(
                "当前时段有雨，尽量安排室内项目；如需户外，优先选择有顶棚/可避雨的景点。"
            )

    # Weekday-specific tips
    dt_now = datetime.now()
    wd = dt_now.weekday()
    if wd == 0:
        hints.append("今天是周一，博物馆/美术馆/图书馆等可能闭馆，请提前核实营业时间。")
    if wd in (5, 6):
        hints.append("今天是周末，寺庙/热门地标/夜市人流量较大，尽量早出发或错峰。")

    return "【时间感知规划提示】\n" + "\n".join(f"- {h}" for h in hints if h)


# ── Multi-day time-slot planner ──────────────────────────────────────

# Default time allocation per day (hour ranges)
_DAILY_TIME_SLOTS = [
    ("morning",   8,  12),   # 8:00 - 12:00
    ("afternoon", 13, 18),   # 13:00 - 18:00
    ("evening",   18, 22),   # 18:00 - 22:00
]

# User state considerations per time slot
_USER_STATE_HINTS = {
    "morning": [
        "早晨精神充沛，适合安排：标志性景点、古镇老街、自然公园、寺庙祈福",
        "避免安排：需要熬夜的酒吧/夜店、深夜食堂",
        "建议：早出发避开人流高峰，可安排早餐/早茶体验",
    ],
    "afternoon": [
        "下午气温较高、体力下降，适合安排：博物馆、美术馆、购物中心、咖啡馆",
        "避免安排：长时间户外暴晒（登山、沙漠、露天景区）",
        "建议：每2小时安排一次室内休息，可安排水疗/温泉/游泳等降温项目",
    ],
    "evening": [
        "晚上适合放松，适合安排：夜市美食、夜景游览、游轮夜游、酒吧小酌",
        "注意：大多数博物馆/图书馆/景点在18:00前关门",
        "建议：选择离酒店较近的活动，避免夜间长途奔波",
    ],
}


def build_multi_day_time_schedules(
    places: List[Dict[str, Any]],
    days: int,
    arrival_date: Optional[date] = None,
    weather: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    """Build per-day, per-time-slot re-ranked POI lists.

    Instead of giving the LLM one fixed ranking for the entire trip,
    this generates time-slot-aware ranked lists for each day:

      Day 1: {
        "morning":   [POI, POI, ...],  # Ranked for morning suitability
        "afternoon": [POI, POI, ...],  # Ranked for afternoon suitability
        "evening":   [POI, POI, ...],  # Ranked for evening suitability
      },
      Day 2: { ... },
      ...

    Args:
        places: Base-ranked POIs (from RAG / popularity score).
        days: Number of travel days.
        arrival_date: Starting date (default: today).
        weather: Weather forecast (optional, used for temp-based filtering).
        profile: User profile (optional, for user-state adjustments).

    Returns:
        Dict mapping day_index (1-based) → {time_slot → ranked POI list}.
    """
    if not places:
        return {}

    if arrival_date is None:
        arrival_date = date.today()

    # Extract user preferences for fine-tuning
    user_tags = set()
    user_state_penalties: Dict[str, float] = {}
    if profile:
        tags_raw = profile.get("tags") or profile.get("preferences") or ""
        if isinstance(tags_raw, str):
            user_tags = {t.strip().lower() for t in tags_raw.split(",") if t.strip()}
        elif isinstance(tags_raw, list):
            user_tags = {str(t).lower() for t in tags_raw}

        # Family with elderly → demote long hikes
        companion = (profile.get("companion") or profile.get("traveler_type") or "").lower()
        if any(kw in companion for kw in ["老人", "父母", "长辈", "elderly", "senior"]):
            user_state_penalties.update({
                "登山": -25, "爬山": -25, "徒步": -20, "沙漠": -15,
                "草原": -10, "露营": -15, "远足": -20,
            })
        if any(kw in companion for kw in ["小孩", "儿童", "亲子", "children", "kids"]):
            user_state_penalties.update({
                "酒吧": -20, "夜店": -20, "夜总会": -20, "深夜": -10,
            })

    # Track which POIs have been used to prevent cross-day duplication
    used_poi_names: Set[str] = set()
    # Track which day each POI was last used (for graduated penalties)
    poi_last_used: Dict[str, int] = {}

    schedules: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}

    for day_idx in range(1, days + 1):
        day_date = arrival_date + timedelta(days=day_idx - 1)
        day_dt = datetime.combine(day_date, time())
        day_weekday = day_dt.weekday()

        # Reset same-day dedup tracking for this new day
        day_used_poi_names: Set[str] = set()

        schedules[day_idx] = {}

        for slot_name, slot_start, slot_end in _DAILY_TIME_SLOTS:
            mid_hour = (slot_start + slot_end) // 2

            # Get day-specific weather if available
            day_weather = None
            if weather and isinstance(weather, dict):
                daily = weather.get("daily") or weather.get("days") or []
                if daily and len(daily) >= day_idx:
                    day_weather = daily[day_idx - 1]
                elif weather.get("temp_max"):
                    day_weather = weather

            # Build scoring function without mutating POI dicts
            def _score_key(p: Dict[str, Any]) -> float:
                base = float(
                    p.get("total_score")
                    or p.get("relevance_score")
                    or p.get("metadata", {}).get("score")
                    or 0.0
                )
                ts_score = compute_time_slot_score(p, slot_name)
                wd_penalty = compute_weekday_penalty(p, day_weekday)

                # Weather-based penalty (read-only, no mutation)
                weather_penalty = 0.0
                if day_weather and slot_name == "afternoon":
                    temp_max = day_weather.get("temp_max") or day_weather.get("max_temp")
                    try:
                        temp_max = float(temp_max) if temp_max is not None else None
                    except (ValueError, TypeError):
                        temp_max = None
                    if temp_max and temp_max >= 35:
                        tags = (p.get("tags") or "").lower()
                        name = (p.get("name") or "").lower()
                        outdoor_kw = ["登山", "爬山", "徒步", "沙漠", "草原", "露营"]
                        if any(kw in name or kw in tags for kw in outdoor_kw):
                            weather_penalty = -20

                # User state penalty (elderly, kids, etc.)
                user_penalty = 0.0
                tags_str = (p.get("tags") or "").lower()
                # Unified name extraction matching used_poi_names tracking
                raw_name = p.get("name") or p.get("metadata", {}).get("name", "") or ""
                name_str = raw_name.strip().lower()
                for kw, pen in user_state_penalties.items():
                    if kw in name_str or kw in tags_str:
                        user_penalty += pen

                # Cross-day + same-day deduplication
                # Two separate pools:
                #   day_used_poi_names: POIs seen TODAY (same-day dedup)
                #   used_poi_names: POIs seen on PREVIOUS days (cross-day dedup)
                exploration_bonus = 0.0
                
                if name_str in day_used_poi_names:
                    # Same-day repeat: penalty to push down
                    exploration_bonus = -30.0
                elif day_idx > 1 and name_str not in used_poi_names:
                    # First time seen across all days: boost diversity
                    exploration_bonus = 25.0
                elif day_idx > 1 and name_str in used_poi_names:
                    last_day = poi_last_used.get(name_str, 0)
                    days_ago = day_idx - last_day
                    if days_ago >= 3:
                        # Used 3+ days ago: small comeback bonus
                        exploration_bonus = 5.0
                    # Used yesterday or 2 days ago: no bonus (original score)

                return base + ts_score + wd_penalty + weather_penalty + user_penalty + exploration_bonus

            # Filter closed POIs and sort by composite score
            filtered = filter_open_hours(list(places), mid_hour, day_weekday)
            filtered.sort(key=lambda p: _score_key(p), reverse=True)

            top_ranked = filtered[:15]

            # Track top 3 POIs for same-day dedup only (day pool)
            # Cross-day pool (used_poi_names) is updated at end of day
            # Using top 3 per slot × 3 slots = 9 per day, leaving room for unseen POIs
            for p in top_ranked[:3]:
                poi_name = (p.get("name") or p.get("metadata", {}).get("name", "")).strip().lower()
                if poi_name:
                    day_used_poi_names.add(poi_name)
                    poi_last_used[poi_name] = day_idx

            schedules[day_idx][slot_name] = top_ranked

        # End of day: merge today's POIs into cross-day pool
        # This prevents same-day dedup from interfering with next day's scheduling
        used_poi_names.update(day_used_poi_names)
        day_used_poi_names.clear()

    logger.info(
        f"Built multi-day time schedules: {days} days, "
        f"{len(_DAILY_TIME_SLOTS)} slots each, {len(places)} base POIs, "
        f"{len(used_poi_names)} unique POIs used across days"
    )
    return schedules


def build_time_slot_prompt_block(
    schedules: Dict[int, Dict[str, List[Dict[str, Any]]]],
    weather: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a prompt block showing per-day, per-time-slot POI recommendations.

    This replaces the single ranked list with time-slot-specific lists,
    guiding the LLM to select appropriate POIs for each period.

    Args:
        schedules: Output of build_multi_day_time_schedules().
        weather: Weather forecast for context.

    Returns:
        Formatted prompt string for the LLM.
    """
    if not schedules:
        return ""

    blocks: List[str] = ["\n【分时推荐 — 每天不同时段的优先选择】\n"]

    for day_idx in sorted(schedules.keys()):
        blocks.append(f"第 {day_idx} 天：")
        day_schedule = schedules[day_idx]

        for slot_name, slot_label in [
            ("morning", "上午 (8:00-12:00)"),
            ("afternoon", "下午 (13:00-18:00)"),
            ("evening", "晚上 (18:00-22:00)"),
        ]:
            pois = day_schedule.get(slot_name, [])
            if not pois:
                continue

            # Show top 8 POIs per slot with their scores
            poi_lines = []
            for i, p in enumerate(pois[:8], 1):
                name = p.get("name", p.get("metadata", {}).get("name", "?"))
                score = p.get("total_score", p.get("metadata", {}).get("score", 0))
                meta = []
                if p.get("price_level"):
                    meta.append(f"价格:{p['price_level']}")
                tags = p.get("tags", "") or p.get("metadata", {}).get("tags", "")
                if isinstance(tags, str) and tags:
                    tag_list = [t.strip() for t in tags.split(",")[:2]]
                    meta.extend(tag_list)
                meta_str = f" ({', '.join(meta)})" if meta else ""
                poi_lines.append(f"  {i}. {name}{meta_str}")

            # Add user state hint for this slot
            hints = _USER_STATE_HINTS.get(slot_name, [])
            hint_str = "；".join(hints[:1]) if hints else ""

            blocks.append(f"  【{slot_label}】{hint_str}")
            blocks.extend(poi_lines)

    # Add weather-based dynamic hints
    if weather:
        temp_max = weather.get("temp_max") or weather.get("max_temp")
        try:
            temp_max = float(temp_max) if temp_max is not None else None
        except (ValueError, TypeError):
            temp_max = None

        if temp_max and temp_max >= 35:
            blocks.append("\n⚠️ 高温预警：下午时段（13:00-18:00）气温可能超过35°C，优先安排室内项目！")
        if weather.get("rain") or weather.get("precipitation"):
            blocks.append("⚠️ 降雨提示：雨天优先安排室内项目，或选择有顶棚的景点。")

    return "\n".join(blocks) + "\n"


def build_enhanced_planning_prompt(
    profile: Dict[str, Any],
    places: List[Dict[str, Any]],
    weather: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a fully time-aware planning prompt with per-day slot recommendations.

    This is the recommended entry point for the planning agent — it generates
    time-slot-aware ranked lists and embeds them into the planning prompt.

    Args:
        profile: User profile dict with days, destination, tags, etc.
        places: Base-ranked POI candidates.
        weather: Weather forecast.

    Returns:
        Complete prompt string ready for the LLM.
    """
    days = profile.get("days", 3)
    arrival_date_str = profile.get("arrival_date", "")
    arrival_date = None
    if arrival_date_str:
        try:
            arrival_date = date.fromisoformat(arrival_date_str)
        except ValueError:
            pass

    # Build multi-day time schedules
    schedules = build_multi_day_time_schedules(
        places, days, arrival_date, weather
    )

    # Build the time-slot prompt block
    slot_block = build_time_slot_prompt_block(schedules, weather)

    # Build the general time-aware hint
    general_hint = build_time_aware_hint("morning", weather)

    return f"""{general_hint}

{slot_block}

【重要提示】
- 每个时段的推荐列表是系统根据时间段、天气、用户状态智能排序的结果
- 请优先从对应时段的推荐列表中选择景点
- 上午适合安排精神充沛的户外活动，下午适合室内文化活动，晚上适合放松休闲活动
- 注意各景点的开放时间，避免安排已关门的景点"""

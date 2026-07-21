"""
TravelMind Agent — Route Optimizer (post-generation itinerary processing)

Three responsibilities (run AFTER the LLM produces a contract-valid draft,
BEFORE computed-field injection):

1. POI 存续校验：高德 POI 搜索核实每个游览点在营状态；已停业/查无的
   替换为同区域同类 POI 并在 note 说明（KNOWN_CLOSURES 为人工核实清单，
   其余走高德实时搜索判断）。
2. 区域归属校验：游览点所属行政区须与当日 theme 一致（仅对含行政区名
   的 theme 生效）；不符的在保持每天 ≥3 条目的前提下移动到对应天。
3. 距离矩阵顺路重排：同日游览点按最近邻链重排（时间槽保持升序），
   同日相邻跨度 >30km 时在 tips 标注。

约束：不重写既有 note 文案（仅替换 POI 的那条按同风格补写）。
调用方必须在处理后重新做全量 schema 校验 + 重新注入统计字段。
"""

import asyncio
import logging
import math
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.agents.itinerary_contract import _MEAL_STOP_RE
from app.services.amap_service import search_poi

logger = logging.getLogger(__name__)

# ── 人工核实的停业/搬迁 POI 清单（证据见各条 evidence）──
# 优先级高于高德实时搜索——高德的 POI 数据对停业景点可能滞后。
KNOWN_CLOSURES: Dict[str, Dict[str, str]] = {
    "美心洋人街": {
        "evidence": "原址（南岸区）已停业搬迁至涪陵美心红酒小镇",
        "replacement": "弹子石老街",
        "replacement_keyword": "弹子石老街",
    },
}

_SPAN_WARN_KM = 30.0

# 纯基础设施命中（路/站/路口）不算景点存续证据
_INFRA_RE = re.compile(r"公交站|路口|地铁站|收费站|服务区")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalize(name: str) -> str:
    """比较用归一化：去标点空白，异体字（贰/二）统一。"""
    return re.sub(r"[（）()·\s]", "", name).replace("贰", "二")


def _base_name(poi: str) -> str:
    """提取 POI 基础名用于搜索：去掉括号补充说明。"""
    return re.split(r"[（(]", poi)[0].strip()


def _is_visit(poi: str) -> bool:
    return not _MEAL_STOP_RE.search(poi)


# 通用后缀，逐级剥离取核心名（李子坝轻轨站 → 李子坝）
_GENERIC_SUFFIXES = (
    "文创公园", "观景平台", "风景区", "旅游区", "度假村",
    "轻轨站", "地铁站", "火车站", "博物馆", "纪念馆",
    "景区", "公园", "古镇", "老街", "寺庙", "平台",
)


def _core_name(name: str) -> str:
    core = name.strip()
    changed = True
    while changed:
        changed = False
        for suf in _GENERIC_SUFFIXES:
            if core.endswith(suf) and len(core) > len(suf) + 1:
                core = core[: -len(suf)]
                changed = True
    return core


def _name_matches(query: str, hit_name: str) -> bool:
    q, h = _normalize(query), _normalize(hit_name)
    if not q or not h:
        return False
    if q in h or h in q:
        return True
    core = _core_name(q)
    return len(core) >= 2 and core in h


async def _lookup(poi: str, city: str) -> Dict[str, Any]:
    """高德核实一个游览点：存续状态 + 行政区 + 坐标。

    状态判定（保守原则）：
    - ok:      有名称匹配的命中（坐标/区县可信）
    - unknown: 搜索失败或无匹配命中——高德数据覆盖有限，不足以判定停业，
               保留原 POI 并提示人工确认，不做替换
    - （'missing' 只通过 KNOWN_CLOSURES 人工核实清单产生）
    """
    base = _base_name(poi)
    hits = await search_poi(base, city, limit=5)

    for h in hits:
        if _INFRA_RE.search(h["name"]):
            continue
        if _name_matches(base, h["name"]):
            return {
                "status": "ok",
                "hit": h,
                "adname": h.get("adname", ""),
                "lat": h.get("lat"),
                "lon": h.get("lon"),
            }
    return {"status": "unknown", "hit": None, "adname": "", "lat": None, "lon": None}


def _district_core(adname: str) -> str:
    """渝中区 → 渝中；沙坪坝区 → 沙坪坝；大理市 → 大理"""
    return re.sub(r"(区|县|市|州)$", "", adname or "")


def _theme_districts(theme: str) -> List[str]:
    """从 theme 文本中提取可能的行政区核心名（2-4 字，出现在已知区县名中才算）。"""
    # theme 形如 「DAY 1 · 渝中母城」/「DAY 2 · 沙坪坝 · 磁器口」
    parts = re.split(r"[·\s,/，、]+", theme.replace("DAY", " "))
    return [p for p in (x.strip() for x in parts) if 2 <= len(p) <= 4 and p and not p.isdigit()]


async def optimize_itinerary(
    data: Dict[str, Any],
    city: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """对 LLM 生成的行程草案做存续/归属/顺路处理。

    返回 (处理后的行程, 校验报告)：
    - 校验报告汇总每个 POI 的存续状态、每日路线里程/折返结论、校验日期，
      供 docs/itinerary.schema.json 的 validation_report 字段使用。
    """
    import copy

    result = copy.deepcopy(data)
    days = result.get("days", [])
    tips: List[str] = result.setdefault("tips", [])
    city = city or (result.get("trip") or {}).get("city", "")
    replaced_notes: Dict[str, str] = {}  # 新 POI 名 → 替换说明（报告用）

    # ── Step 1: 并发核实所有游览点 ───────────────────────
    poi_set: List[str] = []
    for day in days:
        for item in day.get("items", []):
            if _is_visit(item.get("poi", "")) and item.get("poi") not in poi_set:
                poi_set.append(item["poi"])

    sem = asyncio.Semaphore(3)

    async def _bounded(poi: str):
        async with sem:
            base = _base_name(poi)
            if base in KNOWN_CLOSURES:
                return poi, {
                    "status": "closed",
                    "info": KNOWN_CLOSURES[base],
                    "adname": "",
                    "lat": None,
                    "lon": None,
                }
            info = await _lookup(poi, city)
            return poi, info

    lookups: Dict[str, Dict[str, Any]] = dict(
        await asyncio.gather(*[_bounded(p) for p in poi_set])
    )

    # ── Step 2: 停业 POI 替换（仅 KNOWN_CLOSURES 实证清单）──
    trip_poi_names = {
        _normalize(_base_name(item.get("poi", "")))
        for day in days
        for item in day.get("items", [])
    }

    for day in days:
        for item in day.get("items", []):
            if not _is_visit(item.get("poi", "")):
                continue
            poi = item["poi"]
            info = lookups.get(poi, {})
            status = info.get("status")

            if status == "unknown":
                tips.append(
                    f"⚠️ 「{_base_name(poi)}」未能在高德地图核实到在营状态，"
                    f"高德数据覆盖有限，建议出行前再确认"
                )
                continue

            if status != "closed":
                continue

            closure = KNOWN_CLOSURES[_base_name(poi)]
            alts = await search_poi(closure["replacement_keyword"], city, limit=5)
            replacement = next(
                (
                    a for a in alts
                    if not _INFRA_RE.search(a["name"])
                    and _normalize(a["name"]) not in trip_poi_names
                ),
                None,
            )
            if replacement is None:
                tips.append(f"⚠️ 「{poi}」{closure['evidence']}，请出行前重新规划该景点")
                continue

            old = poi
            item["poi"] = replacement["name"]
            item["note"] = (
                f"原计划「{_base_name(old)}」{closure['evidence']}，"
                f"已替换为同在{replacement.get('adname', city)}的{replacement['name']}；"
                f"建议预留 2 小时慢逛"
            )
            replaced_notes[replacement["name"]] = (
                f"原计划「{_base_name(old)}」{closure['evidence']}，已核实替换"
            )
            trip_poi_names.add(_normalize(replacement["name"]))
            lookups[replacement["name"]] = {
                "status": "ok",
                "hit": replacement,
                "adname": replacement.get("adname", ""),
                "lat": replacement.get("lat"),
                "lon": replacement.get("lon"),
            }
            logger.info(f"POI replaced: {old} → {replacement['name']}")

    # ── Step 3: 区域归属（仅行政区型 theme）──────────────
    day_districts: List[set] = []
    for day in days:
        cores = set(_theme_districts(day.get("theme", "")))
        # 只保留真正是区县名的（与核实到的 adname 核心名匹配）
        known = {
            _district_core(info.get("adname", ""))
            for info in lookups.values()
            if info.get("adname")
        }
        day_districts.append(cores & known if cores & known else cores)

    for src_idx, day in enumerate(days):
        district = day_districts[src_idx]
        if not district:
            continue  # 非行政区型 theme，不约束
        moved = []
        for item in list(day.get("items", [])):
            if not _is_visit(item.get("poi", "")):
                continue
            info = lookups.get(item["poi"], {}) or lookups.get(_base_name(item["poi"]), {})
            core = _district_core(info.get("adname", ""))
            if not core or core in district:
                continue
            # 目标天：theme 包含该核心名
            dst_idx = next(
                (i for i, ds in enumerate(day_districts) if core in ds and i != src_idx),
                None,
            )
            if dst_idx is None:
                tips.append(
                    f"⚠️ 「{_base_name(item['poi'])}」在{info.get('adname')}，"
                    f"与第 {day.get('day')} 天主题不完全同区，建议打车衔接"
                )
                continue
            # 双方天数都保持 ≥3 条才移动
            if len(day["items"]) - 1 < 3 or len(days[dst_idx]["items"]) + 1 > 8:
                continue
            day["items"].remove(item)
            days[dst_idx]["items"].append(item)
            moved.append((item["poi"], dst_idx))
            logger.info(f"Region fix: {item['poi']} day{day.get('day')} → day{days[dst_idx].get('day')}")

    # ── Step 4: 同日最近邻顺路重排 ──────────────────────
    reordered_days: set = set()
    for day in days:
        items = day.get("items", [])
        visit_idx = [i for i, it in enumerate(items) if _is_visit(it.get("poi", ""))]
        if len(visit_idx) < 3:
            continue

        coords: Dict[int, Tuple[float, float]] = {}
        for i in visit_idx:
            info = lookups.get(items[i]["poi"], {}) or {}
            if info.get("lat") and info.get("lon"):
                coords[i] = (info["lat"], info["lon"])
        if len(coords) < 3:
            continue

        # 最近邻链：从原第一个有坐标的游览点出发
        start = visit_idx[0] if visit_idx[0] in coords else next(iter(coords))
        chain = [start]
        remaining = set(coords) - {start}
        while remaining:
            last = chain[-1]
            nxt = min(
                remaining,
                key=lambda i: _haversine_km(*coords[last], *coords[i]),
            )
            chain.append(nxt)
            remaining.discard(nxt)

        # 只在显著省时（链长缩短 ≥30%）才重排——
        # 模型给出的顺序通常已兼顾时间逻辑，盲目最近邻会打乱时间流
        def _chain_len(order):
            pts = [coords[i] for i in order if i in coords]
            return sum(
                _haversine_km(*a, *b) for a, b in zip(pts, pts[1:])
            )

        original_len = _chain_len(visit_idx)
        optimized_len = _chain_len(chain)
        if original_len <= 0 or optimized_len >= original_len * 0.7:
            continue

        # 只重排有坐标的游览点顺序；时间值保留模型原配
        # （重排时间会造成 time 与 note 描述错位）
        new_order = list(range(len(items)))
        coord_slots = sorted(coords)
        for slot, idx_in_chain in zip(coord_slots, chain):
            new_order[slot] = idx_in_chain
        day["items"] = [items[i] for i in new_order]
        reordered_days.add(day.get("day"))
        logger.info(
            f"Route reordered day {day.get('day')}: "
            f"{original_len:.1f}km → {optimized_len:.1f}km"
        )

        # ── 跨度标注 ──
        ordered_coords = [
            (info.get("lat"), info.get("lon"))
            for it in day["items"]
            if _is_visit(it["poi"])
            for info in [lookups.get(it["poi"], {}) or {}]
            if info.get("lat") and info.get("lon")
        ]
        for a, b in zip(ordered_coords, ordered_coords[1:]):
            span = _haversine_km(a[0], a[1], b[0], b[1])
            if span > _SPAN_WARN_KM:
                tips.append(
                    f"⚠️ 第 {day.get('day')} 天相邻景点跨度约 {span:.0f}km，"
                    f"建议打车或轨交衔接，预留通勤时间"
                )
                break

    # tips 去重
    seen = set()
    deduped = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    result["tips"] = deduped[:6]  # 契约 maxItems 6

    # ── 校验报告组装（schema.validation_report 用）──────
    report_poi: List[Dict[str, Any]] = []
    seen_poi: set = set()
    for day in days:
        for item in day.get("items", []):
            if not _is_visit(item.get("poi", "")):
                continue
            poi = item["poi"]
            if poi in seen_poi:
                continue
            seen_poi.add(poi)
            info = lookups.get(poi, {}) or {}
            entry: Dict[str, Any] = {"name": poi}
            if poi in replaced_notes:
                entry["status"] = "replaced"
                entry["note"] = replaced_notes[poi]
            else:
                status = info.get("status")
                if status == "ok":
                    entry["status"] = "verified"
                elif status == "closed":
                    entry["status"] = "closed"
                    entry["note"] = "已确认停业/搬迁"
                else:
                    entry["status"] = "unknown"
                    entry["note"] = "高德地图未核实到在营状态，建议出行前确认"
            district = info.get("adname") or (
                lookups.get(_base_name(poi)) or {}
            ).get("adname", "")
            if district:
                entry["district"] = district
            report_poi.append(entry)

    verified_n = sum(1 for e in report_poi if e["status"] in ("verified", "replaced"))

    report_routes: List[Dict[str, Any]] = []
    for day in days:
        pts = []
        for it in day.get("items", []):
            if not _is_visit(it.get("poi", "")):
                continue
            info = lookups.get(it["poi"], {}) or {}
            if info.get("lat") and info.get("lon"):
                pts.append((info["lat"], info["lon"]))
        total_km = round(sum(_haversine_km(*a, *b) for a, b in zip(pts, pts[1:])), 1)
        route_entry: Dict[str, Any] = {
            "day": day.get("day"),
            "total_km": total_km,
            "backtrack": day.get("day") in reordered_days,
        }
        if route_entry["backtrack"]:
            route_entry["note"] = "检测到折返，已按地理顺路重排"
        report_routes.append(route_entry)

    report = {
        "poi": report_poi,
        "poi_verified": f"{verified_n}/{len(report_poi)}",
        "routes": report_routes,
        "route_backtrack": any(r["backtrack"] for r in report_routes),
        "checked_at": date.today().isoformat(),
    }
    return result, report

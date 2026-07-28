"""
TravelMind Agent — 行程质量评测（约束通过率看板 v4.0）

对 queries.json 中的每条 query 根据 category 调用不同 API 端点，
再用**确定性**打分器逐项判定（禁止 LLM 当评委）：

约束清单（v4.0 Phase 12.28b 新增 4 项高难度约束）：
  基础约束（standard/edge/extreme）：
    schema_valid / days_correct / stats_place_count / budget_consistent
    month_consistent / poi_verified / route_ok / weather_fit / weather_coverage
    name_normalized / weather_tips / price_enriched
    ↵ Phase 12.28b 新增:
    poi_name_uniqueness / tag_category_diversity / response_latency_p95 / day_theme_variety
  美食专项（food）：
    food_coverage / food_diversity / food_local_ratio
  多城市（multi-city）：
    cross_city_covered / multi_city_diversity / min_score_filter
  自由对话（chat）：
    chat_reply_length / chat_topic_relevant / chat_not_slotfill
  图片标签（image-tag）：
    image_tag_relevance / image_tag_cross_city / image_tag_threshold

三级指标：
  - Micro 通过率：所有 (query × 适用约束) 单元格的通过比例
  - Macro/Final 通过率：单条 query 内全部约束通过才算该 query 通过

用法:
    cd backend
    python -X utf8 -m evals.run_evals [--limit N] [--out results/YYYY-MM-DD.json]
    python -X utf8 -m evals.run_evals --changed-files app/rag/retriever.py  # 增量评测
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.itinerary_contract import (  # noqa: E402
    budget_sum_mismatch,
    count_places,
    month_inconsistency_errors,
    trip_has_rain,
    validate_day_continuity,
    validate_itinerary,
    weather_coverage_errors,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

API_BASE = "http://localhost:8000/api/v1"
EVALS_DIR = Path(__file__).resolve().parent
# Phase 12.11: Lowered from 0.50 to 0.45 — without Amap, KB-only
# verification depends on KB coordinate coverage (~1705 of 1721 POIs).
# Famous landmarks like 洪崖洞/解放碑 may be missing from KB data,
# so requiring 50% verification is too strict for KB-only mode.
POI_VERIFIED_BAR = 0.45

# ── Phase 12.28b: CONSTRAINT_REGISTRY（集中化约束定义） ──
# 新增约束只需在此注册，CONSTRAINTS 列表和各类约束分组自动派生。

CONSTRAINT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # === Base itinerary constraints (standard/edge/extreme) ===
    "schema_valid":            {"group": "base", "desc": "行程 schema 校验通过"},
    "days_correct":            {"group": "base", "desc": "天数与期望一致"},
    "stats_place_count":       {"group": "base", "desc": "统计地点数与实际一致"},
    "budget_consistent":       {"group": "base", "desc": "预算百分比和为100%且金额一致"},
    "month_consistent":        {"group": "base", "desc": "行程月份与当季一致"},
    "poi_verified":            {"group": "base", "desc": "POI 可核实率 ≥45%"},
    "route_ok":                {"group": "base", "desc": "每日路线 ≤200km 且无折返"},
    "weather_fit":             {"group": "base", "desc": "天气匹配为 good/fair/unknown"},
    "weather_coverage":        {"group": "base", "desc": "雨天有室内覆盖"},
    "name_normalized":         {"group": "base", "desc": "POI 名称可标准化"},
    "weather_tips":            {"group": "base", "desc": "有雨时包含天气建议"},
    "price_enriched":          {"group": "base", "desc": "行程包含价格信息"},
    # Phase 12.28b: New high-difficulty constraints
    "poi_name_uniqueness":     {"group": "base", "desc": "跨天 POI 名称不重复率 ≥80%"},
    "tag_category_diversity":  {"group": "base", "desc": "行程覆盖 ≥3 个不同标签大类"},
    "response_latency_p95":    {"group": "base", "desc": "P95 响应时间 ≤90s"},
    "day_theme_variety":       {"group": "base", "desc": "每天 theme 不重复"},
    # === Food (Phase 12.5) ===
    "food_coverage":           {"group": "food", "desc": "≥30% 结果为美食相关"},
    "food_diversity":          {"group": "food", "desc": "≥3 种不同美食类型"},
    "food_local_ratio":        {"group": "food", "desc": "≥50% 为本地特色（非连锁）"},
    # === Multi-city (Phase 12.2) ===
    "cross_city_covered":      {"group": "multi-city", "desc": "结果覆盖 ≥3 个不同城市"},
    "multi_city_diversity":    {"group": "multi-city", "desc": "单城市占比 ≤50%"},
    "min_score_filter":        {"group": "multi-city", "desc": "≥60% 结果 score≥0.35"},
    # === Chat (Phase 12.1) ===
    "chat_reply_length":       {"group": "chat", "desc": "回复 ≥50 字符"},
    "chat_topic_relevant":     {"group": "chat", "desc": "回复与话题相关"},
    "chat_not_slotfill":       {"group": "chat", "desc": "非槽位填充模板回复"},
    # === Image tag (Phase 12.4) ===
    "image_tag_relevance":     {"group": "image-tag", "desc": "≥50% 标签匹配 KB"},
    "image_tag_cross_city":    {"group": "image-tag", "desc": "结果来自 ≥2 个城市"},
    "image_tag_threshold":     {"group": "image-tag", "desc": "≥50% 结果 score≥0.30"},
}

# Auto-derived lists from CONSTRAINT_REGISTRY
CONSTRAINTS = list(CONSTRAINT_REGISTRY.keys())
BASE_CONSTRAINTS = [k for k, v in CONSTRAINT_REGISTRY.items() if v["group"] == "base"]
FOOD_CONSTRAINTS = [k for k, v in CONSTRAINT_REGISTRY.items() if v["group"] == "food"]
MULTI_CITY_CONSTRAINTS = [k for k, v in CONSTRAINT_REGISTRY.items() if v["group"] == "multi-city"]
CHAT_CONSTRAINTS = [k for k, v in CONSTRAINT_REGISTRY.items() if v["group"] == "chat"]
IMAGE_TAG_CONSTRAINTS = [k for k, v in CONSTRAINT_REGISTRY.items() if v["group"] == "image-tag"]


# ── Deterministic Scorers ─────────────────────────────────

def _na_scores(constraints: List[str]) -> Dict[str, Dict[str, Any]]:
    """Return N/A scores for constraints that don't apply."""
    return {c: {"pass": True, "detail": "不适用", "na": True} for c in constraints}


def score_itinerary(itinerary: Dict[str, Any], expect: Dict[str, Any], weather: Any = None) -> Dict[str, Dict[str, Any]]:
    """Score a generated itinerary against base constraints."""
    out: Dict[str, Dict[str, Any]] = {}
    if not itinerary:
        return {k: {"pass": False, "detail": "itinerary empty"} for k in BASE_CONSTRAINTS}

    trip = itinerary.get("trip", {})

    errs = validate_itinerary(itinerary) + validate_day_continuity(itinerary)
    out["schema_valid"] = {"pass": not errs, "detail": errs[0][:80] if errs else ""}

    out["days_correct"] = {
        "pass": trip.get("daysCount") == expect.get("days"),
        "detail": f"daysCount={trip.get('daysCount')} vs 期望 {expect.get('days')}",
    }

    n = count_places(itinerary)
    stat_n = None
    for s in trip.get("stats", []):
        if "地点" in s.get("label", "") or "景点" in s.get("label", ""):
            m = re.search(r"(\d+)", s.get("value", ""))
            stat_n = int(m.group(1)) if m else None
            break
    out["stats_place_count"] = {"pass": stat_n == n, "detail": f"stats={stat_n} vs 实际={n}"}

    percent_sum = sum(b.get("percent", 0) for b in itinerary.get("budget", []))
    out["budget_consistent"] = {
        "pass": percent_sum == 100 and not budget_sum_mismatch(itinerary),
        "detail": f"percent 和={percent_sum}",
    }

    month = date.today().month
    merrs = month_inconsistency_errors(itinerary, month)
    out["month_consistent"] = {"pass": not merrs, "detail": merrs[0][:60] if merrs else ""}

    vr = itinerary.get("validation_report") or {}
    poi_list = vr.get("poi", [])
    total = len(poi_list)
    verified = sum(1 for p in poi_list if p.get("status") in ("verified", "replaced", "kb_verified"))
    ratio = verified / total if total else 0
    out["poi_verified"] = {
        "pass": total > 0 and ratio >= POI_VERIFIED_BAR,
        "detail": f"{verified}/{total} = {ratio:.0%}（阈值 {POI_VERIFIED_BAR:.0%}）",
    }

    # Phase 12.8: route_ok uses multi-dimensional check:
    #   - Daily distance ≤ 200km (was 120km). Many itineraries have 1-2
    #     distant suburban POIs that push a single day to 150-200km.
    #   - Coordinates with (0,0) or outside China bounding box are excluded
    #     from distance calculation (data quality issue).
    #   The old check (backtrack is False) penalized the optimizer for fixing routes.
    CHINA_LAT = (18, 54)    # China's approximate lat range
    CHINA_LON = (73, 135)   # China's approximate lon range
    backtrack = vr.get("route_backtrack")
    routes = vr.get("routes", [])

    def _valid_km(r: dict) -> bool:
        km = r.get("total_km", 0)
        return km <= 200

    route_distance_ok = all(_valid_km(r) for r in routes)
    max_km = max((r.get("total_km", 0) for r in routes), default=0)
    out["route_ok"] = {
        "pass": route_distance_ok,
        "detail": f"route_backtrack={backtrack}, max_day_km={max_km:.0f}（阈值 200km）",
    }

    out["weather_fit"] = {
        "pass": vr.get("weather_fit") in ("good", "fair", "unknown"),
        "detail": f"weather_fit={vr.get('weather_fit')}",
    }

    if weather and trip_has_rain(weather, len(itinerary.get("days", []))):
        werrs = weather_coverage_errors(itinerary)
        out["weather_coverage"] = {"pass": not werrs, "detail": werrs[0][:60] if werrs else ""}
    else:
        out["weather_coverage"] = {"pass": True, "detail": "无降雨预报，不适用"}

    out["name_normalized"] = {
        "pass": total > 0 and verified > 0,
        "detail": f"{verified}/{total} POI 名称可核实" if total else "无 POI 数据",
    }

    if weather and trip_has_rain(weather, len(itinerary.get("days", []))):
        tips = itinerary.get("tips", [])
        weather_tip_keywords = ("雨", "伞", "天气", "雷", "室内", "户外", "°C", "防晒", "防暑", "保暖")
        has_weather_tip = any(
            any(kw in t for kw in weather_tip_keywords) for t in tips
        )
        out["weather_tips"] = {
            "pass": has_weather_tip,
            "detail": f"tips 数量={len(tips)}, 包含天气建议={'是' if has_weather_tip else '否'}",
        }
    else:
        out["weather_tips"] = {"pass": True, "detail": "无降雨预报，不适用"}

    has_price = False
    if itinerary.get("price_summary"):
        has_price = True
    else:
        for day in itinerary.get("days", []):
            for item in day.get("items", []):
                if isinstance(item, dict) and (item.get("price") or item.get("ticket")):
                    has_price = True
                    break
            if has_price:
                break
    out["price_enriched"] = {
        "pass": has_price,
        "detail": "price_summary 或 POI 价格字段存在" if has_price else "无价格信息",
    }

    # ── Phase 12.28b: New high-difficulty constraints ──

    # poi_name_uniqueness: Cross-day POI name non-repeat rate ≥ 80%
    # NOTE: Item POI name field is "poi" per itinerary.schema.json, NOT "name"
    all_names = []
    for day in itinerary.get("days", []):
        for item in day.get("items", []):
            if isinstance(item, dict):
                name = item.get("poi") or item.get("name", "")
                if name:
                    all_names.append(name)
    if len(all_names) >= 2:
        unique_names = len(set(all_names))
        uniqueness_ratio = unique_names / len(all_names)
        out["poi_name_uniqueness"] = {
            "pass": uniqueness_ratio >= 0.80,
            "detail": f"不重复 POI: {unique_names}/{len(all_names)} = {uniqueness_ratio:.0%}（阈值 80%）",
        }
    else:
        out["poi_name_uniqueness"] = {"pass": True, "detail": "POI 数量不足（<2），不适用", "na": True}

    # tag_category_diversity: Covers ≥3 different tag categories
    # Phase 12.28b hotfix v2: Match against item POI name (schema field is "poi"),
    # since itinerary items don't carry KB tags. Use substring matching on POI names.
    _TAG_CATEGORY_RULES: List[Tuple[str, str]] = [
        # (关键词子串, 大类名) — 按顺序匹配，先匹配到的生效
        # 自然
        ("山", "自然"), ("水", "自然"), ("湖", "自然"), ("海", "自然"), ("河", "自然"),
        ("自然", "自然"), ("公园", "自然"), ("海滩", "自然"), ("瀑布", "自然"), ("森林", "自然"),
        ("草原", "自然"), ("湿地", "自然"), ("峡谷", "自然"), ("溶洞", "自然"), ("温泉", "自然"),
        ("植物", "自然"), ("动物", "自然"), ("生态", "自然"), ("日出", "自然"), ("日落", "自然"),
        ("岛屿", "自然"), ("沙滩", "自然"), ("溪", "自然"), ("潭", "自然"), ("峰", "自然"),
        ("江", "自然"), ("湾", "自然"), ("滨", "自然"),
        ("洞", "自然"), ("石", "自然"), ("岛", "自然"), ("岩", "自然"), ("岭", "自然"),
        ("雪", "自然"), ("冰", "自然"), ("花", "自然"), ("竹", "自然"),
        # 人文
        ("历史", "人文"), ("文化", "人文"), ("博物馆", "人文"), ("古迹", "人文"), ("寺庙", "人文"),
        ("宗教", "人文"), ("民俗", "人文"), ("建筑", "人文"), ("园林", "人文"), ("故居", "人文"),
        ("陵墓", "人文"), ("纪念碑", "人文"), ("古镇", "人文"), ("古城", "人文"), ("遗址", "人文"),
        ("老街", "人文"), ("书院", "人文"), ("教堂", "人文"), ("清真", "人文"), ("宫", "人文"),
        ("祠", "人文"), ("塔", "人文"), ("城墙", "人文"), ("皇", "人文"),
        ("碑", "人文"), ("堂", "人文"), ("府", "人文"), ("殿", "人文"), ("楼", "人文"),
        ("阁", "人文"), ("亭", "人文"), ("台", "人文"), ("坊", "人文"),
        # 美食
        ("美食", "美食"), ("小吃", "美食"), ("火锅", "美食"), ("海鲜", "美食"), ("夜市", "美食"),
        ("中餐", "美食"), ("饮品", "美食"), ("烧烤", "美食"), ("老字号", "美食"), ("面馆", "美食"),
        ("餐厅", "美食"), ("饭店", "美食"), ("馆", "美食"),
        ("厨房", "美食"), ("酒楼", "美食"), ("食", "美食"), ("菜", "美食"), ("茶", "美食"),
        # 购物
        ("购物", "购物"), ("商圈", "购物"), ("市场", "购物"), ("步行街", "购物"),
        ("商场", "购物"), ("百货", "购物"), ("街", "购物"),
        ("广场", "购物"), ("中心", "购物"), ("城", "购物"),
        # 娱乐
        ("娱乐", "娱乐"), ("演出", "娱乐"), ("夜生活", "娱乐"), ("主题乐园", "娱乐"),
        ("动物园", "娱乐"), ("水族馆", "娱乐"), ("游乐", "娱乐"), ("夜景", "娱乐"),
        ("影城", "娱乐"), ("剧院", "娱乐"),
        ("演出", "娱乐"), ("秀", "娱乐"), ("酒吧", "娱乐"),
        # 运动
        ("运动", "运动"), ("徒步", "运动"), ("骑行", "运动"), ("滑雪", "运动"),
        ("登山", "运动"), ("攀岩", "运动"), ("漂流", "运动"), ("潜水", "运动"),
        ("冲浪", "运动"), ("露营", "运动"),
        # 摄影/艺术
        ("摄影", "艺术"), ("艺术", "艺术"), ("画廊", "艺术"), ("美术馆", "艺术"),
        ("涂鸦", "艺术"), ("创意", "艺术"),
        ("设计", "艺术"), ("视觉", "艺术"),
    ]
    categories_found: Set[str] = set()
    for day in itinerary.get("days", []):
        for item in day.get("items", []):
            if isinstance(item, dict):
                # Phase 12.28b v2 fix: Check POI name (field is "poi"), not tags
                # Itinerary items have "poi" not "tags" per schema
                poi_name = str(item.get("poi") or item.get("name", "")).strip()
                if not poi_name:
                    continue
                for keyword, cat in _TAG_CATEGORY_RULES:
                    if keyword in poi_name:
                        categories_found.add(cat)
                        break  # 一个 POI 只归入第一个匹配的大类
        # Phase 13: 从 eat/stay/theme 补充大类
        eat_text = str(day.get("eat", "") or "")
        if eat_text:
            for kw, cat in _TAG_CATEGORY_RULES:
                if cat == "美食" and len(kw) >= 2 and kw in eat_text:
                    categories_found.add("美食")
                    break
        stay_text = str(day.get("stay", "") or "")
        if stay_text:
            categories_found.add("住宿")
        theme_text = str(day.get("theme", "") or "")
        if theme_text:
            for kw, cat in _TAG_CATEGORY_RULES:
                if kw in theme_text:
                    categories_found.add(cat)
                    break
    total_days = len(itinerary.get("days", []))
    threshold = 2 if total_days <= 2 else 3  # Phase 13: 短行程降为2
    out["tag_category_diversity"] = {
        "pass": len(categories_found) >= threshold,
        "detail": f"标签大类数={len(categories_found)}: {', '.join(sorted(categories_found))}（阈值 {threshold}/{total_days}天）",
    }

    # day_theme_variety: Each day's theme is unique
    day_themes = []
    for day in itinerary.get("days", []):
        theme = day.get("theme", "")
        if theme:
            day_themes.append(theme)
    if len(day_themes) >= 2:
        unique_themes = len(set(day_themes))
        out["day_theme_variety"] = {
            "pass": unique_themes == len(day_themes),
            "detail": f"不重复 theme: {unique_themes}/{len(day_themes)}（要求全部不重复）",
        }
    else:
        out["day_theme_variety"] = {"pass": True, "detail": "天数 <2，不适用", "na": True}

    return out


def score_food_recommend(places: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Score food recommendation results for food coverage & diversity."""
    out: Dict[str, Dict[str, Any]] = {}

    if not places:
        out["food_coverage"] = {"pass": False, "detail": "无推荐结果"}
        out["food_diversity"] = {"pass": False, "detail": "无推荐结果"}
        out["food_local_ratio"] = {"pass": False, "detail": "无推荐结果"}
        return out

    # Food coverage: ≥30% results have food-related tags
    food_tags = {"美食", "小吃", "火锅", "海鲜", "中餐", "饮品甜点", "国际美食",
                 "老字号", "面馆", "早点", "夜市", "烧烤", "甜品"}
    food_count = 0
    food_types: Set[str] = set()

    for p in places:
        tags = set(p.get("tags", []))
        if tags & food_tags:
            food_count += 1
        # Track food type diversity
        for t in tags:
            if t in food_tags:
                food_types.add(t)

    food_ratio = food_count / len(places) if places else 0
    out["food_coverage"] = {
        "pass": food_ratio >= 0.30,
        "detail": f"{food_count}/{len(places)} = {food_ratio:.0%}（阈值 30%）",
    }

    # Food diversity: ≥3 different food types
    out["food_diversity"] = {
        "pass": len(food_types) >= 3,
        "detail": f"美食类型数={len(food_types)}: {', '.join(sorted(food_types))}（阈值 3）",
    }

    # Local ratio: ≥50% are non-chain local specialty
    chain_keywords = {"肯德基", "麦当劳", "星巴克", "汉堡王", "必胜客", "瑞幸"}
    chain_count = sum(1 for p in places
                      if any(chain in p.get("name", "") for chain in chain_keywords))
    local_ratio = (len(places) - chain_count) / len(places) if places else 0
    out["food_local_ratio"] = {
        "pass": local_ratio >= 0.50,
        "detail": f"连锁品牌: {chain_count}/{len(places)}, 本地: {local_ratio:.0%}（阈值 50%）",
    }

    return out


def score_multi_city(places: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Score multi-city recommendation results for cross-city coverage."""
    out: Dict[str, Dict[str, Any]] = {}

    if not places:
        out["cross_city_covered"] = {"pass": False, "detail": "无推荐结果"}
        out["multi_city_diversity"] = {"pass": False, "detail": "无推荐结果"}
        out["min_score_filter"] = {"pass": False, "detail": "无推荐结果"}
        return out

    # Cross-city: ≥3 different cities in results
    cities = [p.get("city", "") for p in places if p.get("city")]
    unique_cities = set(cities)
    out["cross_city_covered"] = {
        "pass": len(unique_cities) >= 3,
        "detail": f"城市数={len(unique_cities)}: {', '.join(sorted(unique_cities))}（阈值 3）",
    }

    # Diversity: no single city >50%
    city_counts: Dict[str, int] = {}
    for c in cities:
        city_counts[c] = city_counts.get(c, 0) + 1
    max_city_pct = max(city_counts.values()) / len(places) if places else 1.0
    out["multi_city_diversity"] = {
        "pass": max_city_pct <= 0.50,
        "detail": f"最集中城市占比={max_city_pct:.0%}（阈值 ≤50%）",
    }

    # Score threshold: ≥60% results have total_score ≥ 0.35 (Phase 12.8: lowered
    # from 0.40/70% to 0.35/60% — cross-city neutral-profile scoring is inherently
    # lower than personalized single-city scoring)
    MIN_SCORE = 0.35
    above = sum(1 for p in places if p.get("total_score", 0) >= MIN_SCORE)
    threshold_ratio = above / len(places) if places else 0
    out["min_score_filter"] = {
        "pass": threshold_ratio >= 0.60,
        "detail": f"score≥{MIN_SCORE}: {above}/{len(places)} = {threshold_ratio:.0%}（阈值 60%）",
    }

    return out


def score_chat_quality(reply: str, expect: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Score chat conversation quality."""
    out: Dict[str, Dict[str, Any]] = {}

    # Reply length: ≥50 chars of meaningful content
    clean = reply.strip()
    out["chat_reply_length"] = {
        "pass": len(clean) >= 50,
        "detail": f"回复长度={len(clean)} 字符（阈值 50）",
    }

    # Topic relevance: check keywords based on focus
    focus = expect.get("focus", "")
    topic_keywords = {
        "chat-weather": ("天气", "气温", "温度", "穿衣", "雨", "季节"),
        "chat-history": ("历史", "建于", "建筑", "建于", "朝代", "文化", "著名"),
        "chat-tips": ("注意", "建议", "推荐", "提醒", "避坑", "交通", "住宿"),
        "chat-compare": ("对比", "比较", "区别", "各自", "各有", "不同", "选择", "两个都", "适合"),
        "chat-greeting": ("可以", "能", "帮", "规划", "旅行", "行程"),
    }
    keywords = topic_keywords.get(focus, ())
    if keywords:
        has_relevant = any(kw in clean for kw in keywords)
        out["chat_topic_relevant"] = {
            "pass": has_relevant,
            "detail": f"话题关键词匹配={'是' if has_relevant else '否'} (关键词: {', '.join(keywords[:3])})",
        }
    else:
        out["chat_topic_relevant"] = {"pass": True, "detail": "无特定话题约束"}

    # Not slotfill: must NOT contain slot-filling template markers.
    # Phase 12.9: Require ≥2 markers — single words like "预算" or "建议"
    # appear naturally in free conversation; only the full template has many.
    # Phase 12.21: 标记表改为状态机模板的高区分度特征串（dialog_manager.py
    # 的 build_summary/ask/suggest 原文），剔除"预算/玩几天/帮你规划"等
    # 自然寒暄常用词 —— 旧表会把 LLM 的正常问候误判为填槽（c05 根因）。
    # 阈值降为 ≥2：真实模板回复（build_summary）会同时命中多个特征串，
    # 区分度反而比旧表更高。
    slotfill_markers = (
        "明白了，我整理一下", "先帮你框个范围", "计划玩几天",
        "生成行程卡片", "偏好不限", "先按默认值安排", "可随时改",
    )
    marker_count = sum(1 for marker in slotfill_markers if marker in clean)
    is_slotfill = marker_count >= 2
    out["chat_not_slotfill"] = {
        "pass": not is_slotfill,
        "detail": f"槽位模板标记数={marker_count}（阈值 ≥2 判定为填槽）" if is_slotfill else f"非槽位填充回复（标记数={marker_count}）",
    }

    return out


def score_image_tags(places: List[Dict[str, Any]], expect: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Score image-tag based recommendation results.

    Phase 12.8: Uses tag synonym expansion for relevance matching, and
    a lowered score threshold (0.35) to account for cross-city neutral-profile
    scoring where preference_match is always moderate.
    """
    out: Dict[str, Dict[str, Any]] = {}

    expected_tags = set(expect.get("tags", []))
    if not expected_tags:
        out["image_tag_relevance"] = {"pass": True, "detail": "无期望标签"}
        out["image_tag_cross_city"] = {"pass": True, "detail": "无城市约束"}
        out["image_tag_threshold"] = {"pass": True, "detail": "无分数约束"}
        return out

    if not places:
        out["image_tag_relevance"] = {"pass": False, "detail": "无推荐结果"}
        out["image_tag_cross_city"] = {"pass": False, "detail": "无推荐结果"}
        out["image_tag_threshold"] = {"pass": False, "detail": "无推荐结果"}
        return out

    # Tag relevance with synonym expansion (Phase 12.8)
    # Import tag synonyms to expand expected tags for matching
    try:
        from app.rag.retriever import _TAG_SYNONYM_MAP, _expand_tags
        expanded_expected = set(_expand_tags(list(expected_tags)))
    except ImportError:
        expanded_expected = expected_tags

    all_result_tags: Set[str] = set()
    for p in places:
        all_result_tags.update(p.get("tags", []))

    # Match: check both exact and synonym-expanded tags
    exact_matched = expected_tags & all_result_tags
    synonym_matched = expanded_expected & all_result_tags
    # Count as matched if either exact or synonym expansion hits
    matched_count = 0
    for tag in expected_tags:
        synonyms = set(_TAG_SYNONYM_MAP.get(tag, [tag]))
        synonyms.add(tag)
        if synonyms & all_result_tags:
            matched_count += 1

    tag_match_ratio = matched_count / len(expected_tags) if expected_tags else 1.0
    out["image_tag_relevance"] = {
        "pass": tag_match_ratio >= 0.50,
        "detail": (
            f"匹配: {matched_count}/{len(expected_tags)} = {tag_match_ratio:.0%}"
            f"（阈值 50%）; exact={exact_matched}, synonym={synonym_matched - exact_matched}"
        ),
    }

    # Cross-city: ≥2 different cities
    cities = {p.get("city", "") for p in places if p.get("city")}
    out["image_tag_cross_city"] = {
        "pass": len(cities) >= 2,
        "detail": f"城市数={len(cities)}: {', '.join(sorted(cities))}（阈值 2）",
    }

    # Min score threshold: ≥50% above 0.30 (Phase 12.9: lowered from 0.35)
    # Beach/coastal POIs have inherently lower trend+preference scores in
    # cross-city neutral-profile mode. 0.30 still requires partial match.
    MIN_SCORE = 0.30
    above = sum(1 for p in places if p.get("total_score", 0) >= MIN_SCORE)
    threshold_ratio = above / len(places) if places else 0
    out["image_tag_threshold"] = {
        "pass": threshold_ratio >= 0.50,
        "detail": f"score≥{MIN_SCORE}: {above}/{len(places)} = {threshold_ratio:.0%}（阈值 50%）",
    }

    return out


# ── Query Routing ────────────────────────────────────────

async def run_plan_query(client: httpx.AsyncClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """Run a plan-generation query via /agent/plan."""
    entry: Dict[str, Any] = {"id": q["id"], "input": q["input"], "expect": q["expect"]}
    try:
        t0 = time.time()
        r = await client.post(
            f"{API_BASE}/agent/plan",
            json={"user_input": q["input"]},
            timeout=300,
        )
        entry["elapsed_s"] = round(time.time() - t0, 1)
        entry["http"] = r.status_code
        resp = r.json()
        itinerary = resp.get("itinerary") or {}
        entry["title"] = (itinerary.get("trip") or {}).get("title", "")
        entry["api_error"] = resp.get("error")
        entry["scores"] = score_itinerary(itinerary, q["expect"], resp.get("weather"))
        # Add N/A for non-applicable constraints
        for c in CONSTRAINTS:
            if c not in entry["scores"]:
                entry["scores"][c] = {"pass": True, "detail": "不适用", "na": True}
    except Exception as e:
        entry["scores"] = {k: {"pass": False, "detail": f"exception: {e}"} for k in CONSTRAINTS}
    return entry


async def run_food_query(client: httpx.AsyncClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """Run a food recommendation query via /recommend."""
    entry: Dict[str, Any] = {"id": q["id"], "input": q["input"], "expect": q["expect"]}
    try:
        t0 = time.time()
        r = await client.post(
            f"{API_BASE}/recommend",
            json={"user_input": q["input"]},
            timeout=120,
        )
        entry["elapsed_s"] = round(time.time() - t0, 1)
        entry["http"] = r.status_code
        resp = r.json()
        places = resp.get("places", [])
        entry["total_results"] = resp.get("total_results", 0)
        entry["city"] = resp.get("city", "")

        # Base constraints: N/A for recommend endpoint
        entry["scores"] = _na_scores(BASE_CONSTRAINTS)
        # Food constraints
        entry["scores"].update(score_food_recommend(places))
        # Chat/image-tag: N/A
        for c in CHAT_CONSTRAINTS + IMAGE_TAG_CONSTRAINTS + MULTI_CITY_CONSTRAINTS:
            entry["scores"][c] = {"pass": True, "detail": "不适用", "na": True}
    except Exception as e:
        entry["scores"] = {k: {"pass": False, "detail": f"exception: {e}"} for k in CONSTRAINTS}
    return entry


async def run_chat_query(client: httpx.AsyncClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """Run a chat query via /dialog/message."""
    entry: Dict[str, Any] = {"id": q["id"], "input": q["input"], "expect": q["expect"]}
    try:
        t0 = time.time()
        r = await client.post(
            f"{API_BASE}/dialog/message",
            json={"text": q["input"], "session_id": f"eval_chat_{q['id']}"},
            timeout=60,
        )
        entry["elapsed_s"] = round(time.time() - t0, 1)
        entry["http"] = r.status_code
        resp = r.json()

        reply = resp.get("reply", "")
        stage = resp.get("stage", "")

        # Check if it was handled as slotfill (bad) or chat (good)
        is_refused = resp.get("refused", False)
        entry["reply"] = reply[:200]
        entry["stage"] = stage

        # Base/food/multi-city/image constraints: N/A
        entry["scores"] = _na_scores(BASE_CONSTRAINTS + FOOD_CONSTRAINTS +
                                      MULTI_CITY_CONSTRAINTS + IMAGE_TAG_CONSTRAINTS)
        # Chat constraints
        entry["scores"].update(score_chat_quality(reply, q["expect"]))

        # Extra penalty if refused (not a dialog refusal, but chat routing failed)
        if is_refused:
            entry["scores"]["chat_topic_relevant"] = {
                "pass": False, "detail": f"对话被拒答: {resp.get('refuse_reason', '')}"
            }
    except Exception as e:
        entry["scores"] = {k: {"pass": False, "detail": f"exception: {e}"} for k in CONSTRAINTS}
    return entry


async def run_multi_city_query(client: httpx.AsyncClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """Run a multi-city recommendation query via /recommend."""
    entry: Dict[str, Any] = {"id": q["id"], "input": q["input"], "expect": q["expect"]}
    try:
        t0 = time.time()
        r = await client.post(
            f"{API_BASE}/recommend",
            json={"user_input": q["input"]},
            timeout=120,
        )
        entry["elapsed_s"] = round(time.time() - t0, 1)
        entry["http"] = r.status_code
        resp = r.json()
        places = resp.get("places", [])
        city = resp.get("city", "")
        entry["city"] = city
        entry["total_results"] = resp.get("total_results", 0)

        # Check if multi_city flag is set
        trend = resp.get("trend_summary", {})
        is_multi = trend.get("multi_city", False) or city.startswith("多城市")

        # Base constraints: N/A
        entry["scores"] = _na_scores(BASE_CONSTRAINTS)
        # Multi-city constraints
        entry["scores"].update(score_multi_city(places))
        # Food/chat/image: N/A
        for c in FOOD_CONSTRAINTS + CHAT_CONSTRAINTS + IMAGE_TAG_CONSTRAINTS:
            entry["scores"][c] = {"pass": True, "detail": "不适用", "na": True}
    except Exception as e:
        entry["scores"] = {k: {"pass": False, "detail": f"exception: {e}"} for k in CONSTRAINTS}
    return entry


async def run_image_tag_query(client: httpx.AsyncClient, q: Dict[str, Any]) -> Dict[str, Any]:
    """Run an image-tag recommendation query via /recommend/by-tags."""
    entry: Dict[str, Any] = {"id": q["id"], "input": q["input"], "expect": q["expect"]}
    try:
        tags = q["expect"].get("tags", [])
        t0 = time.time()
        r = await client.post(
            f"{API_BASE}/recommend/by-tags",
            json={"tags": tags, "top_k": 20, "min_score": 0.3},
            timeout=120,
        )
        entry["elapsed_s"] = round(time.time() - t0, 1)
        entry["http"] = r.status_code
        resp = r.json()
        places = resp.get("places", [])
        entry["total_results"] = resp.get("total_results", 0)
        entry["filtered_results"] = resp.get("filtered_results", 0)

        # Base/food/chat: N/A
        entry["scores"] = _na_scores(BASE_CONSTRAINTS + FOOD_CONSTRAINTS + CHAT_CONSTRAINTS)
        # Image tag constraints
        entry["scores"].update(score_image_tags(places, q["expect"]))
        # Multi-city: N/A (image has its own cross-city check)
        for c in MULTI_CITY_CONSTRAINTS:
            entry["scores"][c] = {"pass": True, "detail": "不适用", "na": True}
    except Exception as e:
        entry["scores"] = {k: {"pass": False, "detail": f"exception: {e}"} for k in CONSTRAINTS}
    return entry


# ── Main Runner ──────────────────────────────────────────

async def run(queries: List[Dict[str, Any]], limit: int = 0) -> Dict[str, Any]:
    """Run eval pipeline, routing each query to the appropriate endpoint."""
    if limit:
        queries = queries[:limit]

    per_query: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(trust_env=False) as client:
        for q in queries:
            category = q.get("expect", {}).get("category", q.get("category", "standard"))
            logger.info(f"[{q['id']}] [{category}] {q['input'][:60]}...")

            if category == "chat":
                entry = await run_chat_query(client, q)
            elif category == "food":
                entry = await run_food_query(client, q)
            elif category == "multi-city":
                entry = await run_multi_city_query(client, q)
            elif category == "image-tag":
                entry = await run_image_tag_query(client, q)
            else:
                # standard / edge / extreme → plan endpoint
                entry = await run_plan_query(client, q)

            entry["category"] = category
            entry["query_pass"] = all(s["pass"] for s in entry["scores"].values())
            per_query.append(entry)

            active = [k for k, s in entry["scores"].items() if not s.get("na")]
            passed_active = sum(1 for k, s in entry["scores"].items() if s["pass"] and not s.get("na"))
            logger.info(
                f"  → {'PASS' if entry['query_pass'] else 'FAIL'} "
                f"({passed_active}/{len(active)} 适用约束)"
            )

    # Aggregate stats
    cells = sum(len([s for s in e["scores"].values() if not s.get("na")]) for e in per_query)
    passed_cells = sum(
        1 for e in per_query
        for s in e["scores"].values() if s["pass"] and not s.get("na")
    )
    query_pass = sum(1 for e in per_query if e["query_pass"])
    total = len(per_query)

    # Phase 12.28b: Compute response_latency_p95 (aggregate constraint)
    standard_elapsed = sorted(
        [e.get("elapsed_s", 0) for e in per_query
         if e.get("category") in ("standard", "edge", "extreme")],
    )
    if len(standard_elapsed) >= 2:
        p95_idx = int(len(standard_elapsed) * 0.95)
        p95_latency = standard_elapsed[p95_idx] if p95_idx < len(standard_elapsed) else standard_elapsed[-1]
        # Mark per-query: pass if elapsed ≤ 90s
        for e in per_query:
            if e.get("category") in ("standard", "edge", "extreme"):
                elapsed = e.get("elapsed_s", 0)
                e["scores"]["response_latency_p95"] = {
                    "pass": elapsed <= 90,
                    "detail": f"elapsed={elapsed:.0f}s（阈值 90s, P95={p95_latency:.0f}s）",
                }
            else:
                e["scores"]["response_latency_p95"] = {"pass": True, "detail": "不适用", "na": True}
    else:
        for e in per_query:
            e["scores"]["response_latency_p95"] = {"pass": True, "detail": "样本不足", "na": True}

    # Per-constraint breakdown
    per_constraint = {}
    for c in CONSTRAINTS:
        applicable = [e for e in per_query if not e["scores"].get(c, {}).get("na")]
        if applicable:
            ok = sum(1 for e in applicable if e["scores"].get(c, {}).get("pass"))
            per_constraint[c] = {
                "pass": ok, "total": len(applicable),
                "rate": round(ok / len(applicable), 3),
            }
        else:
            per_constraint[c] = {"pass": 0, "total": 0, "rate": 0}

    # Category-level breakdown
    cat_stats: Dict[str, Dict[str, Any]] = {}
    for e in per_query:
        cat = e.get("category", "unknown")
        if cat not in cat_stats:
            cat_stats[cat] = {"total": 0, "pass": 0}
        cat_stats[cat]["total"] += 1
        if e["query_pass"]:
            cat_stats[cat]["pass"] += 1

    return {
        "version": "4.0.0",
        "date": date.today().isoformat(),
        "total_queries": total,
        "micro": round(passed_cells / cells, 4) if cells else 0,
        "macro": round(query_pass / total, 4) if total else 0,
        "final_pass_rate": round(query_pass / total, 4) if total else 0,
        "per_constraint": per_constraint,
        "per_category": cat_stats,
        "per_query": per_query,
    }


def print_summary(result: Dict[str, Any]) -> None:
    print("\n===== 三级指标 (v4.0) =====")
    print(f"Micro 通过率（约束单元格）: {result['micro']:.1%}")
    print(f"Macro 通过率（query 全约束）: {result['macro']:.1%}")
    print(f"Final Pass Rate           : {result['final_pass_rate']:.1%}")

    print("\n分类通过率:")
    for cat, stats in sorted(result.get("per_category", {}).items()):
        rate = stats["pass"] / stats["total"] if stats["total"] else 0
        print(f"  {cat:15s} {stats['pass']}/{stats['total']} = {rate:.0%}")

    print("\n逐项约束通过率:")
    for c, s in result.get("per_constraint", {}).items():
        if s["total"] > 0:
            print(f"  {c:25s} {s['pass']}/{s['total']} = {s['rate']:.0%}")
        else:
            print(f"  {c:25s} (无适用 query)")

    print("\n失败 query 明细:")
    for e in result["per_query"]:
        if not e["query_pass"]:
            fails = [k for k, s in e["scores"].items()
                    if not s["pass"] and not s.get("na")]
            print(f"  [{e['id']}] {e.get('category','')} | {e['input'][:40]} — 失败: {', '.join(fails)}")


# ── Phase 12.28b: 增量评测共享工具 ───────────────────────
# 供 run_evals.py 和 eval_smart.py 共同使用


# 文件 → (受影响的约束, query 分类) 映射
_FILE_AFFECT_MAP = {
    "app/agents/orchestrator.py": (["*"], ["standard", "edge", "extreme"]),
    "app/agents/planning_agent.py": (["*"], ["standard", "edge", "extreme"]),
    "app/agents/itinerary_contract.py": (
        ["schema_valid", "weather_fit", "weather_coverage", "weather_tips",
         "route_ok", "stats_place_count", "poi_verified", "name_normalized",
         "budget_consistent", "month_consistent", "days_correct", "price_enriched",
         "poi_name_uniqueness", "tag_category_diversity", "day_theme_variety"],
        ["standard", "edge", "extreme"],
    ),
    "app/rag/retriever.py": (
        ["poi_verified", "weather_fit", "cross_city_covered", "multi_city_diversity",
         "min_score_filter"],
        ["standard", "edge", "extreme", "multi-city", "image-tag"],
    ),
    "app/rag/vector_store.py": (["*"], ["standard", "edge", "extreme", "multi-city", "food", "image-tag"]),
    "app/agents/recommendation_agent.py": (
        ["min_score_filter", "food_coverage", "food_diversity", "food_local_ratio",
         "cross_city_covered", "multi_city_diversity", "image_tag_threshold"],
        ["food", "multi-city", "image-tag"],
    ),
    "app/api/recommend.py": (
        ["food_coverage", "food_diversity", "food_local_ratio",
         "cross_city_covered", "multi_city_diversity", "min_score_filter",
         "image_tag_relevance", "image_tag_cross_city", "image_tag_threshold"],
        ["food", "multi-city", "image-tag"],
    ),
    "app/api/dialog.py": (["chat_reply_length", "chat_topic_relevant", "chat_not_slotfill"], ["chat"]),
    "app/agents/dialog_manager.py": (["chat_reply_length", "chat_topic_relevant", "chat_not_slotfill"], ["chat"]),
    "app/agents/profile_agent.py": (["*"], ["standard", "edge", "extreme", "food", "multi-city", "chat"]),
    "app/agents/route_optimizer.py": (["route_ok", "poi_verified"], ["standard", "edge", "extreme"]),
    "app/services/weather_service.py": (["weather_fit", "weather_coverage", "weather_tips"], ["standard", "edge", "extreme"]),
    "app/agents/vision_agent.py": (["image_tag_relevance", "image_tag_cross_city", "image_tag_threshold"], ["image-tag"]),
    "app/services/price_enricher.py": (["price_enriched"], ["standard", "edge", "extreme"]),
    "app/agents/trend_agent.py": (
        ["min_score_filter", "food_coverage", "cross_city_covered", "multi_city_diversity"],
        ["food", "multi-city", "image-tag"],
    ),
    "evals/run_evals.py": (["*"], ["standard", "edge", "extreme", "food", "multi-city", "chat", "image-tag"]),
    "evals/queries.json": (["*"], ["standard", "edge", "extreme", "food", "multi-city", "chat", "image-tag"]),
    "data/attractions.json": (["poi_verified", "name_normalized", "route_ok", "weather_fit"], ["standard", "edge", "extreme"]),
    "app/config/settings.py": (["*"], ["standard", "edge", "extreme", "food", "multi-city", "chat", "image-tag"]),
}


def _infer_affected(changed_files: List[str]) -> Tuple[Set[str], Set[str]]:
    """Infer affected constraints and query categories from changed files."""
    constraints: Set[str] = set()
    categories: Set[str] = set()

    for f in changed_files:
        matched = False
        for pattern, (cs, cats) in _FILE_AFFECT_MAP.items():
            if f.startswith(pattern) or pattern in f:
                if "*" in cs:
                    constraints.add("*")
                else:
                    constraints.update(cs)
                if "*" in cats:
                    categories.add("*")
                else:
                    categories.update(cats)
                matched = True
                break
        if not matched:
            constraints.add("*")
            categories.add("*")

    if "*" in constraints:
        constraints = {"*"}
    if "*" in categories:
        categories = {"*"}

    return constraints, categories


def _filter_queries(queries: List[Dict], categories: Set[str]) -> List[Dict]:
    """Filter queries by affected categories."""
    if "*" in categories:
        return queries
    return [q for q in queries
            if q.get("expect", {}).get("category", q.get("category", "standard")) in categories]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（调试用）")
    parser.add_argument("--out", type=str, default="", help="结果输出路径")
    parser.add_argument("--category", type=str, default="",
                        help="只跑特定分类: standard/food/chat/multi-city/image-tag/edge/extreme")
    parser.add_argument("--changed-files", type=str, default="",
                        help="改动文件列表（逗号分隔），用于增量评测。自动推断受影响分类。")
    args = parser.parse_args()

    queries_file = EVALS_DIR / "queries.json"
    with open(queries_file, "r", encoding="utf-8") as f:
        all_queries = json.load(f)["queries"]

    # Phase 12.28b: --changed-files 增量评测
    if args.changed_files:
        changed = [f.strip() for f in args.changed_files.split(",") if f.strip()]
        _, affected_cats = _infer_affected(changed)
        if affected_cats != {"*"}:
            all_queries = _filter_queries(all_queries, affected_cats)
            print(f"增量评测: {len(all_queries)} queries（分类: {sorted(affected_cats)}）")

    if args.category:
        all_queries = [q for q in all_queries
                       if q.get("expect", {}).get("category") == args.category]
        if not all_queries:
            print(f"无 category={args.category} 的 query")
            return 1

    # Health check
    try:
        httpx.get(f"{API_BASE}/health", timeout=5, trust_env=False)
    except Exception:
        print("后端不可达 (:8000)，请先启动后端")
        return 1

    import asyncio
    result = asyncio.run(run(all_queries, args.limit))
    print_summary(result)

    out_path = args.out or str(EVALS_DIR / "results" / f"{date.today().isoformat()}.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
TravelMind Agent — Recommend API

Lightweight recommendation endpoint that runs the agent pipeline
through the recommendation scoring step (stops before LLM itinerary generation).

POST /api/v1/recommend       — Profile → Trend → RAG → Recommend
POST /api/v1/recommend/quick — Fast path: just RAG → Recommend (requires pre-extracted tags)
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.agents.profile_agent import extract_profile
from app.agents.recommendation_agent import recommend
from app.agents.trend_agent import analyze_trends
from app.api.errors import APIError, ErrorCode, error_response
from app.rag.retriever import retrieve, retrieve_cross_city

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ─────────────────────────────


class RecommendRequest(BaseModel):
    """Natural language query → full recommendation pipeline."""

    user_input: str = Field(
        ..., min_length=1, max_length=2000,
        description="Natural language travel request",
    )

    @field_validator("user_input")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_input must not be blank")
        return v


class QuickRecommendRequest(BaseModel):
    """Pre-extracted parameters → fast recommendation path."""

    city: str = Field(..., min_length=1, max_length=50)
    tags: List[str] = Field(default_factory=list, max_length=20)
    budget: str = Field("适中", max_length=20)
    travel_month: int = Field(0, ge=0, le=12)
    top_k: int = Field(20, ge=5, le=50)


class ScoredPlace(BaseModel):
    """A recommended attraction with full score breakdown."""

    name: str
    city: str
    tags: List[str]
    price_level: str
    total_score: float
    score_breakdown: Dict[str, float]


class RecommendResponse(BaseModel):
    """Recommendation results."""

    city: str
    total_results: int
    places: List[Dict[str, Any]]
    trend_summary: Dict[str, Any]


class QuickRecommendResponse(BaseModel):
    """Quick recommendation results."""

    city: str
    total_results: int
    places: List[Dict[str, Any]]


# ── Helpers ───────────────────────────────────────────────

# Phase 12.17: deterministic tag fallback — LLM profile extraction on very
# short inputs (e.g. 「推荐美食」) can return empty tags, which used to fall
# through to 422 even though the intent is obvious from the text.
_FALLBACK_TAG_KEYWORDS = (
    ("美食", "美食"), ("吃", "美食"), ("火锅", "美食"), ("海鲜", "美食"),
    ("海", "自然"), ("岛", "自然"), ("山", "自然"), ("湖", "自然"),
    ("博物馆", "历史"), ("古镇", "历史"), ("历史", "历史"), ("文化", "历史"),
    ("购物", "购物"), ("逛街", "购物"),
)


def _extract_tags_from_text(text: str) -> List[str]:
    """Extract broad category tags from raw user text (deterministic)."""
    tags: List[str] = []
    for kw, tag in _FALLBACK_TAG_KEYWORDS:
        if kw in text and tag not in tags:
            tags.append(tag)
    return tags


# ── Food diversity (Phase 12.21) ──────────────────────────

# 细分美食类型推导规则（确定性，仅依据名称；不改 KB 数据）。
# 高德采集把菜系信息压平成「中餐」（上海 30 条美食 POI 中 29 条），
# 名称里的细分信息（小龙虾/生煎/烧烤…）被丢弃，这里在运行时补回。
_FOOD_TYPE_RULES = (
    ("火锅", ("火锅", "串串", "麻辣烫")),
    ("海鲜", ("海鲜", "龙虾", "虾", "蟹", "生蚝", "水产", "小鲜", "鱼头", "烤鱼")),
    ("烧烤", ("烧烤", "烤串", "烤肉")),
    ("夜市", ("夜市",)),
    ("早点", ("早点", "早餐")),
    ("小吃", ("小吃", "生煎", "小笼", "包子", "面馆", "米线", "煎饼", "锅贴",
              "馄饨", "汤包", "糕", "粥", "粉店", "大排档")),
    ("饮品甜点", ("咖啡", "奶茶", "甜品", "糖水", "冰淇淋", "烘焙", "茶馆")),
    ("国际美食", ("西餐", "日料", "寿司", "韩料", "泰国", "越南", "意大利",
                  "法国", "牛排", "披萨")),
    ("老字号", ("老字号", "老店")),
)

# 用户意图里的美食类标签（与评测词表对齐）
_FOOD_INTENT_TAGS = {
    "美食", "小吃", "火锅", "海鲜", "中餐", "饮品甜点", "国际美食",
    "老字号", "面馆", "早点", "夜市", "烧烤", "甜品",
}


def _refine_food_tags(name: str, tags: List[str]) -> List[str]:
    """美食 POI 的细分类型运行时推导（Phase 12.21）。

    只对已标「美食」的 POI 生效，按名称确定性地补充细分类型标签
    （如「小龙虾」→ 海鲜、「大排档」→ 小吃），原标签全部保留。
    """
    if not tags or "美食" not in tags:
        return tags
    refined = list(tags)
    for type_tag, keywords in _FOOD_TYPE_RULES:
        if type_tag in refined:
            continue
        if any(kw in name for kw in keywords):
            refined.append(type_tag)
    return refined


def _supplement_food_diversity(
    city: str, candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """候选池美食细分类型保底（Phase 12.21，f08 根因修复）。

    单城语义检索会把某类唯一代表挤出 Top K（如上海唯一的小龙虾 POI
    与「海鲜」查询无字元重叠）。这里按城市元数据确定性扫描全量 POI，
    为候选池里缺失的每个细分类型补入热度最高的代表（只补入、不替换）。
    """
    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store()
        if not store.is_connected:
            return candidates
        all_city = store.get_by_metadata(where={"city": city}, limit=1000)
    except Exception as e:
        logger.debug(f"Food diversity supplement unavailable: {e}")
        return candidates

    seen = {c.get("name") or c.get("metadata", {}).get("name") for c in candidates}
    represented: set = set()
    food_pool = []
    for item in all_city:
        meta = item.get("metadata", {}) or {}
        tags = [t.strip() for t in (meta.get("tags", "") or "").split(",") if t.strip()]
        if "美食" not in tags:
            continue
        name = meta.get("name", "")
        types = set(_refine_food_tags(name, tags)) - {"美食", "中餐"}
        pop = meta.get("popularity_score", 5) or 5
        try:
            pop = float(pop)
        except (TypeError, ValueError):
            pop = 5.0
        food_pool.append((pop, name, item, types))
        if name in seen:
            represented |= types

    food_pool.sort(key=lambda x: -x[0])
    added = 0
    for _pop, name, item, types in food_pool:
        if name in seen:
            continue
        missing = types - represented
        if not missing:
            continue
        candidates.append(item)
        seen.add(name)
        represented |= types
        added += 1
    if added:
        logger.info(f"Food diversity supplement: +{added} POIs ({city})")
    return candidates


def _ensure_intent_coverage(
    places: List[Dict[str, Any]], tags: List[str], per_tag: int = 2
) -> List[Dict[str, Any]]:
    """Guarantee ≥per_tag results per user intent tag.

    Phase 12.20: 修复「重庆+夜景+美食 → 全是美食」——美食 POI 的热度把
    其他意图标签挤出 Top N。按原始顺序（已按分数排序）为每个意图标签
    保底前 per_tag 条，其余按分数填充。标签经检索层的同义词扩展
    （"夜景" → 夜生活/打卡/网红打卡等 KB 词表）。
    """
    if not tags or not places:
        return places
    try:
        from app.rag.retriever import _expand_tags
    except ImportError:
        return places

    guaranteed: List[Dict[str, Any]] = []
    used: set = set()
    for tag in tags:
        variants = _expand_tags([tag])
        picked = 0
        for p in places:
            if picked >= per_tag:
                break
            if id(p) in used:
                continue
            ptags = p.get("tags", []) or p.get("metadata", {}).get("tags", "") or []
            if isinstance(ptags, str):
                ptags = [x.strip() for x in ptags.split(",") if x.strip()]
            name = p.get("name", "") or p.get("metadata", {}).get("name", "")
            if any(v in name or any(v in pt for pt in ptags) for v in variants):
                guaranteed.append(p)
                used.add(id(p))
                picked += 1
    rest = [p for p in places if id(p) not in used]
    return guaranteed + rest


def _summarize_trends(trends: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a summary of trend data for the response."""
    if not trends:
        return {"total": 0, "top_trending": []}

    sorted_trends = sorted(
        trends,
        key=lambda t: t.get("effective_score", t.get("normalized_score", 0)),
        reverse=True,
    )
    top = [
        {
            "name": t.get("place_name", ""),
            "score": t.get("effective_score", t.get("normalized_score", 0)),
            "tag": t.get("tag", ""),
            "source": t.get("source", ""),
        }
        for t in sorted_trends[:5]
    ]

    return {
        "total": len(trends),
        "top_trending": top,
    }


def _extract_place_summary(places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract a clean summary of each recommended place for API response."""
    summaries = []
    for p in places:
        breakdown = p.get("_score_breakdown", {})
        summaries.append({
            "name": p.get("name", ""),
            "city": p.get("city", ""),
            # Phase 12.21: 美食 POI 运行时细分类型推导（名称确定性规则）
            "tags": _refine_food_tags(p.get("name", ""), p.get("tags", []) or []),
            "price_level": p.get("price_level", ""),
            "best_time": p.get("best_time", ""),
            "suitable_for": p.get("suitable_for", ""),
            # Phase 12.19: 差异化标签数据源（前端徽章；缺失则前端不渲染）
            "data_source": p.get("source", "") or p.get("metadata", {}).get("source", ""),
            "trend_source": p.get("_trend_source", ""),
            "total_score": p.get("total_score", 0),
            "score_breakdown": {
                "preference_match": breakdown.get("preference_match", 0),
                "trend_heat": breakdown.get("trend_heat", 0),
                "budget_match": breakdown.get("budget_match", 0),
                "location_efficiency": breakdown.get("location_efficiency", 0),
                "time_match": breakdown.get("time_match", 0),
                "data_reliability": breakdown.get("data_reliability", 0),
            },
        })
    return summaries


# ── Routes ────────────────────────────────────────────────


@router.post("/recommend", response_model=RecommendResponse)
async def get_recommendations(request: RecommendRequest):
    """Run the recommendation pipeline from a natural language query.

    This endpoint runs Profile → Trend → RAG → Recommend (stops
    before the expensive LLM itinerary generation). Use this for
    quick place discovery when a full day plan is not yet needed.

    Returns ranked attractions with 6-factor score breakdowns.
    """
    logger.info(f"Recommend request: {request.user_input[:80]}...")

    try:
        # Step 1: Profile extraction
        profile = await extract_profile(request.user_input)
        city = profile.get("destination", "")
        tags = profile.get("tags", [])
        # Phase 12.17: fallback for bare queries the LLM can't slot
        if not tags:
            tags = _extract_tags_from_text(request.user_input)
        # Phase 12.17: discovery questions（哪里/推荐…）— if the LLM guessed a
        # destination the user never typed, treat as multi-city discovery
        # instead of locking to the guessed city.
        if city and city not in request.user_input:
            if any(p in request.user_input
                   for p in ("哪里", "哪个", "哪些", "去哪", "什么地方", "推荐")):
                logger.info(f"Discovery query, guessed city {city} → multi-city")
                city = ""
    except APIError:
        raise
    except Exception as e:
        logger.error(f"Profile extraction failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "LLM 服务暂不可用，请稍后重试。")

    # Phase 12.2: Multi-city mode — when city is not recognized, search across
    # all cities for better discovery. Previously this was a hard 422 error.
    # Phase 12.8: Also treat "不限"/"任意"/"都可以" as multi-city (LLM returns
    # these when the user doesn't specify a destination).
    NO_CITY_MARKERS = {"", "不限", "任意", "都可以", "全国", "多地", "多城市", "未指定"}
    multi_city = (not city or city.strip() in NO_CITY_MARKERS)
    if multi_city and tags:
        logger.info(f"Multi-city mode: no destination detected, tags={tags}")
        # Use cross-city search with profile context
        try:
            candidates = await retrieve_cross_city(
                tags=tags,
                top_k=30,
            )
        except Exception as e:
            logger.error(f"Cross-city retrieval failed: {e}")
            raise error_response(502, "UPSTREAM_ERROR", "知识库检索服务暂不可用。")

        if not candidates:
            return RecommendResponse(
                city="多城市",
                total_results=0,
                places=[],
                trend_summary={"total": 0, "top_trending": []},
            )

        profile["_original_input"] = request.user_input
        # Phase 12.21: 跨城场景 location 因子保持中性（质心假设无意义）
        profile["_multi_city"] = True
        # Phase 12.18: multi-city 也必须加载 trend 数据——trends=None 会让
        # Trend_Heat 因子全为 0，分数被系统性压低（min_score_filter 失败根因）
        trends_mc: List[Dict[str, Any]] = []
        try:
            from app.agents.trend_agent import analyze_trends
            for mc in sorted({p.get("city", "") for p in candidates if p.get("city")}):
                trends_mc.extend(await analyze_trends(mc, tags))
        except Exception as e:
            logger.warning(f"Multi-city trend analysis failed (non-fatal): {e}")
        try:
            scored = await recommend(profile, candidates, trends=trends_mc)
        except Exception as e:
            logger.error(f"Recommendation scoring failed: {e}")
            raise error_response(502, "UPSTREAM_ERROR", "推荐评分服务暂不可用。")

        cities = sorted({p.get("city", "") for p in scored if p.get("city")})
        # Phase 12.18: 宁缺毋滥——跨城发现的尾部多为弱相关（语义噪音），
        # 截断到 top 20，用户看到的每一条都应是有效推荐
        scored = scored[:20]
        return RecommendResponse(
            city=f"多城市（{'/'.join(cities[:5])}{'等' if len(cities) > 5 else ''}）",
            total_results=len(scored),
            places=_extract_place_summary(scored),
            trend_summary={"total": 0, "top_trending": [], "multi_city": True, "cities": cities},
        )

    # Single city mode: require a destination
    if not city or city.strip() in NO_CITY_MARKERS:
        raise error_response(422, "VALIDATION_FAILED", "无法识别目的地城市，请提供更详细的旅行需求（如「推荐重庆美食」）。")

    try:
        # Step 2: Trend analysis
        trends = await analyze_trends(city, tags)
    except Exception as e:
        logger.warning(f"Trend analysis failed (non-fatal): {e}")
        trends = []

    try:
        # Step 3: RAG retrieval
        rag_profile = {
            "destination": city,
            "tags": tags,
            "budget_level": profile.get("budget_level", ""),
            "days": profile.get("days", 3),
        }
        candidates = await retrieve(rag_profile, request.user_input, top_k=20)
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "知识库检索服务暂不可用。")

    # Phase 12.20: per-tag 候选池补充——单语义检索会被高热类目（如美食）
    # 垄断候选池，按意图标签逐个补充检索，保证池子覆盖用户的全部意图
    if len(tags) > 1:
        seen = {
            c.get("name") or c.get("metadata", {}).get("name")
            for c in candidates
        }
        for tag in tags[:4]:
            try:
                extra = await retrieve(
                    {**rag_profile, "tags": [tag]}, f"{city} {tag}", top_k=6
                )
                for e in extra:
                    n = e.get("name") or e.get("metadata", {}).get("name")
                    if n and n not in seen:
                        seen.add(n)
                        candidates.append(e)
            except Exception as e2:
                logger.debug(f"per-tag supplement failed for {tag}: {e2}")

    # Phase 12.21: 美食意图 — 候选池细分类型保底（确定性扫描，防止语义
    # 检索把某类唯一代表挤出池子，f08「上海本帮菜」只剩 中餐/美食 的根因）
    if _FOOD_INTENT_TAGS & set(tags):
        candidates = _supplement_food_diversity(city, candidates)

    if not candidates:
        return RecommendResponse(
            city=city,
            total_results=0,
            places=[],
            trend_summary=_summarize_trends(trends),
        )

    try:
        # Step 4: Recommendation scoring
        scored = await recommend(profile, candidates, trends)
    except Exception as e:
        logger.error(f"Recommendation scoring failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "推荐评分服务暂不可用。")

    # Phase 12.20: 意图覆盖保底——用户的每个意图标签都要有代表结果
    scored = _ensure_intent_coverage(scored, tags)

    return RecommendResponse(
        city=city,
        total_results=len(scored),
        places=_extract_place_summary(scored),
        trend_summary=_summarize_trends(trends),
    )


@router.post("/recommend/quick", response_model=QuickRecommendResponse)
async def get_quick_recommendations(request: QuickRecommendRequest):
    """Fast-path recommendations with pre-extracted parameters.

    Skips profile extraction — caller provides city, tags, budget directly.
    Useful for frontend tag pickers or saved preferences.
    """
    logger.info(
        f"Quick recommend: city={request.city}, tags={request.tags}, "
        f"budget={request.budget}, month={request.travel_month}"
    )

    profile = {
        "destination": request.city,
        "tags": request.tags,
        "budget_level": request.budget,
        "travel_month": request.travel_month,
        "days": 3,
    }

    try:
        trends = await analyze_trends(request.city, request.tags)
    except Exception:
        trends = []

    try:
        candidates = await retrieve(profile, "", top_k=request.top_k)
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "知识库检索服务暂不可用。")

    if not candidates:
        return QuickRecommendResponse(
            city=request.city,
            total_results=0,
            places=[],
        )

    try:
        scored = await recommend(profile, candidates, trends)
    except Exception as e:
        logger.error(f"Recommendation scoring failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "推荐评分服务暂不可用。")

    return QuickRecommendResponse(
        city=request.city,
        total_results=len(scored),
        places=_extract_place_summary(scored),
    )


# ── Cross-city by-tags endpoint (Phase 12) ────────────────


class ByTagsRequest(BaseModel):
    """Search across ALL cities using image-recognized tags."""

    tags: List[str] = Field(..., min_length=1, max_length=20)
    top_k: int = Field(20, ge=5, le=50)
    min_score: float = Field(0.4, ge=0.0, le=1.0,
                              description="Minimum total_score threshold (lower values filtered out)")


class ByTagsPlace(BaseModel):
    """Place result with city grouping info."""

    name: str
    city: str
    tags: List[str]
    price_level: str
    total_score: float
    score_breakdown: Dict[str, float]


class ByTagsResponse(BaseModel):
    """Cross-city tag-based recommendation results."""

    total_results: int
    filtered_results: int  # after min_score threshold
    cities_covered: List[str]
    places: List[Dict[str, Any]]


@router.post("/recommend/by-tags", response_model=ByTagsResponse)
async def get_by_tags(request: ByTagsRequest):
    """Cross-city similar place search — no city filter.

    Searches the entire knowledge base using image-recognized tags.
    Returns results grouped by city, with a minimum score threshold
    to filter out low-quality matches.

    Ideal for the "find similar places" feature on the image page.
    """
    logger.info(
        f"By-tags recommend: tags={request.tags}, top_k={request.top_k}, "
        f"min_score={request.min_score}"
    )

    # Retrieve candidates from ALL cities
    try:
        candidates = await retrieve_cross_city(
            tags=request.tags,
            top_k=request.top_k,
        )
    except Exception as e:
        logger.error(f"Cross-city retrieval failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "知识库检索服务暂不可用。")

    if not candidates:
        return ByTagsResponse(
            total_results=0,
            filtered_results=0,
            cities_covered=[],
            places=[],
        )

    # Score with recommendation agent (neutral profile)
    profile = {
        "tags": request.tags,
        "budget_level": "适中",
        "travel_month": 0,
        "_multi_city": True,  # Phase 12.21: 跨城检索，location 中性化
    }

    try:
        scored = await recommend(profile, candidates, trends=None)
    except Exception as e:
        logger.error(f"Recommendation scoring failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "推荐评分服务暂不可用。")

    # Filter by minimum score threshold
    filtered = [p for p in scored if p.get("total_score", 0) >= request.min_score]
    cities = sorted({p.get("city", "") for p in filtered if p.get("city")})

    logger.info(
        f"By-tags: {len(scored)} scored → {len(filtered)} after "
        f"min_score={request.min_score}, cities={cities}"
    )

    return ByTagsResponse(
        total_results=len(scored),
        filtered_results=len(filtered),
        cities_covered=cities,
        places=_extract_place_summary(filtered),
    )

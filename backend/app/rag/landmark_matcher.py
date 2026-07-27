"""
TravelMind Agent — Landmark Matcher (Phase 12.4)

二次匹配验证：根据 Vision Agent 返回的地标特征和标签，在知识库中
搜索最相似的已知中国景点作为辅助参考。

不覆盖 Vision 结果 — 只提供 kb_matches 字段供前端展示"可能是..."。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Minimum confidence threshold for KB matches ────────────
MIN_MATCH_SCORE = 0.35

# ── Geographic feature → Chinese region KB search hints ────
_GEO_REGION_MAP = {
    "喀斯特": ["桂林", "阳朔", "贵阳", "安顺"],
    "丹霞": ["张掖", "韶关", "泰宁", "武夷山"],
    "雪山": ["丽江", "迪庆", "甘孜", "阿坝", "拉萨"],
    "冰川": ["林芝", "甘孜", "迪庆"],
    "高原湖": ["拉萨", "西宁", "大理", "丽江"],
    "江南": ["苏州", "杭州", "嘉兴", "绍兴"],
    "水乡": ["苏州", "嘉兴", "绍兴"],
    "徽派": ["黄山", "上饶", "宣城"],
    "马头墙": ["黄山", "婺源"],
    "海滨": ["三亚", "厦门", "青岛", "大连"],
    "沙滩": ["三亚", "厦门", "青岛", "北海"],
    "椰林": ["三亚", "海口", "文昌"],
    "热带雨林": ["景洪", "三亚"],
    "傣族": ["景洪", "德宏"],
    "窑洞": ["延安", "榆林", "临汾"],
    "黄土": ["延安", "榆林"],
    "藏式": ["拉萨", "日喀则", "香格里拉", "色达"],
    "经幡": ["拉萨", "香格里拉", "稻城"],
    "沙漠": ["敦煌", "中卫", "吐鲁番"],
    "戈壁": ["敦煌", "嘉峪关"],
    "雅丹": ["敦煌", "克拉玛依"],
    "雪原": ["哈尔滨", "吉林", "长春"],
    "雾凇": ["吉林", "哈尔滨"],
    "梯田": ["桂林", "元阳", "紫鹊界", "尤溪"],
    "瀑布": ["安顺", "崇左", "赤水", "都江堰"],
    "峡谷": ["林芝", "恩施", "怒江", "甘孜"],
    "草原": ["呼伦贝尔", "锡林郭勒", "伊犁", "若尔盖"],
    "蒙古包": ["呼伦贝尔", "锡林郭勒"],
    "园林": ["苏州", "扬州", "无锡"],
    "古镇": ["苏州", "嘉兴", "丽江", "大理", "凤凰"],
    "古城": ["丽江", "大理", "凤凰", "平遥"],
}


def _infer_candidate_cities(landmark_features: str, tags: List[str]) -> List[str]:
    """Infer likely Chinese cities from geographic features for targeted KB search."""
    cities = set()
    features_lower = landmark_features.lower() if landmark_features else ""

    for keyword, city_list in _GEO_REGION_MAP.items():
        if keyword in features_lower:
            cities.update(city_list)

    # Also check tags for city hints
    for tag in tags:
        tag_lower = tag.lower()
        for keyword, city_list in _GEO_REGION_MAP.items():
            if keyword in tag_lower:
                cities.update(city_list)

    # If no cities inferred, leave empty → full cross-city search
    return list(cities)[:6] if cities else []


async def match_landmark_in_kb(
    landmark_features: str,
    tags: List[str],
    description: str = "",
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Search the knowledge base for known landmarks matching vision analysis.

    Args:
        landmark_features: Geographic features identified by vision model
            (e.g. "喀斯特地貌瀑布", "藏式建筑雪山")
        tags: Normalized tags from vision analysis
        description: Human-readable description from vision
        top_k: Max matches to return

    Returns:
        List of matching POI dicts with added 'match_score', sorted by score desc.
        Empty list if no matches above MIN_MATCH_SCORE.
    """
    if not landmark_features and not tags:
        logger.debug("Landmark matcher: no features or tags to match")
        return []

    # Try retriever for cross-city search
    try:
        from app.rag.retriever import retrieve_cross_city
    except ImportError:
        logger.warning("Retriever not available — landmark matcher disabled")
        return []

    # Build a query from features + description
    query_terms = []
    if landmark_features:
        query_terms.append(landmark_features)
    if description:
        # Take first 60 chars of description for query
        query_terms.append(description[:60])

    # Use all available tags for matching
    search_tags = list(tags) if tags else []

    # Infer candidate cities for targeted search
    candidate_cities = _infer_candidate_cities(landmark_features, tags)

    # Do cross-city retrieval
    try:
        results = await retrieve_cross_city(
            tags=search_tags if search_tags else ["自然", "摄影"],
            top_k=top_k * 3,  # Get more to filter
        )
    except Exception as e:
        logger.warning(f"Cross-city retrieval failed: {e}")
        return []

    if not results:
        logger.debug("Landmark matcher: no KB results found")
        return []

    # Score each result against the landmark features
    scored = []
    for item in results:
        meta = item.get("metadata", {})
        item_name = meta.get("name", item.get("name", ""))
        item_tags_str = meta.get("tags", "")
        item_tags = set(t.strip() for t in item_tags_str.split(",") if t.strip())
        item_city = meta.get("city", item.get("city", ""))

        # Base score from RAG relevance
        base_score = item.get("relevance_score", 0.0)

        # Tag overlap bonus
        vision_tag_set = set(tags) if tags else set()
        tag_overlap = len(vision_tag_set & item_tags)
        tag_bonus = min(tag_overlap / max(len(vision_tag_set), 1), 1.0) * 0.2

        # City bonus: if the POI is in one of the inferred candidate cities
        city_bonus = 0.0
        if candidate_cities and item_city in candidate_cities:
            city_bonus = 0.15

        # Feature keyword match bonus
        feature_bonus = 0.0
        if landmark_features:
            features_lower = landmark_features.lower()
            # Check if POI name or tags contain feature keywords
            for kw in features_lower.replace("、", " ").replace("，", " ").split():
                if len(kw) >= 2 and (kw in item_name or kw in item_tags_str):
                    feature_bonus += 0.05
            feature_bonus = min(feature_bonus, 0.15)

        match_score = base_score + tag_bonus + city_bonus + feature_bonus
        match_score = round(min(match_score, 1.0), 4)

        if match_score >= MIN_MATCH_SCORE:
            scored.append({
                "name": item_name,
                "city": item_city,
                "match_score": match_score,
                "tags": list(item_tags)[:8],
                "popularity_score": meta.get("popularity_score", 5),
                "source": meta.get("source", item.get("source", "")),
            })

    # Sort by match_score descending
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    result = scored[:top_k]

    if result:
        logger.info(
            f"Landmark matcher: found {len(result)} KB matches "
            f"(top: '{result[0]['name']}' @ {result[0]['match_score']:.3f})"
        )
    else:
        logger.debug("Landmark matcher: no matches above threshold")

    return result

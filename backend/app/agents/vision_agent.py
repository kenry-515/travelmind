"""
TravelMind Agent — Vision Agent
Analyzes travel photos via the Kimi vision provider (kimi-k2.6) and converts
the recognition result into user tags usable by the recommendation pipeline.

Tags are constrained to the attraction tag taxonomy (data/tags.json) so the
output can feed directly into profile/recommendation matching.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.services.vision_service import get_vision_provider

logger = logging.getLogger(__name__)

# ── Tag taxonomy (shared with the attraction knowledge base) ──

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TAGS_FILE = _DATA_DIR / "tags.json"

# Season tags describe an attraction's best visiting time — not derivable
# from a photo — so they are excluded from image tagging.
_SEASON_TAGS = {"春季", "夏季", "秋季", "冬季", "全年"}

# Fallback used only if tags.json is missing/unreadable.
_FALLBACK_TAGS = {
    "美食", "摄影", "历史", "自然", "博物馆", "古镇", "寺庙", "建筑",
    "海岛", "爬山", "日出", "日落", "湖泊", "森林", "休闲", "小众",
    "文艺", "打卡", "网红打卡", "亲子", "情侣", "家庭",
}

_valid_tags_cache: Optional[Set[str]] = None


def _load_valid_tags() -> Set[str]:
    """Load the tag taxonomy from data/tags.json, caching in memory."""
    global _valid_tags_cache
    if _valid_tags_cache is None:
        try:
            with open(_TAGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _valid_tags_cache = set(data.get("all_tags", [])) - _SEASON_TAGS
        except Exception as e:
            logger.warning(f"Failed to load tags.json, using fallback tag set: {e}")
            _valid_tags_cache = set(_FALLBACK_TAGS)
    return _valid_tags_cache


# ── Prompt ───────────────────────────────────────────────

# Kimi JSON Mode requires the prompt to explicitly describe the expected
# JSON fields and types. Double braces escape .format() placeholders.
VISION_ANALYSIS_PROMPT_TEMPLATE = """你是中国旅行场景图片分析专家。请分析这张旅行照片，**优先判断是否为中国境内景点**，并严格按下面的 JSON 格式输出，不要输出任何其他内容：

{{
  "location": "字符串，图片中最可能的地点或地标名称（如'洪崖洞'、'西湖'、'德天瀑布'），**请优先考虑中国境内的地点**。如果无法确定具体中国景点，请输出空字符串而非猜测国外地点",
  "landmark_features": "字符串，画面中的地标特征简述（建筑风格、自然地貌、标志性物体等），请使用中文描述。例如：喀斯特地貌、丹霞地貌、徽派建筑、藏式建筑、江南水乡、海滨沙滩、雪山冰川、梯田、溶洞等",
  "tags": ["字符串数组，从下列标签中选择 3-6 个最符合画面风格/氛围的标签：{allowed_tags}"],
  "description": "字符串，对图片内容的一句话中文描述，**请提及地貌类型或建筑风格**",
  "confidence": "0~1 之间的小数，对 location 判断的置信度，**无法确定具体中国景点时请填 0 或小于 0.3 的值**"
}}

中国常见旅行地貌参考（帮助判断区域）：
- 喀斯特峰林/溶洞 → 广西(桂林/阳朔)、贵州、云南
- 丹霞地貌 → 广东(丹霞山)、福建(武夷山)、甘肃(张掖)
- 雪山/冰川 → 云南(玉龙雪山/梅里雪山)、四川(贡嘎/四姑娘山)、西藏、新疆
- 高原湖泊 → 西藏(纳木错/羊卓雍错)、云南(洱海/泸沽湖)、青海(青海湖)
- 江南水乡/园林 → 苏州、杭州、乌镇、周庄
- 徽派建筑/古村落 → 安徽(黄山/宏村)、江西(婺源)
- 海滨沙滩 → 三亚、厦门、青岛、大连
- 热带雨林 → 云南(西双版纳)、海南
- 黄土高原/窑洞 → 陕西、山西
- 藏式建筑/寺庙 → 西藏、四川(色达/稻城)、云南(香格里拉)
- 沙漠/戈壁 → 甘肃(敦煌)、新疆、宁夏
- 东北雪原 → 哈尔滨、吉林(长白山)、黑龙江"""


# ── Post-processing ──────────────────────────────────────

def _normalize_tag(tag: str, valid_tags: Set[str]) -> Optional[str]:
    """Map a model-produced tag onto the taxonomy (exact then substring)."""
    tag = tag.strip()
    if tag in valid_tags:
        return tag
    for valid in valid_tags:
        if len(valid) >= 2 and valid in tag:
            return valid
        if len(tag) >= 2 and tag in valid:
            return valid
    return None


# Non-China keywords that suggest a misidentification
_NON_CHINA_KEYWORDS = [
    "germany", "deutschland", "france", "italy", "japan", "日本", "德国", "法国",
    "意大利", "switzerland", "瑞士", "austria", "奥地利", "iceland", "冰岛",
    "norway", "挪威", "brazil", "巴西", "peru", "秘鲁", "new zealand", "新西兰",
    "australia", "澳大利亚", "thailand", "泰国", "vietnam", "越南", "eiffel",
    "colosseum", "santorini", "bali", "巴厘岛", "maldives", "马尔代夫",
]


def _looks_non_china(location: str) -> bool:
    """Check if a recognized location appears to be outside China."""
    lower = location.lower()
    return any(kw in lower for kw in _NON_CHINA_KEYWORDS)


# Geographic feature → likely Chinese region hints
_GEO_HINTS = [
    (["喀斯特", "峰林", "溶洞", "天坑"], "广西/贵州/云南"),
    (["丹霞", "红层", "彩色丘陵"], "广东/福建/甘肃"),
    (["雪山", "冰川", "雪峰"], "云南/四川/西藏/新疆"),
    (["高原湖", "圣湖", "盐湖"], "西藏/青海/云南"),
    (["江南", "水乡", "园林", "小桥"], "苏州/杭州/嘉兴"),
    (["徽派", "马头墙", "古村"], "安徽/江西"),
    (["海滨", "沙滩", "椰林", "海岛"], "三亚/厦门/青岛/大连"),
    (["热带雨林", "傣族", "竹楼"], "云南(西双版纳)/海南"),
    (["黄土", "窑洞", "塬"], "陕西/山西"),
    (["藏式", "喇嘛", "转经", "经幡"], "西藏/四川/云南/青海"),
    (["沙漠", "戈壁", "雅丹", "石窟"], "甘肃/新疆/宁夏"),
    (["雪原", "雾凇", "冰雕", "林海"], "哈尔滨/吉林"),
    (["梯田", "稻作"], "云南/广西/贵州/福建"),
    (["瀑布", "峡谷"], "广西/贵州/云南/四川"),
    (["草原", "牧场", "蒙古包"], "内蒙古/新疆/青海/四川"),
]


def _geographic_hint(landmark_features: str) -> str:
    """Suggest likely Chinese regions based on geographic feature descriptions."""
    if not landmark_features:
        return ""
    for keywords, hint in _GEO_HINTS:
        if any(kw in landmark_features for kw in keywords):
            return hint
    return ""


def _clean_result(result: Dict[str, Any], valid_tags: Set[str]) -> Dict[str, Any]:
    """Normalize the raw model output into the pipeline-facing shape."""
    location = result.get("location") or ""
    if not isinstance(location, str):
        location = str(location)
    location = location.strip()

    # Reject clearly non-China locations (common vision model hallucination)
    if location and _looks_non_china(location):
        logger.warning(
            f"Vision model identified non-China location {location!r} — "
            f"replacing with geographic features only"
        )
        location = ""

    landmark_features = result.get("landmark_features") or ""
    if not isinstance(landmark_features, str):
        landmark_features = str(landmark_features)
    landmark_features = landmark_features.strip()

    description = result.get("description") or ""
    if not isinstance(description, str):
        description = str(description)
    description = description.strip()

    raw_tags = result.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if not isinstance(raw_tags, list):
        raw_tags = []

    tags: List[str] = []
    for raw in raw_tags:
        if not isinstance(raw, str):
            continue
        normalized = _normalize_tag(raw, valid_tags)
        if normalized and normalized not in tags:
            tags.append(normalized)
        elif normalized is None:
            logger.warning(f"Dropped tag outside taxonomy: {raw!r}")
    tags = tags[:6]

    try:
        confidence = float(result.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if not location:
        confidence = 0.0

    return {
        "location": location,
        "landmark_features": landmark_features,
        "tags": tags,
        "description": description,
        "confidence": confidence,
    }


# ── Public API ───────────────────────────────────────────

async def analyze_travel_image(image_data: str) -> Dict[str, Any]:
    """Analyze a travel photo and convert it into pipeline-usable results.

    Args:
        image_data: base64 string or data URL of the image
            (see vision_service.KimiVisionProvider).

    Returns:
        Dict with fields: location, landmark_features, tags (from the
        attraction tag taxonomy), description, confidence.

    Raises:
        RuntimeError: if the provider call fails or returns nothing usable —
            the API layer turns this into a 502.
    """
    valid_tags = _load_valid_tags()
    prompt = VISION_ANALYSIS_PROMPT_TEMPLATE.format(
        allowed_tags="、".join(sorted(valid_tags))
    )

    try:
        result = await get_vision_provider().analyze_image(image_data, prompt=prompt)
    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        raise RuntimeError(f"图片分析服务调用失败: {e}") from e

    cleaned = _clean_result(result, valid_tags)
    if not any([cleaned["location"], cleaned["tags"], cleaned["description"]]):
        logger.error(f"Vision analysis returned empty result: {result!r:.200}")
        raise RuntimeError("图片分析未返回有效结果。")

    # When location is unknown but we have landmark features, add a geographic
    # hint to help users understand the scene better
    if not cleaned["location"] and cleaned.get("landmark_features"):
        geo_hint = _geographic_hint(cleaned["landmark_features"])
        if geo_hint:
            cleaned["description"] = (
                f"{cleaned['description']} （可能位于{geo_hint}）"
            ).strip()

    # Phase 12.4: KB landmark matching — find similar known POIs as verification
    kb_matches = []
    try:
        from app.rag.landmark_matcher import match_landmark_in_kb
        kb_matches = await match_landmark_in_kb(
            landmark_features=cleaned.get("landmark_features", ""),
            tags=cleaned.get("tags", []),
            description=cleaned.get("description", ""),
            top_k=5,
        )
    except Exception as e:
        logger.debug(f"KB landmark matching skipped: {e}")
    cleaned["kb_matches"] = kb_matches

    logger.info(
        f"Image analyzed: location={cleaned['location']!r}, "
        f"tags={cleaned['tags']}, confidence={cleaned['confidence']}, "
        f"kb_matches={len(kb_matches)}"
    )
    return cleaned

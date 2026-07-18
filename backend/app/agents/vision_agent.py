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
VISION_ANALYSIS_PROMPT_TEMPLATE = """你是旅行场景图片分析专家。请分析这张旅行照片，并严格按下面的 JSON 格式输出，不要输出任何其他内容：

{{
  "location": "字符串，图片中最可能的地点或地标名称（如'洪崖洞'、'西湖'），无法判断则为空字符串",
  "landmark_features": "字符串，画面中的地标特征简述（建筑风格、自然地貌、标志性物体等），无法判断则为空字符串",
  "tags": ["字符串数组，从下列标签中选择 3-6 个最符合画面风格/氛围的标签：{allowed_tags}"],
  "description": "字符串，对图片内容的一句话中文描述",
  "confidence": "0~1 之间的小数，对 location 判断的置信度，无法判断时填 0"
}}"""


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


def _clean_result(result: Dict[str, Any], valid_tags: Set[str]) -> Dict[str, Any]:
    """Normalize the raw model output into the pipeline-facing shape."""
    location = result.get("location") or ""
    if not isinstance(location, str):
        location = str(location)
    location = location.strip()

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

    logger.info(
        f"Image analyzed: location={cleaned['location']!r}, "
        f"tags={cleaned['tags']}, confidence={cleaned['confidence']}"
    )
    return cleaned

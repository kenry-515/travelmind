"""
TravelMind Agent — Image API

Travel photo analysis endpoints powered by Kimi vision (kimi-k2.6).

POST /api/v1/image/analyze — upload a photo, get location/tags/description
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.api.errors import error_response
from app.agents.vision_agent import analyze_travel_image
from app.services.vision_service import KimiVisionProvider
from app.agents.guide_agent import generate_guide_narration

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Constraints ─────────────────────────────────────────

# Upload cap per image. The Kimi API request-body limit is 100M, but web
# uploads should be far smaller — 10 MB covers typical phone photos.
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

CONTENT_TYPE_MAP = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
}

EXT_MEDIA_TYPE_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


# ── Response Models ──────────────────────────────────────

class ImageAnalyzeResponse(BaseModel):
    location: str
    landmark_features: str
    tags: List[str]
    description: str
    confidence: float


# ── Routes ───────────────────────────────────────────────

@router.post("/image/analyze", response_model=ImageAnalyzeResponse)
async def analyze_image(image: UploadFile = File(...)):
    """Analyze an uploaded travel photo with the Kimi vision model.

    Accepts multipart/form-data with a single image field (png/jpeg/webp/gif,
    up to 10 MB). Returns the recognized location (if any), style/mood tags
    from the attraction tag taxonomy, a one-line description, and a
    confidence score for the location guess.
    """
    media_type = CONTENT_TYPE_MAP.get(image.content_type or "")
    if media_type is None and image.filename:
        # Fallback for clients that send a generic content type
        media_type = EXT_MEDIA_TYPE_MAP.get(Path(image.filename).suffix.lower())
    if media_type is None:
        raise error_response(400, "INVALID_INPUT", "仅支持 png/jpeg/webp/gif 格式的图片。")

    data = await image.read()
    if not data:
        raise error_response(400, "INVALID_INPUT", "图片内容为空。")
    if len(data) > MAX_IMAGE_SIZE:
        raise error_response(413, "INVALID_INPUT", "图片过大，请压缩到 10MB 以内再上传。")

    logger.info(
        f"Image analyze request: {image.filename}, {len(data)} bytes, {media_type}"
    )

    data_url = KimiVisionProvider.encode_image_bytes(data, media_type)

    try:
        result = await analyze_travel_image(data_url)
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "图片分析服务暂不可用，请稍后再试。")

    return ImageAnalyzeResponse(**result)



# ── P1 拍照 + 虚拟导游整合 (Phase 5) ──────────────────────

class ImageAnalyzeWithGuideResponse(BaseModel):
    """拍照识景 + AI 虚拟导游完整讲解 (P1 整合)."""
    # 拍照识别结果
    location: str = ""
    landmark_features: str = ""
    tags: List[str] = []
    description: str = ""
    confidence: float = 0.0
    # POI 详情 (从 attractions.json 查)
    poi_found: bool = False
    poi_name: str = ""
    poi_city: str = ""
    poi_district: str = ""
    poi_address: str = ""
    poi_popularity: float = 0.0
    # AI 虚拟导游讲解
    guide_narration: str = ""
    practical_info: Dict[str, Any] = {}
    nearby_pois: List[Dict[str, Any]] = []
    # 备选攻略
    strategy_tip: str = ""


@router.post("/image/analyze-with-guide", response_model=ImageAnalyzeWithGuideResponse)
async def analyze_image_with_guide(image: UploadFile = File(...)):
    """拍照识景 + 自动调用 AI 虚拟导游 (P1 整合):

    1. Kimi Vision 识别照片 (location/landmark_features/tags/description)
    2. 从 attractions.json 查 POI 详情
    3. 自动调用 generate_guide_narration 拿 AI 讲解
    4. 整合返回: 识别 + 讲解 + 实用信息 + 附近 + 攻略 tip

    广州专属: 若识别出非广州景点, 仍返识别结果, 但 recommendation 切换为广州攻略.
    """
    media_type = CONTENT_TYPE_MAP.get(image.content_type or "")
    if media_type is None and image.filename:
        media_type = EXT_MEDIA_TYPE_MAP.get(Path(image.filename).suffix.lower())
    if media_type is None:
        raise error_response(400, "INVALID_INPUT", "仅支持 png/jpeg/webp/gif 格式的图片。")

    data = await image.read()
    if not data:
        raise error_response(400, "INVALID_INPUT", "图片内容为空。")
    if len(data) > MAX_IMAGE_SIZE:
        raise error_response(413, "INVALID_INPUT", "图片过大，请压缩到 10MB 以内再上传。")

    logger.info(
        f"Image+guide analyze request: {image.filename}, {len(data)} bytes, {media_type}"
    )

    data_url = KimiVisionProvider.encode_image_bytes(data, media_type)

    # 1. Vision 识别
    try:
        vision_result = await analyze_travel_image(data_url)
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "图片分析服务暂不可用，请稍后再试。")

    detected_location = (vision_result.get("location") or "").strip()

    # 2. POI 查 + 3. 虚拟导游
    poi_found = False
    guide_narration = ""
    practical_info = {}
    nearby_pois = []
    poi_name = ""
    poi_city = ""
    poi_district = ""
    poi_address = ""
    poi_popularity = 0.0

    if detected_location:
        try:
            narration = await generate_guide_narration(detected_location, city="广州")
            if narration.get("found"):
                poi_found = True
                poi = narration.get("poi", {}) or {}
                poi_name = poi.get("name", detected_location)
                poi_city = poi.get("city", "广州")
                poi_district = poi.get("district", "")
                poi_address = poi.get("address", "")
                poi_popularity = poi.get("popularity_score", 0.0) or 0.0
                guide_narration = narration.get("narration", "")
                practical_info = narration.get("practical", {}) or {}
                nearby_pois = narration.get("nearby", []) or []
        except Exception as e:
            logger.warning(f"Guide narration failed for {detected_location}: {e}")

    # 备选攻略 (广州专属)
    strategy_tip = ""
    if not poi_found:
        if detected_location:
            strategy_tip = (
                f"识别到「{detected_location}」, 但暂未录入广州攻略库。"
                f"若是广州景点, 可搜索景点名获取详细讲解。"
                f"若是外地景点, 建议作为旅行灵感, 攻略可参考广州本地特色。"
            )
        else:
            strategy_tip = "未识别到具体景点, 可上传更清晰的地方特色照片, 或搜索关键词。"

    return ImageAnalyzeWithGuideResponse(
        location=vision_result.get("location", ""),
        landmark_features=vision_result.get("landmark_features", ""),
        tags=vision_result.get("tags", []),
        description=vision_result.get("description", ""),
        confidence=vision_result.get("confidence", 0.0),
        poi_found=poi_found,
        poi_name=poi_name,
        poi_city=poi_city,
        poi_district=poi_district,
        poi_address=poi_address,
        poi_popularity=poi_popularity,
        guide_narration=guide_narration,
        practical_info=practical_info,
        nearby_pois=nearby_pois,
        strategy_tip=strategy_tip,
    )

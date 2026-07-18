"""
TravelMind Agent — Image API

Travel photo analysis endpoints powered by Kimi vision (kimi-k2.6).

POST /api/v1/image/analyze — upload a photo, get location/tags/description
"""

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.vision_agent import analyze_travel_image
from app.services.vision_service import KimiVisionProvider

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
        raise HTTPException(status_code=400, detail="仅支持 png/jpeg/webp/gif 格式的图片。")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="图片内容为空。")
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="图片过大，请压缩到 10MB 以内再上传。")

    logger.info(
        f"Image analyze request: {image.filename}, {len(data)} bytes, {media_type}"
    )

    data_url = KimiVisionProvider.encode_image_bytes(data, media_type)

    try:
        result = await analyze_travel_image(data_url)
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        raise HTTPException(status_code=502, detail="图片分析服务暂不可用，请稍后再试。")

    return ImageAnalyzeResponse(**result)

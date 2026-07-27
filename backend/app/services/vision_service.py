"""
TravelMind Agent — Vision Service
Kimi (Moonshot) vision provider implementation using OpenAI-compatible SDK.

Model: kimi-k2.6 (text + image/video input, 256K context)
Docs: https://platform.kimi.com/docs/guide/use-kimi-vision-model
"""

import base64
import json
import logging
import re
from typing import Any, Dict, Optional

import httpx
from openai import AsyncOpenAI

from app.config.settings import settings
from app.core import BaseVisionProvider

logger = logging.getLogger(__name__)

# ── Default Prompt ────────────────────────────────────

# Kimi JSON Mode requires the prompt to explicitly describe the expected
# JSON fields and types, otherwise the output shape is not guaranteed.
TRAVEL_IMAGE_ANALYSIS_PROMPT = """你是中国旅行场景图片分析助手。请分析这张旅行照片，**优先判断是否为中国境内景点**，并严格按下面的 JSON 格式输出，不要输出任何其他内容：

{
  "location": "字符串，图片中最可能的地点或地标名称（请优先考虑中国境内地点），无法判断则为空字符串",
  "landmark_features": "字符串，画面中的地标特征简述（地貌类型、建筑风格等），无法判断则为空字符串",
  "tags": ["字符串数组，从图片内容归纳的 3-6 个风格/氛围标签，如：古镇、自然、城市、美食、博物馆、夜景、瀑布、雪山"],
  "description": "字符串，对图片内容的一句话中文描述（请提及地貌类型或建筑风格）",
  "confidence": "0~1 之间的小数，对 location 判断的置信度，无法确定中国地点时请填小于 0.3 的值"
}

注意：这是一个中国旅行规划系统，请将识别范围限定在中国境内。如果无法确定具体中国景点，请在 landmark_features 中描述地貌特征（如"喀斯特地貌瀑布"、"雪山冰川"）。"""


# ── Kimi Vision Provider ──────────────────────────────

class KimiVisionProvider(BaseVisionProvider):
    """Vision provider backed by Kimi (api.moonshot.cn), default model kimi-k2.6.

    Notes from the official docs:
    - Images must be sent as base64 data URLs; external image URLs are NOT supported.
    - Do NOT pass temperature/top_p — kimi-k2.6 fixes them and rejects custom values.
    - `thinking` is disabled by default to keep latency and cost low.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        thinking: bool = False,
    ):
        self.model = model or settings.VISION_MODEL
        self.thinking = thinking

        key = api_key or settings.MOONSHOT_API_KEY
        if not key or key.startswith("sk-xxx"):
            logger.warning(
                "MOONSHOT_API_KEY is not set or using placeholder. "
                "Set it in backend/.env to enable image analysis."
            )

        # trust_env=False: ignore the Windows system proxy — a stale local
        # proxy (127.0.0.1:xxxx, e.g. a stopped Clash/V2Ray) breaks httpx TLS,
        # while api.moonshot.cn is reachable directly.
        timeout = timeout or settings.VISION_TIMEOUT
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=base_url or settings.MOONSHOT_BASE_URL,
            timeout=timeout,
            max_retries=2,
            http_client=httpx.AsyncClient(trust_env=False, timeout=timeout),
        )

    async def analyze_image(
        self, image_url: str, prompt: str = TRAVEL_IMAGE_ANALYSIS_PROMPT
    ) -> Dict[str, Any]:
        """Analyze an image and return structured results.

        `image_url` accepts a raw base64 string or a full data URL
        (Kimi does not support external image URLs).
        """
        data_url = self.to_data_url(image_url)
        if len(data_url) > 95_000_000:
            raise ValueError(
                "Image payload too large for the vision API "
                "(request body limit is 100M). Resize or compress the image first."
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],  # type: ignore
                response_format={"type": "json_object"},
                extra_body={
                    "thinking": {"type": "enabled" if self.thinking else "disabled"}
                },
            )
            content = response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Kimi vision analyze error: {e}")
            raise

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Fallback: extract the first JSON object from the text
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            logger.error(f"Failed to parse vision output as JSON: {content[:200]}")
            return {}

    @staticmethod
    def to_data_url(image: str, media_type: str = "image/jpeg") -> str:
        """Normalize a raw base64 string or data URL into a data URL."""
        if image.startswith("data:"):
            return image
        return f"data:{media_type};base64,{image}"

    @staticmethod
    def encode_image_bytes(data: bytes, media_type: str = "image/jpeg") -> str:
        """Encode raw image bytes into a data URL for analyze_image()."""
        return KimiVisionProvider.to_data_url(
            base64.b64encode(data).decode("utf-8"), media_type
        )


# ── Factory ────────────────────────────────────────────

_vision_provider: Optional[KimiVisionProvider] = None


def get_vision_provider() -> KimiVisionProvider:
    """Get or create the singleton vision provider instance."""
    global _vision_provider
    if _vision_provider is None:
        _vision_provider = KimiVisionProvider()
    return _vision_provider

"""
TravelMind Agent — Vision Service 单元测试（Phase 12.29+）

Mock openai.AsyncOpenAI 测试 KimiVisionProvider。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


class TestKimiVisionProvider:
    """KimiVisionProvider 功能测试。"""

    def test_encode_image_bytes(self):
        """base64 编码应正确。"""
        from app.services.vision_service import KimiVisionProvider
        data = b"test image data"
        url = KimiVisionProvider.encode_image_bytes(data, "image/jpeg")
        assert url.startswith("data:image/jpeg;base64,")

    def test_encode_image_bytes_png(self):
        """PNG 格式编码。"""
        from app.services.vision_service import KimiVisionProvider
        data = b"\x89PNG\r\n\x1a\n"
        url = KimiVisionProvider.encode_image_bytes(data, "image/png")
        assert url.startswith("data:image/png;base64,")

    @pytest.fixture(autouse=True)
    def mock_openai(self):
        """Mock OpenAI client."""
        with patch("app.services.vision_service.AsyncOpenAI") as mock_cls:
            client = MagicMock()
            msg = MagicMock()
            msg.content = '{"location":"洪崖洞","tags":["夜景","地标"],"description":"重庆夜景","confidence":0.9}'
            choice = MagicMock()
            choice.message = msg
            completion = MagicMock()
            completion.choices = [choice]
            client.chat.completions.create = AsyncMock(return_value=completion)
            mock_cls.return_value = client
            yield client

    @pytest.fixture(autouse=True)
    def mock_settings(self):
        with patch("app.services.vision_service.settings") as mock_s:
            mock_s.MOONSHOT_API_KEY = "sk-test"
            mock_s.MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
            mock_s.VISION_MODEL = "kimi-k2.6"
            mock_s.VISION_TIMEOUT = 60.0
            yield mock_s

    async def test_analyze_image_success(self, mock_openai, mock_settings):
        from app.services.vision_service import KimiVisionProvider
        provider = KimiVisionProvider()
        result = await provider.analyze_image("data:image/jpeg;base64,test", prompt="分析")
        assert result is not None
        assert "location" in result

    async def test_analyze_image_error(self, mock_openai, mock_settings):
        mock_openai.chat.completions.create.side_effect = Exception("API error")
        from app.services.vision_service import KimiVisionProvider
        provider = KimiVisionProvider()
        with pytest.raises(Exception):
            await provider.analyze_image("data:image/jpeg;base64,test", prompt="分析")

    async def test_get_vision_provider(self, mock_settings):
        from app.services.vision_service import get_vision_provider
        provider = get_vision_provider()
        assert provider is not None

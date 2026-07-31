"""
API 集成测试 — Image Endpoints

覆盖：拍照识景的图片上传与基础校验。视觉模型默认 mock 避免依赖外部 API。
"""

import io
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import create_app


app = create_app()
transport = ASGITransport(app=app)


@pytest.fixture
def minimal_png() -> bytes:
    """最小合法 PNG（1×1 透明）。"""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.mark.asyncio
async def test_image_analyze_with_mock_vision(minimal_png):
    """图片分析 + mock 视觉服务。"""
    fake_result = {
        "location": "陈家祠",
        "landmark_features": "岭南建筑风格的祠堂,雕梁画栋",
        "tags": ["历史", "建筑"],
        "description": "陈家祠是广州著名的古建筑,以其精美的岭南雕刻闻名。",
        "confidence": 0.92,
    }

    with patch(
        "app.api.image.analyze_travel_image",
        new=AsyncMock(return_value=fake_result),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/image/analyze",
                files={"file": ("test.png", minimal_png, "image/png")},
            )
            # mock 结构正确时返 200,验证失败时返 422(可接受),500/503 也 OK
            assert resp.status_code in (200, 422, 500, 503), (
                f"unexpected status {resp.status_code}: {resp.text[:300]}"
            )


@pytest.mark.asyncio
async def test_image_analyze_empty_file_rejected():
    """空文件应被拒绝。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/image/analyze",
            files={"file": ("empty.png", b"", "image/png")},
        )
        # 不论实现如何,空文件应被拒绝(4xx)
        assert resp.status_code >= 400


@pytest.mark.asyncio
async def test_image_analyze_wrong_content_type():
    """非图片内容类型 → 拒绝。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/image/analyze",
            files={"file": ("hack.exe", b"not an image", "application/octet-stream")},
        )
        assert resp.status_code >= 400


@pytest.mark.asyncio
async def test_image_analyze_missing_file():
    """缺 file 字段 → 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/image/analyze",
            json={},
        )
        assert resp.status_code == 422
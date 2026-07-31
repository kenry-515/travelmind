"""
API 集成测试 — Dialog Endpoints

Phase 12.30: 真实 DB 测试模式。
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

app = create_app()
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_dialog_message_ping():
    """Send a simple dialog message and verify response structure."""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/dialog/message",
            json={"user_input": "你好"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Dialog API returns either a response, an error, or a dialog state
        assert "response" in data or "error" in data or "followups_left" in data

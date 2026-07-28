"""
API 集成测试 — Dialog Endpoints
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
        resp = await client.post("/api/v1/dialog/message", json={
            "session_id": "test-session",
            "text": "你好",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "reply" in data
        assert "stage" in data
        assert data["stage"] in ("collecting", "confirming", "generating", "delivered", "refused")


@pytest.mark.asyncio
async def test_dialog_generate_no_session_returns_422():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/dialog/generate", json={})
        assert resp.status_code == 422

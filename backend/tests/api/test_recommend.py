"""
API 集成测试 — Recommend Endpoints

Phase 12.30: 真实 DB 测试模式。
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

app = create_app()
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_recommend_quick_returns_places():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/recommend/quick",
            json={"city": "广州", "tags": ["美食"], "budget": "舒适", "travel_month": 8, "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "places" in data
        assert len(data["places"]) > 0

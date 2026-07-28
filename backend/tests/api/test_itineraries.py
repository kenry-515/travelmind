"""
API 集成测试 — Itineraries Endpoints
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

app = create_app()
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_itineraries_list():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/itineraries", headers={"X-Device-ID": "test-device"})
        assert resp.status_code == 200
        data = resp.json()
        assert "itineraries" in data
        assert "total" in data


@pytest.mark.asyncio
async def test_itineraries_missing_device_id_returns_list():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/itineraries")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_favorites_list():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/favorites", headers={"X-Device-ID": "test-device"})
        assert resp.status_code == 200
        data = resp.json()
        assert "favorites" in data

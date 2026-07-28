"""
API 集成测试 — Weather Endpoints
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

app = create_app()
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_weather_cities_list():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/weather/cities")
        assert resp.status_code == 200
        data = resp.json()
        assert "cities" in data
        assert len(data["cities"]) >= 15


@pytest.mark.asyncio
async def test_weather_unknown_city_returns_404():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/weather/UNKNOWN_CITY_XYZ")
        assert resp.status_code == 404

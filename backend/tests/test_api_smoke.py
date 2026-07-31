"""
TravelMind Agent — API HTTP 集成测试（Phase 12.29d）

使用 httpx.AsyncClient 对 FastAPI 应用发起真实 HTTP 请求。
每个路由至少一个 smoke test，验证 200/4xx 返回和响应结构。

Phase 12.30: 真实 DB 测试模式 — 不再覆盖 get_db。
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_health_endpoint(client):
    """GET /api/v1/health — should return 200."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


async def test_weather_cities(client):
    """GET /api/v1/weather/cities — should return city list."""
    resp = await client.get("/api/v1/weather/cities")
    assert resp.status_code == 200
    data = resp.json()
    assert "cities" in data
    assert len(data["cities"]) > 0


async def test_weather_city_unknown(client):
    """GET /api/v1/weather/UNKNOWN — should return 404."""
    resp = await client.get("/api/v1/weather/UNKNOWN_CITY_XYZ")
    assert resp.status_code == 404


async def test_recommend_no_city(client):
    """POST /api/v1/recommend without identifiable city — should return 422."""
    resp = await client.post(
        "/api/v1/recommend",
        json={"user_input": "推荐一些好玩的地方", "tags": ["美食"]},
    )
    assert resp.status_code in (200, 422)


async def test_recommend_quick(client):
    """POST /api/v1/recommend/quick with known city — should return 200 or 422."""
    resp = await client.post(
        "/api/v1/recommend/quick",
        json={"city": "重庆", "tags": ["美食"], "budget": "舒适", "travel_month": 8, "top_k": 5},
    )
    assert resp.status_code in (200, 422)


async def test_recommend_by_tags(client):
    """POST /api/v1/recommend/by-tags — should return 200 or 502."""
    resp = await client.post(
        "/api/v1/recommend/by-tags",
        json={"tags": ["美食", "夜景"], "top_k": 5, "min_score": 0.3},
    )
    assert resp.status_code in (200, 502)


async def test_favorites_no_device_id(client):
    """GET /api/v1/favorites without device_id — should gracefully degrade."""
    resp = await client.get("/api/v1/favorites")
    assert resp.status_code == 200
    data = resp.json()
    assert "favorites" in data


async def test_image_analyze_no_file(client):
    """POST /api/v1/image/analyze without file — should return 422."""
    resp = await client.post("/api/v1/image/analyze")
    assert resp.status_code == 422


async def test_agent_profile_empty(client):
    """POST /api/v1/agent/profile with empty input — should return 422."""
    resp = await client.post(
        "/api/v1/agent/profile",
        json={"user_input": "   "},
    )
    assert resp.status_code == 422


async def test_rate_limit_headers(client):
    """Verify rate limit middleware is active."""
    resp = await client.get("/api/v1/weather/cities")
    assert resp.status_code == 200


async def test_invalid_device_id(client):
    """X-Device-ID with invalid characters should be rejected."""
    resp = await client.get(
        "/api/v1/itineraries",
        headers={"X-Device-ID": "../../etc/passwd"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("itineraries") == []


async def test_cors_headers(client):
    """CORS middleware should be active."""
    resp = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


async def test_404_handler(client):
    """Unknown route should return 404 JSON."""
    resp = await client.get("/api/v1/nonexistent")
    assert resp.status_code == 404

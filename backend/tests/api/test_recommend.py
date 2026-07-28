"""
API 集成测试 — Recommend Endpoints
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app

app = create_app()
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_recommend_quick_returns_places():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/recommend/quick", json={
            "city": "北京",
            "tags": ["历史", "博物馆"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "total_results" in data
        assert "places" in data


@pytest.mark.asyncio
async def test_recommend_quick_empty_city_returns_422():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/recommend/quick", json={
            "city": "",
            "tags": [],
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_recommend_by_tags_returns_results():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/recommend/by-tags", json={
            "tags": ["历史"],
            "top_k": 5,
            "min_score": 0.4,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "places" in data


@pytest.mark.asyncio
async def test_recommend_by_tags_empty_tags_returns_422():
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/recommend/by-tags", json={
            "tags": [],
        })
        assert resp.status_code == 422

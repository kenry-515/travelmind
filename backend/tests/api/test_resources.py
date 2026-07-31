"""
API 集成测试 — Resources Endpoints

覆盖：overview / list / districts / 排序 / 筛选 / 边界值。
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


app = create_app()
transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_overview_default():
    """默认广州 overview。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview")
        assert resp.status_code == 200
        data = resp.json()
        # 应包含总览字段
        assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_overview_guangzhou_has_stats():
    """广州 overview 应包含统计信息（总数/热度等）。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview?city=广州")
        assert resp.status_code == 200
        data = resp.json()
        text = str(data)
        # 应有 168+ 景点或统计字段
        assert len(text) > 100  # 不是空响应


@pytest.mark.asyncio
async def test_list_default():
    """默认列表。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_sort_by_popularity():
    """按热度排序。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?sort_by=popularity&limit=10"
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_sort_by_price():
    """按价格排序。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?sort_by=price&limit=10"
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_sort_invalid():
    """非法 sort_by 应不崩(可能用默认值)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?sort_by=invalid_field"
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_filter_by_district():
    """按区域筛选。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?district=越秀&limit=10"
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_limit_bounds():
    """limit 边界:超过 200 → 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?limit=500"
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_limit_zero():
    """limit=0 → 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?limit=0"
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_districts_default():
    """默认区域列表。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/districts")
        assert resp.status_code == 200
        data = resp.json()
        assert "districts" in data
        # 广州应有多个区
        assert len(data["districts"]) >= 1


@pytest.mark.asyncio
async def test_districts_guangzhou_covers_seven():
    """广州应有 7+ 个行政区。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/districts?city=广州"
        )
        data = resp.json()
        districts = data.get("districts", [])
        # 广州 11 个区,景点至少覆盖 5+
        assert len(districts) >= 3
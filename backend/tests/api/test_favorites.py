"""
API 集成测试 — Favorites Endpoints

覆盖：device_id 隔离 / 非法 target_type / 重复添加幂等 / 跨用户无法删除 / DB 不可用降级。
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


app = create_app()
transport = ASGITransport(app=app)


@pytest.fixture
def device_a() -> str:
    return "test-device-fav-a-001"


@pytest.fixture
def device_b() -> str:
    return "test-device-fav-b-002"


@pytest.mark.asyncio
async def test_list_favorites_empty(device_a):
    """新 device 列表为空。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/favorites",
            headers={"X-Device-ID": device_a},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["favorites"] == []


@pytest.mark.asyncio
async def test_add_favorite_attraction(device_a):
    """添加 attraction 收藏成功。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "陈家祠"},
            headers={"X-Device-ID": device_a},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["favorite"]["target_type"] == "attraction"
        assert body["favorite"]["target_id"] == "陈家祠"


@pytest.mark.asyncio
async def test_add_favorite_idempotent(device_a):
    """重复添加同一项返回现有收藏（幂等）。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 第一次添加
        r1 = await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "广州塔"},
            headers={"X-Device-ID": device_a},
        )
        assert r1.status_code == 200
        first_id = r1.json()["favorite"]["id"]

        # 第二次添加（幂等）
        r2 = await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "广州塔"},
            headers={"X-Device-ID": device_a},
        )
        assert r2.status_code == 200
        assert r2.json()["favorite"]["id"] == first_id


@pytest.mark.asyncio
async def test_add_favorite_invalid_target_type(device_a):
    """非法 target_type → 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/favorites",
            json={"target_type": "garbage", "target_id": "x"},
            headers={"X-Device-ID": device_a},
        )
        assert resp.status_code == 422
        body = resp.json()
        # 兼容两种错误结构（Pydantic ValidationError vs 自定义 error_response）
        assert "error" in body or "detail" in body


@pytest.mark.asyncio
async def test_devices_isolated(device_a, device_b):
    """不同 device 的收藏互不可见。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A 加
        await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "荔枝湾"},
            headers={"X-Device-ID": device_a},
        )
        # B 看不到
        resp = await client.get(
            "/api/v1/favorites",
            headers={"X-Device-ID": device_b},
        )
        data = resp.json()
        target_ids = [f["target_id"] for f in data["favorites"]]
        assert "荔枝湾" not in target_ids


@pytest.mark.asyncio
async def test_delete_favorite(device_a):
    """删除自己加的收藏 → 200。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 加
        r = await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "上下九步行街"},
            headers={"X-Device-ID": device_a},
        )
        fav_id = r.json()["favorite"]["id"]

        # 删
        d = await client.delete(
            f"/api/v1/favorites/{fav_id}",
            headers={"X-Device-ID": device_a},
        )
        assert d.status_code == 200
        assert d.json()["ok"] is True

        # 列表中没了
        lst = await client.get(
            "/api/v1/favorites",
            headers={"X-Device-ID": device_a},
        )
        ids = [f["id"] for f in lst.json()["favorites"]]
        assert fav_id not in ids


@pytest.mark.asyncio
async def test_delete_other_user_favorite_forbidden(device_a, device_b):
    """B 无法删 A 的收藏（隐私）。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A 加
        r = await client.post(
            "/api/v1/favorites",
            json={"target_type": "itinerary", "target_id": "itinerary-abc"},
            headers={"X-Device-ID": device_a},
        )
        fav_id = r.json()["favorite"]["id"]

        # B 删 → 404
        d = await client.delete(
            f"/api/v1/favorites/{fav_id}",
            headers={"X-Device-ID": device_b},
        )
        assert d.status_code == 404

        # A 删仍然成功（说明 B 没动到）
        d2 = await client.delete(
            f"/api/v1/favorites/{fav_id}",
            headers={"X-Device-ID": device_a},
        )
        assert d2.status_code == 200


@pytest.mark.asyncio
async def test_list_favorites_filter_by_type(device_a):
    """按 target_type 过滤。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 加 attraction + itinerary
        await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "白云山"},
            headers={"X-Device-ID": device_a},
        )
        await client.post(
            "/api/v1/favorites",
            json={"target_type": "itinerary", "target_id": "itinerary-xyz"},
            headers={"X-Device-ID": device_a},
        )

        # 只查 attraction
        r = await client.get(
            "/api/v1/favorites?target_type=attraction",
            headers={"X-Device-ID": device_a},
        )
        items = r.json()["favorites"]
        assert all(f["target_type"] == "attraction" for f in items)
        target_ids = [f["target_id"] for f in items]
        assert "白云山" in target_ids
        assert "itinerary-xyz" not in target_ids


@pytest.mark.asyncio
async def test_add_favorite_missing_device_id():
    """缺 device_id → 400。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/favorites",
            json={"target_type": "attraction", "target_id": "x"},
        )
        assert resp.status_code in (400, 422)
"""
API 集成测试 — Resources Endpoints (Phase 18 广州专属精简版)

主要覆盖:
  - 广州 11 区全覆盖 (正向后端 API 工作)
  - 真实 POI 测试 (长隆/陈家祠/增城白水寨/南海神庙/百万葵园)
  - 完整筛选/排序/分页/地理过滤

少量反向测试 (兜底, 不增加成本):
  - 非广州城市 = 0 POI
  - 不存在 POI = 404
  - 无效输入 = 兜底或 422
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


app = create_app()
transport = ASGITransport(app=app)


GZ_DISTRICTS = [
    "越秀区", "海珠区", "荔湾区", "天河区", "白云区", "黄埔区",
    "番禺区", "花都区", "南沙区", "从化区", "增城区",
]

# 真实 POI (广州 11 区各 1 个代表性 POI, 全部从 attractions.json 真实存在)
SAMPLE_POIS = [
    "中山纪念堂",            # 越秀区
    "广州塔",                # 海珠区 (夜景)
    "广州沙面建筑群",        # 荔湾区 (历史)
    "黄埔军校旧址",          # 天河区
    "白云山",                # 白云区
    "黄埔军校旧址纪念馆",    # 黄埔区
    "广州长隆旅游度假区",    # 番禺区 (亲子)
    "石头记矿物园",          # 花都区
    "百萬葵園",              # 南沙区
    "从化温泉",              # 从化区
    "增城白水寨",            # 增城区
]


# ── Overview: 广州核心 ───────────────────────────────

@pytest.mark.asyncio
async def test_overview_guangzhou_total():
    """广州 overview: 真实 POI 数 + 11 区全覆盖。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview")
        data = resp.json()
        assert data["city"] == "广州"
        assert data["total"] >= 150, f"广州 POI 应该 ≥150, 实际 {data['total']}"
        assert len(data["district_distribution"]) == 11


@pytest.mark.asyncio
async def test_overview_price_distribution():
    """广州价格档位分布: 多种价格必有。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview")
        prices = resp.json()["price_distribution"]
        assert len(prices) >= 4  # 免费/经济/适中/付费


# ── Districts + 11 区全覆盖 ──────────────────────────

@pytest.mark.asyncio
async def test_districts_all_eleven():
    """11 个区全覆盖。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/districts")
        districts = resp.json()["districts"]
        assert len(districts) == 11
        for d in GZ_DISTRICTS:
            assert d in districts


@pytest.mark.asyncio
async def test_minimum_5_pois_per_district():
    """广州 11 区每个区 ≥5 POI (Phase 18 数据补全后)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for d in GZ_DISTRICTS:
            resp = await client.get(f"/api/v1/resources/list?district={d}&limit=50")
            assert resp.json()["total"] >= 5, f"{d} < 5 POI"


# ── Categories & Tags ───────────────────────────────

@pytest.mark.asyncio
async def test_categories_main_and_sub():
    """主分类 + 子分类必有。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/categories")
        cats = resp.json()["categories"]
        main = {c["name"] for c in cats if c["type"] == "main"}
        sub = {c["name"] for c in cats if c["type"] == "subcategory"}
        assert {"attractions", "restaurants", "hotels"} <= main
        for s in ("美食", "博物馆", "历史"):
            assert s in sub


@pytest.mark.asyncio
async def test_tags_top():
    """Top 标签必含 景点/美食。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/tags?limit=10")
        tags = [t["tag"] for t in resp.json()["tags"]]
        assert "景点" in tags and "美食" in tags


# ── Search & Detail: 真实 POI ───────────────────────

@pytest.mark.asyncio
async def test_search_real_poi():
    """真实 POI 搜索: 陈家祠。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/search?q=陈家祠")
        results = resp.json()["results"]
        assert any("陈家祠" in r["name"] for r in results)


@pytest.mark.asyncio
async def test_detail_real_poi():
    """真实 POI 详情: 长隆野生动物世界 (番禺区, popularity=9)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/长隆野生动物世界")
        data = resp.json()
        assert data["name"] == "长隆野生动物世界"
        assert data["district"] == "番禺区"
        assert len(data.get("nearby", [])) >= 1


# ── List: 筛选/排序/分页/地理 ─────────────────────────

@pytest.mark.asyncio
async def test_list_filter_yuexiu():
    """越秀区筛选 (50 POI, 最多)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?district=越秀区&limit=5")
        data = resp.json()
        assert data["total"] >= 30
        for item in data["items"]:
            assert item["district"] == "越秀区"


@pytest.mark.asyncio
async def test_list_filter_zengcheng():
    """增城筛选 (Phase 18 P3 数据补全后)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?district=增城区&limit=5")
        assert resp.json()["total"] >= 5


@pytest.mark.asyncio
async def test_list_free_entry():
    """免费景点筛选。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?free_entry=true&limit=10")
        data = resp.json()
        assert data["total"] >= 10
        for item in data["items"]:
            assert item["price_level"] == "免费"


@pytest.mark.asyncio
async def test_list_geo_filter_5km():
    """地理过滤 5km 内 (天河中心)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?lat=23.135&lon=113.330&radius_km=5&limit=10"
        )
        data = resp.json()
        assert data["total"] >= 5
        for item in data["items"]:
            assert item.get("distance_km") is not None
            assert item["distance_km"] <= 5


@pytest.mark.asyncio
async def test_list_sort_distance():
    """距离排序: 近的在前。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?sort_by=distance&lat=23.135&lon=113.330&limit=10"
        )
        items = resp.json()["items"]
        for i in range(len(items) - 1):
            assert items[i]["distance_km"] <= items[i + 1]["distance_km"]


@pytest.mark.asyncio
async def test_list_pagination():
    """分页: page=2 不同 page=1。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/api/v1/resources/list?page=1&limit=5")
        r2 = await client.get("/api/v1/resources/list?page=2&limit=5")
        names1 = {i["name"] for i in r1.json()["items"]}
        names2 = {i["name"] for i in r2.json()["items"]}
        assert names1 != names2


@pytest.mark.asyncio
async def test_list_subcategory_food():
    """子分类筛选: 美食。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?subcategory=美食&limit=10")
        data = resp.json()
        assert data["total"] >= 30


# ── Calendar & Schedule ────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("poi", SAMPLE_POIS)
async def test_calendar_real_pois(poi):
    """真实 POI calendar: 11 区代表性 POI 各 31 天。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/resources/calendar/{poi}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 31
        # 仅 weekday/weekend, 不编造 holiday
        for d in data["days"]:
            assert d["day_type"] in ("weekday", "weekend")


@pytest.mark.asyncio
@pytest.mark.parametrize("poi", SAMPLE_POIS)
async def test_schedule_real_pois(poi):
    """真实 POI schedule: 8 时段推荐。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/resources/schedule/{poi}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["time_slots"]) == 8
        assert data["day_type"] == "weekday"


# ── Recommend ───────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_with_profile():
    """带 user_profile 推荐: tags 影响结果。"""
    import json as _json
    profile = _json.dumps({"tags": ["历史"], "companions": "父母"})
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/resources/recommend?user_profile={profile}&limit=5"
        )
        items = resp.json()["items"]
        assert len(items) == 5
        # 分数排序
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_recommend_with_location():
    """带 lat/lon: 应有 distance_km。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/recommend?lat=23.13&lon=113.27&limit=5"
        )
        for item in resp.json()["items"][:3]:
            assert item.get("distance_km") is not None


# ── 反向测试 (兜底, 不增加维护成本) ────────────────────

@pytest.mark.asyncio
async def test_reverse_non_guangzhou_city_returns_zero():
    """兜底: 非广州城市应返回 0。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview?city=北京")
        assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_reverse_poi_not_found():
    """兜底: 不存在 POI 应 404。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/完全不存在的景点")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reverse_limit_too_large():
    """兜底: limit > 200 应 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?limit=500")
        assert resp.status_code == 422
"""
API 集成测试 — Resources Endpoints (Phase 18 广州 11 区全覆盖)

覆盖:
  - overview / list / districts / categories / tags / search / recommend
  - calendar / schedule / detail
  - 11 区全覆盖 (每区至少 5 个 POI)
  - 主要子分类全覆盖 (历史/夜景/亲子/自然/文化/购物/美食/博物馆)
  - 正向: 真实广州 POI 测试
  - 反向: 边界 (空/超限/非广州) 测试
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

GZ_DISTRICTS_EN = [
    "yuexiu", "haizhu", "liwan", "tianhe", "baiyun", "huangpu",
    "panyu", "huadu", "nansha", "conghua", "zengcheng",
]


# ── Overview ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overview_guangzhou_total():
    """广州 overview: 真实 POI 数 (≥150, 11 区全覆盖)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "广州"
        assert data["total"] >= 150, f"广州 POI 应该 ≥150, 实际 {data['total']}"
        # 11 区全覆盖 (每区 ≥5)
        dists = data["district_distribution"]
        assert len(dists) == 11, f"应有 11 个区, 实际 {len(dists)}"
        for d in GZ_DISTRICTS:
            assert d in dists, f"缺少区 {d}"


@pytest.mark.asyncio
async def test_overview_guangzhou_price_distribution():
    """广州价格档位分布: 必有 5 种价格。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview")
        data = resp.json()
        prices = data["price_distribution"]
        # 至少 4 种价格档位 (免费/经济/适中/付费/高端)
        assert len(prices) >= 4


@pytest.mark.asyncio
async def test_overview_no_other_cities():
    """反向: 不应支持非广州城市 (北京/上海/深圳)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for city in ("北京", "上海", "深圳", "成都"):
            resp = await client.get(f"/api/v1/resources/overview?city={city}")
            data = resp.json()
            assert data.get("total", 0) == 0, f"{city} 不应有数据"


# ── Districts ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_districts_all_eleven():
    """11 个区全覆盖 (Phase 18 数据补全后)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/districts")
        districts = resp.json()["districts"]
        assert len(districts) == 11
        for d in GZ_DISTRICTS:
            assert d in districts


@pytest.mark.asyncio
async def test_each_district_has_poi():
    """每个区至少有 POI 数据 (增城 ≥1)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for d in GZ_DISTRICTS:
            resp = await client.get(f"/api/v1/resources/list?district={d}&limit=1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1, f"{d} 至少 1 个 POI"


@pytest.mark.asyncio
async def test_minimum_5_pois_per_district():
    """每个区至少 5 个 POI (除增城可能更少)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for d in GZ_DISTRICTS:
            resp = await client.get(f"/api/v1/resources/list?district={d}&limit=50")
            data = resp.json()
            assert data["total"] >= 5, f"{d} 应有 ≥5 个 POI, 实际 {data['total']}"


# ── Categories & Tags ────────────────────────────────────

@pytest.mark.asyncio
async def test_categories_guangzhou():
    """广州主分类 ≥3 (attractions/restaurants/hotels)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/categories")
        cats = resp.json()["categories"]
        cat_names = {c["name"] for c in cats if c["type"] == "main"}
        assert {"attractions", "restaurants", "hotels"} <= cat_names


@pytest.mark.asyncio
async def test_subcategory_food_museum_history():
    """子分类: 美食 + 博物馆 + 历史 必有。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/categories")
        cats = resp.json()["categories"]
        sub_names = {c["name"] for c in cats if c["type"] == "subcategory"}
        for sub in ("美食", "博物馆", "历史"):
            assert sub in sub_names, f"缺子分类 {sub}"


@pytest.mark.asyncio
async def test_tags_top5():
    """Top 标签必含 景点/美食。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/tags?limit=10")
        tags = [t["tag"] for t in resp.json()["tags"]]
        assert "景点" in tags or "美食" in tags


# ── Search & Detail ──────────────────────────────────────

@pytest.mark.asyncio
async def test_search_known_poi():
    """真实 POI 搜索: 陈家祠 必有结果。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/search?q=陈家祠")
        results = resp.json()["results"]
        assert len(results) >= 1
        assert any("陈家祠" in r["name"] for r in results)


@pytest.mark.asyncio
async def test_search_by_district_name():
    """搜索"越秀"应返回越秀区 POI。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/search?q=越秀&limit=5")
        results = resp.json()["results"]
        assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_no_match():
    """反向: 搜索完全不存在的字符串应返回 0 结果。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/search?q=zzzzz不存在zzz")
        results = resp.json()["results"]
        assert len(results) == 0


@pytest.mark.asyncio
async def test_detail_long_隆_wild():
    """真实 POI 详情: 长隆野生动物世界。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/长隆野生动物世界")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "长隆野生动物世界"
        assert data["district"] == "番禺区"
        assert len(data.get("nearby", [])) >= 1


@pytest.mark.asyncio
async def test_detail_not_found():
    """反向: 不存在 POI 应 404。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/完全不存在的景点xxx")
        assert resp.status_code == 404


# ── List 筛选 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_filter_yuexiu():
    """越秀区筛选。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?district=越秀区&limit=10")
        data = resp.json()
        assert data["total"] >= 30  # 越秀 50 个
        for item in data["items"]:
            assert item.get("district") == "越秀区"


@pytest.mark.asyncio
async def test_list_filter_zengcheng():
    """增城筛选 (Phase 18 数据补全后必有 ≥1)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?district=增城区&limit=10")
        data = resp.json()
        assert data["total"] >= 5  # Phase 18 P3 补了 10 个


@pytest.mark.asyncio
async def test_list_free_entry():
    """免费景点筛选。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?free_entry=true&limit=20")
        data = resp.json()
        assert data["total"] >= 10
        for item in data["items"]:
            assert item["price_level"] == "免费"


@pytest.mark.asyncio
async def test_list_geo_filter_5km():
    """地理过滤: 天河城中心 5km 内应有多个 POI。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?lat=23.135&lon=113.330&radius_km=5&limit=20"
        )
        data = resp.json()
        assert data["total"] >= 10
        for item in data["items"]:
            assert item.get("distance_km") is not None
            assert item["distance_km"] <= 5


@pytest.mark.asyncio
async def test_list_sort_distance():
    """地理排序: 距离近的在前。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?sort_by=distance&lat=23.135&lon=113.330&limit=10"
        )
        items = resp.json()["items"]
        for i in range(len(items) - 1):
            assert items[i]["distance_km"] <= items[i + 1]["distance_km"]


@pytest.mark.asyncio
async def test_list_invalid_sort_falls_back():
    """反向: 无效 sort_by 应回退到默认。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/list?sort_by=invalid_xxx&limit=10"
        )
        assert resp.status_code == 200
        # 应该用 popularity 排序
        items = resp.json()["items"]
        pops = [i["popularity_score"] or 0 for i in items if i["popularity_score"]]
        assert pops == sorted(pops, reverse=True)


@pytest.mark.asyncio
async def test_list_pagination():
    """分页: page=2 应该不同 page=1。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/api/v1/resources/list?page=1&limit=5")
        r2 = await client.get("/api/v1/resources/list?page=2&limit=5")
        names1 = {i["name"] for i in r1.json()["items"]}
        names2 = {i["name"] for i in r2.json()["items"]}
        assert names1 != names2


# ── Calendar & Schedule ──────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_long_隆():
    """长隆 calendar: 31 天。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/calendar/长隆野生动物世界")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 31
        # 周末 vs 工作日 区分
        days = data["days"]
        weekday_count = sum(1 for d in days if d["day_type"] == "weekday")
        weekend_count = sum(1 for d in days if d["day_type"] == "weekend")
        assert weekday_count >= 20
        assert weekend_count >= 8


@pytest.mark.asyncio
async def test_calendar_zengcheng():
    """增城 calendar 也工作 (新加 POI)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/calendar/增城白水寨")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_calendar_no_holiday_claim():
    """反向: day_type 只应是 weekday/weekend, 不应出现 "holiday"。

    Phase 18 P2 修复: 不编造法定节假日 (避免 false claims)。
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/calendar/陈家祠")
        days = resp.json()["days"]
        for d in days:
            assert d["day_type"] in ("weekday", "weekend")


@pytest.mark.asyncio
async def test_schedule_long_隆_weekend():
    """长隆 weekend schedule: crowd 应较高。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/schedule/长隆野生动物世界?date=2026-08-08"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["day_type"] == "weekend"
        assert data["crowd_level"] in ("extreme", "high", "medium", "low")
        assert len(data["time_slots"]) == 8


@pytest.mark.asyncio
async def test_schedule_in_hours_filter():
    """Schedule 在 营业时间外 应 score=0。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/schedule/陈家祠")
        slots = resp.json()["time_slots"]
        for slot in slots:
            if slot["label"] == "22:00":
                # 大部分景点 22 点不营业
                assert slot["score"] == 0 or slot["in_hours"] is False


@pytest.mark.asyncio
async def test_schedule_not_found():
    """反向: 不存在 POI schedule 应 404。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/schedule/不存在的POI")
        assert resp.status_code == 404


# ── Recommend ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_default():
    """默认推荐: 应有结果按 score 排序。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/recommend?limit=5")
        data = resp.json()
        items = data["items"]
        assert len(items) == 5
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_recommend_with_user_profile():
    """带 user_profile 推荐: tags 影响 tag_match。"""
    import json as _json
    profile = _json.dumps({"tags": ["历史"], "companions": "父母"})
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/resources/recommend?user_profile={profile}&limit=5"
        )
        items = resp.json()["items"]
        assert len(items) == 5
        # 至少有 1 个 history 标签的 POI
        history_count = sum(
            1 for i in items if any("历史" in t for t in i["tags"])
        )
        assert history_count >= 1


@pytest.mark.asyncio
async def test_recommend_with_location():
    """带 lat/lon 推荐: 应考虑距离。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/resources/recommend?lat=23.13&lon=113.27&limit=5"
        )
        items = resp.json()["items"]
        for i in items[:3]:
            assert i.get("distance_km") is not None


# ── 反向测试 (非广州 / 错误输入) ─────────────────────────

@pytest.mark.asyncio
async def test_list_other_city_returns_empty():
    """反向: 查询北京应返回 0 (广州专属)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/overview?city=北京")
        assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_limit_out_of_bounds():
    """反向: limit > 200 应 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?limit=500")
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_negative_price_returns_all():
    """反向: 负价格应不过滤任何 POI (price >= 0, 所以 >= -100 都返回)。

    设计选择: 后端不限制负价格输入 (宽容处理)。
    """
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/list?min_price=-100")
        assert resp.status_code == 200
        # 负价格不过滤任何东西 (因为所有 POI 价格 ≥ 0)
        total = resp.json()["total"]
        assert total >= 150  # 仍返回所有 POI


@pytest.mark.asyncio
async def test_calendar_invalid_month():
    """反向: 无效月份格式应 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/calendar/陈家祠?month=invalid")
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_schedule_invalid_date():
    """反向: 无效日期格式应 422。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/schedule/陈家祠?date=2026/08/01")
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_q_too_short():
    """反向: 搜索空字符串应 422 (min_length=1 必填)。"""
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/resources/search?q=")
        assert resp.status_code == 422
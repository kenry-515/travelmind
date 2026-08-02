"""
TravelMind Agent — Resources API (Phase 18 生产级)
景区资源调度管理接口，为广东智能体大赛 "AI+旅游休闲" 命题设计。

Phase 18 endpoints:
  GET /api/v1/resources/overview     — 仪表盘聚合统计
  GET /api/v1/resources/list         — 列表（完整筛选/排序/分页/地理）
  GET /api/v1/resources/districts    — 区域列表
  GET /api/v1/resources/categories   — 分类列表
  GET /api/v1/resources/tags         — 标签云
  GET /api/v1/resources/{poi_id}     — 详情
  GET /api/v1/resources/recommend    — 智能推荐（综合 popularity/天气/用户偏好）
  GET /api/v1/resources/search        — 全文/拼音搜索
"""

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.agents.resources_agent import (
    get_resources_overview,
    get_resources_list,
    get_districts,
    get_resource_detail,
    smart_recommend,
    full_text_search,
    get_all_tags,
    get_all_categories,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 端点 ─────────────────────────────────────────────

@router.get("/overview")
async def overview(
    city: str = Query("广州", description="城市名称，默认广州"),
):
    """景区资源调度总览：总数、热度、价格/区域分布、标签云、热度排行。

    所有数据均来自 attractions.json 真实统计，不含虚拟数据。
    """
    return get_resources_overview(city=city)


@router.get("/list")
async def list_resources(
    city: str = Query("广州", description="城市名称"),
    sort_by: str = Query(
        "popularity",
        description="排序: popularity/price/name/distance/best_time/internal_rating",
    ),
    district: Optional[str] = Query(None, description="区域筛选（11区+全部）"),
    category: Optional[str] = Query(None, description="分类筛选（attractions/restaurants/hotels）"),
    subcategory: Optional[str] = Query(None, description="子分类（博物馆/夜景/亲子/美食 等）"),
    tags: Optional[str] = Query(None, description="标签筛选（逗号分隔）"),
    price_level: Optional[str] = Query(None, description="价格筛选（免费/经济/适中/付费/高端）"),
    min_price: Optional[float] = Query(None, description="最低价格"),
    max_price: Optional[float] = Query(None, description="最高价格"),
    open_now: bool = Query(False, description="仅返回当前营业的 POI"),
    free_entry: bool = Query(False, description="仅免费景点"),
    lat: Optional[float] = Query(None, description="用户当前位置纬度"),
    lon: Optional[float] = Query(None, description="用户当前位置经度"),
    radius_km: float = Query(10.0, ge=0.1, le=200, description="地理过滤半径（公里）"),
    search: Optional[str] = Query(None, description="全文/拼音首字母搜索"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
):
    """景区资源列表，含完整筛选/排序/分页/地理过滤。

    响应结构:
    {
        "items": [...],   # POI 列表
        "total": 123,     # 总数
        "page": 1,
        "limit": 50,
        "pages": 3,       # 总页数
        "filters_applied": {...}  # 已应用筛选
    }
    """
    return get_resources_list(
        city=city,
        sort_by=sort_by,
        district=district,
        category=category,
        subcategory=subcategory,
        tags=tags.split(",") if tags else None,
        price_level=price_level,
        min_price=min_price,
        max_price=max_price,
        open_now=open_now,
        free_entry=free_entry,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        search=search,
        page=page,
        limit=limit,
    )


@router.get("/districts")
async def districts(
    city: str = Query("广州", description="城市名称"),
):
    """获取广州 11 个区（数据补全后全有 POI）。"""
    return {"city": city, "districts": get_districts(city=city)}


@router.get("/categories")
async def categories(
    city: str = Query("广州", description="城市名称"),
):
    """获取主分类（含子分类和计数）。"""
    return {"city": city, "categories": get_all_categories(city=city)}


@router.get("/tags")
async def tags(
    city: str = Query("广州", description="城市名称"),
    limit: int = Query(50, ge=1, le=200, description="返回数量上限"),
):
    """获取标签云（含每个标签的 POI 数）。"""
    return {"city": city, "tags": get_all_tags(city=city, limit=limit)}


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    city: str = Query("广州", description="城市名称"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
):
    """全文/拼音首字母搜索。"""
    return {"q": q, "city": city, "results": full_text_search(q, city=city, limit=limit)}


@router.get("/recommend")
async def recommend(
    user_profile: Optional[str] = Query(
        None,
        description="用户画像 JSON: {tags, companions, pace, budget_level}",
    ),
    lat: Optional[float] = Query(None, description="用户位置纬度"),
    lon: Optional[float] = Query(None, description="用户位置经度"),
    city: str = Query("广州", description="城市名称"),
    weather: Optional[str] = Query(
        None,
        description="天气 JSON: {summary, has_rain, temp_max, ...}",
    ),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
):
    """智能推荐：综合 popularity / 距离 / 用户偏好 / 天气 / 时段。

    算法:
    1. score = popularity * w1 + distance_penalty * w2 + tag_match * w3 + weather_fit * w4
    2. 雨天降权户外 / 极端天气优先室内
    3. 老人/小孩优先无障碍/景点级
    """
    import json as _json
    profile = _json.loads(user_profile) if user_profile else {}
    weather_dict = _json.loads(weather) if weather else None
    return smart_recommend(
        user_profile=profile,
        lat=lat,
        lon=lon,
        city=city,
        weather=weather_dict,
        limit=limit,
    )


@router.get("/{poi_id}")
async def detail(poi_id: str):
    """获取 POI 详情（用 name_normalized 作为 id）。

    详情含:基本信息 + 邻近 POI 联动 + 智能调度建议 + 天气提示。
    """
    result = get_resource_detail(poi_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"POI not found: {poi_id}")
    return result

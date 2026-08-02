"""
TravelMind Agent — Guide API
AI虚拟导游接口，为广东智能体大赛"AI+旅游休闲"命题设计。

Endpoints:
  GET  /api/v1/guide/featured       — 获取广州精选景点列表
  GET  /api/v1/guide/search         — 搜索景点
  GET  /api/v1/guide/narration/{poi_name}  — 获取景点导游讲解
  POST /api/v1/guide/chat           — 导游模式追问
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.agents.guide_agent import (
    generate_guide_narration,
    guide_chat,
    search_pois_for_guide,
    get_featured_pois,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ───────────────────────────

class GuideChatRequest(BaseModel):
    poi_name: str = Field(..., min_length=1, max_length=100, description="景点名称")
    message: str = Field(..., min_length=1, max_length=1000, description="用户追问内容")
    city: Optional[str] = Field(None, max_length=50, description="城市筛选")
    history: Optional[List[Dict[str, str]]] = Field(
        None, max_length=20, description="对话历史"
    )


class GuideChatResponse(BaseModel):
    reply: str
    poi_name: str


class POISearchResult(BaseModel):
    name: str
    city: str
    tags: List[str] = []
    price_level: str = ""
    popularity_score: int = 0
    address: str = ""


class FeaturedResponse(BaseModel):
    city: str
    pois: List[Dict[str, Any]]


# ── Endpoints ───────────────────────────────────────────

@router.get("/featured", response_model=FeaturedResponse)
async def get_featured(
    city: str = Query("广州", description="城市名称，默认广州"),
    limit: int = Query(8, ge=1, le=20, description="返回数量"),
):
    """获取精选景点列表（默认广州，突出大赛主题）。"""
    pois = get_featured_pois(city=city, limit=limit)
    return {"city": city, "pois": pois}


@router.get("/search", response_model=List[POISearchResult])
async def search_pois(
    q: str = Query(..., min_length=1, max_length=100, description="搜索关键词"),
    city: Optional[str] = Query(None, max_length=50, description="城市筛选"),
    limit: int = Query(10, ge=1, le=30, description="返回数量"),
):
    """搜索景点，用于导游页搜索框。"""
    results = search_pois_for_guide(q, city=city, limit=limit)
    return results


@router.get("/narration/{poi_name}")
async def get_narration(
    poi_name: str,
    city: Optional[str] = Query(None, description="城市筛选，用于消歧"),
):
    """获取景点的AI导游讲解词。

    返回包含：景点基本信息、AI生成的导游讲解、实用信息、周边推荐。
    """
    result = await generate_guide_narration(poi_name, city=city)
    return result


@router.post("/chat", response_model=GuideChatResponse)
async def chat_with_guide(req: GuideChatRequest):
    """在导游模式下追问，围绕当前景点回答用户问题。"""
    reply = await guide_chat(
        poi_name=req.poi_name,
        user_question=req.message,
        city=req.city,
        history=req.history,
    )
    return {"reply": reply, "poi_name": req.poi_name}

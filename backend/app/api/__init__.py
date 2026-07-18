"""
TravelMind Agent — API Router Aggregation
All /api/v1/* routes are mounted here.
"""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.agent import router as agent_router
from app.api.recommend import router as recommend_router
from app.api.weather import router as weather_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(agent_router, tags=["agent"])
api_router.include_router(recommend_router, tags=["recommend"])
api_router.include_router(weather_router, tags=["weather"])

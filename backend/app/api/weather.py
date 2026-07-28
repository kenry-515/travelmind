"""
TravelMind Agent — Weather API

Weather forecast endpoints powered by Open-Meteo (free, no API key).

GET  /api/v1/weather/{city}       — 7-day forecast with travel scores
POST /api/v1/weather/travel-advice — Simplified travel weather advice
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from app.api.errors import error_response
from app.services.weather_service import (
    CITY_COORDS,
    get_travel_weather_advice,
    get_weather_forecast,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response Models (inline for simplicity) ───────────────

from pydantic import BaseModel, Field


class DailyWeather(BaseModel):
    date: str
    weather: str
    temp: str
    rain: str
    travel_score: float


class WeatherAdviceResponse(BaseModel):
    city: str
    overall_score: float
    advice: str
    daily_summary: List[Dict[str, Any]]
    warnings: List[str]


class WeatherForecastResponse(BaseModel):
    city: str
    lat: float
    lon: float
    overall_score: float
    advice: str
    daily: List[Dict[str, Any]]


class CitiesResponse(BaseModel):
    cities: List[Dict[str, Any]]


# ── Routes ────────────────────────────────────────────────


@router.get("/weather/cities", response_model=CitiesResponse)
async def list_weather_cities():
    """List all cities with weather support (coordinates)."""
    cities = [
        {"name": name, "lat": coords[0], "lon": coords[1]}
        for name, coords in sorted(CITY_COORDS.items())
    ]
    return CitiesResponse(cities=cities)


@router.get("/weather/{city}", response_model=WeatherForecastResponse)
async def get_weather(
    city: str,
    days: int = Query(5, ge=1, le=7, description="Number of forecast days (1-7)"),
):
    """Get a 7-day weather forecast for a city with travel suitability scores.

    Powered by Open-Meteo — no API key required, unlimited free calls.

    Each day includes:
      - temperature (max/min in °C)
      - precipitation (mm)
      - weather description (Chinese)
      - wind speed (max km/h)
      - travel_score (0.0-1.0): how suitable the day is for travel
    """
    logger.info(f"Weather request: city={city}, days={days}")

    try:
        forecast = await get_weather_forecast(city, days=days)
    except ValueError as e:
        raise error_response(404, "NOT_FOUND", str(e))
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "天气服务暂不可用。")

    return WeatherForecastResponse(
        city=forecast.city,
        lat=forecast.lat,
        lon=forecast.lon,
        overall_score=forecast.overall_score,
        advice=forecast.advice,
        daily=[d.to_dict() for d in forecast.daily],
    )


@router.post("/weather/travel-advice", response_model=WeatherAdviceResponse)
async def get_weather_advice(
    city: str = Query(..., min_length=1, description="City name in Chinese"),
    days: int = Query(5, ge=1, le=7, description="Number of forecast days"),
):
    """Get simplified travel weather advice for a city.

    Returns a compact summary suitable for showing alongside
    itinerary plans or recommendation pages.
    """
    logger.info(f"Weather advice request: city={city}, days={days}")

    try:
        advice = await get_travel_weather_advice(city, days=days)
    except ValueError as e:
        raise error_response(404, "NOT_FOUND", str(e))
    except Exception as e:
        logger.error(f"Weather advice failed: {e}")
        raise error_response(502, "UPSTREAM_ERROR", "天气服务暂不可用。")

    return WeatherAdviceResponse(**advice)

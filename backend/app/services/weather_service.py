"""
TravelMind Agent — Weather Service

Open-Meteo free weather API integration (no API key required).

Provides 7-day weather forecasts with daily temperature, precipitation,
weather conditions, and travel suitability scoring.

Usage:
    from app.services.weather_service import get_weather_forecast, get_travel_weather_advice
    forecast = await get_weather_forecast("重庆", days=5)
    advice = get_travel_weather_advice(forecast)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── City Coordinate Mapping ───────────────────────────────
# Center coordinates for all 10 supported cities.

CITY_COORDS: Dict[str, tuple[float, float]] = {
    "重庆": (29.5630, 106.5516),
    "成都": (30.5728, 104.0668),
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "西安": (34.3416, 108.9398),
    "杭州": (30.2741, 120.1551),
    "长沙": (28.2282, 112.9388),
    "厦门": (24.4798, 118.0894),
    "大理": (25.5894, 100.2253),
    # ── Phase 6 expansion cities ──
    "三亚": (18.2528, 109.5119),
    "桂林": (25.2736, 110.2900),
    "苏州": (31.2989, 120.5853),
    "张家界": (29.1167, 110.4792),
    "丽江": (26.8750, 100.2296),
}

# ── Open-Meteo API ────────────────────────────────────────

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather Code → Chinese description
WEATHER_CODES: Dict[int, str] = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "沉积雾凇",
    51: "小毛毛雨",
    53: "中毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "中阵雨",
    82: "大阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷暴",
    96: "冰雹雷暴",
    99: "强冰雹雷暴",
}


@dataclass
class DailyForecast:
    """Single day weather forecast."""
    date: str  # YYYY-MM-DD
    temp_max: float  # °C
    temp_min: float  # °C
    precipitation: float  # mm
    weather_code: int  # WMO code
    weather_desc: str  # Chinese description
    wind_speed_max: float  # km/h
    travel_score: float = 1.0  # 0.0-1.0 suitability for travel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "temp_max": self.temp_max,
            "temp_min": self.temp_min,
            "precipitation": self.precipitation,
            "weather_code": self.weather_code,
            "weather_desc": self.weather_desc,
            "wind_speed_max": self.wind_speed_max,
            "travel_score": self.travel_score,
        }


@dataclass
class WeatherForecast:
    """Multi-day weather forecast for a city."""
    city: str
    lat: float
    lon: float
    daily: List[DailyForecast] = field(default_factory=list)
    overall_score: float = 1.0
    advice: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "city": self.city,
            "lat": self.lat,
            "lon": self.lon,
            "daily": [d.to_dict() for d in self.daily],
            "overall_score": round(self.overall_score, 2),
            "advice": self.advice,
        }


# ── HTTP Client ───────────────────────────────────────────

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Get or create a shared httpx AsyncClient singleton."""
    global _client
    if _client is None:
        # trust_env=False: ignore the Windows system proxy (stale local proxy
        # breaks TLS); Open-Meteo is reached directly, same as amap_service.
        _client = httpx.AsyncClient(timeout=15.0, trust_env=False)
    return _client


# ── Helpers ───────────────────────────────────────────────


def _resolve_city(city: str) -> Optional[tuple[float, float]]:
    """Resolve city name to (lat, lon). Supports fuzzy prefix matching."""
    if not city:
        return None
    # Exact match
    if city in CITY_COORDS:
        return CITY_COORDS[city]
    # Prefix match (e.g. "重庆" in "重庆市")
    for name, coords in CITY_COORDS.items():
        if name in city or city in name:
            return coords
    return None


def _compute_travel_score(day: DailyForecast) -> float:
    """Compute a travel suitability score for a single day.

    Factors:
      - Rain reduces score (heavy rain → 0.3, thunderstorm → 0.0)
      - Extreme temperatures reduce score (>35°C or <0°C → penalty)
      - High wind reduces score (>50 km/h → penalty)
    """
    score = 1.0

    # Weather condition penalties
    code = day.weather_code
    if code in (95, 96, 99):  # Thunderstorms
        score -= 0.8
    elif code in (63, 65):  # Heavy rain
        score -= 0.6
    elif code in (71, 73, 75, 85, 86):  # Snow
        score -= 0.5
    elif code in (61, 80, 81, 82):  # Rain showers
        score -= 0.3
    elif code in (51, 53, 55):  # Drizzle
        score -= 0.15
    elif code in (45, 48):  # Fog
        score -= 0.2

    # Temperature penalties
    if day.temp_max > 38:
        score -= 0.3
    elif day.temp_max > 35:
        score -= 0.15
    if day.temp_min < 0:
        score -= 0.3
    elif day.temp_min < 5:
        score -= 0.1

    # Wind penalty
    if day.wind_speed_max > 50:
        score -= 0.2
    elif day.wind_speed_max > 30:
        score -= 0.1

    return max(0.0, min(1.0, score))


def _compute_overall_score(daily: List[DailyForecast]) -> float:
    """Average travel score across all forecasted days."""
    if not daily:
        return 0.5
    return sum(d.travel_score for d in daily) / len(daily)


def _generate_advice(forecast: WeatherForecast) -> str:
    """Generate Chinese travel weather advice based on the forecast."""
    if not forecast.daily:
        return "暂无天气预报数据。"

    scores = [d.travel_score for d in forecast.daily]
    avg_score = sum(scores) / len(scores)

    if avg_score >= 0.9:
        advice = "天气非常好，非常适合出行！"
    elif avg_score >= 0.7:
        advice = "天气整体不错，适合旅行。"
    elif avg_score >= 0.5:
        advice = "部分时段天气欠佳，建议携带雨具并根据天气调整行程。"
    else:
        advice = "近期天气不太理想，建议关注天气预报，适当调整出行计划。"

    # Add specific warnings
    for d in forecast.daily:
        if d.weather_code in (95, 96, 99):
            advice += f" ⚠️ {d.date} 有雷暴，避免户外活动。"
            break
        elif d.weather_code in (63, 65):
            advice += f" 🌧️ {d.date} 有大雨，建议安排室内景点。"
            break

    # Add temperature advice
    temps = [d.temp_max for d in forecast.daily]
    if temps:
        avg_high = sum(temps) / len(temps)
        if avg_high > 35:
            advice += " 天气炎热，注意防暑降温。"
        elif avg_high < 5:
            advice += " 天气寒冷，注意保暖。"

    return advice


# ── Public API ────────────────────────────────────────────


async def get_weather_forecast(
    city: str,
    days: int = 5,
    start_date: Optional[str] = None,
) -> WeatherForecast:
    """Fetch a weather forecast for a city from Open-Meteo.

    Args:
        city: Chinese city name (e.g. "重庆", "成都").
        days: Number of forecast days (1-7). Open-Meteo provides 7 days free.
        start_date: Optional start date (YYYY-MM-DD). Uses today if None.

    Returns:
        WeatherForecast with daily forecast data and travel scores.

    Raises:
        ValueError: If the city is not recognized.
    """
    coords = _resolve_city(city)
    if not coords:
        raise ValueError(
            f"Unrecognized city: '{city}'. "
            f"Supported cities: {', '.join(CITY_COORDS.keys())}"
        )

    lat, lon = coords
    days = max(1, min(7, days))  # Open-Meteo free tier: 7 days

    params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "weather_code",
            "wind_speed_10m_max",
        ],
        "timezone": "Asia/Shanghai",
        "forecast_days": days,
    }

    forecast = WeatherForecast(city=city, lat=lat, lon=lon)

    try:
        client = _get_client()
        resp = await client.get(OPEN_METEO_URL, params=params)

        if resp.status_code != 200:
            logger.error(
                f"Open-Meteo returned {resp.status_code}: {resp.text[:200]}"
            )
            return forecast  # Return empty forecast on error

        data = resp.json()
        daily_data = data.get("daily", {})

        dates = daily_data.get("time", [])
        temps_max = daily_data.get("temperature_2m_max", [])
        temps_min = daily_data.get("temperature_2m_min", [])
        precip = daily_data.get("precipitation_sum", [])
        weather_codes = daily_data.get("weather_code", [])
        winds = daily_data.get("wind_speed_10m_max", [])

        for i in range(len(dates)):
            daily = DailyForecast(
                date=str(dates[i]),
                temp_max=float(temps_max[i]) if i < len(temps_max) else 0.0,
                temp_min=float(temps_min[i]) if i < len(temps_min) else 0.0,
                precipitation=float(precip[i]) if i < len(precip) else 0.0,
                weather_code=int(weather_codes[i]) if i < len(weather_codes) else 0,
                weather_desc=WEATHER_CODES.get(
                    int(weather_codes[i]) if i < len(weather_codes) else 0,
                    "未知",
                ),
                wind_speed_max=float(winds[i]) if i < len(winds) else 0.0,
            )
            daily.travel_score = _compute_travel_score(daily)
            forecast.daily.append(daily)

        forecast.overall_score = _compute_overall_score(forecast.daily)
        forecast.advice = _generate_advice(forecast)

        logger.info(
            f"Weather fetched for {city}: {len(forecast.daily)} days, "
            f"overall_score={forecast.overall_score:.2f}"
        )

    except httpx.TimeoutException:
        logger.warning(f"Open-Meteo timeout for {city}")
    except Exception as e:
        logger.error(f"Weather fetch failed for {city}: {e}")

    return forecast


async def get_travel_weather_advice(
    city: str,
    days: int = 5,
) -> Dict[str, Any]:
    """Get a simplified weather summary suitable for travel planning.

    Args:
        city: Chinese city name.
        days: Number of forecast days.

    Returns:
        Dict with keys: city, overall_score, advice, daily_summary, warnings.
    """
    forecast = await get_weather_forecast(city, days=days)

    daily_summary = [
        {
            "date": d.date,
            "weather": d.weather_desc,
            "temp": f"{d.temp_min:.0f}~{d.temp_max:.0f}°C",
            "rain": f"{d.precipitation:.1f}mm",
            "travel_score": d.travel_score,
        }
        for d in forecast.daily
    ]

    warnings: List[str] = []
    for d in forecast.daily:
        if d.travel_score < 0.4:
            warnings.append(f"{d.date} 天气恶劣 ({d.weather_desc})，建议调整行程。")
        elif d.travel_score < 0.6:
            warnings.append(f"{d.date} 天气欠佳 ({d.weather_desc})，建议准备备选方案。")

    return {
        "city": city,
        "overall_score": forecast.overall_score,
        "advice": forecast.advice,
        "daily_summary": daily_summary,
        "warnings": warnings,
    }

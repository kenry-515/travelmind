"""
TravelMind Agent — Weather Service Mock 测试（Phase 12.29d）

mock _get_client 来测试 weather_service 的错误处理和降级逻辑。
缓存层在内联 try-except 中静默失败，无需 mock。
"""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.weather_service import (
    get_weather_forecast,
    get_travel_weather_advice,
    CITY_COORDS,
)

pytestmark = pytest.mark.asyncio

MOCK_FORECAST_JSON = {
    "latitude": 29.56,
    "longitude": 106.55,
    "daily": {
        "time": ["2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-01"],
        "temperature_2m_max": [33.0, 31.5, 29.8, 32.1, 28.5],
        "temperature_2m_min": [24.0, 23.2, 21.5, 22.8, 20.1],
        "precipitation_sum": [0.0, 2.5, 15.0, 0.5, 8.0],
        "weather_code": [0, 80, 61, 45, 63],
        "wind_speed_10m_max": [8.5, 12.0, 18.0, 6.5, 14.0],
    },
}


@pytest.fixture(autouse=True)
def mock_http():
    """Mock HTTP 客户端单例以绕过真实 API 请求。"""
    client = MagicMock()
    # client.get() 被 await — 需要 AsyncMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_FORECAST_JSON
    mock_resp.text = ""
    client.get = AsyncMock(return_value=mock_resp)
    with patch("app.services.weather_service._get_client", return_value=client):
        yield client


async def test_get_forecast_success(mock_http):
    """已知城市应返回带 5 天预报的 ForecastResult。"""
    forecast = await get_weather_forecast("重庆", days=5)
    assert forecast is not None
    assert forecast.city == "重庆"
    assert len(forecast.daily) == 5
    assert forecast.daily[0].temp_max == 33.0


async def test_get_forecast_unknown_city():
    """未知城市应抛出 ValueError。"""
    with pytest.raises(ValueError):
        await get_weather_forecast("UNKNOWN_CITY_XYZ", days=3)


async def test_get_forecast_api_error(mock_http):
    """Open-Meteo 返回 500 时应优雅降级返回空预报。"""
    mock_http.get.return_value.status_code = 500
    forecast = await get_weather_forecast("重庆", days=5)
    assert forecast is not None


async def test_get_forecast_connection_error(mock_http):
    """网络错误时应优雅降级。"""
    mock_http.get.side_effect = Exception("Connection refused")
    forecast = await get_weather_forecast("重庆", days=5)
    assert forecast is not None


async def test_weather_advice_success(mock_http):
    """天气建议应包含评分和建议文字。"""
    advice = await get_travel_weather_advice("重庆", days=5)
    assert advice is not None
    assert "overall_score" in advice
    assert "advice" in advice
    assert "daily_summary" in advice


async def test_weather_advice_unknown_city():
    """未知城市的建议应抛出 ValueError。"""
    with pytest.raises(ValueError):
        await get_travel_weather_advice("UNKNOWN_CITY_XYZ", days=5)


async def test_all_cities_have_coords():
    """至少 30 个城市有坐标映射。"""
    assert len(CITY_COORDS) >= 30
    for city in ["重庆", "成都", "上海", "北京", "广州", "深圳", "杭州", "西安", "武汉", "长沙"]:
        assert city in CITY_COORDS, f"Missing coords for {city}"

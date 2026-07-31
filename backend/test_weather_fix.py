"""Quick test for WeatherForecast compatibility fixes."""
import sys
sys.path.insert(0, '.')

from app.services.weather_service import get_weather_forecast
from app.agents.itinerary_contract import compute_weather_fit, enforce_severe_weather_indoor, trip_has_rain

# Test weather service
weather = get_weather_forecast('北京', 3)
print(f'Type: {type(weather).__name__}')

has_dict = hasattr(weather, 'to_dict')
print(f'Has to_dict: {has_dict}')

if has_dict:
    d = weather.to_dict()
    print(f'Keys: {list(d.keys())[:5]}')
    print(f'Daily count: {len(d.get("daily", []))}')

# Test compute_weather_fit with WeatherForecast object
print("\n--- Testing compute_weather_fit with WeatherForecast object ---")
test_data = {
    "trip": {"city": "北京", "days": 2},
    "days": [
        {"day": 1, "items": [{"poi": "故宫", "type": "attraction"}]},
        {"day": 2, "items": [{"poi": "天坛", "type": "attraction"}]}
    ]
}
try:
    fit, notes = compute_weather_fit(test_data, weather, month=7)
    print(f"Fit: {fit}, Notes count: {len(notes)}")
    print("SUCCESS: compute_weather_fit works with WeatherForecast object!")
except Exception as e:
    print(f"FAILED: {e}")

# Test enforce_severe_weather_indoor with WeatherForecast object
print("\n--- Testing enforce_severe_weather_indoor ---")
try:
    result = enforce_severe_weather_indoor(test_data, weather, [])
    print(f"Replaced count: {result}")
    print("SUCCESS: enforce_severe_weather_indoor works!")
except Exception as e:
    print(f"FAILED: {e}")

# Test trip_has_rain with WeatherForecast object
print("\n--- Testing trip_has_rain ---")
try:
    has_rain = trip_has_rain(weather, 3)
    print(f"Has rain: {has_rain}")
    print("SUCCESS: trip_has_rain works!")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== All weather tests completed ===")

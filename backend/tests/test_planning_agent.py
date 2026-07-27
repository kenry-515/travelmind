"""
TravelMind Agent — Planning Agent Unit Tests (Tech Debt Fix #4)

Tests for the pure functions in planning_agent.py:
  - _extract_first_json_object, _parse_json_tolerant
  - _normalize_nested_json, _unwrap_tool_envelope
  - _format_places, _format_weather, _check_feasibility
"""

import json

import pytest


# ── JSON Extraction ──────────────────────────────────────────


class TestExtractFirstJsonObject:
    def test_simple_object(self):
        from app.agents.planning_agent import _extract_first_json_object
        text = 'prefix {"a": 1} suffix'
        assert _extract_first_json_object(text) == '{"a": 1}'

    def test_nested_object(self):
        from app.agents.planning_agent import _extract_first_json_object
        text = 'x {"outer": {"inner": [1,2,3]}, "b": true} y'
        result = _extract_first_json_object(text)
        assert result is not None
        assert '"outer"' in result
        assert '"inner"' in result

    def test_strings_with_braces(self):
        from app.agents.planning_agent import _extract_first_json_object
        text = '{"key": "value with {brace} inside"} trailing'
        result = _extract_first_json_object(text)
        assert result is not None
        assert 'brace' in result

    def test_escaped_quotes(self):
        from app.agents.planning_agent import _extract_first_json_object
        text = r'{"key": "value with \" escaped"} end'
        result = _extract_first_json_object(text)
        assert result is not None

    def test_no_braces(self):
        from app.agents.planning_agent import _extract_first_json_object
        assert _extract_first_json_object("no braces here") is None

    def test_empty_string(self):
        from app.agents.planning_agent import _extract_first_json_object
        assert _extract_first_json_object("") is None

    def test_unbalanced_braces(self):
        from app.agents.planning_agent import _extract_first_json_object
        assert _extract_first_json_object('{"a": 1') is None


# ── Tolerant JSON Parsing ────────────────────────────────────


class TestParseJsonTolerant:
    def test_valid_json(self):
        from app.agents.planning_agent import _parse_json_tolerant
        result = _parse_json_tolerant('{"a": 1, "b": [2, 3]}')
        assert result == {"a": 1, "b": [2, 3]}

    def test_json_with_prefix_text(self):
        from app.agents.planning_agent import _parse_json_tolerant
        result = _parse_json_tolerant('Here is your itinerary: {"trip": {"city": "重庆"}}')
        assert result == {"trip": {"city": "重庆"}}

    def test_json_with_suffix_text(self):
        from app.agents.planning_agent import _parse_json_tolerant
        result = _parse_json_tolerant('{"name": "test"} Hope this helps!')
        assert result == {"name": "test"}

    def test_invalid_json_returns_none(self):
        from app.agents.planning_agent import _parse_json_tolerant
        assert _parse_json_tolerant("not json at all") is None

    def test_empty_string(self):
        from app.agents.planning_agent import _parse_json_tolerant
        assert _parse_json_tolerant("") is None

    def test_unicode_chinese(self):
        from app.agents.planning_agent import _parse_json_tolerant
        result = _parse_json_tolerant('{"城市": "重庆", "景点": ["洪崖洞"]}')
        assert result == {"城市": "重庆", "景点": ["洪崖洞"]}


# ── Normalize Nested JSON ────────────────────────────────────


class TestNormalizeNestedJson:
    def test_string_keys_unwrapped(self):
        from app.agents.planning_agent import _normalize_nested_json
        data = {
            "trip": '{"city": "重庆", "daysCount": 3}',
            "days": '[{"day": 1, "theme": "渝中"}]',
            "other": "keep as string",
        }
        result = _normalize_nested_json(data)
        assert isinstance(result["trip"], dict)
        assert result["trip"]["city"] == "重庆"
        assert isinstance(result["days"], list)
        assert result["days"][0]["day"] == 1
        assert result["other"] == "keep as string"

    def test_no_string_keys_unchanged(self):
        from app.agents.planning_agent import _normalize_nested_json
        data = {"trip": {"city": "重庆"}, "tags": ["美食"]}
        result = _normalize_nested_json(data)
        assert result == data

    def test_invalid_json_string_unchanged(self):
        from app.agents.planning_agent import _normalize_nested_json
        data = {"trip": "not valid json at all!!!"}
        result = _normalize_nested_json(data)
        assert result["trip"] == "not valid json at all!!!"

    def test_non_dict_passthrough(self):
        from app.agents.planning_agent import _normalize_nested_json
        assert _normalize_nested_json([1, 2, 3]) == [1, 2, 3]
        assert _normalize_nested_json("string") == "string"
        assert _normalize_nested_json(None) is None


# ── Unwrap Tool Envelope ─────────────────────────────────────


class TestUnwrapToolEnvelope:
    def test_parameters_dict(self):
        from app.agents.planning_agent import _unwrap_tool_envelope
        data = {"name": "output", "parameters": {"trip": {"city": "重庆"}}}
        result = _unwrap_tool_envelope(data)
        assert "trip" in result
        assert result["trip"]["city"] == "重庆"

    def test_parameters_string(self):
        from app.agents.planning_agent import _unwrap_tool_envelope
        data = {"name": "output", "parameters": '{"trip": {"city": "重庆"}}'}
        result = _unwrap_tool_envelope(data)
        assert "trip" in result
        assert result["trip"]["city"] == "重庆"

    def test_arguments_dict(self):
        from app.agents.planning_agent import _unwrap_tool_envelope
        data = {"arguments": {"trip": {"city": "成都"}}}
        result = _unwrap_tool_envelope(data)
        assert "trip" in result
        assert result["trip"]["city"] == "成都"

    def test_arguments_string(self):
        from app.agents.planning_agent import _unwrap_tool_envelope
        data = {"arguments": '{"trip": {"city": "成都"}}'}
        result = _unwrap_tool_envelope(data)
        assert "trip" in result

    def test_plain_dict_unchanged(self):
        from app.agents.planning_agent import _unwrap_tool_envelope
        data = {"trip": {"city": "北京"}, "days": []}
        result = _unwrap_tool_envelope(data)
        assert result == data

    def test_non_dict_passthrough(self):
        from app.agents.planning_agent import _unwrap_tool_envelope
        assert _unwrap_tool_envelope([1, 2, 3]) == [1, 2, 3]
        assert _unwrap_tool_envelope("text") == "text"


# ── Format Places ─────────────────────────────────────────────


class TestFormatPlaces:
    def test_formats_basic_place(self):
        from app.agents.planning_agent import _format_places
        places = [{
            "name": "洪崖洞",
            "total_score": 0.92,
            "tags": ["夜景", "美食"],
            "suitable_for": "所有人",
            "best_time": "全年",
            "price_level": "适中",
        }]
        result = _format_places(places)
        assert "洪崖洞" in result
        assert "0.92" in result
        assert "夜景" in result

    def test_formats_place_with_price_range(self):
        from app.agents.planning_agent import _format_places
        places = [{
            "name": "故宫",
            "total_score": 0.95,
            "tags": ["历史", "文化"],
            "suitable_for": "所有人",
            "best_time": "秋季",
            "price_range": {"min": 40, "max": 60},
        }]
        result = _format_places(places)
        assert "¥40-60" in result

    def test_free_attraction(self):
        from app.agents.planning_agent import _format_places
        places = [{
            "name": "西湖",
            "total_score": 0.88,
            "tags": ["自然"],
            "suitable_for": "情侣",
            "best_time": "春季",
            "price_range": {"min": 0, "max": 0},
        }]
        result = _format_places(places)
        assert "免费" in result

    def test_respects_limit(self):
        from app.agents.planning_agent import _format_places
        places = [{"name": f"景点{i}", "total_score": 0.5, "tags": [], "suitable_for": "", "best_time": ""} for i in range(20)]
        result = _format_places(places, limit=5)
        # limit=5 shows items 0-4 (enumerated as 1-5 in output)
        assert "景点0" in result
        assert "景点4" in result
        assert "景点5" not in result

    def test_empty_list(self):
        from app.agents.planning_agent import _format_places
        assert _format_places([]) == ""


# ── Format Weather ────────────────────────────────────────────


class TestFormatWeather:
    def test_formats_daily_forecast(self):
        from app.agents.planning_agent import _format_weather
        weather = {
            "daily": [
                {"date": "2026-07-21", "weather_desc": "晴",
                 "temp_min": 25, "temp_max": 35, "precipitation": 0},
                {"date": "2026-07-22", "weather_desc": "雷阵雨",
                 "temp_min": 24, "temp_max": 32, "precipitation": 15},
            ]
        }
        result = _format_weather(weather)
        assert "晴" in result
        assert "雷阵雨" in result
        assert "25~35" in result
        # Phase 12: 高温+降雨双重预警
        assert "高温+降雨双重预警" in result
        assert "午后" in result

    def test_no_weather(self):
        from app.agents.planning_agent import _format_weather
        assert _format_weather(None) == ""

    def test_empty_daily(self):
        from app.agents.planning_agent import _format_weather
        assert _format_weather({}) == ""
        assert _format_weather({"daily": []}) == ""

    def test_high_temp_only(self):
        """Phase 12: 高温≥35°C单独触发高温预警"""
        from app.agents.planning_agent import _format_weather
        weather = {
            "daily": [
                {"date": "2026-07-21", "weather_desc": "晴",
                 "temp_min": 28, "temp_max": 38, "precipitation": 0},
            ]
        }
        result = _format_weather(weather)
        assert "高温预警" in result
        assert "户外活动限早晨/傍晚" in result

    def test_rain_only(self):
        """Phase 12: 降雨单独触发室内优先提示"""
        from app.agents.planning_agent import _format_weather
        weather = {
            "daily": [
                {"date": "2026-07-21", "weather_desc": "小雨",
                 "temp_min": 22, "temp_max": 28, "precipitation": 8},
            ]
        }
        result = _format_weather(weather)
        assert "室内配额" in result
        assert "高温" not in result

    def test_mild_weather(self):
        """Phase 12: 温和天气仅提示晴朗户外"""
        from app.agents.planning_agent import _format_weather
        weather = {
            "daily": [
                {"date": "2026-07-21", "weather_desc": "多云",
                 "temp_min": 20, "temp_max": 28, "precipitation": 1},
            ]
        }
        result = _format_weather(weather)
        assert "晴朗日优先户外" in result


# ── Check Feasibility ────────────────────────────────────────


class TestCheckFeasibility:
    def test_sufficient_candidates(self):
        from app.agents.planning_agent import _check_feasibility
        profile = {"days": 3}
        recs = [{"name": f"景点{i}"} for i in range(15)]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True
        assert result["severity"] == "info"

    def test_few_candidates_warning(self):
        from app.agents.planning_agent import _check_feasibility
        profile = {"days": 5}
        recs = [{"name": f"景点{i}"} for i in range(3)]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True
        assert result["severity"] == "warning"
        assert "不够充实" in result["warning"]

    def test_empty_candidates(self):
        from app.agents.planning_agent import _check_feasibility
        profile = {"days": 1}
        result = _check_feasibility(profile, [])
        assert result["feasible"] is True  # Non-fatal
        assert result["warning"] is not None

    def test_default_days(self):
        from app.agents.planning_agent import _check_feasibility
        # profile with no days key → defaults to 1
        result = _check_feasibility({}, [{"name": "景点1"}])
        assert result["feasible"] is True

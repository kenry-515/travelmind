"""itinerary_contract 单元测试：契约校验、注入计算、月份/天气/预算一致性。

使用 docs/itinerary.example.cq.json 作为合法基准；非法用例就地构造。
"""

import json
from pathlib import Path

from app.agents.itinerary_contract import (
    budget_sum_mismatch,
    compute_weather_fit,
    count_places,
    inject_computed_fields,
    inject_place_count,
    month_inconsistency_errors,
    validate_day,
    validate_day_continuity,
    validate_itinerary,
    weather_coverage_errors,
)

FIXTURE = Path("D:/TravelMindAgent/docs/itinerary.example.cq.json")


def _valid_itinerary():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestValidate:
    def test_valid_fixture_passes(self):
        it = _valid_itinerary()
        assert validate_itinerary(it) == []
        assert validate_day_continuity(it) == []

    def test_missing_trip_rejected(self):
        it = _valid_itinerary()
        del it["trip"]
        assert validate_itinerary(it), "缺少 trip 必须被拒绝"

    def test_empty_days_rejected(self):
        it = _valid_itinerary()
        it["days"] = []
        assert validate_itinerary(it), "days minItems=1"

    def test_day_missing_required_rejected(self):
        day = _valid_itinerary()["days"][0]
        del day["theme"]
        assert validate_day(day), "day 缺 theme 必须被拒绝"

    def test_bad_time_pattern_rejected(self):
        day = _valid_itinerary()["days"][0]
        day["items"][0]["time"] = "9:30"  # 非 HH:MM
        assert validate_day(day), "time 必须匹配 ^\\d{2}:\\d{2}$"

    def test_budget_missing_amount_rejected(self):
        it = _valid_itinerary()
        it["budget"][0] = {"label": "餐饮", "percent": 33}
        assert validate_itinerary(it)

    def test_additional_root_property_rejected(self):
        it = _valid_itinerary()
        it["hack"] = True
        assert validate_itinerary(it), "additionalProperties=false"

    def test_day_continuity_broken(self):
        it = _valid_itinerary()
        it["days"][1]["day"] = 3  # 1,3,3 → 不连续
        assert validate_day_continuity(it)


class TestInjection:
    def test_percent_sums_to_100(self):
        it = _valid_itinerary()
        for b in it["budget"]:
            b.pop("percent", None)
        inject_computed_fields(it)
        assert sum(b["percent"] for b in it["budget"]) == 100

    def test_checklist_done_forced_false(self):
        it = _valid_itinerary()
        it["checklist"][0]["done"] = True
        inject_computed_fields(it)
        assert all(c["done"] is False for c in it["checklist"])

    def test_days_count_and_dates_injected(self):
        it = _valid_itinerary()
        inject_computed_fields(it)
        assert it["trip"]["daysCount"] == len(it["days"])
        assert it["trip"]["dateStart"]
        assert it["schemaVersion"]

    def test_place_count_excludes_stops(self):
        it = _valid_itinerary()
        inject_place_count(it)
        stat = next(s for s in it["trip"]["stats"] if "地点" in s["label"])
        assert stat["value"] == f"{count_places(it)} 个"

    def test_count_places_ignores_meals_and_hotel(self):
        data = {"days": [{"items": [
            {"poi": "洪崖洞"}, {"poi": "磁器口午餐"}, {"poi": "返回酒店休息"},
            {"poi": "回酒店午休"}, {"poi": "长江索道"},
        ]}]}
        assert count_places(data) == 2


class TestConsistency:
    def test_month_mismatch_detected(self):
        it = _valid_itinerary()
        it["tips"] = ["11月记得带薄外套"]
        errs = month_inconsistency_errors(it, 7)
        assert errs and any("薄外套" in e for e in errs), "11月 字样在 7 月行程中必须被拦下"
        errs11 = month_inconsistency_errors(it, 11)
        assert errs11 and not any("薄外套" in e for e in errs11), "11月行程不应误拦 11月 字样"

    def test_budget_sum_mismatch(self):
        it = _valid_itinerary()
        assert not budget_sum_mismatch(it)
        it["budget"][0]["amount"] = 5000  # 大幅溢出
        assert budget_sum_mismatch(it)

    def test_weather_coverage(self):
        it = _valid_itinerary()
        it["tips"] = ["常规建议"]
        it["checklist"] = [{"text": "身份证", "done": False}]
        assert weather_coverage_errors(it), "有雨无天气项必须报错"
        it["tips"] = ["7月记得带折叠伞"]
        it["checklist"] = [{"text": "折叠伞", "done": False}]
        assert not weather_coverage_errors(it)


class TestWeatherFit:
    def _it(self, pois):
        return {"days": [{"day": 1, "items": [{"poi": p, "time": "09:00", "note": ""} for p in pois]}]}

    def test_no_weather_unknown(self):
        fit, notes = compute_weather_fit(self._it(["洪崖洞"]), None)
        assert fit == "unknown"

    def test_rain_outdoor_majority_poor(self):
        weather = {"daily": [{"date": "07-21", "weather_desc": "雷暴", "precipitation": 10}]}
        fit, notes = compute_weather_fit(self._it(["洪崖洞", "长江索道", "南山一棵树"]), weather)
        assert fit == "poor" and notes

    def test_rain_indoor_majority_good(self):
        weather = {"daily": [{"date": "07-21", "weather_desc": "雷暴", "precipitation": 10}]}
        fit, _ = compute_weather_fit(self._it(["三峡博物馆", "磁器口古镇", "湖广会馆"]), weather)
        assert fit == "good"

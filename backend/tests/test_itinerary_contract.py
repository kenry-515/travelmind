"""itinerary_contract 单元测试：契约校验、注入计算、月份/天气/预算一致性。

使用 docs/itinerary.example.cq.json 作为合法基准；非法用例就地构造。
"""

import json
from pathlib import Path

from app.agents.itinerary_contract import (
    budget_sum_mismatch,
    compute_weather_fit,
    count_places,
    enforce_severe_weather_indoor,
    inject_computed_fields,
    inject_place_count,
    month_inconsistency_errors,
    validate_day,
    validate_day_continuity,
    validate_itinerary,
    weather_coverage_errors,
)

FIXTURE = Path(__file__).resolve().parent.parent.parent / "docs" / "itinerary.example.cq.json"


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

    def test_kb_name_vs_normalized_mismatch_still_indoor(self):
        """Phase 12.21: KB 的 name（带标点）与 name_normalized 不一致时，
        行程里写任一变体都必须命中 KB 标签，不得回退名称正则误判为户外。
        （q08/q11/q13 weather_fit=poor 的根因回归）"""
        kb = [
            {"name": "西林·瞰青别墅", "name_normalized": "西林瞰青别墅",
             "tags": ["古建筑", "历史"]},
        ]
        weather = {"daily": [{"date": "07-26", "weather_desc": "雷暴",
                              "precipitation": 40, "weather_code": 96}]}
        # 行程里写带标点的全名 —— 旧代码查表 miss → 误判 outdoor → poor
        fit, _ = compute_weather_fit(
            self._it(["西林·瞰青别墅"]), weather, kb_attractions=kb)
        assert fit == "good"
        # 反过来写规范化名也一样
        fit2, _ = compute_weather_fit(
            self._it(["西林瞰青别墅"]), weather, kb_attractions=kb)
        assert fit2 == "good"

    def test_guard_then_fit_consistent(self):
        """Phase 12.21: 守卫替换上来的室内项，评估器必须同样判为室内
        （两侧 KB 查找口径一致，雷暴日不得再残留"户外"误判）。"""
        kb = [
            {"name": "鼓浪屿沙滩", "name_normalized": "鼓浪屿沙滩", "city": "厦门",
             "tags": ["海滩", "自然"], "popularity_score": 9},
            {"name": "打渔船·老厦门本地菜·姜母鸭(沙坡尾地标美食店)",
             "name_normalized": "打渔船老厦门本地菜姜母鸭沙坡尾地标美食店",
             "city": "厦门", "tags": ["美食", "中餐"], "popularity_score": 6},
        ]
        data = {"trip": {"city": "厦门"}, "days": [
            {"day": 1, "items": [{"poi": "鼓浪屿沙滩", "time": "09:00", "note": ""}]},
        ]}
        weather = {"daily": [{"date": "07-26", "weather_desc": "雷暴",
                              "precipitation": 40, "weather_code": 96}]}
        n = enforce_severe_weather_indoor(data, weather, kb)
        assert n == 1  # 沙滩被替换为餐厅
        fit, _ = compute_weather_fit(data, weather, kb_attractions=kb)
        assert fit == "good"


class TestPaceDensity:
    """Phase 12.27：节奏分档截断（用户反馈"行程很密集"）。"""

    def _data(self, n=7):
        return {"days": [{"day": 1, "items": [
            {"poi": f"景点{i}", "time": f"{9+i}:00", "note": ""} for i in range(n)
        ]}]}

    def test_leisure_caps_at_4(self):
        from app.agents.itinerary_contract import enforce_pace_density
        data = self._data(7)
        trimmed = enforce_pace_density(data, "休闲")
        assert trimmed == 3
        assert len(data["days"][0]["items"]) == 4

    def test_compact_caps_at_6(self):
        from app.agents.itinerary_contract import enforce_pace_density
        data = self._data(7)
        assert enforce_pace_density(data, "特种兵") == 1
        assert len(data["days"][0]["items"]) == 6

    def test_default_caps_at_5(self):
        from app.agents.itinerary_contract import enforce_pace_density
        data = self._data(7)
        assert enforce_pace_density(data, "") == 2
        assert len(data["days"][0]["items"]) == 5

    def test_under_cap_untouched(self):
        from app.agents.itinerary_contract import enforce_pace_density
        data = self._data(3)
        assert enforce_pace_density(data, "休闲") == 0
        assert len(data["days"][0]["items"]) == 3


class TestAttachDiningStay:
    """Phase 12.27：按天挂载 KB 真实餐厅与住宿（用户："吃住都没有推荐"）。"""

    KB = [
        {"name": "老盛兴汤包", "city": "上海", "tags": ["美食", "小吃"], "popularity_score": 8},
        {"name": "绿波廊", "city": "上海", "tags": ["美食", "中餐"], "popularity_score": 7},
        {"name": "小龙虾大排档", "city": "上海", "tags": ["美食", "海鲜"], "popularity_score": 6},
        {"name": "外滩茂悦大酒店", "city": "上海", "tags": ["住宿", "酒店"], "popularity_score": 8},
        {"name": "弄堂民宿", "city": "上海", "tags": ["住宿", "民宿"], "popularity_score": 6},
        {"name": "东方明珠", "city": "上海", "tags": ["地标"], "popularity_score": 9},
    ]

    def _data(self):
        return {
            "trip": {"city": "上海"},
            "days": [
                {"day": 1, "eat": "LLM写的文本", "items": [{"poi": "东方明珠", "time": "09:00", "note": ""}]},
                {"day": 2, "eat": "LLM写的文本2", "items": []},
            ],
        }

    def test_dining_mounted_with_diversity(self):
        from app.agents.itinerary_contract import attach_daily_dining_and_stay
        data = self._data()
        n = attach_daily_dining_and_stay(data, self.KB)
        assert n == 2
        eat1 = data["days"][0]["eat"]
        # 午餐=热度最高（小吃），晚餐=首个与午餐品类不同的（中餐）
        assert "午餐「老盛兴汤包」" in eat1
        assert "晚餐「绿波廊」" in eat1

    def test_stay_mounted_per_day_no_repeat(self):
        from app.agents.itinerary_contract import attach_daily_dining_and_stay
        data = self._data()
        attach_daily_dining_and_stay(data, self.KB)
        assert data["days"][0]["stay"] == "外滩茂悦大酒店"
        assert data["days"][1]["stay"] == "弄堂民宿"

    def test_no_kb_keeps_llm_eat(self):
        from app.agents.itinerary_contract import attach_daily_dining_and_stay
        data = self._data()
        n = attach_daily_dining_and_stay(data, [])
        assert n == 0
        assert data["days"][0]["eat"] == "LLM写的文本"
        assert "stay" not in data["days"][0]

    def test_itinerary_pois_excluded(self):
        from app.agents.itinerary_contract import attach_daily_dining_and_stay
        data = self._data()
        data["days"][0]["items"].append({"poi": "老盛兴汤包", "time": "12:00", "note": ""})
        attach_daily_dining_and_stay(data, self.KB)
        assert "午餐「老盛兴汤包」" not in data["days"][0]["eat"]


class TestSevereGuard:
    """Phase 12.17 v5: 雷暴/冰雹日确定性室内替换。"""

    KB = [
        {"name": "洱海", "city": "大理", "tags": ["湖泊", "自然"], "popularity_score": 9},
        {"name": "大理市博物馆", "city": "大理", "tags": ["博物馆", "文化"], "popularity_score": 6},
        {"name": "古城茶馆", "city": "大理", "tags": ["茶馆", "美食"], "popularity_score": 5},
    ]

    def _data(self):
        return {
            "trip": {"city": "大理"},
            "days": [
                {"day": 1, "items": [
                    {"poi": "洱海", "time": "09:00", "note": "看日出"},
                    {"poi": "大理古城", "time": "14:00", "note": "闲逛"},
                ]},
                {"day": 2, "items": [
                    {"poi": "苍山", "time": "09:00", "note": "登山"},
                ]},
            ],
        }

    def test_severe_day_outdoor_replaced(self):
        weather = {"daily": [
            {"date": "d1", "weather_desc": "雷暴", "precipitation": 8},
            {"date": "d2", "weather_desc": "晴", "precipitation": 0},
        ]}
        data = self._data()
        n = enforce_severe_weather_indoor(data, weather, self.KB)
        assert n == 1  # 只有第1天洱海被替换（大理古城为室内）
        pois = [it["poi"] for it in data["days"][0]["items"]]
        assert "洱海" not in pois
        assert "大理市博物馆" in pois  # 按 popularity 选最高
        assert "系统调整" in data["days"][0]["items"][0]["note"]
        assert data["days"][1]["items"][0]["poi"] == "苍山"  # 晴天不动

    def test_no_candidates_no_crash(self):
        weather = {"daily": [{"date": "d1", "weather_desc": "冰雹雷暴"}]}
        data = {"trip": {"city": "大理"}, "days": [
            {"day": 1, "items": [{"poi": "洱海", "time": "09:00", "note": ""}]},
        ]}
        assert enforce_severe_weather_indoor(data, weather, []) == 0

    def test_non_severe_rain_untouched(self):
        weather = {"daily": [{"date": "d1", "weather_desc": "小雨", "precipitation": 2}]}
        data = self._data()
        assert enforce_severe_weather_indoor(data, weather, self.KB) == 0
        assert data["days"][0]["items"][0]["poi"] == "洱海"

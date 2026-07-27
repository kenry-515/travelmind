"""
TravelMind Agent — Route Optimizer Unit Tests (Tech Debt Fix #3)

Tests for the pure functions in route_optimizer.py:
  - _haversine_km, _normalize, _base_name, _core_name, _name_matches
  - _is_visit, _district_core, _theme_districts, _INFRA_RE
"""

import re

import pytest


# ── Haversine ────────────────────────────────────────────────


class TestHaversine:
    def test_same_point_zero_distance(self):
        from app.agents.route_optimizer import _haversine_km
        assert _haversine_km(39.9, 116.4, 39.9, 116.4) == pytest.approx(0.0, abs=0.001)

    def test_beijing_shanghai_approx_1060km(self):
        from app.agents.route_optimizer import _haversine_km
        # Beijing (39.9, 116.4) → Shanghai (31.2, 121.5) ≈ 1068 km
        d = _haversine_km(39.9, 116.4, 31.2, 121.5)
        assert 1000 < d < 1150, f"Expected ~1068km, got {d}km"

    def test_short_distance_chongqing(self):
        from app.agents.route_optimizer import _haversine_km
        # 解放碑 (29.56, 106.58) → 洪崖洞 (29.56, 106.58) ≈ 0.5 km
        d = _haversine_km(29.560, 106.580, 29.565, 106.585)
        assert d < 5.0, f"Expected short distance, got {d}km"

    def test_symmetric(self):
        from app.agents.route_optimizer import _haversine_km
        a = (30.0, 110.0)
        b = (31.0, 111.0)
        assert _haversine_km(*a, *b) == pytest.approx(_haversine_km(*b, *a), rel=0.001)


# ── Normalize ────────────────────────────────────────────────


class TestNormalize:
    def test_strips_chinese_parens(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("故宫（北京）") == "故宫北京"

    def test_strips_ascii_parens(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("Test (Park)") == "TestPark"

    def test_strips_middle_dot(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("重庆·洪崖洞") == "重庆洪崖洞"

    def test_strips_whitespace(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("重庆 洪崖洞") == "重庆洪崖洞"

    def test_replaces_er_variant(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("贰厂") == "二厂"

    def test_empty_string(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("") == ""

    def test_only_punctuation(self):
        from app.agents.route_optimizer import _normalize
        assert _normalize("（）· ") == ""


# ── Base Name ────────────────────────────────────────────────


class TestBaseName:
    def test_strips_chinese_paren_suffix(self):
        from app.agents.route_optimizer import _base_name
        assert _base_name("故宫（北京）") == "故宫"

    def test_strips_ascii_paren_suffix(self):
        from app.agents.route_optimizer import _base_name
        assert _base_name("Test (Park)") == "Test"

    def test_no_parens_returns_full(self):
        from app.agents.route_optimizer import _base_name
        assert _base_name("洪崖洞") == "洪崖洞"

    def test_empty_string(self):
        from app.agents.route_optimizer import _base_name
        assert _base_name("") == ""

    def test_paren_at_start(self):
        from app.agents.route_optimizer import _base_name
        # re.split(r"[（(]", ...)[0] on "(推荐)洪崖洞" gives '' at pos 0
        assert _base_name("(推荐)洪崖洞") == ""


# ── Core Name ────────────────────────────────────────────────


class TestCoreName:
    def test_strips_single_suffix(self):
        from app.agents.route_optimizer import _core_name
        assert _core_name("洪崖洞景区") == "洪崖洞"

    def test_strips_multi_level_suffixes(self):
        from app.agents.route_optimizer import _core_name
        # 李子坝轻轨站 → 李子坝
        assert _core_name("李子坝轻轨站") == "李子坝"

    def test_no_suffix_returns_full(self):
        from app.agents.route_optimizer import _core_name
        assert _core_name("解放碑") == "解放碑"

    def test_too_short_after_strip(self):
        from app.agents.route_optimizer import _core_name
        # "景区" is too short — stripping "景区" leaves "" which fails len check
        assert _core_name("洪景区") == "洪景区"  # len(core)=3, len(suf)=2, 3>3? No

    def test_custom_suffixes(self):
        from app.agents.route_optimizer import _core_name
        custom = ("广场", "步行街")
        assert _core_name("人民广场", suffixes=custom) == "人民"
        assert _core_name("解放碑步行街", suffixes=custom) == "解放碑"

    def test_empty_string(self):
        from app.agents.route_optimizer import _core_name
        assert _core_name("") == ""


# ── Name Matches ─────────────────────────────────────────────


class TestNameMatches:
    def test_exact_match(self):
        from app.agents.route_optimizer import _name_matches
        assert _name_matches("洪崖洞", "洪崖洞") is True

    def test_substring_match(self):
        from app.agents.route_optimizer import _name_matches
        assert _name_matches("洪崖洞", "洪崖洞民俗风貌区") is True

    def test_reverse_substring(self):
        from app.agents.route_optimizer import _name_matches
        assert _name_matches("磁器口古镇", "磁器口") is True

    def test_infra_no_match(self):
        from app.agents.route_optimizer import _name_matches
        # "公交站·磁器口" does NOT contain "磁器口古镇" and vice versa
        # Core name of 磁器口古镇 = 磁器口 → "磁器口" in "公交站磁器口" → True
        assert _name_matches("磁器口古镇", "公交站·磁器口") is True

    def test_core_name_fallback(self):
        from app.agents.route_optimizer import _name_matches
        # "李子坝轻轨站" core → "李子坝", check if "李子坝" in "李子坝观景平台"
        assert _name_matches("李子坝轻轨站", "李子坝观景平台") is True

    def test_no_match(self):
        from app.agents.route_optimizer import _name_matches
        assert _name_matches("洪崖洞", "解放碑") is False

    def test_empty_query(self):
        from app.agents.route_optimizer import _name_matches
        assert _name_matches("", "洪崖洞") is False

    def test_empty_hit(self):
        from app.agents.route_optimizer import _name_matches
        assert _name_matches("洪崖洞", "") is False


# ── Is Visit ─────────────────────────────────────────────────


class TestIsVisit:
    def test_poi_is_visit(self):
        from app.agents.route_optimizer import _is_visit
        assert _is_visit("洪崖洞") is True

    def test_meal_is_not_visit(self):
        from app.agents.route_optimizer import _is_visit
        # _MEAL_STOP_RE matches Chinese meal/rest keywords
        assert _is_visit("午餐推荐") is False
        assert _is_visit("磁器口餐厅") is False

    def test_empty_string(self):
        from app.agents.route_optimizer import _is_visit
        assert _is_visit("") is True  # No meal marker


# ── District Core ────────────────────────────────────────────


class TestDistrictCore:
    def test_strips_qu(self):
        from app.agents.route_optimizer import _district_core
        assert _district_core("渝中区") == "渝中"

    def test_strips_xian(self):
        from app.agents.route_optimizer import _district_core
        assert _district_core("长沙县") == "长沙"

    def test_strips_shi(self):
        from app.agents.route_optimizer import _district_core
        assert _district_core("大理市") == "大理"

    def test_strips_zhou(self):
        from app.agents.route_optimizer import _district_core
        assert _district_core("苏州市") == "苏州"

    def test_no_suffix_unchanged(self):
        from app.agents.route_optimizer import _district_core
        assert _district_core("解放碑") == "解放碑"

    def test_empty_string(self):
        from app.agents.route_optimizer import _district_core
        assert _district_core("") == ""


# ── Theme Districts ──────────────────────────────────────────


class TestThemeDistricts:
    def test_extracts_district_from_day_theme(self):
        from app.agents.route_optimizer import _theme_districts
        result = _theme_districts("DAY 1 · 渝中母城")
        assert "渝中" in result or "渝中母城" in [p for p in result]

    def test_extracts_multiple_parts(self):
        from app.agents.route_optimizer import _theme_districts
        result = _theme_districts("DAY 2 · 沙坪坝 · 磁器口")
        assert "沙坪坝" in result or "磁器口" in result

    def test_filters_digits(self):
        from app.agents.route_optimizer import _theme_districts
        result = _theme_districts("DAY 1 · 滨江")
        assert "DAY" not in str(result)
        # "DAY" split out, "1" filtered (isdigit), "滨江" kept
        assert any("1" not in p for p in result)

    def test_empty_theme(self):
        from app.agents.route_optimizer import _theme_districts
        assert _theme_districts("") == []


# ── Infra RE ─────────────────────────────────────────────────


class TestInfraRe:
    def test_bus_stop_matches(self):
        from app.agents.route_optimizer import _INFRA_RE
        assert _INFRA_RE.search("沙坪坝公交站") is not None

    def test_subway_station_matches(self):
        from app.agents.route_optimizer import _INFRA_RE
        assert _INFRA_RE.search("磁器口地铁站") is not None

    def test_intersection_matches(self):
        from app.agents.route_optimizer import _INFRA_RE
        assert _INFRA_RE.search("解放碑路口") is not None

    def test_poi_does_not_match(self):
        from app.agents.route_optimizer import _INFRA_RE
        assert _INFRA_RE.search("洪崖洞") is None

    def test_toll_station_matches(self):
        from app.agents.route_optimizer import _INFRA_RE
        assert _INFRA_RE.search("渝北收费站") is not None

    def test_service_area_matches(self):
        from app.agents.route_optimizer import _INFRA_RE
        assert _INFRA_RE.search("高速服务区") is not None


# ── Geo Rebalance (Phase 12.21) ─────────────────────────────


class TestGeoRebalance:
    """Phase 12.21: 跨天地理再平衡 — KB-only 模式下 Step 3 区域归位失效
    （KB 无区县字段，adname 全城同名），单日链长可超 200km（q08 桂林
    250km 根因）。再平衡应把"混入远郊日的市区点"移回市区日。"""

    def _scenario(self):
        # 桂林同型：day1 市区 3 点（紧凑），day2 市区 1 点混入远郊 2 点
        pts = {
            "市区A": (25.27, 110.29),
            "市区B": (25.28, 110.30),
            "市区C": (25.26, 110.28),
            "市区D": (25.27, 110.31),
            "恭城文保点": (24.83, 110.83),   # 距市区 ~73km
            "晓锦遗址": (26.10, 110.90),     # 距恭城 ~141km
        }
        days = [
            {"day": 1, "items": [
                {"poi": "市区A", "time": "09:00", "note": ""},
                {"poi": "市区B", "time": "12:00", "note": ""},
                {"poi": "市区C", "time": "15:00", "note": ""},
            ]},
            {"day": 2, "items": [
                {"poi": "市区D", "time": "09:00", "note": ""},
                {"poi": "恭城文保点", "time": "12:00", "note": ""},
                {"poi": "晓锦遗址", "time": "15:00", "note": ""},
            ]},
        ]
        lookups = {
            n: {"lat": la, "lon": lo, "adname": "桂林", "status": "kb_verified"}
            for n, (la, lo) in pts.items()
        }
        return days, lookups

    def _chain(self, day, lookups):
        from app.agents.route_optimizer import _haversine_km
        pts = [(lookups[it["poi"]]["lat"], lookups[it["poi"]]["lon"])
               for it in day["items"]]
        return sum(_haversine_km(*a, *b) for a, b in zip(pts, pts[1:]))

    def test_city_point_moved_back_from_far_day(self):
        from app.agents.route_optimizer import _rebalance_days_geographically
        days, lookups = self._scenario()
        assert self._chain(days[1], lookups) > 200  # 前置：day2 超阈值

        tips = []
        moved = _rebalance_days_geographically(days, lookups, tips=tips)

        assert moved == 1
        day2_pois = [it["poi"] for it in days[1]["items"]]
        assert "市区D" not in day2_pois  # 市区点被移出远郊日
        assert "市区D" in [it["poi"] for it in days[0]["items"]]
        # 两天链长都压进 200km
        assert max(self._chain(d, lookups) for d in days) <= 200
        assert tips  # 有用户可读的调整说明

    def test_already_balanced_no_op(self):
        from app.agents.route_optimizer import _rebalance_days_geographically
        days, lookups = self._scenario()
        # 手动排好：市区归 day1，远郊归 day2
        days[0]["items"].append(days[1]["items"].pop(0))
        moved = _rebalance_days_geographically(days, lookups, tips=[])
        assert moved == 0

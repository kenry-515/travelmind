"""
TravelMind Agent — Refusal Mechanism Tests (Phase 8.1)

Tests for: KB city coverage check, refuse action, coverage detection,
and infeasibility detection.
"""

import pytest

from app.agents.dialog_manager import (
    _get_kb_cities,
    _reset_kb_cities,
    check_city_coverage,
    next_action,
    DEFAULT_SLOTS,
)
from app.agents.planning_agent import _check_feasibility


# ── KB City Coverage (广州 AI+旅游休闲大赛专属) ────
# 大赛只服务广州；非广州城市统一拒答/降级，全国 KB 已不再维护。
# Phase 18 适配：原 test_kb_cities_loaded 等全国假设测试改写为广州专属。


_GUANGZHOU_ALIASES = ("广州", "广州市", "穗", "羊城")


def _is_guangzhou(city: str) -> bool:
    if not city:
        return False
    c = city.strip()
    if c in _GUANGZHOU_ALIASES:
        return True
    # 行政区名前缀（如 "广州增城"、"广州越秀"）→ 视为广州
    return any(c.startswith(prefix) for prefix in _GUANGZHOU_ALIASES)


class TestCityCoverage:
    def test_guangzhou_is_covered(self):
        """广州应是 KB 覆盖城市。"""
        covered, reason = check_city_coverage("广州")
        assert covered is True
        assert reason == ""

    def test_guangzhou_aliases_covered(self):
        """广州常见别名（「广州市」「广州+行政区」拼接）应识别为广州。"""
        for alias in ("广州市", "广州天河", "广州越秀", "广州番禺"):
            covered, _ = check_city_coverage(alias)
            assert covered is True, f"{alias!r} 应识别为广州"

    def test_guangzhou_districts_covered(self):
        """广州下辖区县（越秀/海珠/荔湾/天河/白云/番禺/花都/黄埔/南沙/增城/从化）
        应通过模糊匹配识别为广州。"""
        for district in (
            "越秀", "海珠", "荔湾", "天河", "白云", "番禺",
            "花都", "黄埔", "南沙", "增城", "从化",
        ):
            covered, reason = check_city_coverage(district)
            assert covered is True, f"{district!r} 应识别为广州（{reason}）"

    def test_unknown_city_not_covered(self):
        """广州以外的城市不应被覆盖（大赛专属广州）。"""
        for foreign in ("纽约", "东京", "巴黎", "伦敦"):
            covered, reason = check_city_coverage(foreign)
            assert covered is False, f"{foreign!r} 不应被覆盖"
            assert foreign in reason

    def test_empty_city_not_covered(self):
        covered, reason = check_city_coverage("")
        assert covered is False

    def test_none_city_not_covered(self):
        covered, reason = check_city_coverage(None)
        assert covered is False

    def test_city_substring_matches(self):
        """部分名应通过子串匹配（如「广州市」中的「广州」）。"""
        covered, reason = check_city_coverage("广州市天河区")
        assert covered is True

    def test_kb_cities_loaded(self):
        """_get_kb_cities 应至少返回广州；其他城市可有可无（大赛允许 runtime 扩展）。"""
        _reset_kb_cities()
        cities = _get_kb_cities()
        assert "广州" in cities
        assert len(cities) >= 1


# ── Refuse Action ─────────────────────────────────────────


class TestRefuseAction:
    def test_next_action_refuses_unknown_city(self):
        """非广州城市被拒答（followups 用完后）。"""
        state = {
            "stage": "collecting",
            "slots": dict(DEFAULT_SLOTS, city="纽约"),
            "followups_used": 3,  # exhausted
            "itinerary": None,
            "queued": [],
            "touched": 0,
        }
        action = next_action(state)
        assert action["type"] == "refuse"
        assert "reason" in action
        assert "纽约" in action["reason"]

    def test_next_action_accepts_known_city(self):
        """广州（KB 覆盖）应推进到 confirming。"""
        state = {
            "stage": "collecting",
            "slots": dict(DEFAULT_SLOTS, city="广州", days=3, tags=["美食"]),
            "followups_used": 3,
            "itinerary": None,
            "queued": [],
            "touched": 0,
        }
        action = next_action(state)
        assert action["type"] == "confirm"
        assert action["confirm"] is True

    def test_next_action_suggests_on_first_unknown(self):
        """首次出现非广州城市 → suggest (有追问配额时) 含广州兜底建议。

        Phase 18 P0: 广州智能体大赛专属。用户输入纽约时,
        followups_used=0 < MAX_FOLLOWUPS → 给出广州兜底建议 + 让用户改回。
        """
        state = {
            "stage": "collecting",
            "slots": dict(DEFAULT_SLOTS, city="纽约", days=3),
            "followups_used": 0,
            "itinerary": None,
            "queued": [],
            "touched": 0,
        }
        action = next_action(state)
        # 第一次出现: suggest 含广州建议
        assert action["type"] == "suggest"
        assert action.get("suggestions")
        labels = [s.get("city", "") for s in action["suggestions"]]
        assert any("广州" in label for label in labels)


# ── Feasibility Detection ───────────────────────────────


class TestFeasibility:
    def test_normal_request_feasible(self):
        """Normal 3-day, 10-place request should be feasible."""
        profile = {"days": 3}
        recs = [{"name": f"景点{i}"} for i in range(10)]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True
        assert result["severity"] == "info"

    def test_few_places_warning(self):
        """1 candidate for 3-day trip should trigger warning."""
        profile = {"days": 3}
        recs = [{"name": "景点1"}]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True
        assert result["warning"] is not None
        assert "较少" in result["warning"]
        assert result["severity"] == "warning"

    def test_excessive_places_per_day(self):
        """15 places for 1 day should trigger warning."""
        profile = {"days": 1}
        recs = [{"name": f"景点{i}"} for i in range(15)]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True
        assert result["warning"] is not None
        assert "不太现实" in result["warning"] or "精选" in result["warning"]

    def test_no_warning_when_sufficient(self):
        """10 places for 3 days should be fine (no warning)."""
        profile = {"days": 3}
        recs = [{"name": f"景点{i}"} for i in range(10)]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True
        assert result["warning"] is None

    def test_zero_days_handled(self):
        """days=0 should be handled (defaults to 1)."""
        profile = {"days": 0}
        recs = [{"name": "景点1"}]
        result = _check_feasibility(profile, recs)
        # 0 days → 1 day, 1 place → no warning
        assert result["feasible"] is True

    def test_no_days_key_defaults(self):
        """Missing 'days' in profile should default to 1."""
        profile = {}
        recs = [{"name": "景点1"}]
        result = _check_feasibility(profile, recs)
        assert result["feasible"] is True

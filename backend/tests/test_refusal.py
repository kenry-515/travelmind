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


# ── KB City Coverage ─────────────────────────────────────


class TestCityCoverage:
    def test_kb_city_is_covered(self):
        """A known KB city should be covered."""
        covered, reason = check_city_coverage("重庆")
        assert covered is True
        assert reason == ""

    def test_kb_city_chengdu_is_covered(self):
        covered, reason = check_city_coverage("成都")
        assert covered is True

    def test_unknown_city_not_covered(self):
        """A city outside the KB should NOT be covered."""
        covered, reason = check_city_coverage("纽约")
        assert covered is False
        assert "纽约" in reason
        assert "暂不在" in reason or "覆盖" in reason

    def test_empty_city_not_covered(self):
        covered, reason = check_city_coverage("")
        assert covered is False

    def test_none_city_not_covered(self):
        covered, reason = check_city_coverage(None)
        assert covered is False

    def test_city_substring_matches(self):
        """Partial city name should match (e.g. '北京' should be covered)."""
        covered, reason = check_city_coverage("北京")
        # 北京 is in the KB
        assert covered is True

    def test_kb_cities_loaded(self):
        """_get_kb_cities should return a non-empty set."""
        _reset_kb_cities()
        cities = _get_kb_cities()
        assert len(cities) >= 10
        assert "重庆" in cities
        assert "成都" in cities


# ── Refuse Action ─────────────────────────────────────────


class TestRefuseAction:
    def test_next_action_refuses_unknown_city(self):
        """When city is set to an unknown city, next_action should refuse."""
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
        """When city is a KB city, next_action should proceed to confirming."""
        state = {
            "stage": "collecting",
            "slots": dict(DEFAULT_SLOTS, city="重庆"),
            "followups_used": 3,
            "itinerary": None,
            "queued": [],
            "touched": 0,
        }
        action = next_action(state)
        assert action["type"] == "confirm"
        assert action["confirm"] is True

    def test_next_action_suggests_on_first_unknown(self):
        """With followup budget remaining and BOTH required slots filled,
        unknown city triggers suggestions."""
        state = {
            "stage": "collecting",
            "slots": dict(DEFAULT_SLOTS, city="纽约", days=3),
            "followups_used": 0,
            "itinerary": None,
            "queued": [],
            "touched": 0,
        }
        action = next_action(state)
        # Both required slots filled → falls through to city coverage check
        assert action["type"] in ("suggest", "refuse")
        if action["type"] == "suggest":
            assert action.get("suggestions")


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

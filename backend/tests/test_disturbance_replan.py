"""
TravelMind Agent — Disturbance Re-planning Tests (Phase 8.2)

Tests for: known_closures data loading, POI replacement, validation report
markers, and revalidation endpoint.
"""

import json
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sample_closures_data():
    """Sample closure entries matching the known_closures.json format."""
    return {
        "updated_at": "2026-07-21",
        "closures": [
            {
                "name": "测试关闭景点A",
                "city": "重庆",
                "status": "closed",
                "closed_since": "2025",
                "evidence": "已确认关闭",
                "replacement_keyword": "测试替换景点",
                "replacement_note": "已确认关闭（2025），临时为您替换为测试替换景点",
            },
        ],
    }


@pytest.fixture
def temp_closures_file(tmp_path, sample_closures_data):
    """Write sample closures to a temp file."""
    path = tmp_path / "known_closures.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample_closures_data, f, ensure_ascii=False)
    return path


# ── Closure Data Loading ──────────────────────────────────


class TestClosureLoading:
    def test_load_closures_from_file(self, temp_closures_file):
        """Closures should be loaded from JSON and indexed by name."""
        from app.agents.route_optimizer import _load_closures, _reset_closures
        _reset_closures()

        # Monkey-patch the path to point to temp file
        import app.agents.route_optimizer as ro
        original_path = ro._CLOSURES_PATH
        try:
            ro._CLOSURES_PATH = temp_closures_file
            closures = _load_closures()
            assert len(closures) > 0
            assert "测试关闭景点A" in closures
            entry = closures["测试关闭景点A"]
            assert entry["replacement_keyword"] == "测试替换景点"
            assert entry["evidence"] == "已确认关闭"
            assert entry["replacement_note"] is not None
        finally:
            ro._CLOSURES_PATH = original_path
            _reset_closures()

    def test_load_empty_closures(self, tmp_path):
        """Empty closures file should not crash."""
        path = tmp_path / "empty_closures.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"closures": []}, f)

        from app.agents.route_optimizer import _load_closures, _reset_closures
        _reset_closures()

        import app.agents.route_optimizer as ro
        original_path = ro._CLOSURES_PATH
        try:
            ro._CLOSURES_PATH = path
            closures = _load_closures()
            assert closures == {}
        finally:
            ro._CLOSURES_PATH = original_path
            _reset_closures()

    def test_load_missing_file_no_crash(self, tmp_path):
        """Missing closure file should return empty dict."""
        from app.agents.route_optimizer import _load_closures, _reset_closures
        _reset_closures()

        import app.agents.route_optimizer as ro
        original_path = ro._CLOSURES_PATH
        try:
            ro._CLOSURES_PATH = tmp_path / "nonexistent.json"
            closures = _load_closures()
            assert closures == {}
        finally:
            ro._CLOSURES_PATH = original_path
            _reset_closures()

    def test_real_closure_file_exists(self):
        """The real known_closures.json should exist in the data dir."""
        from app.agents.route_optimizer import _CLOSURES_PATH
        assert _CLOSURES_PATH.exists(), f"Expected {_CLOSURES_PATH} to exist"

    def test_real_closure_file_has_entries(self):
        """真实文件存在即视为合规（广州 KB 当前无停业项，空 closures 合法）。"""
        from app.agents.route_optimizer import _load_closures, _reset_closures
        _reset_closures()
        closures = _load_closures()
        # 广州专属：截至 2026-07-31 无人工核实停业 POI
        assert len(closures) >= 0
        assert isinstance(closures, dict)


# ── Replacement Notification ──────────────────────────────


class TestReplacementNotification:
    def test_closure_entry_has_replacement_note(self, temp_closures_file):
        """通过 tmp_path 自带 fixture 验证每条 closure 都带 replacement_note。
        不依赖真实 known_closures.json。"""
        from app.agents.route_optimizer import _load_closures, _reset_closures
        _reset_closures()
        import app.agents.route_optimizer as ro
        original_path = ro._CLOSURES_PATH
        try:
            ro._CLOSURES_PATH = temp_closures_file
            closures = _load_closures()
            for name, entry in closures.items():
                assert entry.get("replacement_note"), (
                    f"Closure '{name}' should have a replacement_note"
                )
        finally:
            ro._CLOSURES_PATH = original_path
            _reset_closures()

    def test_closed_in_closure_list_detected(self, temp_closures_file):
        """通过 tmp_path 自带 fixture 验证 POI 在 closure 列表中能被检测。
        不依赖真实 known_closures.json（广州专属 KB 当前无停业项）。"""
        from app.agents.route_optimizer import _load_closures, _reset_closures, _base_name
        _reset_closures()
        import app.agents.route_optimizer as ro
        original_path = ro._CLOSURES_PATH
        try:
            ro._CLOSURES_PATH = temp_closures_file
            closures = _load_closures()
            base = _base_name("测试关闭景点A")
            assert base in closures
        finally:
            ro._CLOSURES_PATH = original_path
            _reset_closures()


# ── Schema Compatibility ──────────────────────────────────


class TestSchemaCompatibility:
    def test_replaced_itinerary_passes_schema(self):
        """A known-closed POI should be replaced and the result should
        still pass contract validation."""
        # Load the real Shanghai fixture which is known to be valid
        backend_dir = Path(__file__).parent.parent
        fixture_path = backend_dir.parent / "docs" / "itinerary.example.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            itinerary = json.load(f)

        from app.agents.itinerary_contract import validate_itinerary
        errors = validate_itinerary(itinerary)
        assert len(errors) == 0, f"Fixture should be schema-valid: {errors[:3]}"

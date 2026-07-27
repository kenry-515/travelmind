"""
TravelMind Agent — Tests for NameNormalizer (Phase 11.1)
"""

import pytest
from app.services.name_normalizer import (
    NameNormalizer,
    extract_core_name,
    normalize_poi_name,
    poi_names_match,
    build_canonical_map,
)


class TestExtractCoreName:
    """Unit tests for core name extraction (no alias file needed)."""

    def test_basic_name_unchanged(self):
        assert extract_core_name("洪崖洞") == "洪崖洞"

    def test_strips_city_prefix(self):
        assert extract_core_name("重庆洪崖洞") == "洪崖洞"

    def test_strips_generic_suffix(self):
        assert extract_core_name("洪崖洞景区") == "洪崖洞"
        assert extract_core_name("洪崖洞民俗风貌区") == "洪崖洞民俗风貌区"

    def test_strips_both_prefix_and_suffix(self):
        assert extract_core_name("重庆磁器口古镇") == "磁器口"

    def test_removes_punctuation(self):
        assert extract_core_name("洪崖洞（重庆）") == "洪崖洞重庆"
        assert extract_core_name("洪崖洞·民俗区") == "洪崖洞民俗区"

    def test_handles_whitespace(self):
        assert extract_core_name("  洪崖洞  ") == "洪崖洞"

    def test_handles_empty(self):
        assert extract_core_name("") == ""
        assert extract_core_name(None) == ""

    def test_converts_financial_chars(self):
        assert "二" in extract_core_name("贰拾")

    def test_strips_longest_suffix_first(self):
        # 国家森林公园 should be stripped before 公园
        assert extract_core_name("张家界国家森林公园") == "张家界"

    def test_leaves_short_names_unchanged(self):
        # Don't strip suffixes from very short names
        assert extract_core_name("南山") == "南山"


class TestNameNormalizerWithAliases:
    """Integration tests with the actual alias file."""

    @pytest.fixture(autouse=True)
    def reset(self):
        NameNormalizer.reset_singleton()
        yield
        NameNormalizer.reset_singleton()

    def test_normalize_with_known_alias(self):
        nn = NameNormalizer.singleton()
        # These aliases should be resolved by the auto-generated file
        result = nn.normalize("故宫")
        # 故宫 → 故宫博物院 (via aliases or core matching)
        assert len(result) >= 2

    def test_matches_same_place_different_names(self):
        nn = NameNormalizer.singleton()
        # Same place, different names
        assert nn.matches("洪崖洞", "洪崖洞民俗风貌区")
        assert nn.matches("重庆磁器口", "磁器口古镇")

    def test_matches_exact(self):
        nn = NameNormalizer.singleton()
        assert nn.matches("洪崖洞", "洪崖洞")

    def test_matches_different_places(self):
        nn = NameNormalizer.singleton()
        assert not nn.matches("洪崖洞", "解放碑")
        assert not nn.matches("故宫", "长城")

    def test_matches_with_traditional_chinese(self):
        nn = NameNormalizer.singleton()
        # zhconv should handle traditional → simplified
        assert nn.matches("斷橋殘雪", "断桥残雪")

    def test_singleton_returns_same_instance(self):
        a = NameNormalizer.singleton()
        b = NameNormalizer.singleton()
        assert a is b

    def test_reset_singleton(self):
        a = NameNormalizer.singleton()
        NameNormalizer.reset_singleton()
        b = NameNormalizer.singleton()
        assert a is not b

    def test_get_variants(self):
        nn = NameNormalizer.singleton()
        variants = nn.get_variants("故宫博物院")
        assert len(variants) >= 1
        assert "故宫博物院" in variants or any("故宫" in v for v in variants)


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def reset(self):
        NameNormalizer.reset_singleton()
        yield
        NameNormalizer.reset_singleton()

    def test_normalize_poi_name(self):
        result = normalize_poi_name("重庆洪崖洞景区")
        assert isinstance(result, str)
        assert len(result) >= 2

    def test_poi_names_match(self):
        assert poi_names_match("洪崖洞", "洪崖洞民俗风貌区")
        assert not poi_names_match("洪崖洞", "解放碑")

    def test_build_canonical_map(self):
        names = [
            "洪崖洞民俗风貌区",
            "解放碑步行街",
            "重庆磁器口古镇",
            "西湖风景名胜区",
        ]
        result = build_canonical_map(names)
        assert isinstance(result, dict)
        # Should have at most 4 entries (possibly fewer if aliases collapse)
        assert 0 < len(result) <= 4
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())

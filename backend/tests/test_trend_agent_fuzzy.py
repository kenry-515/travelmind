"""
TravelMind Agent — Trend Agent 模糊匹配与集成测试（Phase 12.29+）
"""

import json
import pytest
from unittest.mock import MagicMock, patch



MOCK_TRENDS = [
    {"place": "洪崖洞", "city": "重庆", "tag": "夜景", "heat_score": 95},
    {"place": "重庆火锅(解放碑店)", "city": "重庆", "tag": "美食", "heat_score": 85},
    {"place": "南山一棵树观景台", "city": "重庆", "tag": "夜景", "heat_score": 75},
    {"place": "宽窄巷子", "city": "成都", "tag": "美食", "heat_score": 90},
]


@pytest.fixture(autouse=True)
def mock_trends():
    """Reset cache and mock _load_trends to return test data."""
    import app.agents.trend_agent as ta
    ta._trends_cache = MOCK_TRENDS
    yield
    ta._trends_cache = None


# ── 纯函数测试 ──

def test_fuzzy_match_exact():
    from app.agents.trend_agent import _fuzzy_match_name
    assert _fuzzy_match_name("洪崖洞", "洪崖洞") is True


def test_fuzzy_match_substring():
    from app.agents.trend_agent import _fuzzy_match_name
    assert _fuzzy_match_name("解放碑", "重庆火锅(解放碑店)") is True


def test_fuzzy_match_no_match():
    from app.agents.trend_agent import _fuzzy_match_name
    assert _fuzzy_match_name("洪崖洞", "成都大熊猫") is False


def test_fuzzy_match_partial():
    from app.agents.trend_agent import _fuzzy_match_name
    assert _fuzzy_match_name("天安门", "天一广场") is False


def test_score_normalization():
    from app.agents.trend_agent import _normalize_score
    assert _normalize_score(100) == 1.0
    assert _normalize_score(0) == 0.0
    assert _normalize_score(50) == 0.5


# ── analyze_trends 集成测试（使用 mock 缓存）──

@pytest.mark.asyncio
async def test_analyze_known_city():
    from app.agents.trend_agent import analyze_trends
    trends = await analyze_trends("重庆", ["美食", "夜景"])
    assert trends is not None
    assert len(trends) > 0


@pytest.mark.asyncio
async def test_analyze_tags_filter():
    from app.agents.trend_agent import analyze_trends
    trends = await analyze_trends("重庆", ["夜景"])
    assert trends is not None


@pytest.mark.asyncio
async def test_analyze_unknown_city():
    from app.agents.trend_agent import analyze_trends
    trends = await analyze_trends("UNKNOWN", ["美食"])
    assert trends == []


@pytest.mark.asyncio
async def test_analyze_no_tags():
    from app.agents.trend_agent import analyze_trends
    trends = await analyze_trends("重庆", [])
    assert trends is not None

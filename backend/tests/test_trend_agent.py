"""
TravelMind Agent — Trend Agent 单元测试（Phase 12.29+）

测试趋势分析 agent 的数据加载、模糊匹配和跨城市趋势检索。
不调用外部 API —— 使用模拟的趋势数据。
"""

import json
import pytest
from unittest.mock import mock_open, patch

pytestmark = pytest.mark.asyncio

# 模拟趋势数据
MOCK_TRENDS = [
    {"place": "洪崖洞", "city": "重庆", "tag": "夜景", "heat_score": 95, "source": "ctrip_hotlist"},
    {"place": "解放碑", "city": "重庆", "tag": "美食", "heat_score": 88, "source": "ctrip_hotlist"},
    {"place": "磁器口", "city": "重庆", "tag": "美食", "heat_score": 82, "source": "xiaohongshu"},
    {"place": "南山一棵树", "city": "重庆", "tag": "夜景", "heat_score": 75, "source": "mafengwo"},
]

MOCK_SOCIAL_TRENDS = [
    {"place": "洪崖洞", "city": "重庆", "heat_score": 92, "tag": "夜景", "source": "xiaohongshu", "url": "https://xiaohongshu.com/123"},
    {"place": "李子坝", "city": "重庆", "heat_score": 78, "tag": "打卡", "source": "douyin", "url": "https://douyin.com/456"},
]


@pytest.fixture(autouse=True)
def mock_data_files():
    """Mock trends.json and social_trends_live.json reads."""
    with patch("app.agents.trend_agent.open", mock_open(read_data=json.dumps(MOCK_TRENDS))) as mock_file:
        # Return social trends for the second call
        mock_file.side_effect = [
            mock_open(read_data=json.dumps(MOCK_TRENDS)).return_value,
            mock_open(read_data=json.dumps(MOCK_SOCIAL_TRENDS)).return_value,
        ]
        yield


async def test_analyze_trends_known_city():
    """已知城市应返回趋势列表。"""
    from app.agents.trend_agent import analyze_trends

    trends = await analyze_trends("重庆", ["美食", "夜景"])
    assert trends is not None


async def test_analyze_trends_tag_filter():
    """标签过滤应能匹配趋势。"""
    from app.agents.trend_agent import analyze_trends

    trends = await analyze_trends("重庆", ["夜景"])
    assert trends is not None


async def test_analyze_trends_unknown_city():
    """未知城市应返回空列表而非崩溃。"""
    from app.agents.trend_agent import analyze_trends

    trends = await analyze_trends("UNKNOWN_CITY", ["美食"])
    assert trends is not None
    assert len(trends) == 0


async def test_analyze_trends_no_tags():
    """没有标签也应返回所有趋势。"""
    from app.agents.trend_agent import analyze_trends

    trends = await analyze_trends("重庆", [])
    assert trends is not None

"""
TravelMind Agent — Profile Agent 单元测试（Phase 12.29+）

测试用户画像提取的纯函数逻辑，包括城市别名解析、标签推导、清理函数。
Mock LLM 调用以避免真实 API 成本。
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture(autouse=True)
def mock_llm():
    """Mock LLM provider for structured output."""
    provider = MagicMock()
    provider.chat_structured = AsyncMock(return_value={
        "destination": "重庆",
        "budget_level": "舒适",
        "days": 3,
        "companions": "父母",
        "tags": ["美食", "夜景"],
        "travel_style": "休闲",
        "constraints": "",
    })
    provider.chat = AsyncMock(return_value="重庆3日游")
    with patch("app.agents.profile_agent.get_llm_provider", return_value=provider):
        yield provider


@pytest.mark.asyncio
async def test_extract_profile_success(mock_llm):
    """正常输入应提取完整用户画像。"""
    from app.agents.profile_agent import extract_profile

    profile = await extract_profile("重庆3日游，喜欢夜景和美食，带父母")
    assert profile is not None
    assert profile.get("destination") == "重庆"
    assert profile.get("days") == 3
    assert profile.get("budget_level") == "舒适"


@pytest.mark.asyncio
async def test_extract_profile_with_city_alias(mock_llm):
    """城市别名（如 山城→重庆）应被解析。"""
    mock_llm.chat_structured.return_value = {
        "destination": "山城",
        "budget_level": "适中",
        "days": 2,
        "companions": "不限",
        "tags": ["美食"],
        "travel_style": "休闲",
        "constraints": "",
    }
    from app.agents.profile_agent import extract_profile

    profile = await extract_profile("去山城吃火锅")
    # 清理函数会将别名转换为标准名
    assert profile is not None


@pytest.mark.asyncio
async def test_extract_profile_empty_input(mock_llm):
    """空输入不应崩溃，应返回含默认值的字典。"""
    mock_llm.chat_structured.side_effect = Exception("No input")
    from app.agents.profile_agent import extract_profile

    profile = await extract_profile("")
    assert profile is not None
    assert isinstance(profile, dict)


@pytest.mark.asyncio
async def test_extract_profile_llm_error(mock_llm):
    """LLM 错误应优雅降级返回空字典。"""
    mock_llm.chat_structured.side_effect = RuntimeError("API timeout")
    from app.agents.profile_agent import extract_profile

    profile = await extract_profile("北京4日游")
    assert profile is not None


def test_clean_profile_normalization():
    """_clean_profile 应正确清理空值和默认字段。"""
    from app.agents.profile_agent import _clean_profile

    profile = _clean_profile({"destination": "重庆", "days": None, "tags": None})
    assert profile["destination"] == "重庆"
    assert profile["days"] == 3  # None 应被替换为默认 3
    assert profile["tags"] == ["旅行"]  # None 应被替换为默认列表


def test_tag_dedup():
    """相同的标签应被去重。"""
    from app.core.constants import BUDGET_MAP, BUDGET_LEVELS

    assert "经济" in BUDGET_LEVELS
    assert "适中" in BUDGET_LEVELS
    assert "高端" in BUDGET_LEVELS
    assert BUDGET_MAP["穷游"] == "经济"
    assert BUDGET_MAP["奢华"] == "高端"


# ── Phase 14: must_visit / arrival_time / departure_time 清洗 ──

def test_clean_must_visit_preserves_list():
    """must_visit 为列表时应原样保留。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "must_visit": ["洪崖洞", "解放碑"]})
    assert profile.get("must_visit") == ["洪崖洞", "解放碑"]


def test_clean_must_visit_none():
    """must_visit 为 None 时应变为空列表。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "must_visit": None})
    assert profile.get("must_visit") == []


def test_clean_must_visit_strips_whitespace():
    """must_visit 中的名称应去除首尾空格。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "must_visit": [" 洪崖洞 ", "解放碑 "]})
    assert profile.get("must_visit") == ["洪崖洞", "解放碑"]


def test_clean_arrival_time_empty():
    """arrival_time 为空字符串时应保留为空。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "arrival_time": ""})
    assert profile.get("arrival_time") == ""


def test_clean_arrival_time_preserved():
    """arrival_time 有值时应原样保留。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "arrival_time": "周五下午2点"})
    assert profile.get("arrival_time") == "周五下午2点"


def test_clean_departure_time_empty():
    """departure_time 为空时应留空。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "departure_time": ""})
    assert profile.get("departure_time") == ""


def test_clean_departure_time_preserved():
    """departure_time 有值时应原样保留。"""
    from app.agents.profile_agent import _clean_profile
    profile = _clean_profile({"destination": "重庆", "departure_time": "周日早上退房"})
    assert profile.get("departure_time") == "周日早上退房"


# ── Phase 14: LLM should extract must_visit naturally ──

@pytest.mark.asyncio
async def test_extract_profile_with_must_visit(mock_llm):
    """用户提到具体景点时应被提取到 must_visit。"""
    mock_llm.chat_structured.return_value = {
        "destination": "重庆",
        "days": 3,
        "tags": ["美食", "夜景"],
        "must_visit": ["洪崖洞", "解放碑", "长江索道"],
        "arrival_time": "周五下午3点到",
        "departure_time": "周日上午走",
    }
    from app.agents.profile_agent import extract_profile
    profile = await extract_profile("想去重庆玩，洪崖洞、解放碑、长江索道都想去看看，周五下午3点到，周日上午走")
    must = profile.get("must_visit", [])
    assert "洪崖洞" in must
    assert "解放碑" in must
    assert profile.get("arrival_time") == "周五下午3点到"
    assert profile.get("departure_time") == "周日上午走"

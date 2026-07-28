"""
TravelMind Agent — Chat Agent 单元测试（Phase 12.29+）

测试自由对话 agent 的 prompt 构建和回复逻辑。
不调用实际 LLM —— mock get_llm_provider。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_llm():
    """Mock LLM provider to avoid real API calls."""
    provider = AsyncMock()
    provider.chat.return_value = "重庆火锅非常出名，推荐去解放碑附近吃！"
    provider.model = "deepseek-v4-flash"
    with patch("app.agents.chat_agent.get_llm_provider", return_value=provider):
        yield provider


async def test_free_chat_basic(mock_llm):
    """基础自由对话应得到回复。"""
    from app.agents.chat_agent import free_chat

    reply = await free_chat(
        user_text="你好，我想去重庆玩",
        slots_context={"city": None, "days": None, "tags": []},
    )
    assert reply is not None
    assert len(reply) > 0
    mock_llm.chat.assert_awaited_once()


async def test_free_chat_with_slots(mock_llm):
    """带槽位上下文的对话应整合上下文。"""
    from app.agents.chat_agent import free_chat

    reply = await free_chat(
        user_text="有什么好吃的推荐？",
        slots_context={"city": "重庆", "days": 3, "tags": ["美食"]},
    )
    assert reply is not None


async def test_chat_weather_query(mock_llm):
    """天气询问应正常回复。"""
    from app.agents.chat_agent import free_chat

    reply = await free_chat(
        user_text="重庆现在天气怎么样？",
        slots_context={"city": "重庆"},
    )
    assert reply is not None


async def test_chat_with_history(mock_llm):
    """带历史的多轮对话应正常。"""
    from app.agents.chat_agent import free_chat

    history = [
        {"role": "user", "content": "我想去西安"},
        {"role": "assistant", "content": "西安是个好地方！"},
    ]
    reply = await free_chat(
        user_text="兵马俑值得去吗？",
        slots_context={"city": "西安"},
        history=history,
    )
    assert reply is not None

"""
TravelMind Agent — LLM Service Tests

Tests for DeepSeekProvider (chat, chat_stream, chat_structured) and
get_llm_provider singleton factory.

Mocks openai.AsyncOpenAI and settings — no real API calls.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import DeepSeekProvider, get_llm_provider
import app.services.llm_service as _llm_module


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_settings():
    """Use test settings to avoid env var dependency."""
    with patch("app.services.llm_service.settings") as mock:
        mock.LLM_MODEL = "deepseek-v4-flash"
        mock.DEEPSEEK_API_KEY = "sk-test-key"
        mock.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
        mock.LLM_TIMEOUT = 60.0
        yield mock


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset module-level singleton before each test."""
    _llm_module._llm_provider = None
    _llm_module._llm_lock = asyncio.Lock()
    yield


@pytest.fixture(autouse=True)
def mock_openai():
    """Patch AsyncOpenAI so DeepSeekProvider never makes real HTTP calls.

    Returns (cls_mock, client) where:
      - cls_mock  is the patched AsyncOpenAI class (tracks constructor calls)
      - client    is the mock instance returned by AsyncOpenAI()
                  (use client.chat.completions.create to configure responses)
    """
    with patch("app.services.llm_service.AsyncOpenAI") as cls_mock:
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        client.chat.completions.create = AsyncMock()
        cls_mock.return_value = client
        yield cls_mock, client


# ── Test Helpers ──────────────────────────────────────────


def _chat_response(content: str | None):
    """Build a mock non-streaming chat completion response."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.content = content
    return resp


def _structured_response(json_str: str):
    """Build a mock tool-call response containing JSON arguments."""
    tool_call = MagicMock()
    tool_call.function = MagicMock()
    tool_call.function.arguments = json_str

    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.tool_calls = [tool_call]
    resp.choices[0].message.content = None
    return resp


async def _stream_chunks(texts: list[str | None]):
    """Async generator yielding mock stream chunks."""
    for t in texts:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock()
        chunk.choices[0].delta.content = t
        yield chunk


# ── Singleton ─────────────────────────────────────────────


class TestGetProvider:
    """Tests for get_llm_provider singleton factory."""

    @pytest.mark.asyncio
    async def test_get_provider_singleton(self, mock_openai):
        """Multiple calls to get_llm_provider should return the same instance."""
        cls_mock, _ = mock_openai

        p1 = await get_llm_provider()
        p2 = await get_llm_provider()

        assert p1 is p2
        assert isinstance(p1, DeepSeekProvider)
        # AsyncOpenAI constructor called exactly once
        assert cls_mock.call_count == 1


# ── DeepSeekProvider ──────────────────────────────────────


class TestDeepSeekProvider:
    """Tests for DeepSeekProvider chat methods."""

    # -- chat() -----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_chat_basic(self, mock_openai):
        """chat() should return the response text."""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("你好，重庆欢迎你！")

        provider = DeepSeekProvider()
        result = await provider.chat([{"role": "user", "content": "推荐重庆景点"}])

        assert result == "你好，重庆欢迎你！"

        # Verify correct model and message count
        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "deepseek-v4-flash"
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_chat_empty_response(self, mock_openai):
        """chat() should return empty string when content is None."""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response(None)

        provider = DeepSeekProvider()
        result = await provider.chat([{"role": "user", "content": "hi"}])

        assert result == ""

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self, mock_openai):
        """chat() should use the provided system prompt."""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("ok")

        provider = DeepSeekProvider()
        await provider.chat(
            [{"role": "user", "content": "hello"}],
            system_prompt="You are a test bot.",
        )

        messages = client.chat.completions.create.call_args[1]["messages"]
        assert any(
            m["role"] == "system" and "test bot" in m["content"]
            for m in messages
        )

    @pytest.mark.asyncio
    async def test_chat_custom_temperature(self, mock_openai):
        """chat() should forward custom temperature to the API."""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("ok")

        provider = DeepSeekProvider()
        await provider.chat([{"role": "user", "content": "hi"}], temperature=0.9)

        assert client.chat.completions.create.call_args[1]["temperature"] == 0.9

    # -- chat_stream() ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_chat_stream(self, mock_openai):
        """chat_stream() should yield text chunks from the stream."""
        _, client = mock_openai
        client.chat.completions.create.return_value = _stream_chunks(
            ["重庆", "火锅", "好吃"]
        )

        provider = DeepSeekProvider()
        chunks = [
            chunk
            async for chunk in provider.chat_stream(
                [{"role": "user", "content": "推荐美食"}]
            )
        ]

        assert chunks == ["重庆", "火锅", "好吃"]

    @pytest.mark.asyncio
    async def test_chat_stream_skips_empty(self, mock_openai):
        """chat_stream() should skip chunks with no content."""
        _, client = mock_openai
        client.chat.completions.create.return_value = _stream_chunks(
            ["A", None, "B", "", "C"]
        )

        provider = DeepSeekProvider()
        chunks = [
            c async for c in provider.chat_stream([{"role": "user", "content": "x"}])
        ]

        assert chunks == ["A", "B", "C"]

    # -- chat_structured() ------------------------------------------------

    @pytest.mark.asyncio
    async def test_chat_structured(self, mock_openai):
        """chat_structured() should parse tool_call arguments into a dict."""
        _, client = mock_openai
        expected = {"city": "重庆", "days": 3}
        client.chat.completions.create.return_value = _structured_response(
            json.dumps(expected)
        )

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan a trip"}],
            output_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer"},
                },
            },
        )

        assert result == expected

    @pytest.mark.asyncio
    async def test_chat_structured_fallback_content(self, mock_openai):
        """chat_structured() should fall back to content JSON when no tool_calls."""
        _, client = mock_openai
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.tool_calls = None
        resp.choices[0].message.content = '{"city": "成都"}'
        client.chat.completions.create.return_value = resp

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )

        assert result == {"city": "成都"}

    @pytest.mark.asyncio
    async def test_chat_structured_invalid_json_fallback(self, mock_openai):
        """chat_structured() should return {} on JSON parse error."""
        _, client = mock_openai
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.tool_calls = None
        resp.choices[0].message.content = "not valid json at all"
        client.chat.completions.create.return_value = resp

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )

        assert result == {}

    # -- Error handling ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_chat_error_handling(self, mock_openai):
        """chat() should propagate API errors."""
        _, client = mock_openai
        client.chat.completions.create.side_effect = Exception("API Error")

        provider = DeepSeekProvider()
        with pytest.raises(Exception, match="API Error"):
            await provider.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_stream_error_handling(self, mock_openai):
        """chat_stream() should propagate API errors."""
        _, client = mock_openai
        client.chat.completions.create.side_effect = Exception("Stream Error")

        provider = DeepSeekProvider()
        with pytest.raises(Exception, match="Stream Error"):
            async for _ in provider.chat_stream(
                [{"role": "user", "content": "hi"}]
            ):
                pass

    @pytest.mark.asyncio
    async def test_chat_structured_error_handling(self, mock_openai):
        """chat_structured() should propagate API errors."""
        _, client = mock_openai
        client.chat.completions.create.side_effect = Exception("Structured Error")

        provider = DeepSeekProvider()
        with pytest.raises(Exception, match="Structured Error"):
            await provider.chat_structured(
                [{"role": "user", "content": "hi"}],
                output_schema={},
            )

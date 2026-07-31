"""
LLM Service 稳定性增强测试（Phase 16.6）。

覆盖：
- JSON 修复回退：chat_structured 在 tool_call/content 解析失败时自动修复
- 超时分层：chat_structured 默认使用 1.5x 超时
- 并发限流：Semaphore 限制同时进行的 LLM 调用
- thinking/tool_choice 冲突：thinking 模式下自动改用 tool_choice="auto"
- 向后兼容：新增 timeout 参数不破坏现有调用
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import DeepSeekProvider, get_llm_provider, reset_llm_provider
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
        mock.LLM_MAX_CONCURRENT = 4
        mock.LLM_STRUCTURED_TIMEOUT_MULT = 1.5
        yield mock


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset module-level singleton before each test."""
    reset_llm_provider()
    yield
    reset_llm_provider()


@pytest.fixture(autouse=True)
def mock_openai():
    """Patch AsyncOpenAI so DeepSeekProvider never makes real HTTP calls."""
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
    resp.usage = None
    return resp


def _content_only_response(content: str):
    """Build a response with no tool_calls, only content."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.content = content
    resp.usage = None
    return resp


# ── JSON 修复回退测试 ─────────────────────────────────────


class TestJsonRepairFallback:
    """chat_structured 应在 JSON 解析失败时自动应用修复。"""

    @pytest.mark.asyncio
    async def test_tool_call_with_markdown_wrapper(self, mock_openai):
        """tool_call 参数带 markdown 包裹时应被修复。"""
        _, client = mock_openai
        expected = {"city": "重庆", "days": 3}
        # LLM 偶发在 tool_call arguments 里返回 markdown 包裹的 JSON
        wrapped = f'```json\n{json.dumps(expected, ensure_ascii=False)}\n```'
        client.chat.completions.create.return_value = _structured_response(wrapped)

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_tool_call_with_trailing_comma(self, mock_openai):
        """tool_call 参数带尾逗号时应被修复。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _structured_response(
            '{"city": "成都", "days": 2,}'
        )

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )
        assert result == {"city": "成都", "days": 2}

    @pytest.mark.asyncio
    async def test_content_with_markdown_fallback(self, mock_openai):
        """无 tool_call 时，content 里的 markdown JSON 应被修复。"""
        _, client = mock_openai
        expected = {"trip": {"city": "三亚"}}
        wrapped = f'```json\n{json.dumps(expected, ensure_ascii=False)}\n```'
        client.chat.completions.create.return_value = _content_only_response(wrapped)

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_content_with_explanation_text(self, mock_openai):
        """content 里 JSON 前后有解释文本时应被提取。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _content_only_response(
            '好的，这是您的行程：\n{"city": "重庆"}\n希望您喜欢！'
        )

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )
        assert result == {"city": "重庆"}

    @pytest.mark.asyncio
    async def test_completely_invalid_raises(self, mock_openai):
        """完全无法修复的输出应抛出 ValueError。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _content_only_response(
            "这是纯文本，没有任何 JSON 结构"
        )

        provider = DeepSeekProvider()
        with pytest.raises(ValueError, match="chat_structured failed to parse"):
            await provider.chat_structured(
                [{"role": "user", "content": "plan"}],
                output_schema={},
            )


# ── 超时分层测试 ─────────────────────────────────────────


class TestTimeoutStratification:
    """不同方法应使用不同的超时配置。"""

    @pytest.mark.asyncio
    async def test_chat_uses_default_timeout(self, mock_openai):
        """chat() 应使用基础超时。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("ok")

        provider = DeepSeekProvider()
        await provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["timeout"] == 60.0

    @pytest.mark.asyncio
    async def test_structured_uses_extended_timeout(self, mock_openai):
        """chat_structured() 应使用 1.5x 超时（默认 90s）。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _structured_response('{"ok": 1}')

        provider = DeepSeekProvider()
        await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["timeout"] == 90.0  # 60 * 1.5

    @pytest.mark.asyncio
    async def test_chat_timeout_override(self, mock_openai):
        """chat() 的 timeout 参数应覆盖默认值。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("ok")

        provider = DeepSeekProvider()
        await provider.chat([{"role": "user", "content": "hi"}], timeout=30.0)

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["timeout"] == 30.0

    @pytest.mark.asyncio
    async def test_structured_timeout_override(self, mock_openai):
        """chat_structured() 的 timeout 参数应覆盖默认值。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _structured_response('{"ok": 1}')

        provider = DeepSeekProvider()
        await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
            timeout=120.0,
        )

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["timeout"] == 120.0


# ── 并发限流测试 ─────────────────────────────────────────


class TestConcurrencyControl:
    """Semaphore 应限制同时进行的 LLM 调用。"""

    @pytest.mark.asyncio
    async def test_concurrent_calls_limited(self, mock_openai):
        """max_concurrent=2 时，最多 2 个调用同时执行。"""
        _, client = mock_openai

        provider = DeepSeekProvider(max_concurrent=2)

        # 跟踪同时在执行的调用数
        in_flight = 0
        max_in_flight = 0

        async def tracking_create(*args, **kwargs):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.05)  # 模拟 IO 延迟
            in_flight -= 1
            return _chat_response("ok")  # 直接返回，避免回调 mock 造成递归

        client.chat.completions.create.side_effect = tracking_create

        # 发起 6 个并发调用
        tasks = [
            provider.chat([{"role": "user", "content": f"msg {i}"}])
            for i in range(6)
        ]
        await asyncio.gather(*tasks)

        # 并发上限不应超过 max_concurrent=2
        assert max_in_flight <= 2
        assert max_in_flight >= 1  # 至少有 1 个在执行

    @pytest.mark.asyncio
    async def test_semaphore_does_not_deadlock(self, mock_openai):
        """正常调用不应死锁——所有调用都应完成。"""
        _, client = mock_openai

        provider = DeepSeekProvider(max_concurrent=3)

        async def quick_create(*args, **kwargs):
            await asyncio.sleep(0.01)
            return _chat_response("done")

        client.chat.completions.create.side_effect = quick_create

        tasks = [
            provider.chat([{"role": "user", "content": f"msg {i}"}])
            for i in range(10)
        ]
        # Python 3.10: gather 不支持 timeout 参数，用 wait_for 包裹
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

        assert len(results) == 10
        assert all(r == "done" for r in results)


# ── thinking/tool_choice 冲突测试 ────────────────────────


class TestThinkingToolChoiceConflict:
    """thinking 模式下应自动调整 tool_choice。"""

    @pytest.mark.asyncio
    async def test_non_thinking_forces_tool_choice(self, mock_openai):
        """非 thinking 模式应强制 tool_choice。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _structured_response('{"x": 1}')

        provider = DeepSeekProvider(thinking=False)
        await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["tool_choice"] == {
            "type": "function",
            "function": {"name": "output"},
        }

    @pytest.mark.asyncio
    async def test_thinking_uses_auto_tool_choice(self, mock_openai):
        """thinking 模式应使用 tool_choice='auto' 避免冲突。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _structured_response('{"x": 1}')

        provider = DeepSeekProvider(thinking=True)
        await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_thinking_extra_body_reflects_state(self, mock_openai):
        """thinking 状态应正确传到 extra_body。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("ok")

        provider = DeepSeekProvider(thinking=True)
        await provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = client.chat.completions.create.call_args[1]
        assert call_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


# ── 向后兼容测试 ─────────────────────────────────────────


class TestBackwardCompatibility:
    """新增的 timeout 参数不应破坏现有调用。"""

    @pytest.mark.asyncio
    async def test_chat_without_timeout_works(self, mock_openai):
        """chat() 不传 timeout 应正常工作。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _chat_response("hi")

        provider = DeepSeekProvider()
        result = await provider.chat([{"role": "user", "content": "hello"}])
        assert result == "hi"

    @pytest.mark.asyncio
    async def test_structured_without_timeout_works(self, mock_openai):
        """chat_structured() 不传 timeout 应正常工作。"""
        _, client = mock_openai
        client.chat.completions.create.return_value = _structured_response('{"ok": true}')

        provider = DeepSeekProvider()
        result = await provider.chat_structured(
            [{"role": "user", "content": "plan"}],
            output_schema={},
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_singleton_factory_still_works(self, mock_openai):
        """get_llm_provider 单例工厂应继续可用。"""
        p1 = await get_llm_provider()
        p2 = await get_llm_provider()
        assert p1 is p2
        assert isinstance(p1, DeepSeekProvider)


# ── planning_agent 向后兼容别名测试 ──────────────────────


class TestPlanningAgentAliases:
    """planning_agent 的 JSON 工具别名应继续可用。"""

    def test_repair_json_alias(self):
        from app.agents.planning_agent import _repair_json
        assert _repair_json('{"a": 1}') == {"a": 1}

    def test_extract_first_json_object_alias(self):
        from app.agents.planning_agent import _extract_first_json_object
        assert _extract_first_json_object('{"a": 1}') == '{"a": 1}'

    def test_parse_json_tolerant_alias(self):
        from app.agents.planning_agent import _parse_json_tolerant
        assert _parse_json_tolerant('text {"a": 1} end') == {"a": 1}

    def test_aliases_share_implementation(self):
        """别名应指向共享模块的同一函数。"""
        from app.agents.planning_agent import (
            _repair_json,
            _extract_first_json_object,
            _parse_json_tolerant,
        )
        from app.services.llm_json_utils import (
            repair_json,
            extract_first_json_object,
            parse_json_tolerant,
        )
        assert _repair_json is repair_json
        assert _extract_first_json_object is extract_first_json_object
        assert _parse_json_tolerant is parse_json_tolerant

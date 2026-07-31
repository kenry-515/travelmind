"""
TravelMind Agent — LLM Service
DeepSeek provider implementation using OpenAI-compatible SDK.

Phase 16.6 stability enhancements:
- Concurrency control (Semaphore): prevents 429 rate limiting under load
- Timeout stratification: structured calls get 1.5x timeout (heavier JSON gen)
- JSON repair fallback: reuses llm_json_utils to recover malformed output
- thinking/tool_choice conflict handling: auto-degrades when thinking is on
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from app.config.settings import settings
from app.core import BaseLLMProvider
from app.services.llm_json_utils import parse_structured_output

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────

TRAVEL_SYSTEM_PROMPT = """你是 TravelMind（智游伴），一个专业的 AI 旅行规划助手。

你的职责：
1. 理解用户的旅行需求（目的地、预算、天数、偏好、同行人员等）
2. 根据用户需求推荐合适的城市、景点、路线
3. 提供实用的旅行建议（交通、天气、美食、住宿等）
4. 帮助用户优化行程安排

回答规则：
- 使用中文回复，语气亲切专业
- 如果用户需求不明确，主动询问关键信息（目的地？天数？预算？同行人？兴趣爱好？）
- 推荐时给出具体理由，避免泛泛而谈
- 涉及地点时，提供简要介绍和适合人群
- 回答简洁但有深度，避免冗长

你是旅行专家，不是通用助手。始终围绕旅行规划展开对话。"""


# ── DeepSeek Provider ──────────────────────────────────

class DeepSeekProvider(BaseLLMProvider):
    """LLM provider backed by DeepSeek API (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: Optional[float] = None,
        thinking: bool = False,
        max_concurrent: Optional[int] = None,
    ):
        self.model = model or settings.LLM_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        # DeepSeek V4 defaults to thinking mode, which rejects forced
        # tool_choice and burns output tokens on reasoning. The old
        # deepseek-chat was non-thinking — disable it to keep behavior
        # (and cost/latency) consistent.
        self.thinking = thinking

        key = api_key or settings.DEEPSEEK_API_KEY
        if not key or key.startswith("sk-xxx"):
            logger.warning(
                "DEEPSEEK_API_KEY is not set or using placeholder. "
                "Set it in backend/.env to enable AI responses."
            )

        # trust_env=False: ignore the Windows system proxy — a stale local
        # proxy breaks httpx TLS, while api.deepseek.com is reachable directly.
        self._timeout = timeout or settings.LLM_TIMEOUT
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=base_url or settings.DEEPSEEK_BASE_URL,
            timeout=self._timeout,
            max_retries=2,
            http_client=httpx.AsyncClient(trust_env=False, timeout=self._timeout),
        )

        # Phase 16.6: 结构化调用超时 — 生成复杂 JSON 需更长时间
        self._structured_timeout = self._timeout * settings.LLM_STRUCTURED_TIMEOUT_MULT

        # Phase 16.6: 并发限流器 — 懒初始化以兼容测试中的多事件循环
        # 单例 provider 共享一个 Semaphore，生产环境全局生效；
        # 测试中每个 provider 实例独立，互不干扰。
        self._max_concurrent = max_concurrent or settings.LLM_MAX_CONCURRENT
        self._concurrency: Optional[asyncio.Semaphore] = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        """懒创建并发限流器（在首次异步调用时绑定当前事件循环）。"""
        if self._concurrency is None:
            self._concurrency = asyncio.Semaphore(self._max_concurrent)
        return self._concurrency

    def _thinking_extra_body(self) -> Dict[str, Any]:
        """Request body extension: explicitly toggle DeepSeek V4 thinking mode."""
        return {"thinking": {"type": "enabled" if self.thinking else "disabled"}}

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> str:
        """Send a chat completion and return the response text.

        Phase 16.6: 加入并发限流与按调用超时覆盖。
        """
        full_messages = self._build_messages(messages, system_prompt)
        call_timeout = timeout if timeout is not None else self._timeout

        async with self._get_semaphore():
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,  # type: ignore
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                    timeout=call_timeout,
                    extra_body=self._thinking_extra_body(),
                    **kwargs,
                )
                content = response.choices[0].message.content
                return content or ""

            except Exception as e:
                logger.error(f"DeepSeek chat error: {e}")
                raise

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Send a streaming chat completion, yielding text chunks.

        Phase 16.6: 加入并发限流与按调用超时覆盖。
        """
        full_messages = self._build_messages(messages, system_prompt)
        call_timeout = timeout if timeout is not None else self._timeout

        async with self._get_semaphore():
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,  # type: ignore
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                    stream=True,
                    timeout=call_timeout,
                    extra_body=self._thinking_extra_body(),
                    **kwargs,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

            except Exception as e:
                logger.error(f"DeepSeek stream error: {e}")
                raise

    async def chat_structured(
        self,
        messages: List[Dict[str, str]],
        output_schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a chat request and return structured JSON output.

        Uses tool-calling with a single 'output' function whose parameters
        are defined by output_schema.

        Phase 16.6 stability enhancements:
        - 并发限流：Semaphore 防止高并发触发 429
        - 超时分层：默认 1.5x LLM_TIMEOUT（结构化生成更重）
        - JSON 修复回退：tool_call 参数或 content 解析失败时，走
          parse_structured_output 全流程（markdown 剥离、尾逗号清理、
          单引号转双引号），大幅降低 JSONDecodeError 抛出率
        - thinking/tool_choice 冲突：thinking 模式下强制 tool_choice 会被
          DeepSeek 拒绝，自动改用 "auto" 并依赖 content+repair 兜底
        """
        full_messages = self._build_messages(messages, system_prompt)

        # Append tool-calling instruction to the existing system message
        # (work on a copy to avoid mutating caller's data)
        full_messages = [dict(m) for m in full_messages]
        tool_instruction = (
            "You MUST call the 'output' function with your structured result. "
            "Do not respond in plain text — always use the function."
        )
        for m in full_messages:
            if m["role"] == "system":
                m["content"] = f"{m['content']}\n\n{tool_instruction}"
                break
        else:
            full_messages.insert(0, {"role": "system", "content": tool_instruction})

        tools = [{
            "type": "function",
            "function": {
                "name": "output",
                "description": "Return the structured result.",
                "parameters": output_schema,
            },
        }]

        # Phase 16.6: thinking 模式拒绝强制 tool_choice，改用 auto + content 兜底
        if self.thinking:
            tool_choice: Any = "auto"
        else:
            tool_choice = {"type": "function", "function": {"name": "output"}}

        call_timeout = timeout if timeout is not None else self._structured_timeout

        async with self._get_semaphore():
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,  # type: ignore
                    temperature=temperature,
                    tools=tools,  # type: ignore
                    tool_choice=tool_choice,
                    timeout=call_timeout,
                    extra_body=self._thinking_extra_body(),
                    **kwargs,
                )

                # Phase 14e: Log token usage
                usage = getattr(response, "usage", None)
                if usage:
                    logger.info(
                        "LLM tokens — prompt=%d completion=%d total=%d",
                        usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                    )

                # 1. 优先走 tool_call 参数（最可靠的结构化路径）
                tool_calls = response.choices[0].message.tool_calls
                if tool_calls and tool_calls[0].function.arguments:
                    args_str = tool_calls[0].function.arguments
                    # Phase 16.6: 容错解析 tool_call 参数（偶发带 markdown/尾逗号）
                    result = parse_structured_output(args_str)
                    if result is not None:
                        return result
                    logger.warning(
                        "tool_call arguments JSON parse failed, trying content fallback"
                    )

                # 2. 回退：解析 content（带完整修复流程）
                content = response.choices[0].message.content
                if content:
                    result = parse_structured_output(content)
                    if result is not None:
                        logger.info(
                            "Structured output recovered via content + JSON repair"
                        )
                        return result

                raise ValueError("chat_structured failed to parse LLM output")

            except Exception as e:
                logger.error(f"DeepSeek structured output error: {e}")
                raise

    def _build_messages(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build the full message list with system prompt."""
        result: List[Dict[str, str]] = []

        # Add system prompt if not already present
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            result.append({
                "role": "system",
                "content": system_prompt or TRAVEL_SYSTEM_PROMPT,
            })

        result.extend(messages)
        return result


# ── Factory singleton with lock ───────────────────────────

_llm_provider: Optional[DeepSeekProvider] = None
_llm_lock: asyncio.Lock = asyncio.Lock()


async def get_llm_provider() -> DeepSeekProvider:
    """Get or create the singleton LLM provider instance (thread-safe)."""
    global _llm_provider
    if _llm_provider is not None:
        return _llm_provider
    async with _llm_lock:
        if _llm_provider is None:
            _llm_provider = DeepSeekProvider()
    return _llm_provider


def reset_llm_provider() -> None:
    """测试用：重置工厂单例。"""
    global _llm_provider
    _llm_provider = None

"""
TravelMind Agent — LLM Service
DeepSeek provider implementation using OpenAI-compatible SDK.
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from app.config.settings import settings
from app.core import BaseLLMProvider

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
        timeout = timeout or settings.LLM_TIMEOUT
        self.client = AsyncOpenAI(
            api_key=key,
            base_url=base_url or settings.DEEPSEEK_BASE_URL,
            timeout=timeout,
            max_retries=2,
            http_client=httpx.AsyncClient(trust_env=False, timeout=timeout),
        )

    def _thinking_extra_body(self) -> Dict[str, Any]:
        """Request body extension: explicitly toggle DeepSeek V4 thinking mode."""
        return {"thinking": {"type": "enabled" if self.thinking else "disabled"}}

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Send a chat completion and return the response text."""
        full_messages = self._build_messages(messages, system_prompt)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,  # type: ignore
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
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
        **kwargs,
    ) -> AsyncIterator[str]:
        """Send a streaming chat completion, yielding text chunks."""
        full_messages = self._build_messages(messages, system_prompt)

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,  # type: ignore
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                stream=True,
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
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a chat request and return structured JSON output.

        Uses tool-calling with a single 'output' function whose parameters
        are defined by output_schema. The model is forced to call this function.
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

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,  # type: ignore
                temperature=temperature,
                tools=tools,  # type: ignore
                tool_choice={"type": "function", "function": {"name": "output"}},
                extra_body=self._thinking_extra_body(),
                **kwargs,
            )

            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and tool_calls[0].function.arguments:
                return json.loads(tool_calls[0].function.arguments)

            # Fallback: try to parse content as JSON
            content = response.choices[0].message.content
            if content:
                return json.loads(content)

            return {}

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse structured output: {e}")
            return {}
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

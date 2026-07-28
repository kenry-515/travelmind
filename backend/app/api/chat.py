"""
TravelMind Agent — Chat API
POST /api/v1/chat  — send messages, get AI response (streaming or non-streaming).
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.api.errors import error_response
from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_ROLES = {"user", "assistant", "system"}

# ── Request / Response Models ─────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' | 'assistant' | 'system'")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, max_length=50)
    session_id: Optional[str] = Field(None, max_length=128)
    stream: bool = Field(False)

    @model_validator(mode="after")
    def validate_roles(self):
        for i, m in enumerate(self.messages):
            if m.role not in ALLOWED_ROLES:
                raise ValueError(
                    f"messages[{i}].role must be one of {ALLOWED_ROLES}, got '{m.role}'"
                )
        return self


class ChatResponse(BaseModel):
    content: str
    session_id: str
    model: str


# ── Session ───────────────────────────────────────────

def _generate_session_id() -> str:
    return f"s_{uuid.uuid4().hex[:16]}"


# ── SSE Helpers ───────────────────────────────────────

def _sse_encode(text: str) -> str:
    """Encode text as SSE data lines per the SSE specification.

    Each line of the message is prefixed with 'data: ' so that multi-line
    LLM output is transmitted correctly without premature event termination.
    """
    lines = text.split("\n")
    return "".join(f"data: {line}\n" for line in lines) + "\n"


# ── Routes ────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send messages to the LLM and get a response.

    Non-streaming: returns full response at once.
    Streaming: returns text/event-stream (SSE) for real-time display.
    """
    session_id = request.session_id or _generate_session_id()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    llm = await get_llm_provider()

    logger.info(
        "Chat — session=%s messages=%d stream=%s model=%s",
        session_id, len(messages), request.stream, llm.model,
    )

    # ── Streaming path ───────────────────────────────
    if request.stream:
        async def event_stream():
            try:
                async for chunk in llm.chat_stream(messages):
                    yield _sse_encode(chunk).encode("utf-8")
                yield b"data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield _sse_encode("[ERROR] 服务暂不可用，请稍后重试").encode("utf-8")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Session-Id": session_id,
            },
        )

    # ── Non-streaming path ───────────────────────────
    try:
        content = await llm.chat(messages)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise error_response(
            status_code=502,
            code="UPSTREAM_ERROR",
            message="LLM service error. Please try again later.",
        )

    return ChatResponse(
        content=content,
        session_id=session_id,
        model=llm.model,
    )

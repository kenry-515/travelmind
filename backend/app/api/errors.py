"""
TravelMind Agent — 统一错误响应格式（Phase 12.28c）

所有 API 模块的错误响应使用统一结构：
  {"error": {"code": "...", "message": "...", "details": ...}}

用法：
    from app.api.errors import error_response
    raise error_response(400, "INVALID_INPUT", "city 不能为空", {"field": "city"})

    # 在 FastAPI exception handler 中统一捕获：
    from app.api.errors import APIError, api_error_handler
    app.add_exception_handler(APIError, api_error_handler)
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class APIError(HTTPException):
    """Unified API error with machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = code
        self.error_message = message
        self.error_details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[Any] = None,
) -> "APIError":
    """Create a unified error response.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        code: Machine-readable error code (e.g. "INVALID_INPUT", "RATE_LIMITED")
        message: Human-readable error message
        details: Optional extra details (field name, constraints, etc.)

    Returns:
        APIError that FastAPI renders as:
        {"error": {"code": "...", "message": "...", "details": ...}}
    """
    return APIError(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    )


async def api_error_handler(request: Any, exc: APIError) -> JSONResponse:
    """FastAPI exception handler for APIError."""
    body: Dict[str, Any] = {
        "error": {
            "code": exc.error_code,
            "message": exc.error_message,
        }
    }
    if exc.error_details is not None:
        body["error"]["details"] = exc.error_details
    return JSONResponse(status_code=exc.status_code, content=body)


# ── Common error codes ────────────────────────────────────


class ErrorCode:
    """Standardized error codes for the application."""
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    VALIDATION_FAILED = "VALIDATION_FAILED"

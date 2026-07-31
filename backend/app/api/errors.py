"""
TravelMind Agent — 统一错误响应格式（Phase 12.28c）

所有 API 模块的错误响应使用统一结构：
  {
    "error": {
      "code": "...",
      "message": "...",        # 用户可读的中文消息
      "suggestion": "...",     # 可执行的下一步建议（可选）
      "details": ...,          # 机器可读细节
      "retryable": bool        # 前端可据此显示重试按钮
    }
  }

用法：
    from app.api.errors import error_response
    raise error_response(400, "INVALID_INPUT", "city 不能为空",
                         suggestion="请填写城市后再试",
                         details={"field": "city"})

    # 在 FastAPI exception handler 中统一捕获：
    from app.api.errors import APIError, api_error_handler
    app.add_exception_handler(APIError, api_error_handler)

Phase 18 M5: 新增 suggestion + retryable 字段,改善前端错误体验。
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class APIError(HTTPException):
    """Unified API error with machine-readable code.

    Phase 18: 新增 error_suggestion / error_retryable 字段,
    让前端能展示「可执行的下一步建议」+「重试按钮」。
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
        suggestion: Optional[str] = None,
        retryable: bool = False,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = code
        self.error_message = message
        self.error_details = details
        self.error_suggestion = suggestion
        self.error_retryable = retryable


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[Any] = None,
    suggestion: Optional[str] = None,
    retryable: bool = False,
) -> "APIError":
    """Create a unified error response.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        code: Machine-readable error code (e.g. "INVALID_INPUT", "RATE_LIMITED")
        message: Human-readable Chinese error message
        details: Optional extra details (field name, constraints, etc.)
        suggestion: Optional actionable next-step for the user
        retryable: Whether the user can retry the request

    Returns:
        APIError that FastAPI renders as:
        {"error": {"code": "...", "message": "...", "suggestion": "...", "retryable": bool, "details": ...}}
    """
    return APIError(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        suggestion=suggestion,
        retryable=retryable,
    )


async def api_error_handler(request: Any, exc: APIError) -> JSONResponse:
    """FastAPI exception handler for APIError.

    响应结构：
    {
      "error": {
        "code": str,
        "message": str,
        "suggestion": str | None,
        "retryable": bool,
        "details": Any | None
      }
    }
    """
    body: Dict[str, Any] = {
        "error": {
            "code": exc.error_code,
            "message": exc.error_message,
            "suggestion": exc.error_suggestion,
            "retryable": exc.error_retryable,
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
    LLM_TIMEOUT = "LLM_TIMEOUT"
    CITY_NOT_SUPPORTED = "CITY_NOT_SUPPORTED"


# ── 常用错误预设（前端可直接根据 code 复用建议文本） ────


class ErrorPresets:
    """Predefined user-facing error messages with actionable suggestions.

    用法：
        raise error_response(
            400, **ErrorPresets.rate_limited(retry_after=30)
        )
    """
    _MESSAGES = {
        "rate_limited": {
            "message": "请求过于频繁,请稍后再试",
            "suggestion": "请等待 {retry_after} 秒后重试,避免连续点击",
            "retryable": True,
        },
        "service_unavailable": {
            "message": "服务暂不可用",
            "suggestion": "可能是后端启动中或维护中,请刷新页面或稍后重试",
            "retryable": True,
        },
        "llm_timeout": {
            "message": "AI 生成超时,请重试",
            "suggestion": "复杂行程生成需要 30-60 秒。如多次失败,可缩短行程天数或减少偏好标签",
            "retryable": True,
        },
        "city_not_supported": {
            "message": "暂不支持该城市",
            "suggestion": "当前智能体专注于广州旅游规划。请选择广州或周边的景点",
            "retryable": False,
        },
        "internal_error": {
            "message": "服务内部错误",
            "suggestion": "已记录错误日志,请稍后重试。如反复出现请联系管理员",
            "retryable": True,
        },
        "auth_required": {
            "message": "需要设备标识",
            "suggestion": "请刷新页面让系统自动生成设备标识",
            "retryable": False,
        },
    }

    @classmethod
    def get(cls, key: str, **format_args) -> Dict[str, Any]:
        """获取预设错误响应字段(message/suggestion/retryable)。"""
        preset = cls._MESSAGES.get(key, {})
        msg = preset.get("message", "未知错误")
        sug = preset.get("suggestion", "")
        if format_args and sug:
            try:
                sug = sug.format(**format_args)
            except (KeyError, IndexError):
                pass
        return {
            "message": msg,
            "suggestion": sug,
            "retryable": preset.get("retryable", False),
        }

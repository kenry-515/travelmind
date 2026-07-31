"""
错误响应结构测试(Phase 18 M5.1)。

验证 suggestion / retryable 字段、ErrorPresets、向后兼容。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from app.api.errors import (
    APIError,
    ErrorCode,
    ErrorPresets,
    api_error_handler,
    error_response,
)


# ── 向后兼容:旧调用方式仍工作 ───────────────────


def test_error_response_basic_compat():
    """旧调用方式(status, code, message, details)仍合法。"""
    err = error_response(400, "INVALID_INPUT", "city 不能为空", {"field": "city"})
    assert err.status_code == 400
    assert err.error_code == "INVALID_INPUT"
    assert err.error_message == "city 不能为空"
    assert err.error_details == {"field": "city"}
    # 新字段默认 None / False
    assert err.error_suggestion is None
    assert err.error_retryable is False


def test_error_response_minimal():
    """最小调用方式(只 3 个参数)仍合法。"""
    err = error_response(404, "NOT_FOUND", "未找到")
    assert err.error_details is None
    assert err.error_suggestion is None
    assert err.error_retryable is False


# ── 新功能:suggestion + retryable ──────────────────


def test_error_response_with_suggestion():
    """带 suggestion 的错误响应。"""
    err = error_response(
        400,
        "INVALID_INPUT",
        "天数必须是 1-14 的整数",
        suggestion="请填写有效天数(1-14 天)",
        retryable=False,
    )
    assert err.error_suggestion == "请填写有效天数(1-14 天)"
    assert err.error_retryable is False


def test_error_response_retryable_true():
    """可重试错误标记。"""
    err = error_response(
        503,
        "SERVICE_UNAVAILABLE",
        "服务暂不可用",
        suggestion="请稍后重试",
        retryable=True,
    )
    assert err.error_retryable is True


# ── ErrorPresets 预设 ──────────────────────────────


def test_presets_rate_limited():
    p = ErrorPresets.get("rate_limited", retry_after=30)
    assert p["retryable"] is True
    assert "30" in p["suggestion"]
    assert "请求过于频繁" in p["message"]


def test_presets_llm_timeout():
    p = ErrorPresets.get("llm_timeout")
    assert p["retryable"] is True
    assert "超时" in p["message"]
    assert "30-60 秒" in p["suggestion"]


def test_presets_city_not_supported():
    p = ErrorPresets.get("city_not_supported")
    assert p["retryable"] is False
    assert "广州" in p["suggestion"]


def test_presets_unknown_key_fallback():
    """未知 key 返回安全默认。"""
    p = ErrorPresets.get("nonexistent_key")
    assert p["message"] == "未知错误"
    assert p["retryable"] is False


def test_presets_format_args_missing():
    """format_args 缺失时优雅降级(不抛 KeyError)。"""
    p = ErrorPresets.get("rate_limited")  # 没传 retry_after
    # 应不抛,返回原文 suggestion
    assert "{" not in p["suggestion"] or p["suggestion"]  # 不应保留占位符


# ── HTTP handler 集成 ──────────────────────────────


@pytest.fixture
def error_app():
    """带错误路由的 FastAPI 测试 app。"""
    app = FastAPI()
    app.add_exception_handler(APIError, api_error_handler)

    @app.get("/test/error/basic")
    async def basic_error():
        raise error_response(400, "INVALID_INPUT", "city 不能为空")

    @app.get("/test/error/with_suggestion")
    async def with_suggestion():
        raise error_response(
            503,
            "SERVICE_UNAVAILABLE",
            "服务暂不可用",
            suggestion="请刷新页面",
            retryable=True,
        )

    @app.get("/test/error/preset")
    async def preset_error():
        p = ErrorPresets.get("llm_timeout")
        raise error_response(504, "LLM_TIMEOUT", p["message"],
                             suggestion=p["suggestion"], retryable=p["retryable"])

    return app


@pytest.mark.asyncio
async def test_error_handler_basic_compat(error_app):
    """旧调用在 handler 中仍正确渲染(无 suggestion/retryable 字段为 null/false)。"""
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/test/error/basic")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "INVALID_INPUT"
        assert body["error"]["message"] == "city 不能为空"
        # 新字段存在但为 None/False(向后兼容)
        assert body["error"]["suggestion"] is None
        assert body["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_error_handler_with_suggestion(error_app):
    """新调用渲染完整错误结构。"""
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/test/error/with_suggestion")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["suggestion"] == "请刷新页面"
        assert body["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_error_handler_preset(error_app):
    """ErrorPresets 预设错误响应。"""
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/test/error/preset")
        assert resp.status_code == 504
        body = resp.json()
        assert "超时" in body["error"]["message"]
        assert body["error"]["retryable"] is True
        assert "30-60 秒" in body["error"]["suggestion"]


# ── ErrorCode 新增 code ──────────────────────────


def test_error_code_new_codes():
    """Phase 18 新增的 error code 应可用。"""
    assert ErrorCode.LLM_TIMEOUT == "LLM_TIMEOUT"
    assert ErrorCode.CITY_NOT_SUPPORTED == "CITY_NOT_SUPPORTED"
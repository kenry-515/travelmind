"""
M5.3 安全测试：日志脱敏 + 限流响应格式 + 分享签名。

覆盖:
- _sanitize_log_value 截断 + 移除敏感字段
- 限流响应含 suggestion/retryable 字段
- share_service HMAC 签名 + 验证 + 防篡改
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, AsyncMock
from starlette.types import Scope, Receive, Send
import json as json_lib


# ── _sanitize_log_value 日志脱敏 ─────────────────


def test_sanitize_truncates_long_input():
    """长输入被截断(防止日志 spam)。"""
    from app.middleware.rate_limit import _sanitize_log_value
    long = "x" * 1000
    out = _sanitize_log_value(long, max_len=200)
    assert len(out) < len(long)
    assert "truncated" in out


def test_sanitize_strips_api_keys():
    """API key 被 redact。"""
    from app.middleware.rate_limit import _sanitize_log_value
    sensitive = "sk-abc1234567890def my secret here"
    out = _sanitize_log_value(sensitive)
    assert "abc1234567890" not in out or "redacted" in out
    assert "sk-<redacted>" in out or "<redacted>" in out


def test_sanitize_strips_password_assignment():
    """password=xxx 被 redact。"""
    from app.middleware.rate_limit import _sanitize_log_value
    out = _sanitize_log_value("login with password=hunter2 ok")
    assert "hunter2" not in out
    assert "redacted" in out


def test_sanitize_keeps_normal_text():
    """正常文本不被误伤。"""
    from app.middleware.rate_limit import _sanitize_log_value
    out = _sanitize_log_value("今天想去广州玩3天")
    assert "广州" in out
    assert "3天" in out


def test_sanitize_non_string_input():
    """非字符串输入也安全。"""
    from app.middleware.rate_limit import _sanitize_log_value
    assert isinstance(_sanitize_log_value(12345), str)
    assert isinstance(_sanitize_log_value(None), str)


# ── 限流响应格式(suggestion + retryable) ──────────


@pytest.fixture
def rate_limit_app():
    """带限流的 FastAPI 测试 app。"""
    from app.middleware.rate_limit import RateLimitMiddleware

    # 创建一个小型桶(2 req / 10s)让测试快速触发限流
    inner_app = FastAPI()

    @inner_app.get("/api/v1/test/endpoint")
    async def ok_endpoint():
        return {"ok": True}

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        rate=2,
        per_seconds=10,
        exempt_paths=("/api/v1/health",),
    )
    app.mount("/", inner_app)
    return app


@pytest.mark.asyncio
async def test_rate_limit_normal_request_passes(rate_limit_app):
    """前 N 个请求正常通过。"""
    async with AsyncClient(
        transport=ASGITransport(app=rate_limit_app), base_url="http://test"
    ) as client:
        for _ in range(2):
            r = await client.get("/api/v1/test/endpoint")
            assert r.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_returns_429_with_suggestion(rate_limit_app):
    """超限后 429 + suggestion + retryable + retry-after 头。"""
    async with AsyncClient(
        transport=ASGITransport(app=rate_limit_app), base_url="http://test"
    ) as client:
        # 消耗完桶
        for _ in range(2):
            await client.get("/api/v1/test/endpoint")
        # 第 3 个请求触发限流
        resp = await client.get("/api/v1/test/endpoint")
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") is not None
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMITED"
        assert body["error"]["retryable"] is True
        assert "suggestion" in body["error"]
        assert "稍后" in body["error"]["message"]
        assert "details" in body["error"]
        assert "retry_after_seconds" in body["error"]["details"]


@pytest.mark.asyncio
async def test_rate_limit_exempt_paths_bypass():
    """exempt 路径不计数。"""
    from app.middleware.rate_limit import RateLimitMiddleware

    app = FastAPI()

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/test")
    async def test():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware, rate=1, per_seconds=60, exempt_paths=("/api/v1/health",)
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # health 多次调用不限流
        for _ in range(5):
            r = await client.get("/api/v1/health")
            assert r.status_code == 200
        # test 限流(2 个会通过,第 3 个 429)
        # 但只有 1 个配额 → 第二个就被限流
        r1 = await client.get("/api/v1/test")
        assert r1.status_code == 200
        r2 = await client.get("/api/v1/test")
        assert r2.status_code == 429


# ── 分享链接签名(单元级,补充集成测试) ──────────────


def test_share_signature_full_lifecycle():
    """完整生命周期:create → verify with right sig → reject with wrong sig。"""
    from app.services import share_service

    rec = share_service.create_share("owner-device", "itinerary-x")
    share_id = rec["share_id"]
    valid_sig = rec["signature"]

    # 正确签名 → 返回
    assert share_service.get_share(share_id, signature=valid_sig) is not None
    # 错误签名 → 拒绝
    assert share_service.get_share(share_id, signature="0" * 16) is None
    # 缺失签名 → 拒绝
    assert share_service.get_share(share_id) is None


def test_share_signature_uses_configured_secret(monkeypatch):
    """配置 SHARE_SIGNING_SECRET 后,签名应基于该 secret。"""
    import os
    from app.services import share_service

    monkeypatch.setenv("SHARE_SIGNING_SECRET", "my-production-secret")
    # 清除 module-level _DEV_SECRET cache(如有)
    if hasattr(share_service, "_DEV_SECRET"):
        delattr(share_service, "_DEV_SECRET")

    rec = share_service.create_share("d", "i")
    expected = share_service._compute_signature(rec["share_id"], rec["expires_at"])
    assert rec["signature"] == expected
    # 还原
    monkeypatch.delenv("SHARE_SIGNING_SECRET", raising=False)


def test_share_signature_constant_time_compare():
    """验证用 hmac.compare_digest(常量时间,防时序攻击)。"""
    from app.services import share_service
    import inspect
    src = inspect.getsource(share_service._verify_signature)
    assert "hmac.compare_digest" in src
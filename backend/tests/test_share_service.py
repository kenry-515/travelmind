"""
Tests for share_service module.

Phase 18 M5.3: 验证 HMAC 签名机制 + 向后兼容。
"""

import pytest
from app.services import share_service


@pytest.fixture(autouse=True)
def cleanup_shares():
    """Cleanup shares before and after each test."""
    import shutil
    from pathlib import Path
    share_root = Path(share_service._SHARE_ROOT)
    if share_root.exists():
        shutil.rmtree(share_root)
    yield
    if share_root.exists():
        shutil.rmtree(share_root)


# ── Phase 18 M5.3: 新签名 API ─────────────────────


def test_create_share_returns_signature_dict():
    """create_share 返回 dict 含 share_id + signature + expires_at。"""
    rec = share_service.create_share("test-device-123", "test-itinerary-456")
    assert isinstance(rec, dict)
    assert "share_id" in rec
    assert "signature" in rec
    assert "expires_at" in rec
    assert len(rec["signature"]) == 16  # 16 hex chars
    assert rec["signature"] != ""


def test_create_and_get_with_valid_signature():
    """create_share 后,用正确签名 get_share 应返回 record。"""
    rec = share_service.create_share("test-device-123", "test-itinerary-456",
                                     expires_days=30)
    share_id = rec["share_id"]
    sig = rec["signature"]

    record = share_service.get_share(share_id, signature=sig)
    assert record is not None
    assert record["share_id"] == share_id
    assert record["device_id"] == "test-device-123"
    assert record["itinerary_id"] == "test-itinerary-456"
    assert record["days_valid"] == 30
    # 签名也被持久化到 record
    assert record.get("signature") == sig


def test_get_with_wrong_signature_returns_none():
    """错误签名 → None(如同不存在)。"""
    rec = share_service.create_share("d", "i")
    record = share_service.get_share(rec["share_id"], signature="deadbeef" * 4)
    assert record is None


def test_get_with_missing_signature_returns_none():
    """没传签名参数 → None(安全默认值,所有记录都带签名)。"""
    rec = share_service.create_share("d", "i")
    record = share_service.get_share(rec["share_id"])  # 无 signature 参数
    # 新逻辑:任何 record 都有 signature,不传 → 验证失败
    assert record is None


def test_signature_is_deterministic_with_secret():
    """同 secret + 同输入 → 同签名。"""
    rec = share_service.create_share("d", "i")
    share_id = rec["share_id"]
    expires_at = rec["expires_at"]
    expected = share_service._compute_signature(share_id, expires_at)
    assert rec["signature"] == expected
    # 用 verify 验证
    assert share_service._verify_signature(share_id, expires_at, expected)


def test_signature_changes_with_id():
    """不同 share_id → 不同签名(没有碰撞)。"""
    rec1 = share_service.create_share("d", "i1")
    rec2 = share_service.create_share("d", "i2")
    assert rec1["signature"] != rec2["signature"]


def test_signature_verification_rejects_tampering():
    """篡改 share_id / expires_at → 验证失败。"""
    rec = share_service.create_share("d", "i")
    real_id = rec["share_id"]
    fake_id = "00000000-0000-0000-0000-000000000000"
    sig = rec["signature"]

    # 真签名 + 假 share_id → 失败
    assert share_service.get_share(fake_id, signature=sig) is None


def test_get_nonexistent_share():
    """不存在的 share + 任意签名 → None。"""
    result = share_service.get_share("non-existent-id", signature="x" * 16)
    assert result is None


# ── 基础 CRUD(向后兼容) ──────────────────────────────


def test_delete_share():
    """删除 share。"""
    rec = share_service.create_share("test-device-123", "test-itinerary-456")
    share_id = rec["share_id"]
    assert share_service.get_share(share_id, signature=rec["signature"]) is not None

    deleted = share_service.delete_share(share_id)
    assert deleted is True
    assert share_service.get_share(share_id, signature=rec["signature"]) is None


def test_delete_nonexistent_share():
    """删除不存在的 share → False。"""
    deleted = share_service.delete_share("non-existent-id")
    assert deleted is False


def test_list_shares():
    """按 device 列出 shares。"""
    share_service.create_share("test-device-123", "itinerary-1")
    share_service.create_share("test-device-123", "itinerary-2")
    share_service.create_share("other-device", "itinerary-3")

    shares = share_service.list_shares("test-device-123")
    assert len(shares) == 2


def test_different_expiry_days():
    """不同 expires_days。"""
    rec_7 = share_service.create_share("device", "itin-1", expires_days=7)
    rec_90 = share_service.create_share("device", "itin-2", expires_days=90)

    r7 = share_service.get_share(rec_7["share_id"], signature=rec_7["signature"])
    r90 = share_service.get_share(rec_90["share_id"], signature=rec_90["signature"])

    assert r7["days_valid"] == 7
    assert r90["days_valid"] == 90
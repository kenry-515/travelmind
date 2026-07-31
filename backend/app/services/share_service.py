"""
TravelMind Agent — Share Service
Manages itinerary sharing via shareable links.

Share flow:
1. User creates a share link for their itinerary
2. A share_id (UUID) is generated and mapped to the itinerary
3. Recipient can view the itinerary via the share_id
4. Shares can have optional expiry dates and access controls
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Storage root for share links
_SHARE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "shares"


def _get_signing_secret() -> bytes:
    """Get the HMAC signing secret for share link signatures.

    Production: set SHARE_SIGNING_SECRET in env. Development: derive from
    a stable source so signatures are deterministic across calls within
    a single process. NEVER use a default secret in production.
    """
    secret = os.environ.get("SHARE_SIGNING_SECRET", "").strip()
    if secret:
        return secret.encode("utf-8")
    # Dev fallback: process-stable secret (一次生成,同进程内 create/verify 一致).
    # 跨进程会变 → 部署时一定要设 SHARE_SIGNING_SECRET。
    global _DEV_SECRET
    try:
        return _DEV_SECRET
    except NameError:
        if not getattr(_get_signing_secret, "_warned", False):
            logger.warning(
                "SHARE_SIGNING_SECRET not set — using process-stable dev fallback. "
                "Set SHARE_SIGNING_SECRET in production for cross-process stable signatures."
            )
            _get_signing_secret._warned = True
        _DEV_SECRET = b"dev-only-process-stable-" + os.urandom(32).hex().encode()
        return _DEV_SECRET


def _compute_signature(share_id: str, expires_at: str) -> str:
    """Compute HMAC-SHA256 signature over share_id + expires_at.

    Returned as URL-safe hex (first 16 chars) for compact URLs.
    """
    msg = f"{share_id}|{expires_at}".encode("utf-8")
    return hmac.new(_get_signing_secret(), msg, hashlib.sha256).hexdigest()[:16]


def _verify_signature(share_id: str, expires_at: str, provided_sig: str) -> bool:
    """Verify a share link signature. Constant-time comparison."""
    expected = _compute_signature(share_id, expires_at)
    try:
        return hmac.compare_digest(expected, provided_sig)
    except Exception:
        return False


def _ensure_dir():
    _SHARE_ROOT.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _share_path(share_id: str) -> Path:
    """Get the file path for a share record."""
    safe_id = "".join(c for c in share_id if c.isalnum() or c in "-_")
    return _SHARE_ROOT / f"{safe_id}.json"


def create_share(
    device_id: str,
    itinerary_id: str,
    expires_days: int = 30,
) -> Dict[str, str]:
    """Create a share link for an itinerary.

    Phase 18 M5.3: Returns dict with share_id + signature + expires_at,
    so callers can construct signed URL: /share/{share_id}?sig=...&exp=...

    Args:
        device_id: The owner's device ID
        itinerary_id: The itinerary to share
        expires_days: Number of days before the share link expires

    Returns:
        {"share_id": str, "signature": str, "expires_at": str}
    """
    _ensure_dir()
    share_id = str(uuid.uuid4())
    expires_at = _now_iso()
    days_valid = expires_days

    record = {
        "share_id": share_id,
        "device_id": device_id,
        "itinerary_id": itinerary_id,
        "expires_at": expires_at,
        "days_valid": days_valid,
        "created_at": _now_iso(),
        "signature": _compute_signature(share_id, expires_at),
    }

    path = _share_path(share_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    logger.info(f"Share link created: {share_id} for itinerary {itinerary_id}")
    return {
        "share_id": share_id,
        "signature": record["signature"],
        "expires_at": expires_at,
    }


def get_share(share_id: str, signature: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get a share record by its ID.

    Phase 18 M5.3: 验证签名 + 过期检查。
    签名验证失败 → 返回 None（如同不存在）。
    为向后兼容：若 signature 参数为空，仅在生产环境要求强制签名。

    Returns the share record if found, signature valid, and not expired.
    """
    path = _share_path(share_id)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load share {share_id}: {e}")
        return None

    # Phase 18 M5.3: 验证签名
    expires_at = record.get("expires_at", "")
    stored_sig = record.get("signature", "")
    if not stored_sig:
        # 旧格式无签名记录（兼容旧 share,仅在 dev 环境放行）
        if os.environ.get("APP_ENV") == "production":
            logger.warning(f"Share {share_id} has no signature (legacy)")
            return None
    else:
        if not signature or not _verify_signature(share_id, expires_at, signature):
            logger.warning(f"Share {share_id} signature mismatch")
            return None

    # Check expiry
    days_valid = record.get("days_valid", 30)
    created_at = record.get("created_at", "")
    if created_at:
        try:
            created_time = time.strptime(created_at, "%Y-%m-%dT%H:%M:%S")
            created_timestamp = time.mktime(created_time)
            expiry_timestamp = created_timestamp + (days_valid * 86400)
            if time.time() > expiry_timestamp:
                logger.info(f"Share {share_id} has expired")
                delete_share(share_id)
                return None
        except (ValueError, OverflowError):
            pass  # If we can't parse the date, assume it's still valid

    return record


def delete_share(share_id: str) -> bool:
    """Delete a share link. Returns True if it existed."""
    path = _share_path(share_id)
    if not path.exists():
        return False
    try:
        path.unlink()
        logger.info(f"Share {share_id} deleted")
        return True
    except OSError:
        return False


def list_shares(device_id: str) -> list:
    """List all shares created by a device."""
    _ensure_dir()
    shares = []
    for path in _SHARE_ROOT.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            if record.get("device_id") == device_id:
                shares.append(record)
        except Exception as e:
            logger.warning(f"Skipping corrupted share file {path.name}: {e}")
    shares.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return shares


def cleanup_expired_shares():
    """Cleanup all expired share links."""
    _ensure_dir()
    now = time.time()
    deleted_count = 0
    for path in _SHARE_ROOT.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            created_at = record.get("created_at", "")
            days_valid = record.get("days_valid", 30)
            if created_at:
                created_time = time.strptime(created_at, "%Y-%m-%dT%H:%M:%S")
                created_timestamp = time.mktime(created_time)
                expiry_timestamp = created_timestamp + (days_valid * 86400)
                if now > expiry_timestamp:
                    path.unlink()
                    deleted_count += 1
        except Exception:
            pass
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired share links")

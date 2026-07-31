"""
TravelMind Agent — Share Service
Manages itinerary sharing via shareable links.

Share flow:
1. User creates a share link for their itinerary
2. A share_id (UUID) is generated and mapped to the itinerary
3. Recipient can view the itinerary via the share_id
4. Shares can have optional expiry dates and access controls
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Storage root for share links
_SHARE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "shares"


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
) -> str:
    """Create a share link for an itinerary.
    
    Args:
        device_id: The owner's device ID
        itinerary_id: The itinerary to share
        expires_days: Number of days before the share link expires
        
    Returns:
        A share_id string (UUID)
    """
    _ensure_dir()
    share_id = str(uuid.uuid4())
    
    record = {
        "share_id": share_id,
        "device_id": device_id,
        "itinerary_id": itinerary_id,
        "expires_at": _now_iso(),  # Simple timestamp, actual expiry checked by days
        "days_valid": expires_days,
        "created_at": _now_iso(),
    }
    
    path = _share_path(share_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Share link created: {share_id} for itinerary {itinerary_id}")
    return share_id


def get_share(share_id: str) -> Optional[Dict[str, Any]]:
    """Get a share record by its ID.
    
    Returns the share record if found and not expired, or None otherwise.
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

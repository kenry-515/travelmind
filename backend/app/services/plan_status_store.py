"""
TravelMind Agent — Plan Status Store
In-memory store for tracking streaming plan generation status.
Used by the frontend polling fallback when SSE connections drop.
"""

import asyncio
import time
from typing import Any, Dict, Optional

# Simple in-memory store with lock for thread safety
_status_store: Dict[str, Dict[str, Any]] = {}
_lock = asyncio.Lock()
_expiry_time = 600  # 10 minutes


async def set_status(task_id: str, status: str, data: Optional[Dict[str, Any]] = None):
    """Set the status of a plan generation task."""
    async with _lock:
        _status_store[task_id] = {
            "status": status,  # "generating", "completed", "error"
            "data": data,
            "updated_at": time.time(),
        }


async def get_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a plan generation task."""
    async with _lock:
        item = _status_store.get(task_id)
        if not item:
            return None
        # Check expiry
        if time.time() - item["updated_at"] > _expiry_time:
            _status_store.pop(task_id, None)
            return None
        return item


async def delete_status(task_id: str):
    """Delete a plan generation task status."""
    async with _lock:
        _status_store.pop(task_id, None)


def cleanup_expired():
    """Cleanup expired entries (can be called periodically)."""
    now = time.time()
    keys_to_delete = [k for k, v in _status_store.items() if now - v.get("updated_at", 0) > _expiry_time]
    for k in keys_to_delete:
        _status_store.pop(k, None)

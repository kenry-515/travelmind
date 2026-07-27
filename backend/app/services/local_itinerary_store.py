"""
TravelMind Agent — Local Itinerary Store（PostgreSQL 不可用时的文件型回退）

当 DATABASE_URL 指向的 PG 不可达（本地开发常见），行程保存/历史读取
静默失败——用户看到"行程无法保存、我的行程为空"。本模块提供零依赖的
JSON 文件存储，目录结构：

  backend/data/user_itineraries/{device_id}/{itinerary_id}.json

与 itinerary_service 对齐的最小接口：save / list / get / delete。
单机部署下数据可持久、可备份（直接拷贝目录）。
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_STORE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "user_itineraries"


def _user_dir(device_id: str) -> Path:
    # device_id 只保留安全字符，避免路径穿越
    safe = "".join(c for c in device_id if c.isalnum() or c in "-_")[:64] or "anon"
    d = _STORE_ROOT / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def save_itinerary(
    device_id: str,
    itinerary: Dict[str, Any],
    validation_report: Optional[Dict[str, Any]] = None,
    profile_snapshot: Optional[Dict[str, Any]] = None,
    weather_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    """Persist one itinerary; returns the new itinerary id."""
    iid = uuid.uuid4().hex[:16]
    trip = itinerary.get("trip") or {}
    record = {
        "id": iid,
        "title": trip.get("title", ""),
        "city": trip.get("city", ""),
        "days": trip.get("daysCount", len(itinerary.get("days", []))),
        "plan": itinerary,
        "validation_report": validation_report,
        "profile_snapshot": profile_snapshot,
        "weather_snapshot": weather_snapshot,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "store": "local-file",
    }
    path = _user_dir(device_id) / f"{iid}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    logger.info(f"Local itinerary saved: {iid} ({trip.get('city', '')})")
    return iid


def _load_all(device_id: str) -> List[Dict[str, Any]]:
    d = _user_dir(device_id)
    records = []
    for path in d.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                records.append(json.load(f))
        except Exception as e:
            logger.warning(f"Skipping corrupted itinerary file {path.name}: {e}")
    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return records


def list_itineraries(
    device_id: str, page: int = 1, page_size: int = 20
) -> Tuple[List[Dict[str, Any]], int]:
    """Return (summaries, total), newest first."""
    records = _load_all(device_id)
    total = len(records)
    start = (page - 1) * page_size
    window = records[start: start + page_size]
    summaries = [
        {
            "id": r["id"],
            "title": r.get("title", ""),
            "city": r.get("city", ""),
            "days": r.get("days", 0),
            "created_at": r.get("created_at", ""),
        }
        for r in window
    ]
    return summaries, total


def get_itinerary(device_id: str, itinerary_id: str) -> Optional[Dict[str, Any]]:
    """Fetch one itinerary by id (owner-scoped by device dir)."""
    safe_id = "".join(c for c in itinerary_id if c.isalnum() or c in "-_")
    path = _user_dir(device_id) / f"{safe_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_itinerary(device_id: str, itinerary_id: str) -> bool:
    """Delete one itinerary; returns True if it existed."""
    safe_id = "".join(c for c in itinerary_id if c.isalnum() or c in "-_")
    path = _user_dir(device_id) / f"{safe_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True

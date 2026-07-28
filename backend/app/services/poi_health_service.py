"""
TravelMind Agent — POI Health Service

Lazy-loads the latest POI health report and provides inactive-POI
name lookups for the recommendation pipeline.

Usage:
    from app.services.poi_health_service import _load_inactive_poi_names
    inactive = _load_inactive_poi_names()
    if poi_name in inactive:
        ...  # exclude this POI

Module-level caching (same pattern as _load_closures):
    _reset_inactive_cache() clears the cache — used only in tests.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Simple normalize for POI health matching (strips punctuation only,
# intentionally does NOT strip city prefixes/suffixes — those are needed
# for exact inactive-name matching).
def _normalize_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"[（）()·\s]", "", name).replace("贰", "二")

# ── Module-level cache ─────────────────────────────────────

_inactive_names: Optional[Set[str]] = None
_loaded_report_path: Optional[Path] = None

# Path to the data directory
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"

# Regex to extract date from filename: poi_health_YYYY-MM-DD.json
_REPORT_DATE_RE = re.compile(r"poi_health_(\d{4}-\d{2}-\d{2})\.json")


# ── Public API ─────────────────────────────────────────────


def _find_latest_report() -> Optional[Path]:
    """Scan data/ for the most recent poi_health_*.json.

    Returns the Path of the most recent report, or None if none found.
    """
    if not _DATA_DIR.exists():
        return None

    reports: list[tuple[datetime, Path]] = []
    for f in _DATA_DIR.glob("poi_health_*.json"):
        m = _REPORT_DATE_RE.match(f.name)
        if m:
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d")
                reports.append((d, f))
            except ValueError:
                pass

    if not reports:
        return None

    # Return the newest report
    reports.sort(key=lambda x: x[0], reverse=True)
    return reports[0][1]


def _load_inactive_poi_names() -> Set[str]:
    """Lazy-load inactive POI names from the latest health report.

    Normalizes names for fuzzy matching. Returns an empty set if:
    - No health report exists
    - The report has no inactive_pois
    - The report file is malformed

    The result is cached at module level. Call _reset_inactive_cache()
    to force a reload (e.g. in tests).
    """
    global _inactive_names, _loaded_report_path

    if _inactive_names is not None:
        return _inactive_names

    report_path = _find_latest_report()
    if report_path is None:
        logger.debug("No POI health report found — all POIs treated as active")
        _inactive_names = set()
        return _inactive_names

    # Avoid re-loading the same file
    if _loaded_report_path == report_path:
        return _inactive_names if _inactive_names is not None else set()

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read health report {report_path}: {e}")
        _inactive_names = set()
        return _inactive_names

    inactive = set()
    for entry in report.get("inactive_pois", []):
        name = entry.get("name", "")
        if name:
            # Store normalized form for comparison
            inactive.add(_normalize_name(name))

    _inactive_names = inactive
    _loaded_report_path = report_path
    logger.info(
        f"Loaded {len(inactive)} inactive POI names from {report_path.name}"
    )
    return _inactive_names


def is_poi_inactive(name: str) -> bool:
    """Check if a given POI name is in the inactive set.

    Args:
        name: Raw POI name (will be normalized before comparison).

    Returns:
        True if the POI is known to be inactive.
    """
    inactive = _load_inactive_poi_names()
    return _normalize_name(name) in inactive


def _reset_inactive_cache() -> None:
    """Reset the module-level cache (for testing only)."""
    global _inactive_names, _loaded_report_path
    _inactive_names = None
    _loaded_report_path = None

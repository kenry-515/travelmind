"""
TravelMind Agent — Amap Maps Service

Routing, distance matrix, and POI search via Amap (高德地图) Web API.

Replaces the originally-planned Baidu Maps — Amap covers all the same
capabilities (walking, transit, driving, distance matrix) and we already
have the API key + digital signing configured.

Phase 12.11: When AMAP_API_KEY is empty, all calls return empty results
gracefully (no errors, no warnings). The system falls back to KB coordinates
for route calculation and name-based matching for POI verification.

Usage:
    from app.services.amap_service import get_distance_matrix, get_walking_route
"""

import asyncio
import threading
import hashlib
import json
import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── API Key availability ───────────────────────────────────

def is_amap_available() -> bool:
    """Check if the Amap API key is configured and non-empty."""
    key = getattr(settings, "AMAP_API_KEY", "")
    return bool(key and key.strip())


_AMAP_UNAVAILABLE_LOG = False  # log once per process


def _check_amap_available() -> bool:
    """Check Amap availability; log info once when unavailable."""
    global _AMAP_UNAVAILABLE_LOG
    if is_amap_available():
        return True
    if not _AMAP_UNAVAILABLE_LOG:
        _AMAP_UNAVAILABLE_LOG = True
        logger.info(
            "Amap API key is not configured — POI verification and route "
            "distance will use KB coordinates and name matching only."
        )
    return False

# ── API endpoints ────────────────────────────────────────

BASE_URL = "https://restapi.amap.com"
WALKING_URL = f"{BASE_URL}/v3/direction/walking"
TRANSIT_URL = f"{BASE_URL}/v3/direction/transit/integrated"
DISTANCE_URL = f"{BASE_URL}/v3/distance"
SEARCH_URL = f"{BASE_URL}/v3/place/text"

# ── Rate limiting ────────────────────────────────────────

# Amap free tier: 5000 calls/day, 30 QPS for personal dev
_client: Optional[httpx.AsyncClient] = None
_client_lock = threading.Lock()


def _get_client() -> httpx.AsyncClient:
    """Get or create a shared httpx AsyncClient."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(timeout=15.0, trust_env=False)
    return _client


# ── Signing ──────────────────────────────────────────────


def _sign_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Add digital signature to params if AMAP_SIGN_KEY is configured."""
    sign_key = getattr(settings, "AMAP_SIGN_KEY", "")
    if not sign_key:
        return params

    # Build sorted query string and append sign key
    sorted_items = sorted(
        (k, str(v)) for k, v in params.items() if k != "sig"
    )
    raw = "&".join(f"{k}={v}" for k, v in sorted_items) + sign_key
    sig = hashlib.md5(raw.encode("utf-8")).hexdigest()

    params["sig"] = sig
    return params


async def search_poi(
    keywords: str,
    city: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Search Amap POI by keywords within a city.

    Returns a list of {name, adname (行政区, e.g. 渝中区), address, typecode,
    lat, lon} — used for POI 存续校验、区域归属和地理坐标。
    Returns [] on any failure (treated as 'not found' by callers).

    Phase 12.11: Returns [] gracefully when Amap API key is not configured.
    """
    if not _check_amap_available():
        return []

    params = _sign_params({
        "key": settings.AMAP_API_KEY,
        "keywords": keywords,
        "city": city,
        "citylimit": "true",
        "offset": str(limit),
        "page": "1",
        "extensions": "all",
        "output": "JSON",
    })

    try:
        # 异常重试一次（Amap 偶发抖动）；空结果不重试（可能是真无此 POI）
        for attempt in range(2):
            try:
                response = await _get_client().get(SEARCH_URL, params=params)
                response.raise_for_status()
                data = response.json()
                break
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(0.4)
                else:
                    raise
        if data.get("status") != "1":
            logger.debug(f"POI search failed: {data.get('info')} for {keywords}@{city}")
            return []

        results: List[Dict[str, Any]] = []
        for poi in data.get("pois", []):
            lat, lon = None, None
            loc = poi.get("location", "")
            if "," in loc:
                lon_str, lat_str = loc.split(",", 1)
                try:
                    lon, lat = float(lon_str), float(lat_str)
                except ValueError:
                    pass
            results.append({
                "name": poi.get("name", ""),
                "adname": poi.get("adname", ""),
                "address": poi.get("address", ""),
                "typecode": poi.get("typecode", ""),
                "lat": lat,
                "lon": lon,
            })
        return results
    except Exception as e:
        logger.debug(f"POI search error for {keywords}@{city}: {e}")
        return []


# ── Public API ───────────────────────────────────────────


async def get_walking_route(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
) -> Optional[Dict[str, Any]]:
    """Get walking directions between two points.

    Args:
        origin: (longitude, latitude) tuple.
        destination: (longitude, latitude) tuple.

    Returns:
        Dict with distance (meters), duration (seconds), or None on failure.
    """
    if not _check_amap_available():
        # Fallback: estimate distance using haversine
        try:
            lat1, lon1 = radians(destination[1]), radians(destination[0])
            lat2, lon2 = radians(origin[1]), radians(origin[0])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            dist_m = 6371000 * c
            return {"distance_m": int(dist_m), "duration_s": int(dist_m / 1.2), "steps": 1}
        except Exception:
            return None

    params = _sign_params({
        "key": settings.AMAP_API_KEY,
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "output": "JSON",
    })

    try:
        response = await _get_client().get(WALKING_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "1":
            logger.debug(f"Walking route failed: {data.get('info')}")
            return None

        route = data.get("route", {})
        paths = route.get("paths", [])
        if not paths:
            return None

        return {
            "distance_m": int(paths[0].get("distance", 0)),
            "duration_s": int(paths[0].get("duration", 0)),
            "steps": len(paths[0].get("steps", [])),
        }
    except Exception as e:
        logger.debug(f"Walking route error: {e}")
        return None


async def get_transit_route(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    city: str = "",
) -> Optional[Dict[str, Any]]:
    """Get public transit directions between two points.

    Args:
        origin: (longitude, latitude) tuple.
        destination: (longitude, latitude) tuple.
        city: City name for transit search context.

    Returns:
        Dict with distance, duration, cost, or None on failure.
    """
    if not _check_amap_available():
        # Fallback: estimate using haversine
        try:
            lat1, lon1 = radians(destination[1]), radians(destination[0])
            lat2, lon2 = radians(origin[1]), radians(origin[0])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            dist_m = 6371000 * c
            return {
                "distance_m": int(dist_m),
                "duration_s": int(dist_m / 8.0),  # transit ~8 m/s avg
                "cost_yuan": max(2.0, dist_m / 1000 * 3.0),
                "walking_distance_m": 500,
            }
        except Exception:
            return None

    params = _sign_params({
        "key": settings.AMAP_API_KEY,
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "city": city,
        "output": "JSON",
    })

    try:
        response = await _get_client().get(TRANSIT_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "1":
            logger.debug(f"Transit route failed: {data.get('info')}")
            return None

        route = data.get("route", {})
        transits = route.get("transits", [])
        if not transits:
            return None

        t = transits[0]
        return {
            "distance_m": int(t.get("distance", 0)),
            "duration_s": int(t.get("duration", 0)),
            "cost_yuan": float(t.get("cost", 0)),
            "walking_distance_m": int(t.get("walking_distance", 0)),
        }
    except Exception as e:
        logger.debug(f"Transit route error: {e}")
        return None


async def get_distance_matrix(
    origins: List[Tuple[float, float]],
    destination: Tuple[float, float],
) -> List[Dict[str, Any]]:
    """Get distances from multiple origins to a single destination.

    Useful for evaluating location efficiency: how far each attraction
    is from the user's hotel or city center.

    Args:
        origins: List of (lon, lat) tuples (max 10 per call).
        destination: (lon, lat) tuple.

    Returns:
        List of dicts with distance_m, duration_s per origin.
    """
    if not origins:
        return []

    if not _check_amap_available():
        # Fallback: haversine distances
        results = []
        dlat, dlon = radians(destination[1]), radians(destination[0])
        for lon, lat in origins[:10]:
            try:
                olat, olon = radians(lat), radians(lon)
                dlat2, dlon2 = olat - dlat, olon - dlon
                a = sin(dlat2/2)**2 + cos(dlat)*cos(olat)*sin(dlon2/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                dist_m = int(6371000 * c)
                results.append({"distance_m": dist_m, "duration_s": int(dist_m / 10.0)})
            except Exception:
                results.append({"distance_m": 0, "duration_s": 0})
        return results

    # Amap distance API: origins as pipe-separated coords
    origins_str = "|".join(f"{lon},{lat}" for lon, lat in origins[:10])
    dest_str = f"{destination[0]},{destination[1]}"

    params = _sign_params({
        "key": settings.AMAP_API_KEY,
        "origins": origins_str,
        "destination": dest_str,
        "type": "0",  # 0 = driving
        "output": "JSON",
    })

    try:
        response = await _get_client().get(DISTANCE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "1":
            logger.debug(f"Distance matrix failed: {data.get('info')}")
            return []

        results = data.get("results", [])
        return [
            {
                "distance_m": int(r.get("distance", 0)),
                "duration_s": int(r.get("duration", 0)),
            }
            for r in results
        ]
    except Exception as e:
        logger.debug(f"Distance matrix error: {e}")
        return []


async def score_location_efficiency(
    places: List[Dict[str, Any]],
    city_center: Optional[Tuple[float, float]] = None,
) -> List[float]:
    """Score location efficiency for multiple attractions.

    Uses Amap distance matrix to compute how close each attraction
    is to the city center (or geometric centroid of all attractions).

    Scoring:
      - Attractions within 5km of center → 1.0
      - 5-15km → 0.7
      - 15-30km → 0.4
      - >30km → 0.1

    Args:
        places: List of attraction dicts, each with 'lat'/'lon' or 'metadata'.
        city_center: Optional (lon, lat) for city center. Auto-computed if None.

    Returns:
        List of scores 0.0-1.0, one per place.
    """
    # Extract coordinates
    coords: List[Optional[Tuple[float, float]]] = []
    for p in places:
        meta = p.get("metadata", {})
        lat = meta.get("lat") or p.get("lat")
        lon = meta.get("lon") or p.get("lon")
        if lat and lon:
            try:
                coords.append((float(lon), float(lat)))
            except (ValueError, TypeError):
                coords.append(None)
        else:
            coords.append(None)

    valid_coords = [c for c in coords if c is not None]
    if not valid_coords:
        return [0.5] * len(places)

    # Compute city center: geometric centroid of all valid attractions
    if city_center is None:
        avg_lon = sum(c[0] for c in valid_coords) / len(valid_coords)
        avg_lat = sum(c[1] for c in valid_coords) / len(valid_coords)
        city_center = (avg_lon, avg_lat)

    # Phase 10: Check cache for Amap distance matrix (most expensive API call)
    #   Key includes city_center — different destinations produce different distances
    coord_key = hashlib.md5(
        json.dumps((sorted(valid_coords), city_center), sort_keys=True).encode()
    ).hexdigest()
    cache_key = f"amap:{coord_key}"
    distances = None
    cache = None
    try:
        from app.services.cache_service import get_cache
        cache = get_cache()
        cached = await cache.get(cache_key)
        if cached:
            distances = json.loads(cached)
            logger.debug("Amap distance cache hit for %d coords", len(valid_coords))
    except Exception as e:
        logger.debug("Cache read failed (non-fatal): %s", e)

    if distances is None:
        distances = await get_distance_matrix(valid_coords, city_center)
        if cache is not None:
            try:
                await cache.set(cache_key, json.dumps(distances), ttl=3600)
            except Exception:
                pass  # cache write failure is non-fatal

    # Map distances back to scores
    dist_map: Dict[Tuple[float, float], float] = {}
    for i, dist in enumerate(distances):
        if i < len(valid_coords):
            dist_map[valid_coords[i]] = dist.get("distance_m", 99999)

    scores = []
    for c in coords:
        if c is None or c not in dist_map:
            scores.append(0.5)  # unknown — neutral
            continue

        d = dist_map[c]
        if d <= 5000:
            scores.append(1.0)
        elif d <= 15000:
            scores.append(0.7)
        elif d <= 30000:
            scores.append(0.4)
        else:
            scores.append(0.1)

    return scores

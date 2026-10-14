"""Geocoding tools: forward/reverse map lookup plus a served-city snapshot.

Coordinate order: callers pass user-facing ``lat``/``long`` floats. The
geocoder itself takes ``lng,lat`` strings (``district`` for forward bias,
``location`` for reverse); the helpers below encode that order internally.

Geocoding success is not delivery coverage: the forward endpoint resolves
unserved cities (e.g. Isfahan, Tabriz) with HTTP 200, so these tools never
claim catalog coverage.
"""

from __future__ import annotations

import math
from typing import Any

from .http import ApiError, fetch
from .registry import tool

OBSERVED_AT = "2026-10-14"

_FORWARD_PATH = "/v1/api/Map/geocode/forward"
_REVERSE_PATH = "/v1/api/Map/geocode/reverse"
_FORWARD_SOURCE = "Map/geocode/forward"
_REVERSE_SOURCE = "Map/geocode/reverse"

# Static snapshot of the site city selector observed 2026-10-14. There is no
# observed city-list API; this list is explicitly not exhaustive or live.
_CITIES: tuple[dict[str, Any], ...] = (
    {"name": "تهران", "name_en": "Tehran", "lat": 35.6892, "long": 51.389, "served": True},
    {"name": "مشهد", "name_en": "Mashhad", "lat": 36.295289, "long": 59.585015, "served": True},
    {"name": "شیراز", "name_en": "Shiraz", "lat": 29.67185, "long": 52.499858, "served": True},
    {"name": "اصفهان", "name_en": "Isfahan", "lat": 32.651789, "long": 51.693768, "served": False},
    {"name": "تبریز", "name_en": "Tabriz", "lat": 38.080028, "long": 46.2919, "served": False},
)


def _check_coords(lat: float, long: float) -> None:
    for label, value, low, high in (("lat", lat, -90.0, 90.0), ("long", long, -180.0, 180.0)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a number")
        if not (low <= float(value) <= high):
            raise ValueError(f"{label} out of range")


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _norm_corner(value: Any) -> dict[str, float | None] | None:
    if not isinstance(value, dict):
        return None
    lat = _to_float(value.get("lat"))
    long = _to_float(value.get("lng", value.get("long")))
    if lat is None and long is None:
        return None
    return {"lat": lat, "long": long}


def _norm_place(item: Any) -> dict[str, Any]:
    geo = item.get("geo_location") if isinstance(item, dict) else None
    if not isinstance(geo, dict):
        geo = {}
    center = geo.get("center")
    if not isinstance(center, dict):
        center = {}
    south_west = _norm_corner(geo.get("south_west"))
    north_east = _norm_corner(geo.get("north_east"))
    return {
        "name": geo.get("title") or (item.get("title") if isinstance(item, dict) else None),
        "description": item.get("description") or None if isinstance(item, dict) else None,
        "lat": _to_float(center.get("lat")),
        "long": _to_float(center.get("lng", center.get("long"))),
        "category": geo.get("category") or None,
        "bounds": None
        if south_west is None and north_east is None
        else {"south_west": south_west, "north_east": north_east},
    }


@tool("Find a place by name")
async def find_location(
    query: str, near_lat: float | None = None, near_long: float | None = None, limit: int = 10
) -> dict:
    """Forward-geocode ``query``; optional ``near_lat``/``near_long`` search bias.

    The bias is encoded as ``district=<long>,<lat>`` and only narrows search
    ranking, never delivery coverage. Returns ``places`` with name,
    description, center lat/long, bounds and category (nullable where absent).
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if (near_lat is None) != (near_long is None):
        raise ValueError("near_lat and near_long must be given together")
    if near_lat is not None and near_long is not None:
        _check_coords(near_lat, near_long)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    params: dict[str, object] = {"search_text": query}
    if near_lat is not None and near_long is not None:
        params["district"] = f"{near_long},{near_lat}"
    body = await fetch(_FORWARD_PATH, params=params)
    if not isinstance(body, dict):
        raise ApiError(f"Unexpected {_FORWARD_SOURCE} response shape.", 200)
    if body.get("status") != "OK":
        raise ApiError(f"{_FORWARD_SOURCE} reported status {body.get('status')!r}.", 200)
    results = body.get("results")
    if not isinstance(results, list):
        raise ApiError(f"Unexpected {_FORWARD_SOURCE} response shape: 'results' is missing or not a list.", 200)
    places = [_norm_place(item) for item in results if isinstance(item, dict)][:limit]
    return {"query": query, "places": places, "source": _FORWARD_SOURCE}


@tool("Reverse-geocode coordinates to an address")
async def reverse_geocode(lat: float, long: float) -> dict:
    """Reverse-geocode ``lat``/``long`` (sent as ``location=<long>,<lat>``).

    Returns the street address, local address, subdivision titles and the
    geocoder certainty (nullable where absent). Not a coverage check.
    """
    _check_coords(lat, long)
    body = await fetch(
        _REVERSE_PATH,
        params={"location": f"{long},{lat}", "subdivision": "true", "local_address": "true"},
    )
    if not isinstance(body, dict):
        raise ApiError(f"Unexpected {_REVERSE_SOURCE} response shape.", 200)
    if body.get("status") != "OK":
        raise ApiError(f"{_REVERSE_SOURCE} reported status {body.get('status')!r}.", 200)
    raw_subdivisions = body.get("subdivisions")
    subdivisions: dict[str, str | None] = {}
    if isinstance(raw_subdivisions, dict):
        for level, entry in raw_subdivisions.items():
            subdivisions[level] = entry.get("title") or None if isinstance(entry, dict) else None
    return {
        "lat": lat,
        "long": long,
        "address": body.get("address") or None,
        "local_address": body.get("local_Address") or None,
        "subdivision_prefix": body.get("subdivision_Prefix") or None,
        "subdivisions": subdivisions,
        "certainty": _to_int(body.get("certainty")),
        "source": _REVERSE_SOURCE,
    }


@tool("Served-city snapshot")
async def supported_cities() -> dict:
    """Static snapshot of the cities observed served on 2026-10-14.

    Tehran, Mashhad and Shiraz were selectable in the site city selector;
    Isfahan and Tabriz were marked coming-soon. There is no city-list API, so
    this is documentation, not a live or exhaustive list, and geocoding one of
    these names says nothing about delivery coverage.
    """
    return {
        "observed_at": OBSERVED_AT,
        "source": "Tapsi Food site city selector (no city-list API observed)",
        "coverage_note": "Snapshot only: geocoding a city does not mean Tapsi Food serves it.",
        "cities": [dict(city) for city in _CITIES],
    }

"""Behavior tests for the Tapsi geocoding tools.

Public names (server adds the prefix): tapsi_find_location,
tapsi_reverse_geocode, tapsi_supported_cities.
"""

import pytest

from tapsi_food_mcp.http import ApiError
from tapsi_food_mcp.location import find_location, reverse_geocode, supported_cities

pytestmark = pytest.mark.anyio

FORWARD_BODY = {
    "status": "OK",
    "results": [
        {
            "geo_location": {
                "south_west": {"lat": 35.57112, "lng": 51.096799},
                "north_east": {"lat": 35.832211, "lng": 51.633199},
                "center": {"lat": 35.701737, "lng": 51.385173},
                "title": "تهران",
                "category": "District",
            },
            "description": "شهر تهران،تهران",
        },
        {
            "geo_location": {
                "south_west": {"lat": 34.883788, "lng": 50.32948},
                "north_east": {"lat": 36.10204, "lng": 53.154468},
                "center": {"lat": 35.494973, "lng": 51.328772},
                "title": "استان تهران",
                "category": "District",
            },
            "description": "استان تهران",
        },
    ],
}

REVERSE_BODY = {
    "address": "حر، خ. امام خمینی، بعد از خ. کارگر جنوبی، دانشگاه فرماندهی و ستاد آجا",
    "subdivision_Prefix": "تهران",
    "local_Address": "حر",
    "subdivisions": {
        "ostan": {"id": 1001, "title": "تهران", "code": "23", "type": "ostan"},
        "shahrestan": {"id": 100101, "title": "تهران", "code": "2301", "type": "shahrestan"},
        "bakhsh": {"id": 10410151, "title": "مرکزی", "code": "230102", "type": "bakhsh"},
    },
    "certainty": 92,
    "status": "OK",
}


async def test_find_location_bias_is_lng_lat_and_places_normalized(api):
    api["/v1/api/Map/geocode/forward"] = FORWARD_BODY
    result = await find_location("تهران", near_lat=35.6892, near_long=51.389)

    (call,) = api.calls
    assert call.url.params["search_text"] == "تهران"
    # Geocoder bias order is longitude,latitude (distinct asymmetric values).
    assert call.url.params["district"] == "51.389,35.6892"

    (first, second) = result["places"]
    assert first["name"] == "تهران"
    assert first["description"] == "شهر تهران،تهران"
    assert first["lat"] == pytest.approx(35.701737)
    assert first["long"] == pytest.approx(51.385173)
    assert first["category"] == "District"
    assert first["bounds"]["south_west"] == {"lat": pytest.approx(35.57112), "long": pytest.approx(51.096799)}
    assert first["bounds"]["north_east"] == {"lat": pytest.approx(35.832211), "long": pytest.approx(51.633199)}
    assert second["name"] == "استان تهران"
    assert result["source"] == "Map/geocode/forward"


async def test_find_location_without_bias_omits_district(api):
    api["/v1/api/Map/geocode/forward"] = FORWARD_BODY
    result = await find_location("تهران")
    assert "district" not in api.calls[0].url.params
    assert len(result["places"]) == 2


async def test_find_location_empty_results_is_empty_places(api):
    api["/v1/api/Map/geocode/forward"] = {"status": "OK", "results": []}
    result = await find_location("ناموجود")
    assert result["places"] == []


async def test_find_location_nullable_bounds_and_category(api):
    api["/v1/api/Map/geocode/forward"] = {
        "status": "OK",
        "results": [{"geo_location": {"center": {"lat": 32.65, "lng": 51.69}, "title": "x"}}],
    }
    (place,) = (await find_location("x"))["places"]
    assert place["category"] is None
    assert place["bounds"] is None
    assert place["description"] is None
    assert place["lat"] == pytest.approx(32.65)
    assert place["long"] == pytest.approx(51.69)


async def test_find_location_rejects_half_specified_bias(api):
    with pytest.raises(ValueError):
        await find_location("تهران", near_lat=35.6892)
    with pytest.raises(ValueError):
        await find_location("تهران", near_long=51.389)
    assert api.calls == []


async def test_find_location_rejects_bad_query_limit_and_bias_range(api):
    with pytest.raises(ValueError):
        await find_location("  ")
    with pytest.raises(ValueError):
        await find_location("تهران", limit=0)
    with pytest.raises(ValueError):
        await find_location("تهران", near_lat=95.0, near_long=51.389)
    assert api.calls == []


async def test_reverse_geocode_location_is_lng_lat_and_nested_fields_mapped(api):
    api["/v1/api/Map/geocode/reverse"] = REVERSE_BODY
    result = await reverse_geocode(35.6892, 51.389)

    (call,) = api.calls
    assert call.url.params["location"] == "51.389,35.6892"
    assert call.url.params["subdivision"] == "true"
    assert call.url.params["local_address"] == "true"

    assert result["address"].startswith("حر، خ. امام خمینی")
    assert result["local_address"] == "حر"
    assert result["subdivision_prefix"] == "تهران"
    assert result["subdivisions"]["ostan"] == "تهران"
    assert result["subdivisions"]["bakhsh"] == "مرکزی"
    assert result["certainty"] == 92
    assert result["lat"] == pytest.approx(35.6892)
    assert result["long"] == pytest.approx(51.389)


async def test_reverse_geocode_nullable_fields(api):
    api["/v1/api/Map/geocode/reverse"] = {"status": "OK"}
    result = await reverse_geocode(29.67185, 52.499858)
    assert result["address"] is None
    assert result["local_address"] is None
    assert result["subdivision_prefix"] is None
    assert result["subdivisions"] == {}
    assert result["certainty"] is None


async def test_reverse_geocode_rejects_invalid_coordinates(api):
    with pytest.raises(ValueError):
        await reverse_geocode(95.0, 51.389)
    with pytest.raises(ValueError):
        await reverse_geocode(35.6892, 200.0)
    assert api.calls == []


async def test_find_location_rejects_failed_status(api):
    api["/v1/api/Map/geocode/forward"] = {"status": "ZERO_RESULTS", "results": []}
    with pytest.raises(ApiError):
        await find_location("تهران")


async def test_find_location_rejects_missing_or_non_list_results(api):
    api["/v1/api/Map/geocode/forward"] = {"status": "OK"}
    with pytest.raises(ApiError):
        await find_location("تهران")
    api["/v1/api/Map/geocode/forward"] = {"status": "OK", "results": {"center": 1}}
    with pytest.raises(ApiError):
        await find_location("تهران")


async def test_reverse_geocode_rejects_failed_status(api):
    api["/v1/api/Map/geocode/reverse"] = {"status": "ZERO_RESULTS"}
    with pytest.raises(ApiError):
        await reverse_geocode(35.6892, 51.389)


async def test_supported_cities_marks_served_and_unserved(api):
    result = await supported_cities()
    by_en = {city["name_en"]: city for city in result["cities"]}
    assert by_en["Tehran"]["served"] is True
    assert by_en["Mashhad"]["served"] is True
    assert by_en["Shiraz"]["served"] is True
    assert by_en["Isfahan"]["served"] is False
    assert by_en["Tabriz"]["served"] is False
    assert by_en["Tehran"]["lat"] == pytest.approx(35.6892)
    assert by_en["Tehran"]["long"] == pytest.approx(51.389)
    assert result["observed_at"] == "2026-10-14"
    # Static snapshot: no API traffic, no per-city coverage claim.
    assert api.calls == []

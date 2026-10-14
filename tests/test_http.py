"""Behavior tests for the anonymous Tapsi Food transport (src/tapsi_food_mcp/http.py)."""

import httpx
import pytest

from tapsi_food_mcp import http
from tapsi_food_mcp.http import ApiError, fetch

pytestmark = pytest.mark.anyio


def test_api_base_is_tapsi_food():
    assert http.API_BASE == "https://api.tapsi.food"


async def test_fetch_gets_relative_path_and_drops_none_params(api):
    api["/v1/api/Map/geocode/forward"] = {"status": "OK", "results": []}
    body = await fetch("/v1/api/Map/geocode/forward", params={"search_text": "تهران", "district": None})
    assert body == {"status": "OK", "results": []}
    (call,) = api.calls
    assert call.method == "GET"
    assert call.url.host == "api.tapsi.food"
    assert call.url.path == "/v1/api/Map/geocode/forward"
    assert call.url.params["search_text"] == "تهران"
    assert "district" not in call.url.params


async def test_fetch_accepts_path_without_leading_slash(api):
    api["/v1/api/search-discovery/page-content/"] = {"content": []}
    await fetch("v1/api/search-discovery/page-content/", params={"pageNumber": 1})
    assert api.calls[0].url.path == "/v1/api/search-discovery/page-content/"


async def test_fetch_encodes_brackets_and_persian_query(api):
    api["/v1/api/search-discovery/Search/product-search"] = {"data": {}}
    await fetch(
        "/v1/api/search-discovery/Search/product-search",
        params={"query": "شیر", "latitude": 35.6892, "longitude": 51.389, "businessTypeIds[0]": 13},
    )
    params = api.calls[0].url.params
    assert params["query"] == "شیر"
    assert params["businessTypeIds[0]"] == "13"
    assert params["latitude"] == "35.6892"


async def test_fetch_404_is_unavailable_coverage_not_an_empty_list(api):
    api["/v1/api/search-discovery/page-content/business-line-15"] = lambda r: httpx.Response(404, text="Not Found")
    with pytest.raises(ApiError) as exc:
        await fetch("/v1/api/search-discovery/page-content/business-line-15")
    assert exc.value.status == 404
    assert "coverage" in str(exc.value).lower() or "404" in str(exc.value)


async def test_fetch_429_stays_actionable(api):
    api["/v1/api/search-discovery/Search/product-search"] = lambda r: httpx.Response(429, text="slow down")
    with pytest.raises(ApiError) as exc:
        await fetch("/v1/api/search-discovery/Search/product-search")
    assert exc.value.status == 429
    assert "429" in str(exc.value)


async def test_fetch_invalid_json_is_an_error(api):
    api["/v1/api/Map/geocode/forward"] = lambda r: httpx.Response(200, text="<html>not json</html>")
    with pytest.raises(ApiError) as exc:
        await fetch("/v1/api/Map/geocode/forward")
    assert exc.value.status == 200
    assert "non-JSON" in str(exc.value)


async def test_fetch_timeout_is_an_error_without_status(api):
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("upstream is slow")

    api["/v1/api/Map/geocode/forward"] = slow
    with pytest.raises(ApiError) as exc:
        await fetch("/v1/api/Map/geocode/forward")
    assert exc.value.status is None


async def test_fetch_status_false_envelope_is_an_error(api):
    api["/v1/api/Map/geocode/forward"] = lambda r: httpx.Response(200, json={"status": False, "message": "bad key"})
    with pytest.raises(ApiError) as exc:
        await fetch("/v1/api/Map/geocode/forward")
    assert exc.value.status == 200
    assert "bad key" in str(exc.value)

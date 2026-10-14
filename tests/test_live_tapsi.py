"""Live end-to-end tests over a spawned stdio server subprocess (opt-in, `pytest -m live`).

Auto-excluded by default (`pyproject.toml` defaults to `-m 'not live'`).
Anonymous read-only calls only; no login/cart/order, no retries.
~8 real GET requests total across the three tests.

Known volatility risks: vendor 2y97wk may change status/menu/reviews; Tehran/Mashhad
coverage, search results and grocery rows are live data; Isfahan 404/OutOfCoverage
shapes may change if Tapsi expands coverage. Assertions avoid exact counts, prices,
names and ratings for this reason.
"""

import json
import sys

import pytest
from mcp import Client, StdioServerParameters

pytestmark = [pytest.mark.live, pytest.mark.anyio]

TEHRAN_LAT = 35.6892
TEHRAN_LONG = 51.389
MASHHAD_LAT = 36.295289
MASHHAD_LONG = 59.585015
ISFAHAN_LAT = 32.651789
ISFAHAN_LONG = 51.693768
VENDOR_CODE = "2y97wk"


def _stdio_client() -> Client:
    return Client(
        StdioServerParameters(command=sys.executable, args=["-m", "tapsi_food_mcp.server"]),
        read_timeout_seconds=30,
    )


def _payload(result) -> dict:
    """Unwrap a CallToolResult robustly: structured_content first, else content[0].text JSON."""
    assert not result.is_error, f"tool returned is_error: {result.content!r}"
    data = result.structured_content
    if isinstance(data, dict) and data:
        return data.get("result", data) if isinstance(data.get("result"), dict) else data
    assert result.content, "empty tool result content"
    text = getattr(result.content[0], "text", None)
    assert isinstance(text, str) and text.strip(), f"unexpected content block: {result.content!r}"
    parsed = json.loads(text)
    assert isinstance(parsed, dict), f"expected a JSON object, got: {text[:200]!r}"
    return parsed


async def test_live_tehran_tools_menu_and_reviews():
    """List the 17 tapsi_* tools, then Tehran geocode/search/menu/reviews via stdio."""
    async with _stdio_client() as client:
        tools = (await client.list_tools()).tools
        names = {t.name for t in tools}
        assert len(tools) == 17
        assert len(names) == len(tools)
        assert all(t.name.startswith("tapsi_") for t in tools)
        assert all(t.annotations is not None and t.annotations.read_only_hint is True for t in tools), sorted(
            t.name for t in tools if t.annotations is None or not t.annotations.read_only_hint
        )

        place = _payload(await client.call_tool("tapsi_find_location", {"query": "تهران", "limit": 1}))
        assert isinstance(place.get("places"), list) and len(place["places"]) >= 1
        first = place["places"][0]
        assert isinstance(first.get("name"), str) and first["name"].strip()

        search = _payload(
            await client.call_tool(
                "tapsi_search_products",
                {"query": "پیتزا", "lat": TEHRAN_LAT, "long": TEHRAN_LONG, "page_size": 2},
            )
        )
        assert search.get("coverage") == "available"
        assert isinstance(search.get("products"), list) and search["products"]
        assert len(search["products"]) <= 2
        for row in search["products"]:
            assert isinstance(row, dict) and row.get("name")

        menu = _payload(
            await client.call_tool(
                "tapsi_vendor_menu",
                {"vendor_code": VENDOR_CODE, "lat": TEHRAN_LAT, "long": TEHRAN_LONG},
            )
        )
        assert menu.get("vendor", {}).get("code") == VENDOR_CODE
        assert isinstance(menu.get("categories"), list) and menu["categories"]
        assert menu.get("coverage") == "available"

        reviews = _payload(await client.call_tool("tapsi_vendor_reviews", {"vendor_code": VENDOR_CODE, "page_size": 2}))
        assert reviews.get("vendor_code") == VENDOR_CODE
        assert isinstance(reviews.get("reviews"), list)
        assert len(reviews["reviews"]) <= 2


async def test_live_mashhad_and_grocery_search():
    """Served Mashhad food search plus Tehran grocery search stay available and bounded."""
    async with _stdio_client() as client:
        mashhad = _payload(
            await client.call_tool(
                "tapsi_search_products",
                {"query": "پیتزا", "lat": MASHHAD_LAT, "long": MASHHAD_LONG, "page_size": 2},
            )
        )
        assert mashhad.get("coverage") == "available"
        assert isinstance(mashhad.get("source"), str) and mashhad["source"]
        assert isinstance(mashhad.get("products"), list)
        assert len(mashhad["products"]) <= 2

        grocery = _payload(
            await client.call_tool(
                "tapsi_grocery_search",
                {"query": "شیر", "lat": TEHRAN_LAT, "long": TEHRAN_LONG, "page_size": 2},
            )
        )
        assert grocery.get("coverage") == "available"
        assert isinstance(grocery.get("source"), str) and grocery["source"]
        assert isinstance(grocery.get("products"), list)
        assert len(grocery["products"]) <= 2


async def test_live_isfahan_unserved_coverage():
    """Isfahan hub 404s and the Tehran vendor menu there is not deliverable."""
    async with _stdio_client() as client:
        hub = _payload(await client.call_tool("tapsi_restaurants", {"lat": ISFAHAN_LAT, "long": ISFAHAN_LONG}))
        assert hub.get("coverage") == "unavailable"

        menu = _payload(
            await client.call_tool(
                "tapsi_vendor_menu",
                {"vendor_code": VENDOR_CODE, "lat": ISFAHAN_LAT, "long": ISFAHAN_LONG},
            )
        )
        assert menu.get("vendor", {}).get("code") == VENDOR_CODE
        assert menu.get("coverage") == "unavailable"
        assert menu.get("deliverable") is False

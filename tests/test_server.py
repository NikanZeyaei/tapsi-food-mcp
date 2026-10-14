"""Registry tests: the server must expose exactly the 17 tapsi_* tools, all read-only, none Snapp."""

import pytest

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    # Location (3)
    "tapsi_find_location",
    "tapsi_reverse_geocode",
    "tapsi_supported_cities",
    # Discovery/search (7)
    "tapsi_search_products",
    "tapsi_search_vendors",
    "tapsi_restaurants",
    "tapsi_discounted_vendors",
    "tapsi_flash_deals",
    "tapsi_discovery_feed",
    "tapsi_collection",
    # Vendor/reviews (4)
    "tapsi_vendor_menu",
    "tapsi_order_costs",
    "tapsi_vendor_reviews",
    "tapsi_product_reviews",
    # Grocery (3)
    "tapsi_grocery_categories",
    "tapsi_grocery_stores",
    "tapsi_grocery_search",
}

OBSOLETE_SNAPP_TOOLS = {
    "find_location",
    "reverse_geocode",
    "list_cities",
    "food_search",
    "food_find_cheapest",
    "food_restaurants",
    "food_menu",
    "food_order_costs",
    "food_reviews",
    "food_party_deals",
    "food_meal_for_one",
    "food_discounted_vendors",
    "market_categories",
    "market_search",
    "market_find_cheapest",
    "market_stores",
    "market_store_info",
    "market_store_products",
    "market_product",
    "market_reviews",
    "market_party_deals",
}


async def _names(client):
    return {t.name for t in (await client.list_tools()).tools}


async def test_no_snapp_tools_registered(client):
    names = await _names(client)
    assert not (names & OBSOLETE_SNAPP_TOOLS)
    assert all(name.startswith("tapsi_") and "snapp" not in name for name in names)


async def test_registered_tools_are_read_only(client):
    tools = (await client.list_tools()).tools
    assert len(tools) == len(EXPECTED_TOOLS)
    for t in tools:
        assert t.annotations is not None and t.annotations.read_only_hint is True, t.name


async def test_exact_tapsi_tool_inventory(client):
    assert await _names(client) == EXPECTED_TOOLS

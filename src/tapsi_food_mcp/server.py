"""MCP server entry point: registers every read-only Tapsi Food tool."""

import logging

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import __version__, discovery, grocery, location, vendor  # noqa: F401  (imports register the tools)
from .registry import TOOLS

INSTRUCTIONS = """\
Unofficial, read-only access to Tapsi Food (food delivery catalog, api.tapsi.food) in Iran.
Nothing here can log in, add to a basket, order or pay.

Workflow:
1. Get coordinates: tapsi_find_location (place name) or tapsi_supported_cities (snapshot of
   observed served cities). Every catalog tool needs lat/long because menus, prices and
   delivery depend on the delivery point.
2. Food: tapsi_search_products / tapsi_search_vendors for dishes and restaurants,
   tapsi_restaurants for the restaurant hub, tapsi_vendor_menu for one restaurant,
   tapsi_order_costs before quoting any total (delivery fee, minimum order; no coupons).
   Deals via tapsi_flash_deals / tapsi_discounted_vendors; discovery via
   tapsi_discovery_feed / tapsi_collection; reviews via tapsi_vendor_reviews /
   tapsi_product_reviews.
3. Groceries: tapsi_grocery_categories / tapsi_grocery_stores / tapsi_grocery_search
   (grocery lives inside the same Tapsi catalog; there is no separate market host).

Conventions: prices are integer Toman. Ratings are 0-5 (null = not rated). Vendor codes look
like '2y97wk'. Persian queries match best ('پیتزا', 'شیر'). Search/list/collection pages are
1-based; review pages are 0-based. Geocoding a place is not delivery coverage: only Tehran,
Mashhad and Shiraz were observed served (2026-10-14); elsewhere the catalog 404s or returns
empty, and vendor menus may report OutOfCoverage. A 404 is unavailable coverage, never an
empty list; a 429 means back off, never silently empty results.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

mcp = MCPServer(
    "tapsi-food-mcp",
    title="Tapsi Food",
    instructions=INSTRUCTIONS,
    version=__version__,
    website_url="https://github.com/NikanZeyaei/tapsi-food-mcp",
)

for fn, title in TOOLS:
    # Capability modules define plain names (find_location); the public tool
    # name always carries the tapsi_ prefix.
    name = fn.__name__ if fn.__name__.startswith("tapsi_") else f"tapsi_{fn.__name__}"
    mcp.add_tool(fn, name=name, title=title, annotations=READ_ONLY)


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request floods client logs
    mcp.run()


if __name__ == "__main__":
    main()

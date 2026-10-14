<!-- mcp-name: io.github.NikanZeyaei/tapsi-food-mcp -->
<div align="center">

# tapsi-food-mcp: Tapsi Food MCP server for AI agents

**Let your AI agent browse Tapsi Food's catalog (تپسی‌فود).**
An unofficial, anonymous, read-only MCP server for Tapsi Food in Iran: search dishes and groceries,
read menus, delivery costs and reviews, and catch flash deals — with no login, from Claude, Cursor or Copilot.

</div>

---

## Contract

- Exactly **17 `tapsi_*` tools**: 3 location, 7 discovery/search, 4 vendor/review, 3 grocery. No in-store cluster tool: its map sits next to a login-only purchase flow, out of scope for this anonymous catalog.
- All tools register via `@tool` in `tapsi_food_mcp/registry.py` (`TOOLS`) and are served with `ToolAnnotations(read_only_hint=True)`. Capability modules define plain function names (e.g. `find_location`); `server.py` adds the public `tapsi_` prefix at registration.
- Anonymous GET only against `https://api.tapsi.food` via `tapsi_food_mcp.http.fetch(path, *, params)`. No auth, cookies, signed headers, cart or order APIs.
- Input coordinates are distinct `lat: float, long: float`. Geocode bias is `near_lat`/`near_long`; the geocoder wire format stays `lng,lat` internally.
- Search/list/collection pages are **1-based** (`page`, default 1, `page_size` default 10, bounded 1-50); review pages are **0-based** (`page` default 0, `page_size` default 20, bounded 1-50).
- Money is **integer Toman** (never divided). A search `id`/`productVariationId` is not a menu `productId`; no global SKU exists.
- 404 on a catalog page = **unavailable coverage**, never an empty list. 429 = **back off**, never silently empty results.
- `supported_cities` is a dated observed snapshot (Tehran, Mashhad, Shiraz served), not a live endpoint.

| Tool | Inputs beyond defaults | Source and output |
|---|---|---|
| `tapsi_find_location` | `query: str, near_lat: float \| None = None, near_long: float \| None = None, limit: int = 10` | `Map/geocode/forward`; places with name, description, center lat/long, bounds, category; bias is longitude,latitude. |
| `tapsi_reverse_geocode` | `lat: float, long: float` | `Map/geocode/reverse`; address, subdivisions, certainty; location param longitude,latitude. |
| `tapsi_supported_cities` | none | Static observed snapshot (Tehran, Mashhad, Shiraz active; Isfahan/Tabriz unserved), explicitly not exhaustive or live. |
| `tapsi_search_products` | `query: str, lat: float, long: float, business_type_id: int \| None = None, page: int = 1, page_size: int = 10` | `Search/product-search`; total/products, vendor/fee/ETA as observed, no stock promise. |
| `tapsi_search_vendors` | same search inputs | `Search/vendor-search`; total/vendors with code, rating/status, fee/ETA as observed. |
| `tapsi_restaurants` | `lat: float, long: float, page: int = 1, page_size: int = 10` | `page-content/business-line-15`; typed vendor rows, observed filters, not arbitrary filter parameters. |
| `tapsi_discounted_vendors` | same list inputs | `page-content/فودشات`; curated vendor rows, not all discounted stores. |
| `tapsi_flash_deals` | same list inputs | `page-content/تپ-تایم`; products, nullable discount stock and countdown; not FoodParty parity. |
| `tapsi_discovery_feed` | `lat: float, long: float, page: int = 1` | `page-content/`; typed sections and total_sections; preserve unknown widgets. |
| `tapsi_collection` | `slug: str, lat: float, long: float, page: int = 1, page_size: int = 10, filter_value: str \| None = None` | Allowlisted/current-feed `page-content/{slug}`; config, available filters, typed sections; only observed filter `1-82`. |
| `tapsi_vendor_menu` | `vendor_code: str, lat: float, long: float, query: str \| None = None` | `v2/api/Vendor/{code}/vendor`; complete nested categories/products/variations/options/stock, coverage; optional local query filter. |
| `tapsi_order_costs` | `vendor_code: str, lat: float, long: float` | Menu + `v1/api/Vendor/{code}/profile`; source-labelled minima/statuses with warnings on conflict, delivery/packing/tax flag, no checkout quote. |
| `tapsi_vendor_reviews` | `vendor_code: str, page: int = 0, page_size: int = 20` | `Vendor/{code}/profile`; total/reviews including nested order-item comments. |
| `tapsi_product_reviews` | `product_id: int` | `RateAndReview/{id}/review`; reviews and rate detail, no invented pagination. |
| `tapsi_grocery_categories` | `lat: float, long: float` | `page-content/business-line-7` chips with content ID/filter value, not an exhaustive taxonomy. |
| `tapsi_grocery_stores` | `lat: float, long: float, page: int = 1, page_size: int = 10` | Business-line-7 vendor rows with fee/minimum/ETA; no separate market host. |
| `tapsi_grocery_search` | `query: str, lat: float, long: float, page: int = 1, page_size: int = 10` | `Search/product-search` with `businessTypeIds[0]=13`, grocery products only, no invented brand/SKU or exact cheapest claim. |

Deliberately omitted (no parity promised): cheapest-basket comparison, single-person meal rule, coupons/rewards, grocery flash deals, in-store purchase, login/cart/order/payment, and all upstream Snapp tools.

## Usage

```sh
uv run tapsi-food-mcp   # stdio MCP server
```

Typical sequence: `tapsi_find_location(query="میدان ونک")` → `tapsi_search_products(query="پیتزا", lat=…, long=…)` → `tapsi_vendor_menu(vendor_code=…)` → `tapsi_order_costs(…)` (groceries: `tapsi_grocery_search` → `tapsi_vendor_menu`).

## For AI agents

- **What:** unofficial, anonymous, read-only MCP server for Tapsi Food (api.tapsi.food) in Iran. Queries in Persian match best; prices in integer Toman.
- **Install:** not published — **do not install from PyPI or the MCP Registry**; there is no `tapsi-food-mcp` artifact there. From source: `uv run tapsi-food-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none, no API key or account.
- **Access:** read-only GETs only. No login, basket, orders or payment, so no confirmation is needed before calling any tool.
- **Output:** compact JSON. Prices in integer Toman, ratings 0-5 (`null` = not rated). Vendor `vendor_code` values pass between tools.

## Source, coverage and limitations

- Evidence: [Tapsi API findings](research/tapsi-api-findings.md) (snapshot **2026-10-14**) and raw captures in `research/samples/`. The endpoints are undocumented site behavior and can change without notice.
- Served cities observed: **Tehran (35.6892, 51.389), Mashhad (36.295289, 59.585015), Shiraz (29.67185, 52.499858)**. Isfahan/Tabriz currently yield page-content 404, empty search, but vendor menus may return 200 `OutOfCoverage` with `Unknown/-1` fee — reported as not deliverable, never orderable.
- Menu/profile minimum-basket and status may conflict (observed `2y97wk`: 400000/Open vs 300000/Close). `tapsi_order_costs` reports both with source labels and a warning; never a checkout-accurate total. The `tax` field is a boolean flag, not a tax amount.
- No coupon/reward data, market-wide taxonomy, brand/SKU equivalence, single-person meal rule, grocery flash deals or complete cheapest results are claimed; bounded comparisons are labelled incomplete.
- Throttling headers observed (`ofd-ratelimit-limit: 500`); access policy for hosted/non-Iranian IPs is unverified — use low concurrency and back off on 429.

## Development

- Deterministic unit tests with a `MockTransport` route table: `uv run pytest -q` (offline; live network never required on PRs).
- Opt-in live end-to-end tests: `uv run pytest -m live -q`. Three tests spawn the stdio MCP server and make anonymous GET calls for Tehran search/menu/reviews, Mashhad and grocery search, and unserved Isfahan. These depend on network access and mutable catalog coverage; they never run in the default suite.
- Lint: `uv run ruff check .`, `uv run ruff format --check .`.
- Release automation is **disabled** (`.github/workflows/publish.yml` is a no-op). Any future release needs a separately reviewed workflow; `server.json` carries no `packages` block until a real artifact exists.

## Provenance

Forked from [`sepehr071/snapp-mcp` at `aef14709260263df1add16dc2665ce28451c48a7`](https://github.com/sepehr071/snapp-mcp/tree/aef14709260263df1add16dc2665ce28451c48a7) (Snappfood/SnappMarket MCP). Upstream MIT copyright (Sepehr Radmard) is preserved in [`LICENSE`](LICENSE); Tapsi Food functionality here is new work in this fork and is unaffiliated with Tapsi or Snapp.

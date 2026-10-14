# Tapsi Food MCP — agent implementation task list

> **For agentic workers:** Execute this plan with independent task owners and one integration owner. This is a **plan only**; the current fork still runs the upstream Snapp MCP. Read [`research/tapsi-api-findings.md`](../../../research/tapsi-api-findings.md) and the cited [`research/samples/`](../../../research/samples/) before coding. Track each checkbox. Do not release or advertise Tapsi tools until end-to-end verified.

**Goal:** Turn the fork of [`sepehr071/snapp-mcp` at `aef14709260263df1add16dc2665ce28451c48a7`](https://github.com/sepehr071/snapp-mcp/tree/aef14709260263df1add16dc2665ce28451c48a7) into an anonymous, read-only Python MCP for Tapsi Food, preserving the recognizable stdio/registry/http/module/test structure, while replacing *all* Snapp functionality and identity in a clean cutover.

**Architecture:** Keep the existing registration pattern (`@tool` → `registry.TOOLS` → `MCPServer.add_tool` with `read_only_hint=True`), `httpx` transport injection for deterministic tests, and stdio entrypoint. Replace `snapp_mcp` with `tapsi_food_mcp`; use one anonymous GET client for `https://api.tapsi.food`, separate modules for geocoding, discovery/search, vendor detail/reviews and grocery views. Return concise normalized Toman amounts and explicit coverage/source warnings; shared parsing helpers should only exist where repeated consumers justify them.

**Tech stack:** Python >=3.10, MCP SDK `mcp>=2.2,<3`, `httpx>=0.27`, hatchling, pytest, ruff, uv (already in [`pyproject.toml`](../../../pyproject.toml)). Avoid new runtime dependencies without need. Preserve upstream MIT `LICENSE` and copyright/attribution; new project metadata can identify the fork without claiming authorship of upstream code.

**Spec/evidence:** [`research/tapsi-api-findings.md`](../../../research/tapsi-api-findings.md); source snapshots in `research/samples/`. Research is dated 2026-10-14 and describes undocumented, mutable site behavior, not guaranteed official API. Prices are **integer Toman**, search/catalog pages **1-based**, vendor-review pages **0-based**, geocode coordinates **`lng,lat`**, food catalog query coordinates **separate `latitude,longitude`**, and supported cities observed **Tehran/Mashhad/Shiraz** only. Do not forge browser cookies, signed headers or auth; minimal curl worked during research.

## Global constraints and non-goals

- Read-only GETs exclusively. Never login, add to cart, order, pay, write to a user account, or expose in-store purchase actions. `ToolAnnotations(read_only_hint=True)` for every registered tool.
- Clean cutover: migrate every caller/import/fixture/docs/entrypoint; delete Snapp-specific tools, code, aliases, re-exports, tests and release metadata. Do not keep a functioning Snapp fallback under the Tapsi name. Preserve `LICENSE` and provenance note.
- Unknown/unserved locations: geocoding a city is not catalog coverage; Isfahan/Tabriz currently yield page-content 404, empty search, but vendor menus can return 200 `OutOfCoverage` and `Unknown/-1` fee. Do not represent those as orderable.
- Menu/profile minimum-basket and status may conflict (`2y97wk`: 400000/Open vs 300000/Close). Report both values with source when relevant, favor user-facing profile only with a clear conflict warning; never claim checkout-accurate total. A boolean `tax` is not a tax amount.
- Do not invent coupon/reward data, market-wide taxonomy, brand/SKU equivalence, single-person meal rule, grocery flash deals or complete cheapest results; bounded comparison is labeled incomplete. Candidate tools are in the research doc; scope below implements evidence-backed tools only.
- Fixtures: raw captures in `research/samples/` are evidence, not permanent unit-test goldens with time-sensitive fields. Create minimal deterministic fixtures representing real consumer-visible branches. Tests must exercise behavior/edge cases, not wording, forwarding or implementation snapshots.
- Safe concurrency: no concurrent editing of shared metadata/server/registry/README/tests/conftest.py. Parallel owners may edit disjoint modules + disjoint tests after shared interfaces are settled; integration owner resolves cross-module imports and runs checks only after changes land.

## Locked implementation contract (Task 1; 2026-10-14)

The public surface is exactly **17 `tapsi_*` tools**: three location, seven discovery/search, four vendor/review, three grocery. Do not add the optional in-store clusters tool: its map is adjacent to a login-only purchasing flow and is not needed for this anonymous food catalog. All registered functions use the existing `@tool` decorator and `registry.TOOLS`; the integration owner alone edits registry/server/README/test harness/metadata. Input coordinates are distinct `lat: float, long: float`; geocode query bias uses `near_lat: float | None = None, near_long: float | None = None`. Search/list/collection pages are 1-based; review pages are 0-based. `page_size` defaults to 10 for catalog lists and 20 for reviews, bounded 1–50; page is positive except review page >=0. Fetch accepts relative paths and keyword `params` only; only anonymous GET is allowed. Money is integer Toman without conversion; absent values remain null, never inferred. Catalog outputs carry `total`, `page`, `source`, `coverage` (`available` or `unavailable`), and when relevant `items` under the specific `products`/`vendors`/`stores`/`deals` key. Coverage is about the requested location, not geocode reachability; an empty search cannot establish service alone, so report `unavailable` for an empty result and do not assert orderability. Paginated CMS `meta.totalItems` counts sections when sections are mixed, not vendors; keep `total_sections` on generic feeds. No speculative `sort` or arbitrary filters: only collection `filtersAndSorts=1-82` exposed as optional `filter_value: str | None` on an allowlisted collection. Slugs limited to `تپ-تایم`, `فودشات`, `تخفیف-فضایی`, `business-line-15`, `business-line-7` plus slugs discovered in the current feed (validated as a single path segment).

| Owner | Public tool (Python symbol is name without `tapsi_`) | Inputs beyond defaults | Read-only source and output |
|---|---|---|---|
| Location | `tapsi_find_location` | `query: str, near_lat: float | None = None, near_long: float | None = None, limit: int = 10` | `Map/geocode/forward`; `places` with name, description, center lat/long, bounds and category; bias is longitude,latitude. |
| Location | `tapsi_reverse_geocode` | `lat: float, long: float` | `Map/geocode/reverse`; address, subdivisions, certainty; location param longitude,latitude. |
| Location | `tapsi_supported_cities` | none | Static observed selector snapshot (Tehran, Mashhad, Shiraz active; Isfahan/Tabriz unserved), explicitly not exhaustive or live. |
| Discovery | `tapsi_search_products` | `query: str, lat: float, long: float, business_type_id: int | None = None, page: int = 1, page_size: int = 10` | `Search/product-search`; total/products with variation ID separate from product/header ID, vendor/fee/ETA as observed, no stock promise. |
| Discovery | `tapsi_search_vendors` | same search inputs | `Search/vendor-search`; total/vendors with code, rating/status, fee/ETA as observed. |
| Discovery | `tapsi_restaurants` | `lat: float, long: float, page: int = 1, page_size: int = 10` | `page-content/business-line-15`; typed vendor rows, observed available filters, not arbitrary filter parameters. |
| Discovery | `tapsi_discounted_vendors` | same list inputs | `page-content/فودشات`; curated vendor rows, not all discounted stores. |
| Discovery | `tapsi_flash_deals` | same list inputs | `page-content/تپ-تایم`; products, nullable discount stock and countdown; not FoodParty parity. |
| Discovery | `tapsi_discovery_feed` | `lat: float, long: float, page: int = 1` | `page-content/`; typed sections and total_sections; preserve unknown widgets. |
| Discovery | `tapsi_collection` | `slug: str, lat: float, long: float, page: int = 1, page_size: int = 10, filter_value: str | None = None` | Allowlisted/current-feed `page-content/{slug}`; config, available filters and typed sections; only observed filter `1-82`. |
| Vendor | `tapsi_vendor_menu` | `vendor_code: str, lat: float, long: float, query: str | None = None` | `v2/api/Vendor/{code}/vendor`; complete nested categories/products/variations/options/stock, coverage; optional local query filter. |
| Vendor | `tapsi_order_costs` | `vendor_code: str, lat: float, long: float` | Menu and `v1/api/Vendor/{code}/profile`; source-labelled minima/statuses and warnings on conflict, delivery/packing/tax flag, no checkout quote. |
| Vendor | `tapsi_vendor_reviews` | `vendor_code: str, page: int = 0, page_size: int = 20` | `Vendor/{code}/profile`; total/reviews including nested order-item comments. |
| Vendor | `tapsi_product_reviews` | `product_id: int` | `RateAndReview/{id}/review`; reviews and rate detail, no invented pagination. |
| Grocery | `tapsi_grocery_categories` | `lat: float, long: float` | `page-content/business-line-7` chips with content ID/filter value, not an exhaustive taxonomy. |
| Grocery | `tapsi_grocery_stores` | `lat: float, long: float, page: int = 1, page_size: int = 10` | Business-line-7 vendor rows with fee/minimum/ETA; no separate market host. |
| Grocery | `tapsi_grocery_search` | `query: str, lat: float, long: float, page: int = 1, page_size: int = 10` | `Search/product-search` with `businessTypeIds[0]=13`, grocery products only, no invented brand/SKU or exact cheapest claim. |

Omitted deliberately: Snapp cheapest comparison, meal-for-one, coupons, grocery party deals, in-store purchase, login/cart/order/payment, and all upstream Snapp tools. A 404 catalog page maps to explicit unavailable coverage; a 429 remains actionable, never silently empties a response. The integration owner resolves cross-module imports and removes the obsolete package and fixtures only after parallel tasks land.

## File ownership map and fixed interfaces

| Unit | Files to own | Interface / downstream contract |
|---|---|---|
| Identity/bootstrap | `pyproject.toml`, `server.json`, `uv.lock`, `.github/workflows/*.yml`, `src/tapsi_food_mcp/{__init__,registry,server}.py`, `README.md` | `tapsi-food-mcp = tapsi_food_mcp.server:main`; `MCPServer("tapsi-food-mcp", ...)`; same `TOOLS` registration behavior; one integration owner. |
| Anonymous HTTP | `src/tapsi_food_mcp/http.py`; `tests/test_http.py` | `API_BASE="https://api.tapsi.food"`; `ApiError(status:int|None)`; `async fetch(path:str, *, params:Mapping[str,object]|None=None)->Any` (path relative to API base), `set_transport(httpx.AsyncBaseTransport|None)` for tests. Only GET. No Snapp common params or auth. Errors distinguish 404 catalog absent and 429 throttling; do not hide actionable status. |
| Location | `src/tapsi_food_mcp/location.py`; `tests/test_location.py` | `find_location`, `reverse_geocode`, `supported_cities` consume `fetch`; coords `Lat` and `Long` typed floats, `supported_cities` documented snapshot. |
| Search/discovery | `src/tapsi_food_mcp/discovery.py`; `tests/test_discovery.py` | `search_products`, `search_vendors`, `restaurants`, `discounted_vendors`, `flash_deals`, `discovery_feed`, `collection`; results expose `meta.totalItems`, page, coverage, source slug; no unbounded all-pages scan. |
| Vendor/reviews | `src/tapsi_food_mcp/vendor.py`; `tests/test_vendor.py` | `vendor_menu`, `order_costs`, `vendor_reviews`, `product_reviews`; vendor code + coordinates for menu/costs, 0-based review page. See actual nested `data.categories[].products[].productVariations[]` and `data.insight.reviews[].orderItems[]`. |
| Grocery views | `src/tapsi_food_mcp/grocery.py`; `tests/test_grocery.py` | `grocery_categories`, `grocery_stores`, `grocery_search` compose discovery/search and vendor endpoints; business line 7, search businessTypeIds[0]=13; no distinct market auth/host. Optional product/store info can reuse `vendor_menu`/`product_reviews`, not duplicate transport. |
| Integration/acceptance | `tests/conftest.py`, `tests/test_server.py`, optional `tests/test_live_tapsi.py`, `README.md`, `.github/*`; integration owner | One stdio MCP invocation, all registered read-only tools and no Snapp tools/metadata; live smoke manual/opt-in only, no network in default suite. |

**Boundary convention:** Accept user-facing `lat,long` consistently; an internal helper encodes geocoder `lng,lat`. Currency stays Toman throughout. `fetch` returns decoded JSON without silently changing envelope; each tool normalizes its own response. A menu `productId` is not the search `id`/`productVariationId`, and no global SKU key exists. `page_size` limits are local safety bounds, not proven backend maximums. Exact public tool names should be fixed in Task 1 (prefer the `tapsi_*` names in the research proposal or project-wide unprefixed names, **not both**), then used consistently in tests/docs.

## Review focus — consumer failure modes to pin to owning tasks

1. Swapped coordinate order or wrong city → Task 3 geocode and Task 4 search tests use distinct lat/lng, plus Task 7 cross-city smoke.
2. Empty 200 search or full 200 out-of-coverage menu presented as available → Task 4/5/6 coverage tests.
3. Disagreeing menu/profile minimum basket or negative delivery fee → Task 5 discrepancy test preserves source fields/warning; no fabricated total.
4. Pagination off by one, totalItems counting CMS sections rather than vendors, or filters silently ignored → Task 4/6 tests for p1/p2 and mixed widget pages.
5. Stock, volatile discount, no brand or unidentifiable equivalent product → Task 5/6 tests for sold-out variation, nullable values and explicitly bounded comparisons.

## Tasks and dependencies

### Task 1 — Lock public API and migration boundary (integration owner; prerequisite)

**Files:** This plan and `research/tapsi-api-findings.md` (only if evidence corrections); no code yet.

- [ ] Confirm 17 evidence-backed proposed tools from the research document (location 3; search/list/discovery 7; vendor/review 4; grocery 3) and decide whether `tapsi_instore_clusters` is an optional 18th **read-only map-only** tool. The list count must be reconciled against exact tool table before coding; do not copy all 21 Snapp names for symmetry.
- [ ] Fix exported name scheme (`tapsi_*` vs unprefixed), input shapes, bounds, paginated output `total`, `page`, `source`, and availability representation in a brief contract at top of `README.md` or this plan. Ensure contract matches source evidence, especially `supported_cities` is a snapshot and `food_find_cheapest`/market deals are not exact parity.
- [ ] Define task-owner boundaries using the file map above; communicate `http.fetch` signature and the choice of registry decorator to all owners before parallel work. No code generation/scaffolding yet.

**Acceptance:** One named contract; every selected tool has an owner, endpoint/source, input and output; omitted parity tools are explicitly marked partial/unobserved rather than fake stubs.

### Task 2 — Package/registry/transport cutover (integration owner; prerequisite for parallel modules)

**Files:** Move `src/snapp_mcp/{__init__,registry,server,http}.py` to `src/tapsi_food_mcp/` with appropriate content; edit `pyproject.toml`, `server.json`, `.github/workflows/{ci,publish}.yml`, `uv.lock`, `tests/conftest.py`; create `tests/test_http.py`, `tests/test_server.py`. Remove obsolete Snapp tests/fixtures when moving the package, then remove obsolete Snapp source paths once all imports have migrated.

- [ ] Before moving imports, migrate `tests/conftest.py` to inject `tapsi_food_mcp.http.set_transport` and remove or quarantine all Snapp-only tests/fixtures (including live tests) from default collection; they must not execute or import the obsolete package during parallel module work. Keep the new transport tests runnable in isolation throughout the wave. Task 7 owns the final whole-tree deletion/check.
- [ ] First write failing tests for anonymous `fetch` (GET URL/params with percent-encoded Persian and brackets, 404, 429, invalid JSON, timeout), read-only annotation on every tool and absence of Snapp tools after full integration. Use `httpx.MockTransport`/the existing `set_transport` seam. Tests should check public behavior rather than cosmetic metadata text.
- [ ] Implement one shared async httpx client/semaphore with modest concurrency and timeout; no Snapp PWA params, `svc.snapp.market`, bearer minting, fake cookies or retry loops on arbitrary errors. Treat 429 visibly (bounded backoff only if empirically needed). Carry through status in `ApiError`.
- [ ] Rename package/project/script/server identity and provenance carefully; `__version__` uses new distribution name. **Disable the existing tag-triggered `.github/workflows/publish.yml` before any branch/tag exposure during migration**, including its PyPI and MCP Registry jobs; the current workflow still waits for `snapp-mcp`. Do **not** publish a package/registry entry during this task. `server.json` must not claim a PyPI identifier/version that does not exist yet—keep unpublished package metadata out of publication until release. Any later release requires a separately reviewed workflow with package lookup and manifest identifier/version checked against the actual artifact. Preserve upstream MIT copyright in `LICENSE`; update URLs/CI workflow references and opt-in live marker.
- [ ] Use registry's import-side-effect registration for all new modules when they exist; central server instructions must describe only Tapsi, Toman units and supported-city caveat. During migration, avoid exposing a half-Snapp, half-Tapsi runnable server; land cohesive cutover only when Tasks 3–6 are integrated.

**Acceptance:** Local deterministic transport tests pass for new module; final registered tool inventory is Tapsi-only/read-only. No stale `snapp_mcp` imports in source/tests/metadata after Task 7 cleanup.

### Task 3 — Location and supported-city snapshot (parallel owner after Task 2 contract)

**Files:** Create `src/tapsi_food_mcp/location.py`; replace `tests/test_location.py` and location fixtures with minimal captured-shape fixtures from `research/samples/location-{forward,reverse}.json`.

- [ ] Tests first: `find_location("مشهد", near_lat=35.6892, near_long=51.389)` sends `district=51.389,35.6892` and returns city/street results without treating search bias as service filter; reverse with same point sends `location=51.389,35.6892` and maps nested subdivisions/certainty.
- [ ] Expose only three actively served snapshot cities (Tehran `35.6892,51.389`; Mashhad `36.295289,59.585015`; Shiraz `29.67185,52.499858`) with observed date/source; Isfahan/Tabriz may be listed as unserved only if contract explicitly says so. Do not call unobserved city-list endpoint.
- [ ] Validate latitude/longitude bounds and preserve Unicode titles, nullable/bounds/category fields. Throw on failed API envelope; do not infer serviceability from geocode success.

**Acceptance:** Location tool tests exercise lng/lat order, mixed-category results and supported snapshot provenance.

### Task 4 — Search and CMS discovery (parallel owner after Task 2 contract)

**Files:** Create `src/tapsi_food_mcp/discovery.py`, `tests/test_discovery.py`, compact fixtures derived from `food-search.json`, `vendor-list.json`, `tapsi-page-content-p*.json`, `tapsi-product-collection-taptime.json`, `verification-isfahan.json`.

- [ ] Tests first for dedicated `Search/product-search` and `Search/vendor-search`, `Search/facets`, `Search/aggregated-search` where useful; verify `pageNumber=1` then 2, `businessTypeIds[0]` encoding, product variation `id` vs `headerId`, `null` rating and stable output even when suggestions are empty.
- [ ] Build bounded `restaurants` from `page-content/business-line-15`, discounted vendors from `/فودشات`, flash products from `/تپ-تایم`, plus generic `discovery_feed` and `collection` if included in Task 1. Parse `content[]` discriminator: `type:0` widget versus `type:1/2` feed row; `meta.totalItems` counts mixed sections in some pages. Do not fetch all pages to answer one page.
- [ ] Tests for unserved city: page-content 404 and `Search` 200+empty must return explicit unavailable/empty rather than a false restaurant list. For a served city, carry only fields actually observed (`deliveryPrice`, `eta`, `vendorStatus`, `discountStock` optional). Slugs derive from observed feed/allowlist; user input must not turn into arbitrary host URL.
- [ ] Only implement filter encoding actually verified (`filtersAndSorts=1-82` on collection); either exercise sort/toggle UI/network first in an isolated research task or leave those optional filters out of the published schema. Document unknown widget types without crashing the full page.

**Acceptance:** Tests prove distinct search pagination, CMS mixed page interpretation, location coverage and deal stock; a smoke script prints Tehran pizza results and a deal row from actual GET endpoints.

### Task 5 — Vendor menu, costs, vendor and product reviews (parallel owner after Task 2 contract)

**Files:** Create `src/tapsi_food_mcp/vendor.py`, `tests/test_vendor.py`, compact fixtures derived from `vendor-detail.json`, `reviews.json`, `grocery-product-1867178-review.json`, `verification-vendor-tehran.json`.

- [ ] Tests first for `GET /v2/api/Vendor/{code}/vendor?latitude&longitude` mapping `data.categories[].products[].productVariations[]`: sold-out stock=0, nullable image/rating, option category IDs, integer Toman, fee/packing/tax fields. Validate code before interpolating URL and map `OutOfCoverage`/`Unknown:-1` to not-deliverable.
- [ ] Tests for `GET /v1/api/Vendor/{code}/profile?pageSize=20&pageNumber=0`: `data.info`, `data.shift`, `data.insight.reviews[].orderItems[].comment`, meta total, 0-based next page. Product reviews use `GET /v1/api/RateAndReview/{productId}/review`, no invented pagination; test zero-review and nonempty sample.
- [ ] `order_costs` obtains menu plus profile only where needed, surfaces both minimums and statuses on disagreement with `source_warnings` and no fabricated coupon/tax total; handle profile failure without disguising menu coverage, and avoid fetching menu twice for `vendor_menu` call.

**Acceptance:** Tests prove 200 `OutOfCoverage` is never marked available, discrepancy visible, reviews nested correctly, Toman unchanged; smoke one local vendor menu and vendor profile/review.

### Task 6 — Grocery composition (parallel owner after Tasks 4–5 public functions are fixed)

**Files:** Create `src/tapsi_food_mcp/grocery.py`, `tests/test_grocery.py`; reuse Task 4/5 interfaces, no independent HTTP convention or token mechanism.

- [ ] Tests first: `business-line-7` yields category chip `payload.contentId` and `filterValue` (do not invent taxonomy tree), grocery vendors carry fee/minimum/ETA, `Search/product-search?businessTypeIds[0]=13&query=شیر` isolates grocery product instead of including milkshakes from other business types.
- [ ] Implement `grocery_categories`, `grocery_stores`, `grocery_search` via existing discovery tools/transport. A store's details/products reuse `vendor_menu`; product reviews reuse `product_reviews`. For 0-stock menu variation, show unavailable; search responses lack stock/brand, so expose null/unknown rather than false stock or inferred brand.
- [ ] No dedicated `market_find_cheapest` until same-product equivalence and completeness are solved. If Task 1 explicitly selects a bounded comparison, label `results_scanned`, page bounds, unverified SKU equivalence, minimum-basket caveat; do not present it as an exact purchasable price.

**Acceptance:** Grocery filter and stock behavior tested; consumers can list grocery stores, search grocery products and inspect a real store via vendor detail without SnappMarket auth.

### Task 7 — Whole-tree cleanup, tests, docs and release guard (integration owner; after Tasks 3–6)

**Files:** `src/`, `tests/fixtures/`, `tests/{conftest,test_live_food,test_live_market}.py`, `README.md`, `pyproject.toml`, `server.json`, `uv.lock`, `.github/workflows/*.yml`, `.github/ISSUE_TEMPLATE/*`, `.github/banner.png` if used.

- [ ] Delete remaining upstream Snapp modules, OAuth/device token cache, FoodParty/Gem/SnappMarket helper paths and all obsolete Snapp fixtures/tests—including wording/incidental tests—rather than re-pinning them. Preserve `LICENSE` and a clear fork credit. No `snappfood.ir`, `snapp.market`, `SNAPP_MCP_PROXY`, `snapp_mcp` or old command in active product/docs/workflows; historical research links to reference repo stay.
- [ ] Replace README's badges, quick starts, example outputs, tool inventory, supported cities, deployment/geo limitations and attribution. This fork's publication status must be truthful; do not show PyPI or MCP Registry badges/deeplinks for an unpublished Tapsi package. Update `server.json` package info only when corresponding artifact exists; do not publish as part of research-to-code migration.
- [ ] One independent code review pass for security, read-only guarantees, request amplification, per-city availability and HTTP error handling; reconcile findings. Run `uv sync --group dev`, `uv run pytest`, `uv run ruff check .` once integrated; update lockfile via normal tooling. Default suite offline; opt-in live suite exercises *only* safe Tapsi GETs at Tehran and at least one other served city, plus an unserved-city expectation.
- [ ] Smoke actual MCP stdio server (`uv run tapsi-food-mcp`) with an MCP client that lists tools, asserts the **exact selected Task 1 inventory** (all named tools present, no extras/write/Snapp tools), then invokes the chosen public names for location search, pizza search, vendor menu, reviews and grocery search through stdio. Exercise 404/out-of-coverage explicitly; note live data may change and avoid burst traffic. CI runs deterministic suite; no live network requirement on PRs.

**Acceptance:** Entire source/tests/docs/release metadata consistently Tapsi-only; deterministic tests/lint and real MCP client smoke observed; no misleading working/released claims. Log verified checks and known limitations in README. Keep research samples as evidence and document their capture date.

## Agent handoff/order

1. **Integration owner:** Task 1 contract, Task 2 shared core; keep all metadata/server edits exclusive. Stop before claiming a runnable server if feature modules are not landed.
2. **Parallel wave:** Task 3 location, Task 4 discovery/search and Task 5 vendor/reviews in separate files/test files. Each agent gets this plan, research doc, exact interface contract and a prohibition on mid-flight full-suite/build/lint/formatting.
3. **Dependent wave:** Task 6 grocery after Task 4/5 interfaces stabilize. Agents can communicate narrow API signatures, not edit each other's files. If optional map-cluster tool was chosen, a small separate owner can add it under discovery after contract selection.
4. **Integration owner:** Task 7 cutover, deletion of Snapp behavior and docs/test migration, then one consolidated verification/review/smoke. Do not merge partly working phases into the advertised default branch.

## Outstanding research before promising extra features

- Exact sort/toggle filter request syntax and combination precedence, product-review pagination, rate-limit reset window, real hosted-IP access policy, whether active-city selector has a hidden authoritative API, and Tapsi Terms of Service for automation/redistribution.
- Whether any anonymous read-only coupon feed, grocery flash-deal feed or real single-person-free-delivery rule exists; do not create placeholders while this is unknown.
- Checkout-accurate delivery/packing/minimum when menu and profile disagree; no order/cart APIs should be used merely to resolve a read-only MCP planning question.

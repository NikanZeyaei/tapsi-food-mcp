"""Search and CMS discovery tools (Task 4).

Dedicated ``Search/product-search`` and ``Search/vendor-search`` plus the
``page-content`` CMS family (restaurant hub, discount/ flash collections,
homepage feed and slug-addressed collections). All calls are anonymous GETs
with explicit ``latitude``/``longitude``; search/list/collection pages are
1-based. Exactly one page is fetched per call (no all-pages scanning).

Observed evidence (research/samples, 2026-10-14):
- Dedicated search responses use ``data[]`` with ``meta:{pageSize,pageNumber,
  totalItems}``; the aggregate ``food-search`` shape is aggregate-only and is
  not used here. ``businessTypeIds[0]=13`` isolates grocery products.
- CMS responses come in two shapes: newer ``{meta,config,content[]}`` where
  ``content[].type`` discriminates 0 widget / 1 vendor / 2 product, and the
  older ``{meta,config,filters,feeds[]}`` (vendor-list captures) where
  ``feeds[]`` holds bare vendor or product rows.
- ``meta.totalItems`` counts the catalog behind the page (e.g. 192 hub
  vendors, 23 home sections), never the returned rows; it is reported
  verbatim, not recomputed from sections.
- Unserved points (Isfahan/Tabriz) yield page-content 404 or a first page
  200 with ``data:[]``/``totalItems:0``; both map to ``coverage="unavailable"``
  with a ``coverage_reason``. An empty page with ``meta.totalItems > 0`` is
  past-the-end exhaustion: ``coverage`` stays ``"available"``, ``total`` is
  preserved and a ``page_note`` says to request a lower page. A 429 stays
  actionable and propagates.
"""

from __future__ import annotations

import math
from typing import Any

from .http import ApiError, fetch
from .registry import tool

_PRODUCT_SEARCH_PATH = "/v1/api/search-discovery/Search/product-search"
_VENDOR_SEARCH_PATH = "/v1/api/search-discovery/Search/vendor-search"
_FEED_PATH = "/v1/api/search-discovery/page-content/"
_RESTAURANTS_SLUG = "business-line-15"
_DISCOUNTED_SLUG = "فودشات"
_FLASH_SLUG = "تپ-تایم"

_PRODUCT_SEARCH_SOURCE = "Search/product-search"
_VENDOR_SEARCH_SOURCE = "Search/vendor-search"
_FEED_SOURCE = "page-content/"

# Single segment of _FEED_PATH is the CMS slug; sources below name it.
_RESTAURANTS_SOURCE = f"page-content/{_RESTAURANTS_SLUG}"
_DISCOUNTED_SOURCE = f"page-content/{_DISCOUNTED_SLUG}"
_FLASH_SOURCE = f"page-content/{_FLASH_SLUG}"

# Slugs observed in feeds/captures on 2026-10-14. `collection` serves only
# these; anything else is rejected before any fetch so caller input cannot
# become an arbitrary CMS URL.
KNOWN_SLUGS = frozenset(
    {
        "business-line-6",
        "business-line-7",
        "business-line-8",
        "business-line-9",
        "business-line-10",
        "business-line-11",
        "business-line-12",
        "business-line-13",
        "business-line-14",
        "business-line-15",
        "business-line-16",
        "business-line-17",
        "فودشات",
        "تپ-تایم",
        "تخفیف-فضایی",
        "خنک-بار",
        "کافه-بار",
        "رستوران-های-با-بالاترین-امتیاز",
        "بهترین-های-آجیل-با-بیشترین-تخفیف-ها",
        "بهترین-های-خواربار-با-بیشترین-تخفیف-ها",
        "بهترین-های-شیرینی-با-بیشترین-تخفیف-ها",
        "بهترین-های-میوه-با-بیشترین-تخفیف-ها",
        "بهترین-های-پروتئین-با-بیشترین-تخفیف-ها",
        "بهترین-های-کافه-و-آبمیوه-بستنی-با-بیشترین-تخفیف-ها",
        "تپ-تایم-بیزنس-لاین-آبمیوه-بستنی",
        "تپ-تایم-بیزنس-لاین-آجیل",
        "تپ-تایم-بیزنس-لاین-شیرینی",
        "تپ-تایم-بیزنس-لاین-قهوه-و-شکلات",
        "تپ-تایم-بیزنس-لاین-میوه",
        "تپ-تایم-بیزنس-لاین-پروتئین",
        "تپ-تایم-بیزنس-لاین-کافه",
        "تپ-تایم-سبزیجات-با-کوپن-تخفیف",
        "تپ-تایم-شیرینی-تر-بنر",
        "تپ-تایم-شیرینی-خشک-بنر",
        "تپ-تایم-میوه-با-کوپن-تخفیف",
        "تپ-تایم-گوشت-سفید-با-کوپن-تخفیف",
        "تپ-تایم-گوشت-قرمز-با-کوپن-تخفیف",
        "تپ‌_تایم-از-پیتزا-تا-برگر",
        "تپ‌تایم-لذت-کباب-و-پلو",
    }
)

# Only collection filter encoding exercised end-to-end (تپ‌تایم category
# chips such as کباب change totalItems 166 -> 61). Nothing else is sent.
OBSERVED_FILTERS = frozenset({"1-82"})


def _require_coords(lat: float, long: float) -> None:
    for label, value in (("lat", lat), ("long", long)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ApiError(f"{label} must be a number, got {value!r}.")
        number = float(value)
        if not math.isfinite(number):
            raise ApiError(f"{label} must be finite, got {value!r}.")
    if not -90.0 <= float(lat) <= 90.0:
        raise ApiError(f"lat out of range: {lat!r}.")
    if not -180.0 <= float(long) <= 180.0:
        raise ApiError(f"long out of range: {long!r}.")


def _require_paging(page: int, page_size: int) -> None:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ApiError(f"page must be a positive integer (1-based), got {page!r}.")
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise ApiError(f"page_size must be an integer between 1 and 50, got {page_size!r}.")
    if not 1 <= page_size <= 50:
        raise ApiError(f"page_size must be an integer between 1 and 50, got {page_size!r}.")


def _require_query(query: str) -> str:
    text = query.strip() if isinstance(query, str) else ""
    if not text:
        raise ApiError("query must be a non-empty string.")
    return text


def _require_business_type(business_type_id: int | None) -> int | None:
    if business_type_id is None:
        return None
    if isinstance(business_type_id, bool) or not isinstance(business_type_id, int):
        raise ApiError(f"business_type_id must be a positive integer, got {business_type_id!r}.")
    if business_type_id <= 0:
        raise ApiError(f"business_type_id must be a positive integer, got {business_type_id!r}.")
    return business_type_id


def _require_slug(slug: str) -> str:
    text = slug.strip() if isinstance(slug, str) else ""
    if not text or text in (".", "..") or ".." in text:
        raise ApiError(f"slug must be a single CMS path segment, got {slug!r}.")
    if any(c in text for c in ("/", "\\", "%")):
        raise ApiError(f"slug must be a single CMS path segment, got {slug!r}.")
    if text not in KNOWN_SLUGS:
        raise ApiError(
            f"unknown collection slug {text!r}; only slugs observed in the "
            "feed/captures are served, e.g. 'business-line-15', 'فودشات', 'تپ-تایم'."
        )
    return text


def _money(value: Any) -> int | None:
    """Normalize a Toman amount to int; None/bool/unparseable stay null."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            try:
                number = float(value.strip())
            except ValueError:
                return None
            return int(number) if math.isfinite(number) and number.is_integer() else None
    return None


def _norm_search_product(item: dict[str, Any]) -> dict[str, Any]:
    info = item.get("productInfo") or {}
    vendor = item.get("vendorInfo") or {}
    variation = item.get("id") or info.get("id")
    return {
        "variation_id": str(variation) if variation is not None else None,
        "product_id": info.get("headerId"),
        "name": info.get("name"),
        "price": _money(info.get("price")),
        "final_price": _money(info.get("priceAfterDiscount")),
        "discount_ratio": info.get("discountRatio"),
        "rate": info.get("rate"),
        "rates_count": info.get("ratesCount"),
        "vendor": vendor.get("title"),
        "vendor_code": vendor.get("vendorCode"),
        "vendor_open": vendor.get("vendorStatus"),
        "delivery_fee": _money(vendor.get("deliveryPrice")),
        "delivery_type": vendor.get("deliveryType"),
        "eta": vendor.get("eta"),
        # Search carries no per-variation stock; never promise availability.
        "stock": None,
    }


def _norm_search_vendor(item: dict[str, Any]) -> dict[str, Any]:
    info = item.get("vendorInfo") or {}
    return {
        "code": item.get("vendorCode"),
        "title": info.get("title"),
        "rating": info.get("rate"),
        "ratings_count": info.get("ratesCount"),
        "open": info.get("isOpen"),
        "eta": info.get("eta"),
        "delivery_fee": _money(info.get("deliveryPrice")),
        "delivery_type": info.get("deliveryType"),
    }


def _norm_cms_vendor(row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("vendorStatus")
    return {
        "code": row.get("vendorCode"),
        "title": row.get("title"),
        "status": status,
        "open": status == "Open",
        "discount": row.get("discount"),
        "delivery_fee": _money(row.get("deliveryPrice")),
        "delivery_type": row.get("deliveryType"),
        "minimum_basket": _money(row.get("minimumBasket")),
        "eta": row.get("eta"),
        "rate": row.get("rate"),
        "rates_count": row.get("ratesCount"),
        "is_new": row.get("isNewVendor"),
    }


def _norm_cms_product(row: dict[str, Any]) -> dict[str, Any]:
    variation = row.get("productVariationId") or row.get("productId")
    return {
        "variation_id": str(variation) if variation is not None else None,
        "product_id": row.get("headerId"),
        "name": row.get("productName"),
        "price": _money(row.get("price")),
        "final_price": _money(row.get("priceAfterDiscount")),
        "discount_ratio": row.get("discountRatio"),
        "discount_stock": row.get("discountStock"),
        "rate": row.get("productRate"),
        "vendor": row.get("vendorName"),
        "vendor_code": row.get("vendorCode"),
        "vendor_status": row.get("vendorStatus"),
        "delivery_fee": _money(row.get("deliveryPrice")),
        "delivery_type": row.get("deliveryType"),
    }


def _norm_filter_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": item.get("key"),
        "name": item.get("name"),
        "type": item.get("type"),
        "role": item.get("role"),
        "options": [
            {"key": o.get("key"), "name": o.get("name"), "active": o.get("active")}
            for o in item.get("options") or []
            if isinstance(o, dict)
        ],
    }


def _cms_entries(body: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a CMS body into uniform content entries plus top-level filters.

    Newer captures use ``content[]`` with ``type`` 0/1/2; older captures use
    ``feeds[]`` of bare vendor/product rows, which are wrapped so downstream
    code only handles one shape.
    """
    if isinstance(body, dict) and isinstance(body.get("content"), list):
        entries = [e for e in body["content"] if isinstance(e, dict)]
        return entries, []
    if isinstance(body, dict) and isinstance(body.get("feeds"), list):
        entries = []
        for row in body["feeds"]:
            if not isinstance(row, dict):
                continue
            if row.get("productName") is not None or row.get("productVariationId") is not None:
                entries.append({"type": 2, "component": None, "defaultFeedContent": row})
            elif row.get("vendorCode") is not None:
                entries.append({"type": 1, "component": None, "defaultFeedContent": row})
        top = body.get("filters") if isinstance(body.get("filters"), list) else []
        return entries, [f for f in top if isinstance(f, dict)]
    top = body.get("filters") if isinstance(body, dict) and isinstance(body.get("filters"), list) else []
    return [], [f for f in top if isinstance(f, dict)]


def _cms_meta(body: Any, page: int, page_size: int, fallback_total: int) -> tuple[int, int, int]:
    meta = body.get("meta") if isinstance(body, dict) and isinstance(body.get("meta"), dict) else {}
    total = meta.get("totalItems")
    return (
        total if isinstance(total, int) else fallback_total,
        meta.get("pageNumber") if isinstance(meta.get("pageNumber"), int) else page,
        meta.get("pageSize") if isinstance(meta.get("pageSize"), int) else page_size,
    )


def _collect_filters(entries: list[dict[str, Any]], top_filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group in top_filters:
        if group.get("componentType") == 1025:
            for item in group.get("items") or []:
                if isinstance(item, dict):
                    out.append(_norm_filter_item(item))
    for entry in entries:
        component = entry.get("component") or {}
        if entry.get("type") == 0 and component.get("type") == 1025:
            for item in component.get("items") or []:
                if isinstance(item, dict):
                    out.append(_norm_filter_item(item))
    return out


def _collect_widgets(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Type-0 sections, verbatim items; unknown component types preserved."""
    widgets = []
    for entry in entries:
        if entry.get("type") != 0:
            continue
        component = entry.get("component") or {}
        meta = component.get("componentMeta") or {}
        options = meta.get("options") or {}
        items = component.get("items")
        widgets.append(
            {
                "component_type": component.get("type"),
                "title": meta.get("title"),
                "items": items if isinstance(items, list) else [],
                "options": options if isinstance(options, dict) else {},
                "more": options.get("viewMoreUrlOrSlug") if isinstance(options, dict) else None,
            }
        )
    return widgets


def _collect_rows(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    vendors: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    for entry in entries:
        content = entry.get("defaultFeedContent")
        if not isinstance(content, dict):
            continue
        if entry.get("type") == 1:
            vendors.append(_norm_cms_vendor(content))
        elif entry.get("type") == 2:
            products.append(_norm_cms_product(content))
    return vendors, products


def _countdown(entries: list[dict[str, Any]]) -> str | None:
    for entry in entries:
        options = ((entry.get("component") or {}).get("componentMeta") or {}).get("options") or {}
        if options.get("countdownEndsAt") is not None:
            return options.get("countdownEndsAt")
    return None


def _empty_search_reason(point: str) -> str:
    return (
        f"HTTP 200 with zero rows and meta.totalItems=0 for this {point}; the point "
        "may be unserved (Isfahan/Tabriz return empty search) or the query may "
        "simply have no matches."
    )


def _beyond_end_note(page: int, total: int) -> str:
    return (
        f"HTTP 200 with zero rows on page {page} while meta.totalItems={total}: "
        "the page is past the end of the results, not an unserved location; "
        "request a lower page number."
    )


@tool("Search food products")
async def search_products(
    query: str,
    lat: float,
    long: float,
    business_type_id: int | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """Dedicated product search at a delivery point (1-based page).

    ``business_type_id`` is sent as ``businessTypeIds[0]`` (13 isolates
    grocery products). Variation ``variation_id`` is kept apart from the
    header ``product_id``; ratings are nullable and stock is always null
    because search promises none. 404 maps to unavailable coverage, as does
    a first page with ``meta.totalItems=0`` (unserved point or no matches);
    an empty page with ``meta.totalItems>0`` is past-the-end exhaustion with
    ``total`` preserved and coverage still ``"available"``. 429 propagates.
    """
    text = _require_query(query)
    _require_coords(lat, long)
    _require_paging(page, page_size)
    business_type = _require_business_type(business_type_id)
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": long,
        "pageNumber": page,
        "pageSize": page_size,
        "query": text,
    }
    if business_type is not None:
        params["businessTypeIds[0]"] = business_type
    try:
        body = await fetch(_PRODUCT_SEARCH_PATH, params=params)
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "query": text,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "products": [],
            "coverage": "unavailable",
            "coverage_reason": str(e),
            "source": _PRODUCT_SEARCH_SOURCE,
        }
    data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
    products = [_norm_search_product(item) for item in data if isinstance(item, dict)]
    meta = body.get("meta") if isinstance(body, dict) and isinstance(body.get("meta"), dict) else {}
    total = meta.get("totalItems") if isinstance(meta.get("totalItems"), int) else len(products)
    current_page = meta.get("pageNumber") if isinstance(meta.get("pageNumber"), int) else page
    current_size = meta.get("pageSize") if isinstance(meta.get("pageSize"), int) else page_size
    if not products and total > 0:
        return {
            "query": text,
            "total": total,
            "page": current_page,
            "page_size": current_size,
            "products": [],
            "coverage": "available",
            "page_note": _beyond_end_note(current_page, total),
            "source": _PRODUCT_SEARCH_SOURCE,
        }
    if not products:
        return {
            "query": text,
            "total": 0,
            "page": current_page,
            "page_size": current_size,
            "products": [],
            "coverage": "unavailable",
            "coverage_reason": _empty_search_reason("query/point"),
            "source": _PRODUCT_SEARCH_SOURCE,
        }
    return {
        "query": text,
        "total": total,
        "page": current_page,
        "page_size": current_size,
        "products": products,
        "coverage": "available",
        "source": _PRODUCT_SEARCH_SOURCE,
    }


@tool("Search vendors")
async def search_vendors(
    query: str,
    lat: float,
    long: float,
    business_type_id: int | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """Dedicated vendor search at a delivery point (1-based page)."""
    text = _require_query(query)
    _require_coords(lat, long)
    _require_paging(page, page_size)
    business_type = _require_business_type(business_type_id)
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": long,
        "pageNumber": page,
        "pageSize": page_size,
        "query": text,
    }
    if business_type is not None:
        params["businessTypeIds[0]"] = business_type
    try:
        body = await fetch(_VENDOR_SEARCH_PATH, params=params)
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "query": text,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "vendors": [],
            "coverage": "unavailable",
            "coverage_reason": str(e),
            "source": _VENDOR_SEARCH_SOURCE,
        }
    data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
    vendors = [_norm_search_vendor(item) for item in data if isinstance(item, dict)]
    meta = body.get("meta") if isinstance(body, dict) and isinstance(body.get("meta"), dict) else {}
    total = meta.get("totalItems") if isinstance(meta.get("totalItems"), int) else len(vendors)
    current_page = meta.get("pageNumber") if isinstance(meta.get("pageNumber"), int) else page
    current_size = meta.get("pageSize") if isinstance(meta.get("pageSize"), int) else page_size
    if not vendors and total > 0:
        return {
            "query": text,
            "total": total,
            "page": current_page,
            "page_size": current_size,
            "vendors": [],
            "coverage": "available",
            "page_note": _beyond_end_note(current_page, total),
            "source": _VENDOR_SEARCH_SOURCE,
        }
    if not vendors:
        return {
            "query": text,
            "total": 0,
            "page": current_page,
            "page_size": current_size,
            "vendors": [],
            "coverage": "unavailable",
            "coverage_reason": _empty_search_reason("query/point"),
            "source": _VENDOR_SEARCH_SOURCE,
        }
    return {
        "query": text,
        "total": total,
        "page": current_page,
        "page_size": current_size,
        "vendors": vendors,
        "coverage": "available",
        "source": _VENDOR_SEARCH_SOURCE,
    }


async def _vendor_list(path: str, source: str, lat: float, long: float, page: int, page_size: int) -> dict:
    _require_coords(lat, long)
    _require_paging(page, page_size)
    try:
        body = await fetch(
            path,
            params={
                "latitude": lat,
                "longitude": long,
                "bypassCache": False,
                "pageNumber": page,
                "pageSize": page_size,
            },
        )
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "vendors": [],
            "widgets": [],
            "available_filters": [],
            "coverage": "unavailable",
            "coverage_reason": str(e),
            "source": source,
        }
    entries, top_filters = _cms_entries(body)
    vendors, _ = _collect_rows(entries)
    total, current_page, current_size = _cms_meta(body, page, page_size, len(vendors))
    if not vendors and total > 0:
        return {
            "total": total,
            "page": current_page,
            "page_size": current_size,
            "vendors": [],
            "widgets": _collect_widgets(entries),
            "available_filters": _collect_filters(entries, top_filters),
            "coverage": "available",
            "page_note": _beyond_end_note(current_page, total),
            "source": source,
        }
    if not vendors:
        return {
            "total": 0,
            "page": current_page,
            "page_size": current_size,
            "vendors": [],
            "widgets": _collect_widgets(entries),
            "available_filters": _collect_filters(entries, top_filters),
            "coverage": "unavailable",
            "coverage_reason": (
                "HTTP 200 with zero vendor rows and meta.totalItems=0 for this point; "
                "the point may be unserved (unserved cities 404 or return empty CMS pages)."
            ),
            "source": source,
        }
    return {
        "total": total,
        "page": current_page,
        "page_size": current_size,
        "vendors": vendors,
        "widgets": _collect_widgets(entries),
        "available_filters": _collect_filters(entries, top_filters),
        "coverage": "available",
        "source": source,
    }


@tool("Restaurant hub vendor list")
async def restaurants(lat: float, long: float, page: int = 1, page_size: int = 10) -> dict:
    """Restaurant hub (``page-content/business-line-15``) vendor rows.

    ``total`` is the hub's ``meta.totalItems``, not the returned rows.
    Filter/sort UI is reported in ``available_filters``; only observed
    encodings are ever sent, so no filter input is accepted here.
    """
    return await _vendor_list(f"{_FEED_PATH}{_RESTAURANTS_SLUG}", _RESTAURANTS_SOURCE, lat, long, page, page_size)


@tool("Curated discounted vendors")
async def discounted_vendors(lat: float, long: float, page: int = 1, page_size: int = 10) -> dict:
    """Curated discounted-vendor collection (``page-content/فودشات``).

    A curated source, not an exhaustive list of every discounted store.
    """
    return await _vendor_list(f"{_FEED_PATH}{_DISCOUNTED_SLUG}", _DISCOUNTED_SOURCE, lat, long, page, page_size)


@tool("Flash-sale products")
async def flash_deals(lat: float, long: float, page: int = 1, page_size: int = 10) -> dict:
    """Flash-sale products (``page-content/تپ-تایم``) with countdown.

    ``discount_stock`` is nullable and volatile; it is reported, never used
    to promise orderability. Not FoodParty parity.
    """
    _require_coords(lat, long)
    _require_paging(page, page_size)
    try:
        body = await fetch(
            f"{_FEED_PATH}{_FLASH_SLUG}",
            params={
                "latitude": lat,
                "longitude": long,
                "bypassCache": False,
                "pageNumber": page,
                "pageSize": page_size,
            },
        )
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "deals": [],
            "countdown": None,
            "available_filters": [],
            "coverage": "unavailable",
            "coverage_reason": str(e),
            "source": _FLASH_SOURCE,
        }
    entries, top_filters = _cms_entries(body)
    _, products = _collect_rows(entries)
    total, current_page, current_size = _cms_meta(body, page, page_size, len(products))
    countdown = _countdown(entries)
    if not products and total > 0:
        return {
            "total": total,
            "page": current_page,
            "page_size": current_size,
            "deals": [],
            "countdown": countdown,
            "available_filters": _collect_filters(entries, top_filters),
            "coverage": "available",
            "page_note": _beyond_end_note(current_page, total),
            "source": _FLASH_SOURCE,
        }
    if not products:
        return {
            "total": 0,
            "page": current_page,
            "page_size": current_size,
            "deals": [],
            "countdown": countdown,
            "available_filters": _collect_filters(entries, top_filters),
            "coverage": "unavailable",
            "coverage_reason": (
                "HTTP 200 with zero deal rows and meta.totalItems=0 for this point; "
                "the point may be unserved (unserved cities 404 or return empty CMS pages)."
            ),
            "source": _FLASH_SOURCE,
        }
    return {
        "total": total,
        "page": current_page,
        "page_size": current_size,
        "deals": products,
        "countdown": countdown,
        "available_filters": _collect_filters(entries, top_filters),
        "coverage": "available",
        "source": _FLASH_SOURCE,
    }


@tool("Homepage discovery feed")
async def discovery_feed(lat: float, long: float, page: int = 1) -> dict:
    """Paged multi-widget homepage feed (``page-content/``).

    Sections are typed by ``content.type`` (0 widget / 1 vendor / 2
    product); unknown widget component types are preserved verbatim.
    ``total_sections`` is ``meta.totalItems``, not the returned sections.
    """
    _require_coords(lat, long)
    _require_paging(page, 10)
    try:
        body = await fetch(
            _FEED_PATH,
            params={
                "latitude": lat,
                "longitude": long,
                "bypassCache": False,
                "pageNumber": page,
                "pageSize": 10,
            },
        )
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "total_sections": 0,
            "page": page,
            "sections": [],
            "coverage": "unavailable",
            "coverage_reason": str(e),
            "source": _FEED_SOURCE,
        }
    entries, _ = _cms_entries(body)
    sections: list[dict[str, Any]] = []
    for entry in entries:
        kind = entry.get("type")
        if kind == 0:
            (widget,) = _collect_widgets([entry])
            sections.append({"kind": "widget", **widget})
        elif kind == 1 and isinstance(entry.get("defaultFeedContent"), dict):
            sections.append({"kind": "vendor", "vendor": _norm_cms_vendor(entry["defaultFeedContent"])})
        elif kind == 2 and isinstance(entry.get("defaultFeedContent"), dict):
            sections.append({"kind": "product", "product": _norm_cms_product(entry["defaultFeedContent"])})
        else:
            sections.append({"kind": "unknown", "type": kind, "raw": entry})
    total, current_page, _ = _cms_meta(body, page, 10, len(sections))
    return {
        "total_sections": total,
        "page": current_page,
        "sections": sections,
        "coverage": "available",
        "source": _FEED_SOURCE,
    }


@tool("Slug-addressed CMS collection")
async def collection(
    slug: str,
    lat: float,
    long: float,
    page: int = 1,
    page_size: int = 10,
    filter_value: str | None = None,
) -> dict:
    """One CMS collection page (``page-content/{slug}``).

    ``slug`` must be one of the feed/capture-observed slugs and is rejected
    before any fetch otherwise. The only accepted ``filter_value`` is the
    observed ``"1-82"`` (category کباب), sent as ``filtersAndSorts``. An
    empty page with ``meta.totalItems>0`` is past-the-end exhaustion with
    ``total`` preserved and coverage still ``"available"``.
    """
    clean = _require_slug(slug)
    _require_coords(lat, long)
    _require_paging(page, page_size)
    if filter_value is not None and filter_value not in OBSERVED_FILTERS:
        raise ApiError(
            f"filter_value {filter_value!r} has no observed encoding; "
            f"only {sorted(OBSERVED_FILTERS)} was exercised end-to-end."
        )
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": long,
        "bypassCache": False,
        "pageNumber": page,
        "pageSize": page_size,
    }
    if filter_value is not None:
        params["filtersAndSorts"] = filter_value
    path = f"{_FEED_PATH}{clean}"
    source = f"page-content/{clean}"
    # `_require_slug` admits only observed slugs, so this is always True; kept
    # for downstream consumers that key off it.
    known = True
    try:
        body = await fetch(path, params=params)
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "slug": clean,
            "known_slug": known,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "config": None,
            "available_filters": [],
            "widgets": [],
            "vendors": [],
            "products": [],
            "coverage": "unavailable",
            "coverage_reason": str(e),
            "source": source,
        }
    entries, top_filters = _cms_entries(body)
    vendors, products = _collect_rows(entries)
    rows = len(vendors) + len(products)
    total, current_page, current_size = _cms_meta(body, page, page_size, rows)
    base: dict[str, Any] = {
        "slug": clean,
        "known_slug": known,
        "total": total,
        "page": current_page,
        "page_size": current_size,
        "config": body.get("config") if isinstance(body, dict) else None,
        "available_filters": _collect_filters(entries, top_filters),
        "widgets": _collect_widgets(entries),
        "vendors": vendors,
        "products": products,
        "source": source,
    }
    if not rows and total > 0:
        return {
            **base,
            "coverage": "available",
            "page_note": _beyond_end_note(current_page, total),
        }
    if not rows:
        return {
            **base,
            "total": 0,
            "coverage": "unavailable",
            "coverage_reason": (
                "HTTP 200 with zero vendor/product rows and meta.totalItems=0 for "
                "this slug/point; the slug may be empty here or the point unserved."
            ),
        }
    return {**base, "coverage": "available"}

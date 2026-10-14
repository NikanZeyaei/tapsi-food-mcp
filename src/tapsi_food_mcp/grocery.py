"""Grocery views over the food catalog (Task 6).

There is no separate market host or auth: grocery categories and stores read
the ``page-content/business-line-7`` CMS hub via
:func:`tapsi_food_mcp.discovery.collection`, and grocery search delegates to
:func:`tapsi_food_mcp.discovery.search_products` with ``business_type_id=13``
(خواربار). Money stays integer Toman, exactly as observed.

Return shapes:
- ``grocery_categories`` → ``{total, categories[{id,name,content_id,
  filter_value}], coverage[, coverage_reason], source}``. Chips come from the
  page-1 ``component.type == 1039`` widget ``items[]`` (``payload.contentId``
  and ``filterValue``); this is a filter-chip list, not an exhaustive taxonomy.
- ``grocery_stores`` → ``{total, page, page_size, stores[{code,title,status,
  open,delivery_fee,minimum_basket,eta,rate,...}], coverage[,
  coverage_reason][, page_note], source}``. ``total`` is the hub's
  ``meta.totalItems``, not the returned rows. A past-the-end page
  (``total>0``, zero rows) stays ``coverage="available"`` with ``total``
  preserved and ``page_note`` passed through; a 404 or an empty hub
  (``total=0``) maps to ``coverage="unavailable"``.
- ``grocery_search`` → ``{query, total, page, page_size, products[{
  variation_id,product_id,name,price,final_price,vendor_code,brand,stock,
  ...}], coverage[, coverage_reason][, page_note], source}``. ``brand`` is
  always null (search carries no brand; never invented), ``stock`` is always
  null (search promises none), and different stores' same-named items have
  different IDs, so no cross-store equivalence is promised. Past-the-end
  pages mirror ``search_products`` exhaustion (``total`` preserved,
  ``page_note`` passed through).
"""

from __future__ import annotations

from typing import Any

from . import discovery
from .registry import tool

_GROCERY_SLUG = "business-line-7"
_GROCERY_SOURCE = "page-content/business-line-7"
_GROCERY_BUSINESS_TYPE_ID = 13
_CHIP_COMPONENT = 1039


def _chips(widgets: Any) -> list[dict[str, Any]]:
    """Normalize 1039 chip items to {id,name,content_id,filter_value}."""
    out: list[dict[str, Any]] = []
    if not isinstance(widgets, list):
        return out
    for widget in widgets:
        if not isinstance(widget, dict):
            continue
        if widget.get("component_type") != _CHIP_COMPONENT:
            continue
        items = widget.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                {
                    "id": item.get("id"),
                    "name": payload.get("title"),
                    "content_id": payload.get("contentId"),
                    "filter_value": item.get("filterValue"),
                }
            )
    return out


@tool("Grocery category chips")
async def grocery_categories(lat: float, long: float) -> dict:
    """Grocery filter chips from ``page-content/business-line-7`` page 1.

    Reads the ``component 1039`` chip widget (``items[].payload.contentId``
    and ``items[].filterValue``). A 404 hub or a hub with no chips
    (``total=0``) maps to explicit unavailable coverage; a 429 propagates.
    A collection ``page_note`` (past-the-end hint) is passed through when
    present.
    """
    page = await discovery.collection(_GROCERY_SLUG, lat, long, page=1, page_size=10)
    categories = _chips(page.get("widgets"))
    if not categories:
        reason = page.get("coverage_reason")
        if reason is None:
            reason = (
                "HTTP 200 with zero category chips for this point; the hub may be empty here or the point unserved."
            )
        out: dict[str, Any] = {
            "total": 0,
            "categories": [],
            "coverage": "unavailable",
            "coverage_reason": reason,
            "source": _GROCERY_SOURCE,
        }
        if page.get("page_note") is not None:
            out["page_note"] = page.get("page_note")
        return out
    return {
        "total": len(categories),
        "categories": categories,
        "coverage": "available",
        "source": _GROCERY_SOURCE,
    }


@tool("Grocery store list")
async def grocery_stores(lat: float, long: float, page: int = 1, page_size: int = 10) -> dict:
    """Grocery vendor rows from ``page-content/business-line-7`` (1-based page).

    ``total`` is the hub's ``meta.totalItems``. Vendor fee/minimum/ETA/rating/
    status fields are preserved exactly as observed (Toman unchanged). A 404
    hub or an empty business line (``total=0``) maps to explicit unavailable
    coverage; a past-the-end page (``total>0``, zero rows) keeps
    ``coverage="available"`` with ``total`` preserved and ``page_note``.
    """
    page_out = await discovery.collection(_GROCERY_SLUG, lat, long, page=page, page_size=page_size)
    if page_out.get("coverage") != "available":
        return {
            "total": 0,
            "page": page_out.get("page", page),
            "page_size": page_out.get("page_size", page_size),
            "stores": [],
            "coverage": "unavailable",
            "coverage_reason": page_out.get("coverage_reason"),
            "source": _GROCERY_SOURCE,
        }
    out: dict[str, Any] = {
        "total": page_out.get("total", 0),
        "page": page_out.get("page", page),
        "page_size": page_out.get("page_size", page_size),
        "stores": page_out.get("vendors", []),
        "coverage": "available",
        "source": _GROCERY_SOURCE,
    }
    if page_out.get("page_note") is not None:
        out["page_note"] = page_out.get("page_note")
    return out


@tool("Grocery product search")
async def grocery_search(query: str, lat: float, long: float, page: int = 1, page_size: int = 10) -> dict:
    """Grocery-only product search (``businessTypeIds[0]=13``, 1-based page).

    Delegates to ``search_products`` so grocery isolation, pagination and
    coverage stay identical, including past-the-end exhaustion (``total``
    preserved, ``page_note`` passed through). ``brand`` is null (search
    carries no brand) and ``stock`` is null (search promises none); prices
    are Toman unchanged and no cross-store equivalence is claimed.
    """
    out = await discovery.search_products(
        query, lat, long, business_type_id=_GROCERY_BUSINESS_TYPE_ID, page=page, page_size=page_size
    )
    if out.get("coverage") != "available":
        return {
            "query": out.get("query", query.strip() if isinstance(query, str) else query),
            "total": 0,
            "page": out.get("page", page),
            "page_size": out.get("page_size", page_size),
            "products": [],
            "coverage": "unavailable",
            "coverage_reason": out.get("coverage_reason"),
            "source": out.get("source", "Search/product-search"),
        }
    products = []
    for row in out.get("products", []):
        if not isinstance(row, dict):
            continue
        products.append({**row, "brand": None})
    result: dict[str, Any] = {
        "query": out.get("query", query),
        "total": out.get("total", len(products)),
        "page": out.get("page", page),
        "page_size": out.get("page_size", page_size),
        "products": products,
        "coverage": "available",
        "source": out.get("source", "Search/product-search"),
    }
    if out.get("page_note") is not None:
        result["page_note"] = out.get("page_note")
    return result

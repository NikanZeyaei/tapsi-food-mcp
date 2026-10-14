"""Vendor menu, order costs and reviews (Task 5).

Anonymous read-only views over the Tapsi Food vendor endpoints:

- ``GET /v2/api/Vendor/{code}/vendor`` — location-sensitive full menu
  (``data.categories[].products[].productVariations[]`` with stock and
  option categories), fee/packing/tax flag and coverage status.
- ``GET /v1/api/Vendor/{code}/profile`` — info, shift and paginated
  reviews (``data.insight.reviews[].orderItems[]``); review pages are
  0-based.
- ``GET /v1/api/RateAndReview/{product_id}/review`` — product reviews;
  no pagination was observed, so none is invented.

Money stays integer Toman exactly as returned; nullable API fields stay
null. HTTP 200 with ``OutOfCoverage`` status or ``Unknown``/``-1`` fee is
never reported deliverable. Menu and profile minimum-basket/status values
are source-labelled because they can disagree; no coupon, tax amount or
checkout quote is fabricated.
"""

from __future__ import annotations

from typing import Any

from .http import ApiError, fetch
from .registry import tool

MENU_SOURCE = "v2/api/Vendor/{code}/vendor"
PROFILE_SOURCE = "v1/api/Vendor/{code}/profile"
PRODUCT_REVIEW_SOURCE = "v1/api/RateAndReview/{product_id}/review"


def _require_vendor_code(vendor_code: str) -> str:
    code = vendor_code.strip() if isinstance(vendor_code, str) else ""
    if not code or "/" in code or any(ch.isspace() for ch in code):
        raise ApiError("vendor_code must be a non-empty vendor code (e.g. '2y97wk').")
    return code


def _require_product_id(product_id: int) -> int:
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
        raise ApiError("product_id must be a positive integer.")
    return product_id


def _require_coords(lat: float, long: float) -> None:
    if not (-90 <= lat <= 90 and -180 <= long <= 180):
        raise ApiError(f"Coordinates out of range: lat={lat}, long={long}.")


def _require_review_paging(page: int, page_size: int) -> None:
    if isinstance(page, bool) or not isinstance(page, int) or page < 0:
        raise ApiError("Review pages are 0-based: page must be an integer >= 0.")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 50:
        raise ApiError("page_size must be an integer between 1 and 50.")


def _delivery_types(vendor: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for entry in vendor.get("deliveryTypes") or []:
        if isinstance(entry, dict):
            out.append({"type": entry.get("deliveryType"), "price": entry.get("deliveryPrice")})
    return out


def _coverage_of(vendor: dict[str, Any]) -> tuple[str, bool, str | None]:
    """Map the menu vendor block to (coverage, deliverable, reason)."""
    status = vendor.get("vendorStatus")
    types = _delivery_types(vendor)
    unknown_fee = bool(types) and all(t["type"] == "Unknown" or t["price"] == -1 or t["price"] is None for t in types)
    if status == "OutOfCoverage" or unknown_fee:
        return (
            "unavailable",
            False,
            f"Vendor reports status={status!r} with delivery={types or 'none'}: "
            "not deliverable to this point; do not treat the menu as orderable.",
        )
    return "available", True, None


def _normalize_variation(raw: dict[str, Any]) -> dict[str, Any]:
    options = []
    for cat in raw.get("optionCategories") or []:
        if not isinstance(cat, dict):
            continue
        options.append(
            {
                "id": cat.get("optionCategoryId"),
                "name": cat.get("optionCategoryName"),
                "capacity": cat.get("capacity"),
                "mandatory": cat.get("isMandatory"),
                "options": [
                    {"id": o.get("optionId"), "name": o.get("optionName"), "price": o.get("price")}
                    for o in cat.get("options") or []
                    if isinstance(o, dict)
                ],
            }
        )
    stock = raw.get("stock")
    return {
        "id": raw.get("productVariationId"),
        "name": raw.get("productVariationName"),
        "description": raw.get("productVariationDescription"),
        "price": raw.get("price"),
        "final_price": raw.get("priceAfterDiscount"),
        "discount_ratio": raw.get("discountRatio"),
        "stock": stock,
        "available": (stock or 0) > 0,
        "discount_stock": raw.get("discountStock"),
        "mandatory_option_category_ids": raw.get("mandatoryOptionCategoryIds") or [],
        "option_categories": options,
    }


def _normalize_categories(data: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    categories = []
    total_products = 0
    total_variations = 0
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        products = []
        for prod in cat.get("products") or []:
            if not isinstance(prod, dict):
                continue
            variations = [_normalize_variation(v) for v in prod.get("productVariations") or [] if isinstance(v, dict)]
            total_variations += len(variations)
            total_products += 1
            products.append(
                {
                    "id": prod.get("productId"),
                    "name": prod.get("productName"),
                    "description": prod.get("productDescription"),
                    "images": prod.get("images"),
                    "rate": prod.get("productRate"),
                    "variations": variations,
                }
            )
        categories.append({"id": cat.get("categoryId"), "name": cat.get("categoryName"), "products": products})
    return categories, total_products, total_variations


def _normalize_vendor(vendor: dict[str, Any], review: dict[str, Any] | None = None) -> dict[str, Any]:
    review = review if isinstance(review, dict) else {}
    return {
        "code": vendor.get("vendorCode"),
        "title": vendor.get("title"),
        "status": vendor.get("vendorStatus"),
        "in_service": vendor.get("vendorHasInServiceState"),
        "minimum_basket": vendor.get("minimumBasket"),
        "packing_price": vendor.get("packingPrice"),
        "tax_included": vendor.get("tax"),
        "delivery_types": _delivery_types(vendor),
        "eta": vendor.get("eta"),
        "discount": vendor.get("discount"),
        "rate": review.get("rate"),
        "rates_count": review.get("rateCount"),
        "business_type_id": vendor.get("businessTypeId"),
        "city_id": vendor.get("cityId"),
    }


def _filter_categories(categories: list[dict[str, Any]], query: str) -> tuple[list[dict[str, Any]], int, int]:
    needle = query.casefold()
    kept = []
    total_products = 0
    total_variations = 0
    for cat in categories:
        products = [
            p
            for p in cat["products"]
            if needle in (p["name"] or "").casefold()
            or any(needle in (v["name"] or "").casefold() for v in p["variations"])
        ]
        if products:
            kept.append({**cat, "products": products})
            total_products += len(products)
            total_variations += sum(len(p["variations"]) for p in products)
    return kept, total_products, total_variations


async def _load_menu(vendor_code: str, lat: float, long: float) -> dict[str, Any]:
    code = _require_vendor_code(vendor_code)
    _require_coords(lat, long)
    body = await fetch(f"/v2/api/Vendor/{code}/vendor", params={"latitude": lat, "longitude": long})
    data = body.get("data") or {}
    vendor = _normalize_vendor(data.get("vendor") or {}, data.get("review"))
    categories, total_products, total_variations = _normalize_categories(data)
    coverage, deliverable, reason = _coverage_of(data.get("vendor") or {})
    return {
        "vendor": vendor,
        "raw_vendor": data.get("vendor") or {},
        "categories": categories,
        "total_products": total_products,
        "total_variations": total_variations,
        "coverage": coverage,
        "deliverable": deliverable,
        "coverage_reason": reason,
        "source": MENU_SOURCE.format(code=code),
    }


@tool("Vendor menu with categories, variations, stock and coverage")
async def vendor_menu(vendor_code: str, lat: float, long: float, query: str | None = None) -> dict:
    """Full menu of one vendor at a delivery point, with deliverability.

    `query` filters the already-fetched menu locally (product/variation
    name substring); it never triggers another request. A 404 (unknown
    code or unserved catalog) returns explicit unavailable coverage.
    """
    code = _require_vendor_code(vendor_code)
    _require_coords(lat, long)
    try:
        menu = await _load_menu(code, lat, long)
    except ApiError as e:
        if e.status != 404:
            raise
        return {
            "vendor": {"code": code},
            "coverage": "unavailable",
            "deliverable": False,
            "coverage_reason": str(e),
            "source": MENU_SOURCE.format(code=code),
            "query": query,
            "total_categories": 0,
            "total_products": 0,
            "total_variations": 0,
            "categories": [],
        }
    categories = menu["categories"]
    total_products = menu["total_products"]
    total_variations = menu["total_variations"]
    if query:
        categories, total_products, total_variations = _filter_categories(categories, query)
    return {
        "vendor": menu["vendor"],
        "coverage": menu["coverage"],
        "deliverable": menu["deliverable"],
        "coverage_reason": menu["coverage_reason"],
        "source": menu["source"],
        "query": query,
        "total_categories": len(categories),
        "total_products": total_products,
        "total_variations": total_variations,
        "categories": categories,
    }


@tool("Order costs: delivery, packing, minimum basket with source warnings")
async def order_costs(vendor_code: str, lat: float, long: float) -> dict:
    """Delivery/packing/minimum-basket planning figures from menu + profile.

    One menu fetch and one profile fetch per call. When menu and profile
    disagree, both values are reported with `source_warnings` and the
    user-facing profile value is preferred. `coverage` always comes from the
    menu (geographic deliverability); `deliverable` additionally follows the
    preferred vendor status, so a preferred `Close` is never deliverable even
    when the menu point is inside geographic coverage. A failing profile
    degrades to menu-only figures instead of hiding coverage. No coupon, tax
    amount or checkout total is invented: tax is only a boolean flag.
    """
    menu = await _load_menu(vendor_code, lat, long)
    code = menu["vendor"]["code"]
    try:
        profile = await fetch(f"/v1/api/Vendor/{code}/profile", params={"pageSize": 1, "pageNumber": 0})
    except ApiError as e:
        profile = None
        profile_error = str(e)
    else:
        profile_error = None

    info = (profile.get("data") or {}).get("info") or {} if profile else {}
    menu_min = menu["raw_vendor"].get("minimumBasket")
    profile_min = info.get("minimumBasket")
    menu_status = menu["raw_vendor"].get("vendorStatus")
    profile_status = info.get("vendorStatus")
    preferred_status = profile_status if profile is not None else menu_status

    warnings = []
    if profile is None:
        warnings.append(
            f"Vendor profile unreadable ({profile_error}); figures are menu-only and coverage comes from the menu."
        )
    else:
        if profile_min != menu_min:
            warnings.append(
                f"minimum_basket disagrees: menu={menu_min} vs profile={profile_min} "
                "(Toman); preferring the user-facing profile value."
            )
        if profile_status != menu_status:
            warnings.append(
                f"vendor status disagrees: menu={menu_status!r} vs profile={profile_status!r}; "
                "preferring the user-facing profile value."
            )

    deliverable = menu["deliverable"] and preferred_status == "Open"
    if deliverable or menu["coverage_reason"]:
        coverage_reason = menu["coverage_reason"]
    else:
        coverage_reason = (
            f"Vendor reports preferred status={preferred_status!r} "
            f"({('profile' if profile is not None else 'menu')}); not orderable right now. "
            f"Geographic coverage from the menu is {menu['coverage']!r}."
        )

    return {
        "vendor_code": code,
        "title": info.get("title") or menu["vendor"]["title"],
        "coverage": menu["coverage"],
        "deliverable": deliverable,
        "coverage_reason": coverage_reason,
        "vendor_status": preferred_status,
        "vendor_status_sources": {"menu": menu_status, "profile": profile_status},
        "minimum_basket": profile_min if profile is not None else menu_min,
        "minimum_basket_sources": {"menu": menu_min, "profile": profile_min},
        "delivery_types": [{**entry, "source": "menu"} for entry in menu["vendor"]["delivery_types"]],
        "packing_price": menu["vendor"]["packing_price"],
        "packing_price_source": "menu",
        "tax_included": menu["vendor"]["tax_included"],
        "tax_source": "menu",
        "eta": info.get("eta") if profile is not None and info.get("eta") is not None else menu["vendor"]["eta"],
        "profile_status": "ok" if profile is not None else "error",
        "profile_error": profile_error,
        "source_warnings": warnings,
        "source": f"{menu['source']} + {PROFILE_SOURCE.format(code=code)}",
    }


def _normalize_review(raw: dict[str, Any]) -> dict[str, Any]:
    items = []
    for entry in raw.get("orderItems") or []:
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "product_name": entry.get("productName"),
                "rating": entry.get("rating"),
                "comment": entry.get("comment"),
                "replies": entry.get("replies") or [],
            }
        )
    return {
        "writer_name": raw.get("writerName"),
        "created_at": raw.get("createdAt"),
        "order_rating": raw.get("orderRating"),
        "order_items": items,
    }


@tool("Vendor reviews with nested per-item comments")
async def vendor_reviews(vendor_code: str, page: int = 0, page_size: int = 20) -> dict:
    """Paginated vendor reviews from the profile endpoint (0-based page)."""
    code = _require_vendor_code(vendor_code)
    _require_review_paging(page, page_size)
    body = await fetch(f"/v1/api/Vendor/{code}/profile", params={"pageSize": page_size, "pageNumber": page})
    data = body.get("data") or {}
    meta = data.get("meta") or {}
    total = meta.get("total") or 0
    info = data.get("info") or {}
    insight = data.get("insight") or {}
    shift = data.get("shift") or {}
    reviews = [_normalize_review(r) for r in insight.get("reviews") or [] if isinstance(r, dict)]
    address = info.get("address") or {}
    return {
        "vendor_code": code,
        "total": total,
        "page": page,
        "page_size": page_size,
        "next_page": page + 1 if (page + 1) * page_size < total else None,
        "source": PROFILE_SOURCE.format(code=code),
        "info": {
            "title": info.get("title"),
            "status": info.get("vendorStatus"),
            "minimum_basket": info.get("minimumBasket"),
            "address": address.get("addressDetails"),
        },
        "shift": shift or None,
        "reviews": reviews,
    }


@tool("Product reviews and rate detail")
async def product_reviews(product_id: int) -> dict:
    """Reviews of one product; no pagination is observed, so none is reported."""
    pid = _require_product_id(product_id)
    body = await fetch(f"/v1/api/RateAndReview/{pid}/review")
    data = body.get("data") or {}
    raw_reviews = data.get("reviews") or []
    reviews = []
    for entry in raw_reviews:
        if not isinstance(entry, dict):
            continue
        reviews.append(
            {
                "rating": entry.get("rating"),
                "comment": entry.get("comment"),
                "created_at": entry.get("createdAt") or entry.get("created_at"),
                "replies": entry.get("replies") or [],
            }
        )
    rate_detail = data.get("rateDetail") or {}
    return {
        "product_id": pid,
        "total": len(reviews),
        "rate": rate_detail.get("rate"),
        "source": PRODUCT_REVIEW_SOURCE.format(product_id=pid),
        "reviews": reviews,
    }

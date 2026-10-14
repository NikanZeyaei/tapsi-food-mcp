"""Behavior tests for grocery views (src/tapsi_food_mcp/grocery.py).

Covers the business-line-7 category chips (component 1039 ``payload.contentId``
and ``filterValue``), grocery store pagination/fields/404/empty coverage, and
grocery product search isolated with ``businessTypeIds[0]=13`` (nullable brand,
null stock, Toman unchanged). Fixtures are compact hand-built shapes mirroring
research/samples, not live goldens.
"""

import httpx
import pytest

from tapsi_food_mcp.grocery import (
    grocery_categories,
    grocery_search,
    grocery_stores,
)
from tapsi_food_mcp.http import ApiError

pytestmark = pytest.mark.anyio

LAT = 35.6892
LONG = 51.389
BL7_PATH = "/v1/api/search-discovery/page-content/business-line-7"
PRODUCT_SEARCH_PATH = "/v1/api/search-discovery/Search/product-search"


def _chip(item_id, title, content_id, filter_value):
    return {
        "id": item_id,
        "payload": {
            "businessLineId": None,
            "title": title,
            "subtitle": None,
            "imageUrl": None,
            "linkUrl": None,
            "videoUrl": None,
            "linkType": 1,
            "pageSlug": None,
            "price": None,
            "badge": None,
            "type": 1,
            "contentId": content_id,
        },
        "pinned": False,
        "filterValue": filter_value,
        "isSelected": False,
    }


def _chip_widget():
    return {
        "type": 0,
        "component": {
            "type": 1039,
            "componentMeta": {"title": None, "description": "", "options": {}},
            "config": None,
            "items": [
                _chip(3704, "غلات و حبوبات", 24, "1-24"),
                _chip(3705, "برنج", 38, "1-38"),
            ],
        },
        "defaultFeedContent": None,
    }


def _cms_vendor(code="2nz941"):
    return {
        "vendorCode": code,
        "title": "لبنیات سنتی جمالزاده",
        "vendorStatus": "Open",
        "discount": 0,
        "mainImage": None,
        "logo": None,
        "businessTypeId": 13,
        "cityId": 2,
        "deliveryType": "OfoodDelivery",
        "deliveryPrice": 38000,
        "minimumBasket": 300000,
        "eta": 65,
        "isInstallmentalPaymentActive": False,
        "badges": [],
        "rate": 4.1,
        "ratesCount": 212,
        "isNewVendor": False,
        "categories": [],
        "distance": 0,
        "documentId": None,
        "index": 0,
    }


def _cms_page(entries, total=13, page=1, size=10):
    return {
        "meta": {"pageSize": size, "pageNumber": page, "totalItems": total},
        "config": None,
        "content": entries,
    }


def _vendor_entry(code="2nz941"):
    return {"type": 1, "component": None, "defaultFeedContent": _cms_vendor(code)}


def _grocery_product(variation="2479746", header=1867178):
    # Search carries no brand field at all; stock must never be promised.
    return {
        "id": variation,
        "queryId": "snd-product-aaa",
        "position": 1,
        "productInfo": {
            "name": "شیر محلی (1.5 لیتر)",
            "images": [],
            "discountRatio": 0,
            "price": 212000,
            "priceAfterDiscount": 212000,
            "headerId": header,
            "id": variation,
            "rate": None,
            "ratesCount": None,
            "badges": [],
        },
        "vendorInfo": {
            "title": "لبنیات سنتی جمالزاده",
            "logo": None,
            "vendorCode": "2nz941",
            "deliveryPrice": 38000,
            "deliveryType": "OfoodDelivery",
            "vendorStatus": True,
            "eta": 65,
            "rate": 0,
            "ratesCount": 0,
        },
        "subDocs": None,
    }


def _search_page(items, total=1, page=1, size=5):
    return {
        "statusCode": 200,
        "message": "Search completed successfully",
        "data": items,
        "meta": {"pageSize": size, "pageNumber": page, "totalItems": total},
        "filters": [],
    }


async def test_grocery_categories_reads_chip_payload_content_id_and_filter(api):
    api[BL7_PATH] = _cms_page([_chip_widget(), _vendor_entry()])
    out = await grocery_categories(LAT, LONG)
    assert out["coverage"] == "available"
    assert out["source"] == "page-content/business-line-7"
    assert out["total"] == 2
    assert out["categories"] == [
        {"id": 3704, "name": "غلات و حبوبات", "content_id": 24, "filter_value": "1-24"},
        {"id": 3705, "name": "برنج", "content_id": 38, "filter_value": "1-38"},
    ]


async def test_grocery_categories_always_uses_cms_page_one(api):
    api[BL7_PATH] = _cms_page([_chip_widget()])
    await grocery_categories(LAT, LONG)
    assert api.calls[0].url.params["pageNumber"] == "1"


async def test_grocery_categories_404_is_unavailable(api):
    out = await grocery_categories(32.651789, 51.693768)
    assert out["coverage"] == "unavailable"
    assert out["categories"] == [] and out["total"] == 0
    assert out["source"] == "page-content/business-line-7"


async def test_grocery_stores_preserves_total_and_observed_fields(api):
    api[BL7_PATH] = _cms_page([_chip_widget(), _vendor_entry()])
    out = await grocery_stores(LAT, LONG)
    assert out["total"] == 13  # meta total, not the single returned row
    assert out["page"] == 1 and out["coverage"] == "available"
    assert out["source"] == "page-content/business-line-7"
    (store,) = out["stores"]
    assert store["code"] == "2nz941"
    assert store["delivery_fee"] == 38000
    assert store["minimum_basket"] == 300000
    assert store["eta"] == 65
    assert store["rate"] == 4.1
    assert store["status"] == "Open" and store["open"] is True


async def test_grocery_stores_pages_are_distinct(api):
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNumber"])
        code = f"store-p{page}"
        return httpx.Response(200, json=_cms_page([_vendor_entry(code)], total=13, page=page, size=1))

    api[BL7_PATH] = handler
    first = await grocery_stores(LAT, LONG, page=1, page_size=1)
    second = await grocery_stores(LAT, LONG, page=2, page_size=1)
    assert first["page"] == 1 and second["page"] == 2
    assert first["total"] == 13 and second["total"] == 13
    assert first["stores"][0]["code"] != second["stores"][0]["code"]


async def test_grocery_stores_404_is_unavailable(api):
    out = await grocery_stores(38.080028, 46.2919)
    assert out["coverage"] == "unavailable"
    assert out["stores"] == [] and out["total"] == 0


async def test_grocery_stores_empty_business_line_is_unavailable(api):
    api[BL7_PATH] = _cms_page([], total=0)
    out = await grocery_stores(LAT, LONG)
    assert out["coverage"] == "unavailable"
    assert out["stores"] == [] and out["total"] == 0


async def test_grocery_stores_past_end_page_stays_available_with_total(api):
    api[BL7_PATH] = _cms_page([], total=13, page=5, size=10)
    out = await grocery_stores(LAT, LONG, page=5)
    assert out["coverage"] == "available"
    assert out["stores"] == [] and out["total"] == 13
    assert out["page"] == 5 and "page_note" in out


async def test_grocery_search_sends_business_type_13(api):
    api[PRODUCT_SEARCH_PATH] = _search_page([_grocery_product()])
    out = await grocery_search("شیر", LAT, LONG)
    call = api.calls[0]
    assert call.url.params["businessTypeIds[0]"] == "13"
    assert call.url.params["query"] == "شیر"
    assert out["total"] == 1 and out["coverage"] == "available"
    assert out["source"] == "Search/product-search"


async def test_grocery_search_keeps_ids_toman_and_nullable_brand(api):
    api[PRODUCT_SEARCH_PATH] = _search_page([_grocery_product()])
    out = await grocery_search("شیر", LAT, LONG)
    (row,) = out["products"]
    assert row["variation_id"] == "2479746"
    assert row["product_id"] == 1867178
    assert row["price"] == 212000 and row["final_price"] == 212000
    assert row["brand"] is None  # search carries no brand; never invented
    assert row["stock"] is None  # search promises no stock
    assert row["vendor_code"] == "2nz941"


async def test_grocery_search_pages_are_distinct(api):
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNumber"])
        assert request.url.params["businessTypeIds[0]"] == "13"
        item = _grocery_product(variation=f"247974{page}", header=1867170 + page)
        return httpx.Response(200, json=_search_page([item], total=2, page=page, size=1))

    api[PRODUCT_SEARCH_PATH] = handler
    first = await grocery_search("شیر", LAT, LONG, page=1, page_size=1)
    second = await grocery_search("شیر", LAT, LONG, page=2, page_size=1)
    assert first["page"] == 1 and second["page"] == 2
    assert first["products"][0]["variation_id"] != second["products"][0]["variation_id"]


async def test_grocery_search_empty_200_is_unavailable(api):
    api[PRODUCT_SEARCH_PATH] = _search_page([], total=0)
    out = await grocery_search("شیر", 32.651789, 51.693768)
    assert out["coverage"] == "unavailable"
    assert out["products"] == [] and out["total"] == 0


async def test_grocery_search_404_is_unavailable(api):
    out = await grocery_search("شیر", LAT, LONG)
    assert out["coverage"] == "unavailable"
    assert out["products"] == [] and out["total"] == 0


async def test_grocery_search_past_end_page_stays_available_with_total(api):
    api[PRODUCT_SEARCH_PATH] = _search_page([], total=2, page=3, size=1)
    out = await grocery_search("شیر", LAT, LONG, page=3, page_size=1)
    assert out["coverage"] == "available"
    assert out["products"] == [] and out["total"] == 2
    assert out["page"] == 3 and "page_note" in out


async def test_grocery_paging_and_coords_are_validated(api):
    with pytest.raises(ApiError):
        await grocery_stores(LAT, LONG, page=0)
    with pytest.raises(ApiError):
        await grocery_search("شیر", LAT, LONG, page_size=51)
    with pytest.raises(ApiError):
        await grocery_categories(200.0, LONG)
    assert api.calls == []

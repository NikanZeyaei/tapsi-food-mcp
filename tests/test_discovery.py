"""Behavior tests for search/CMS discovery (src/tapsi_food_mcp/discovery.py).

Covers the dedicated Search endpoints (product-search, vendor-search with
``businessTypeIds[0]`` encoding and 1-based pagination) and the CMS
page-content lists/collections (mixed widget/vendor/product sections,
meta totals, 404/empty coverage, nullable fields, slug allowlist and the
single observed ``filtersAndSorts=1-82`` filter). Fixtures below are compact
hand-built shapes mirroring research/samples, not live goldens.
"""

import httpx
import pytest

from tapsi_food_mcp.discovery import (
    collection,
    discounted_vendors,
    discovery_feed,
    flash_deals,
    restaurants,
    search_products,
    search_vendors,
)
from tapsi_food_mcp.http import ApiError

pytestmark = pytest.mark.anyio

LAT = 35.6892
LONG = 51.389

PRODUCT_SEARCH_PATH = "/v1/api/search-discovery/Search/product-search"
VENDOR_SEARCH_PATH = "/v1/api/search-discovery/Search/vendor-search"
FEED_PATH = "/v1/api/search-discovery/page-content/"
RESTAURANTS_PATH = "/v1/api/search-discovery/page-content/business-line-15"
FOODSHAT_PATH = "/v1/api/search-discovery/page-content/فودشات"
TAPTIME_PATH = "/v1/api/search-discovery/page-content/تپ-تایم"


def _search_product(variation="2479746", header=1867178, rate=None):
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
            "rate": rate,
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


def _search_vendor(code="5z68lm"):
    return {
        "vendorCode": code,
        "queryId": "snd-vendor-bbb",
        "position": 1,
        "vendorInfo": {
            "title": "پیتزا کیوان",
            "logo": None,
            "rate": 3.6,
            "ratesCount": 30,
            "isOpen": True,
            "eta": 55,
            "deliveryType": "OfoodDelivery",
            "deliveryPrice": 32000,
            "vendorTags": [],
            "badges": [],
        },
    }


def _cms_vendor(code="21y3nr"):
    return {
        "vendorCode": code,
        "title": "فست فود تاپ استیک",
        "vendorStatus": "Open",
        "discount": 25,
        "mainImage": None,
        "logo": None,
        "businessTypeId": None,
        "cityId": 2,
        "deliveryType": "OfoodDelivery",
        "deliveryPrice": 30000,
        "minimumBasket": 300000.0,
        "eta": 55,
        "isInstallmentalPaymentActive": False,
        "badges": [],
        "rate": 3.8,
        "ratesCount": 1180,
        "isNewVendor": False,
        "categories": [],
        "distance": 0,
        "documentId": None,
        "index": 0,
    }


def _cms_product(variation="2121886", header="1582926", stock=6, rate=4.4):
    return {
        "discountStock": stock,
        "vendorCode": "5w71ym",
        "vendorName": "فست فود یامی لند",
        "vendorStatus": "Open",
        "businessTypeId": None,
        "cityId": 2,
        "deliveryType": "OfoodDelivery",
        "deliveryPrice": 34000,
        "productId": variation,
        "headerId": header,
        "productName": "رویال برگر با نان باگت",
        "productImages": [],
        "productVariationId": variation,
        "productVariationName": "",
        "price": 650000,
        "logo": None,
        "discountRatio": 59.0,
        "priceAfterDiscount": 266500,
        "badges": [],
        "categories": [],
        "productRate": rate,
    }


def _filter_widget():
    return {
        "type": 0,
        "component": {
            "type": 1025,
            "componentMeta": {"title": None, "description": "", "options": {}},
            "config": None,
            "items": [
                {
                    "id": 0,
                    "key": "p-sort",
                    "name": "مرتب‌سازی",
                    "displayAsChip": False,
                    "icon": "List",
                    "isActive": True,
                    "sortOrder": 0,
                    "type": "radio",
                    "role": "sort",
                    "active": False,
                    "options": [{"key": "ratingdesc", "name": "بالاترین امتیاز", "active": False}],
                }
            ],
        },
        "defaultFeedContent": None,
    }


async def test_search_products_sends_location_query_and_paging(api):
    api[PRODUCT_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [_search_product()],
        "meta": {"pageSize": 5, "pageNumber": 1, "totalItems": 1},
        "filters": [],
    }
    out = await search_products("شیر", LAT, LONG, page=1, page_size=5)
    (call,) = api.calls
    params = call.url.params
    assert params["query"] == "شیر"
    assert params["latitude"] == str(LAT) and params["longitude"] == str(LONG)
    assert params["pageNumber"] == "1" and params["pageSize"] == "5"
    assert "businessTypeIds[0]" not in params
    assert out["total"] == 1 and out["page"] == 1
    assert out["coverage"] == "available"
    assert out["source"] == "Search/product-search"


async def test_search_products_pages_are_distinct(api):
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNumber"])
        item = _search_product(variation=f"1000{page}", header=9000 + page)
        return httpx.Response(
            200,
            json={
                "statusCode": 200,
                "message": "Success",
                "data": [item],
                "meta": {"pageSize": 1, "pageNumber": page, "totalItems": 2},
                "filters": [],
            },
        )

    api[PRODUCT_SEARCH_PATH] = handler
    first = await search_products("پیتزا", LAT, LONG, page=1, page_size=1)
    second = await search_products("پیتزا", LAT, LONG, page=2, page_size=1)
    assert first["page"] == 1 and second["page"] == 2
    assert first["products"][0]["variation_id"] != second["products"][0]["variation_id"]


async def test_search_products_business_type_filter_encoding(api):
    api[PRODUCT_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [_search_product()],
        "meta": {"pageSize": 5, "pageNumber": 1, "totalItems": 1},
        "filters": [],
    }
    await search_products("شیر", LAT, LONG, business_type_id=13)
    assert api.calls[0].url.params["businessTypeIds[0]"] == "13"


async def test_search_products_variation_id_kept_apart_from_header_id(api):
    api[PRODUCT_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [_search_product(variation="2479746", header=1867178, rate=None)],
        "meta": {"pageSize": 5, "pageNumber": 1, "totalItems": 1},
        "filters": [],
    }
    out = await search_products("شیر", LAT, LONG)
    (row,) = out["products"]
    assert row["variation_id"] == "2479746"
    assert row["product_id"] == 1867178
    assert row["rate"] is None  # nullable rating preserved, not defaulted
    assert row["vendor_code"] == "2nz941"
    assert row["delivery_fee"] == 38000
    assert row["stock"] is None  # search carries no stock promise


async def test_search_products_empty_first_page_is_unavailable_not_vendors(api):
    api[PRODUCT_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [],
        "meta": {"pageSize": 5, "pageNumber": 1, "totalItems": 0},
        "filters": [],
    }
    out = await search_products("پیتزا", 32.651789, 51.693768)
    assert out["coverage"] == "unavailable"
    assert out["products"] == [] and out["total"] == 0
    assert "coverage_reason" in out


async def test_search_products_empty_later_page_preserves_total(api):
    api[PRODUCT_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [],
        "meta": {"pageSize": 1, "pageNumber": 9, "totalItems": 2},
        "filters": [],
    }
    out = await search_products("پیتزا", LAT, LONG, page=9, page_size=1)
    assert out["coverage"] == "available"
    assert out["products"] == [] and out["total"] == 2
    assert out["page"] == 9
    assert "coverage_reason" not in out
    assert "lower page" in out["page_note"]


async def test_search_products_404_is_unavailable_coverage(api):
    out = await search_products("پیتزا", LAT, LONG)
    assert out["coverage"] == "unavailable"
    assert out["products"] == [] and out["total"] == 0
    assert out["source"] == "Search/product-search"


async def test_search_products_429_propagates(api):
    api[PRODUCT_SEARCH_PATH] = lambda r: httpx.Response(429, text="slow down")
    with pytest.raises(ApiError) as exc:
        await search_products("پیتزا", LAT, LONG)
    assert exc.value.status == 429


async def test_search_vendors_maps_wrapped_rows(api):
    api[VENDOR_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [_search_vendor()],
        "meta": {"pageSize": 5, "pageNumber": 1, "totalItems": 12},
        "filters": [],
    }
    out = await search_vendors("پیتزا", LAT, LONG)
    assert out["total"] == 12 and out["coverage"] == "available"
    assert out["source"] == "Search/vendor-search"
    (row,) = out["vendors"]
    assert row["code"] == "5z68lm" and row["title"] == "پیتزا کیوان"
    assert row["rating"] == 3.6 and row["open"] is True
    assert row["delivery_fee"] == 32000 and row["eta"] == 55
    (call,) = api.calls
    assert call.url.params["query"] == "پیتزا"


async def test_search_vendors_404_is_unavailable(api):
    out = await search_vendors("پیتزا", LAT, LONG)
    assert out["coverage"] == "unavailable" and out["vendors"] == []


async def test_search_vendors_empty_later_page_preserves_total(api):
    api[VENDOR_SEARCH_PATH] = {
        "statusCode": 200,
        "message": "Success",
        "data": [],
        "meta": {"pageSize": 5, "pageNumber": 4, "totalItems": 12},
        "filters": [],
    }
    out = await search_vendors("پیتزا", LAT, LONG, page=4, page_size=5)
    assert out["coverage"] == "available"
    assert out["vendors"] == [] and out["total"] == 12
    assert "lower page" in out["page_note"]


async def test_restaurants_parses_mixed_sections_without_conflating_total(api):
    api[RESTAURANTS_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 1, "totalItems": 192},
        "config": None,
        "content": [
            _filter_widget(),
            {
                "type": 0,
                "component": {"type": 9999, "componentMeta": {}, "items": [{"odd": 1}]},
                "defaultFeedContent": None,
            },
            {"type": 1, "component": None, "defaultFeedContent": _cms_vendor()},
        ],
    }
    out = await restaurants(LAT, LONG)
    assert out["total"] == 192  # meta total, not the single vendor row
    assert out["page"] == 1 and out["coverage"] == "available"
    assert out["source"] == "page-content/business-line-15"
    (vendor,) = out["vendors"]
    assert vendor["code"] == "21y3nr" and vendor["minimum_basket"] == 300000
    assert vendor["rate"] == 3.8
    kinds = {w["component_type"] for w in out["widgets"]}
    assert 9999 in kinds  # unknown widget types are preserved, not dropped
    assert out["available_filters"][0]["key"] == "p-sort"


async def test_restaurants_404_is_unavailable(api):
    out = await restaurants(32.651789, 51.693768)
    assert out["coverage"] == "unavailable"
    assert out["vendors"] == [] and out["total"] == 0


async def test_discounted_vendors_reads_feeds_shape(api):
    api[FOODSHAT_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 1, "totalItems": 110},
        "config": None,
        "filters": [],
        "feeds": [_cms_vendor("569ywk"), _cms_vendor("5w71ym")],
    }
    out = await discounted_vendors(LAT, LONG)
    assert out["source"] == "page-content/فودشات"
    assert out["total"] == 110 and len(out["vendors"]) == 2
    assert out["coverage"] == "available"


async def test_flash_deals_products_countdown_and_nullable_stock(api):
    api[TAPTIME_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 1, "totalItems": 166},
        "config": {"pageTitle": "تپ‌تایم"},
        "content": [
            {
                "type": 0,
                "component": {
                    "type": 1019,
                    "componentMeta": {
                        "title": None,
                        "options": {"enableCountdown": True, "countdownEndsAt": "15:00:00"},
                    },
                    "items": [],
                },
                "defaultFeedContent": None,
            },
            {"type": 2, "component": None, "defaultFeedContent": _cms_product(stock=6)},
            {"type": 2, "component": None, "defaultFeedContent": _cms_product("2401970", "1816475", None, None)},
        ],
    }
    out = await flash_deals(LAT, LONG)
    assert out["source"] == "page-content/تپ-تایم"
    assert out["total"] == 166 and out["countdown"] == "15:00:00"
    first, second = out["deals"]
    assert first["discount_stock"] == 6
    assert second["discount_stock"] is None and second["rate"] is None
    assert first["variation_id"] == "2121886" and first["product_id"] == "1582926"
    assert first["final_price"] == 266500


async def test_flash_deals_empty_later_page_preserves_total(api):
    api[TAPTIME_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 30, "totalItems": 166},
        "config": {"pageTitle": "تپ‌تایم"},
        "content": [],
    }
    out = await flash_deals(LAT, LONG, page=30)
    assert out["coverage"] == "available"
    assert out["deals"] == [] and out["total"] == 166
    assert "lower page" in out["page_note"]


async def test_discovery_feed_types_sections_and_preserves_unknown(api):
    api[FEED_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 1, "totalItems": 23},
        "config": None,
        "content": [
            {
                "type": 0,
                "component": {
                    "type": 1038,
                    "componentMeta": {},
                    "items": [{"id": 15, "name": "رستوران", "destination": "business-line-15"}],
                },
                "defaultFeedContent": None,
            },
            {
                "type": 0,
                "component": {"type": 9999, "componentMeta": {}, "items": [{"odd": True}]},
                "defaultFeedContent": None,
            },
            {"type": 1, "component": None, "defaultFeedContent": _cms_vendor()},
            {"type": 2, "component": None, "defaultFeedContent": _cms_product()},
        ],
    }
    out = await discovery_feed(LAT, LONG)
    assert out["total_sections"] == 23  # meta total, not the 4 returned sections
    assert out["source"] == "page-content/" and out["coverage"] == "available"
    by_kind = {}
    for section in out["sections"]:
        by_kind.setdefault(section["kind"], []).append(section)
    assert len(by_kind["vendor"]) == 1 and len(by_kind["product"]) == 1
    widgets = {w["component_type"]: w for w in by_kind["widget"]}
    assert widgets[1038]["items"][0]["destination"] == "business-line-15"
    assert widgets[9999]["items"] == [{"odd": True}]


async def test_discovery_feed_404_is_unavailable(api):
    out = await discovery_feed(32.651789, 51.693768)
    assert out["coverage"] == "unavailable" and out["sections"] == []


async def test_collection_allowlisted_slug_with_observed_filter(api):
    api[TAPTIME_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 1, "totalItems": 61},
        "config": {"pageTitle": "تپ‌تایم"},
        "filters": [],
        "content": [
            _filter_widget(),
            {"type": 2, "component": None, "defaultFeedContent": _cms_product()},
        ],
    }
    out = await collection("تپ-تایم", LAT, LONG, filter_value="1-82")
    (call,) = api.calls
    assert call.url.path == TAPTIME_PATH
    assert call.url.params["filtersAndSorts"] == "1-82"
    assert out["known_slug"] is True
    assert out["total"] == 61 and out["config"] == {"pageTitle": "تپ‌تایم"}
    assert len(out["products"]) == 1 and out["vendors"] == []
    assert out["available_filters"][0]["key"] == "p-sort"


async def test_collection_rejects_unobserved_filter(api):
    with pytest.raises(ApiError):
        await collection("تپ-تایم", LAT, LONG, filter_value="2-99")


async def test_collection_rejects_non_segment_slug(api):
    with pytest.raises(ApiError):
        await collection("../business-line-15", LAT, LONG)
    with pytest.raises(ApiError):
        await collection("", LAT, LONG)


async def test_collection_rejects_unknown_slug_before_fetch(api):
    with pytest.raises(ApiError):
        await collection("some-new-slug", LAT, LONG)
    assert api.calls == []


async def test_collection_empty_later_page_preserves_total(api):
    api[TAPTIME_PATH] = {
        "meta": {"pageSize": 1, "pageNumber": 200, "totalItems": 166},
        "config": {"pageTitle": "تپ‌تایم"},
        "content": [],
    }
    out = await collection("تپ-تایم", LAT, LONG, page=200, page_size=1)
    assert out["coverage"] == "available"
    assert out["vendors"] == [] and out["products"] == []
    assert out["total"] == 166 and out["page"] == 200
    assert "lower page" in out["page_note"]


async def test_restaurants_empty_later_page_preserves_total(api):
    api[RESTAURANTS_PATH] = {
        "meta": {"pageSize": 10, "pageNumber": 25, "totalItems": 192},
        "config": None,
        "content": [],
    }
    out = await restaurants(LAT, LONG, page=25)
    assert out["coverage"] == "available"
    assert out["vendors"] == [] and out["total"] == 192
    assert "lower page" in out["page_note"]


async def test_collection_404_is_unavailable(api):
    out = await collection("تپ-تایم", 38.080028, 46.2919)
    assert out["coverage"] == "unavailable" and out["total"] == 0


async def test_catalog_paging_and_coords_are_validated(api):
    with pytest.raises(ApiError):
        await search_products("پیتزا", LAT, LONG, page=0)
    with pytest.raises(ApiError):
        await search_products("پیتزا", LAT, LONG, page_size=51)
    with pytest.raises(ApiError):
        await restaurants(200.0, LONG)
    with pytest.raises(ApiError):
        await collection("تپ-تایم", LAT, LONG, page_size=0)
    assert api.calls == []

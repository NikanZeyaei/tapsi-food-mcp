"""Behavior tests for the vendor menu/costs/review tools (src/tapsi_food_mcp/vendor.py)."""

import httpx
import pytest

from tapsi_food_mcp import vendor
from tapsi_food_mcp.http import ApiError

pytestmark = pytest.mark.anyio

LAT, LONG = 35.6892, 51.389

MENU_PATH = "/v2/api/Vendor/2y97wk/vendor"
PROFILE_PATH = "/v1/api/Vendor/2y97wk/profile"


def _menu_body(**vendor_overrides):
    vendor_block = {
        "vendorCode": "2y97wk",
        "vendorStatus": "Open",
        "vendorHasInServiceState": True,
        "title": "فست فود مارچوبه",
        "minimumBasket": 400000,
        "packingPrice": 0,
        "tax": False,
        "deliveryTypes": [{"deliveryType": "Ofood", "deliveryPrice": 61500}],
        "eta": 55,
        "rate": None,
        "ratesCount": None,
        "businessTypeId": 1,
        "cityId": 2,
    }
    vendor_block.update(vendor_overrides)
    return {
        "status": True,
        "message": "",
        "data": {
            "vendor": vendor_block,
            "review": {"rate": 4.2, "rateCount": 1626},
            "vendorCarousels": [],
            "categories": [
                {
                    "categoryId": "189516",
                    "categoryName": "پیتزا ایتالیایی",
                    "products": [
                        {
                            "productId": "1472033",
                            "productRate": 0,
                            "productName": "پیتزا رست بیف ایتالیایی",
                            "productDescription": "خمیر ایتالیایی، گوشت رست شده",
                            "images": ["https://cdn.tapsi.food/vendor/product/img.jpg"],
                            "productVariations": [
                                {
                                    "productVariationId": "1982313",
                                    "productVariationName": "پیتزا رست بیف ایتالیایی",
                                    "productVariationDescription": None,
                                    "price": 1400000,
                                    "discountRatio": 0,
                                    "priceAfterDiscount": 1400000,
                                    "stock": 100,
                                    "capacity": 10,
                                    "discountStock": 0,
                                    "mandatoryOptionCategoryIds": [],
                                    "optionCategories": [
                                        {
                                            "optionCategoryId": "68884",
                                            "optionCategoryName": "کارد و چنگال",
                                            "capacity": 2,
                                            "isMandatory": False,
                                            "options": [
                                                {
                                                    "optionId": "198816",
                                                    "optionName": "کارد",
                                                    "price": 3500,
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "productId": "1472034",
                            "productRate": None,
                            "productName": "پیتزا مارگاریتا یک نفره",
                            "productDescription": None,
                            "images": None,
                            "productVariations": [
                                {
                                    "productVariationId": "1982303",
                                    "productVariationName": "پیتزا مارگاریتا یک نفره",
                                    "productVariationDescription": None,
                                    "price": 395000,
                                    "discountRatio": 0,
                                    "priceAfterDiscount": 395000,
                                    "stock": 0,
                                    "capacity": 10,
                                    "discountStock": 0,
                                    "mandatoryOptionCategoryIds": [],
                                    "optionCategories": [],
                                }
                            ],
                        },
                    ],
                }
            ],
        },
    }


def _profile_body(**info_overrides):
    info = {
        "vendorCode": "2y97wk",
        "title": "فست فود مارچوبه",
        "vendorStatus": "Close",
        "minimumBasket": 300000,
        "businessTypeId": 1,
        "cityId": 2,
        "eta": 55,
        "address": {
            "addressDetails": "میدان توحید، ابتدای ستارخان",
            "location": {"latitude": 35.707, "longitude": 51.376},
        },
    }
    info.update(info_overrides)
    return {
        "statusCode": 200,
        "message": "Success",
        "data": {
            "info": info,
            "shift": {},
            "insight": {
                "reviews": [
                    {
                        "vendorCode": "2y97wk",
                        "writerName": "نگین حیدریان",
                        "createdAt": "2026-10-13T17:18:30.621Z",
                        "orderRating": 5,
                        "orderItems": [
                            {
                                "productName": "قارچ سوخاری",
                                "rating": 5,
                                "comment": "خیلی عالی و تازه بود",
                                "replies": [],
                            },
                            {
                                "productName": "برگر با سس قارچ",
                                "rating": 5,
                                "comment": "همه چی عالی بود",
                                "replies": [],
                            },
                        ],
                    }
                ],
                "rateDetails": {"rate": 4.24492},
            },
            "meta": {"pageSize": 20, "pageNumber": 0, "total": 88},
        },
    }


async def test_vendor_menu_maps_nesting_stock_options_and_toman(api):
    api[MENU_PATH] = _menu_body()
    out = await vendor.vendor_menu("2y97wk", LAT, LONG)
    assert out["coverage"] == "available" and out["deliverable"] is True
    assert out["vendor"]["minimum_basket"] == 400000  # Toman unchanged
    assert out["total_categories"] == 1 and out["total_products"] == 2
    assert out["total_variations"] == 2
    in_stock, sold_out = out["categories"][0]["products"]
    assert in_stock["variations"][0]["final_price"] == 1400000
    assert in_stock["variations"][0]["available"] is True
    assert in_stock["variations"][0]["option_categories"][0]["options"] == [
        {"id": "198816", "name": "کارد", "price": 3500}
    ]
    assert sold_out["variations"][0]["stock"] == 0
    assert sold_out["variations"][0]["available"] is False


async def test_vendor_menu_preserves_nullable_fields(api):
    api[MENU_PATH] = _menu_body()
    out = await vendor.vendor_menu("2y97wk", LAT, LONG)
    # Rating lives in data.review, not data.vendor (raw vendor-detail.json).
    assert out["vendor"]["rate"] == 4.2
    assert out["vendor"]["rates_count"] == 1626
    sold_out = out["categories"][0]["products"][1]
    assert sold_out["rate"] is None and sold_out["description"] is None
    assert sold_out["images"] is None
    assert sold_out["variations"][0]["description"] is None


async def test_vendor_menu_missing_review_block_leaves_rating_null(api):
    body = _menu_body()
    body["data"].pop("review", None)
    api[MENU_PATH] = body
    out = await vendor.vendor_menu("2y97wk", LAT, LONG)
    assert out["vendor"]["rate"] is None
    assert out["vendor"]["rates_count"] is None


async def test_order_costs_falls_back_to_menu_eta_when_profile_eta_null(api):
    api[MENU_PATH] = _menu_body()  # menu eta 55
    api[PROFILE_PATH] = _profile_body(eta=None)
    out = await vendor.order_costs("2y97wk", LAT, LONG)
    assert out["eta"] == 55


async def test_vendor_menu_query_filters_locally_without_second_fetch(api):
    api[MENU_PATH] = _menu_body()
    out = await vendor.vendor_menu("2y97wk", LAT, LONG, query="مارگاریتا")
    assert out["query"] == "مارگاریتا"
    assert out["total_products"] == 1
    assert [p["name"] for p in out["categories"][0]["products"]] == ["پیتزا مارگاریتا یک نفره"]
    menu_calls = [c for c in api.calls if c.url.path == MENU_PATH]
    assert len(menu_calls) == 1


async def test_vendor_menu_out_of_coverage_is_not_deliverable(api):
    api[MENU_PATH] = _menu_body(
        vendorStatus="OutOfCoverage",
        deliveryTypes=[{"deliveryType": "Unknown", "deliveryPrice": -1}],
    )
    out = await vendor.vendor_menu("2y97wk", 32.651789, 51.693768)
    assert out["coverage"] == "unavailable"
    assert out["deliverable"] is False
    assert out["coverage_reason"]
    assert out["total_products"] == 2  # full menu still returned, never orderable


async def test_vendor_menu_unknown_code_maps_404_to_unavailable(api):
    out = await vendor.vendor_menu("nope01", LAT, LONG)
    assert out["coverage"] == "unavailable" and out["deliverable"] is False
    assert out["categories"] == []


async def test_vendor_menu_rejects_bad_code_before_any_request(api):
    with pytest.raises(ApiError):
        await vendor.vendor_menu("2y97wk/x", LAT, LONG)
    with pytest.raises(ApiError):
        await vendor.vendor_menu("  ", LAT, LONG)
    assert api.calls == []


async def test_order_costs_surfaces_disagreement_with_sources(api):
    api[MENU_PATH] = _menu_body()  # menu: 400000 / Open
    api[PROFILE_PATH] = _profile_body()  # profile: 300000 / Close
    out = await vendor.order_costs("2y97wk", LAT, LONG)
    assert out["minimum_basket"] == 300000  # user-facing profile preferred
    assert out["minimum_basket_sources"] == {"menu": 400000, "profile": 300000}
    assert out["vendor_status_sources"] == {"menu": "Open", "profile": "Close"}
    assert len(out["source_warnings"]) == 2
    assert out["delivery_types"] == [{"type": "Ofood", "price": 61500, "source": "menu"}]
    assert out["packing_price"] == 0 and out["tax_included"] is False
    assert "coupon" not in str(out).lower()
    assert len([c for c in api.calls if c.url.path == MENU_PATH]) == 1
    assert len([c for c in api.calls if c.url.path == PROFILE_PATH]) == 1


async def test_order_costs_profile_failure_keeps_menu_coverage(api):
    api[MENU_PATH] = _menu_body()
    api[PROFILE_PATH] = lambda r: httpx.Response(500, text="boom")
    out = await vendor.order_costs("2y97wk", LAT, LONG)
    assert out["profile_status"] == "error" and out["profile_error"]
    assert out["minimum_basket"] == 400000  # menu fallback, no fabricated quote
    assert out["coverage"] == "available" and out["deliverable"] is True
    assert out["source_warnings"]


async def test_order_costs_preferred_close_is_not_deliverable(api):
    api[MENU_PATH] = _menu_body()  # menu: Open at this point
    api[PROFILE_PATH] = _profile_body()  # profile: Close
    out = await vendor.order_costs("2y97wk", LAT, LONG)
    assert out["coverage"] == "available"  # menu geographic coverage preserved
    assert out["deliverable"] is False  # preferred Close is never orderable
    assert out["vendor_status"] == "Close"
    assert out["coverage_reason"] and "Close" in out["coverage_reason"]


async def test_vendor_menu_exposes_mandatory_option_category_ids(api):
    body = _menu_body()
    variation = body["data"]["categories"][0]["products"][0]["productVariations"][0]
    variation["mandatoryOptionCategoryIds"] = ["68884"]
    api[MENU_PATH] = body
    out = await vendor.vendor_menu("2y97wk", LAT, LONG)
    assert out["categories"][0]["products"][0]["variations"][0]["mandatory_option_category_ids"] == ["68884"]


async def test_vendor_reviews_exposes_shift_schedule(api):
    body = _profile_body()
    schedule = {
        "todayOperatingSchedule": {
            "dayOfWeek": 3,
            "workingHours": [{"startTime": "11:00:00", "endTime": "23:45:00"}],
        }
    }
    body["data"]["shift"] = schedule
    api[PROFILE_PATH] = body
    out = await vendor.vendor_reviews("2y97wk", page=0, page_size=20)
    assert out["shift"] == schedule


async def test_vendor_reviews_nesting_pagination_and_next_page(api):
    api[PROFILE_PATH] = _profile_body()
    out = await vendor.vendor_reviews("2y97wk", page=0, page_size=20)
    assert out["total"] == 88 and out["page"] == 0 and out["next_page"] == 1
    (review,) = out["reviews"]
    assert review["writer_name"] == "نگین حیدریان" and review["order_rating"] == 5
    assert [i["comment"] for i in review["order_items"]] == [
        "خیلی عالی و تازه بود",
        "همه چی عالی بود",
    ]
    assert out["info"]["minimum_basket"] == 300000
    params = api.calls[0].url.params
    assert params["pageNumber"] == "0" and params["pageSize"] == "20"


async def test_vendor_reviews_last_page_has_no_next_page(api):
    body = _profile_body()
    body["data"]["meta"] = {"pageSize": 20, "pageNumber": 4, "total": 88}
    body["data"]["insight"]["reviews"] = []
    api[PROFILE_PATH] = body
    out = await vendor.vendor_reviews("2y97wk", page=4, page_size=20)
    assert out["reviews"] == [] and out["next_page"] is None


async def test_vendor_reviews_rejects_one_based_page(api):
    with pytest.raises(ApiError):
        await vendor.vendor_reviews("2y97wk", page=-1)
    assert api.calls == []


async def test_product_reviews_empty_reports_zero_without_paging(api):
    api["/v1/api/RateAndReview/1867178/review"] = {
        "statusCode": 200,
        "message": "Success",
        "data": {"reviews": [], "rateDetail": {"rate": 0}},
    }
    out = await vendor.product_reviews(1867178)
    assert out == {
        "product_id": 1867178,
        "total": 0,
        "rate": 0,
        "source": "v1/api/RateAndReview/1867178/review",
        "reviews": [],
    }
    assert "page" not in out and "next_page" not in out


async def test_product_reviews_nonempty_maps_comments(api):
    api["/v1/api/RateAndReview/1640969/review"] = {
        "statusCode": 200,
        "message": "Success",
        "data": {
            "reviews": [
                {
                    "rating": 5,
                    "comment": "تازه بود",
                    "createdAt": "2026-10-12T10:00:00Z",
                    "replies": [],
                },
                {"rating": None, "comment": None, "createdAt": None, "replies": None},
            ],
            "rateDetail": {"rate": 4.5},
        },
    }
    out = await vendor.product_reviews(1640969)
    assert out["total"] == 2 and out["rate"] == 4.5
    assert out["reviews"][0]["comment"] == "تازه بود"
    assert out["reviews"][1] == {
        "rating": None,
        "comment": None,
        "created_at": None,
        "replies": [],
    }


async def test_product_reviews_rejects_bad_id_before_any_request(api):
    with pytest.raises(ApiError):
        await vendor.product_reviews(0)
    assert api.calls == []

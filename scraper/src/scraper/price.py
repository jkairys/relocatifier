"""Price parsing for OTH listings — pure, no I/O.

Ported from school-map `price_normaliser/parser.py`, narrowed to the OTH path.

RECENTLYSOLD price comes from `lastSale.salePrice` (an integer, not a display
string). Per the contract a `salePrice` of 0 or missing means the sale price is
SUPPRESSED (restricted source) — we map it to `price=None` / `PriceKind.UNKNOWN`,
never `0`, so suppressed sales never surface a fake zero price downstream.
"""

from __future__ import annotations

from typing import Any

from scraper.vendor import Category, NormalisedPrice, PriceKind


def parse_oth_listing(raw: dict, category: Category) -> NormalisedPrice:
    """Extract and classify the price for an OTH listing item.

    Only RECENTLYSOLD is exercised in v1; ForSale/ForRent fall through to an
    UNKNOWN result since this service never queries those categories.
    """
    if category is Category.RECENTLYSOLD:
        last_sale = raw.get("lastSale") or {}
        price = _as_int_optional(last_sale.get("salePrice"))
        # salePrice 0 (or missing) == suppressed: store/export null, not zero.
        if not price:
            return NormalisedPrice(kind=PriceKind.UNKNOWN, low=None, high=None, display=None)
        return NormalisedPrice(
            kind=PriceKind.PRICE, low=price, high=None, display=str(price)
        )

    return NormalisedPrice(kind=PriceKind.UNKNOWN, low=None, high=None, display=None)


def _as_int_optional(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

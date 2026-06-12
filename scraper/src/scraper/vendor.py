"""Vendor-neutral listing models and OTH request/response types.

Ported from school-map (`vendor_clients/base.py`, `vendor_clients/oth/types.py`,
`price_normaliser/types.py`). Trimmed to the recentlysold v1 surface: ForSale/
ForRent categories are kept in the enums for payload parity but are not exercised.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Vendor(str, Enum):
    OTH = "oth"


class Category(str, Enum):
    """Search categories. Only RECENTLYSOLD is exercised in v1."""

    FORSALE = "forsale"
    FORRENT = "forrent"
    RECENTLYSOLD = "recentlysold"

    @property
    def oth_name(self) -> str:
        """Mixed-case form OTH's API expects in the request payload."""
        return _OTH_CATEGORY_NAMES[self]


_OTH_CATEGORY_NAMES = {
    Category.FORSALE: "SaleListing",
    Category.FORRENT: "RentalListing",
    Category.RECENTLYSOLD: "RecentlySold",
}


class PriceKind(str, Enum):
    PRICE = "price"
    RANGE = "range"
    AUCTION = "auction"
    EOI = "eoi"
    CONTACT = "contact"
    RENT_WEEKLY = "rent_weekly"
    UNKNOWN = "unknown"


class NormalisedPrice(BaseModel):
    """Classified price value object produced by the price normaliser."""

    model_config = ConfigDict(frozen=True)

    kind: PriceKind
    low: Optional[int] = None
    high: Optional[int] = None
    display: Optional[str] = None


class ResolvedSuburb(BaseModel):
    """A suburb with everything the OTH search payload needs.

    Built at watchlist-add time from metrics.json (name/state) plus the OTH
    slug (the source of the postcode). `oth_slug` is provenance only.
    """

    model_config = ConfigDict(frozen=True)

    sal_code: str
    name: str
    state: str
    postcode: str
    oth_slug: str


class VendorListing(BaseModel):
    """Vendor-neutral listing model produced by the OTH parser."""

    model_config = ConfigDict(frozen=True)

    # Identity
    source: Vendor
    external_listing_id: str
    external_property_id: Optional[str] = None
    listing_url: Optional[str] = None

    # Address
    formatted_address: str
    postcode: str
    state: Optional[str] = None
    suburb_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Features
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    land_size_sqm: Optional[float] = None
    property_type: Optional[str] = None

    # Marketing
    title: Optional[str] = None
    status: Optional[str] = None
    agent_name: Optional[str] = None
    agency_name: Optional[str] = None

    # Price
    raw_price_display: Optional[str] = None
    price: Optional[int] = None
    price_high: Optional[int] = None
    price_kind: PriceKind = PriceKind.UNKNOWN

    observed_at: datetime


class SearchPage(BaseModel):
    """One parsed OTH search response page."""

    model_config = ConfigDict(frozen=True)

    listings: list[VendorListing]
    raw_payloads: list[dict]
    page: int
    has_next: bool
    total: Optional[int] = None

"""Parse OTH search responses into vendor-neutral `VendorListing` objects.

Ported from school-map `vendor_clients/oth/parser.py`. Defensive about missing
fields: OTH omits `address.location` for some older sold properties, omits
`landSize` for apartments, and so on. Anything optional in `VendorListing` may
legitimately be None. `landSize` is trusted only when `landSizeUnit` is
"squareMeter" — any other unit drops the field rather than emitting wrong sqm.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from scraper.price import parse_oth_listing
from scraper.vendor import Category, SearchPage, Vendor, VendorListing

_LAND_SIZE_UNIT_SQM = "squareMeter"


class ParseError(ValueError):
    """Raised when an OTH response cannot be parsed into listings."""


def parse_search_response(
    body: dict[str, Any],
    *,
    category: Category,
    page: int,
) -> SearchPage:
    """Parse one OTH search response page into a vendor-neutral `SearchPage`."""
    if not isinstance(body, dict):
        raise ParseError(f"expected JSON object, got {type(body).__name__}")

    raw_content = body.get("content")
    if raw_content is None:
        raise ParseError("response missing 'content' array")
    if not isinstance(raw_content, list):
        raise ParseError("response 'content' is not a list")

    observed_at = datetime.now(tz=timezone.utc)

    listings: list[VendorListing] = []
    raw_payloads: list[dict] = []
    for i, item in enumerate(raw_content):
        if not isinstance(item, dict):
            raise ParseError(f"content[{i}] is not an object: {type(item).__name__}")
        listings.append(_parse_listing(item, category, index=i, observed_at=observed_at))
        raw_payloads.append(item)

    total = _as_int(body.get("totalElements"), default=len(listings))
    page_number = _as_int(body.get("number"), default=page)
    # Default `last` to True when missing so malformed pagination can't loop forever.
    has_next = not bool(body.get("last", True))

    return SearchPage(
        listings=listings,
        raw_payloads=raw_payloads,
        total=total,
        page=page_number,
        has_next=has_next,
    )


def _parse_listing(
    item: dict[str, Any],
    category: Category,
    *,
    index: int,
    observed_at: datetime,
) -> VendorListing:
    oth_id = item.get("othPropertyId")
    if oth_id is None or oth_id == "":
        raise ParseError(f"content[{index}] missing 'othPropertyId'")

    address = item.get("address") or {}
    formatted_address = address.get("formattedAddress") or ""
    if not formatted_address:
        raise ParseError(f"content[{index}] missing 'address.formattedAddress'")

    postcode = address.get("postCode") or ""
    location = address.get("location") or {}

    normalised = parse_oth_listing(item, category)
    agent_name, agency_name = _extract_agent_and_agency(item, category)
    status = _derive_status(item, category)

    external_property_id = str(oth_id)
    # OTH search-list responses carry no stable per-campaign listing id; derive
    # one from the property id (per-campaign dedup is therefore approximate).
    external_listing_id = external_property_id

    return VendorListing(
        source=Vendor.OTH,
        external_listing_id=external_listing_id,
        external_property_id=external_property_id,
        listing_url=_extract_oth_web_url(item.get("links")),
        formatted_address=formatted_address,
        postcode=str(postcode),
        state=address.get("stateCode") or None,
        suburb_name=address.get("suburb") or None,
        latitude=_as_float(location.get("lat")),
        longitude=_as_float(location.get("lon")),
        bedrooms=_as_int_optional(item.get("beds")),
        bathrooms=_as_int_optional(item.get("baths")),
        parking=_as_int_optional(item.get("carSpaces")),
        land_size_sqm=_extract_land_size_sqm(item),
        property_type=item.get("type"),
        agent_name=agent_name,
        agency_name=agency_name,
        title=formatted_address,
        status=status,
        raw_price_display=normalised.display,
        price=normalised.low,
        price_high=normalised.high,
        price_kind=normalised.kind,
        observed_at=observed_at,
    )


def _extract_agent_and_agency(
    item: dict[str, Any], category: Category
) -> tuple[Optional[str], Optional[str]]:
    if category is Category.RECENTLYSOLD:
        agency = (item.get("lastSale") or {}).get("sellingAgency") or {}
    else:
        agency = (item.get("listing") or {}).get("agency") or {}

    agency_name = agency.get("name") or None

    agents = agency.get("agents") or []
    agent_name: Optional[str] = None
    if agents:
        first = agents[0]
        if isinstance(first, dict):
            agent_name = first.get("name") or None

    return agent_name, agency_name


def _derive_status(item: dict[str, Any], category: Category) -> str:
    if category is Category.RECENTLYSOLD:
        return "sold"
    if category is Category.FORRENT:
        return "current"
    if item.get("underOffer") is True:
        return "under_offer"
    return "current"


def _extract_land_size_sqm(item: dict[str, Any]) -> Optional[float]:
    raw = item.get("landSize")
    if raw is None:
        return None
    unit = item.get("landSizeUnit")
    if unit and unit != _LAND_SIZE_UNIT_SQM:
        # Unknown unit — drop rather than emit a wrong sqm number.
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _extract_oth_web_url(links: Any) -> Optional[str]:
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "othWebUrl":
            href = link.get("href")
            if isinstance(href, str) and href:
                return href
    return None


def _as_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_int_optional(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

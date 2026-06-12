"""OTH search-API request payload builder — pure, no I/O.

Ported from school-map `vendor_clients/oth/payload.py`, narrowed to the
RECENTLYSOLD path this service uses. Every filter dimension is a flat
string-valued key inside the single per-suburb target under
`query.queries[0]`; OTH rejects nested `{min, max}` structures.
"""

from __future__ import annotations

from typing import Any

from scraper.vendor import Category, ResolvedSuburb

SEARCH_URL = "https://www.onthehouse.com.au/odin/api/composite/search"
DEFAULT_PAGE_SIZE = 24

_CATEGORY_SORT: dict[Category, list[dict[str, str]]] = {
    Category.FORSALE: [{"listing.listedDate": "desc"}],
    Category.FORRENT: [{"listing.listedDate": "desc"}],
    Category.RECENTLYSOLD: [{"lastSale.eventDate": "desc"}],
}

# ForSale/ForRent carry an explicit status discriminator; RecentlySold does not.
_REQUIRES_STATUS_CURRENT = {Category.FORSALE, Category.FORRENT}


def build_search_payload(
    suburb: ResolvedSuburb,
    category: Category,
    page: int,
    *,
    size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Build the JSON body for a paginated OTH search request.

    `page` is 0-indexed. `suburb.name` is lowercased and space-separated
    (e.g. "bli bli"); `suburb.state` is uppercased; `postCode` comes from the
    resolved slug.
    """
    target: dict[str, Any] = {
        "category": category.oth_name,
        "stateCode": suburb.state.upper(),
        "suburb": suburb.name.lower(),
        "postCode": suburb.postcode,
    }
    if category in _REQUIRES_STATUS_CURRENT:
        target["status"] = "current"

    return {
        "size": size,
        "number": page,
        "sort": _CATEGORY_SORT[category],
        "query": {"queries": [target]},
    }

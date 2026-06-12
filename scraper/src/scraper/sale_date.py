"""Extract the settled-sale date from an OTH recentlysold raw payload.

Ported verbatim (logic) from school-map `sale_date_extractor.py`. Pure: no DB,
no I/O, no async. The sale date lives at `lastSale.eventDate` as an ISO-8601
date string; absent or unparseable values yield None rather than raising.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

_CANDIDATE_PATHS: list[tuple[str, str]] = [
    ("lastSale", "eventDate"),
]


def extract_sale_date(raw_payload: dict[str, Any]) -> date | None:
    """Return the settled-sale date from an OTH recentlysold payload, or None."""
    for outer_key, inner_key in _CANDIDATE_PATHS:
        outer = raw_payload.get(outer_key)
        if not isinstance(outer, dict):
            continue
        raw_value = outer.get(inner_key)
        if raw_value is None:
            continue
        parsed = _parse_date(raw_value)
        if parsed is not None:
            return parsed
    return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        logger.debug("sale_date: could not parse %r as a date: %s", value, exc)
        return None

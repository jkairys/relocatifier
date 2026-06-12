"""Slug resolution at watchlist-add time (ADR-0007).

A scrape job is keyed by `sal_code`; the OTH slug is resolved exactly once, at
add time, refusing ambiguous names rather than guessing. We:

1. read the SAL's display name + state from the metrics.json artifact;
2. match the normalised name against OTH sitemap slugs (`<name>-<postcode>`)
   within that state;
3. resolve only on exactly one candidate. Zero or multiple → refuse (the API
   surfaces a 422 naming the candidates and referencing issue #2).

Issue #2's dominant-POA disambiguation is not yet implemented, so same-name
collisions within a state are refused honestly, not resolved.

The sitemap parser is adapted from etl's `house_prices.py` (the per-state `<loc>`
regex + `normalise_name`) rather than importing the etl package, whose build
deps (geopandas/pandas) are far heavier than this single regex needs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

OTH_SITEMAP_URL = "https://www.onthehouse.com.au/sitemap/suburb_profiles.xml"

# slug format: <suburb-name-hyphenated>-<4-digit-postcode>, e.g. "bli-bli-4560".
_SITEMAP_RE = re.compile(
    r"<loc>https://www\.onthehouse\.com\.au/property/([a-z]{2,3})/([a-z0-9-]+-\d{4})</loc>"
)

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalise_name(name: str) -> str:
    """Canonical matching form: uppercase, punctuation/whitespace collapsed.

    Mirrors etl `crosswalk.normalise_name`. "Bli Bli" -> "BLI BLI".
    """
    return _NON_ALNUM.sub(" ", name.upper()).strip()


class SalNotFoundError(LookupError):
    """The SAL code is not present in metrics.json (→ 404)."""


class SlugResolutionError(ValueError):
    """The slug could not be resolved unambiguously (→ 422).

    `candidates` names the slugs considered so the caller can report an honest
    data gap. Empty means no candidate matched.
    """

    def __init__(self, message: str, *, candidates: list[str]) -> None:
        super().__init__(message)
        self.candidates = candidates


@dataclass(frozen=True)
class ResolvedSAL:
    """A SAL resolved to its OTH slug, ready to store on the watchlist."""

    sal_code: str
    name: str
    state: str
    oth_slug: str
    postcode: str


def lookup_sal(metrics_path: Path, sal_code: str) -> tuple[str, str]:
    """Return (name, state) for `sal_code` from metrics.json, or raise."""
    data = json.loads(Path(metrics_path).read_text())
    record = (data.get("suburbs") or {}).get(sal_code)
    if record is None:
        raise SalNotFoundError(f"SAL {sal_code} not in metrics.json")
    return record["name"], record["state"]


def parse_oth_sitemap(xml_text: str) -> dict[tuple[str, str], list[str]]:
    """Slugs keyed by (normalised name, uppercased state).

    A name can map to several slugs (same name, different postcodes within a
    state); the ambiguity is refused at resolution time.
    """
    by_key: dict[tuple[str, str], list[str]] = {}
    for state, slug in _SITEMAP_RE.findall(xml_text):
        name = normalise_name(slug.rsplit("-", 1)[0])
        by_key.setdefault((name, state.upper()), []).append(slug)
    return by_key


def load_sitemap(
    cache_path: Path,
    *,
    client: Optional[httpx.Client] = None,
    force_refresh: bool = False,
) -> str:
    """Return the OTH sitemap XML, fetching and caching it under `cache_path`.

    Tests pass a fake `client` (or a pre-populated cache file) so no real
    network call is made.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not force_refresh:
        return cache_path.read_text()

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        response = client.get(OTH_SITEMAP_URL, timeout=30.0)
        response.raise_for_status()
        xml_text = response.text
    finally:
        if owns_client:
            client.close()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(xml_text)
    return xml_text


def resolve_slug(
    sal_code: str,
    *,
    metrics_path: Path,
    sitemap_cache_path: Path,
    client: Optional[httpx.Client] = None,
) -> ResolvedSAL:
    """Resolve `sal_code` to its OTH slug, refusing ambiguity.

    Raises `SalNotFoundError` (404) when the SAL is unknown, `SlugResolutionError`
    (422) when zero or more-than-one sitemap slugs match.
    """
    name, state = lookup_sal(metrics_path, sal_code)
    xml_text = load_sitemap(sitemap_cache_path, client=client)
    by_key = parse_oth_sitemap(xml_text)

    candidates = by_key.get((normalise_name(name), state.upper()), [])
    if not candidates:
        raise SlugResolutionError(
            f"No OTH suburb-profile slug for {name} ({state}). "
            f"The suburb may not be on OnTheHouse, or its name differs from the SAL "
            f"name. Refusing to guess (see issue #2).",
            candidates=[],
        )
    if len(candidates) > 1:
        raise SlugResolutionError(
            f"Ambiguous OTH slug for {name} ({state}): {', '.join(sorted(candidates))}. "
            f"Dominant-POA disambiguation is not implemented (issue #2); refusing to guess.",
            candidates=sorted(candidates),
        )

    slug = candidates[0]
    postcode = slug.rsplit("-", 1)[1]
    return ResolvedSAL(
        sal_code=sal_code,
        name=name,
        state=state.upper(),
        oth_slug=slug,
        postcode=postcode,
    )

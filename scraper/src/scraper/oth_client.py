"""OTH search client — plain httpx, no browser/camoufox bootstrap.

The spike (tmp/oth_spike.py + oth_spike_response.json) proved that a plain
httpx POST with realistic browser headers and no cookies is accepted by OTH's
search API. We reproduce those exact headers here. The anti-bot sentinel check
(403/429 status or a challenge-page sentinel in the body) is kept: on detection
we raise `AntiBotError` and the run loop aborts honestly — no retries past one
caller-driven backoff.

Synchronous by design: this is a single-flight, one-suburb-at-a-time service,
so the async ScrapeSession machinery from school-map is unnecessary.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

import httpx

from scraper.oth_parser import parse_search_response
from scraper.oth_payload import SEARCH_URL, build_search_payload
from scraper.vendor import Category, ResolvedSuburb, SearchPage

logger = logging.getLogger(__name__)

OTH_ORIGIN = "https://www.onthehouse.com.au"
OTH_HOST = "onthehouse.com.au"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Realistic browser headers proven by the spike. Cookies are deliberately
# absent — the spike succeeded without them.
_BASE_HEADERS: dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-AU,en;q=0.9",
    "content-type": "application/json",
    "origin": OTH_ORIGIN,
    "user-agent": _USER_AGENT,
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

# Sentinel substrings of an anti-bot challenge page (Cloudflare / Imperva).
_SENTINEL_STRINGS: tuple[str, ...] = (
    "Checking your browser",
    "cf-browser-verification",
    "cf_chl_opt",
    "Just a moment",
    "Attention Required! | Cloudflare",
    "_Incapsula_Resource",
    "Request unsuccessful. Incapsula",
)


class AntiBotError(RuntimeError):
    """Raised when OTH responds with an anti-bot block. The run aborts."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        sentinel: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.sentinel = sentinel


class RateLimiter:
    """Polite jittered spacing between requests to a host.

    Blocks until at least `min_interval` (plus up to `jitter`) seconds have
    elapsed since the previous acquire. Clock/sleep/rng are injectable so tests
    drive it without real waits.
    """

    def __init__(
        self,
        min_interval_s: float = 1.5,
        max_interval_s: float = 3.0,
        *,
        clock=time.monotonic,
        sleep=time.sleep,
        rng=random.random,
    ) -> None:
        self._min_interval = min_interval_s
        self._jitter = max(0.0, max_interval_s - min_interval_s)
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self._next_available = 0.0

    def acquire(self) -> None:
        now = self._clock()
        wait = self._next_available - now
        if wait > 0:
            self._sleep(wait)
            now = self._clock()
        jitter = self._rng() * self._jitter if self._jitter > 0 else 0.0
        self._next_available = now + self._min_interval + jitter


def _check_anti_bot(response: httpx.Response) -> None:
    """Raise `AntiBotError` on a 403/429 status or a sentinel in the body."""
    if response.status_code in (403, 429):
        raise AntiBotError(
            f"OTH responded {response.status_code}; treating as anti-bot block",
            status_code=response.status_code,
        )
    try:
        body = response.text
    except Exception:  # noqa: BLE001 - body unreadable means we can't sentinel-check
        return
    for sentinel in _SENTINEL_STRINGS:
        if sentinel in body:
            raise AntiBotError(
                f"Anti-bot sentinel detected in response body: {sentinel!r}",
                status_code=response.status_code,
                sentinel=sentinel,
            )


class OTHClient:
    """Issues paginated recentlysold searches against OTH and parses them.

    Rate limiting is applied before each request. The HTTP client is injectable
    (`client`) so tests pass an `httpx.Client(transport=httpx.MockTransport(...))`.
    """

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        rate_limiter: Optional[RateLimiter] = None,
        page_size: int = 24,
        timeout_s: float = 30.0,
    ) -> None:
        self._client = client or httpx.Client(follow_redirects=True)
        self._owns_client = client is None
        self._rate_limiter = rate_limiter or RateLimiter()
        self._page_size = page_size
        self._timeout = timeout_s

    def search(
        self,
        suburb: ResolvedSuburb,
        page: int,
        *,
        category: Category = Category.RECENTLYSOLD,
    ) -> SearchPage:
        """Fetch one page; raises `AntiBotError` on a block, `ParseError` on bad JSON."""
        payload = build_search_payload(suburb, category, page, size=self._page_size)
        referer = f"{OTH_ORIGIN}/sold/{suburb.state.lower()}/{suburb.oth_slug}"
        headers = {**_BASE_HEADERS, "referer": referer}

        self._rate_limiter.acquire()
        logger.debug(
            "OTH search: suburb=%s/%s page=%d", suburb.name, suburb.postcode, page
        )
        response = self._client.post(
            SEARCH_URL, json=payload, headers=headers, timeout=self._timeout
        )
        _check_anti_bot(response)
        response.raise_for_status()
        return parse_search_response(response.json(), category=category, page=page)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OTHClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

"""OTH client tests: pagination, rate limiting, anti-bot abort (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from scraper.oth_client import AntiBotError, OTHClient, RateLimiter
from scraper.vendor import ResolvedSuburb

SUBURB = ResolvedSuburb(
    sal_code="30900", name="Bli Bli", state="QLD", postcode="4560", oth_slug="bli-bli-4560"
)


class TestRateLimiter:
    def test_spaces_requests(self):
        slept: list[float] = []
        ticks = iter([0.0, 0.0, 0.0])  # clock returns 0 each call

        limiter = RateLimiter(
            min_interval_s=1.5,
            max_interval_s=3.0,
            clock=lambda: next(ticks),
            sleep=slept.append,
            rng=lambda: 0.0,
        )
        limiter.acquire()  # first acquire: no wait
        limiter.acquire()  # second: must wait min_interval since clock didn't advance
        assert slept == [1.5]

    def test_jitter_within_bounds(self):
        limiter = RateLimiter(
            min_interval_s=1.5, max_interval_s=3.0,
            clock=lambda: 0.0, sleep=lambda _: None, rng=lambda: 1.0,
        )
        limiter.acquire()
        # next_available = 0 + 1.5 + 1.0*1.5 = 3.0 (upper bound)
        assert limiter._next_available == pytest.approx(3.0)


class TestClientPagination:
    def _client(self, captured):
        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"content": [], "number": json.loads(request.content)["number"], "last": True},
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_builds_recentlysold_payload(self):
        captured: list[dict] = []
        client = OTHClient(client=self._client(captured), rate_limiter=_no_wait())
        client.search(SUBURB, page=0)
        body = captured[0]
        assert body["number"] == 0
        q = body["query"]["queries"][0]
        assert q["category"] == "RecentlySold"
        assert q["suburb"] == "bli bli"
        assert q["stateCode"] == "QLD"
        assert q["postCode"] == "4560"
        assert "status" not in q  # recentlysold omits status

    def test_referer_uses_slug(self):
        sent_headers: list[dict] = []

        def handler(request):
            sent_headers.append(dict(request.headers))
            return httpx.Response(200, json={"content": [], "last": True})

        client = OTHClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            rate_limiter=_no_wait(),
        )
        client.search(SUBURB, page=0)
        assert sent_headers[0]["referer"].endswith("/sold/qld/bli-bli-4560")


class TestAntiBot:
    def test_403_raises(self):
        def handler(request):
            return httpx.Response(403, text="blocked")

        client = OTHClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            rate_limiter=_no_wait(),
        )
        with pytest.raises(AntiBotError) as exc:
            client.search(SUBURB, page=0)
        assert exc.value.status_code == 403

    def test_sentinel_body_raises(self):
        def handler(request):
            return httpx.Response(200, text="Just a moment...")

        client = OTHClient(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            rate_limiter=_no_wait(),
        )
        with pytest.raises(AntiBotError) as exc:
            client.search(SUBURB, page=0)
        assert "Just a moment" in str(exc.value)


def _no_wait() -> RateLimiter:
    return RateLimiter(clock=lambda: 0.0, sleep=lambda _: None, rng=lambda: 0.0,
                       min_interval_s=0.0, max_interval_s=0.0)

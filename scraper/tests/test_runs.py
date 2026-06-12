"""Run-orchestration tests: single-flight, pagination caps, cutoff, abort."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from scraper.config import load_settings
from scraper.oth_client import AntiBotError, OTHClient, RateLimiter
from scraper.resolver import ResolvedSAL
from scraper.runs import RunInProgressError, RunRegistry, execute_run, get_run, list_runs
from scraper.storage import connect, init_db
from scraper.vendor import Category, SearchPage, Vendor, VendorListing
from scraper.watchlist import add_to_watchlist

NOW = datetime(2026, 6, 13, 3, 0, tzinfo=timezone.utc)


@pytest.fixture
def settings(tmp_path):
    base = load_settings()
    return replace(
        base,
        duckdb_path=tmp_path / "listings.duckdb",
        sales_artifact_path=tmp_path / "sales.json",
        max_pages=3,
    )


@pytest.fixture
def db(settings):
    init_db(settings.duckdb_path)
    add_to_watchlist(
        settings.duckdb_path,
        ResolvedSAL(sal_code="30900", name="Bli Bli", state="QLD",
                    oth_slug="bli-bli-4560", postcode="4560"),
    )
    return settings.duckdb_path


def _listing(lid: str) -> VendorListing:
    return VendorListing(
        source=Vendor.OTH,
        external_listing_id=lid,
        external_property_id=lid,
        formatted_address=f"{lid} St, Bli Bli QLD 4560",
        postcode="4560",
        price=850000,
        status="sold",
        observed_at=NOW,
    )


def _raw(lid: str, event_date: str) -> dict:
    return {"othPropertyId": lid, "lastSale": {"eventDate": event_date, "salePrice": 850000}}


class _FakeClient:
    """Returns scripted SearchPages by page number; records calls."""

    def __init__(self, pages: list[SearchPage]):
        self._pages = pages
        self.calls: list[int] = []
        self.closed = False

    def search(self, suburb, page, *, category=Category.RECENTLYSOLD) -> SearchPage:
        self.calls.append(page)
        return self._pages[page]

    def close(self):
        self.closed = True


def _page(items, *, has_next: bool) -> SearchPage:
    listings = [_listing(lid) for lid, _ in items]
    raws = [_raw(lid, ed) for lid, ed in items]
    return SearchPage(listings=listings, raw_payloads=raws, page=0, has_next=has_next)


class TestPaginationCaps:
    def test_stops_at_max_pages(self, db, settings):
        # 5 pages all in-window with has_next True; max_pages=3 caps it.
        pages = [_page([(f"P{p}", "2026-05-01")], has_next=True) for p in range(5)]
        client = _FakeClient(pages)
        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=client, now=NOW)
        assert client.calls == [0, 1, 2]  # capped at max_pages=3

    def test_stops_on_last_page(self, db, settings):
        pages = [
            _page([("A", "2026-05-01")], has_next=True),
            _page([("B", "2026-05-01")], has_next=False),
        ]
        client = _FakeClient(pages)
        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=client, now=NOW)
        assert client.calls == [0, 1]

    def test_stops_when_page_all_older_than_window(self, db, settings):
        pages = [
            _page([("A", "2026-05-01")], has_next=True),       # in window
            _page([("OLD", "2024-01-01")], has_next=True),     # all old -> stop
            _page([("C", "2026-05-01")], has_next=True),
        ]
        client = _FakeClient(pages)
        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=client, now=NOW)
        assert client.calls == [0, 1]  # stopped after the all-old page


class TestRunLifecycle:
    def test_run_recorded_completed(self, db, settings):
        pages = [_page([("A", "2026-05-01")], has_next=False)]
        client = _FakeClient(pages)
        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=client, now=NOW)
        run = get_run(db, run_id)
        assert run["status"] == "completed"
        assert run["detail"]["suburbs"]["30900"]["pages"] == 1
        assert not reg.is_active

    def test_last_run_at_bumped_and_export_written(self, db, settings):
        pages = [_page([("A", "2026-05-01")], has_next=False)]
        client = _FakeClient(pages)
        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=client, now=NOW)
        with connect(db, read_only=True) as conn:
            last_run = conn.execute(
                "SELECT last_run_at FROM watchlist WHERE sal_code = '30900'"
            ).fetchone()[0]
        assert last_run is not None
        assert settings.sales_artifact_path.exists()


class TestSingleFlight:
    def test_second_begin_rejected(self, db):
        reg = RunRegistry(db)
        reg.begin(["30900"])
        with pytest.raises(RunInProgressError):
            reg.begin(["30900"])

    def test_slot_released_after_finish(self, db, settings):
        client = _FakeClient([_page([("A", "2026-05-01")], has_next=False)])
        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=client, now=NOW)
        # Slot free again — a second run can begin.
        reg.begin(["30900"])


class TestAntiBotAbort:
    def test_anti_bot_marks_run_failed(self, db, settings):
        class _Blocked:
            def search(self, *a, **k):
                raise AntiBotError("blocked", status_code=403)

            def close(self):
                pass

        reg = RunRegistry(db)
        run_id = reg.begin(["30900"])
        execute_run(db, settings, reg, run_id, ["30900"], client=_Blocked(), now=NOW)
        run = get_run(db, run_id)
        assert run["status"] == "failed"
        assert any("anti-bot" in e.get("error", "") for e in run["detail"]["errors"])
        assert not reg.is_active

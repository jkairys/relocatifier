"""Reconciler upsert/idempotency + snapshot-diff semantics against a temp DuckDB."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from scraper.reconciler import listing_uid, reconcile_listing
from scraper.storage import connect, init_db
from scraper.vendor import PriceKind, Vendor, VendorListing


def _listing(**over) -> VendorListing:
    base = dict(
        source=Vendor.OTH,
        external_listing_id="P1",
        external_property_id="P1",
        formatted_address="12 Example St, Bli Bli QLD 4560",
        postcode="4560",
        bedrooms=4,
        bathrooms=2,
        parking=2,
        land_size_sqm=640.0,
        property_type="House",
        status="sold",
        price=850000,
        price_kind=PriceKind.PRICE,
        observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    base.update(over)
    return VendorListing(**base)


def _raw(event_date: str = "2026-03-14", sale_price: int = 850000) -> dict:
    return {
        "othPropertyId": "P1",
        "lastSale": {"eventDate": event_date, "salePrice": sale_price},
    }


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "listings.duckdb"
    init_db(path)
    return path


def _count(db, table: str) -> int:
    with connect(db, read_only=True) as conn:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


class TestReconcileFirstObservation:
    def test_writes_property_listing_snapshot(self, db):
        with connect(db) as conn:
            wrote = reconcile_listing(conn, _listing(), _raw(), sal_code="30900")
        assert wrote is True
        assert _count(db, "property") == 1
        assert _count(db, "listing") == 1
        assert _count(db, "listing_snapshot") == 1

    def test_sale_date_stored(self, db):
        with connect(db) as conn:
            reconcile_listing(conn, _listing(), _raw("2026-03-14"), sal_code="30900")
            row = conn.execute(
                "SELECT sale_date, sal_code FROM listing WHERE listing_uid = ?",
                [listing_uid("P1")],
            ).fetchone()
        assert row[0] == date(2026, 3, 14)
        assert row[1] == "30900"


class TestIdempotency:
    def test_unchanged_reobservation_no_new_snapshot(self, db):
        with connect(db) as conn:
            reconcile_listing(conn, _listing(), _raw(), sal_code="30900")
        with connect(db) as conn:
            wrote = reconcile_listing(conn, _listing(), _raw(), sal_code="30900")
        assert wrote is False
        assert _count(db, "listing_snapshot") == 1
        assert _count(db, "listing") == 1

    def test_last_seen_bumped_on_reobservation(self, db):
        with connect(db) as conn:
            reconcile_listing(
                conn,
                _listing(observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
                _raw(),
                sal_code="30900",
            )
        with connect(db) as conn:
            reconcile_listing(
                conn,
                _listing(observed_at=datetime(2026, 6, 8, tzinfo=timezone.utc)),
                _raw(),
                sal_code="30900",
            )
            row = conn.execute(
                "SELECT first_seen_at, last_seen_at FROM listing WHERE listing_uid = ?",
                [listing_uid("P1")],
            ).fetchone()
        assert row[1] > row[0]


class TestMaterialDiff:
    def test_price_change_writes_snapshot_with_changed_field(self, db):
        with connect(db) as conn:
            reconcile_listing(conn, _listing(price=850000), _raw(), sal_code="30900")
        with connect(db) as conn:
            wrote = reconcile_listing(
                conn, _listing(price=900000), _raw(sale_price=900000), sal_code="30900"
            )
            changed = conn.execute(
                "SELECT changed_fields FROM listing_snapshot ORDER BY snapshot_id DESC LIMIT 1"
            ).fetchone()[0]
        assert wrote is True
        assert _count(db, "listing_snapshot") == 2
        assert "price" in changed

    def test_status_change_writes_snapshot(self, db):
        with connect(db) as conn:
            reconcile_listing(conn, _listing(status="sold"), _raw(), sal_code="30900")
        with connect(db) as conn:
            wrote = reconcile_listing(
                conn, _listing(status="withdrawn"), _raw(), sal_code="30900"
            )
        assert wrote is True
        assert _count(db, "listing_snapshot") == 2


class TestWriteOnce:
    def test_sale_date_not_overwritten(self, db):
        with connect(db) as conn:
            reconcile_listing(conn, _listing(), _raw("2026-03-14"), sal_code="30900")
        # Re-observe with a different (later) event date and a material change.
        with connect(db) as conn:
            reconcile_listing(
                conn, _listing(price=999000), _raw("2026-05-01", 999000), sal_code="30900"
            )
            sale_date = conn.execute(
                "SELECT sale_date FROM listing WHERE listing_uid = ?",
                [listing_uid("P1")],
            ).fetchone()[0]
        assert sale_date == date(2026, 3, 14)  # original kept

    def test_sal_code_not_overwritten(self, db):
        with connect(db) as conn:
            reconcile_listing(conn, _listing(), _raw(), sal_code="30900")
        with connect(db) as conn:
            reconcile_listing(conn, _listing(price=999000), _raw(sale_price=999000), sal_code="40000")
            sal = conn.execute(
                "SELECT sal_code FROM listing WHERE listing_uid = ?",
                [listing_uid("P1")],
            ).fetchone()[0]
        assert sal == "30900"  # first writer wins

    def test_raw_payload_stored_verbatim(self, db):
        import json

        raw = _raw()
        with connect(db) as conn:
            reconcile_listing(conn, _listing(), raw, sal_code="30900")
            stored = conn.execute(
                "SELECT raw_payload FROM listing_snapshot LIMIT 1"
            ).fetchone()[0]
        assert json.loads(stored) == raw

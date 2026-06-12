"""Sales-artifact export shape + windowing tests against a temp DuckDB."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scraper.exporter import build_sales_payload, export_sales
from scraper.reconciler import reconcile_listing
from scraper.resolver import ResolvedSAL
from scraper.storage import connect, init_db
from scraper.vendor import PriceKind, Vendor, VendorListing
from scraper.watchlist import add_to_watchlist, mark_run_completed

NOW = datetime(2026, 6, 13, 3, 0, tzinfo=timezone.utc)


def _listing(lid: str, price, **over) -> VendorListing:
    base = dict(
        source=Vendor.OTH,
        external_listing_id=lid,
        external_property_id=lid,
        formatted_address=f"{lid} Example St, Bli Bli QLD 4560",
        postcode="4560",
        latitude=-26.62,
        longitude=153.05,
        bedrooms=4,
        bathrooms=2,
        parking=2,
        land_size_sqm=640.0,
        property_type="House",
        status="sold",
        price=price if price else None,
        price_kind=PriceKind.PRICE if price else PriceKind.UNKNOWN,
        raw_price_display=str(price) if price else None,
        observed_at=NOW,
    )
    base.update(over)
    return VendorListing(**base)


def _raw(lid: str, event_date: str, sale_price) -> dict:
    return {"othPropertyId": lid, "lastSale": {"eventDate": event_date, "salePrice": sale_price}}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "listings.duckdb"
    init_db(path)
    add_to_watchlist(
        path,
        ResolvedSAL(sal_code="30900", name="Bli Bli", state="QLD",
                    oth_slug="bli-bli-4560", postcode="4560"),
    )
    return path


def _seed(db, items):
    with connect(db) as conn:
        for lid, ed, sp in items:
            reconcile_listing(conn, _listing(lid, sp), _raw(lid, ed, sp), sal_code="30900")
    mark_run_completed(db, ["30900"], NOW)


def _seed_no_coords(db, items):
    with connect(db) as conn:
        for lid, ed, sp in items:
            reconcile_listing(
                conn,
                _listing(lid, sp, latitude=None, longitude=None),
                _raw(lid, ed, sp),
                sal_code="30900",
            )
    mark_run_completed(db, ["30900"], NOW)


def _seed_types(db, items):
    """Seed listings with explicit property types: items = (lid, ed, sp, ptype)."""
    with connect(db) as conn:
        for lid, ed, sp, ptype in items:
            reconcile_listing(
                conn,
                _listing(lid, sp, property_type=ptype),
                _raw(lid, ed, sp),
                sal_code="30900",
            )
    mark_run_completed(db, ["30900"], NOW)


class TestExportShape:
    def test_payload_structure(self, db):
        _seed(db, [("A", "2026-05-01", 850000)])
        payload = build_sales_payload(db, now=NOW)
        assert payload["schema_version"] == 2
        assert payload["generated_at"] == "2026-06-13T03:00:00Z"
        sub = payload["suburbs"]["30900"]
        assert sub["name"] == "Bli Bli"
        assert sub["state"] == "QLD"
        assert sub["oth_slug"] == "bli-bli-4560"
        assert sub["fetched_at"] == "2026-06-13T03:00:00Z"

    def test_sale_fields(self, db):
        _seed(db, [("A", "2026-05-01", 850000)])
        sale = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"][0]
        assert sale["address"] == "A Example St, Bli Bli QLD 4560"
        assert sale["price"] == 850000
        assert sale["price_display"] == "850000"
        assert sale["bedrooms"] == 4
        assert sale["land_size_sqm"] == 640
        assert sale["property_type"] == "House"
        assert sale["sale_date"] == "2026-05-01"

    def test_coords_from_property(self, db):
        _seed(db, [("A", "2026-05-01", 850000)])
        sale = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"][0]
        assert sale["lat"] == pytest.approx(-26.62)
        assert sale["lon"] == pytest.approx(153.05)

    def test_null_coords_exported_as_null(self, db):
        _seed_no_coords(db, [("A", "2026-05-01", 850000)])
        sale = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"][0]
        assert sale["lat"] is None
        assert sale["lon"] is None

    def test_suppressed_price_null(self, db):
        _seed(db, [("A", "2026-05-01", 0)])
        sale = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"][0]
        assert sale["price"] is None


class TestWindowing:
    def test_sorted_desc(self, db):
        _seed(db, [
            ("A", "2026-01-01", 800000),
            ("B", "2026-05-01", 900000),
            ("C", "2026-03-01", 850000),
        ])
        sales = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"]
        dates = [s["sale_date"] for s in sales]
        assert dates == ["2026-05-01", "2026-03-01", "2026-01-01"]

    def test_excludes_older_than_12_months(self, db):
        _seed(db, [
            ("OLD", "2025-01-01", 700000),  # >12 months before NOW
            ("NEW", "2026-05-01", 900000),
        ])
        sales = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"]
        addresses = [s["address"] for s in sales]
        assert any("NEW" in a for a in addresses)
        assert not any("OLD" in a for a in addresses)

    def test_empty_suburb_present_with_empty_sales(self, db):
        payload = build_sales_payload(db, now=NOW)
        assert payload["suburbs"]["30900"]["sales"] == []


class TestTypeFilter:
    def test_excluded_types_absent(self, db):
        _seed_types(db, [
            ("HOUSE", "2026-05-01", 900000, "House"),
            ("UNIT", "2026-05-02", 500000, "Unit"),
            ("APT", "2026-05-03", 450000, "Apartment"),
            ("LAND", "2026-05-04", 300000, "Land"),
            ("COMM", "2026-05-05", 800000, "Commercial"),
            ("TOWN", "2026-05-06", 700000, "Townhouse"),
        ])
        sales = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"]
        types = {s["property_type"] for s in sales}
        assert types == {"House", "Townhouse"}
        for excluded in ("Unit", "Apartment", "Land", "Commercial"):
            assert excluded not in types

    def test_unknown_type_retained(self, db):
        _seed_types(db, [
            ("UNK", "2026-05-01", 850000, "Unknown"),
            ("NULL", "2026-05-02", 750000, None),
        ])
        sales = build_sales_payload(db, now=NOW)["suburbs"]["30900"]["sales"]
        types = [s["property_type"] for s in sales]
        assert "Unknown" in types
        assert None in types


class TestExportFile:
    def test_writes_file(self, db, tmp_path):
        _seed(db, [("A", "2026-05-01", 850000)])
        out = tmp_path / "nested" / "sales.json"
        written = export_sales(db, out, now=NOW)
        assert written == out
        assert out.exists()
        import json

        data = json.loads(out.read_text())
        assert data["schema_version"] == 2

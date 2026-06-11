"""Unit tests for house_prices pure logic — fixtures only, no network."""

import datetime as dt
from pathlib import Path

from relocatifier_etl.source_modules.house_prices import (
    SaleRecord,
    is_house_sale,
    latest_house_median,
    median_price_by_locality,
    parse_oth_page,
    parse_oth_sitemap_qld,
    parse_psi_dat,
)

FIXTURES = Path(__file__).parent / "fixtures" / "house_prices"

WINDOW_START = dt.date(2025, 6, 10)
WINDOW_END = dt.date(2026, 6, 10)


def _rec(**overrides) -> SaleRecord:
    """A valid house sale; overrides break one rule at a time."""
    base = dict(
        property_id="1",
        sale_counter="1",
        download_dt="20260608 01:00",
        unit_number="",
        locality="WESTON",
        postcode="2326",
        contract_date=dt.date(2026, 5, 8),
        price=1_100_000,
        zoning="R5",
        nature_of_property="R",
        primary_purpose="RESIDENCE",
        strata_lot="",
    )
    base.update(overrides)
    return SaleRecord(**base)


class TestParsePsiDat:
    def setup_method(self):
        self.records = parse_psi_dat((FIXTURES / "sample.dat").read_text())

    def test_only_well_formed_b_records(self):
        # 11 full B records; A/C/D rows, the truncated B and junk are skipped.
        assert len(self.records) == 11
        assert all(isinstance(r, SaleRecord) for r in self.records)

    def test_field_extraction(self):
        first = self.records[0]
        assert first.locality == "WESTON"
        assert first.postcode == "2326"
        assert first.contract_date == dt.date(2026, 5, 8)
        assert first.price == 1_100_000
        assert first.zoning == "R5"
        assert first.nature_of_property == "R"
        assert first.primary_purpose == "RESIDENCE"
        assert first.strata_lot == ""

    def test_strata_and_unit_number_captured(self):
        strata = self.records[1]
        assert strata.strata_lot == "1"
        assert strata.unit_number == "1"

    def test_missing_contract_date_is_none(self):
        assert self.records[9].contract_date is None


class TestIsHouseSale:
    def test_valid_house_sale(self):
        assert is_house_sale(_rec())

    def test_strata_lot_excluded(self):
        assert not is_house_sale(_rec(strata_lot="1"))

    def test_unit_number_excluded(self):
        assert not is_house_sale(_rec(unit_number="2"))

    def test_vacant_land_excluded(self):
        assert not is_house_sale(_rec(nature_of_property="V", primary_purpose="VACANT LAND"))

    def test_non_residential_purpose_excluded(self):
        assert not is_house_sale(_rec(primary_purpose="SHOP"))

    def test_residence_purpose_variants_kept(self):
        assert is_house_sale(_rec(primary_purpose="RESIDENCE"))
        assert is_house_sale(_rec(primary_purpose="RESIDENTIAL"))

    def test_blank_purpose_needs_residential_zoning(self):
        assert is_house_sale(_rec(primary_purpose="", zoning="R2"))
        assert not is_house_sale(_rec(primary_purpose="", zoning="B2"))

    def test_price_bounds(self):
        assert not is_house_sale(_rec(price=30_000))
        assert not is_house_sale(_rec(price=60_000_000))
        assert not is_house_sale(_rec(price=None))
        assert is_house_sale(_rec(price=50_000))
        assert is_house_sale(_rec(price=50_000_000))

    def test_needs_locality_and_contract_date(self):
        assert not is_house_sale(_rec(locality=""))
        assert not is_house_sale(_rec(contract_date=None))


class TestMedianPriceByLocality:
    def test_fixture_end_to_end(self):
        records = parse_psi_dat((FIXTURES / "sample.dat").read_text())
        medians = median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=3)
        # WESTON house sales surviving the filters: 1.1m, 700k, 950k.
        # Excluded: vacant land, shop, too-cheap, too-dear, B2-no-purpose,
        # no-contract-date, no-locality; CESSNOCK is strata (and < min_sales).
        assert medians == {"WESTON": (950_000, 3)}

    def test_min_sales_threshold(self):
        records = [_rec(property_id=str(i)) for i in range(4)]
        assert median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=5) == {}
        got = median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=4)
        assert got["WESTON"][1] == 4

    def test_window_excludes_old_and_future_sales(self):
        records = [
            _rec(property_id="1", contract_date=dt.date(2024, 1, 1)),
            _rec(property_id="2", contract_date=dt.date(2026, 7, 1)),
            _rec(property_id="3", contract_date=dt.date(2025, 6, 10)),  # boundary in
        ]
        got = median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=1)
        assert got["WESTON"][1] == 1

    def test_dedupes_re_reported_sale_keeping_latest_download(self):
        records = [
            _rec(download_dt="20260101 01:00", price=500_000),
            _rec(download_dt="20260601 01:00", price=650_000),  # corrected later
        ]
        got = median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=1)
        assert got["WESTON"] == (650_000, 1)

    def test_locality_names_normalised(self):
        records = [
            _rec(property_id="1", locality="BLI BLI"),
            _rec(property_id="2", locality="Bli-Bli"),
        ]
        got = median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=2)
        assert list(got) == ["BLI BLI"]

    def test_even_count_median_rounds_to_int(self):
        records = [
            _rec(property_id="1", price=500_000),
            _rec(property_id="2", price=500_001),
        ]
        got = median_price_by_locality(records, WINDOW_START, WINDOW_END, min_sales=1)
        # 500000.5 -> 500000 (banker's rounding); a $1 difference is noise.
        assert got["WESTON"] == (500_000, 2)


class TestParseOthPage:
    def setup_method(self):
        self.parsed = parse_oth_page((FIXTURES / "oth_suburb_page.html").read_text())

    def test_extracts_locality_and_postcode(self):
        assert self.parsed["locality_name"] == "Bli Bli"
        assert self.parsed["postcode"] == "4560"

    def test_extracts_house_metrics_only(self):
        types = {m["metricType"] for m in self.parsed["house_metrics"]}
        assert "Median Sale Price (12 months)" in types
        assert all(m["propertyType"] == "Houses" for m in self.parsed["house_metrics"])

    def test_latest_house_median(self):
        value = latest_house_median(self.parsed["house_metrics"], today=dt.date(2026, 6, 11))
        assert value == 1_137_500

    def test_stale_series_yields_none(self):
        # Same series viewed from 2029: latest point is way out of date.
        value = latest_house_median(self.parsed["house_metrics"], today=dt.date(2029, 1, 1))
        assert value is None

    def test_no_redux_data_returns_none(self):
        assert parse_oth_page("<html><body>404</body></html>") is None

    def test_no_median_series_returns_none(self):
        metrics = [m for m in self.parsed["house_metrics"] if m["metricTypeId"] != 21]
        assert latest_house_median(metrics, today=dt.date(2026, 6, 11)) is None


class TestParseOthSitemap:
    def setup_method(self):
        self.by_name = parse_oth_sitemap_qld((FIXTURES / "oth_sitemap.xml").read_text())

    def test_qld_only(self):
        assert "MOSMAN" not in self.by_name  # NSW entry ignored

    def test_duplicate_names_collected(self):
        assert sorted(self.by_name["BUDERIM"]) == ["buderim-4519", "buderim-4556"]

    def test_names_normalised_like_crosswalk(self):
        assert self.by_name["BLI BLI"] == ["bli-bli-4560"]
        assert self.by_name["MOUNT COOT THA"] == ["mount-coot-tha-4066"]

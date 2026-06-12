"""Parser + price-normalisation tests against both real OTH fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.oth_parser import parse_search_response
from scraper.price import parse_oth_listing
from scraper.vendor import Category, PriceKind

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestParseRecentlysoldFixture:
    """The Paddington page: has landSize + lastSale on some items."""

    def setup_method(self):
        self.body = load_fixture("oth_recentlysold_fixture.json")
        self.page = parse_search_response(
            self.body, category=Category.RECENTLYSOLD, page=0
        )

    def test_parses_all_content_items(self):
        assert len(self.page.listings) == len(self.body["content"])
        assert len(self.page.raw_payloads) == len(self.page.listings)

    def test_pagination_flags_from_body(self):
        assert self.page.page == self.body["number"]
        assert self.page.has_next == (not self.body["last"])
        assert self.page.total == self.body["totalElements"]

    def test_all_recentlysold_status_sold(self):
        assert all(l.status == "sold" for l in self.page.listings)

    def test_addresses_present(self):
        assert all(l.formatted_address for l in self.page.listings)

    def test_suppressed_price_is_null_not_zero(self):
        # Any item with salePrice 0/missing must yield price None, kind UNKNOWN.
        for listing, raw in zip(self.page.listings, self.page.raw_payloads):
            sale_price = (raw.get("lastSale") or {}).get("salePrice")
            if not sale_price:
                assert listing.price is None
                assert listing.price_kind is PriceKind.UNKNOWN

    def test_real_prices_are_positive_ints(self):
        for listing, raw in zip(self.page.listings, self.page.raw_payloads):
            sale_price = (raw.get("lastSale") or {}).get("salePrice")
            if sale_price:
                assert listing.price == int(sale_price)
                assert listing.price_kind is PriceKind.PRICE

    def test_missing_land_size_is_none(self):
        # Items without landSize must surface land_size_sqm None (no fabrication).
        for listing, raw in zip(self.page.listings, self.page.raw_payloads):
            if raw.get("landSize") is None:
                assert listing.land_size_sqm is None
            else:
                assert listing.land_size_sqm == float(raw["landSize"])


class TestParseSpikeFixture:
    """The live Bli Bli response (page 1)."""

    def setup_method(self):
        self.body = load_fixture("oth_spike_response.json")
        self.page = parse_search_response(
            self.body, category=Category.RECENTLYSOLD, page=1
        )

    def test_page_number_and_has_next(self):
        assert self.page.page == 1
        assert self.page.has_next is True  # last == false in fixture

    def test_some_suppressed_some_real(self):
        prices = [l.price for l in self.page.listings]
        assert any(p is None for p in prices)
        assert any(p is not None for p in prices)


class TestPriceNormalisation:
    def test_zero_sale_price_suppressed(self):
        result = parse_oth_listing(
            {"lastSale": {"salePrice": 0}}, Category.RECENTLYSOLD
        )
        assert result.low is None
        assert result.kind is PriceKind.UNKNOWN

    def test_missing_sale_price_suppressed(self):
        result = parse_oth_listing({"lastSale": {}}, Category.RECENTLYSOLD)
        assert result.low is None
        assert result.kind is PriceKind.UNKNOWN

    def test_real_sale_price(self):
        result = parse_oth_listing(
            {"lastSale": {"salePrice": 850000}}, Category.RECENTLYSOLD
        )
        assert result.low == 850000
        assert result.high is None
        assert result.kind is PriceKind.PRICE
        assert result.display == "850000"

    def test_no_last_sale_block(self):
        result = parse_oth_listing({}, Category.RECENTLYSOLD)
        assert result.low is None
        assert result.kind is PriceKind.UNKNOWN


class TestLandSizeUnitValidation:
    def _item(self, **over):
        from scraper.oth_parser import _extract_land_size_sqm

        return _extract_land_size_sqm(over)

    def test_squaremeter_kept(self):
        assert self._item(landSize=640, landSizeUnit="squareMeter") == 640.0

    def test_unknown_unit_dropped(self):
        assert self._item(landSize=2, landSizeUnit="acre") is None

    def test_missing_unit_kept(self):
        # Absent unit is trusted (OTH always sends squareMeter when present).
        assert self._item(landSize=640) == 640.0

    def test_missing_land_size(self):
        assert self._item(landSizeUnit="squareMeter") is None

"""Sale-date extraction tests."""

from __future__ import annotations

from datetime import date

from scraper.sale_date import extract_sale_date


class TestExtractSaleDate:
    def test_event_date(self):
        assert extract_sale_date({"lastSale": {"eventDate": "2026-04-28"}}) == date(
            2026, 4, 28
        )

    def test_empty(self):
        assert extract_sale_date({}) is None

    def test_no_last_sale(self):
        assert extract_sale_date({"foo": 1}) is None

    def test_unparseable(self):
        assert extract_sale_date({"lastSale": {"eventDate": "not-a-date"}}) is None

    def test_non_string(self):
        assert extract_sale_date({"lastSale": {"eventDate": 20260428}}) is None

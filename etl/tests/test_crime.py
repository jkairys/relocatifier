"""Unit tests for the crime module's pure logic — no network, no downloads.

Covers the rate maths, the population floor, the BOCSAR 12-month windowing /
summation, and the complete-month window calculation. The QLD protobuf parser
is exercised against a tiny hand-built fixture so it has no live dependency.
"""

import datetime

import pytest

from relocatifier_etl.source_modules.crime import (
    MIN_POPULATION,
    count_qld_incidents,
    crime_rate,
    parse_qld_suburbs,
    recent_month_columns,
    sum_nsw_incidents,
    window_to_complete_month,
)


class TestCrimeRate:
    def test_basic_per_1000(self):
        # 250 incidents / 5000 people * 1000 = 50.0
        assert crime_rate(250, 5000) == 50.0

    def test_rounds_to_one_decimal(self):
        assert crime_rate(40, 3000) == 13.3

    def test_zero_incidents_is_zero_not_none(self):
        assert crime_rate(0, 5000) == 0.0

    def test_none_incidents_is_none(self):
        assert crime_rate(None, 5000) is None

    @pytest.mark.parametrize("pop", [None, 0, 1, 199])
    def test_population_floor_nulls_small_suburbs(self, pop):
        # A highway servo with 3 residents and 40 thefts must not read 13,000.
        assert crime_rate(40, pop) is None

    def test_at_floor_is_reported(self):
        assert crime_rate(40, MIN_POPULATION) == round(40 / MIN_POPULATION * 1000, 1)


class TestRecentMonthColumns:
    def _header(self):
        # Suburb / category / subcategory, then chronological months out of order.
        return [
            "Suburb", "Offence category", "Subcategory",
            "Jan 1995", "Feb 1995",
            "Oct 2025", "Nov 2025", "Dec 2025",
            "Jan 2025", "Feb 2025", "Mar 2025", "Apr 2025", "May 2025",
            "Jun 2025", "Jul 2025", "Aug 2025", "Sep 2025",
        ]

    def test_picks_latest_twelve_chronologically(self):
        header = self._header()
        cols = recent_month_columns(header, 12)
        labels = [header[c] for c in cols]
        # The 12 months of 2025, ending Dec 2025 — never the 1995 columns.
        assert labels[-1] == "Dec 2025"
        assert "Jan 1995" not in labels
        assert set(labels) == {
            f"{m} 2025" for m in
            ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        }

    def test_ignores_non_month_columns(self):
        cols = recent_month_columns(self._header(), 12)
        assert all(c >= 3 for c in cols)  # never Suburb/category/subcategory

    def test_window_smaller_than_n(self):
        header = ["Suburb", "Jan 2025", "Feb 2025"]
        cols = recent_month_columns(header, 12)
        assert [header[c] for c in cols] == ["Jan 2025", "Feb 2025"]


class TestSumNswIncidents:
    def test_sums_all_categories_for_a_suburb(self):
        header = ["Suburb", "Cat", "Sub", "Jan 2025", "Feb 2025"]
        rows = [
            ["Bli Bli", "Homicide", "Murder", "1", "0"],
            ["Bli Bli", "Theft", "Steal", "3", "5"],
            ["Maroochydore", "Theft", "Steal", "10", "20"],
        ]
        cols = recent_month_columns(header, 12)
        totals = sum_nsw_incidents(rows, cols)
        assert totals["Bli Bli"] == 9  # 1+0+3+5
        assert totals["Maroochydore"] == 30

    def test_blank_and_nonnumeric_cells_count_zero(self):
        header = ["Suburb", "Jan 2025", "Feb 2025"]
        rows = [["X", "", "na"], ["X", "2", "3"]]
        cols = recent_month_columns(header, 12)
        assert sum_nsw_incidents(rows, cols)["X"] == 5

    def test_only_windowed_months_are_summed(self):
        header = ["Suburb", "Cat", "Jan 1995", "Dec 2025"]
        rows = [["X", "T", "999", "7"]]
        cols = recent_month_columns(header, 1)  # just Dec 2025
        assert sum_nsw_incidents(rows, cols)["X"] == 7

    def test_skips_blank_suburb_names(self):
        header = ["Suburb", "Jan 2025"]
        rows = [["", "5"], ["X", "2"]]
        assert sum_nsw_incidents(rows, recent_month_columns(header, 12)) == {"X": 2}


class TestWindowToCompleteMonth:
    def test_excludes_partial_current_month(self):
        # 2026-06-11: June is partial, so the window is the 12 months to May 2026.
        start, end = window_to_complete_month(datetime.date(2026, 6, 11), 12)
        assert start == datetime.date(2025, 6, 1)
        assert end == datetime.date(2026, 5, 31)

    def test_january_rolls_back_a_year(self):
        start, end = window_to_complete_month(datetime.date(2026, 1, 15), 12)
        assert end == datetime.date(2025, 12, 31)
        assert start == datetime.date(2025, 1, 1)

    def test_end_is_last_day_of_month(self):
        # Month before March is February — non-leap 2026 has 28 days.
        _, end = window_to_complete_month(datetime.date(2026, 3, 1), 12)
        assert end == datetime.date(2026, 2, 28)


# --- QLD protobuf fixtures (built in-line, no network) -----------------------

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    return bytes(out)


def _ld(field: int, payload: bytes) -> bytes:
    """A length-delimited (wire type 2) field."""
    return _varint(field << 3 | 2) + _varint(len(payload)) + payload


def _cell_int(v: int) -> bytes:
    # field 13 (cell) wrapping a sub-message with an int at field 3
    return _ld(13, _varint(3 << 3 | 0) + _varint(v))


def _cell_str(s: str) -> bytes:
    return _ld(13, _ld(1, s.encode()))


def _ocm_table(rows: list[bytes]) -> bytes:
    """An OCM 'table' message: data lives in field 4, rows are field 1."""
    data = b"".join(_ld(1, r) for r in rows)
    return _ld(4, data)


class TestParseQldSuburbs:
    def test_extracts_suburb_objectids_keeps_others_out(self):
        rows = [
            _cell_int(465) + _cell_str("Agnes Water") + _cell_str("Suburb"),
            _cell_int(961) + _cell_str("Brisbane City") + _cell_str("Suburb"),
            _cell_int(1) + _cell_str("4000") + _cell_str("Postcode"),
        ]
        suburbs = parse_qld_suburbs(_ocm_table(rows))
        assert suburbs == {"Agnes Water": 465, "Brisbane City": 961}

    def test_preserves_disambiguated_names(self):
        rows = [_cell_int(503) + _cell_str("Alligator Creek - Townsville") + _cell_str("Suburb")]
        assert parse_qld_suburbs(_ocm_table(rows)) == {"Alligator Creek - Townsville": 503}


class TestCountQldIncidents:
    def test_one_row_per_incident(self):
        # Three incident rows, each a (date, o_code, l_code) cell triple.
        rows = [
            _cell_int(100) + _cell_int(310) + _cell_int(465),
            _cell_int(101) + _cell_int(290) + _cell_int(465),
            _cell_int(102) + _cell_int(650) + _cell_int(465),
        ]
        assert count_qld_incidents(_ocm_table(rows)) == 3

    def test_empty_table_is_zero(self):
        assert count_qld_incidents(_ocm_table([])) == 0

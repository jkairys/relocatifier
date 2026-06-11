"""Unit tests for the rents source module's pure logic — no downloads.

Fixture rows mimic openpyxl values_only output, including its habit of
trimming trailing empty cells (shorter tuples) and the RTA's mix of '' and
None for suppressed medians.
"""

import geopandas as gpd
import pytest
from shapely.geometry import box

from relocatifier_etl.source_modules.rents import (
    dominant_zone_by_area,
    fill_missing_from_postcodes,
    parse_nsw_bond_rows,
    parse_rta_postcode_rents,
    parse_rta_suburb_rents,
    pick_house_rent,
    postcode_medians,
)

# --- RTA suburb-rents sheet parsing -----------------------------------------

# Layout mirrors "4 sub-rents": junk preamble, Suburb/Dwelling header, month
# row, year row, blank row, then data rows. Quarter columns: 2025-Q2..2026-Q1.
RTA_ROWS = [
    (None, "Contents", None, None, None, None, None, None),
    (None, "Median rents, by Suburb", None, None, None, None, None, None),
    (None, None, "Suburb", "Dwelling", None, None, None, None),
    (None, None, None, None, "Jun", "Sep", "Dec", "Mar"),
    (None, None, None, None, 2025, 2025, 2025, 2026),
    (None, None, None, None, None, None, None, None),
    (None, None, "Bli Bli", "House 3", 700, 720, "", 780),
    (None, None, "Bli Bli", "House 4", 800, "", 850, 880),
    (None, None, "Bli Bli", "All dwellings", 650, 660, 670, 700),
    (None, None, "Suppressedville", "House 3", 500, 510, "", ""),
    (None, None, "Suppressedville", "House 4", "", "", 560, ""),
    (None, None, "Flatland", "Flat 2", 400, 410, 420, 430),
    (None, None, "Flatland", "All dwellings", 410, 415, 425, 435),
    # openpyxl trims trailing empties: short tuple = latest quarters missing.
    (None, None, "Trimmed", "House 3", 600),
]


class TestParseRtaSuburbRents:
    def test_latest_quarter_label(self):
        quarter, _ = parse_rta_suburb_rents(RTA_ROWS)
        assert quarter == "2026-Q1"

    def test_series_values_oldest_first_with_suppression(self):
        _, suburbs = parse_rta_suburb_rents(RTA_ROWS)
        assert suburbs["Bli Bli"]["House 3"] == [700.0, 720.0, None, 780.0]
        assert suburbs["Suppressedville"]["House 3"] == [500.0, 510.0, None, None]

    def test_lookback_window(self):
        _, suburbs = parse_rta_suburb_rents(RTA_ROWS, lookback=2)
        assert suburbs["Bli Bli"]["House 3"] == [None, 780.0]

    def test_short_rows_pad_with_none(self):
        _, suburbs = parse_rta_suburb_rents(RTA_ROWS)
        assert suburbs["Trimmed"]["House 3"] == [600.0, None, None, None]

    def test_missing_header_raises(self):
        with pytest.raises(ValueError, match="header"):
            parse_rta_suburb_rents([(None, "no", "headers", "here")])


class TestPickHouseRent:
    def parsed(self, suburb):
        _, suburbs = parse_rta_suburb_rents(RTA_ROWS)
        return suburbs[suburb]

    def test_latest_house3_wins(self):
        assert pick_house_rent(self.parsed("Bli Bli")) == 780.0

    def test_series_preference_beats_recency(self):
        # House 3 newest value is 2025-Q3's 510 — preferred over House 4's
        # more recent 560.
        assert pick_house_rent(self.parsed("Suppressedville")) == 510.0

    def test_flats_and_all_dwellings_never_used(self):
        assert pick_house_rent(self.parsed("Flatland")) is None

    def test_empty_series(self):
        assert pick_house_rent({}) is None


# --- RTA postcode-rents sheet parsing -----------------------------------------

# Layout mirrors "1 pc-rents": same shape as the suburb sheet but the entity
# column is headed "Postcode" and holds numbers.
RTA_PC_ROWS = [
    (None, "Contents", None, None, None, None, None, None),
    (None, "Median rents, by Postcode", None, None, None, None, None, None),
    (None, None, "Postcode", "Dwelling", None, None, None, None),
    (None, None, None, None, "Jun", "Sep", "Dec", "Mar"),
    (None, None, None, None, 2025, 2025, 2025, 2026),
    (None, None, None, None, None, None, None, None),
    (None, None, 4560, "House 3", 640, 650, "", 680),
    (None, None, 4560, "House 4", 700, 720, 740, 760),
    (None, None, 4560, "All dwellings", 600, 610, 620, 630),
    (None, None, "4870", "House 4", 500, 510, 520, 530),  # postcode as string
    (None, None, 870, "House 3", 450, 455, 460, 465),     # zero-padded to 0870
    (None, None, "Total", "House 3", 999, 999, 999, 999), # non-numeric: skipped
    (None, None, 4561, "Flat 2", 400, 410, 420, 430),
]


class TestParseRtaPostcodeRents:
    def test_latest_quarter_label(self):
        quarter, _ = parse_rta_postcode_rents(RTA_PC_ROWS)
        assert quarter == "2026-Q1"

    def test_postcodes_normalised_to_padded_strings(self):
        _, postcodes = parse_rta_postcode_rents(RTA_PC_ROWS)
        assert postcodes["4560"]["House 3"] == [640.0, 650.0, None, 680.0]
        assert postcodes["4870"]["House 4"] == [500.0, 510.0, 520.0, 530.0]
        assert "0870" in postcodes

    def test_non_numeric_entities_skipped(self):
        _, postcodes = parse_rta_postcode_rents(RTA_PC_ROWS)
        assert "Total" not in postcodes

    def test_same_house_series_rules_apply(self):
        _, postcodes = parse_rta_postcode_rents(RTA_PC_ROWS)
        assert pick_house_rent(postcodes["4560"]) == 680.0
        assert pick_house_rent(postcodes["4561"]) is None  # flats never used

    def test_missing_header_raises(self):
        with pytest.raises(ValueError, match="header"):
            parse_rta_postcode_rents([(None, "no", "headers", "here")])

    def test_suburb_parser_ignores_postcode_sheet(self):
        # The Suburb wrapper must not accidentally accept the postcode header.
        with pytest.raises(ValueError, match="header"):
            parse_rta_suburb_rents(RTA_PC_ROWS)


class TestFillMissingFromPostcodes:
    SAL_TO_POSTCODE = {"30001": "4560", "30002": "4560", "30003": "4870"}

    def test_fills_only_missing_sals(self):
        # 30001 already has a suburb-sheet value: it must win.
        filled = fill_missing_from_postcodes(
            {"30001": 780.0},
            self.SAL_TO_POSTCODE,
            {"4560": 680.0, "4870": 530.0},
        )
        assert filled == {"30002": 680.0, "30003": 530.0}

    def test_postcode_without_house_median_gives_nothing(self):
        # A suppressed/absent postcode median must not be inherited from
        # some lesser-overlap postcode.
        filled = fill_missing_from_postcodes(
            {}, self.SAL_TO_POSTCODE, {"4560": 680.0, "4870": None}
        )
        assert filled == {"30001": 680.0, "30002": 680.0}

    def test_empty_inputs(self):
        assert fill_missing_from_postcodes({}, {}, {}) == {}


# --- NSW bond lodgement parsing ----------------------------------------------

NSW_ROWS = [
    ("NSW Fair Trading\nResidential Rental Bond Lodgements\nApril 2026", None, None, None, None),
    (None, None, None, None, None),
    ("Lodgement Date", "Postcode", "Dwelling Type", "Bedrooms", "Weekly Rent"),
    ("2026-04-01", 2536, "H", "3", "580"),       # rent as string
    ("2026-04-02", 2536, "H", "4", 640),          # rent as number
    ("2026-04-03", 2536, "F", "2", "900"),        # flat: excluded
    ("2026-04-04", 2536, "T", "3", "550"),        # townhouse: excluded
    ("2026-04-05", "2088", "H", "U", "1,990"),    # postcode as string, comma rent
    ("2026-04-06", 2088, "H", "3", "U"),          # unknown rent: dropped
    ("2026-04-07", "U", "H", "3", "500"),         # unknown postcode: dropped
    ("2026-04-08", 800, "H", "3", "400"),         # zero-padded to 0800
    ("2026-04-09", 2536, "H", "3", 0),            # non-positive rent: dropped
]


class TestParseNswBondRows:
    def test_houses_only_with_messy_types(self):
        assert list(parse_nsw_bond_rows(NSW_ROWS)) == [
            ("2536", 580.0),
            ("2536", 640.0),
            ("2088", 1990.0),
            ("0800", 400.0),
        ]

    def test_missing_header_raises(self):
        with pytest.raises(ValueError, match="header"):
            list(parse_nsw_bond_rows([("just", "some", "cells", None, None)]))


class TestPostcodeMedians:
    def test_median_per_postcode(self):
        lodgements = [("2536", r) for r in (500, 580, 560, 700, 620)]
        lodgements += [("2088", r) for r in (1800, 1990, 2200, 1900, 2100, 2000)]
        assert postcode_medians(lodgements, min_count=5) == {
            "2536": 580.0,
            "2088": 1995.0,  # even count -> mean of middle two
        }

    def test_small_samples_suppressed(self):
        lodgements = [("2536", 580.0)] * 5 + [("2999", 400.0)] * 4
        assert postcode_medians(lodgements, min_count=5) == {"2536": 580.0}


# --- postcode -> SAL by largest area overlap ----------------------------------


class TestDominantZoneByArea:
    CRS = "EPSG:3577"  # any planar CRS; areas are computed in its units

    def test_largest_overlap_wins(self):
        # Suburb A: 70% inside postcode 2001, 30% in 2002. Suburb B fully in
        # 2002. Suburb C is offshore: no overlap, absent from the result.
        targets = gpd.GeoDataFrame(
            {"sal_code": ["10001", "10002", "10003"]},
            geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10), box(50, 50, 60, 60)],
            crs=self.CRS,
        )
        zones = gpd.GeoDataFrame(
            {"postcode": ["2001", "2002"]},
            geometry=[box(0, 0, 7, 10), box(7, 0, 30, 10)],
            crs=self.CRS,
        )
        assert dominant_zone_by_area(targets, zones, "postcode") == {
            "10001": "2001",
            "10002": "2002",
        }

    def test_no_overlap_at_all(self):
        targets = gpd.GeoDataFrame(
            {"sal_code": ["10001"]}, geometry=[box(0, 0, 1, 1)], crs=self.CRS
        )
        zones = gpd.GeoDataFrame(
            {"postcode": ["2001"]}, geometry=[box(5, 5, 6, 6)], crs=self.CRS
        )
        assert dominant_zone_by_area(targets, zones, "postcode") == {}

    def test_touching_but_not_overlapping_is_not_assigned(self):
        # Shared border only — zero-area intersection must not win by accident.
        targets = gpd.GeoDataFrame(
            {"sal_code": ["10001"]}, geometry=[box(0, 0, 1, 1)], crs=self.CRS
        )
        zones = gpd.GeoDataFrame(
            {"postcode": ["2001"]}, geometry=[box(1, 0, 2, 1)], crs=self.CRS
        )
        assert dominant_zone_by_area(targets, zones, "postcode") == {}

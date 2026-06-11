"""Unit tests for the schools module's pure logic — no downloads required."""

import pandas as pd

from relocatifier_etl.source_modules.schools import (
    aggregate_icsea,
    clean_schools,
    icsea_in_range,
    valid_coords,
    weighted_mean_icsea,
)


class TestWeightedMeanIcsea:
    def test_weighted_by_enrolments(self):
        # (1000*100 + 1100*300) / 400 = 1075
        assert weighted_mean_icsea([(1000, 100), (1100, 300)]) == 1075

    def test_rounds_to_whole_number(self):
        # (1000*1 + 1001*2) / 3 = 1000.666... -> 1001
        assert weighted_mean_icsea([(1000, 1), (1001, 2)]) == 1001

    def test_single_school(self):
        assert weighted_mean_icsea([(987, 250)]) == 987

    def test_null_enrolment_falls_back_to_unweighted(self):
        # One missing weight disables weighting for the whole group:
        # (1000 + 1200) / 2 = 1100, not biased towards the weighted school.
        assert weighted_mean_icsea([(1000, None), (1200, 400)]) == 1100

    def test_nan_enrolment_falls_back_to_unweighted(self):
        assert weighted_mean_icsea([(1000, float("nan")), (1200, 400)]) == 1100

    def test_zero_enrolment_falls_back_to_unweighted(self):
        # A zero weight would silently erase the school; treat like null.
        assert weighted_mean_icsea([(1000, 0), (1200, 400)]) == 1100

    def test_empty_is_none(self):
        assert weighted_mean_icsea([]) is None


class TestSanityFilters:
    def test_icsea_bounds_inclusive(self):
        assert icsea_in_range(500)
        assert icsea_in_range(1300)
        assert icsea_in_range(1000.0)

    def test_icsea_out_of_range(self):
        assert not icsea_in_range(499)
        assert not icsea_in_range(1301)
        assert not icsea_in_range(0)

    def test_icsea_missing(self):
        assert not icsea_in_range(None)
        assert not icsea_in_range(float("nan"))

    def test_coords_sydney_ok(self):
        assert valid_coords(-33.87, 151.21)

    def test_coords_lord_howe_island_ok(self):
        # NSW external territory at ~159°E must survive the bounding box.
        assert valid_coords(-31.52, 159.07)

    def test_coords_null_island_rejected(self):
        assert not valid_coords(0.0, 0.0)

    def test_coords_missing_rejected(self):
        assert not valid_coords(None, 151.21)
        assert not valid_coords(-33.87, None)
        assert not valid_coords(float("nan"), 151.21)

    def test_coords_out_of_range_rejected(self):
        assert not valid_coords(51.5, -0.1)  # London


class TestCleanSchools:
    @staticmethod
    def _profile(rows):
        return pd.DataFrame(
            rows,
            columns=["ACARA SML ID", "School Name", "State", "School Sector", "ICSEA", "Total Enrolments"],
        )

    @staticmethod
    def _location(rows):
        return pd.DataFrame(rows, columns=["ACARA SML ID", "Latitude", "Longitude"])

    def test_joins_by_id_and_filters(self):
        profile = self._profile(
            [
                (1, "Keep Primary", "NSW", "Government", 1100, 300),
                (2, "Wrong State", "VIC", "Government", 1100, 300),
                (3, "No ICSEA", "QLD", "Catholic", None, 300),
                (4, "Bad ICSEA", "QLD", "Independent", 9999, 300),
                (5, "Bad Coords", "QLD", "Government", 1000, 300),
                (6, "Not In Location Table", "NSW", "Government", 1000, 300),
            ]
        )
        location = self._location(
            [
                (1, -33.8, 151.2),
                (2, -37.8, 145.0),
                (3, -27.5, 153.0),
                (4, -27.5, 153.0),
                (5, 0.0, 0.0),
                (7, -27.5, 153.0),  # sub-campus with no profile row
            ]
        )
        cleaned = clean_schools(profile, location)
        assert list(cleaned["acara_id"]) == [1]
        assert list(cleaned.columns) == ["acara_id", "icsea", "enrolments", "lat", "lon"]

    def test_all_sectors_kept(self):
        profile = self._profile(
            [
                (1, "Gov", "QLD", "Government", 1000, 100),
                (2, "Cath", "QLD", "Catholic", 1000, 100),
                (3, "Ind", "QLD", "Independent", 1000, 100),
            ]
        )
        location = self._location([(1, -27.5, 153.0), (2, -27.5, 153.0), (3, -27.5, 153.0)])
        assert len(clean_schools(profile, location)) == 3


class TestAggregateIcsea:
    def test_groups_by_sal_and_weights(self):
        df = pd.DataFrame(
            {
                "sal_code": ["10001", "10001", "30002"],
                "icsea": [1000.0, 1100.0, 950.0],
                "enrolments": [100.0, 300.0, 200.0],
            }
        )
        assert aggregate_icsea(df) == {"10001": 1075, "30002": 950}

    def test_null_enrolment_group_falls_back(self):
        df = pd.DataFrame(
            {
                "sal_code": ["10001", "10001"],
                "icsea": [1000.0, 1200.0],
                "enrolments": [float("nan"), 400.0],
            }
        )
        assert aggregate_icsea(df) == {"10001": 1100}

    def test_empty_frame(self):
        df = pd.DataFrame({"sal_code": [], "icsea": [], "enrolments": []})
        assert aggregate_icsea(df) == {}

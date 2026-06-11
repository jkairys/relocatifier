"""ACARA school ICSEA aggregated to SAL: enrolment-weighted mean per suburb.

School identity, ICSEA, enrolments and sector come from ACARA's School
Profile table; coordinates from the School Location table (ADR-0003). The
two are joined by ACARA SML ID — never by school name (ADR-0001). Schools
are assigned to suburbs by point-in-polygon against the SAL boundaries, so
no name-based crosswalk is involved at all.

All sectors (Government, Catholic, Independent) are included. SALs that
contain no ICSEA-bearing school are omitted, so they render grey.
"""

from __future__ import annotations

from collections.abc import Iterable

import geopandas as gpd
import pandas as pd

from ..context import BuildContext
from ..paths import RAW_DIR
from ..sources import Source

# ACARA Data Access Program bulk tables, calendar year 2025. Publisher:
# Australian Curriculum, Assessment and Reporting Authority (ACARA).
# Source page: https://www.acara.edu.au/contact-us/acara-data-access
# Verified June 2026: direct download, no registration required.
SCHOOL_PROFILE = Source(
    name="ACARA School Profile 2025",
    url=(
        "https://dataandreporting.blob.core.windows.net/anrdataportal/"
        "Data-Access-Program/School%20Profile%202025.xlsx"
    ),
    filename="acara_school_profile_2025.xlsx",
)
SCHOOL_LOCATION = Source(
    name="ACARA School Location 2025",
    url=(
        "https://dataandreporting.blob.core.windows.net/anrdataportal/"
        "Data-Access-Program/School%20Location%202025.xlsx"
    ),
    filename="acara_school_location_2025.xlsx",
)

RAW_SOURCES = [SCHOOL_PROFILE, SCHOOL_LOCATION]

METRICS = {
    "icsea": {
        "label": "School ICSEA (avg)",
        "format": "index",
        "direction": "higher_better",
        "notes": (
            "Enrolment-weighted mean ICSEA of schools located in the suburb; "
            "all sectors."
        ),
    },
}

VINTAGES = {"acara": "2025"}

# The workbooks each carry a DataDictionary sheet plus one data sheet.
_PROFILE_SHEET = "SchoolProfile 2025"
_LOCATION_SHEET = "SchoolLocations 2025"

STATES = {"NSW", "QLD"}

# ICSEA is constructed with mean 1000 / SD 100; published values span roughly
# 500-1300. Anything outside that is treated as a data error, not a school.
ICSEA_MIN = 500
ICSEA_MAX = 1300

# Generous Australia-plus-external-territories bounding box (Lord Howe Island
# is NSW at ~159°E). Points outside any NSW/QLD SAL polygon are dropped by the
# spatial join anyway; this only rejects null/garbage coordinates early.
_LAT_RANGE = (-44.0, -9.0)
_LON_RANGE = (96.0, 168.0)


def icsea_in_range(icsea: float | None) -> bool:
    """True when ICSEA is present and within the published sanity range."""
    return icsea is not None and not pd.isna(icsea) and ICSEA_MIN <= icsea <= ICSEA_MAX


def valid_coords(lat: float | None, lon: float | None) -> bool:
    """True when both coordinates are present and plausibly Australian."""
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return False
    return _LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon <= _LON_RANGE[1]


def weighted_mean_icsea(schools: Iterable[tuple[float, float | None]]) -> int | None:
    """Enrolment-weighted mean ICSEA over (icsea, enrolments) pairs, rounded
    to a whole number.

    Falls back to the unweighted mean when any school lacks a positive
    enrolment count — a partial weighting would silently bias the result
    towards whichever schools happened to report enrolments.
    """
    pairs = [(i, e) for i, e in schools]
    if not pairs:
        return None
    weights_usable = all(e is not None and not pd.isna(e) and e > 0 for _, e in pairs)
    if weights_usable:
        total = sum(e for _, e in pairs)
        mean = sum(i * e for i, e in pairs) / total
    else:
        mean = sum(i for i, _ in pairs) / len(pairs)
    return int(round(mean))


def clean_schools(profile: pd.DataFrame, location: pd.DataFrame) -> pd.DataFrame:
    """Join Profile to Location by ACARA SML ID and apply sanity filters.

    Input column names are the raw ACARA headers. Output: one row per school
    with columns acara_id, icsea, enrolments, lat, lon — NSW/QLD only,
    in-range ICSEA, plausible coordinates.
    """
    prof = profile.rename(
        columns={
            "ACARA SML ID": "acara_id",
            "ICSEA": "icsea",
            "Total Enrolments": "enrolments",
            "State": "state",
        }
    )[["acara_id", "icsea", "enrolments", "state"]]
    loc = location.rename(
        columns={
            "ACARA SML ID": "acara_id",
            "Latitude": "lat",
            "Longitude": "lon",
        }
    )[["acara_id", "lat", "lon"]]

    # Inner join by ID only (ADR-0001). Profile is the school-level table;
    # Location rows without a profile (sub-campuses) drop out here.
    schools = prof.merge(loc, on="acara_id", how="inner", validate="one_to_one")

    in_state = schools["state"].isin(STATES)
    icsea_ok = schools["icsea"].map(icsea_in_range)
    coords_ok = [valid_coords(lat, lon) for lat, lon in zip(schools["lat"], schools["lon"])]
    return schools.loc[in_state & icsea_ok & pd.Series(coords_ok, index=schools.index)].drop(
        columns=["state"]
    )


def aggregate_icsea(schools_with_sal: pd.DataFrame) -> dict[str, int]:
    """Per-SAL enrolment-weighted mean ICSEA.

    Expects columns sal_code, icsea, enrolments (one row per school already
    assigned to a suburb).
    """
    out: dict[str, int] = {}
    for sal_code, group in schools_with_sal.groupby("sal_code"):
        value = weighted_mean_icsea(
            (float(i), None if pd.isna(e) else float(e))
            for i, e in zip(group["icsea"], group["enrolments"])
        )
        if value is not None:
            out[str(sal_code)] = value
    return out


def _read_sheet(source: Source, sheet: str) -> pd.DataFrame:
    path = RAW_DIR / source.filename
    if not path.exists():
        raise SystemExit(f"missing {path} — run `etl fetch` first")
    return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")


def assign_suburbs(schools: pd.DataFrame, suburbs: gpd.GeoDataFrame) -> pd.DataFrame:
    """Point-in-polygon: attach sal_code to each school (EPSG:4326)."""
    points = gpd.GeoDataFrame(
        schools,
        geometry=gpd.points_from_xy(schools["lon"], schools["lat"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(points, suburbs[["sal_code", "geometry"]], predicate="within")
    return pd.DataFrame(joined.drop(columns="geometry"))


def build(ctx: BuildContext) -> dict[str, dict[str, float | None]]:
    profile = _read_sheet(SCHOOL_PROFILE, _PROFILE_SHEET)
    location = _read_sheet(SCHOOL_LOCATION, _LOCATION_SHEET)
    schools = clean_schools(profile, location)
    assigned = assign_suburbs(schools, ctx.suburbs)
    return {sal: {"icsea": value} for sal, value in aggregate_icsea(assigned).items()}

"""ABS Census 2021 demographics: median age and % children per SAL.

DataPack joins are by SAL code (ADR-0001). SALs with zero/null population get
null values so their polygons render grey rather than misleadingly coloured.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import duckdb

from ..context import BuildContext
from ..paths import RAW_DIR
from ..sources import Source
from ..transform import normalise_sal_code, pct_children

# ABS Census 2021 General Community Profile DataPack, all of Australia at SAL
# level, short-header variant.
# Source page: https://www.abs.gov.au/census/find-census-data/datapacks
# (2021 Census GCP > Suburbs and Localities > AUS). Licence: CC BY 4.0.
CENSUS_GCP_SAL = Source(
    name="ABS Census 2021 GCP DataPack (SAL, AUS, short header)",
    url=(
        "https://www.abs.gov.au/census/find-census-data/datapacks/download/"
        "2021_GCP_SAL_for_AUS_short-header.zip"
    ),
    filename="2021_GCP_SAL_for_AUS_short-header.zip",
)

RAW_SOURCES = [CENSUS_GCP_SAL]

METRICS = {
    "median_age": {"label": "Median age", "format": "years", "direction": "lower_better"},
    "pct_children": {"label": "% children (0–14)", "format": "percent", "direction": "higher_better"},
}

VINTAGES = {"census": "2021"}


def _extract_census_csvs(workdir: Path) -> dict[str, Path]:
    """Pull the G01 and G02 AUST x SAL CSVs out of the DataPack zip."""
    zip_path = RAW_DIR / CENSUS_GCP_SAL.filename
    if not zip_path.exists():
        raise SystemExit(f"missing {zip_path} — run `etl fetch` first")
    wanted = {"G01": None, "G02": None}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            base = Path(member).name
            for table in wanted:
                if base == f"2021Census_{table}_AUST_SAL.csv":
                    target = workdir / base
                    with zf.open(member) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    wanted[table] = target
    missing = [t for t, p in wanted.items() if p is None]
    if missing:
        raise SystemExit(f"DataPack zip is missing tables: {missing}")
    return wanted


def load_population() -> dict[str, int]:
    """Census 2021 total persons per sal_code (all states; harmless superset)."""
    with tempfile.TemporaryDirectory() as tmp:
        csvs = _extract_census_csvs(Path(tmp))
        rows = duckdb.connect().execute(
            "SELECT SAL_CODE_2021, Tot_P_P FROM read_csv(?, header = true)",
            [str(csvs["G01"])],
        ).fetchall()
    return {normalise_sal_code(code): int(total or 0) for code, total in rows}


def build(ctx: BuildContext) -> dict[str, dict[str, float | None]]:
    with tempfile.TemporaryDirectory() as tmp:
        csvs = _extract_census_csvs(Path(tmp))
        rows = duckdb.connect().execute(
            """
            SELECT
                g01.SAL_CODE_2021    AS sal_code,
                g01.Tot_P_P          AS total_persons,
                g01.Age_0_4_yr_P     AS age_0_4,
                g01.Age_5_14_yr_P    AS age_5_14,
                g02.Median_age_persons AS median_age
            FROM read_csv(?, header = true) AS g01
            LEFT JOIN read_csv(?, header = true) AS g02 USING (SAL_CODE_2021)
            """,
            [str(csvs["G01"]), str(csvs["G02"])],
        ).fetchall()

    metrics: dict[str, dict[str, float | None]] = {}
    for raw_code, total, age_0_4, age_5_14, median_age in rows:
        code = normalise_sal_code(raw_code)
        if code not in ctx.sal_codes:
            continue
        has_population = total is not None and total > 0
        metrics[code] = {
            "median_age": float(median_age) if has_population and median_age is not None else None,
            "pct_children": pct_children(age_0_4, age_5_14, total) if has_population else None,
        }
    return metrics

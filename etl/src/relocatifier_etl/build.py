"""Build the static artifacts: suburbs.pmtiles + metrics.json.

Reads the raw ABS downloads, keeps NSW + QLD Suburbs (SALs), joins Census
metrics by SAL code (never by name — ADR-0001), and emits the artifact
contract defined in docs/PRD.md into app/public/data/.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import duckdb
import geopandas as gpd

from .paths import ARTIFACT_DIR, RAW_DIR
from .sources import CENSUS_GCP_SAL, SAL_BOUNDARIES
from .transform import (
    STATE_NAME_TO_ABBREV,
    display_name,
    metric_stats,
    normalise_sal_code,
    pct_children,
)

METRIC_DEFS = {
    "median_age": {"label": "Median age", "format": "years", "direction": "lower_better"},
    "pct_children": {"label": "% children (0–14)", "format": "percent", "direction": "higher_better"},
}


def load_suburbs() -> gpd.GeoDataFrame:
    """NSW + QLD SAL polygons with sal_code, name, state columns."""
    zip_path = RAW_DIR / SAL_BOUNDARIES.filename
    if not zip_path.exists():
        raise SystemExit(f"missing {zip_path} — run `etl fetch` first")
    gdf = gpd.read_file(f"zip://{zip_path}")
    gdf = gdf[gdf["STE_NAME21"].isin(STATE_NAME_TO_ABBREV)].copy()
    gdf = gdf[gdf.geometry.notna()]  # a few SALs are non-spatial placeholders
    gdf["sal_code"] = gdf["SAL_CODE21"].map(normalise_sal_code)
    gdf["name"] = gdf["SAL_NAME21"].map(display_name)
    gdf["state"] = gdf["STE_NAME21"].map(STATE_NAME_TO_ABBREV)
    return gdf[["sal_code", "name", "state", "geometry"]].to_crs(epsg=4326)


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


def load_census_metrics() -> dict[str, dict[str, float | None]]:
    """Per-SAL metric values keyed by normalised SAL code.

    SALs with zero/null population get null values (their polygons stay).
    """
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
        has_population = total is not None and total > 0
        metrics[code] = {
            "median_age": float(median_age) if has_population and median_age is not None else None,
            "pct_children": pct_children(age_0_4, age_5_14, total) if has_population else None,
        }
    return metrics


def build_pmtiles(suburbs: gpd.GeoDataFrame, out_path: Path) -> None:
    """Render suburb polygons to PMTiles via tippecanoe."""
    if shutil.which("tippecanoe") is None:
        raise SystemExit("tippecanoe not found on PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        seq = Path(tmp) / "suburbs.geojsonl"
        suburbs.to_file(seq, driver="GeoJSONSeq")
        cmd = [
            "tippecanoe",
            "-o", str(out_path),
            "--layer", "suburbs",
            "--minimum-zoom", "4",
            "--maximum-zoom", "12",
            "--detect-shared-borders",
            "--coalesce-densest-as-needed",
            "--simplification", "10",
            "--force",
            "--read-parallel",
            "--quiet",
            str(seq),
        ]
        subprocess.run(cmd, check=True)
    print(f"[artifact] {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


def build_metrics_json(
    suburbs: gpd.GeoDataFrame,
    census: dict[str, dict[str, float | None]],
    out_path: Path,
) -> dict:
    """Assemble metrics.json per the PRD artifact contract."""
    suburb_entries: dict[str, dict] = {}
    for row in suburbs.itertuples():
        values = census.get(row.sal_code, {})
        suburb_entries[row.sal_code] = {
            "name": row.name,
            "state": row.state,
            "values": {metric: values.get(metric) for metric in METRIC_DEFS},
        }

    doc = {
        "schema_version": 1,
        "vintages": {"census": "2021"},
        "metrics": {
            metric: {
                **defn,
                "stats": metric_stats(
                    [
                        entry["values"][metric]
                        for entry in suburb_entries.values()
                        if entry["values"][metric] is not None
                    ]
                ),
            }
            for metric, defn in METRIC_DEFS.items()
        },
        "suburbs": suburb_entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"[artifact] {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    return doc


def build_all() -> None:
    suburbs = load_suburbs()
    print(f"[build] {len(suburbs)} NSW+QLD suburbs loaded from SAL boundaries")
    census = load_census_metrics()
    print(f"[build] census metrics for {len(census)} SALs")

    doc = build_metrics_json(suburbs, census, ARTIFACT_DIR / "metrics.json")
    with_values = sum(
        1 for e in doc["suburbs"].values() if any(v is not None for v in e["values"].values())
    )
    print(f"[build] {with_values}/{len(doc['suburbs'])} suburbs have metric values")

    build_pmtiles(suburbs, ARTIFACT_DIR / "suburbs.pmtiles")

"""Build the static artifacts: suburbs.pmtiles + metrics.json.

Loads the spatial backbone (NSW + QLD SALs), runs every discovered source
module against it, derives cross-source metrics (gross yield), and emits the
artifact contract defined in docs/PRD.md into app/public/data/.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd

from .context import BuildContext
from .paths import ARTIFACT_DIR, RAW_DIR
from .sources import SAL_BOUNDARIES
from .source_modules import iter_source_modules
from .transform import (
    STATE_NAME_TO_ABBREV,
    display_name,
    gross_yield,
    metric_stats,
    normalise_sal_code,
)

# Derived in core, not by any single source module: needs rent AND price.
DERIVED_METRICS = {
    "gross_yield": {"label": "Gross yield", "format": "percent", "direction": "higher_better"},
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
    metric_defs: dict[str, dict],
    values: dict[str, dict[str, float | None]],
    vintages: dict[str, str],
    out_path: Path,
) -> dict:
    """Assemble metrics.json per the PRD artifact contract.

    Metrics with zero non-null values are dropped entirely — the frontend
    then renders them as pending ("soon") rather than as an all-grey layer.
    """
    populated = {
        metric: defn
        for metric, defn in metric_defs.items()
        if any(v.get(metric) is not None for v in values.values())
    }
    for metric in metric_defs.keys() - populated.keys():
        print(f"[build] WARNING: metric {metric} has no values anywhere — dropped")
    metric_defs = populated

    suburb_entries: dict[str, dict] = {}
    centres = suburbs.geometry.representative_point()
    for row, centre in zip(suburbs.itertuples(), centres):
        suburb_values = values.get(row.sal_code, {})
        suburb_entries[row.sal_code] = {
            "name": row.name,
            "state": row.state,
            "centre": [round(centre.x, 4), round(centre.y, 4)],
            "values": {metric: suburb_values.get(metric) for metric in metric_defs},
        }

    doc = {
        "schema_version": 1,
        "vintages": vintages,
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
            for metric, defn in metric_defs.items()
        },
        "suburbs": suburb_entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print(f"[artifact] {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")
    return doc


def build_all() -> None:
    from .source_modules import abs_census

    suburbs = load_suburbs()
    print(f"[build] {len(suburbs)} NSW+QLD suburbs loaded from SAL boundaries")
    ctx = BuildContext(suburbs=suburbs, population=abs_census.load_population())

    metric_defs: dict[str, dict] = {}
    vintages: dict[str, str] = {}
    values: dict[str, dict[str, float | None]] = {}
    for module in iter_source_modules():
        name = module.__name__.rsplit(".", 1)[-1]
        overlap = metric_defs.keys() & module.METRICS.keys()
        if overlap:
            raise SystemExit(f"source module {name} redefines metrics: {sorted(overlap)}")
        module_values = module.build(ctx)
        metric_defs.update(module.METRICS)
        vintages.update(module.VINTAGES)
        for sal_code, suburb_values in module_values.items():
            values.setdefault(sal_code, {}).update(suburb_values)
        covered = sum(
            1 for v in module_values.values() if any(x is not None for x in v.values())
        )
        print(f"[build] {name}: {sorted(module.METRICS)} for {covered} suburbs")

    metric_defs.update(DERIVED_METRICS)
    for suburb_values in values.values():
        suburb_values["gross_yield"] = gross_yield(
            suburb_values.get("median_rent_house"), suburb_values.get("median_house_price")
        )

    doc = build_metrics_json(
        suburbs, metric_defs, values, vintages, ARTIFACT_DIR / "metrics.json"
    )
    with_values = sum(
        1 for e in doc["suburbs"].values() if any(v is not None for v in e["values"].values())
    )
    print(f"[build] {with_values}/{len(doc['suburbs'])} suburbs have metric values")

    build_pmtiles(suburbs, ARTIFACT_DIR / "suburbs.pmtiles")

# Relocatifier ETL

Batch pipeline (Python + DuckDB, per ADR-0002): fetch raw sources, normalise
everything to ABS SAL codes (joins by name are banned — ADR-0001), and emit
the static artifacts the frontend consumes.

## Run

Requires [uv](https://docs.astral.sh/uv/) and [tippecanoe](https://github.com/felt/tippecanoe) on PATH.

```sh
task fetch   # download raw sources into data/raw/ (~300 MB, cached)
task build   # emit ../app/public/data/{suburbs.pmtiles, metrics.json}
task test    # unit tests for the transformation logic (no downloads)
```

(or `uv run etl fetch` / `uv run etl build` / `uv run pytest` directly.)

## Artifacts

Written to `../app/public/data/` per the contract in `docs/PRD.md`:

- `suburbs.pmtiles` — NSW + QLD SAL polygons, layer `suburbs`, zooms 4–12,
  feature properties `sal_code`, `name`, `state`.
- `metrics.json` — schema_version 1; metrics `median_age` and `pct_children`
  (walking skeleton — the remaining v1 metrics land in later build stages),
  with median/p10/p90 stats and per-suburb values keyed by SAL code.
  Suburbs with zero Census population keep their polygons but carry `null`
  values.

## Data sources, vintages, licences

| Source | Vintage | Licence |
|---|---|---|
| ABS Suburbs and Localities (SAL) digital boundaries, ASGS Edition 3, GDA2020 shapefile | 2021 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| ABS Census General Community Profile DataPack, SAL level, all Australia, short header (tables G01, G02) | 2021 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

Direct URLs are hardcoded in `src/relocatifier_etl/sources.py` with the source
pages noted alongside.

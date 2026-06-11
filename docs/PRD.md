# Discovery v1 — PRD

## Goal

A static map of the Search Zone where every Suburb is a choropleth polygon, colourable by seven Metrics, with a click-anywhere suburb stat sheet.

**Done means:** pan along the coast coloured by yield, click a suburb, read its stat sheet.

## Metrics (v1)

| # | Metric | Source | Unit native to source | Notes |
|---|--------|--------|----------------------|-------|
| 1 | Median age | ABS Census 2021 GCP DataPack (G02) | SAL | |
| 2 | % children (0–14) | ABS Census 2021 GCP DataPack (G01) | SAL | (Age 0–4 + 5–14) ÷ total persons |
| 3 | Median weekly rent (houses) | QLD RTA quarterly medians; NSW rental bond lodgements | suburb (QLD), postcode (NSW) | NSW needs POA→SAL crosswalk, labelled approximate |
| 4 | Median house price | NSW Valuer General bulk PSI (computed); QLD suburb-profile scrape | address (NSW), suburb (QLD) | 12-month rolling median of house sales |
| 5 | Gross yield | Derived: rent × 52 ÷ price | — | The headline metric (see CONTEXT.md) |
| 6 | ICSEA (suburb aggregate) | ACARA School Profile + Location tables | school point | Enrolment-weighted mean of schools in suburb |
| 7 | Crime rate | NSW BOCSAR; QLD QPS crime map exports | suburb | Incidents per 1,000 residents (Census population) |

Geographic coverage: all of QLD + NSW ingested; default view centred on the Search Zone. Coastal-band filtering is a UI concern, later.

## Architecture (per ADR-0002)

```
etl/   Python + DuckDB batch pipeline: fetch raw sources → normalise to SAL → emit artifacts
app/   Vite + React + MapLibre GL static frontend: consumes artifacts, no backend
```

### Artifact contract

The ETL emits to `app/public/data/`:

- **`suburbs.pmtiles`** — vector tiles, layer `suburbs`, one feature per SAL polygon with properties `sal_code` (string), `name` (string). Generated with tippecanoe, zooms 4–12.
- **`metrics.json`**:

```json
{
  "schema_version": 1,
  "vintages": {"census": "2021", "...": "..."},
  "metrics": {
    "median_age": {
      "label": "Median age", "format": "years", "direction": "lower_better",
      "stats": {"median": 43, "p10": 33, "p90": 56}
    }
  },
  "suburbs": {
    "<sal_code>": {"name": "Bli Bli", "state": "QLD", "centre": [153.03, -26.62], "values": {"median_age": 38, "...": null}}
  }
}
```

`direction` declares which end is green. `stats` are computed across the Search Zone and drive relative-to-average colouring. Missing values are `null` and render grey.

## Frontend requirements

- Full-screen map, token-free basemap, default view on the QLD/NSW coast.
- Metric switcher (the seven metrics); choropleth fill green=good → red=bad relative to search-zone stats; hard polygon boundaries, never continuous gradients.
- Click suburb → stat sheet panel: name, state, all seven metrics with values or "no data".
- Layer toggle scaffold (suburb fill on/off) designed for more layers later (parcels v1.1).
- Contemporary, clean design; no admin-panel aesthetics.

## Build order (walking skeleton first)

1. **Skeleton**: SAL boundaries + Census (metrics 1–2) end-to-end → map renders, switcher works, stat sheet works.
2. Rents (QLD RTA, NSW bonds + crosswalk).
3. NSW prices (VG PSI); QLD prices (suburb-medians scrape); yield derived.
4. ICSEA aggregation.
5. Crime.
6. Polish pass on frontend.

## Out of scope for v1

Parcels/block-size layer (v1.1) · climate (v1.2) · NAPLAN via MySchool scraper port (Watchlist phase) · listings scraper port, Watchlist mode, Starred Listings (Watchlist phase) · authentication, hosting decisions, multi-user anything.

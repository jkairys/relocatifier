# Static-first architecture: batch ETL → static artifacts → no-backend map

Discovery mode is served entirely by static files: a batch ETL (Python + DuckDB) ingests raw sources, normalises everything to SAL codes, and emits canonical artifacts — vector tiles of suburb boundaries (PMTiles, pre-simplified per zoom) plus a small per-suburb metrics file. A MapLibre GL frontend consumes them from static hosting; switching metrics is a client-side recolour. No server runs in Discovery mode.

## Considered options

- **Server-backed app (FastAPI + Postgres serving the frontend)** — rejected for now: every Discovery dataset is a periodic batch download, ~2,000–4,000 suburbs is small, and running infrastructure before a single suburb is shortlisted is premature. The escape hatch is a thin API over the same DuckDB the ETL already uses; the artifacts and contract don't change, so nothing is wasted if we outgrow static.
- **Raw GeoJSON + Leaflet (the predecessor's approach)** — rejected: a 12 MB GeoJSON worked but was sluggish at QLD-catchment scale; PMTiles + GPU rendering solves the "every suburb on the east coast" volume concern without a tile server.

## Consequences

- The per-suburb metrics artifact is the contract between data layer and frontend — the thing the predecessor never had (its UI globbed raw scraper output and guessed at schemas).
- DuckDB-WASM querying static GeoParquet over HTTP is the planned interactive-query layer for Watchlist mode; it layers onto the same artifacts without rearchitecting.
- Scrapers (listings, NAPLAN) live as separate acquisition services with their own storage, feeding the ETL via export. They are sources, not the platform.

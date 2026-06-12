# Handoff — Discovery v1 shipped (June 2026)

Orientation for a fresh session. Read `CONTEXT.md` (glossary — canonical terms), `docs/adr/` (decisions), `docs/PRD.md` (Discovery v1 spec + artifact contract) before changing anything; this file covers state, provenance, and what's next.

## Where things stand

**Discovery v1 is complete and working.** Static MapLibre choropleth of 7,775 NSW+QLD suburbs (ABS SALs), seven metrics, suburb search, shortlist with compare table, stat sheets. Run it: `task etl:fetch && task etl:build` then `task app:dev`. All code on `main` at github.com/jkairys/relocatifier.

ETL: `etl/` — uv-managed Python, DuckDB + geopandas + tippecanoe. Each data source is an auto-discovered module in `source_modules/` exposing `RAW_SOURCES / METRICS / VINTAGES / build(ctx)`; adding a source touches no shared code. 116 tests (`uv run pytest`). Frontend: `app/` — Vite + React + TS strict + MapLibre + PMTiles. The contract between them is `app/public/data/{suburbs.pmtiles, metrics.json}` (spec in PRD).

## Data provenance (and the caveats that matter)

| Metric | Source | Caveats |
|---|---|---|
| median_age, pct_children | ABS Census 2021 DataPack (SAL) | 2021 vintage; next Census lands mid-2027 |
| median_rent_house | QLD: RTA bond stats workbook (suburb sheet, 3br-house preferred; postcode-sheet fallback where suppressed). NSW: Fair Trading bond lodgements, 12m pooled postcode medians → dominant-overlap SAL | NSW + QLD-fallback values are postcode approximations; ~1,400 QLD SALs still unpublished |
| median_house_price | NSW: computed from Valuer General bulk PSI (12m, ≥5 sales). QLD: scraped OnTheHouse suburb profiles (CoreLogic 12m medians, ~2-3mo lag, 15mo staleness guard) | Different methodologies — don't read small NSW-vs-QLD deltas as signal. QLD scrape cache: `etl/data/raw/qld_prices/` (resumable; errors cached and re-scrapable by deleting their JSON) |
| gross_yield | Derived: rent × 52 ÷ price | Only where both inputs exist (2,662 suburbs, 894 QLD) |
| icsea | ACARA School Profile + Location 2025 (free bulk xlsx), enrolment-weighted mean per SAL | No per-school NAPLAN — that needs the MySchool scraper port (ADR-0003) |
| crime_rate | NSW BOCSAR suburb incidents; QLD QPS crime-map API (undocumented but public; protobuf) | 2021 population denominator vs 2025/26 incidents; CBD/tourist suburbs inflated; <200-population SALs nulled |

Name→SAL joins go through `crosswalk.py` only (exact normalised match, ambiguous names refused — ADR-0001). Known refusals: ~45 NSW VG localities, ~300 QLD crime suburbs, "White Rock"-type same-name-in-state pairs (two QLD White Rocks).

## Operational notes

- Raw downloads (~420 MB) cache in `etl/data/raw/`; artifacts in `app/public/data/`; both gitignored. The QLD OTH scrape (~40 min full) only ever runs incrementally off its cache.
- RTA workbook URL is overwritten in place quarterly; build fails loudly if its quarter drifts from `VINTAGES`. NSW bond files have irregular monthly URLs (dict in `rents.py` with refresh instructions).
- Predecessor repo github.com/jkairys/school-map stays untouched as the quarry (ADR-style decision: port piecemeal). Its listings-scraper (OnTheHouse, Postgres/FastAPI, snapshot diffing) and MySchool NAPLAN scraper port across in the Watchlist phase.

### Deploying (ADR-0005)

Cloudflare Worker (static assets = `app/dist`) + R2 bucket `relocatifier-data` for `/data/*`. Code and data deploy on separate cadences.

- **First-time setup**: `npx wrangler login`; create the bucket (`npx wrangler r2 bucket create relocatifier-data`); `task data:publish` to upload the artifacts; set the `CLOUDFLARE_API_TOKEN` repo secret (Actions). A push to `main` then deploys the app.
- **Steady state**: push to `main` → GitHub Actions builds `app/` and deploys code (`.github/workflows/deploy.yml`). After a quarterly `task etl:build`, run `task data:publish` to re-upload `suburbs.pmtiles` + `metrics.json` to R2. `task deploy` does a manual build-and-deploy from your machine if needed.
- Custom domain is a `TODO-DOMAIN` placeholder in `wrangler.jsonc`; until it's filled in, the app lives on `*.workers.dev`.

## Next steps, in rough order

1. **Small**: QLD price ambiguous-name fix — disambiguate same-name OTH slugs by matching slug postcode to each SAL's dominant POA (machinery exists in `rents.py::dominant_zone_by_area`); recovers White Rock & ~14 friends. Also worth trying for the QLD crime unmatched names.
2. **v1.1 Parcels**: block-size layer. Port `school-map/services/parcel-analytics` (QLD ArcGIS cadastre, adaptive batching) + add NSW DCS Spatial cadastre; zoom-dependent rendering (individual parcels coloured by size ≥z13, suburb median block size choropleth below). User's filter: targets 600–800 m² blocks, avoids ~400 m² new estates.
3. **v1.2 Climate**: BOM gridded climatology sampled at suburb centroids (monthly temp/rain).
4. **Watchlist phase**: recent-sales-per-suburb is fully worked up in issue #3 (recentlysold-only port, DuckDB store + artifact reads per ADR-0006, queried-SAL assignment per ADR-0007) — start there. Then: forsale observation for time-on-market, Starred Listings hand-import, NAPLAN via slimmed MySchool scraper keyed by ACARA ID.

## Working-style notes (the user's stated preferences)

Sub-agents aggressively for investigation/implementation; protect the main context. Decisions get written into CONTEXT.md/ADRs as they crystallise, not batched. Choropleths with hard boundaries, green=good/red=bad, relative-to-search-zone colouring; never rainbow gradients. Honest gaps over guessed joins, always.

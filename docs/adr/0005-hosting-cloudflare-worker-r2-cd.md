# Hosting: Cloudflare Worker + R2, with split deploys

Discovery is hosted on a Cloudflare Worker with static assets: the Vite build (`app/dist`) ships as the asset bundle, and a small worker intercepts `/data/*` to range-serve the artifacts (`suburbs.pmtiles`, `metrics.json`) from an R2 bucket. Code deploys from GitHub Actions on push to `main`; data is published separately from the local machine, because the raw caches (~420 MB) and the ~40-minute QLD scrape that produce the artifacts live only there (ADR-0002's batch ETL is a developer-machine job, not a CI job). The same `/data/*` URLs the app already fetches are honoured in production, so no app code changes.

## Considered options

- **Cloudflare Pages git-integration** — rejected on two counts: Pages' static-asset serving doesn't reliably honour HTTP Range, which PMTiles depends on for tile reads; and Pages wants to build on push, but the artifacts can't be built in CI anyway. The worker exists precisely to range-serve from R2.
- **Committing the artifacts to the repo** — rejected: a 17 MB binary that re-churns every quarter, and they're gitignored by design (`app/public/data/`). R2 + a publish task keeps the repo a code repo.

## Consequences

- `/data/*` is now a worker contract — a stateless range-serving shim over R2, returning 206/Content-Range for ranged reads, 304 for conditional ones, ETag from R2. ADR-0002's "no backend" is amended to **no *dynamic* backend**: this shim runs no logic over the data, just serves bytes with the right headers.
- Local dev is unchanged: Vite serves `app/public/data/` directly; the worker only exists in production.
- Two release cadences: push to `main` deploys code; `task data:publish` refreshes data (quarterly). First-time setup needs a `wrangler login`, the `relocatifier-data` bucket created, and the `CLOUDFLARE_API_TOKEN` repo secret set — see `docs/HANDOFF.md`.
- The custom domain is not yet chosen; until the `routes` block in `wrangler.jsonc` is filled in, deploys land on `*.workers.dev`.

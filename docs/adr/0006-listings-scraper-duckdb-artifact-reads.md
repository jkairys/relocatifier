# Listings scraper stores in DuckDB; frontend reads exported artifacts, never the service

The listings-scraper port (Watchlist phase, scoped by ADR-0004 to OnTheHouse historical research) does not bring its Postgres/PostGIS/SQLAlchemy stack across. The acquisition service stores in its own DuckDB file — the "thin API over the same DuckDB" escape hatch anticipated in ADR-0002 — and the frontend never reads from the service: at the end of each run the service exports a sales artifact into `app/public/data/`, extending the existing artifact contract. The local service is control-plane only (Watchlist membership, triggering runs).

## Considered options

- **Postgres in Docker, port as-is** — rejected: least code churn, but requires Docker+Postgres running to use a personal local tool, reintroducing the infrastructure ADR-0002 deferred. The Postgres job queue (`FOR UPDATE SKIP LOCKED`) coordinated parallel multi-vendor workers that no longer exist.
- **SQLite** — rejected: zero-infra too, and would keep the old SQLAlchemy code, but adds a second database tech when DuckDB is already the project's data engine and the ETL reads it natively.
- **Live API reads from the service** — rejected: freshest reads, but sales would vanish whenever the service is down, and it creates a second frontend–data interface beside the artifact contract. The deployed site (relocatifier.com) has no local service, so artifact reads are the only path that works everywhere.

## Consequences

- DuckDB is single-writer: the service must open connections per operation (or write-then-release), never hold a long-lived read-write handle, or concurrent ETL reads of the same file fail.
- The old SQLAlchemy reconciler and Alembic migrations are not ported; the Property/Listing/Snapshot *schema shape* (including write-once `raw_payload` provenance) is kept in DuckDB DDL so that forsale observation (snapshot diffing, time-on-market) can be switched on later without a storage redesign.
- Freshly scraped sales appear only after the post-run export (seconds, automatic) and a frontend data reload. In production the sales artifact reaches R2 via the same `task data:publish` path as the other artifacts (ADR-0005).

"""DuckDB storage — per-operation connections only (ADR-0006).

DuckDB is single-writer: the service must never hold a long-lived read-write
handle, or a concurrent ETL read of the same file fails. Every public function
here opens a connection, does its work, and closes — callers (FastAPI handlers,
the run loop) drive one operation at a time.

The schema mirrors the school-map Property/Listing/Snapshot shape (ADR-0006)
so forsale observation can be switched on later without a storage redesign.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import duckdb

_DDL = """
CREATE TABLE IF NOT EXISTS watchlist (
    sal_code    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    state       TEXT NOT NULL,
    oth_slug    TEXT NOT NULL,
    added_at    TIMESTAMP NOT NULL,
    last_run_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS property (
    property_uid         TEXT PRIMARY KEY,
    external_property_id TEXT NOT NULL,
    source               TEXT NOT NULL DEFAULT 'oth',
    formatted_address    TEXT,
    postcode             TEXT,
    lat                  DOUBLE,
    lon                  DOUBLE,
    first_seen_at        TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS listing (
    listing_uid         TEXT PRIMARY KEY,
    property_uid        TEXT NOT NULL,
    external_listing_id TEXT NOT NULL,
    source              TEXT NOT NULL DEFAULT 'oth',
    category            TEXT NOT NULL,
    sal_code            TEXT NOT NULL,
    sale_date           DATE,
    agent_name          TEXT,
    agency_name         TEXT,
    first_seen_at       TIMESTAMP NOT NULL,
    last_seen_at        TIMESTAMP NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS listing_snapshot_id_seq START 1;

CREATE TABLE IF NOT EXISTS listing_snapshot (
    snapshot_id    BIGINT PRIMARY KEY DEFAULT nextval('listing_snapshot_id_seq'),
    listing_uid    TEXT NOT NULL,
    observed_at    TIMESTAMP NOT NULL,
    price          BIGINT,
    price_high     BIGINT,
    price_kind     TEXT,
    price_display  TEXT,
    bedrooms       INTEGER,
    bathrooms      INTEGER,
    parking        INTEGER,
    land_size_sqm  INTEGER,
    property_type  TEXT,
    status         TEXT,
    raw_payload    JSON NOT NULL,
    changed_fields VARCHAR[]
);

CREATE TABLE IF NOT EXISTS run (
    run_id      TEXT PRIMARY KEY,
    started_at  TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status      TEXT NOT NULL,
    detail      JSON
);
"""


@contextlib.contextmanager
def connect(db_path: Path, *, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a DuckDB connection for a single operation, then close it.

    Per ADR-0006 callers must scope each connection to one operation. The parent
    directory is created on demand so the first write succeeds on a clean tree.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Create the schema if absent. Idempotent — safe to call on every startup."""
    with connect(db_path) as conn:
        conn.execute(_DDL)

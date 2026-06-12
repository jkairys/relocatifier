"""Export the sales artifact (`app/public/data/sales.json`) at end of run.

One read query joins the latest snapshot per listing to its property and
watchlist suburb, filters to sales <= 12 months old, and groups by SAL. The
frontend reads this static file (ADR-0006); a 404 is normal when the watchlist
is empty.

Sales are sorted by sale_date desc, nulls last. Any field may be null except
address. `price` is null for suppressed sales (never 0).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scraper.storage import connect

SCHEMA_VERSION = 2
_WINDOW_MONTHS = 12

# Property types excluded from the sales artifact (the exporter filters; DuckDB
# keeps storing every type as raw provenance). Everything else — House,
# Townhouse, DuplexSemi-detached, AcreageSemi-rural, Unknown/null — is retained.
EXCLUDED_PROPERTY_TYPES = frozenset({"Unit", "Apartment", "Land", "Commercial"})


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_sales_payload(
    db_path: Path,
    *,
    now: datetime | None = None,
    window_months: int = _WINDOW_MONTHS,
) -> dict:
    """Build the sales artifact dict from the store (no file write)."""
    now = now or datetime.now(tz=timezone.utc)
    cutoff = (now.date() - timedelta(days=int(window_months * 30.4375)))

    with connect(db_path, read_only=True) as conn:
        suburbs = conn.execute(
            """
            SELECT sal_code, name, state, oth_slug, last_run_at
            FROM watchlist
            ORDER BY sal_code
            """
        ).fetchall()

        suburbs_out: dict[str, dict] = {}
        for sal_code, name, state, oth_slug, last_run_at in suburbs:
            rows = conn.execute(
                """
                WITH latest AS (
                    SELECT s.*,
                           row_number() OVER (
                               PARTITION BY s.listing_uid ORDER BY s.snapshot_id DESC
                           ) AS rn
                    FROM listing_snapshot s
                    JOIN listing l ON l.listing_uid = s.listing_uid
                    WHERE l.sal_code = ?
                )
                SELECT p.formatted_address, latest.price, latest.price_display,
                       latest.bedrooms, latest.bathrooms, latest.parking,
                       latest.land_size_sqm, latest.property_type, l.sale_date,
                       p.lat, p.lon
                FROM latest
                JOIN listing l ON l.listing_uid = latest.listing_uid
                JOIN property p ON p.property_uid = l.property_uid
                WHERE latest.rn = 1
                  AND (l.sale_date IS NULL OR l.sale_date >= ?)
                ORDER BY l.sale_date DESC NULLS LAST
                """,
                [sal_code, cutoff],
            ).fetchall()

            sales = [
                {
                    "address": address,
                    "price": price,
                    "price_display": price_display,
                    "bedrooms": bedrooms,
                    "bathrooms": bathrooms,
                    "parking": parking,
                    "land_size_sqm": land_size_sqm,
                    "property_type": property_type,
                    "sale_date": sale_date.isoformat()
                    if isinstance(sale_date, date)
                    else sale_date,
                    "lat": lat,
                    "lon": lon,
                }
                for (
                    address,
                    price,
                    price_display,
                    bedrooms,
                    bathrooms,
                    parking,
                    land_size_sqm,
                    property_type,
                    sale_date,
                    lat,
                    lon,
                ) in rows
                if property_type not in EXCLUDED_PROPERTY_TYPES
            ]

            fetched_at = _iso(last_run_at) if isinstance(last_run_at, datetime) else None
            suburbs_out[sal_code] = {
                "name": name,
                "state": state,
                "oth_slug": oth_slug,
                "fetched_at": fetched_at,
                "sales": sales,
            }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(now),
        "suburbs": suburbs_out,
    }


def export_sales(
    db_path: Path,
    output_path: Path,
    *,
    now: datetime | None = None,
) -> Path:
    """Write the sales artifact to `output_path`. Returns the path written."""
    payload = build_sales_payload(db_path, now=now)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    return output_path

"""Reconcile a parsed listing into the DuckDB store.

Snapshot semantics for recentlysold v1 (per CONTRACTS.md):

- property: upsert by `property_uid` ("oth:<external_property_id>"); identity
  + first_seen_at written once.
- listing: upsert by `listing_uid` ("oth:recentlysold:<external_listing_id>").
  `sal_code` and `sale_date` are WRITE-ONCE (never overwritten once non-null,
  ADR-0007). agent/agency and last_seen_at are refreshed.
- listing_snapshot: write a NEW snapshot only when a material field changed
  (price, price_kind, bedrooms, bathrooms, parking, land_size_sqm,
  property_type, status); otherwise just bump listing.last_seen_at. The very
  first observation always writes a snapshot. `raw_payload` is stored verbatim.

The caller passes the parsed `VendorListing`, its verbatim raw payload, and the
queried `sal_code`. One reconcile == one short-lived write (ADR-0006); the
caller opens/closes the connection per the run loop's batching.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from duckdb import DuckDBPyConnection

from scraper.sale_date import extract_sale_date
from scraper.vendor import VendorListing

# Fields whose change triggers a new snapshot.
_MATERIAL_FIELDS = (
    "price",
    "price_kind",
    "bedrooms",
    "bathrooms",
    "parking",
    "land_size_sqm",
    "property_type",
    "status",
)


def property_uid(external_property_id: str) -> str:
    return f"oth:{external_property_id}"


def listing_uid(external_listing_id: str) -> str:
    return f"oth:recentlysold:{external_listing_id}"


def reconcile_listing(
    conn: DuckDBPyConnection,
    listing: VendorListing,
    raw_payload: dict,
    *,
    sal_code: str,
    observed_at: datetime | None = None,
) -> bool:
    """Upsert one listing; return True when a new snapshot was written."""
    observed_at = observed_at or listing.observed_at or datetime.now(tz=timezone.utc)
    prop_uid = property_uid(listing.external_property_id or listing.external_listing_id)
    lst_uid = listing_uid(listing.external_listing_id)

    _upsert_property(conn, prop_uid, listing, observed_at)
    sale_date = extract_sale_date(raw_payload)
    _upsert_listing(conn, lst_uid, prop_uid, listing, sal_code, sale_date, observed_at)

    snapshot = _latest_snapshot_material(conn, lst_uid)
    current = _material_tuple(listing)
    if snapshot is not None and snapshot == current:
        # Nothing material changed: bump last_seen_at only.
        conn.execute(
            "UPDATE listing SET last_seen_at = ? WHERE listing_uid = ?",
            [observed_at, lst_uid],
        )
        return False

    changed = _changed_fields(snapshot, current)
    _write_snapshot(conn, lst_uid, listing, raw_payload, observed_at, changed)
    return True


def _upsert_property(
    conn: DuckDBPyConnection,
    prop_uid: str,
    listing: VendorListing,
    observed_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO property (
            property_uid, external_property_id, source,
            formatted_address, postcode, lat, lon, first_seen_at
        )
        VALUES (?, ?, 'oth', ?, ?, ?, ?, ?)
        ON CONFLICT (property_uid) DO UPDATE SET
            formatted_address = COALESCE(excluded.formatted_address, property.formatted_address),
            postcode = COALESCE(excluded.postcode, property.postcode),
            lat = COALESCE(excluded.lat, property.lat),
            lon = COALESCE(excluded.lon, property.lon)
        """,
        [
            prop_uid,
            listing.external_property_id or listing.external_listing_id,
            listing.formatted_address,
            listing.postcode or None,
            listing.latitude,
            listing.longitude,
            observed_at,
        ],
    )


def _upsert_listing(
    conn: DuckDBPyConnection,
    lst_uid: str,
    prop_uid: str,
    listing: VendorListing,
    sal_code: str,
    sale_date,
    observed_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO listing (
            listing_uid, property_uid, external_listing_id, source, category,
            sal_code, sale_date, agent_name, agency_name,
            first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, 'oth', 'recentlysold', ?, ?, ?, ?, ?, ?)
        ON CONFLICT (listing_uid) DO UPDATE SET
            -- sal_code and sale_date are write-once: keep the existing value.
            sale_date = COALESCE(listing.sale_date, excluded.sale_date),
            agent_name = excluded.agent_name,
            agency_name = excluded.agency_name,
            last_seen_at = excluded.last_seen_at
        """,
        [
            lst_uid,
            prop_uid,
            listing.external_listing_id,
            sal_code,
            sale_date,
            listing.agent_name,
            listing.agency_name,
            observed_at,
            observed_at,
        ],
    )


def _latest_snapshot_material(conn: DuckDBPyConnection, lst_uid: str):
    row = conn.execute(
        """
        SELECT price, price_kind, bedrooms, bathrooms, parking,
               land_size_sqm, property_type, status
        FROM listing_snapshot
        WHERE listing_uid = ?
        ORDER BY snapshot_id DESC
        LIMIT 1
        """,
        [lst_uid],
    ).fetchone()
    return tuple(row) if row is not None else None


def _material_tuple(listing: VendorListing) -> tuple:
    land = listing.land_size_sqm
    return (
        listing.price,
        listing.price_kind.value,
        listing.bedrooms,
        listing.bathrooms,
        listing.parking,
        int(land) if land is not None else None,
        listing.property_type,
        listing.status,
    )


def _changed_fields(previous, current: tuple) -> list[str]:
    if previous is None:
        return list(_MATERIAL_FIELDS)
    return [
        field
        for field, old, new in zip(_MATERIAL_FIELDS, previous, current)
        if old != new
    ]


def _write_snapshot(
    conn: DuckDBPyConnection,
    lst_uid: str,
    listing: VendorListing,
    raw_payload: dict,
    observed_at: datetime,
    changed_fields: list[str],
) -> None:
    land = listing.land_size_sqm
    conn.execute(
        """
        INSERT INTO listing_snapshot (
            listing_uid, observed_at, price, price_high, price_kind, price_display,
            bedrooms, bathrooms, parking, land_size_sqm, property_type, status,
            raw_payload, changed_fields
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            lst_uid,
            observed_at,
            listing.price,
            listing.price_high,
            listing.price_kind.value,
            listing.raw_price_display,
            listing.bedrooms,
            listing.bathrooms,
            listing.parking,
            int(land) if land is not None else None,
            listing.property_type,
            listing.status,
            json.dumps(raw_payload),
            changed_fields,
        ],
    )

"""Watchlist membership operations — per-operation DuckDB connections (ADR-0006).

Adding a suburb stores its resolved OTH slug (ADR-0007); removing keeps all
scraped data and only drops membership.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scraper.resolver import ResolvedSAL
from scraper.storage import connect
from scraper.vendor import ResolvedSuburb


def list_watchlist(db_path: Path) -> list[dict]:
    """Return watchlist entries with a per-suburb listing_count, by sal_code."""
    with connect(db_path, read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT w.sal_code, w.name, w.state, w.oth_slug, w.added_at, w.last_run_at,
                   (SELECT count(*) FROM listing l WHERE l.sal_code = w.sal_code) AS listing_count
            FROM watchlist w
            ORDER BY w.sal_code
            """
        ).fetchall()
    return [
        {
            "sal_code": sal_code,
            "name": name,
            "state": state,
            "oth_slug": oth_slug,
            "added_at": added_at,
            "last_run_at": last_run_at,
            "listing_count": listing_count,
        }
        for sal_code, name, state, oth_slug, added_at, last_run_at, listing_count in rows
    ]


def is_on_watchlist(db_path: Path, sal_code: str) -> bool:
    with connect(db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM watchlist WHERE sal_code = ?", [sal_code]
        ).fetchone()
    return row is not None


def add_to_watchlist(db_path: Path, resolved: ResolvedSAL) -> dict:
    """Insert a resolved suburb. Returns the stored entry."""
    added_at = datetime.now(tz=timezone.utc)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO watchlist (sal_code, name, state, oth_slug, added_at, last_run_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            [resolved.sal_code, resolved.name, resolved.state, resolved.oth_slug, added_at],
        )
    return {
        "sal_code": resolved.sal_code,
        "name": resolved.name,
        "state": resolved.state,
        "oth_slug": resolved.oth_slug,
        "added_at": added_at,
        "last_run_at": None,
        "listing_count": 0,
    }


def remove_from_watchlist(db_path: Path, sal_code: str) -> None:
    """Drop membership; scraped data is retained."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM watchlist WHERE sal_code = ?", [sal_code])


def resolved_suburbs(db_path: Path, sal_codes: list[str] | None) -> list[ResolvedSuburb]:
    """Build `ResolvedSuburb` search inputs for the given SALs (or all if None)."""
    with connect(db_path, read_only=True) as conn:
        if sal_codes is None:
            rows = conn.execute(
                "SELECT sal_code, name, state, oth_slug FROM watchlist ORDER BY sal_code"
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in sal_codes)
            rows = conn.execute(
                f"SELECT sal_code, name, state, oth_slug FROM watchlist "
                f"WHERE sal_code IN ({placeholders}) ORDER BY sal_code",
                sal_codes,
            ).fetchall()
    return [
        ResolvedSuburb(
            sal_code=sal_code,
            name=name,
            state=state,
            postcode=oth_slug.rsplit("-", 1)[1],
            oth_slug=oth_slug,
        )
        for sal_code, name, state, oth_slug in rows
    ]


def mark_run_completed(db_path: Path, sal_codes: list[str], finished_at: datetime) -> None:
    """Set last_run_at for the suburbs covered by a finished run."""
    if not sal_codes:
        return
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in sal_codes)
        conn.execute(
            f"UPDATE watchlist SET last_run_at = ? WHERE sal_code IN ({placeholders})",
            [finished_at, *sal_codes],
        )

"""Run orchestration: single-flight, paginated scrape, reconcile, export.

A run fetches each suburb's OTH recentlysold pages politely (the client applies
the 1.5–3.0 s jittered spacing), stopping when a page's sales are all older than
12 months, when `last == true`, or after the page cap — whichever first. Each
listing is reconciled into DuckDB. After all suburbs the sales artifact is
exported and `last_run_at` is bumped.

Single-flight is enforced by `RunRegistry`: at most one run is in progress at a
time. Anti-bot detection (`AntiBotError`) aborts the run, marking it failed with
an honest detail message — no retries past the client's own spacing.

Per ADR-0006 the reconcile writes use a short-lived connection per suburb; the
API process never pins a long-lived read-write handle.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from scraper import watchlist
from scraper.config import Settings
from scraper.oth_client import AntiBotError, OTHClient
from scraper.reconciler import reconcile_listing
from scraper.sale_date import extract_sale_date
from scraper.storage import connect
from scraper.vendor import ResolvedSuburb

logger = logging.getLogger(__name__)


class RunInProgressError(RuntimeError):
    """Raised when a run is requested while one is already in progress (→ 409)."""


class RunRegistry:
    """Single-flight guard plus the run-row lifecycle in DuckDB."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._active = False

    def begin(self, sal_codes: list[str]) -> str:
        """Reserve the single-flight slot and create the run row. Raises if busy."""
        with self._lock:
            if self._active:
                raise RunInProgressError("a run is already in progress")
            self._active = True
        run_id = uuid.uuid4().hex
        started_at = datetime.now(tz=timezone.utc)
        with connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO run (run_id, started_at, finished_at, status, detail) "
                "VALUES (?, ?, NULL, 'running', ?)",
                [run_id, started_at, json.dumps({"sal_codes": sal_codes})],
            )
        return run_id

    def finish(self, run_id: str, status: str, detail: dict) -> None:
        finished_at = datetime.now(tz=timezone.utc)
        with connect(self._db_path) as conn:
            conn.execute(
                "UPDATE run SET finished_at = ?, status = ?, detail = ? WHERE run_id = ?",
                [finished_at, status, json.dumps(detail), run_id],
            )
        with self._lock:
            self._active = False

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active


def get_run(db_path: Path, run_id: str) -> Optional[dict]:
    with connect(db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT run_id, started_at, finished_at, status, detail FROM run WHERE run_id = ?",
            [run_id],
        ).fetchone()
    return _run_row(row) if row else None


def list_runs(db_path: Path, *, limit: int = 10) -> list[dict]:
    with connect(db_path, read_only=True) as conn:
        rows = conn.execute(
            "SELECT run_id, started_at, finished_at, status, detail FROM run "
            "ORDER BY started_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return [_run_row(r) for r in rows]


def _run_row(row) -> dict:
    run_id, started_at, finished_at, status, detail = row
    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "detail": json.loads(detail) if isinstance(detail, str) else detail,
    }


def execute_run(
    db_path: Path,
    settings: Settings,
    registry: RunRegistry,
    run_id: str,
    sal_codes: list[str],
    *,
    client: Optional[OTHClient] = None,
    now: datetime | None = None,
) -> dict:
    """Scrape the given suburbs, reconcile, export, and finalise the run.

    Returns the run detail. Owns the OTH client unless one is injected (tests
    inject a MockTransport-backed client). Always finalises the run row and
    releases the single-flight slot, even on failure.
    """
    now = now or datetime.now(tz=timezone.utc)
    cutoff = now.date() - timedelta(days=int(settings.sale_window_months * 30.4375))
    suburbs = watchlist.resolved_suburbs(db_path, sal_codes)
    covered = [s.sal_code for s in suburbs]

    detail: dict = {"suburbs": {}, "errors": []}
    owns_client = client is None
    client = client or OTHClient(
        page_size=settings.page_size,
        timeout_s=settings.http_timeout_s,
        rate_limiter=None,
    )

    status = "completed"
    try:
        for suburb in suburbs:
            try:
                counts = _scrape_suburb(db_path, settings, client, suburb, cutoff)
                detail["suburbs"][suburb.sal_code] = counts
            except AntiBotError as exc:
                # Abort the whole run honestly — no point hammering a blocked host.
                detail["errors"].append(
                    {"sal_code": suburb.sal_code, "error": f"anti-bot block: {exc}"}
                )
                status = "failed"
                break
            except Exception as exc:  # noqa: BLE001 - record and continue other suburbs
                logger.exception("suburb %s failed", suburb.sal_code)
                detail["errors"].append(
                    {"sal_code": suburb.sal_code, "error": str(exc)}
                )
                status = "failed"
    finally:
        if owns_client:
            client.close()

    # Bump last_run_at for suburbs we actually processed, then export.
    processed = list(detail["suburbs"].keys())
    if processed:
        watchlist.mark_run_completed(db_path, processed, now)

    from scraper.exporter import export_sales

    try:
        export_sales(db_path, settings.sales_artifact_path, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sales export failed")
        detail["errors"].append({"error": f"export failed: {exc}"})
        status = "failed"

    detail["covered"] = covered
    registry.finish(run_id, status, detail)
    return detail


def _scrape_suburb(
    db_path: Path,
    settings: Settings,
    client: OTHClient,
    suburb: ResolvedSuburb,
    cutoff: date,
) -> dict:
    """Paginate one suburb, reconciling each page. Returns per-suburb counts."""
    listings_seen = 0
    snapshots_written = 0
    pages = 0

    for page in range(settings.max_pages):
        result = client.search(suburb, page)
        pages += 1

        with connect(db_path) as conn:
            for listing, raw in zip(result.listings, result.raw_payloads):
                listings_seen += 1
                if reconcile_listing(conn, listing, raw, sal_code=suburb.sal_code):
                    snapshots_written += 1

        # Stop once every sale on this page is older than the window, or OTH
        # says this was the last page.
        page_dates = [extract_sale_date(raw) for raw in result.raw_payloads]
        all_old = bool(page_dates) and all(
            d is not None and d < cutoff for d in page_dates
        )
        if all_old or not result.has_next:
            break

    return {
        "pages": pages,
        "listings_seen": listings_seen,
        "snapshots_written": snapshots_written,
    }

"""FastAPI control plane (port 8210).

Control-plane only (ADR-0006): watchlist membership + triggering runs. The
frontend never reads listings from here — it reads the exported sales.json. Runs
execute in-process as a background task with per-operation DuckDB connections.

CORS is open to the local Vite dev server (localhost/127.0.0.1, any port).
"""

from __future__ import annotations

from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scraper import watchlist
from scraper.config import Settings, load_settings
from scraper.exporter import export_sales
from scraper.resolver import (
    SalNotFoundError,
    SlugResolutionError,
    resolve_slug,
)
from scraper.runs import (
    RunInProgressError,
    RunRegistry,
    execute_run,
    get_run,
    list_runs,
)
from scraper.storage import init_db


class RunRequest(BaseModel):
    sal_codes: Optional[list[str]] = None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. `settings` is injectable so tests point at a temp DB."""
    settings = settings or load_settings()
    init_db(settings.duckdb_path)
    registry = RunRegistry(settings.duckdb_path)

    app = FastAPI(title="relocatifier-scraper", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.registry = registry

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/watchlist")
    def get_watchlist() -> list[dict]:
        return watchlist.list_watchlist(settings.duckdb_path)

    @app.post("/watchlist/{sal_code}", status_code=201)
    def add_watchlist(sal_code: str) -> dict:
        if watchlist.is_on_watchlist(settings.duckdb_path, sal_code):
            raise HTTPException(status_code=409, detail=f"{sal_code} already on watchlist")
        try:
            resolved = resolve_slug(
                sal_code,
                metrics_path=settings.metrics_path,
                sitemap_cache_path=settings.sitemap_cache_path,
            )
        except SalNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SlugResolutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return watchlist.add_to_watchlist(settings.duckdb_path, resolved)

    @app.delete("/watchlist/{sal_code}", status_code=204)
    def delete_watchlist(sal_code: str) -> None:
        watchlist.remove_from_watchlist(settings.duckdb_path, sal_code)

    @app.post("/runs", status_code=202)
    def start_run(body: RunRequest, background: BackgroundTasks) -> dict:
        sal_codes = body.sal_codes
        try:
            run_id = registry.begin(sal_codes or [])
        except RunInProgressError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        background.add_task(
            execute_run,
            settings.duckdb_path,
            settings,
            registry,
            run_id,
            sal_codes,
        )
        return {"run_id": run_id}

    @app.post("/export")
    def export() -> dict:
        """Regenerate sales.json from the existing store, no scraping. Fast and
        synchronous — used whenever the artifact schema changes."""
        written = export_sales(settings.duckdb_path, settings.sales_artifact_path)
        return {"status": "ok", "path": str(written)}

    @app.get("/runs")
    def recent_runs(limit: int = 10) -> list[dict]:
        return list_runs(settings.duckdb_path, limit=limit)

    @app.get("/runs/{run_id}")
    def run_status(run_id: str) -> dict:
        run = get_run(settings.duckdb_path, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return run

    return app


app = create_app()

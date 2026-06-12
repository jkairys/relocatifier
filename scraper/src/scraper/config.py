"""Runtime configuration, resolved from environment with sensible defaults.

All paths default relative to the `scraper/` project root so the service runs
the same from the worktree as from a checkout. Override via the `SCRAPER_*`
environment variables; tests construct `Settings` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# scraper/src/scraper/config.py -> scraper/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Resolved service settings."""

    duckdb_path: Path
    metrics_path: Path
    sitemap_cache_path: Path
    sales_artifact_path: Path

    # Rate limiting between OTH requests (jittered 1.5–3.0 s by default).
    rate_limit_min_interval_s: float = 1.5
    rate_limit_max_interval_s: float = 3.0

    # Pagination caps for a single suburb run.
    max_pages: int = 10
    page_size: int = 24
    sale_window_months: int = 12

    http_timeout_s: float = 30.0


def _env_path(key: str, default: Path) -> Path:
    raw = os.environ.get(key)
    return Path(raw).expanduser().resolve() if raw else default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    return float(raw) if raw else default


def load_settings() -> Settings:
    """Build `Settings` from the environment, defaulting under the project root."""
    return Settings(
        duckdb_path=_env_path(
            "SCRAPER_DUCKDB_PATH", _PROJECT_ROOT / "data" / "listings.duckdb"
        ),
        metrics_path=_env_path(
            "SCRAPER_METRICS_PATH",
            (_PROJECT_ROOT / ".." / "app" / "public" / "data" / "metrics.json").resolve(),
        ),
        sitemap_cache_path=_env_path(
            "SCRAPER_SITEMAP_CACHE_PATH",
            _PROJECT_ROOT / "data" / "oth_sitemap.xml",
        ),
        sales_artifact_path=_env_path(
            "SCRAPER_SALES_ARTIFACT_PATH",
            (_PROJECT_ROOT / ".." / "app" / "public" / "data" / "sales.json").resolve(),
        ),
        rate_limit_min_interval_s=_env_float("SCRAPER_RATE_LIMIT_MIN_INTERVAL", 1.5),
        rate_limit_max_interval_s=_env_float("SCRAPER_RATE_LIMIT_MAX_INTERVAL", 3.0),
    )

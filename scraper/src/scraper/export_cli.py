"""Export-only entry point: regenerate sales.json from the existing DuckDB.

No scraping — just re-runs the exporter against the current store. Needed
whenever the artifact schema changes (e.g. the v2 lat/lon + type-filter bump).
Invoke via ``uv run python -m scraper.export_cli`` or the matching
``POST /export`` API endpoint.
"""

from __future__ import annotations

from scraper.config import load_settings
from scraper.exporter import export_sales


def main() -> None:
    """Export the sales artifact to the configured path, printing where."""
    settings = load_settings()
    written = export_sales(settings.duckdb_path, settings.sales_artifact_path)
    print(f"wrote {written}")


if __name__ == "__main__":
    main()

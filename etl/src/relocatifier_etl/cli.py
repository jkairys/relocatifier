"""`etl` command-line interface."""

import typer

app = typer.Typer(help="Relocatifier ETL: fetch raw sources and build static artifacts.", no_args_is_help=True)


@app.command()
def fetch() -> None:
    """Download raw sources into etl/data/raw/ (skips files already present)."""
    from .fetch import fetch_all

    fetch_all()


@app.command()
def build() -> None:
    """Build app/public/data/suburbs.pmtiles and metrics.json from raw sources."""
    from .build import build_all

    build_all()


if __name__ == "__main__":
    app()

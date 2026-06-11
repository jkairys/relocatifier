"""Filesystem layout for the ETL.

Everything is resolved relative to the etl/ project root so commands behave
the same regardless of the caller's working directory.
"""

from pathlib import Path

# src/relocatifier_etl/paths.py -> src/relocatifier_etl -> src -> etl/
ETL_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ETL_ROOT.parent

RAW_DIR = ETL_ROOT / "data" / "raw"
ARTIFACT_DIR = REPO_ROOT / "app" / "public" / "data"

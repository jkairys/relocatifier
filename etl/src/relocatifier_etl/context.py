"""BuildContext: everything a source module may need, assembled once.

Source modules receive this rather than loading the spatial backbone
themselves, so the SAL shapefile is read exactly once per build.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import geopandas as gpd

from .crosswalk import NameLookup
from .paths import RAW_DIR


@dataclass
class BuildContext:
    suburbs: gpd.GeoDataFrame
    """NSW+QLD SAL polygons (EPSG:4326): columns sal_code, name, state, geometry."""

    population: dict[str, int]
    """Census 2021 total persons per sal_code (0 for zero/unknown population)."""

    raw_dir: Path = RAW_DIR

    @cached_property
    def name_lookup(self) -> NameLookup:
        """The sanctioned name→SAL bridge for code-less sources (see crosswalk.py)."""
        return NameLookup(self.suburbs)

    @cached_property
    def sal_codes(self) -> set[str]:
        return set(self.suburbs["sal_code"])


def make_context() -> BuildContext:
    """Build a real context from the raw downloads — for standalone module
    development and testing without running the full artifact build."""
    from .build import load_suburbs
    from .source_modules import abs_census

    return BuildContext(suburbs=load_suburbs(), population=abs_census.load_population())

"""Auto-discovered metric source modules.

Every module in this package is a self-contained data source that must expose:

    RAW_SOURCES: list[Source]   # files `etl fetch` downloads for it
    METRICS: dict[str, dict]    # metric_id -> {label, format, direction}
    VINTAGES: dict[str, str]    # e.g. {"rta_rents": "2026-Q1"}
    def build(ctx: BuildContext) -> dict[str, dict[str, float | None]]
        # sal_code -> {metric_id: value}; omit suburbs it knows nothing about

Modules are discovered automatically — adding a source means adding a file
here, never editing shared code. Discovery order (alphabetical) has no
semantic meaning; the frontend imposes its own metric ordering.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

_REQUIRED = ("RAW_SOURCES", "METRICS", "VINTAGES", "build")


def iter_source_modules() -> list[ModuleType]:
    modules = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        missing = [attr for attr in _REQUIRED if not hasattr(module, attr)]
        if missing:
            raise RuntimeError(f"source module {info.name} is missing {missing}")
        modules.append(module)
    return modules

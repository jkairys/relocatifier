"""Pure transformation logic, unit-testable without the raw downloads.

All joins are by SAL code, never by name (ADR-0001).
"""

from __future__ import annotations

import re
from statistics import quantiles

# Census DataPack codes look like "SAL10001"; the boundary shapefile carries
# the bare digits "10001". The bare-digits form is canonical.
_DATAPACK_CODE = re.compile(r"^SAL(\d{5})$")
_BARE_CODE = re.compile(r"^\d{5}$")

# Cross-state duplicate suburb names are disambiguated by ABS with a trailing
# parenthetical, e.g. "Richmond (Qld)", "Hillsdale (NSW)", or the longer
# "Karrabin (Ipswich - Qld)" form. Strip it for display.
_STATE_SUFFIX = re.compile(r"\s*\((?:[^()]*\s-\s)?(?:NSW|Qld)\.?\)$")

STATE_NAME_TO_ABBREV = {
    "New South Wales": "NSW",
    "Queensland": "QLD",
}


def normalise_sal_code(code: str) -> str:
    """Normalise a SAL code from either source to the canonical bare form.

    "SAL10001" -> "10001"; "10001" -> "10001". Anything else is an error —
    silently passing malformed keys through a join is how the predecessor
    project corrupted its data.
    """
    code = str(code).strip()
    if m := _DATAPACK_CODE.match(code):
        return m.group(1)
    if _BARE_CODE.match(code):
        return code
    raise ValueError(f"not a SAL code: {code!r}")


def display_name(sal_name: str) -> str:
    """Strip ABS state-disambiguation suffixes like ' (NSW)' / ' (Qld)'."""
    return _STATE_SUFFIX.sub("", sal_name).strip()


def pct_children(age_0_4: float | None, age_5_14: float | None, total_persons: float | None) -> float | None:
    """% of persons aged 0-14, one decimal. None when population is zero/null."""
    if not total_persons or total_persons <= 0:
        return None
    if age_0_4 is None or age_5_14 is None:
        return None
    return round((age_0_4 + age_5_14) / total_persons * 100, 1)


def gross_yield(weekly_rent: float | None, price: float | None) -> float | None:
    """Gross rental yield %, per CONTEXT.md: weekly rent × 52 ÷ price. 1 dp."""
    if weekly_rent is None or price is None or price <= 0:
        return None
    return round(weekly_rent * 52 / price * 100, 1)


def metric_stats(values: list[float]) -> dict[str, float]:
    """median / p10 / p90 across non-null suburb values, rounded to 1 dp."""
    if not values:
        raise ValueError("no values to summarise")
    ordered = sorted(values)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    if n >= 2:
        deciles = quantiles(ordered, n=10, method="inclusive")
        p10, p90 = deciles[0], deciles[-1]
    else:
        p10 = p90 = ordered[0]
    return {"median": round(median, 1), "p10": round(p10, 1), "p90": round(p90, 1)}

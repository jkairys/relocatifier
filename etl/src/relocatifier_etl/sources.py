"""Core raw-source definitions.

The Source dataclass is shared by every source module. Only the SAL
boundaries live here — they are the spatial backbone, not a metric source.
Metric sources declare their own RAW_SOURCES in relocatifier_etl/source_modules/.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    filename: str


# ABS Suburbs and Localities (SAL) 2021 digital boundaries, GDA2020 shapefile.
# Source page: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files
# (ASGS Edition 3, "Suburbs and Localities - 2021 - Shapefile"). Licence: CC BY 4.0.
SAL_BOUNDARIES = Source(
    name="ABS SAL 2021 boundaries (GDA2020 shapefile)",
    url=(
        "https://www.abs.gov.au/statistics/standards/"
        "australian-statistical-geography-standard-asgs/"
        "edition-3-july-2021-june-2026/access-and-downloads/"
        "digital-boundary-files/SAL_2021_AUST_GDA2020_SHP.zip"
    ),
    filename="SAL_2021_AUST_GDA2020_SHP.zip",
)

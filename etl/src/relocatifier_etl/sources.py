"""Raw source registry: every upstream file the ETL depends on.

Each source is a direct, hardcoded URL with provenance noted. All ABS data is
licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
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

# ABS Census 2021 General Community Profile DataPack, all of Australia at SAL
# level, short-header variant.
# Source page: https://www.abs.gov.au/census/find-census-data/datapacks
# (2021 Census GCP > Suburbs and Localities > AUS). Licence: CC BY 4.0.
CENSUS_GCP_SAL = Source(
    name="ABS Census 2021 GCP DataPack (SAL, AUS, short header)",
    url=(
        "https://www.abs.gov.au/census/find-census-data/datapacks/download/"
        "2021_GCP_SAL_for_AUS_short-header.zip"
    ),
    filename="2021_GCP_SAL_for_AUS_short-header.zip",
)

ALL_SOURCES = [SAL_BOUNDARIES, CENSUS_GCP_SAL]

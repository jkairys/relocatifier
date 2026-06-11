"""Crime rate per 1,000 residents, per SAL, for NSW and QLD.

Two upstream sources, each code-less, joined to SAL only by exact suburb name
(ADR-0001) via ``ctx.name_lookup`` — no fuzzy matching, unmatched suburbs are
counted and dropped, never guessed.

NSW — BOCSAR "Recorded Criminal Incidents by month, by Suburb" (SuburbData.zip).
A wide CSV: one row per (suburb, offence category, subcategory), one column per
month back to 1995. We sum *all* offence categories across the most recent 12
month-columns the file carries (currently the 12 months to Dec 2025).

QLD — QPS Online Crime Map API (the S3-hosted React app's backend). There is no
static suburb-level QLD file: the LGA/region/district CSVs on data.qld.gov.au do
not go down to suburb. The OCM API does, and is fetchable with plain httpx (no
browser) once you send an Origin header. It returns a protobuf table; each row
is one criminal incident tagged with a locality code. We pull the suburb lookup
table, then count incident rows per suburb over the most recent 12 complete
months. Responses are cached under ``raw_dir`` so a rebuild does no network.

Method (both states): incidents_per_1000 = incidents_12m / population * 1000,
rounded to 1 dp. Population is Census 2021 persons (``ctx.population``); suburbs
with fewer than 200 residents are nulled, because a tiny denominator turns a
handful of incidents at a highway service centre into an absurd four-figure
"rate". This is a deliberate vintage mismatch — 2021 population against current
incidents — recorded in the metric notes.
"""

from __future__ import annotations

import calendar
import csv
import datetime
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from ..context import BuildContext
from ..paths import RAW_DIR
from ..sources import Source

# --- NSW ---------------------------------------------------------------------

# BOCSAR open data, "Recorded Criminal Incidents by month - by Suburb".
# Source page: https://bocsar.nsw.gov.au/statistics-dashboards/open-datasets/criminal-offences-data.html
# Updated annually; the zip holds a single wide CSV (SuburbData<YY>Q<Q>.csv).
# Licence: CC BY 4.0.
NSW_SUBURB_CRIME = Source(
    name="BOCSAR Recorded Criminal Incidents by month, by Suburb",
    url="https://bocsarblob.blob.core.windows.net/bocsar-open-data/SuburbData.zip",
    filename="SuburbData.zip",
)

RAW_SOURCES = [NSW_SUBURB_CRIME]

# Population floor below which the per-1,000 rate is too noisy to report.
MIN_POPULATION = 200

# How many trailing months define "recent".
WINDOW_MONTHS = 12

_MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}  # "Jan" -> 1


# --- QLD OCM API -------------------------------------------------------------

# The Online Crime Map's backend (its React bundle on qps-ocm.s3...amazonaws.com
# calls this). x-api-key is baked into the public bundle; Authorization is a
# trivial Basic token the bundle derives client-side; Origin is required or the
# API gateway returns 403.
_QLD_API = "https://4w0qhtalkj.execute-api.ap-southeast-2.amazonaws.com"
_QLD_API_KEY = "XoeWxarxOs1PKmZ2UkAnm8LfSjo29sei4P01NEbo"
_QLD_ORIGIN = "https://qps-ocm.s3-ap-southeast-2.amazonaws.com"
_QLD_SUBURB_TYPE = "Suburb"
_QLD_WORKERS = 8

# QLD source page (for provenance; not a file download):
# https://www.police.qld.gov.au/maps-and-statistics  /  https://qps-ocm.s3-ap-southeast-2.amazonaws.com/

METRICS = {
    "crime_rate": {
        "label": "Crime rate (per 1,000)",
        "format": "per_1000",
        "direction": "lower_better",
        "notes": (
            "All recorded criminal incidents over the most recent 12 months, per "
            "1,000 residents. NSW: BOCSAR suburb data. QLD: QPS Online Crime Map "
            "API. Denominator is Census 2021 population (a vintage mismatch against "
            f"current incidents); suburbs under {MIN_POPULATION} residents are null "
            "because tiny denominators produce absurd rates."
        ),
    }
}

# VINTAGES is filled at build time with the actual windows observed (NSW from
# the CSV's last month column, QLD from the detected latest complete month), but
# carries sensible defaults so the module is importable without a build.
VINTAGES = {"crime_nsw": "12m (BOCSAR SuburbData)", "crime_qld": "12m (QPS OCM)"}


# --- pure logic (unit-tested, no network) ------------------------------------

def crime_rate(incidents: int | None, population: int | None) -> float | None:
    """Incidents per 1,000 residents, 1 dp. None when the rate is unreportable.

    Returns None for unknown incidents, and for any suburb whose population is
    null, zero, or below ``MIN_POPULATION`` — small denominators make the rate
    meaningless (3 residents + 40 thefts is not "13,000 per 1,000").
    """
    if incidents is None:
        return None
    if population is None or population < MIN_POPULATION:
        return None
    return round(incidents / population * 1000, 1)


def _parse_month(label: str) -> tuple[int, int] | None:
    """'Jan 1995' -> (1995, 1); non-month columns -> None."""
    parts = label.split()
    if len(parts) != 2:
        return None
    mon = _MONTHS.get(parts[0][:3].title())
    if mon is None or not parts[1].isdigit():
        return None
    return int(parts[1]), mon


def recent_month_columns(header: list[str], n: int = WINDOW_MONTHS) -> list[int]:
    """Indices of the most recent ``n`` month columns in a BOCSAR wide header.

    Month columns are 'Mon YYYY'; the rest (Suburb / Offence category / …) are
    ignored. The trailing ``n`` chronologically-latest months are returned.
    """
    months = [(i, ym) for i, col in enumerate(header) if (ym := _parse_month(col))]
    months.sort(key=lambda t: t[1])  # by (year, month)
    return [i for i, _ in months[-n:]]


def sum_nsw_incidents(
    rows: list[list[str]], month_cols: list[int], suburb_col: int = 0
) -> dict[str, int]:
    """Total incidents per suburb across the chosen month columns.

    All offence categories/subcategories for a suburb are summed — the metric is
    *all* recorded incidents, not any one category. Blank/non-numeric cells count
    as zero.
    """
    totals: dict[str, int] = {}
    for row in rows:
        suburb = row[suburb_col].strip()
        if not suburb:
            continue
        acc = totals.get(suburb, 0)
        for c in month_cols:
            cell = row[c].strip() if c < len(row) else ""
            if cell:
                try:
                    acc += int(float(cell))
                except ValueError:
                    pass
        totals[suburb] = acc
    return totals


def window_to_complete_month(today: datetime.date, n: int = WINDOW_MONTHS) -> tuple[datetime.date, datetime.date]:
    """The ``n`` complete months ending the month before ``today``.

    Today's own month is partial, so it is excluded: for 2026-06-11 with n=12
    this returns (2025-06-01, 2026-05-31).
    """
    end_year, end_month = today.year, today.month
    end_month -= 1
    if end_month == 0:
        end_month = 12
        end_year -= 1
    last_day = calendar.monthrange(end_year, end_month)[1]
    end = datetime.date(end_year, end_month, last_day)
    start_month = end_month - (n - 1)
    start_year = end_year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = datetime.date(start_year, start_month, 1)
    return start, end


# --- NSW build ---------------------------------------------------------------

def _read_nsw(zip_path: Path) -> tuple[dict[str, int], str]:
    """Per-suburb 12-month incident totals from SuburbData.zip; plus the vintage."""
    if not zip_path.exists():
        raise SystemExit(f"missing {zip_path} — run `etl fetch` first")
    with zipfile.ZipFile(zip_path) as zf:
        member = next(m for m in zf.namelist() if m.lower().endswith(".csv"))
        with zf.open(member) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            header = next(reader)
            rows = list(reader)
    cols = recent_month_columns(header, WINDOW_MONTHS)
    if not cols:
        raise SystemExit(f"no month columns found in {member}")
    totals = sum_nsw_incidents(rows, cols)
    last_label = header[cols[-1]]
    year, month = _parse_month(last_label)
    vintage = f"12m to {year}-{month:02d}"
    return totals, vintage


# --- QLD build ---------------------------------------------------------------

def _qld_headers() -> dict[str, str]:
    import base64
    import time

    token = base64.b64encode(str(int(time.time() * 1000))[::-1].encode()).decode()
    return {
        "x-api-key": _QLD_API_KEY,
        "Authorization": "Basic " + token,
        "Origin": _QLD_ORIGIN,
    }


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
    return value, i


def _field_blobs(buf: bytes) -> "list[tuple[int, bytes]]":
    """Yield (field_number, payload) for length-delimited fields; skip the rest.

    A tolerant protobuf scanner — enough to walk the OCM "table" messages, whose
    binary geometry/styling fields we never need to decode, only step over.
    """
    out: list[tuple[int, bytes]] = []
    i = 0
    n = len(buf)
    while i < n:
        tag, i = _read_varint(buf, i)
        field, wt = tag >> 3, tag & 7
        if wt == 0:
            _, i = _read_varint(buf, i)
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            out.append((field, buf[i : i + ln]))
            i += ln
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        else:  # group / unknown — stop, the rest is unreadable
            break
    return out


def _ocm_table_field4(buf: bytes) -> bytes:
    """The OCM table payload (field 4) holding the repeated row messages."""
    for field, payload in _field_blobs(buf):
        if field == 4:
            return payload
    return b""


def parse_qld_suburbs(lut: bytes) -> dict[str, int]:
    """Parse the OCM lookup table into {suburb_name: objectid}.

    Each row's cells (field 13) are [objectid:int, label:str, type:str]; we keep
    rows whose type is 'Suburb'. Names carry BOCSAR-style disambiguation
    ('Alligator Creek - Townsville') we leave intact for exact SAL matching.
    """
    suburbs: dict[str, int] = {}
    for field, row in _field_blobs(_ocm_table_field4(lut)):
        if field != 1:
            continue
        cells: list = []
        for cf, cell in _field_blobs(row):
            if cf != 13:
                continue
            # a cell is a sub-message with either a varint (field 3) or a string
            i = 0
            val = None
            while i < len(cell):
                tag, i = _read_varint(cell, i)
                f, wt = tag >> 3, tag & 7
                if wt == 0:
                    val, i = _read_varint(cell, i)
                elif wt == 2:
                    ln, i = _read_varint(cell, i)
                    val = cell[i : i + ln].decode("utf-8", "replace")
                    i += ln
                else:
                    break
            cells.append(val)
        if len(cells) >= 3 and cells[2] == _QLD_SUBURB_TYPE and isinstance(cells[0], int):
            suburbs[str(cells[1])] = cells[0]
    return suburbs


def count_qld_incidents(offences: bytes) -> int:
    """Number of incident rows in an OCM /offences response (one row = one incident)."""
    return sum(1 for field, _ in _field_blobs(_ocm_table_field4(offences)) if field == 1)


def _qld_fetch_counts(
    raw_dir: Path, today: datetime.date
) -> tuple[dict[str, int], str]:
    """{suburb_name: incidents_12m} for QLD, plus the vintage string.

    Caches the aggregated per-suburb counts to ``raw_dir`` keyed by the window so
    repeat builds (and standalone verification) do no network.
    """
    start, end = window_to_complete_month(today, WINDOW_MONTHS)
    vintage = f"12m to {end.year}-{end.month:02d}"
    cache = raw_dir / f"crime_qld_{start:%Y%m}_{end:%Y%m}.json"
    if cache.exists():
        return json.loads(cache.read_text()), vintage

    frm = f"{start.month:02d}-{start.day:02d}-{start.year}"
    to = f"{end.month:02d}-{end.day:02d}-{end.year}"

    with httpx.Client(timeout=httpx.Timeout(120, connect=30), headers=_qld_headers()) as client:
        # httpx transparently decodes the Content-Encoding: gzip the API uses,
        # so .content is already the protobuf table.
        lut_resp = client.get(f"{_QLD_API}/dev/lut")
        lut_resp.raise_for_status()
        suburbs = parse_qld_suburbs(lut_resp.content)

        def fetch(item: tuple[str, int]) -> tuple[str, int]:
            name, oid = item
            url = f"{_QLD_API}/dev/offences/{frm}/{to}/{oid}"
            resp = client.get(url)
            resp.raise_for_status()
            return name, count_qld_incidents(resp.content)

        counts: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=_QLD_WORKERS) as pool:
            for name, n in pool.map(fetch, suburbs.items()):
                counts[name] = n

    cache.write_text(json.dumps(counts))
    return counts, vintage


# --- entry point -------------------------------------------------------------

def build(ctx: BuildContext) -> dict[str, dict[str, float | None]]:
    today = datetime.date.today()

    nsw_totals, nsw_vintage = _read_nsw(ctx.raw_dir / NSW_SUBURB_CRIME.filename)
    qld_totals, qld_vintage = _qld_fetch_counts(ctx.raw_dir, today)
    VINTAGES["crime_nsw"] = nsw_vintage
    VINTAGES["crime_qld"] = qld_vintage

    result: dict[str, dict[str, float | None]] = {}
    stats = {
        "NSW": {"matched": 0, "unmatched": 0, "floored": 0},
        "QLD": {"matched": 0, "unmatched": 0, "floored": 0},
    }

    for state, totals in (("NSW", nsw_totals), ("QLD", qld_totals)):
        for name, incidents in totals.items():
            sal = ctx.name_lookup.sal_code(name, state)
            if sal is None or sal not in ctx.sal_codes:
                stats[state]["unmatched"] += 1
                continue
            stats[state]["matched"] += 1
            rate = crime_rate(incidents, ctx.population.get(sal))
            if rate is None:
                stats[state]["floored"] += 1
            # last writer wins is irrelevant: NSW and QLD suburbs are disjoint SALs
            result[sal] = {"crime_rate": rate}

    for state, s in stats.items():
        print(
            f"[crime] {state}: {s['matched']} matched, {s['unmatched']} unmatched, "
            f"{s['floored']} nulled (population < {MIN_POPULATION})"
        )
    return result

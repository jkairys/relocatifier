"""Median house price per suburb: NSW computed from sales, QLD scraped medians.

Two sub-sources feed the one metric:

NSW — Valuer General Bulk Property Sales Information (PSI).
    Free bulk download of every NSW property sale, published weekly at
    https://valuergeneral.nsw.gov.au (Creative Commons). Files are the
    community-documented "2001 format": semicolon-delimited .DAT files where
    B records carry address, locality, postcode, area, contract date,
    purchase price, zoning, nature-of-property, primary purpose and a strata
    lot number. We take the most recent yearly archive (52 nested weekly
    zips) plus the current year's weekly files, filter to house sales
    (no strata lot, no unit number, residence nature/purpose, sane price),
    and compute a trailing-12-month median per locality. Locality+NSW maps
    to SAL via ctx.name_lookup — exact match only (ADR-0001), unmatched
    counts are printed, never hidden.

QLD — no free sales feed exists, so this is best-effort: suburb-profile
    medians scraped from onthehouse.com.au (CoreLogic-backed). Profile pages
    are plain server-rendered HTML with a `window.REDUX_DATA` JSON blob
    containing a "Median Sale Price (12 months)" series for Houses; the
    suburb_profiles sitemap provides canonical slugs. Scraping is a separate
    explicit step (`scrape_qld`) that caches one small extracted-JSON file
    per suburb under data/raw/qld_prices/; build() only ever reads that
    cache, so suburbs never scraped simply have no value.

The two sub-sources never overlap (different states), so merging is trivial.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from statistics import median

from ..context import BuildContext
from ..crosswalk import normalise_name
from ..paths import RAW_DIR
from ..sources import Source

# --------------------------------------------------------------------------
# Raw sources
# --------------------------------------------------------------------------

_PSI_BASE = "https://www.valuergeneral.nsw.gov.au/__psi"

# Most recent complete year of NSW sales: a zip of 52 weekly zips of .DAT
# files. Licence: Creative Commons (creative_commons.txt ships in each zip).
NSW_PSI_YEARLY = Source(
    name="NSW VG bulk property sales 2025 (yearly archive)",
    url=f"{_PSI_BASE}/yearly/2025.zip",
    filename="nsw_vg_psi_yearly_2025.zip",
)

# Current-year sales arrive as one zip per Monday. Files appear within a few
# days of the date in the name (verified: every Monday of 2026 so far exists,
# including public holidays), so we enumerate Mondays at least 5 days old.
_WEEKLY_START = dt.date(2026, 1, 5)  # first Monday of 2026


def _weekly_mondays(today: dt.date | None = None) -> list[dt.date]:
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=5)
    mondays = []
    day = _WEEKLY_START
    while day <= cutoff:
        mondays.append(day)
        day += dt.timedelta(days=7)
    return mondays


def _weekly_source(monday: dt.date) -> Source:
    return Source(
        name=f"NSW VG bulk property sales week of {monday:%Y-%m-%d}",
        url=f"{_PSI_BASE}/weekly/{monday:%Y%m%d}.zip",
        filename=f"nsw_vg_psi_weekly_{monday:%Y%m%d}.zip",
    )


NSW_PSI_WEEKLIES = [_weekly_source(d) for d in _weekly_mondays()]

# OnTheHouse suburb-profiles sitemap: canonical profile URLs (slug includes
# the postcode we have no other source for). Profile pages themselves are
# fetched by scrape_qld(), not by `etl fetch`.
OTH_SITEMAP = Source(
    name="onthehouse.com.au suburb-profiles sitemap",
    url="https://www.onthehouse.com.au/sitemap/suburb_profiles.xml",
    filename="onthehouse_suburb_profiles.xml",
)

RAW_SOURCES = [NSW_PSI_YEARLY, *NSW_PSI_WEEKLIES, OTH_SITEMAP]

METRICS = {
    "median_house_price": {
        "label": "Median house price",
        "format": "aud",
        "direction": "lower_better",
        "notes": (
            "NSW: 12-month rolling median of house sales computed from NSW "
            "Valuer General bulk PSI (strata/units excluded, min "
            "5 sales). QLD: 12-month median sale price for houses scraped "
            "from onthehouse.com.au suburb profiles; only suburbs present "
            "in the scrape cache have values."
        ),
    },
}

_WINDOW_END = _weekly_mondays()[-1] if _weekly_mondays() else dt.date(2025, 12, 31)

VINTAGES = {
    "nsw_sales": f"12m to {_WINDOW_END:%Y-%m}",
    "qld_prices": "12m medians from onthehouse.com.au suburb profiles (scraped 2026-06)",
}

# --------------------------------------------------------------------------
# NSW: PSI .DAT parsing and house-sale filtering (pure, unit-tested)
# --------------------------------------------------------------------------

# B-record field positions in the post-2001 PSI format (0-based after
# splitting on ';'). Community-documented; verified against live files.
_B_MIN_FIELDS = 20

PRICE_MIN = 50_000
PRICE_MAX = 50_000_000
MIN_SALES = 5  # localities with fewer sales in the window get no median

# Zonings that count as residential when the primary-purpose field is blank.
# R1-R5 standard-instrument residential, RU5 village, E4/C4 environmental/
# rural living, plus legacy single-letter residential "A".
RESIDENTIAL_ZONES = {"R1", "R2", "R3", "R4", "R5", "RU5", "E4", "C4", "A"}


@dataclass(frozen=True)
class SaleRecord:
    property_id: str
    sale_counter: str
    download_dt: str  # "CCYYMMDD HH:MM" — lexicographic order is time order
    unit_number: str
    locality: str
    postcode: str
    contract_date: dt.date | None
    price: int | None
    zoning: str
    nature_of_property: str  # V=vacant land, R=residence, 3=other
    primary_purpose: str
    strata_lot: str


def _parse_compact_date(raw: str) -> dt.date | None:
    raw = raw.strip()
    if not re.fullmatch(r"\d{8}", raw):
        return None
    try:
        return dt.date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _parse_price(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def parse_psi_dat(text: str) -> list[SaleRecord]:
    """Extract sale records from the B records of a PSI .DAT file."""
    records = []
    for line in text.splitlines():
        if not line.startswith("B;"):
            continue
        f = line.split(";")
        if len(f) < _B_MIN_FIELDS:
            continue
        records.append(
            SaleRecord(
                property_id=f[2].strip(),
                sale_counter=f[3].strip(),
                download_dt=f[4].strip(),
                unit_number=f[6].strip(),
                locality=f[9].strip(),
                postcode=f[10].strip(),
                contract_date=_parse_compact_date(f[13]),
                price=_parse_price(f[15]),
                zoning=f[16].strip().upper(),
                nature_of_property=f[17].strip().upper(),
                primary_purpose=f[18].strip().upper(),
                strata_lot=f[19].strip(),
            )
        )
    return records


def is_house_sale(rec: SaleRecord) -> bool:
    """House (non-strata residential dwelling) sale at a sane price."""
    if rec.strata_lot or rec.unit_number:
        return False  # strata lot or unit number -> unit/townhouse, not house
    if rec.nature_of_property != "R":
        return False  # V = vacant land, 3 = other
    if rec.primary_purpose:
        if not rec.primary_purpose.startswith("RESID"):
            return False
    elif rec.zoning not in RESIDENTIAL_ZONES:
        return False  # no purpose recorded and not residential-zoned
    if rec.price is None or not PRICE_MIN <= rec.price <= PRICE_MAX:
        return False
    return bool(rec.locality) and rec.contract_date is not None


def median_price_by_locality(
    records: list[SaleRecord],
    window_start: dt.date,
    window_end: dt.date,
    min_sales: int = MIN_SALES,
) -> dict[str, tuple[int, int]]:
    """Trailing-window median house price per normalised locality name.

    Returns {normalised_locality: (median_price, n_sales)}. Records are
    deduplicated on (property_id, sale_counter, contract_date) keeping the
    most recently downloaded version, because the same sale is re-reported
    across weekly files and the yearly archive overlaps the weeklies.
    """
    latest: dict[tuple[str, str, dt.date], SaleRecord] = {}
    for rec in records:
        if not is_house_sale(rec):
            continue
        if not window_start <= rec.contract_date <= window_end:
            continue
        key = (rec.property_id, rec.sale_counter, rec.contract_date)
        kept = latest.get(key)
        if kept is None or rec.download_dt > kept.download_dt:
            latest[key] = rec

    by_locality: dict[str, list[int]] = {}
    for rec in latest.values():
        by_locality.setdefault(normalise_name(rec.locality), []).append(rec.price)

    return {
        loc: (int(round(median(prices))), len(prices))
        for loc, prices in by_locality.items()
        if len(prices) >= min_sales
    }


def _iter_dat_texts(zip_path: Path):
    """Yield the text of every .DAT inside a PSI zip, descending into the
    nested weekly zips that yearly archives are made of."""
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            lower = member.lower()
            if lower.endswith(".dat"):
                yield zf.read(member).decode("latin-1")
            elif lower.endswith(".zip"):
                with zipfile.ZipFile(BytesIO(zf.read(member))) as inner:
                    for name in inner.namelist():
                        if name.lower().endswith(".dat"):
                            yield inner.read(name).decode("latin-1")


def _load_nsw_records(raw_dir: Path) -> list[SaleRecord]:
    yearly = raw_dir / NSW_PSI_YEARLY.filename
    if not yearly.exists():
        raise SystemExit(f"missing {yearly} — run `etl fetch` first")
    weeklies = sorted(raw_dir.glob("nsw_vg_psi_weekly_*.zip"))
    expected = len(NSW_PSI_WEEKLIES)
    if len(weeklies) < expected:
        print(
            f"[house_prices] NOTE: {len(weeklies)}/{expected} weekly PSI files "
            "cached — run `etl fetch` for the full window"
        )
    records: list[SaleRecord] = []
    for zip_path in [yearly, *weeklies]:
        for text in _iter_dat_texts(zip_path):
            records.extend(parse_psi_dat(text))
    return records


# --------------------------------------------------------------------------
# QLD: onthehouse.com.au suburb-profile parsing (pure, unit-tested)
# --------------------------------------------------------------------------

QLD_CACHE_DIR = RAW_DIR / "qld_prices"

_OTH_BASE = "https://www.onthehouse.com.au"
_REDUX_RE = re.compile(r"window\.REDUX_DATA\s*=\s*")
_SITEMAP_QLD_RE = re.compile(
    r"<loc>https://www\.onthehouse\.com\.au/property/qld/([a-z0-9-]+-\d{4})</loc>"
)

# A "Median Sale Price (12 months)" series whose latest point is older than
# this is stale (suburb with no recent sales) and yields no value.
STALE_AFTER_MONTHS = 15

USER_AGENT = (
    "relocatifier-etl/0.1 (personal relocation research, low volume; "
    "contact: jethro.kairys@gmail.com)"
)


def parse_oth_sitemap_qld(xml_text: str) -> dict[str, list[str]]:
    """QLD suburb-profile slugs keyed by normalised suburb name.

    A name can map to several slugs (same suburb name, different postcodes);
    the ambiguity is resolved later by which cached page actually carries
    house data.
    """
    by_name: dict[str, list[str]] = {}
    for slug in _SITEMAP_QLD_RE.findall(xml_text):
        name = normalise_name(slug.rsplit("-", 1)[0])
        by_name.setdefault(name, []).append(slug)
    return by_name


def parse_oth_page(html: str) -> dict | None:
    """Extract the House market-trend metrics from a suburb-profile page.

    Returns {"locality_name", "postcode", "house_metrics": [...]} where
    house_metrics is the raw list of metric objects for Houses, or None when
    the page carries no REDUX_DATA (not a profile page).
    """
    m = _REDUX_RE.search(html)
    if not m:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
    except json.JSONDecodeError:
        return None
    metrics = ((data.get("marketTrends") or {}).get("metrics") or {})
    house_groups = metrics.get("House") or {}
    # The series sit under a year-span key ("10"); take whichever is present.
    house_metrics: list = []
    for group in house_groups.values():
        if isinstance(group, list):
            house_metrics = group
            break
    locality = postcode = None
    for entry in house_metrics:
        locality = entry.get("localityName") or locality
        postcode = entry.get("postcodeName") or postcode
    return {"locality_name": locality, "postcode": postcode, "house_metrics": house_metrics}


def latest_house_median(house_metrics: list, today: dt.date | None = None) -> float | None:
    """Latest 'Median Sale Price (12 months)' point, unless stale."""
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=STALE_AFTER_MONTHS * 30)
    for entry in house_metrics:
        if entry.get("metricType") != "Median Sale Price (12 months)":
            continue
        if entry.get("locationType") not in (None, "Locality"):
            continue
        points = entry.get("seriesDataList") or []
        dated = []
        for p in points:
            when = _parse_iso_date(p.get("dateTime"))
            if when is not None and p.get("value") is not None:
                dated.append((when, float(p["value"])))
        if not dated:
            return None
        when, value = max(dated)
        return value if when >= cutoff else None
    return None


def _parse_iso_date(raw) -> dt.date | None:
    if not isinstance(raw, str):
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


# --------------------------------------------------------------------------
# QLD: explicit scrape step (network — run deliberately, never from build)
# --------------------------------------------------------------------------


def _cache_path(slug: str) -> Path:
    return QLD_CACHE_DIR / f"{slug}.json"


def _fetch_one(client, slug: str) -> dict:
    """Fetch one suburb profile and cache the extracted JSON (or the error)."""
    url = f"{_OTH_BASE}/property/qld/{slug}"
    started = time.monotonic()
    entry: dict = {"slug": slug, "url": url, "fetched_at": dt.datetime.now().isoformat()}
    try:
        resp = client.get(url)
        entry["http_status"] = resp.status_code
        entry["page_bytes"] = len(resp.content)
        if resp.status_code == 200:
            parsed = parse_oth_page(resp.text)
            if parsed is None:
                entry["error"] = "no REDUX_DATA in page"
            else:
                entry.update(parsed)
        else:
            entry["error"] = f"HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001 — record and move on, it's a scrape
        entry["error"] = f"{type(exc).__name__}: {exc}"
    entry["fetch_seconds"] = round(time.monotonic() - started, 2)
    QLD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(slug).write_text(json.dumps(entry))
    return entry


def scrape_qld(slugs: list[str], concurrency: int = 4) -> list[dict]:
    """Politely fetch + cache the given suburb-profile slugs (skips cached).

    Network step, run explicitly:
        from relocatifier_etl.source_modules import house_prices
        house_prices.scrape_qld([...])
    """
    import httpx  # local import: build() must work without network deps in play

    todo = [s for s in slugs if not _cache_path(s).exists()]
    print(f"[house_prices] scrape_qld: {len(slugs)} requested, {len(todo)} not cached")
    if not todo:
        return []
    results = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30, connect=15),
        follow_redirects=True,
    ) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for entry in pool.map(lambda s: _fetch_one(client, s), todo):
                status = entry.get("http_status", "ERR")
                note = entry.get("error", "ok")
                print(
                    f"[house_prices]   {entry['slug']}: {status} "
                    f"{entry.get('fetch_seconds')}s ({note})"
                )
                results.append(entry)
    return results


def qld_slugs_for(ctx: BuildContext, names: list[str] | None = None) -> list[str]:
    """Map QLD SAL suburb names to all candidate OnTheHouse slugs.

    Uses the downloaded sitemap (run `etl fetch` first). With names=None,
    covers every QLD suburb in the context.
    """
    sitemap_path = RAW_DIR / OTH_SITEMAP.filename
    if not sitemap_path.exists():
        raise SystemExit(f"missing {sitemap_path} — run `etl fetch` first")
    by_name = parse_oth_sitemap_qld(sitemap_path.read_text())
    if names is None:
        qld = ctx.suburbs[ctx.suburbs["state"] == "QLD"]
        names = list(qld["name"])
    slugs: list[str] = []
    for name in names:
        slugs.extend(by_name.get(normalise_name(name), []))
    return slugs


# --------------------------------------------------------------------------
# build(): cache/raw-files in, sal_code -> value out. No network.
# --------------------------------------------------------------------------


def _build_nsw(ctx: BuildContext) -> dict[str, float]:
    records = _load_nsw_records(ctx.raw_dir)
    window_end = dt.date.today()
    window_start = window_end - dt.timedelta(days=365)
    medians = median_price_by_locality(records, window_start, window_end)

    values: dict[str, float] = {}
    unmatched = []
    for locality, (price, _n) in medians.items():
        sal = ctx.name_lookup.sal_code(locality, "NSW")
        if sal is None:
            unmatched.append(locality)
        else:
            values[sal] = float(price)
    print(
        f"[house_prices] NSW: {len(records)} B records -> {len(medians)} localities "
        f"with >={MIN_SALES} house sales in {window_start}..{window_end}; "
        f"{len(values)} matched to SAL, {len(unmatched)} unmatched"
    )
    if unmatched:
        sample = ", ".join(sorted(unmatched)[:10])
        print(f"[house_prices] NSW unmatched localities (sample): {sample}")
    return values


def _build_qld(ctx: BuildContext) -> dict[str, float]:
    """Whatever the scrape cache holds, resolved to SALs.

    Same-name slugs (e.g. buderim-4556 vs buderim-4519) are resolved by
    which cached page actually has a usable house median; if several do,
    the name is ambiguous and skipped — never guessed (ADR-0001 spirit).
    """
    if not QLD_CACHE_DIR.is_dir():
        print("[house_prices] QLD: no scrape cache — skipping (NSW only)")
        return {}

    by_name: dict[str, list[float]] = {}
    cached = errored = 0
    for path in sorted(QLD_CACHE_DIR.glob("*.json")):
        entry = json.loads(path.read_text())
        cached += 1
        if entry.get("error") or not entry.get("locality_name"):
            errored += 1
            continue
        value = latest_house_median(entry.get("house_metrics") or [])
        if value is None:
            continue
        by_name.setdefault(normalise_name(entry["locality_name"]), []).append(value)

    values: dict[str, float] = {}
    unmatched = ambiguous = 0
    for name, candidates in by_name.items():
        if len(candidates) > 1:
            ambiguous += 1
            continue
        sal = ctx.name_lookup.sal_code(name, "QLD")
        if sal is None:
            unmatched += 1
        else:
            values[sal] = float(candidates[0])
    print(
        f"[house_prices] QLD: {cached} cached pages ({errored} unusable) -> "
        f"{len(by_name)} suburbs with a recent house median; {len(values)} matched "
        f"to SAL, {unmatched} unmatched, {ambiguous} ambiguous same-name skipped"
    )
    return values


def build(ctx: BuildContext) -> dict[str, dict[str, float | None]]:
    prices: dict[str, float] = {}
    prices.update(_build_nsw(ctx))
    prices.update(_build_qld(ctx))  # states disjoint; update is safe
    return {
        sal: {"median_house_price": value}
        for sal, value in prices.items()
        if sal in ctx.sal_codes
    }

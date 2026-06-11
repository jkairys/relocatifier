"""Download raw sources into data/raw/ with skip-if-present caching."""

import sys
from pathlib import Path

import httpx

from .paths import RAW_DIR
from .sources import ALL_SOURCES, Source

_CHUNK = 1 << 20  # 1 MiB
_PROGRESS_EVERY = 10 * _CHUNK


def download(source: Source, dest_dir: Path = RAW_DIR) -> Path:
    """Stream a source to dest_dir; skip if the file already exists."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.filename
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[cached] {source.filename} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest

    print(f"[fetch]  {source.name}")
    print(f"         {source.url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(1800, connect=60)) as client:
        with client.stream("GET", source.url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0)) or None
            done = 0
            next_report = _PROGRESS_EVERY
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes(_CHUNK):
                    fh.write(chunk)
                    done += len(chunk)
                    if done >= next_report:
                        pct = f" ({done / total * 100:.0f}%)" if total else ""
                        print(f"         {done / 1e6:.0f} MB{pct}", flush=True)
                        next_report += _PROGRESS_EVERY
    tmp.rename(dest)
    print(f"[done]   {source.filename} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def fetch_all() -> None:
    for source in ALL_SOURCES:
        try:
            download(source)
        except httpx.HTTPError as exc:
            print(f"[error]  {source.filename}: {exc}", file=sys.stderr)
            raise SystemExit(1)

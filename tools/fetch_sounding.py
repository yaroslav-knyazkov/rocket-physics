"""Hand-run helper: fetch one radiosonde sounding from the University of
Wyoming archive and write it in the canonical CSV format `sim/soundings.py`
reads (architecture.md SS17; roadmap.md Step 26).

    python tools/fetch_sounding.py --station 72672 \\
        --datetime "2024-01-15 12:00:00" --case example_live --step-m 250

**Never imported by `sim/`.** This is the *only* part of the project that
touches the network (architecture.md SS17/SS21/SS22 item 4 -- a live API
call inside `run_sim` or the RHS is rejected outright; the simulator stays
offline and deterministic). Run by hand, occasionally, one request at a
time.

Endpoint: `https://weather.arcc.uwyo.edu/wsgi/sounding` (the archive's
current domain -- the older `weather.uwyo.edu` host has moved). Query
parameters: `datetime` (one of the synoptic hours 00/03/06/09/12/15/18/21Z,
though not every station reports at every hour), `id` (5-digit WMO station
number), `src=UNKNOWN`, `type=TEXT:CSV`.

**robots.txt disclosure:** `weather.arcc.uwyo.edu/robots.txt` disallows
`/wsgi`. This script uses that path anyway, with the user's explicit,
informed approval (architecture.md SS22 item 4; roadmap.md Step 26 is an
approval gate) -- on the basis that a single hand-run request, run
occasionally by one person, is not the kind of bulk/automated crawling
robots.txt is aimed at preventing. This is documented here and in every
file this script writes (the `# source:` metadata line), not buried.

Response shape: a raw query returns roughly one CSV row per second of
balloon ascent -- several thousand rows, far finer-grained than this
project's canonical format wants ("a few kB each", architecture.md SS17).
This script resamples down to one row per `--step-m` metres of altitude
(default 250 m), picking the nearest raw sample to each grid level.

When the archive has no data for the requested station/time, it responds
with HTTP 404 and a plain-text body such as
`"Unable to retrieve the data for 72469 at 2024-01-15 12:00:00."` --
detected in `parse_response()` (the body doesn't start with the CSV header
row) and raised as `SoundingFetchError`, a clear, actionable error instead
of a raw urllib traceback or a bogus output file.

Network I/O (`fetch_raw`) and pure logic (`parse_response`,
`resample_rows`, `format_canonical`) are kept in separate functions so the
parsing/resampling/formatting path can be unit-tested offline, without
hitting the network (tests/test_fetch_sounding.py).
"""

import argparse
import csv
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import NamedTuple

import numpy as np

_BASE_URL = "https://weather.arcc.uwyo.edu/wsgi/sounding"
_USER_AGENT = "rocket-trajectory-sim/tools/fetch_sounding.py (hand-run, single request)"

# Raw response header row, used to distinguish real CSV data from the
# archive's plain-text "no data" message (same status either way is a 404,
# see fetch_raw()'s docstring -- the *body* is what tells them apart).
_CSV_HEADER_PREFIX = "time,"


class SoundingFetchError(Exception):
    """The archive had no data for the requested station/time, or returned
    a response that isn't parseable sounding CSV."""


class RawRow(NamedTuple):
    """One row of the archive's ~1s-resolution response, already unit
    converted to the canonical format's units."""

    h_m: float       # geopotential height -> h_msl_m, meters
    p_Pa: float       # pressure_hPa * 100
    T_K: float        # temperature_C + 273.15
    wdir_deg: float   # wind direction_degree, no conversion
    wspd_ms: float    # wind speed_m/s, no conversion
    lat_deg: float
    lon_deg: float


# ----------------------------------------------------------------------
# Network I/O -- the only part of this script (and of the whole project)
# that touches the network.
# ----------------------------------------------------------------------


def build_url(station: str, dt_str: str) -> str:
    """Build the archive query URL for `station` (WMO number) at `dt_str`
    (`"YYYY-MM-DD HH:00:00"`, UTC)."""
    params = {
        "datetime": dt_str,
        "id": station,
        "src": "UNKNOWN",
        "type": "TEXT:CSV",
    }
    return _BASE_URL + "?" + urllib.parse.urlencode(params)


def fetch_raw(station: str, dt_str: str, timeout: float = 60.0) -> str:
    """GET the archive endpoint and return the raw response text.

    On success this is the CSV body. When the archive has no data for the
    request it responds with **HTTP 404** and a plain-text error message
    as the body -- that's still returned here as plain text (not raised),
    so `parse_response()` is the single place that decides "no data" vs.
    "real CSV" and raises `SoundingFetchError` with a clear message. Any
    other transport failure (DNS, timeout, non-404 HTTP error) is left to
    propagate as the underlying `urllib` exception -- a real network
    problem, not a "no data" domain error.
    """
    url = build_url(station, dt_str)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return e.read().decode("utf-8", errors="replace")
        raise


# ----------------------------------------------------------------------
# Pure logic -- parsing, resampling, formatting. No network access here,
# fully unit-testable against a captured response string.
# ----------------------------------------------------------------------


def parse_response(text: str) -> "list[RawRow]":
    """Parse the archive's raw response text into a list of `RawRow`,
    sorted by ascending altitude, with unit conversions applied
    (hPa -> Pa, degC -> K).

    Raises `SoundingFetchError` if `text` isn't a CSV response with the
    expected header (the archive's "no data" case is a plain-text
    sentence, not CSV -- see the module docstring).

    Rows with a non-numeric essential field (height, pressure,
    temperature, wind) are skipped rather than crashing -- the archive
    leaves humidity-only columns blank near the ceiling of some
    soundings, but that never happens to the columns this script uses.
    Rows are also required to have strictly increasing height versus the
    previous *kept* row; a balloon can jitter within a second of ascent,
    and that guarantees `resample_rows()` always starts from a strictly
    ascending source array.
    """
    lines = text.strip("\n").split("\n")
    if not lines or not lines[0].strip().startswith(_CSV_HEADER_PREFIX):
        raise SoundingFetchError(
            "Sounding archive returned no usable data "
            f"(response was: {text.strip()!r})"
        )

    reader = csv.DictReader(lines)
    rows: "list[RawRow]" = []
    last_h = None
    for rec in reader:
        try:
            h = float(rec["geopotential height_m"])
            p_Pa = float(rec["pressure_hPa"]) * 100.0
            T_K = float(rec["temperature_C"]) + 273.15
            wdir = float(rec["wind direction_degree"])
            wspd = float(rec["wind speed_m/s"])
            lat = float(rec["latitude"])
            lon = float(rec["longitude"])
        except (KeyError, ValueError, TypeError):
            continue
        if last_h is not None and h <= last_h:
            continue
        rows.append(RawRow(h, p_Pa, T_K, wdir, wspd, lat, lon))
        last_h = h

    if not rows:
        raise SoundingFetchError(
            "Sounding archive response had a CSV header but no usable data rows"
        )
    return rows


def resample_rows(rows: "list[RawRow]", step_m: float) -> "list[RawRow]":
    """Decimate ~1s-resolution `rows` (sorted, strictly ascending `h_m`)
    down to roughly one row per `step_m` metres of altitude.

    Method: the lowest raw row is always kept (it doubles as the launch
    point used for the output's metadata); above it, one row is picked
    per altitude grid level (`step_m` apart), the pick being the raw row
    nearest that level ("nearest raw sample" -- simplest, and plenty for
    a physics sim per the roadmap's own call).

    When `step_m` is finer than the source's own vertical resolution
    (~a few metres per row, ascent-rate dependent), adjacent grid levels
    can pick the *same* raw row -- those consecutive duplicate picks are
    collapsed so the output's `h_msl_m` stays strictly increasing, which
    `sim.soundings.load_case` requires.
    """
    if not rows:
        return []

    h = np.array([r.h_m for r in rows])
    h_min, h_max = float(h[0]), float(h[-1])

    picked: "list[RawRow]" = [rows[0]]
    last_h = h_min

    if h_max > h_min:
        first_level = math.ceil(h_min / step_m) * step_m
        if first_level <= h_min:
            first_level += step_m
        levels = np.arange(first_level, h_max + step_m / 2.0, step_m)

        for level in levels:
            idx = int(np.searchsorted(h, level))
            candidates = [i for i in (idx - 1, idx) if 0 <= i < len(rows)]
            best = min(candidates, key=lambda i: abs(h[i] - level))
            if rows[best].h_m > last_h:
                picked.append(rows[best])
                last_h = rows[best].h_m

    return picked


def format_canonical(
    station: str, time_utc: str, rows: "list[RawRow]", source: str
) -> str:
    """Render `rows` as the canonical sounding CSV text (architecture.md
    SS17 / `sim/soundings.py`'s module docstring): `#`-prefixed metadata
    lines, then a `h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms` header and body.

    `lat_deg`/`lon_deg`/`elevation_m` come from `rows[0]` -- the lowest
    kept altitude, the closest thing to "launch point" a drifting balloon
    offers (architecture.md SS17).
    """
    if not rows:
        raise ValueError("format_canonical: no rows to write")

    first = rows[0]
    lines = [
        f"# station: {station}",
        f"# lat_deg: {first.lat_deg}",
        f"# lon_deg: {first.lon_deg}",
        f"# elevation_m: {first.h_m}",
        f"# time_utc: {time_utc}",
        f"# source: {source}",
        "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
    ]
    for r in rows:
        lines.append(
            f"{r.h_m:.1f},{r.p_Pa:.1f},{r.T_K:.2f},{r.wdir_deg:.1f},{r.wspd_ms:.1f}"
        )
    return "\n".join(lines) + "\n"


def build_source_note(url: str, step_m: float) -> str:
    """The `# source:` metadata line: the exact endpoint used, an explicit
    robots.txt disclosure (see module docstring), and the resampling
    applied -- so anyone reading the file later knows exactly where the
    numbers came from and that they're decimated, not raw."""
    return (
        "University of Wyoming radiosonde archive, "
        f"GET {url} -- weather.arcc.uwyo.edu/robots.txt disallows /wsgi; "
        "used anyway with explicit user approval for this hand-run, "
        "single-request tool (architecture.md SS17/SS22 item 4, "
        "roadmap.md Step 26), not the bulk/automated crawling robots.txt "
        f"targets. Raw ~1s-resolution response resampled to {step_m:g} m "
        "altitude steps (nearest raw sample per level)."
    )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def output_path(repo_root: str, case: str, station: str, dt: datetime) -> str:
    fname = f"{station}_{dt.strftime('%Y%m%d%H%M')}.csv"
    return os.path.join(repo_root, "data", "soundings", case, fname)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch one radiosonde sounding from the University of Wyoming "
            "archive and write it in the canonical CSV format sim/soundings.py "
            "reads. Hand-run only -- never called from sim/."
        )
    )
    parser.add_argument(
        "--station", required=True,
        help="5-digit WMO station number, e.g. 72672",
    )
    parser.add_argument(
        "--datetime", required=True, dest="datetime_str",
        help=(
            "Synoptic time, UTC, as 'YYYY-MM-DD HH:00:00' "
            "(hour one of 00/03/06/09/12/15/18/21Z, station-dependent)"
        ),
    )
    parser.add_argument(
        "--case", required=True,
        help="Case folder name written under data/soundings/<case>/",
    )
    parser.add_argument(
        "--step-m", type=float, default=250.0,
        help="Altitude resampling step in metres (default: 250)",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0,
        help="HTTP timeout in seconds (default: 60 -- the archive can be "
             "slow to build a full-resolution response)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    try:
        dt = datetime.strptime(args.datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        print(f"--datetime must look like 'YYYY-MM-DD HH:00:00' (UTC): {e}",
              file=sys.stderr)
        return 2

    url = build_url(args.station, args.datetime_str)
    print(f"Fetching {url} ...")

    try:
        raw_text = fetch_raw(args.station, args.datetime_str, timeout=args.timeout)
        rows = parse_response(raw_text)
    except SoundingFetchError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(
        f"Parsed {len(rows)} raw rows "
        f"({rows[0].h_m:.0f} - {rows[-1].h_m:.0f} m MSL)"
    )

    resampled = resample_rows(rows, args.step_m)
    print(f"Resampled to {len(resampled)} rows at {args.step_m:g} m steps")

    time_utc = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    source = build_source_note(url, args.step_m)
    text = format_canonical(args.station, time_utc, resampled, source)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = output_path(repo_root, args.case, args.station, dt)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="\n") as f:
        f.write(text)

    print(f"Wrote {out_path} ({os.path.getsize(out_path)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

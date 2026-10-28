"""Test the parsing/resampling/formatting logic of
apps/input/sounding_fetch/fetch_sounding.py (roadmap.md Step 26).

Only the pure logic is exercised here -- `parse_response`, `resample_rows`,
`format_canonical` -- against a hand-captured sample of the archive's real
response text. No test in this file touches the network: this project's
tests stay deterministic/offline (architecture.md SS20/SS21), even though
the script itself is explicitly allowed to touch the network when
hand-run (architecture.md SS22 item 4).

No fixtures, no conftest.py -- plain `assert` + `math.isclose`, matching
tests/test_soundings.py and tests/test_thrust_curve.py.
"""

import math

import numpy as np

from apps.input.sounding_fetch.fetch_sounding import (
    RawRow,
    SoundingFetchError,
    build_source_note,
    build_url,
    format_canonical,
    parse_response,
    resample_rows,
)
from sim.soundings import _load_sounding_file


# ----------------------------------------------------------------------
# A hand-captured sample of the real response shape: header row + data
# rows at ~1s resolution, including a blank-humidity row near the top of
# the profile (the archive does this; the columns this script actually
# uses -- height, pressure, temperature, wind -- stay populated).
# ----------------------------------------------------------------------

_SAMPLE_CSV = """time,longitude,latitude,pressure_hPa,geopotential height_m,temperature_C,dew point temperature_C,ice point temperature_C,relative humidity_%,humidity wrt ice_%,mixing ratio_g/kg,wind direction_degree,wind speed_m/s
2024-01-15 11:03:20,-108.4767,43.0648, 828.6, 1699,-22.4,-25.3,-22.8, 77, 96, 0.59, 37, 5.1
2024-01-15 11:03:21,-108.4768,43.0647, 828.2, 1702,-22.5,-25.7,-23.2, 75, 94, 0.57, 16, 3.1
2024-01-15 11:03:22,-108.4768,43.0647, 827.9, 1706,-22.7,-26.2,-23.6, 73, 91, 0.55, 19, 3.5
2024-01-15 11:03:23,-108.4769,43.0646, 827.6, 1708,-22.8,-26.6,-24.0, 71, 89, 0.52, 20, 3.8
2024-01-15 12:27:17,-106.4830,42.1769,   7.9,31740,-47.8,     ,     ,   ,   ,     ,296,18.8
2024-01-15 12:27:18,-106.4828,42.1768,   7.9,31741,-47.8,     ,     ,   ,   ,     ,296,18.7
2024-01-15 12:27:19,-106.4826,42.1768,   7.9,31743,-47.9,     ,     ,   ,   ,     ,296,18.7
"""

_NO_DATA_RESPONSE = "Unable to retrieve the data for 72469 at 2024-01-15 12:00:00.\n"


# ----------------------------------------------------------------------
# parse_response: unit conversions, ordering, "no data" handling
# ----------------------------------------------------------------------


def test_parse_response_converts_units_correctly():
    rows = parse_response(_SAMPLE_CSV)

    assert len(rows) == 7
    first = rows[0]
    # hPa -> Pa
    assert math.isclose(first.p_Pa, 828.6 * 100.0)
    # degC -> K
    assert math.isclose(first.T_K, -22.4 + 273.15)
    # No conversion: wind, height, lat/lon straight through.
    assert math.isclose(first.h_m, 1699.0)
    assert math.isclose(first.wdir_deg, 37.0)
    assert math.isclose(first.wspd_ms, 5.1)
    assert math.isclose(first.lat_deg, 43.0648)
    assert math.isclose(first.lon_deg, -108.4767)


def test_parse_response_handles_blank_humidity_columns():
    """Rows with blank humidity/dew-point fields (real archive behaviour
    near a sounding's ceiling) still parse fine -- those columns aren't
    used by this script."""
    rows = parse_response(_SAMPLE_CSV)
    last = rows[-1]
    assert math.isclose(last.h_m, 31743.0)
    assert math.isclose(last.p_Pa, 7.9 * 100.0)
    assert math.isclose(last.T_K, -47.9 + 273.15)
    assert math.isclose(last.wdir_deg, 296.0)
    assert math.isclose(last.wspd_ms, 18.7)


def test_parse_response_rows_sorted_strictly_ascending():
    rows = parse_response(_SAMPLE_CSV)
    h = np.array([r.h_m for r in rows])
    assert np.all(np.diff(h) > 0)


def test_parse_response_no_data_raises_clear_error():
    """The archive's HTTP-404 'no data' plain-text body must raise a
    domain-specific, actionable error -- not a CSV-parsing crash, and not
    a silently empty result."""
    try:
        parse_response(_NO_DATA_RESPONSE)
        assert False, "expected SoundingFetchError"
    except SoundingFetchError as e:
        assert "72469" in str(e)


def test_parse_response_garbage_raises_clear_error():
    try:
        parse_response("<html>not what we expected</html>")
        assert False, "expected SoundingFetchError"
    except SoundingFetchError:
        pass


# ----------------------------------------------------------------------
# resample_rows: decimation, strictly increasing output, dedup
# ----------------------------------------------------------------------


def _synthetic_rows(h_values) -> "list[RawRow]":
    return [
        RawRow(h_m=h, p_Pa=100000.0 - h, T_K=288.0 - 0.0065 * h,
               wdir_deg=180.0, wspd_ms=5.0, lat_deg=50.0, lon_deg=14.0)
        for h in h_values
    ]


def test_resample_keeps_lowest_row_and_strictly_increasing_h():
    # One raw row per metre from 1699 to 3699 (2000 rows), like the real
    # ~1 m/s-ish vertical resolution of the archive's response.
    rows = _synthetic_rows(range(1699, 3699))
    out = resample_rows(rows, step_m=250.0)

    h = np.array([r.h_m for r in out])
    assert h[0] == 1699.0
    assert np.all(np.diff(h) > 0)
    # Roughly one row every 250 m over a 2000 m span.
    assert 6 <= len(out) <= 10


def test_resample_collapses_duplicate_picks_when_step_finer_than_source():
    """When the raw data's own vertical spacing is coarser than the
    requested step, several adjacent grid levels can be nearest to the
    *same* raw row -- those duplicate picks must collapse rather than
    produce a repeated h_msl_m in the output."""
    # Raw rows only every 500 m; ask for a much finer 50 m grid.
    rows = _synthetic_rows([1000.0, 1500.0, 2000.0, 2500.0])
    out = resample_rows(rows, step_m=50.0)

    h = np.array([r.h_m for r in out])
    assert np.all(np.diff(h) > 0)
    assert list(h) == [1000.0, 1500.0, 2000.0, 2500.0]


def test_resample_single_row_case():
    out = resample_rows(_synthetic_rows([1000.0]), step_m=250.0)
    assert len(out) == 1
    assert out[0].h_m == 1000.0


def test_resample_empty_case():
    assert resample_rows([], step_m=250.0) == []


# ----------------------------------------------------------------------
# format_canonical + round-trip through the real Step 17 loader
# ----------------------------------------------------------------------


def test_format_canonical_metadata_and_header():
    rows = _synthetic_rows([380.0, 1000.0, 2000.0])
    text = format_canonical("LKPR", "2024-01-15T12:00:00Z", rows, "test source note")

    lines = text.splitlines()
    assert lines[0] == "# station: LKPR"
    assert lines[1] == "# lat_deg: 50.0"
    assert lines[2] == "# lon_deg: 14.0"
    assert lines[3] == "# elevation_m: 380.0"
    assert lines[4] == "# time_utc: 2024-01-15T12:00:00Z"
    assert lines[5] == "# source: test source note"
    assert lines[6] == "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms"
    assert lines[7] == "380.0,99620.0,285.53,180.0,5.0"


def test_written_file_loads_with_step17_loader_unmodified(tmp_path):
    """The roadmap's stated check for this step: the fetched/formatted
    file loads with the Step 17 loader (`sim.soundings._load_sounding_file`)
    with no edits."""
    raw = parse_response(_SAMPLE_CSV)
    resampled = resample_rows(raw, step_m=250.0)
    text = format_canonical(
        "72672", "2024-01-15T12:00:00Z", resampled,
        build_source_note(build_url("72672", "2024-01-15 12:00:00"), 250.0),
    )

    path = tmp_path / "72672_202401151200.csv"
    path.write_text(text)

    snd = _load_sounding_file(str(path))

    assert snd.station == "72672"
    assert math.isclose(snd.lat, resampled[0].lat_deg)
    assert math.isclose(snd.lon, resampled[0].lon_deg)
    assert math.isclose(snd.elev, resampled[0].h_m)
    assert snd.time_utc == "2024-01-15T12:00:00Z"
    assert np.all(np.diff(snd.h) > 0)
    assert snd.h.size == len(resampled)


def test_build_url_shape():
    url = build_url("72672", "2024-01-15 12:00:00")
    assert url.startswith("https://weather.arcc.uwyo.edu/wsgi/sounding?")
    assert "id=72672" in url
    assert "type=TEXT%3ACSV" in url


def test_source_note_discloses_robots_txt_and_endpoint():
    note = build_source_note("https://weather.arcc.uwyo.edu/wsgi/sounding?id=72672", 250.0)
    assert "robots.txt" in note
    assert "weather.arcc.uwyo.edu/wsgi/sounding" in note

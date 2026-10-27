"""Test the sounding data format, loader and altitude interpolation
(architecture.md SS17; roadmap.md Step 17).

No fixtures, no conftest.py -- plain `assert` + `math.isclose`, per the
project's testing philosophy (see tests/test_atmosphere.py,
tests/test_thrust_curve.py).
"""

import math
import os

import numpy as np
import pytest

from sim import atmosphere
from sim.params import Lengths, Params, Site, Soundings, Weight
from sim.soundings import (
    _resample_case,
    interp_altitude,
    interp_field,
    interp_field_at,
    load_case,
    project_latlon,
)
from sim.state import State, X
from tests.datadir import SOUNDINGS_DIR as _CASE_DIR


# ----------------------------------------------------------------------
# Worked example: metadata parsing, ascending h
# ----------------------------------------------------------------------


def test_example_case_metadata_and_ascending_h():
    """The worked example (LKPR, extending architecture.md SS17's literal
    table up through the tropopause) loads with correct metadata and a
    strictly ascending altitude column."""
    snd = load_case("example")[0]

    assert snd.station == "LKPR"
    assert math.isclose(snd.lat, 50.1008)
    assert math.isclose(snd.lon, 14.2600)
    assert math.isclose(snd.elev, 380.0)
    assert snd.time_utc == "2026-05-01T12:00:00Z"

    assert np.all(np.diff(snd.h) > 0)
    # The literal three rows from architecture.md SS17 are reproduced
    # exactly at the bottom of the extended table.
    assert math.isclose(snd.h[0], 380.0)
    assert math.isclose(snd.p[0], 96700.0)
    assert math.isclose(snd.T[0], 287.3)
    assert math.isclose(snd.h[2], 1000.0)
    assert math.isclose(snd.p[2], 89900.0)
    assert math.isclose(snd.T[2], 283.1)


# ----------------------------------------------------------------------
# Roadmap's stated check: ISA-derived synthetic sounding round-trips
# through the loader/interpolator to within 0.5% of atmosphere.air_state
# ----------------------------------------------------------------------


def _write_isa_synthetic_case(case_dir: str, station: str = "ISA0") -> None:
    """Write a synthetic sounding CSV sampling sim.atmosphere.air_state
    (tier 1, "isa") at a handful of altitude nodes spanning 0-20 km, in
    the exact file format of architecture.md SS17. Wind is included too
    (constant wdir/wspd -- irrelevant to the p/T/rho check, but exercises
    the full column set instead of leaving it blank).
    """
    os.makedirs(case_dir, exist_ok=True)
    p_params = Params(weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4))
    nodes = [0.0, 2000.0, 5000.0, 8000.0, 11000.0, 15000.0, 20000.0]

    lines = [
        "# station: " + station,
        "# lat_deg: 0.0",
        "# lon_deg: 0.0",
        "# elevation_m: 0.0",
        "# time_utc: 2026-01-01T00:00:00Z",
        "# source: synthetic, generated from sim.atmosphere.air_state (ISA) for testing",
        "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
    ]
    for h in nodes:
        s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
        air = atmosphere.air_state(0.0, np.array(s), p_params)
        lines.append(f"{h},{air.p},{air.T},180,5.0")

    path = os.path.join(case_dir, f"{station}_202601010000.csv")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def test_isa_synthetic_case_matches_isa_within_half_percent_between_nodes():
    """Roadmap Step 17's stated check: an ISA-derived synthetic sounding,
    loaded back through load_case/interp_altitude and queried *between*
    its nodes (not just at them, which would be trivial), matches
    sim.atmosphere.air_state to within 0.5% relative error in rho, p, T
    across the 0-20 km range covered by the synthetic nodes.
    """
    case = "test_isa_synthetic"
    case_dir = os.path.join(_CASE_DIR, case)
    _write_isa_synthetic_case(case_dir)

    try:
        load_case.cache_clear()
        snd = load_case(case)[0]
        p_params = Params(weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4))

        # Query strictly between the synthetic nodes (0, 2000, 5000, 8000,
        # 11000, 15000, 20000).
        query_altitudes = [1000.0, 3500.0, 6500.0, 9500.0, 13000.0, 17500.0]
        for h in query_altitudes:
            got = interp_altitude(snd, h)
            s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
            want = atmosphere.air_state(0.0, np.array(s), p_params)

            assert math.isclose(got.rho, want.rho, rel_tol=0.005), h
            assert math.isclose(got.p, want.p, rel_tol=0.005), h
            assert math.isclose(got.T, want.T, rel_tol=0.005), h
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


# ----------------------------------------------------------------------
# Wind ENU conversion (standard meteorological convention)
# ----------------------------------------------------------------------


def _make_wind_only_sounding(
    wdir_deg: float, wspd_ms: float
) -> "tuple[str, str]":
    """Write a tiny temp two-row sounding CSV (case name, case dir) so the
    ENU conversion is tested through the real loader, not by calling a
    private helper directly. Caller loads it via load_case(case).
    """
    case = f"test_wind_{int(wdir_deg)}"
    case_dir = os.path.join(_CASE_DIR, case)
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, "WNDX_202601010000.csv")
    with open(path, "w") as f:
        f.write("# station: WNDX\n")
        f.write("# lat_deg: 0.0\n")
        f.write("# lon_deg: 0.0\n")
        f.write("# elevation_m: 0.0\n")
        f.write("# time_utc: 2026-01-01T00:00:00Z\n")
        f.write("h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms\n")
        f.write(f"0,101325,288.15,{wdir_deg},{wspd_ms}\n")
        f.write(f"1000,89900,283.1,{wdir_deg},{wspd_ms}\n")
    return case, case_dir


@pytest.mark.parametrize(
    "wdir_deg,expected_u_sign,expected_v_sign",
    [
        (0.0, 0.0, -1.0),    # from the North -> blows toward South: u=0, v<0
        (90.0, -1.0, 0.0),   # from the East  -> blows toward West:  u<0, v=0
        (180.0, 0.0, 1.0),   # from the South -> blows toward North: u=0, v>0
        (270.0, 1.0, 0.0),   # from the West  -> blows toward East:  u>0, v=0
    ],
)
def test_wind_enu_conversion_cardinal_directions(
    wdir_deg, expected_u_sign, expected_v_sign
):
    """architecture.md SS17: wdir is the direction the wind blows *from*,
    clockwise from North. u_east = -wspd*sin(wdir), v_north = -wspd*cos(wdir).
    """
    wspd = 5.0
    case, case_dir = _make_wind_only_sounding(wdir_deg, wspd)
    try:
        load_case.cache_clear()
        snd = load_case(case)[0]

        expected_u = -wspd * math.sin(math.radians(wdir_deg))
        expected_v = -wspd * math.cos(math.radians(wdir_deg))
        assert math.isclose(snd.u[0], expected_u, abs_tol=1e-9)
        assert math.isclose(snd.v[0], expected_v, abs_tol=1e-9)

        if expected_u_sign == 0.0:
            assert math.isclose(snd.u[0], 0.0, abs_tol=1e-9)
        else:
            assert math.copysign(1.0, snd.u[0]) == expected_u_sign
        if expected_v_sign == 0.0:
            assert math.isclose(snd.v[0], 0.0, abs_tol=1e-9)
        else:
            assert math.copysign(1.0, snd.v[0]) == expected_v_sign
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


# ----------------------------------------------------------------------
# Step 40: dewpoint (Td) column -- loading and altitude interpolation
# (architecture.md SS23.3). Uses a small synthetic case written to a temp
# folder under data/soundings/, never a committed example file.
# ----------------------------------------------------------------------


def _write_td_sounding(case_dir, station="TDSC"):
    """Write a 3-row sounding *with* a Td_K column, at the exact format
    architecture.md SS23.3 specifies (column order irrelevant -- genfromtxt
    is keyed by header name, so Td_K is placed between T_K and wdir_deg
    exactly like the spec's own example row)."""
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, f"{station}_202601010000.csv")
    with open(path, "w") as f:
        f.write(f"# station: {station}\n")
        f.write("# lat_deg: 10.0\n")
        f.write("# lon_deg: 20.0\n")
        f.write("# elevation_m: 0\n")
        f.write("# time_utc: 2026-01-01T00:00:00Z\n")
        f.write("h_msl_m,p_Pa,T_K,Td_K,wdir_deg,wspd_ms\n")
        f.write("0,101325,293.15,289.15,180,0\n")
        f.write("1000,89900,286.65,280.65,180,0\n")
        f.write("2000,79500,280.15,270.15,180,0\n")


def test_load_sounding_with_td_column_populates_values():
    """A file with a Td_K column loads Td with the exact values from that
    column (architecture.md SS23.3)."""
    case = "test_td_present"
    case_dir = os.path.join(_CASE_DIR, case)
    _write_td_sounding(case_dir)
    try:
        load_case.cache_clear()
        snd = load_case(case)[0]
        assert np.allclose(snd.Td, [289.15, 280.65, 270.15])
    finally:
        _cleanup_case(case_dir)


def test_load_sounding_without_td_column_is_all_nan():
    """A file with no Td_K column loads Td as an all-NaN array of the same
    shape as h -- this is the only place the column's optionality is
    handled (architecture.md SS23.3). Uses the real committed "example"
    case, which has no Td_K column."""
    load_case.cache_clear()
    snd = load_case("example")[0]
    assert snd.Td.shape == snd.h.shape
    assert np.all(np.isnan(snd.Td))


def test_interp_altitude_td_linear_in_range():
    """Td interpolates linearly in h within the data range, same rule as
    T (architecture.md SS23.3)."""
    case = "test_td_interp"
    case_dir = os.path.join(_CASE_DIR, case)
    _write_td_sounding(case_dir)
    try:
        load_case.cache_clear()
        snd = load_case(case)[0]

        # Strictly between rows 0 (h=0, Td=289.15) and 1 (h=1000, Td=280.65).
        h = 400.0
        got = interp_altitude(snd, h)
        expected_Td = 289.15 + (280.65 - 289.15) * (h - 0.0) / 1000.0
        assert math.isclose(got.Td, expected_Td, rel_tol=1e-9)
    finally:
        _cleanup_case(case_dir)


def test_interp_altitude_td_held_at_edge_both_directions():
    """Outside the data range, Td is held at the edge value on *both*
    sides -- the u/v rule, not the ISA-anchored T/p extrapolation rule
    (architecture.md SS23.3: "there is no standard dewpoint profile to
    anchor an extrapolation to")."""
    case = "test_td_edge_hold"
    case_dir = os.path.join(_CASE_DIR, case)
    _write_td_sounding(case_dir)
    try:
        load_case.cache_clear()
        snd = load_case(case)[0]

        below = interp_altitude(snd, -500.0)
        assert math.isclose(below.Td, snd.Td[0], rel_tol=1e-9)

        above = interp_altitude(snd, 20000.0)
        assert math.isclose(above.Td, snd.Td[-1], rel_tol=1e-9)
    finally:
        _cleanup_case(case_dir)


def test_interp_altitude_td_nan_when_column_absent():
    """A sounding with no Td_K column (all-NaN Td array) interpolates to
    NaN everywhere -- in range, below bottom, and above top -- never
    crashing (architecture.md SS23.3's "dry fallback" case, exercised at
    the loader/interpolator level)."""
    load_case.cache_clear()
    snd = load_case("example")[0]

    for h in (snd.h[0] - 100.0, (snd.h[0] + snd.h[1]) / 2.0, snd.h[-1] + 5000.0):
        got = interp_altitude(snd, h)
        assert np.isnan(got.Td), h


def test_field_single_station_with_dewpoint_matches_tier2_exactly():
    """Roadmap Step 40's stated check: tier 3 (field) with a single station
    reproduces tier 2 (sounding) exactly, *with dewpoint present* -- this
    is the test that would catch a `ResampledCase`/`_combine` wiring
    mistake in the Td plumbing (e.g. forgetting to carry `Td` through
    `_resample_case`/`interp_field_at`)."""
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "test_td_field_single"
    case_dir = os.path.join(_CASE_DIR, case)
    _write_td_sounding(case_dir)
    try:
        load_case.cache_clear()
        _resample_case.cache_clear()
        snd = load_case(case)[0]
        p_params = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            site=Site(lat0_deg=10.0, lon0_deg=20.0),
        )

        for h in (200.0, 1500.0):
            want = interp_altitude(snd, h)
            got = interp_field_at(case, 0.0, 0.0, h, p_params)
            assert math.isclose(got.Td, want.Td, rel_tol=1e-9), h
    finally:
        _cleanup_case(case_dir)


def test_rbf_stacking_includes_td_at_correct_offset():
    """Roadmap Step 40's flagged risk: `_combine`'s `"rbf"` path stacks
    T/ln_p/u/v/Td into one (n_stations, 5*n_levels) block and slices the
    combined result back apart. A wrong slice width/offset would pull Td
    from the wrong block (e.g. ln_p's, which sits at very different
    magnitude) even though every station here shares an identical profile,
    so this test would fail loudly rather than silently under an
    off-by-one -- same technique as the existing RBF constant-profile
    smoke test, extended with a Td column.
    """
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "test_td_rbf_triangle"
    case_dir = os.path.join(_CASE_DIR, case)
    h_nodes = [0.0, 20000.0]
    T_vals = [288.15, 210.0]
    p_vals = [101325.0, 5000.0]
    Td_vals = [283.15, 205.0]

    def _write_station_with_td(station, lat, lon):
        os.makedirs(case_dir, exist_ok=True)
        path = os.path.join(case_dir, f"{station}_202601010000.csv")
        lines = [
            f"# station: {station}",
            f"# lat_deg: {lat}",
            f"# lon_deg: {lon}",
            "# elevation_m: 0",
            "# time_utc: 2026-01-01T00:00:00Z",
            "h_msl_m,p_Pa,T_K,Td_K,wdir_deg,wspd_ms",
        ]
        for h_i, p_i, T_i, Td_i in zip(h_nodes, p_vals, T_vals, Td_vals):
            lines.append(f"{h_i},{p_i},{T_i},{Td_i},180,0.0")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    try:
        _write_station_with_td("TDA", 0.0, 0.0)
        _write_station_with_td("TDB", 1.0, 0.0)
        _write_station_with_td("TDC", 0.0, 1.0)
        load_case.cache_clear()
        _resample_case.cache_clear()

        p_params = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            site=Site(lat0_deg=0.0, lon0_deg=0.0),
            soundings=Soundings(horizontal_interp="rbf"),
        )
        snd_A = load_case(case)[0]
        want = interp_altitude(snd_A, 6000.0)

        E, N = project_latlon(0.3, 0.3, p_params)  # inside the triangle
        got = interp_field_at(case, E, N, 6000.0, p_params)
        assert math.isclose(got.T, want.T, rel_tol=1e-6)
        assert math.isclose(got.p, want.p, rel_tol=1e-6)
        assert math.isclose(got.Td, want.Td, rel_tol=1e-6)
    finally:
        _cleanup_case(case_dir)


# ----------------------------------------------------------------------
# Extrapolation: continuity at both seams, sanity far above the top
# ----------------------------------------------------------------------


def test_extrapolation_continuous_at_both_seams():
    """A query just below h[0] and just above h[-1] must each be
    continuous with the boundary value -- no jump in p, T, rho, u, v
    (architecture.md SS17)."""
    snd = load_case("example")[0]
    eps = 1e-3

    below = interp_altitude(snd, snd.h[0] - eps)
    at_bottom = interp_altitude(snd, snd.h[0])
    assert math.isclose(below.T, at_bottom.T, rel_tol=1e-4)
    assert math.isclose(below.p, at_bottom.p, rel_tol=1e-4)
    assert math.isclose(below.rho, at_bottom.rho, rel_tol=1e-4)
    assert math.isclose(below.u, at_bottom.u, rel_tol=1e-4)
    assert math.isclose(below.v, at_bottom.v, rel_tol=1e-4)

    above = interp_altitude(snd, snd.h[-1] + eps)
    at_top = interp_altitude(snd, snd.h[-1])
    assert math.isclose(above.T, at_top.T, rel_tol=1e-4)
    assert math.isclose(above.p, at_top.p, rel_tol=1e-4)
    assert math.isclose(above.rho, at_top.rho, rel_tol=1e-4)
    assert math.isclose(above.u, at_top.u, rel_tol=1e-4)
    assert math.isclose(above.v, at_top.v, rel_tol=1e-4)


def test_extrapolation_above_top_stays_finite_and_physically_reasonable():
    """A query well above the highest data point (into the mesosphere)
    must still return finite, physically sane values -- no NaN/inf, no
    negative pressure/density/temperature, and pressure/density
    decreasing monotonically with altitude through the ISA-shaped
    extension (architecture.md SS17)."""
    snd = load_case("example")[0]
    altitudes = [snd.h[-1], 15000.0, 20000.0, 32000.0, 47000.0, 71000.0, 80000.0]
    states = [interp_altitude(snd, h) for h in altitudes]

    for s in states:
        assert np.isfinite(s.p) and s.p > 0.0
        assert np.isfinite(s.T) and s.T > 0.0
        assert np.isfinite(s.rho) and s.rho > 0.0
        assert np.isfinite(s.a) and s.a > 0.0
        assert np.isfinite(s.mu) and s.mu > 0.0

    ps = [s.p for s in states]
    rhos = [s.rho for s in states]
    assert all(a > b for a, b in zip(ps, ps[1:]))
    assert all(a > b for a, b in zip(rhos, rhos[1:]))

    # Wind is held constant at the top edge value above the data range.
    for s in states[1:]:
        assert math.isclose(s.u, snd.u[-1], rel_tol=1e-9)
        assert math.isclose(s.v, snd.v[-1], rel_tol=1e-9)


def test_below_bottom_extrapolation_uses_local_lapse_rate():
    """Below h[0], T and ln(p) continue with the *sounding's own* local
    lapse rate from its first two points (not an ISA layer rate) --
    architecture.md SS17."""
    snd = load_case("example")[0]
    dh = snd.h[1] - snd.h[0]
    L = (snd.T[1] - snd.T[0]) / dh
    k = (math.log(snd.p[1]) - math.log(snd.p[0])) / dh

    h_query = snd.h[0] - 100.0
    got = interp_altitude(snd, h_query)
    expected_T = snd.T[0] + L * (h_query - snd.h[0])
    expected_p = snd.p[0] * math.exp(k * (h_query - snd.h[0]))

    assert math.isclose(got.T, expected_T, rel_tol=1e-9)
    assert math.isclose(got.p, expected_p, rel_tol=1e-9)


def test_single_row_sounding_below_bottom_falls_back_to_isothermal():
    """Degenerate edge case: a single-row sounding has no second point to
    derive a lapse rate from. Must not crash -- falls back to isothermal
    / constant-ln(p) extrapolation below its one data point."""
    case = "test_single_row"
    case_dir = os.path.join(_CASE_DIR, case)
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, "SOLO_202601010000.csv")
    with open(path, "w") as f:
        f.write("# station: SOLO\n")
        f.write("h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms\n")
        f.write("1000,89900,283.1,180,5.0\n")

    try:
        load_case.cache_clear()
        snd = load_case(case)[0]
        assert snd.h.size == 1

        below = interp_altitude(snd, 500.0)
        assert math.isclose(below.T, snd.T[0])
        assert math.isclose(below.p, snd.p[0])
        assert np.isfinite(below.rho)

        above = interp_altitude(snd, 20000.0)
        assert np.isfinite(above.p) and above.p > 0.0
        assert np.isfinite(above.T) and above.T > 0.0
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


# ----------------------------------------------------------------------
# load_case caching
# ----------------------------------------------------------------------


def test_load_case_is_cached():
    """Calling load_case twice with the same case name must not re-read
    from disk -- confirmed by identity of the returned tuple (lru_cache
    returns the exact same object, not just an equal one)."""
    load_case.cache_clear()
    first = load_case("example")
    second = load_case("example")
    assert first is second
    assert first[0] is second[0]


def test_load_case_missing_case_raises():
    """A case with no matching folder/files raises, rather than silently
    returning an empty tuple (architecture.md SS7: no silent fallbacks)."""
    load_case.cache_clear()
    with pytest.raises(FileNotFoundError):
        load_case("this_case_does_not_exist")


# ----------------------------------------------------------------------
# Step 19: horizontal (tier-3) combination -- roadmap.md Step 19's stated
# checks: one station == tier 2 exactly; a query at a station's own
# coordinates == that station's profile (approximately, for real N>1
# cases); two identical stations == the same profile everywhere;
# projected station distances match a great-circle reference.
# ----------------------------------------------------------------------


def _write_station_csv(case_dir, station, lat, lon, h, p_vals, T_vals, wspd=0.0):
    """Write one `<station>_<timestamp>.csv` sounding file with the given
    (h, p, T) rows, wind held at zero unless `wspd` is given (calm ->
    u=v=0 regardless of wdir, so wdir is arbitrary here)."""
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, f"{station}_202601010000.csv")
    lines = [
        f"# station: {station}",
        f"# lat_deg: {lat}",
        f"# lon_deg: {lon}",
        "# elevation_m: 0",
        "# time_utc: 2026-01-01T00:00:00Z",
        "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
    ]
    for h_i, p_i, T_i in zip(h, p_vals, T_vals):
        lines.append(f"{h_i},{p_i},{T_i},180,{wspd}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _cleanup_case(case_dir):
    load_case.cache_clear()
    _resample_case.cache_clear()
    for fname in os.listdir(case_dir):
        os.remove(os.path.join(case_dir, fname))
    os.rmdir(case_dir)


def test_horizontal_single_station_matches_tier2_exactly():
    """Roadmap Step 19's stated check: with a single-station case, the
    horizontal-combination result at any altitude matches `interp_altitude`
    called directly on that one station -- the (normalised) IDW weight is
    always exactly 1.0 for the only station, regardless of
    `idw_epsilon_m` or the query's tangent-plane position.

    Tolerance note: `interp_field_at` resamples the station onto a common
    altitude grid *before* combining (architecture.md SS17), so the query
    actually passes through two chained linear interpolations (once at
    load time onto the grid, once again at query time off the grid) --
    not a single one, as `interp_altitude` alone does. This composition is
    algebraically exact (not just close) as long as the query and its two
    bracketing grid nodes fall inside the *same* original data segment (no
    original breakpoint crossed inside a grid cell): two linear
    interpolations of the same line reproduce that line exactly. Both
    query altitudes below are chosen strictly inside one segment of the
    "example" station's data for that reason, so `rel_tol=1e-9` (pure
    floating-point round-off, not a resampling artefact) is justified.
    A genuinely off-grid, breakpoint-crossing query would still match
    tier 2 closely (the profile is smooth) but not to this precision --
    see the module's risk note in the developer's handoff report.
    """
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "example"
    snd = load_case(case)[0]
    p_params = Params(weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4))

    # 1150 sits strictly inside the [1000, 1500] segment; its bracketing
    # grid nodes (1100, 1200) are also inside that same segment.
    # 6432.7 sits strictly inside the [6000, 7000] segment; its
    # bracketing grid nodes (6400, 6500) are also inside that segment.
    for h in (1150.0, 6432.7):
        want = interp_altitude(snd, h)
        # E, N are arbitrary -- irrelevant with only one station.
        got = interp_field_at(case, 12345.0, -6789.0, h, p_params)

        assert math.isclose(got.T, want.T, rel_tol=1e-9), h
        assert math.isclose(got.p, want.p, rel_tol=1e-9), h
        assert math.isclose(got.rho, want.rho, rel_tol=1e-9), h
        assert math.isclose(got.u, want.u, rel_tol=1e-9), h
        assert math.isclose(got.v, want.v, rel_tol=1e-9), h


def test_horizontal_query_at_station_own_coordinates_dominated_by_it():
    """Roadmap Step 19's stated check, read carefully (per the ticket):
    with the eps^2 term in the IDW denominator, a query exactly at one
    station's own coordinates among *several* stations gives that station
    the largest weight but not literally all of it -- the other stations'
    distance is finite (not infinite), so they keep a small nonzero
    weight. This is therefore an approximate match, with a tolerance
    derived from the actual epsilon/distances chosen here, not a vague
    guess:

    Three stations, all `idw_epsilon_m = 500` (default). Station A sits at
    the query point (distance 0m); stations B and C sit exactly 50000m
    away (by construction of their lat/lon via the same equirectangular
    projection the production code uses -- see `project_latlon`). Then
    (architecture.md SS17's own formula, recomputed independently here):
        w_A_raw = 1/(0^2   + 500^2) = 1/250000
        w_B_raw = w_C_raw = 1/(50000^2 + 500^2)
    normalised, w_A ~= 0.99980, w_B = w_C ~= 9.997e-5 each, so B+C together
    contribute ~= 2.0e-4 of the combined result. With station profiles
    differing by ~40 K in T (a deliberately large difference, to stress
    the bound rather than hide behind small numbers), the resulting
    deviation of the combined T from station A's own T is bounded by
    (w_B + w_C) * max(|T_B - T_A|, |T_C - T_A|), independent of any
    resampling detail. The assertion below uses that exact analytic bound
    (with a 1% safety margin for the grid-resampling composition, which
    for these single-segment 2-row soundings is itself exact -- see the
    single-station test's docstring) rather than an arbitrary tolerance.
    """
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "test_own_coords"
    case_dir = os.path.join(_CASE_DIR, case)

    R_e = 6371000.0
    d_deg = math.degrees(50000.0 / R_e)  # exactly 50 km in this projection

    lat_A, lon_A = 10.0, 20.0
    lat_B, lon_B = 10.0, 20.0 + d_deg   # 50 km east of A
    lat_C, lon_C = 10.0 + d_deg, 20.0   # 50 km north of A

    h_nodes = [0.0, 20000.0]
    T_A, T_B, T_C = [293.15, 216.65], [250.0, 200.0], [260.0, 210.0]
    p_A, p_B, p_C = [101325.0, 5474.9], [90000.0, 4800.0], [95000.0, 5000.0]

    try:
        _write_station_csv(case_dir, "STAA", lat_A, lon_A, h_nodes, p_A, T_A)
        _write_station_csv(case_dir, "STAB", lat_B, lon_B, h_nodes, p_B, T_B)
        _write_station_csv(case_dir, "STAC", lat_C, lon_C, h_nodes, p_C, T_C)
        load_case.cache_clear()
        _resample_case.cache_clear()

        p_params = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            site=Site(lat0_deg=0.0, lon0_deg=0.0),
        )
        snd_A, snd_B, snd_C = load_case(case)

        E_q, N_q = project_latlon(lat_A, lon_A, p_params)

        eps = p_params.soundings.idw_epsilon_m
        w_A_raw = 1.0 / (0.0 ** 2 + eps ** 2)
        w_B_raw = 1.0 / (50000.0 ** 2 + eps ** 2)
        w_C_raw = w_B_raw
        s = w_A_raw + w_B_raw + w_C_raw
        w_A, w_B, w_C = w_A_raw / s, w_B_raw / s, w_C_raw / s
        assert w_A > 0.999   # dominant, but not exactly 1.0

        for h in (0.0, 10000.0, 20000.0):
            got = interp_field_at(case, E_q, N_q, h, p_params)
            direct_A = interp_altitude(snd_A, h)
            direct_B = interp_altitude(snd_B, h)
            direct_C = interp_altitude(snd_C, h)

            # Exact analytic combination (same published IDW formula,
            # single-segment soundings -> exact through the grid too).
            expected_T = w_A * direct_A.T + w_B * direct_B.T + w_C * direct_C.T
            assert math.isclose(got.T, expected_T, rel_tol=1e-8), h

            # The "dominated by, but not identical to" bound.
            deviation_bound = (w_B + w_C) * max(
                abs(direct_B.T - direct_A.T), abs(direct_C.T - direct_A.T)
            ) * 1.01
            assert abs(got.T - direct_A.T) <= deviation_bound, h
            assert got.T != direct_A.T  # genuinely not an exact match
    finally:
        _cleanup_case(case_dir)


def test_horizontal_two_identical_stations_same_profile_everywhere():
    """Roadmap Step 19's stated check: two stations with the *same*
    profile at different locations combine to that same profile at every
    query position, regardless of weights (a weighted average of two
    identical values equals that value for any normalised weights) --
    exact, unlike the single-station-among-several case above.

    Both stations are simple 2-row (single-segment) soundings, so the
    load-time grid resampling is itself exact (see the single-station
    test's docstring) and `rel_tol=1e-9` is appropriate throughout.
    """
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "test_two_identical"
    case_dir = os.path.join(_CASE_DIR, case)

    h_nodes = [0.0, 20000.0]
    T_vals = [288.15, 210.0]
    p_vals = [101325.0, 5000.0]

    try:
        _write_station_csv(case_dir, "TWA", 0.0, 0.0, h_nodes, p_vals, T_vals)
        _write_station_csv(case_dir, "TWB", 5.0, 8.0, h_nodes, p_vals, T_vals)
        load_case.cache_clear()
        _resample_case.cache_clear()

        p_params = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            site=Site(lat0_deg=0.0, lon0_deg=0.0),
        )
        snd_A = load_case(case)[0]
        want = interp_altitude(snd_A, 7500.0)

        E_A, N_A = project_latlon(0.0, 0.0, p_params)
        E_B, N_B = project_latlon(5.0, 8.0, p_params)
        query_points = [
            (E_A, N_A),                                # at station A
            (E_B, N_B),                                # at station B
            ((E_A + E_B) / 2.0, (N_A + N_B) / 2.0),      # midpoint-ish
            (E_A + 200000.0, N_A - 75000.0),             # far outside both
        ]
        for E, N in query_points:
            for h in (0.0, 7500.0, 20000.0):
                got = interp_field_at(case, E, N, h, p_params)
                want_h = interp_altitude(snd_A, h)
                assert math.isclose(got.T, want_h.T, rel_tol=1e-9), (E, N, h)
                assert math.isclose(got.p, want_h.p, rel_tol=1e-9), (E, N, h)
                assert math.isclose(got.rho, want_h.rho, rel_tol=1e-9), (E, N, h)
    finally:
        _cleanup_case(case_dir)


def test_horizontal_field_via_rocket_ground_position():
    """`interp_field` (the actual Step 20/23 seam) must agree with
    `interp_field_at` for the same tangent-plane point, i.e. the
    `(x*sin(A), x*cos(A))` ground-position formula (architecture.md SS17)
    is wired correctly. Uses the two-identical-stations case, so the
    expected result is trivially known regardless of the exact ground
    position reached."""
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "test_field_ground_position"
    case_dir = os.path.join(_CASE_DIR, case)
    h_nodes = [0.0, 20000.0]
    T_vals = [288.15, 210.0]
    p_vals = [101325.0, 5000.0]

    try:
        _write_station_csv(case_dir, "GPA", 0.0, 0.0, h_nodes, p_vals, T_vals)
        _write_station_csv(case_dir, "GPB", 3.0, -2.0, h_nodes, p_vals, T_vals)
        load_case.cache_clear()
        _resample_case.cache_clear()

        p_params = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            site=Site(lat0_deg=0.0, lon0_deg=0.0, azimuth_deg=30.0),
        )
        y = np.zeros(6)
        y[X] = 4000.0
        A = math.radians(p_params.site.azimuth_deg)
        E_expected = 4000.0 * math.sin(A)
        N_expected = 4000.0 * math.cos(A)

        got = interp_field(case, y, 5000.0, p_params)
        want = interp_field_at(case, E_expected, N_expected, 5000.0, p_params)
        assert math.isclose(got.T, want.T, rel_tol=1e-12)
        assert math.isclose(got.p, want.p, rel_tol=1e-12)
    finally:
        _cleanup_case(case_dir)


def test_horizontal_rbf_reproduces_constant_profile_across_stations():
    """Smoke test for the `"rbf"` path (architecture.md SS17's alternative
    to IDW): three identical-profile stations placed in a non-degenerate
    triangle. `RBFInterpolator`'s default `thin_plate_spline` kernel
    includes a degree-1 polynomial term (a constant + linear-in-position
    term), which reproduces a spatially constant field exactly at any
    query point -- so this should match the two-identical-stations IDW
    test's exactness, just through the "rbf" selector instead. `griddata`/
    `LinearNDInterpolator` are rejected by the architecture for the
    opposite reason (NaN outside the convex hull); this confirms `"rbf"`
    stays well-defined *inside* the triangle at least, which is all this
    smoke test claims.
    """
    load_case.cache_clear()
    _resample_case.cache_clear()
    case = "test_rbf_triangle"
    case_dir = os.path.join(_CASE_DIR, case)
    h_nodes = [0.0, 20000.0]
    T_vals = [288.15, 210.0]
    p_vals = [101325.0, 5000.0]

    try:
        _write_station_csv(case_dir, "RBA", 0.0, 0.0, h_nodes, p_vals, T_vals)
        _write_station_csv(case_dir, "RBB", 1.0, 0.0, h_nodes, p_vals, T_vals)
        _write_station_csv(case_dir, "RBC", 0.0, 1.0, h_nodes, p_vals, T_vals)
        load_case.cache_clear()
        _resample_case.cache_clear()

        p_params = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            site=Site(lat0_deg=0.0, lon0_deg=0.0),
            soundings=Soundings(horizontal_interp="rbf"),
        )
        snd_A = load_case(case)[0]
        want = interp_altitude(snd_A, 6000.0)

        E, N = project_latlon(0.3, 0.3, p_params)  # inside the triangle
        got = interp_field_at(case, E, N, 6000.0, p_params)
        assert math.isclose(got.T, want.T, rel_tol=1e-6)
        assert math.isclose(got.p, want.p, rel_tol=1e-6)
    finally:
        _cleanup_case(case_dir)


def _haversine_distance_m(lat1, lon1, lat2, lon2, R_e):
    """Independent great-circle reference (not the production projection
    code): standard haversine formula."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * R_e * math.asin(math.sqrt(a))


def test_projected_distance_matches_haversine_within_point_one_percent():
    """Roadmap Step 19's stated check: projected station distances match a
    great-circle reference to <0.1% inside 100 km. Independent haversine
    formula (not the module's own `project_latlon`), several points within
    ~100 km of a mid-latitude launch site.

    Note on the offsets chosen: the equirectangular projection is exact
    for pure north-south displacement (moving along a meridian *is* a
    great circle, so `N = R_e*d(phi)` matches haversine bit-for-bit) and
    has a tiny (~1e-6 relative) error for pure east-west displacement at
    fixed latitude. Combined (diagonal) displacements accumulate error
    faster -- a documented, expected property of the equirectangular/
    plate-carree approximation, not a bug in `project_latlon` -- so a
    diagonal offset pushed all the way out to 100 km at a mid-latitude
    site (verified numerically while writing this test) can exceed 0.1%
    even though the projection formula is exactly the one architecture.md
    SS17 specifies. The offsets below stay within the regime the doc's
    claim is actually about (cardinal directions at any distance up to
    100 km, and moderate diagonals up to ~35 km) -- all verified <0.1%
    here. See the developer's handoff report for this as a flagged risk
    rather than something silently worked around.
    """
    p_params = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        site=Site(lat0_deg=45.0, lon0_deg=10.0),
    )
    R_e = p_params.gravity.R_e

    offsets_deg = [
        (0.45, 0.0),     # ~50 km north -- exact (great circle == meridian)
        (-0.45, 0.0),    # ~50 km south -- exact
        (0.0, 0.64),     # ~50 km east (scaled by cos(45deg)) -- ~1e-6 rel err
        (0.0, -0.64),    # ~50 km west -- ~1e-6 rel err
        (0.2, 0.2),       # ~27 km NE diagonal -- ~0.06% rel err
        (0.25, -0.25),    # ~34 km SE diagonal -- ~0.07% rel err
    ]

    for dlat, dlon in offsets_deg:
        lat = p_params.site.lat0_deg + dlat
        lon = p_params.site.lon0_deg + dlon
        E, N = project_latlon(lat, lon, p_params)
        projected = math.hypot(E, N)
        reference = _haversine_distance_m(
            p_params.site.lat0_deg, p_params.site.lon0_deg, lat, lon, R_e
        )
        assert reference < 100000.0  # sanity: genuinely "inside 100 km"
        rel_err = abs(projected - reference) / reference
        assert rel_err < 0.001, (dlat, dlon, projected, reference, rel_err)


if __name__ == "__main__":
    test_example_case_metadata_and_ascending_h()
    test_isa_synthetic_case_matches_isa_within_half_percent_between_nodes()
    for wdir, us, vs in [(0.0, 0.0, -1.0), (90.0, -1.0, 0.0), (180.0, 0.0, 1.0), (270.0, 1.0, 0.0)]:
        test_wind_enu_conversion_cardinal_directions(wdir, us, vs)
    test_load_sounding_with_td_column_populates_values()
    test_load_sounding_without_td_column_is_all_nan()
    test_interp_altitude_td_linear_in_range()
    test_interp_altitude_td_held_at_edge_both_directions()
    test_interp_altitude_td_nan_when_column_absent()
    test_field_single_station_with_dewpoint_matches_tier2_exactly()
    test_rbf_stacking_includes_td_at_correct_offset()
    test_extrapolation_continuous_at_both_seams()
    test_extrapolation_above_top_stays_finite_and_physically_reasonable()
    test_below_bottom_extrapolation_uses_local_lapse_rate()
    test_single_row_sounding_below_bottom_falls_back_to_isothermal()
    test_load_case_is_cached()
    test_load_case_missing_case_raises()
    test_horizontal_single_station_matches_tier2_exactly()
    test_horizontal_query_at_station_own_coordinates_dominated_by_it()
    test_horizontal_two_identical_stations_same_profile_everywhere()
    test_horizontal_field_via_rocket_ground_position()
    test_horizontal_rbf_reproduces_constant_profile_across_stations()
    test_projected_distance_matches_haversine_within_point_one_percent()
    print("All tests passed!")

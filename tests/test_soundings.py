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
from sim.params import Params
from sim.soundings import (
    interp_altitude,
    load_case,
)
from sim.state import State


_CASE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "soundings"
)


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
    p_params = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)
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
        p_params = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)

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


if __name__ == "__main__":
    test_example_case_metadata_and_ascending_h()
    test_isa_synthetic_case_matches_isa_within_half_percent_between_nodes()
    for wdir, us, vs in [(0.0, 0.0, -1.0), (90.0, -1.0, 0.0), (180.0, 0.0, 1.0), (270.0, 1.0, 0.0)]:
        test_wind_enu_conversion_cardinal_directions(wdir, us, vs)
    test_extrapolation_continuous_at_both_seams()
    test_extrapolation_above_top_stays_finite_and_physically_reasonable()
    test_below_bottom_extrapolation_uses_local_lapse_rate()
    test_single_row_sounding_below_bottom_falls_back_to_isothermal()
    test_load_case_is_cached()
    test_load_case_missing_case_raises()
    print("All tests passed!")

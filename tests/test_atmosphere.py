"""Reference-value tests for sim/atmosphere.py's "isa" and "sounding" tiers
(architecture.md SS14; main.tex SSModels > Atmosphere; roadmap.md Steps 12,
18).

Physics sanity checks against well-known ISA reference values, per the
project's testing philosophy -- no fixtures, no conftest.py, plain
`assert` + `math.isclose`.
"""

import math
import os

import numpy as np
import pytest

from sim.atmosphere import (
    _G_ISA,
    _R_D,
    _R_ISA,
    air_state,
    moist_density,
    sat_vapor_pressure,
    virtual_temperature,
)
from sim.gravity import altitude_msl
from sim.integrate import run_sim
from sim.params import Aero, Atmosphere, Lengths, Params, Site, Soundings, Thrust, Weight, with_solver
from sim.params import replace as params_replace
from sim.soundings import interp_altitude as soundings_interp_altitude
from sim.soundings import load_case
from sim.state import State, X, Z
from tests.datadir import SOUNDINGS_DIR as _SOUNDINGS_DIR

_P = Params(weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4))


def _y_at_altitude(h: float) -> np.ndarray:
    """State vector at altitude h above the launch point (z = -h), all
    other components zero -- only altitude matters to atmosphere.air_state.
    """
    s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def _y_at(x: float, z: float) -> np.ndarray:
    """State vector at (x, z), all other components zero -- Step 45's
    curvature-aware altitude tests need x != 0 as well as z."""
    s = State(x=x, z=z, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def _h_msl_for_geopotential(H: float) -> float:
    """Inverse of H = R_isa*h/(R_isa + h): the geometric h_msl that maps to
    a given geopotential altitude H. Needed because architecture.md SS14's
    layer table boundaries (e.g. H = 11000 m) are geopotential, while
    air_state's input is geometric h_msl -- the two differ by ~19 m at
    11 km, enough to move a geometric h_msl=11000 test point into the wrong
    layer. Used only to pin the layer table exactly in tests below.
    """
    return H * _R_ISA / (_R_ISA - H)


def test_sea_level_matches_isa_reference_values():
    """Standard ISA sea-level reference point (roadmap.md Step 12's check
    and the well-known textbook values)."""
    air = air_state(0.0, _y_at_altitude(0.0), _P)
    assert math.isclose(air.rho, 1.225, rel_tol=1e-3)
    assert math.isclose(air.p, 101325.0, rel_tol=1e-9)
    assert math.isclose(air.T, 288.15, rel_tol=1e-9)
    assert math.isclose(air.a, 340.29, rel_tol=1e-3)


def test_sea_level_sutherland_viscosity():
    """mu(288.15 K) = 1.789e-5 Pa*s (roadmap.md Step 12's check)."""
    air = air_state(0.0, _y_at_altitude(0.0), _P)
    assert math.isclose(air.mu, 1.789e-5, rel_tol=2e-3)


def test_tropopause_temperature_and_pressure():
    """At the geopotential H = 11 km (the troposphere/tropopause boundary),
    T = 216.65 K exactly (start of the isothermal layer) and
    p = 22632.06 Pa (architecture.md SS14's layer table; roadmap.md Step
    12's check). Uses the geometric h_msl that maps to H = 11000 m exactly,
    since air_state's input is geometric, not geopotential, altitude."""
    h_msl = _h_msl_for_geopotential(11000.0)
    air = air_state(0.0, _y_at_altitude(h_msl), _P)
    assert math.isclose(air.T, 216.65, rel_tol=1e-9)
    assert math.isclose(air.p, 22632.06, rel_tol=1e-4)


def test_tropopause_at_geometric_11km_shows_geopotential_correction():
    """At a *geometric* h_msl = 11000 m exactly (as opposed to geopotential
    H = 11000 m above), the geopotential correction
    (H = R_isa*h/(R_isa+h) < h) keeps H just under the 11 km boundary, so
    the point is still (barely) inside the troposphere's lapse layer and T
    is slightly above 216.65 K, not equal to it. Documents the distinction
    exercised by the two tests around it."""
    air = air_state(0.0, _y_at_altitude(11000.0), _P)
    assert air.T > 216.65
    assert math.isclose(air.T, 216.65, rel_tol=1e-3)


def test_20km_temperature_matches_layer_table():
    """T(20 km) = 216.65 K -- end of the isothermal tropopause layer, still
    the same temperature as its base (roadmap.md Step 12's check)."""
    air = air_state(0.0, _y_at_altitude(20000.0), _P)
    assert math.isclose(air.T, 216.65, rel_tol=1e-6)


def test_5000m_interpolates_within_troposphere_layer():
    """h_msl = 5000 m sits inside the troposphere's linear-lapse layer:
    T = 288.15 - 0.0065*H(5000) is within a fraction of a kelvin of the
    naive 255.65 K (the ~4 m geopotential-vs-geometric correction at this
    altitude), and rho/p/a/mu should all be strictly between their
    sea-level and tropopause values, showing the formula interpolates
    smoothly across the layer."""
    air = air_state(0.0, _y_at_altitude(5000.0), _P)
    air0 = air_state(0.0, _y_at_altitude(0.0), _P)
    air11 = air_state(0.0, _y_at_altitude(11000.0), _P)

    assert math.isclose(air.T, 255.65, rel_tol=1e-3)
    assert air11.rho < air.rho < air0.rho
    assert air11.p < air.p < air0.p
    assert air11.a < air.a < air0.a
    assert air11.mu < air.mu < air0.mu


def test_density_decreases_monotonically_with_altitude():
    """rho monotone decreasing to 80 km (roadmap.md Step 12's check),
    spanning all seven layers of the table."""
    altitudes = [0.0, 5_000.0, 11_000.0, 15_000.0, 20_000.0, 32_000.0,
                 47_000.0, 51_000.0, 71_000.0, 80_000.0]
    values = [air_state(0.0, _y_at_altitude(h), _P).rho for h in altitudes]
    assert all(a > b for a, b in zip(values, values[1:]))


# ----------------------------------------------------------------------
# Step 105 (Phase 2.17, architecture-35-paper-alignment.md SS35.4.1/SS35.4.5,
# D-105 dispersion hooks): `Atmosphere.dT_K`, a launch-day ISA temperature
# offset read only by the "isa" tier.
# ----------------------------------------------------------------------


def test_dT_K_zero_is_bit_identical_to_the_legacy_isa_tier():
    """The default (0.0) must be SKIPPED entirely, not added as 0.0 -- same
    convention as every other Step 97-115 no-op field."""
    p0 = _P
    p_zero = params_replace(_P, {"atmosphere.dT_K": 0.0})
    for h in (0.0, 1000.0, 11_000.0, 20_000.0, 50_000.0):
        y = _y_at_altitude(h)
        assert air_state(0.0, y, p_zero) == air_state(0.0, y, p0)


@pytest.mark.parametrize("h", [0.0, 2000.0, 11_000.0, 25_000.0])
@pytest.mark.parametrize("dT_K", [15.0, -10.0])
def test_dT_K_offset_lowers_or_raises_density_by_the_isa_ratio(h, dT_K):
    """A launch-day temperature offset leaves the pressure profile untouched
    (same hydrostatic/lapse-rate formula) and adds `dT_K` straight to the
    standard ISA temperature; density, being `p/(R_d*T)` at a FIXED `p`,
    then scales by the analytic ratio `T_isa / (T_isa + dT_K)` -- `rho(T +
    dT_K) = rho(T) * T / (T + dT_K)`. `dT_K = +15` (hotter) lowers density;
    `dT_K = -10` (colder) raises it."""
    p_base = _P
    p_hot = params_replace(_P, {"atmosphere.dT_K": dT_K})
    y = _y_at_altitude(h)
    base = air_state(0.0, y, p_base)
    hot = air_state(0.0, y, p_hot)

    assert math.isclose(hot.p, base.p, rel_tol=1e-12)  # pressure profile unchanged
    assert math.isclose(hot.T, base.T + dT_K, rel_tol=1e-12)
    expected_rho = base.rho * base.T / (base.T + dT_K)
    assert math.isclose(hot.rho, expected_rho, rel_tol=1e-9)
    if dT_K > 0.0:
        assert hot.rho < base.rho
    else:
        assert hot.rho > base.rho


def test_isa_ignores_gravity_model():
    """g_isa = 9.80665 is baked into the ISA formula and must not come from
    gravity.g() / p.gravity_model (architecture.md SS14, roadmap.md Step 12
    "Careful"): changing gravity_model must not change the air state."""
    h = 5000.0
    air_const = air_state(
        0.0, _y_at_altitude(h), params_replace(_P, {"gravity.model": "constant"})
    )
    air_wgs84 = air_state(
        0.0,
        _y_at_altitude(h),
        params_replace(_P, {"gravity.model": "wgs84", "site.lat0_deg": 45.5}),
    )
    assert air_const == air_wgs84


# ----------------------------------------------------------------------
# Step 45 (Phase 2.8; architecture.md SS25.4/SS25.9): h_msl now goes
# through sim.gravity.altitude_msl instead of the inlined -y[Z] + h0_m,
# curvature-aware once p.gravity_direction is non-"parallel".
# ----------------------------------------------------------------------


def test_isa_ignores_gravity_model_at_nonzero_downrange_under_curved_direction():
    """The flip side of `test_isa_ignores_gravity_model` above, newly load-
    bearing since Step 45 (architecture.md SS25.9): atmosphere.py now
    imports sim.gravity for the surface-geometry seam, so SS14's "must not
    call gravity.g()" is no longer guaranteed by the absence of an import
    at all -- this test guarantees it structurally. Sweeping
    `p.gravity_model` at a curved `gravity_direction` and x != 0 (so
    `altitude_msl` is actually doing curvature arithmetic) must still leave
    every `air_state` field exactly unchanged.
    """
    y = _y_at(10_000.0, -1000.0)
    common = {"gravity.direction": "radial", "site.lat0_deg": 50.0, "gravity.R_e": 6371000.0}
    air_const = air_state(0.0, y, params_replace(_P, {**common, "gravity.model": "constant"}))
    air_radial = air_state(0.0, y, params_replace(_P, {**common, "gravity.model": "radial"}))
    air_wgs84 = air_state(0.0, y, params_replace(_P, {**common, "gravity.model": "wgs84"}))
    assert air_const == air_radial == air_wgs84


def test_isa_constants_are_still_the_isa_standards_own_values():
    """architecture.md SS25.2/SS25.8: `_R_ISA`/`_G_ISA` are constants of the
    ISA standard's own definition and must not become curvature-aware --
    only the `h_msl` fed into the ISA formula changes with Step 45."""
    assert _R_ISA == 6356766.0
    assert _G_ISA == 9.80665


def test_isa_rho_pinned_parallel_vs_radial():
    """architecture.md SS25.7's pinned table: at (x=10km, z=-1000, R_e=
    6371000), ISA rho moves from 1.111659912 ("parallel") to 1.110803679
    ("radial") -- a -7.7023e-4 relative change, the air reading thinner at
    the true (curved) altitude than the flat reading said."""
    y = _y_at(10_000.0, -1000.0)
    p_par = params_replace(_P, {"gravity.direction": "parallel"})
    p_rad = params_replace(_P, {"gravity.direction": "radial", "gravity.R_e": 6371000.0})

    rho_par = air_state(0.0, y, p_par).rho
    rho_rad = air_state(0.0, y, p_rad).rho

    assert math.isclose(rho_par, 1.111659912, rel_tol=1e-8)
    assert math.isclose(rho_rad, 1.110803679, rel_tol=1e-8)
    assert math.isclose((rho_rad - rho_par) / rho_par, -7.7023e-4, rel_tol=1e-2)


def test_isa_rho_thermodynamically_consistent_under_curved_altitude():
    """rho == p/(R_d*T) must still hold exactly under a curved
    `gravity_direction`, not just under the flat default (architecture.md
    SS25.9)."""
    y = _y_at(10_000.0, -1000.0)
    p = params_replace(_P, {"gravity.direction": "radial", "gravity.R_e": 6371000.0})
    air = air_state(0.0, y, p)
    assert math.isclose(air.rho, air.p / (_R_D * air.T), rel_tol=1e-12)


def test_h0_m_shifts_altitude_to_msl():
    """air_state uses h_msl = p.h0_m - z (architecture.md SS15), so a
    launch site elevated above sea level sees the atmosphere's conditions
    at the corresponding higher MSL altitude even at z = 0."""
    p_high = params_replace(_P, {"site.h0_m": 5000.0})
    air_at_pad = air_state(0.0, _y_at_altitude(0.0), p_high)
    air_5000_sea = air_state(0.0, _y_at_altitude(5000.0), _P)
    assert math.isclose(air_at_pad.T, air_5000_sea.T, rel_tol=1e-9)
    assert math.isclose(air_at_pad.p, air_5000_sea.p, rel_tol=1e-9)


def test_unknown_atmosphere_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12): an unrecognised
    `atmosphere_model` string raises KeyError at the first call, from the
    module-private dispatch dict."""
    p = params_replace(_P, {"atmosphere.model": "not-a-real-model"})
    with pytest.raises(KeyError):
        air_state(0.0, _y_at_altitude(0.0), p)


# ----------------------------------------------------------------------
# Tier 2: "sounding" -- single-station real data (roadmap.md Step 18)
# ----------------------------------------------------------------------

# Same 0.5% relative tolerance Step 17 established for the loader/
# interpolator itself (tests/test_soundings.py); tier 2's atmosphere.py
# wrapper adds no further approximation on top of soundings.interp_altitude,
# so the same bound applies here.
_INTERP_TOL = 0.005

# data/motors/placeholder.csv's burn profile (see tests/test_integrate.py).
_MOTOR_CURVE = "placeholder.csv"

# A minimal "coefficients" aero setup so the atmosphere is actually
# load-bearing on the aero forces (architecture.md SS12: "constant" ignores
# the atmosphere entirely). Flight stays vertical (theta = pi/2, no wind,
# no lateral perturbation) so alpha == 0 throughout and C_N_alpha/C_m_alpha
# never actually engage -- only C_A0 (axial drag, driven by q = 0.5*rho*V^2)
# matters for these comparisons.
_AERO_KW = dict(
    model="linearized",
    S=0.005,
    d_ref=0.08,
    C_A0=0.5,
    C_N_alpha=2.0,
    C_m_alpha=-0.5,
)


def _write_isa_synthetic_case(case_dir: str, station: str = "ISA0") -> None:
    """Write a synthetic sounding CSV sampling sim.atmosphere.air_state
    (tier 1, "isa") at a handful of altitude nodes spanning 0-20 km, in the
    exact file format of architecture.md SS17 -- same technique as
    tests/test_soundings.py's helper of the same name (duplicated here
    rather than imported, per this project's "no fixtures, no
    conftest.py" testing philosophy: each test file is self-contained).
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
        air = air_state(0.0, _y_at_altitude(h), p_params)
        lines.append(f"{h},{air.p},{air.T},180,5.0")

    path = os.path.join(case_dir, f"{station}_202601010000.csv")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def test_sounding_tier_matches_isa_between_synthetic_nodes():
    """air_state(..., atmosphere_model="sounding") with an ISA-derived
    synthetic case must reproduce air_state(..., atmosphere_model="isa")
    to within the loader/interpolator's own error (roadmap.md Step 18's
    stated check), queried strictly *between* the synthetic nodes (0,
    2000, 5000, 8000, 11000, 15000, 20000 m) so the check exercises
    interpolation, not just the nodes themselves.
    """
    case = "test_atmo_isa_synthetic"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    _write_isa_synthetic_case(case_dir)

    try:
        load_case.cache_clear()
        p_isa = params_replace(_P, {"atmosphere.model": "isa"})
        p_snd = params_replace(_P, {"atmosphere.model": "sounding", "soundings.case": case})

        for h in [1000.0, 3500.0, 6500.0, 9500.0, 13000.0, 17500.0]:
            y = _y_at_altitude(h)
            want = air_state(0.0, y, p_isa)
            got = air_state(0.0, y, p_snd)

            assert math.isclose(got.rho, want.rho, rel_tol=_INTERP_TOL), h
            assert math.isclose(got.p, want.p, rel_tol=_INTERP_TOL), h
            assert math.isclose(got.T, want.T, rel_tol=_INTERP_TOL), h
            assert math.isclose(got.a, want.a, rel_tol=_INTERP_TOL), h
            assert math.isclose(got.mu, want.mu, rel_tol=_INTERP_TOL), h
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_sounding_tier_trajectory_matches_isa_within_interpolation_error():
    """A full run_sim trajectory with atmosphere_model="sounding" (ISA-
    derived synthetic case) must match the atmosphere_model="isa" run's
    apogee altitude/time and impact ("ground") time to within the same
    interpolation-error tolerance, with `aero_model="linearized"` so the
    atmosphere is actually load-bearing on drag (architecture.md SS12's
    note: "constant" ignores the atmosphere entirely, which would make
    this comparison vacuous).

    Numerically the apogee for this scenario (~140 m) sits well below the
    synthetic case's first node spacing (0-2000 m), where the loader's own
    interpolation error against ISA is <0.05% (far tighter than the 0.5%
    bound used here) -- so 0.5% leaves ample margin while still being a
    real, non-trivial check tied to Step 17's established tolerance.
    """
    case = "test_atmo_isa_synthetic_traj"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    _write_isa_synthetic_case(case_dir)

    try:
        load_case.cache_clear()
        weight = Weight(m=0.5, I=0.05)
        lengths = Lengths(l1=0.3, l2=0.4)
        thrust = Thrust(motor_curve=_MOTOR_CURVE)
        aero = Aero(**_AERO_KW)
        p_isa = Params(
            weight=weight, lengths=lengths, thrust=thrust, aero=aero,
            atmosphere=Atmosphere(model="isa"),
        )
        p_snd = Params(
            weight=weight, lengths=lengths, thrust=thrust, aero=aero,
            atmosphere=Atmosphere(model="sounding"), soundings=Soundings(case=case),
        )
        s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

        r_isa = run_sim(with_solver(p_isa, t_max=120.0), s0)
        r_snd = run_sim(with_solver(p_snd, t_max=120.0), s0)

        t_apogee_isa = r_isa.events["apogee"]
        t_apogee_snd = r_snd.events["apogee"]
        h_apogee_isa = -r_isa.raw.sol(t_apogee_isa)[Z]
        h_apogee_snd = -r_snd.raw.sol(t_apogee_snd)[Z]

        assert math.isclose(h_apogee_snd, h_apogee_isa, rel_tol=_INTERP_TOL)
        assert math.isclose(t_apogee_snd, t_apogee_isa, rel_tol=_INTERP_TOL)
        assert math.isclose(
            r_snd.events["ground"], r_isa.events["ground"], rel_tol=_INTERP_TOL
        )
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_sounding_real_example_density_lower_than_isa_at_station_elevation():
    """The real worked example (station LKPR, `data/soundings/example`,
    Step 17) has, at its own first data row (h_msl = 380 m, p = 96700 Pa,
    T = 287.3 K), a *higher* temperature than the ISA lapse-rate value at
    the same altitude (ISA: ~285.68 K) and a very slightly lower pressure
    (ISA: ~96842.8 Pa) -- i.e. this station's air, at its own elevation,
    is warmer than the standard atmosphere predicts there. Since
    rho = p/(R_d*T), a higher T together with a not-higher p makes the
    real-data density *lower* than the ISA tier's at the same h_msl
    (ideal gas law, holding p roughly fixed): this is the "physically
    sensible direction" the roadmap's check asks for, derived from this
    station's actual first-row values rather than asserted blindly.
    """
    p_isa = params_replace(_P, {"atmosphere.model": "isa", "site.h0_m": 380.0})
    p_snd = params_replace(
        _P,
        {
            "atmosphere.model": "sounding",
            "soundings.case": "example",
            "site.h0_m": 380.0,
        },
    )
    y = _y_at_altitude(0.0)  # z = 0 -> h_msl = h0_m = 380 m, the station's own row

    air_isa = air_state(0.0, y, p_isa)
    air_snd = air_state(0.0, y, p_snd)

    assert air_snd.T > air_isa.T
    assert air_snd.rho < air_isa.rho


def test_sounding_tier2_reads_the_same_h_msl_as_soundings_interp_altitude():
    """architecture.md SS25.9's tier-2 consistency check: at a curved,
    non-zero-downrange state, `_sounding_air_state`'s `h_msl` lookup is
    exactly `gravity.altitude_msl(y, p)`, and its output matches
    `soundings.interp_altitude` queried at that same `h_msl` directly --
    the check that the atmosphere tier-2 call site was actually converted,
    not merely reproducing ISA-like values by coincidence.
    """
    p = params_replace(
        _P,
        {
            "atmosphere.model": "sounding",
            "soundings.case": "example",
            "site.h0_m": 380.0,
            "gravity.direction": "radial",
            "gravity.R_e": 6371000.0,
        },
    )
    y = _y_at(10_000.0, -500.0)

    h_msl = altitude_msl(y, p)
    snd = load_case(p.soundings.case)[0]
    want = soundings_interp_altitude(snd, h_msl)

    got = air_state(0.0, y, p)

    assert math.isclose(got.p, want.p, rel_tol=1e-12)
    assert math.isclose(got.T, want.T, rel_tol=1e-12)


def test_sounding_real_example_trajectory_apogee_shifts_higher_than_isa():
    """Consequence of the density difference above: launching from the
    real station's own elevation (h0_m = 380 m matches LKPR's
    `elevation_m`, so the whole low-altitude flight stays inside the
    station's own measured data, no extrapolation involved), the less
    dense real-data air produces less axial drag throughout the flight
    than the ISA tier at the same altitudes, so apogee altitude must come
    out *higher* with the real sounding than with ISA -- the same
    "physically sensible direction" check as the density comparison
    above, carried through a full trajectory.
    """
    weight = Weight(m=0.5, I=0.05)
    lengths = Lengths(l1=0.3, l2=0.4)
    thrust = Thrust(motor_curve=_MOTOR_CURVE)
    aero = Aero(**_AERO_KW)
    site = Site(h0_m=380.0)
    p_isa = Params(
        weight=weight, lengths=lengths, thrust=thrust, aero=aero, site=site,
        atmosphere=Atmosphere(model="isa"),
    )
    p_snd = Params(
        weight=weight, lengths=lengths, thrust=thrust, aero=aero, site=site,
        atmosphere=Atmosphere(model="sounding"), soundings=Soundings(case="example"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    load_case.cache_clear()
    r_isa = run_sim(with_solver(p_isa, t_max=120.0), s0)
    r_snd = run_sim(with_solver(p_snd, t_max=120.0), s0)

    h_apogee_isa = -r_isa.raw.sol(r_isa.events["apogee"])[Z]
    h_apogee_snd = -r_snd.raw.sol(r_snd.events["apogee"])[Z]

    assert h_apogee_snd > h_apogee_isa
    # Sanity bound: the density difference at this station is ~0.7%, so
    # the apogee shift should be a small fraction of that, not a large
    # swing (rules out a sign flip elsewhere masquerading as the right
    # direction by coincidence).
    assert math.isclose(h_apogee_snd, h_apogee_isa, rel_tol=0.05)


# ----------------------------------------------------------------------
# Tier 3: "field" -- multi-station spatial interpolation (roadmap.md
# Step 20)
# ----------------------------------------------------------------------

# data/soundings/field_example/: two synthetic stations, FLDA (lat 48.0,
# lon 16.0) and FLDB (lat 48.0, lon 16.5, ~37 km due east of FLDA -- a
# purely cardinal separation, per Step 19's own risk note about diagonal
# placements degrading the tangent-plane projection). Both share the
# standard troposphere lapse rate but a different sea-level anchor:
#   FLDA: T0 = 293.15 K, p0 = 102000 Pa (warmer, higher pressure)
#   FLDB: T0 = 288.15 K, p0 = 99000 Pa  (cooler, lower pressure)
# Despite FLDA also being warmer (which alone would lower its density),
# its larger pressure offset dominates: FLDA is denser than FLDB at every
# shared altitude node (rho_A(0) = 1.212 kg/m^3 > rho_B(0) = 1.197 kg/m^3,
# and the same ordering holds up through 10 km) -- see this test module's
# docstring convention of deriving the "expected direction" from the
# stations' own real numbers rather than asserting it blindly.
_E_B_M = 37206.0  # projected FLDA->FLDB distance at lat0=48 deg, dlon=0.5 deg


def test_field_single_station_matches_sounding_tier_exactly():
    """Roadmap Step 20's first stated check: a case folder with a single
    station reproduces Step 18 ("sounding" tier) exactly, confirmed
    through the full atmosphere.air_state seam (not just at the
    soundings.py level, where Step 19 already covers this guarantee for
    interp_field itself). Reuses the existing single-station "example"
    case (LKPR) so no new data is needed for this check."""
    p_field = params_replace(
        _P,
        {
            "atmosphere.model": "field",
            "soundings.case": "example",
            "site.h0_m": 380.0,
        },
    )
    p_snd = params_replace(
        _P,
        {
            "atmosphere.model": "sounding",
            "soundings.case": "example",
            "site.h0_m": 380.0,
        },
    )

    load_case.cache_clear()
    for x, h in [(0.0, 0.0), (1000.0, 500.0), (-500.0, 2000.0), (300.0, 8000.0)]:
        y = np.zeros(6)
        y[X] = x
        y[Z] = -h
        want = air_state(0.0, y, p_snd)
        got = air_state(0.0, y, p_field)

        assert math.isclose(got.rho, want.rho, rel_tol=1e-9), h
        assert math.isclose(got.p, want.p, rel_tol=1e-9), h
        assert math.isclose(got.T, want.T, rel_tol=1e-9), h
        assert math.isclose(got.a, want.a, rel_tol=1e-9), h
        assert math.isclose(got.mu, want.mu, rel_tol=1e-9), h


def test_field_two_stations_density_monotonic_along_ground_track():
    """Roadmap Step 20's second stated check: with two stations differing
    in sea-level pressure, the sampled density varies monotonically along
    the ground track.

    `p.lat0_deg`/`lon0_deg` are set to FLDA's own coordinates (so FLDA
    sits at the tangent-plane origin, E=N=0) and `p.azimuth_deg` is left
    at its default 90 deg (East, `main.tex`/`architecture.md`'s "+x is
    East" convention), matching FLDB sitting due east of FLDA -- so
    sweeping `y[X]` from 0 to ~37 km moves the ground track from
    (near) FLDA straight to (near) FLDB, with no north-south drift.

    Since FLDA is denser than FLDB at every shared altitude (see the
    module comment above), and IDW weight shifts monotonically from FLDA
    to FLDB as `x` increases along the direct line between them, rho must
    decrease monotonically along this sweep -- not asserted blindly, but
    the direction implied by the two stations' actual numbers.
    """
    p = params_replace(
        _P,
        {
            "atmosphere.model": "field",
            "soundings.case": "field_example",
            "site.lat0_deg": 48.0,
            "site.lon0_deg": 16.0,
        },
    )
    load_case.cache_clear()

    xs = np.linspace(0.0, _E_B_M, 9)
    rhos = []
    for x in xs:
        y = np.zeros(6)
        y[X] = float(x)
        y[Z] = -1000.0  # fixed altitude, well inside both stations' data range
        rhos.append(air_state(0.0, y, p).rho)

    assert all(a > b for a, b in zip(rhos, rhos[1:])), rhos


# ----------------------------------------------------------------------
# Step 40: humid-air density -- virtual-temperature correction
# (architecture.md SS23.3; main.tex SSModels > Atmosphere > Density)
# ----------------------------------------------------------------------


def test_sat_vapor_pressure_pinned_values():
    """Magnus/Alduchov-Eskridge formula, pinned at 0 degC and 20 degC
    (architecture.md SS23.3). The ~0.2-0.4% gap to the more "textbook"
    611.2/2339 Pa reference values is the Magnus fit's own known accuracy
    -- not something to chase closer here.

    Note: the ticket's own pinned value at 20 degC (2333.4 Pa) is a
    slightly-under-rounded version of what `100*6.1094*exp(17.625*Tc/(Tc+
    243.04))` actually evaluates to at Tc=20 -- 2333.4406 Pa, verified
    independently here with `decimal` at 50-digit precision, i.e. this is
    not a floating-point artefact. 2333.4406 is used as the pinned value
    below (1e-2 abs_tol around the *exact* formula result), per this
    ticket's own instruction to trust an independently-verified
    from-scratch computation over a hand-typed reference number -- flagged
    in the handoff report rather than silently "fixed" by loosening the
    tolerance instead."""
    assert math.isclose(sat_vapor_pressure(273.15), 610.94, abs_tol=1e-2)
    assert math.isclose(sat_vapor_pressure(293.15), 2333.4406, abs_tol=1e-2)


def test_virtual_temperature_and_moist_density_pinned_reference_values():
    """Hand-derived reference values from architecture.md SS23.3, to
    1e-3 relative tolerance (these are not exact closed forms)."""
    T, Td, p_Pa = 287.3, 283.15, 96700.0
    T_v = virtual_temperature(T, Td, p_Pa)
    rho_moist = moist_density(p_Pa, T, Td)
    rho_dry = p_Pa / (_R_D * T)

    assert math.isclose(T_v - T, 1.384, rel_tol=1e-3)
    assert math.isclose(rho_moist, 1.16692, rel_tol=1e-3)
    assert math.isclose(rho_dry, 1.17254, rel_tol=1e-3)
    assert math.isclose((rho_moist - rho_dry) / rho_dry, -0.00479, abs_tol=2e-4)

    T2, Td2, p2 = 303.15, 299.15, 101325.0
    rho_moist2 = moist_density(p2, T2, Td2)
    rho_dry2 = p2 / (_R_D * T2)
    assert math.isclose((rho_moist2 - rho_dry2) / rho_dry2, -0.01252, abs_tol=2e-4)


def test_virtual_temperature_gte_and_moist_density_lte_dry_for_arbitrary_inputs():
    """For any physically valid input (Td <= T), T_v >= T always and
    rho_moist <= rho_dry always -- moist air is less dense, never denser
    (architecture.md SS23.3)."""
    cases = [
        (300.0, 300.0, 101325.0),   # saturated -- largest correction
        (250.0, 210.0, 50000.0),    # cold, dry -- correction near zero
        (310.0, 305.0, 95000.0),    # warm, humid
        (216.65, -60.0 + 273.15, 22632.06),  # tropopause-like, very dry
        (293.15, 293.15, 101325.0),  # Td == T exactly
    ]
    for T, Td, p_Pa in cases:
        T_v = virtual_temperature(T, Td, p_Pa)
        rho_dry = p_Pa / (_R_D * T)
        rho_moist = moist_density(p_Pa, T, Td)
        assert T_v >= T, (T, Td, p_Pa)
        assert rho_moist <= rho_dry, (T, Td, p_Pa)


def test_virtual_temperature_clamps_supersaturated_dewpoint():
    """Td > T is unphysical (implied supersaturation from noisy data); the
    min(Td, T) clamp makes it harmless -- same result as Td == T exactly
    (architecture.md SS23.3)."""
    T, p_Pa = 290.0, 95000.0
    assert math.isclose(
        virtual_temperature(T, 295.0, p_Pa),  # Td > T
        virtual_temperature(T, T, p_Pa),      # clamped equivalent
    )


def _write_humid_sounding(case_dir, station, h, p_vals, T_vals, Td_vals):
    """Write a sounding CSV with a Td_K column and the given per-row
    (h, p, T, Td) values (architecture.md SS23.3's file format)."""
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, f"{station}_202601010000.csv")
    lines = [
        f"# station: {station}",
        "# lat_deg: 0.0",
        "# lon_deg: 0.0",
        "# elevation_m: 0",
        "# time_utc: 2026-01-01T00:00:00Z",
        "h_msl_m,p_Pa,T_K,Td_K,wdir_deg,wspd_ms",
    ]
    for h_i, p_i, T_i, Td_i in zip(h, p_vals, T_vals, Td_vals):
        lines.append(f"{h_i},{p_i},{T_i},{Td_i},180,0.0")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def test_isa_density_unaffected_by_humid_air_flag():
    """The ISA tier is dry air by definition and must never be touched by
    `humid_air` -- `_isa_air_state` was not even modified in Step 40, so
    this is a regression guard on that invariant."""
    h = 5000.0
    air_dry = air_state(0.0, _y_at_altitude(h), params_replace(_P, {"atmosphere.humid_air": False}))
    air_humid_flag = air_state(0.0, _y_at_altitude(h), params_replace(_P, {"atmosphere.humid_air": True}))
    assert air_dry == air_humid_flag


def test_humid_air_false_is_bit_for_bit_dry_even_with_dewpoint_data_present():
    """With `humid_air=False` (the default), the sounding tier's density
    stays exactly `p/(R_d*T)` -- `moist_density` is never evaluated -- even
    when the sounding *does* have dewpoint data available. Reproduces the
    pre-Step-40 code path bit-for-bit; only `humid_air=True` engages the
    correction."""
    case = "test_humid_flag_off"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    h_nodes = [0.0, 1000.0, 2000.0]
    p_vals = [101325.0, 89900.0, 79500.0]
    T_vals = [293.15, 286.65, 280.15]
    Td_vals = [289.15, 280.65, 270.15]
    _write_humid_sounding(case_dir, "HOFF", h_nodes, p_vals, T_vals, Td_vals)

    try:
        load_case.cache_clear()
        p_off = params_replace(
            _P,
            {
                "atmosphere.model": "sounding",
                "soundings.case": case,
                "atmosphere.humid_air": False,
            },
        )
        for h in (200.0, 900.0, 1800.0):
            air = air_state(0.0, _y_at_altitude(h), p_off)
            assert math.isclose(air.rho, air.p / (_R_D * air.T), rel_tol=1e-12), h
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_humid_air_true_applies_moist_density_when_dewpoint_present():
    """With `humid_air=True` and dewpoint data present, the sounding tier's
    `rho` matches `moist_density(p, T, Td)` computed independently from the
    same (p, T, Td) triple -- and is strictly lower than the dry value."""
    case = "test_humid_flag_on"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    h_nodes = [0.0, 1000.0, 2000.0]
    p_vals = [101325.0, 89900.0, 79500.0]
    T_vals = [293.15, 286.65, 280.15]
    Td_vals = [289.15, 280.65, 270.15]
    _write_humid_sounding(case_dir, "HON", h_nodes, p_vals, T_vals, Td_vals)

    try:
        load_case.cache_clear()
        p_on = params_replace(
            _P,
            {
                "atmosphere.model": "sounding",
                "soundings.case": case,
                "atmosphere.humid_air": True,
            },
        )
        snd = load_case(case)[0]
        for h in (200.0, 900.0, 1800.0):
            air = air_state(0.0, _y_at_altitude(h), p_on)
            snd_state = soundings_interp_altitude(snd, h)
            rho_dry = air.p / (_R_D * air.T)
            expected = moist_density(air.p, air.T, snd_state.Td)

            assert math.isclose(air.rho, expected, rel_tol=1e-9), h
            assert air.rho < rho_dry, h
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_sounding_without_td_column_dry_fallback_regardless_of_humid_air_flag():
    """A sounding CSV with no Td_K column loads fine and runs correctly
    with `humid_air` either True or False -- `interp_altitude`'s Td is
    all-NaN, so `np.isfinite` gates the correction off, and `rho` stays
    dry either way (architecture.md SS23.3). Uses the real committed
    "example" case (no Td_K column)."""
    load_case.cache_clear()
    for flag in (False, True):
        p_snd = params_replace(
            _P,
            {
                "atmosphere.model": "sounding",
                "soundings.case": "example",
                "site.h0_m": 380.0,
                "atmosphere.humid_air": flag,
            },
        )
        air = air_state(0.0, _y_at_altitude(0.0), p_snd)
        assert math.isclose(air.rho, air.p / (_R_D * air.T), rel_tol=1e-12), flag


def test_field_tier_humid_air_matches_sounding_tier_single_station():
    """Same "field tier with a single station reproduces the sounding
    tier exactly" guarantee as Step 20, now exercised with `humid_air=True`
    and dewpoint data present, through the full `atmosphere.air_state`
    seam."""
    case = "test_humid_field_single"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    h_nodes = [0.0, 1000.0, 2000.0]
    p_vals = [101325.0, 89900.0, 79500.0]
    T_vals = [293.15, 286.65, 280.15]
    Td_vals = [289.15, 280.65, 270.15]
    _write_humid_sounding(case_dir, "HFS", h_nodes, p_vals, T_vals, Td_vals)

    try:
        load_case.cache_clear()
        p_field = params_replace(
            _P,
            {
                "atmosphere.model": "field",
                "soundings.case": case,
                "atmosphere.humid_air": True,
            },
        )
        p_snd = params_replace(
            _P,
            {
                "atmosphere.model": "sounding",
                "soundings.case": case,
                "atmosphere.humid_air": True,
            },
        )
        for h in (200.0, 900.0, 1800.0):
            y = _y_at_altitude(h)
            want = air_state(0.0, y, p_snd)
            got = air_state(0.0, y, p_field)
            assert math.isclose(got.rho, want.rho, rel_tol=1e-9), h
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)

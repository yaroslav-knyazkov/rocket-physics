"""Reference-value tests for sim/atmosphere.py's "isa" and "sounding" tiers
(architecture.md SS14; main.tex SSModels > Atmosphere; roadmap.md Steps 12,
18).

Physics sanity checks against well-known ISA reference values, per the
project's testing philosophy -- no fixtures, no conftest.py, plain
`assert` + `math.isclose`.
"""

import dataclasses
import math
import os

import numpy as np
import pytest

from sim.atmosphere import _R_ISA, air_state
from sim.integrate import run_sim
from sim.params import Params
from sim.soundings import load_case
from sim.state import State, X, Z

_P = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)

_SOUNDINGS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "soundings"
)


def _y_at_altitude(h: float) -> np.ndarray:
    """State vector at altitude h above the launch point (z = -h), all
    other components zero -- only altitude matters to atmosphere.air_state.
    """
    s = State(x=0.0, z=-h, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
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


def test_isa_ignores_gravity_model():
    """g_isa = 9.80665 is baked into the ISA formula and must not come from
    gravity.g() / p.gravity_model (architecture.md SS14, roadmap.md Step 12
    "Careful"): changing gravity_model must not change the air state."""
    h = 5000.0
    air_const = air_state(
        0.0, _y_at_altitude(h), dataclasses.replace(_P, gravity_model="constant")
    )
    air_wgs84 = air_state(
        0.0,
        _y_at_altitude(h),
        dataclasses.replace(_P, gravity_model="wgs84", lat0_deg=45.5),
    )
    assert air_const == air_wgs84


def test_h0_m_shifts_altitude_to_msl():
    """air_state uses h_msl = p.h0_m - z (architecture.md SS15), so a
    launch site elevated above sea level sees the atmosphere's conditions
    at the corresponding higher MSL altitude even at z = 0."""
    p_high = dataclasses.replace(_P, h0_m=5000.0)
    air_at_pad = air_state(0.0, _y_at_altitude(0.0), p_high)
    air_5000_sea = air_state(0.0, _y_at_altitude(5000.0), _P)
    assert math.isclose(air_at_pad.T, air_5000_sea.T, rel_tol=1e-9)
    assert math.isclose(air_at_pad.p, air_5000_sea.p, rel_tol=1e-9)


def test_unknown_atmosphere_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12): an unrecognised
    `atmosphere_model` string raises KeyError at the first call, from the
    module-private dispatch dict."""
    p = dataclasses.replace(_P, atmosphere_model="not-a-real-model")
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
    aero_model="coefficients",
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
        p_isa = dataclasses.replace(_P, atmosphere_model="isa")
        p_snd = dataclasses.replace(
            _P, atmosphere_model="sounding", sounding_case=case
        )

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
    interpolation-error tolerance, with `aero_model="coefficients"` so the
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
        common = dict(
            m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve=_MOTOR_CURVE, **_AERO_KW
        )
        p_isa = Params(**common, atmosphere_model="isa")
        p_snd = Params(
            **common, atmosphere_model="sounding", sounding_case=case
        )
        s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

        r_isa = run_sim(p_isa, s0, t_max=120.0)
        r_snd = run_sim(p_snd, s0, t_max=120.0)

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
    p_isa = dataclasses.replace(_P, atmosphere_model="isa", h0_m=380.0)
    p_snd = dataclasses.replace(
        _P, atmosphere_model="sounding", sounding_case="example", h0_m=380.0
    )
    y = _y_at_altitude(0.0)  # z = 0 -> h_msl = h0_m = 380 m, the station's own row

    air_isa = air_state(0.0, y, p_isa)
    air_snd = air_state(0.0, y, p_snd)

    assert air_snd.T > air_isa.T
    assert air_snd.rho < air_isa.rho


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
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve=_MOTOR_CURVE, h0_m=380.0,
        **_AERO_KW,
    )
    p_isa = Params(**common, atmosphere_model="isa")
    p_snd = Params(**common, atmosphere_model="sounding", sounding_case="example")
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    load_case.cache_clear()
    r_isa = run_sim(p_isa, s0, t_max=120.0)
    r_snd = run_sim(p_snd, s0, t_max=120.0)

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
    p_field = dataclasses.replace(
        _P, atmosphere_model="field", sounding_case="example", h0_m=380.0
    )
    p_snd = dataclasses.replace(
        _P, atmosphere_model="sounding", sounding_case="example", h0_m=380.0
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
    p = dataclasses.replace(
        _P,
        atmosphere_model="field",
        sounding_case="field_example",
        lat0_deg=48.0,
        lon0_deg=16.0,
        # azimuth_deg left at its default (90 deg, East) -- matches FLDB
        # sitting due east of FLDA.
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

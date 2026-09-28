"""Tests for sim/wind.py tier 1, "analytic" (architecture.md SS16; main.tex
SSModels > Wind; roadmap.md Step 21).

Physics sanity checks + a wiring regression, per the project's testing
philosophy -- no fixtures, no conftest.py, plain `assert` + `math.isclose`/
`numpy` comparisons.
"""

import dataclasses
import math
import os

import numpy as np
import pytest

import sim.flow as flow_mod
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Params
from sim.soundings import load_case
from sim.state import State, VX, X, Z
from sim.wind import wind_horizontal_enu, wind_inertial

_MOTOR_CURVE = "placeholder.csv"  # data/motors/placeholder.csv, see tests/test_thrust_curve.py

_SOUNDINGS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "soundings"
)


# ----------------------------------------------------------------------
# "none" (the default) reproduces the pre-Step-21 zero-wind stub exactly
# ----------------------------------------------------------------------


def test_wind_inertial_is_zero_for_the_default_model():
    """`p.wind_model` defaults to `"none"`; `wind_inertial` must return
    exactly zero for arbitrary `(t, y)` (architecture.md SS16: "the
    default; makes every Phase 1/2 result reproducible").
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)
    for t, y in [
        (0.0, np.zeros(6)),
        (5.3, np.array([12.0, -340.0, 71.0, -8.0, 0.4, -0.1])),
    ]:
        assert np.array_equal(wind_inertial(t, y, p), np.zeros(2))


def test_none_model_full_trajectory_matches_pre_wind_stub_bit_for_bit():
    """Roadmap Step 21's first stated check: `"none"` reproduces Step 20
    bit-for-bit. Verified directly against the pre-Step-21 implementation
    of `flow._wind_inertial` (an inline zeros stub, monkeypatched back in
    here) rather than a hard-coded reference trajectory -- this proves the
    Step 21 wiring change (`flow._wind_inertial` now delegating to
    `sim.wind.wind_inertial`) is behaviour-preserving for the default
    model, without needing to pin an arbitrary numeric baseline.
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve=_MOTOR_CURVE,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.5, C_N_alpha=2.0, C_m_alpha=-0.5,
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r_new = run_sim(p, s0, t_max=30.0)

    original = flow_mod._wind_inertial
    flow_mod._wind_inertial = lambda t, y, p: np.zeros(2)
    try:
        r_old = run_sim(p, s0, t_max=30.0)
    finally:
        flow_mod._wind_inertial = original

    assert np.array_equal(r_new.y, r_old.y)
    assert np.array_equal(r_new.t, r_old.t)
    assert r_new.events == r_old.events


# ----------------------------------------------------------------------
# Pure headwind raises V by exactly the wind speed
# ----------------------------------------------------------------------


def test_pure_headwind_raises_V_by_exactly_wind_speed():
    """A rocket moving purely along `+x` (vx = U, vz = 0) with a headwind
    blowing directly along `-x` (azimuth = 0 deg = North, wdir = 0 deg =
    wind from North -- a pure headwind per the cardinal-direction mapping
    below) gives a relative wind vector exactly colinear with the
    rocket's own velocity, so `V = |v_rel|` adds linearly: `V_head =
    U + W`, exactly, not just to some tolerance. The state's altitude is
    pinned to exactly `wind_ref_h_m` so `W(h) == wind_ref_ms` exactly (no
    shear correction to account for).
    """
    U = 50.0
    W = 12.0
    h_ref = 10.0
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, azimuth_deg=0.0)
    p_none = Params(**common, wind_model="none")
    p_head = Params(
        **common, wind_model="analytic", wind_dir_deg=0.0,
        wind_ref_ms=W, wind_ref_h_m=h_ref,
    )

    s = State(x=0.0, z=-h_ref, vx=U, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)

    V_none = flow_state(0.0, y, p_none).V
    V_head = flow_state(0.0, y, p_head).V

    assert math.isclose(V_none, U, rel_tol=1e-12)
    assert math.isclose(V_head, U + W, rel_tol=1e-12)
    assert math.isclose(V_head - V_none, W, rel_tol=1e-12)


# ----------------------------------------------------------------------
# Cardinal wind directions map to the expected downrange sign
# ----------------------------------------------------------------------


def test_cardinal_wind_directions_give_expected_downrange_sign():
    """Fixed `azimuth_deg = 0` (North-facing flight plane, `+x` = North).
    With meteorological `wdir` (direction the wind blows *from*) and
    `w_x = -W*cos(wdir - azimuth)` (architecture.md SS16), the four
    cardinal directions work out to:

        wdir =   0 (from North, blowing North->South) -> headwind,  w_x = -W
        wdir =  90 (from East,  blowing East->West)    -> pure crosswind, w_x == 0
        wdir = 180 (from South, blowing South->North)  -> tailwind,  w_x = +W
        wdir = 270 (from West,  blowing West->East)    -> pure crosswind, w_x == 0

    Derived directly from the formula above, not asserted blindly: at
    wdir=90/270 the wind is perpendicular to the North-facing flight
    plane, so all of it lands on the (discarded) cross-plane component.
    """
    W_ref = 12.0
    h_ref = 10.0
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, wind_model="analytic",
        azimuth_deg=0.0, wind_ref_ms=W_ref, wind_ref_h_m=h_ref,
    )
    y = np.zeros(6)
    y[Z] = -h_ref  # W(h) == W_ref exactly

    w_x_north = wind_inertial(0.0, y, Params(**common, wind_dir_deg=0.0))[0]
    w_x_east = wind_inertial(0.0, y, Params(**common, wind_dir_deg=90.0))[0]
    w_x_south = wind_inertial(0.0, y, Params(**common, wind_dir_deg=180.0))[0]
    w_x_west = wind_inertial(0.0, y, Params(**common, wind_dir_deg=270.0))[0]

    assert math.isclose(w_x_north, -W_ref, rel_tol=1e-12)  # headwind
    assert math.isclose(w_x_east, 0.0, abs_tol=1e-9)       # crosswind
    assert math.isclose(w_x_south, W_ref, rel_tol=1e-12)   # tailwind
    assert math.isclose(w_x_west, 0.0, abs_tol=1e-9)       # crosswind


# ----------------------------------------------------------------------
# Headwind / tailwind bracket the still-air apogee
# ----------------------------------------------------------------------


def test_headwind_and_tailwind_bracket_the_still_air_apogee():
    """Full trajectory runs: a headwind and a tailwind of the same speed
    must bracket the still-air ("none") apogee, in the physically correct
    order.

    `aero_model="coefficients"` with `C_N_alpha = C_m_alpha = 0` and
    `l1 = 0.0` isolates pure axial drag (`A_x = q*S*C_A0`, no normal
    force/pitching moment engaged, no moment arm for the axial force
    either) so `theta` never departs from its initial value -- this test
    is about the drag-vs-relative-airspeed effect on apogee, not about
    weathercocking dynamics (a separate, and here destabilizing for the
    coefficient combination borrowed from other test modules, concern).

    The launch is inclined (`theta0 = 1.2 rad`, not the vertical `pi/2`)
    so the rocket builds up a genuine downrange velocity `vx > 0` of its
    own during the powered ascent -- with a purely vertical launch, a
    horizontal wind is orthogonal to the dominant (vertical) velocity
    component and a headwind/tailwind of the same speed are indistinguishable
    (`|v_rel|` depends on `wx**2`, not on its sign, when `vx` is negligible).
    Only once the rocket has its own horizontal groundspeed does "wind
    against/with direction of travel" raise/lower `|v_rel|` asymmetrically.

    Physical reasoning, confirmed below rather than asserted blindly: a
    headwind (opposing the rocket's own `+x` motion) raises `|v_rel|`
    throughout the ascent, raising drag, so its apogee must be *lower*
    than the still-air case; a tailwind lowers `|v_rel|`, lowers drag, so
    its apogee must be *higher*. Ordering: h_head < h_none < h_tail.
    """
    common = dict(
        m=0.5, I=0.05, l1=0.0, l2=0.4, motor_curve=_MOTOR_CURVE,
        azimuth_deg=0.0, aero_model="coefficients",
        S=0.005, d_ref=0.08, C_A0=0.5, C_N_alpha=0.0, C_m_alpha=0.0,
    )
    theta0 = 1.2  # rad, inclined launch (not vertical) -- see docstring
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=theta0, omega=0.0)

    W = 4.0
    p_none = Params(**common, wind_model="none")
    p_head = Params(
        **common, wind_model="analytic", wind_dir_deg=0.0,
        wind_ref_ms=W, wind_ref_h_m=1.0,
    )
    p_tail = Params(
        **common, wind_model="analytic", wind_dir_deg=180.0,
        wind_ref_ms=W, wind_ref_h_m=1.0,
    )

    r_none = run_sim(p_none, s0, t_max=60.0)
    r_head = run_sim(p_head, s0, t_max=60.0)
    r_tail = run_sim(p_tail, s0, t_max=60.0)

    h_none = -r_none.raw.sol(r_none.events["apogee"])[Z]
    h_head = -r_head.raw.sol(r_head.events["apogee"])[Z]
    h_tail = -r_tail.raw.sol(r_tail.events["apogee"])[Z]

    assert h_head < h_none < h_tail


# ----------------------------------------------------------------------
# Gust determinism (the hard solve_ivp constraint, architecture.md SS16)
# ----------------------------------------------------------------------


def test_gust_is_deterministic_bit_for_bit_across_repeated_calls():
    """`solve_ivp` evaluates the RHS at arbitrary, repeated, and rejected
    times, so the gust perturbation must be a pure, repeatable function of
    `(t, p)` -- never a fresh random draw per call. Calling `wind_inertial`
    twice with identical `(t, y, p)` (including a nonzero `gust_sigma`)
    must give bit-for-bit identical results.
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4, wind_model="analytic",
        wind_ref_ms=8.0, wind_ref_h_m=10.0, gust_sigma=1.5, gust_seed=42,
    )
    y = np.zeros(6)
    y[Z] = -50.0

    w1 = wind_inertial(3.7, y, p)
    w2 = wind_inertial(3.7, y, p)
    assert np.array_equal(w1, w2)

    # A different seed still gives a deterministic (if different)
    # realization -- each seed's own results are reproducible too, not
    # just the first one tried.
    p2 = dataclasses.replace(p, gust_seed=7)
    w3 = wind_inertial(3.7, y, p2)
    w4 = wind_inertial(3.7, y, p2)
    assert np.array_equal(w3, w4)


def test_gust_sigma_zero_reproduces_no_gust_analytic_profile_exactly():
    """`gust_sigma = 0.0` (the default) must turn gusts off entirely, not
    merely make them small: the wind must exactly match the plain
    power-law-shear profile with no perturbation, regardless of
    `gust_seed` (which must never even be consulted).
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, wind_model="analytic",
        wind_ref_ms=8.0, wind_ref_h_m=10.0, wind_dir_deg=45.0,
        azimuth_deg=90.0, gust_sigma=0.0,
    )
    p_seed_a = Params(**common, gust_seed=123)
    p_seed_b = Params(**common, gust_seed=999999)

    y = np.zeros(6)
    y[Z] = -30.0

    w_a = wind_inertial(5.0, y, p_seed_a)
    w_b = wind_inertial(5.0, y, p_seed_b)
    assert np.array_equal(w_a, w_b)

    # Matches the hand-computed no-gust power-law-shear formula exactly.
    h = 30.0
    h_ref = common["wind_ref_h_m"]
    W = common["wind_ref_ms"] * (max(h, h_ref) / h_ref) ** Params(**common).wind_shear_exp
    delta = math.radians(common["wind_dir_deg"] - common["azimuth_deg"])
    expected_w_x = -W * math.cos(delta)
    assert math.isclose(w_a[0], expected_w_x, rel_tol=1e-12)


# ----------------------------------------------------------------------
# Tier 2: "sounding" -- single-station real data (roadmap.md Step 22)
# ----------------------------------------------------------------------


def _write_constant_wind_case(case_dir: str, wdir_deg: float, wspd_ms: float) -> None:
    """Write a synthetic sounding whose `wdir`/`wspd` are the *same* at
    every altitude node (0, 2000, 5000, 8000, 11000 m) -- a "no-shear,
    no-veer" profile. Since `u`/`v` are derived from `wdir`/`wspd` at load
    time (soundings.py), a constant `wdir`/`wspd` gives a constant `(u,
    v)` at every node too, so `np.interp` between any two identical
    values reproduces that exact value at any altitude *inside* the data
    range -- linear interpolation of a constant function carries no
    approximation error at all. This is what lets the test below use a
    tight tolerance instead of the loader's usual ~0.5% interpolation
    bound (architecture.md SS17/roadmap.md Step 17): there is nothing to
    interpolate away from here, only floating-point roundoff between the
    two independently-written formulas (`_analytic_wind`'s
    `-W*cos(wdir-azimuth)` vs `_sounding_wind`'s ENU dot product).

    p_Pa/T_K columns are filled with plausible-looking placeholder values
    (unused by wind.py, which only reads `u`/`v`) so the file still
    round-trips through the shared loader's full column set.
    """
    os.makedirs(case_dir, exist_ok=True)
    nodes = [0.0, 2000.0, 5000.0, 8000.0, 11000.0]
    lines = [
        "# station: WNDCONST",
        "# lat_deg: 0.0",
        "# lon_deg: 0.0",
        "# elevation_m: 0.0",
        "# time_utc: 2026-01-01T00:00:00Z",
        "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
    ]
    for h in nodes:
        p_placeholder = 101325.0 * math.exp(-h / 8000.0)
        T_placeholder = 288.15 - 0.0065 * h
        lines.append(f"{h},{p_placeholder},{T_placeholder},{wdir_deg},{wspd_ms}")
    path = os.path.join(case_dir, "WNDCONST_202601010000.csv")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def test_sounding_constant_wind_reproduces_analytic_model_with_zero_shear():
    """Roadmap Step 22's first stated check: a synthetic constant-wind
    sounding reproduces the analytic model with `wind_shear_exp = 0.0`
    and the equivalent `wind_ref_ms`/`wind_dir_deg`, at a couple of
    different altitudes -- including altitudes strictly between the
    sounding's own nodes, so the check exercises `interp_altitude`, not
    just the raw node values.

    `wind_shear_exp = 0.0` makes tier 1's `W(h)` altitude-independent
    (`(h/h_ref)**0 == 1` for any `h`), matching the sounding's own
    altitude-independent `wdir`/`wspd` -- the two tiers describe the same
    physical wind by construction, just through different native
    representations ((wdir, wspd) vs (u, v) ENU), so the module docstring's
    algebraic consistency check should make them agree here to near
    machine precision (see `_write_constant_wind_case`'s docstring for
    why no ~0.5% interpolation-error margin is needed).
    """
    wdir_deg = 205.0
    W = 9.0
    azimuth_deg = 40.0  # a non-cardinal azimuth, exercising the general formula

    case = "test_wind_sounding_constant"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    _write_constant_wind_case(case_dir, wdir_deg, W)

    try:
        load_case.cache_clear()
        common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, azimuth_deg=azimuth_deg)
        p_analytic = Params(
            **common, wind_model="analytic", wind_dir_deg=wdir_deg,
            wind_ref_ms=W, wind_ref_h_m=1.0, wind_shear_exp=0.0,
        )
        p_sounding = Params(**common, wind_model="sounding", sounding_case=case)

        for h in [0.0, 500.0, 3000.0, 7000.0, 9500.0, 11000.0]:
            y = np.zeros(6)
            y[Z] = -h

            w_analytic = wind_horizontal_enu(0.0, y, p_analytic)
            w_sounding = wind_horizontal_enu(0.0, y, p_sounding)

            assert math.isclose(w_sounding[0], w_analytic[0], rel_tol=1e-9, abs_tol=1e-9), h
            assert math.isclose(w_sounding[1], w_analytic[1], rel_tol=1e-9, abs_tol=1e-9), h
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_sounding_pure_veering_shifts_downrange_component_as_predicted():
    """A synthetic case whose `wdir` changes with altitude at *constant*
    `wspd` (0 deg at h=0, 45 deg at h=5000, 90 deg at h=10000 -- veering
    clockwise with altitude, a textbook boundary-layer effect), isolating
    the pure direction-change (veering) effect on the downrange component
    from any accompanying speed change.

    With `azimuth_deg = 0.0` (flight plane facing North), the along-plane
    formula collapses to `w_along = -W*cos(wdir)` (delta = wdir - 0):
    at wdir=0 the wind blows from due North straight down the flight
    plane (a pure headwind, w_along = -W); as it veers toward wdir=90
    (from due East, a pure crosswind in this plane) the along-plane
    projection shrinks toward zero. So `w_along` must increase
    monotonically (become less negative) with altitude here -- derived
    directly from the formula, not asserted blindly.
    """
    W = 8.0
    case = "test_wind_sounding_veer"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    os.makedirs(case_dir, exist_ok=True)
    lines = [
        "# station: WNDVEER",
        "# lat_deg: 0.0",
        "# lon_deg: 0.0",
        "# elevation_m: 0.0",
        "# time_utc: 2026-01-01T00:00:00Z",
        "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
        f"0,101325,288.15,0,{W}",
        f"5000,54048,255.65,45,{W}",
        f"10000,26436,223.15,90,{W}",
    ]
    path = os.path.join(case_dir, "WNDVEER_202601010000.csv")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    try:
        load_case.cache_clear()
        p = Params(
            m=0.5, I=0.05, l1=0.3, l2=0.4,
            wind_model="sounding", sounding_case=case, azimuth_deg=0.0,
        )

        w0 = wind_inertial(0.0, np.zeros(6), p)[0]
        y1 = np.zeros(6)
        y1[Z] = -5000.0
        w1 = wind_inertial(0.0, y1, p)[0]
        y2 = np.zeros(6)
        y2[Z] = -10000.0
        w2 = wind_inertial(0.0, y2, p)[0]

        expected0 = -W * math.cos(math.radians(0.0))
        expected1 = -W * math.cos(math.radians(45.0))
        expected2 = -W * math.cos(math.radians(90.0))

        assert math.isclose(w0, expected0, rel_tol=1e-9)
        assert math.isclose(w1, expected1, rel_tol=1e-9)
        assert math.isclose(w2, expected2, abs_tol=1e-9)

        # The predicted direction of change, confirmed against the actual
        # dispatched values, not just the hand-computed ones above.
        assert w0 < w1 < w2
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_sounding_real_example_case_veers_and_shifts_downrange_component():
    """Roadmap Step 22's second stated check, against the actual worked
    example (`data/soundings/example`, station LKPR, Step 17): its
    `wdir` genuinely varies with altitude (210 deg at h_msl=380 m up to
    265 deg at h_msl=10000 m, per the committed CSV -- not just used for
    the atmosphere tiers so far), so `wind_model="sounding"` must sample
    a different downrange wind component at these two altitudes, and by
    the amount and direction the projection formula predicts from the
    file's own (wdir, wspd) values at each row -- not merely `!=`.

    Queried exactly at the sounding's own two altitude nodes, so the
    values compared are exact table entries, not something blurred by
    `interp_altitude`'s in-range interpolation.
    """
    wdir_low, wspd_low = 210.0, 4.1      # h_msl = 380 m (first row)
    wdir_high, wspd_high = 265.0, 35.0   # h_msl = 10000 m (last row)
    azimuth_deg = 0.0

    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        wind_model="sounding", sounding_case="example", azimuth_deg=azimuth_deg,
    )

    load_case.cache_clear()
    snd = load_case("example")[0]
    assert not math.isclose(snd.h[0], snd.h[-1])
    assert wdir_low != wdir_high  # the real profile does veer, not just a wspd change

    y_low = np.zeros(6)
    y_low[Z] = -380.0
    y_high = np.zeros(6)
    y_high[Z] = -10000.0

    w_low = wind_inertial(0.0, y_low, p)[0]
    w_high = wind_inertial(0.0, y_high, p)[0]

    expected_low = -wspd_low * math.cos(math.radians(wdir_low - azimuth_deg))
    expected_high = -wspd_high * math.cos(math.radians(wdir_high - azimuth_deg))

    assert math.isclose(w_low, expected_low, rel_tol=1e-6)
    assert math.isclose(w_high, expected_high, rel_tol=1e-6)

    # The formula-derived expectation itself shows the direction the
    # veering (plus the accompanying speed increase) pushes the downrange
    # component: as wdir sweeps from 210 deg toward 270 deg (due West, a
    # pure crosswind against this North-facing flight plane) cos(wdir)
    # shrinks in magnitude fast enough to outweigh the simultaneous wspd
    # increase, so w_along must be *smaller* at the top of the profile.
    assert expected_high < expected_low
    assert w_high < w_low


def test_sounding_uses_msl_altitude_not_agl_unlike_analytic_tier():
    """Unlike tier 1's `altitude_agl`-referenced shear profile, tier 2
    reads the sounding at `h_msl = -y[Z] + p.h0_m` -- the same MSL
    convention `sim.atmosphere`'s sounding/field tiers use (architecture.md
    SS17). A nonzero `h0_m` must shift which row of the sounding is read
    at the pad (`z = 0`), exactly like `test_h0_m_shifts_altitude_to_msl`
    in tests/test_atmosphere.py.
    """
    case = "test_wind_sounding_h0"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    # A profile whose speed (hence downrange component, at azimuth=wdir=0)
    # actually varies with altitude, so h0_m computed wrongly (e.g. as
    # plain AGL like tier 1) would sample the wrong row and this check
    # would fail loudly instead of passing vacuously.
    os.makedirs(case_dir, exist_ok=True)
    lines = [
        "# station: WNDH0",
        "# lat_deg: 0.0",
        "# lon_deg: 0.0",
        "# elevation_m: 0.0",
        "# time_utc: 2026-01-01T00:00:00Z",
        "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
        "0,101325,288.15,0,4.0",
        "5000,54048,255.65,0,10.0",
    ]
    path = os.path.join(case_dir, "WNDH0_202601010000.csv")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

    try:
        load_case.cache_clear()
        p_pad = Params(
            m=0.5, I=0.05, l1=0.3, l2=0.4, azimuth_deg=0.0,
            wind_model="sounding", sounding_case=case, h0_m=5000.0,
        )
        p_direct = Params(
            m=0.5, I=0.05, l1=0.3, l2=0.4, azimuth_deg=0.0,
            wind_model="sounding", sounding_case=case, h0_m=0.0,
        )

        w_at_pad_elevated = wind_inertial(0.0, np.zeros(6), p_pad)[0]
        y_direct = np.zeros(6)
        y_direct[Z] = -5000.0
        w_direct_5000 = wind_inertial(0.0, y_direct, p_direct)[0]

        assert math.isclose(w_at_pad_elevated, w_direct_5000, rel_tol=1e-9)
        # And it must differ from the sea-level (h_msl=0) row's own value.
        w_direct_0 = wind_inertial(0.0, np.zeros(6), p_direct)[0]
        assert not math.isclose(w_at_pad_elevated, w_direct_0, rel_tol=1e-6)
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


# ----------------------------------------------------------------------
# Tier 3: "field" -- multi-station spatial interpolation (roadmap.md
# Step 23)
# ----------------------------------------------------------------------


def test_field_single_station_matches_sounding_tier_exactly():
    """Roadmap Step 23's first stated check: a case folder with a single
    station reproduces Step 22 ("sounding" tier) exactly, confirmed
    through the full `wind_inertial`/`wind_horizontal_enu` seam -- not
    just at the `soundings.interp_field` level, where Step 19's own
    "one station => tier 2 exactly" guarantee already covers this.
    Reuses the existing single-station "example" case (LKPR), same as
    `test_field_single_station_matches_sounding_tier_exactly` in
    tests/test_atmosphere.py, so no new data is needed for this check.
    """
    p_field = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        wind_model="field", sounding_case="example", azimuth_deg=0.0,
    )
    p_sounding = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        wind_model="sounding", sounding_case="example", azimuth_deg=0.0,
    )

    load_case.cache_clear()
    for t, x, h in [(0.0, 0.0, 0.0), (1.3, 1000.0, 500.0), (7.0, -500.0, 2000.0), (12.0, 300.0, 8000.0)]:
        y = np.zeros(6)
        y[X] = x
        y[Z] = -h

        want = wind_horizontal_enu(t, y, p_sounding)
        got = wind_horizontal_enu(t, y, p_field)

        assert math.isclose(got[0], want[0], rel_tol=1e-9, abs_tol=1e-9), h
        assert math.isclose(got[1], want[1], rel_tol=1e-9, abs_tol=1e-9), h
        assert np.array_equal(wind_inertial(t, y, p_field), wind_inertial(t, y, p_sounding))


def _write_opposing_stations_case(case_dir: str, lat_b_deg: float, W: float) -> None:
    """Write a synthetic two-station case, station FLDWA at (lat=0,
    lon=0) with `wdir=0` (wind from due North -- blowing due South) and
    station FLDWB at (lat=lat_b_deg, lon=0), due *North* of FLDWA, with
    `wdir=180` (wind from due South -- blowing due North): genuinely
    opposing directions, not merely a modest ~20 deg difference like
    `data/soundings/field_example/` (built for Step 20's atmosphere
    tier-3 tests).

    Both stations share the same altitude nodes and the same constant
    `wspd=W` at every node -- only `wdir` differs -- so `(u, v)` at every
    node is exactly `(0, -W)` for FLDWA and exactly `(0, +W)` for FLDWB
    (meteorological ENU conversion, `sim/soundings.py`'s docstring),
    independent of altitude.

    Cardinal (North-South) separation, not diagonal, same "keep it
    cardinal" consideration `data/soundings/field_example/` (Step
    19/20) already established for the tangent-plane projection.
    """
    os.makedirs(case_dir, exist_ok=True)
    nodes = [0.0, 5000.0, 11000.0]

    def _write(station: str, lat_deg: float, wdir_deg: float) -> None:
        lines = [
            f"# station: {station}",
            f"# lat_deg: {lat_deg}",
            "# lon_deg: 0.0",
            "# elevation_m: 0.0",
            "# time_utc: 2026-01-01T00:00:00Z",
            "h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms",
        ]
        for h in nodes:
            p_placeholder = 101325.0 * math.exp(-h / 8000.0)
            T_placeholder = 288.15 - 0.0065 * h
            lines.append(f"{h},{p_placeholder},{T_placeholder},{wdir_deg},{W}")
        path = os.path.join(case_dir, f"{station}_202601010000.csv")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    _write("FLDWA", 0.0, wdir_deg=0.0)
    _write("FLDWB", lat_b_deg, wdir_deg=180.0)


def test_field_two_opposing_stations_wind_reverses_smoothly_along_ground_track():
    """Roadmap Step 23's second stated check: with two stations of
    opposing wind direction, the wind sampled along the ground track
    reverses smoothly.

    `p.azimuth_deg = 0.0` (North-facing flight plane, `+x = North`) and
    the two stations are placed North-South of each other (FLDWA at the
    tangent-plane origin, FLDWB `D_m` due North), matching the ground
    track `(E, N) = (x*sin(A), x*cos(A)) = (0, x)` -- a straight line
    from FLDWA to FLDWB with no East-West drift, same "keep it cardinal"
    reasoning as `sim.soundings.interp_field`'s own docstring.

    With `A = 0`, `w_along = u*sin(0) + v*cos(0) = v`. FLDWA's `v = -W`
    (wdir=0, a pure headwind against the `+x`-North flight direction);
    FLDWB's `v = +W` (wdir=180, a pure tailwind) -- derived directly from
    the ENU conversion, not asserted blindly.

    Monotonicity is not asserted blindly either: IDW weight `w_A(x) =
    f(d_A^2)/(f(d_A^2)+f(d_B^2))` with `f(d^2) = 1/(d^2+eps^2)`. Along the
    straight segment between the two stations, `d_A^2 = x^2` is strictly
    increasing in `x` and `d_B^2 = (D_m - x)^2` is strictly decreasing, so
    `f(d_A^2)` is strictly decreasing and `f(d_B^2)` is strictly
    increasing; `w_A = 1/(1 + f(d_B^2)/f(d_A^2))` is therefore strictly
    decreasing in `x` (the ratio `f(d_B^2)/f(d_A^2)` is strictly
    increasing, being a ratio of an increasing over a decreasing positive
    function), and `w_B = 1 - w_A` strictly increasing. The combined
    `v = w_A*(-W) + w_B*(+W) = W*(w_B - w_A)` is then strictly increasing
    in `x` over the whole sweep -- so `w_along` must change sign exactly
    once, monotonically, not merely flip.
    """
    D_m = 20000.0  # separation [m], >> idw_epsilon_m's default 500 m
    W = 9.0

    p_probe = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)  # only for its R_e default
    lat_b_deg = math.degrees(D_m / p_probe.R_e)

    case = "test_wind_field_opposing"
    case_dir = os.path.join(_SOUNDINGS_DIR, case)
    _write_opposing_stations_case(case_dir, lat_b_deg, W)

    try:
        load_case.cache_clear()
        p = Params(
            m=0.5, I=0.05, l1=0.3, l2=0.4,
            wind_model="field", sounding_case=case, azimuth_deg=0.0,
            lat0_deg=0.0, lon0_deg=0.0,
        )

        xs = np.linspace(0.0, D_m, 11)
        w_alongs = []
        for x in xs:
            y = np.zeros(6)
            y[X] = float(x)
            y[Z] = 0.0  # pad altitude, h_msl = 0 -- exactly node 0 of both stations
            w_alongs.append(wind_inertial(0.0, y, p)[0])

        # Strictly increasing across the whole sweep (headwind -> tailwind).
        assert all(a < b for a, b in zip(w_alongs, w_alongs[1:])), w_alongs

        # Near FLDWA: dominated by its headwind (negative); near FLDWB:
        # dominated by its tailwind (positive).
        assert w_alongs[0] < 0.0
        assert w_alongs[-1] > 0.0

        # Exactly one sign change across the sweep -- no oscillation.
        signs = [w > 0.0 for w in w_alongs]
        transitions = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
        assert transitions == 1
    finally:
        load_case.cache_clear()
        for fname in os.listdir(case_dir):
            os.remove(os.path.join(case_dir, fname))
        os.rmdir(case_dir)


def test_unknown_wind_model_raises_keyerror():
    """No input validation (architecture.md SS7/SS12), same as
    atmosphere.py's and gravity.py's dispatch tables: an unrecognised
    `wind_model` string raises KeyError at the first call.
    """
    p = dataclasses.replace(Params(m=0.5, I=0.05, l1=0.3, l2=0.4), wind_model="not-a-real-model")
    with pytest.raises(KeyError):
        wind_inertial(0.0, np.zeros(6), p)


# ----------------------------------------------------------------------
# Step 45 (Phase 2.8; architecture.md SS25.4/SS25.9): tier 1's `h` and
# tiers 2/3's `h_msl` now go through sim.gravity.altitude_agl/altitude_msl
# instead of the flat `altitude_agl(y)`/inlined `-y[Z] + p.h0_m`, curvature-
# aware once p.gravity_direction is non-"parallel".
# ----------------------------------------------------------------------


def _y_at(x: float, z: float) -> np.ndarray:
    """State vector at (x, z), all other components zero."""
    s = State(x=x, z=z, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    return np.array(s)


def test_tier1_W_pinned_parallel_vs_radial():
    """architecture.md SS25.7's pinned table: at (x=10km, z=-1000,
    R_e=6371000), tier-1 shear wind speed W moves from 9.659841585
    ("parallel") to 9.670644585 ("radial") -- a *stronger* wind at the
    higher true altitude, a positive shear exponent's expected direction.
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, wind_model="analytic",
        azimuth_deg=0.0, wind_dir_deg=0.0,  # pure headwind: w_x == -W exactly
        wind_ref_ms=5.0, wind_ref_h_m=10.0, wind_shear_exp=0.143,
    )
    y = _y_at(10_000.0, -1000.0)
    p_par = Params(**common, gravity_direction="parallel")
    p_rad = Params(**common, gravity_direction="radial", R_e=6371000.0)

    W_par = -wind_inertial(0.0, y, p_par)[0]
    W_rad = -wind_inertial(0.0, y, p_rad)[0]

    assert math.isclose(W_par, 9.659841585, rel_tol=1e-8)
    assert math.isclose(W_rad, 9.670644585, rel_tol=1e-8)
    assert math.isclose((W_rad - W_par) / W_par, 1.1183e-3, rel_tol=1e-2)


def test_tier2_and_tier3_field_read_the_same_h_msl_as_atmosphere():
    """architecture.md SS25's "orthogonality consequence" applied across
    modules: wind tier 2 and atmosphere tier 2 read the *same* sounding
    file at the *same* h_msl for one state, so curving one and not the
    other would be a genuine inconsistency, not a stylistic one (SS25.4).
    Confirmed at a curved, non-zero-downrange state against the committed
    `example` case.
    """
    from sim import soundings
    from sim.gravity import altitude_msl

    p = dataclasses.replace(
        Params(m=0.5, I=0.05, l1=0.3, l2=0.4),
        wind_model="sounding", sounding_case="example",
        h0_m=380.0, gravity_direction="radial", R_e=6371000.0,
    )
    y = _y_at(10_000.0, -500.0)

    h_msl = altitude_msl(y, p)
    snd = soundings.load_case(p.sounding_case)[0]
    want = soundings.interp_altitude(snd, h_msl)

    A = math.radians(p.azimuth_deg)
    want_along = want.u * math.sin(A) + want.v * math.cos(A)

    got_along, _ = wind_horizontal_enu(0.0, y, p)

    assert math.isclose(got_along, want_along, rel_tol=1e-12)

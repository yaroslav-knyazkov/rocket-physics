"""Tests for sim/wind.py tier 1, "analytic" (architecture.md SS16; main.tex
SSModels > Wind; roadmap.md Step 21).

Physics sanity checks + a wiring regression, per the project's testing
philosophy -- no fixtures, no conftest.py, plain `assert` + `math.isclose`/
`numpy` comparisons.
"""

import dataclasses
import math

import numpy as np

import sim.flow as flow_mod
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Params
from sim.state import State, VX, X, Z
from sim.wind import wind_inertial

_MOTOR_CURVE = "placeholder.csv"  # data/motors/placeholder.csv, see tests/test_thrust_curve.py


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

"""Cross-check that RK4 (sim/integrate.py's `method="rk4"`) and RK45
(`method="RK45"`, the default) agree on the flight of the same scenario
(roadmap.md Step 8).

This is the test that proves sim/dynamics.py is genuinely solver-agnostic:
both paths call `derivatives(t, y, p)` with no special-casing, and only
differ in how they step through time. It is a physics/numerics sanity
check, not a unit test of a single function -- per the project's testing
philosophy, no fixtures, no conftest.py, plain `assert` + `math.isclose`.

Step 36 (roadmap.md; main.tex SSModels > Mass and moment of inertia) adds
the variable-mass tests below: `state.m`/`params.m_d` on/off gate,
`dm/dt = -T_ref(t)/(I_sp*g0)` reaching the dry mass at burnout, and the
two-lumped-mass `l_B(t)`/`I(t)` model (parallel-axis theorem). See
sim/dynamics.py's module docstring for the one deliberate scope decision
made here: `p.l1`/`p.l2` (the CoP-to-CoG and CoP-to-thrust moment arms)
are *not* made functions of `l_B(t)` by this step -- main.tex's Mass and
moment of inertia section gives no formula for that, and architecture.md
SS19 flags it as a still-open question. `I(t)`'s own parallel-axis terms
already depend on `l_B(t)`, which is what the tests below exercise.
"""

import math

import numpy as np

from sim.dynamics import _cog_position, _moment_of_inertia, _propellant_mass, derivatives
from sim.integrate import run_sim
from sim.params import Params
from sim.state import M, THETA, State, Z


def test_rk4_agrees_with_rk45_on_apogee_and_impact():
    """Same scenario as run.py's placeholder: the placeholder motor curve
    (Step 14) plus a constant axial drag, vertical launch from rest.

    Note (Step 14): this used to set `T=50.0` (Phase 1's constant-thrust
    magnitude). `motor_curve` now fully owns thrust (`forces.thrust_body`
    no longer reads `p.T` at all -- see sim/thrust_curve.py), so a `T=...`
    value alone would silently mean *zero* thrust for the whole flight,
    not "a different thrust profile". That degenerate scenario also makes
    this specific cross-check impractically slow: with nothing to
    overcome gravity, the flight runs the full default `t_max` and RK4's
    fixed dt=1e-4 grid turns into millions of steps in a pure-Python loop.
    Using the real placeholder curve keeps both the physics and the
    runtime representative of an actual flight.

    Tolerance rationale: RK4 here has no event location, only a fixed dt
    grid refined by linear interpolation across the one step that
    straddles each event (see `_run_rk4`'s docstring) -- so its event
    times and apogee altitude are grid-resolution-limited, not exact.
    Measured directly (this scenario, dt=1e-4 s): apogee time differs by
    ~3.2e-5 s, impact time by ~5.9e-5 s, apogee altitude by ~8.7e-3 m from
    RK45's values. The tolerances below (1e-3 s, 5e-2 m) sit comfortably
    above those measured differences while still being tight enough that
    an actual dynamics.py bug (a sign error, a missing term) -- which
    would show up as a difference many orders of magnitude larger, not a
    grid-resolution artifact -- would fail this test.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv", A_x=0.5, A_z=0.0, A_m=0.0)
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    rk45 = run_sim(p, s0, method="RK45")
    rk4 = run_sim(p, s0, method="rk4", dt=1e-4)

    apogee_rk45 = rk45.events["apogee"]
    apogee_rk4 = rk4.events["apogee"]
    impact_rk45 = rk45.events["ground"]
    impact_rk4 = rk4.events["ground"]

    assert apogee_rk45 is not None and apogee_rk4 is not None
    assert impact_rk45 is not None and impact_rk4 is not None

    alt_rk45 = -rk45.raw.sol(apogee_rk45)[Z]
    alt_rk4 = -rk4.raw.sol(apogee_rk4)[Z]

    assert math.isclose(apogee_rk4, apogee_rk45, abs_tol=1e-3)
    assert math.isclose(impact_rk4, impact_rk45, abs_tol=1e-3)
    assert math.isclose(alt_rk4, alt_rk45, abs_tol=5e-2)


# ---------------------------------------------------------------------
# Step 36: variable mass -- CoG and moment-of-inertia travel
# ---------------------------------------------------------------------

# data/motors/placeholder.csv's own header comment: "total impulse:
# 162.75 N*s" -- used below to pick an initial propellant mass that
# consumes itself exactly (to numerical-integration tolerance) over the
# curve's whole burn, so "final m == m_d" is a real check, not a fudge.
_PLACEHOLDER_IMPULSE_NS = 162.75
_ISP_S = 200.0          # s, placeholder specific impulse
_G0 = 9.80665            # m/s^2, matches Params.g's default (read as g0)
_M_D = 0.4               # kg, dry (burnout) mass
_M_P0 = _PLACEHOLDER_IMPULSE_NS / (_ISP_S * _G0)  # kg, initial propellant mass
_M0 = _M_D + _M_P0        # kg, initial (wet) mass


def test_mass_model_off_reproduces_fixed_mass_bit_for_bit():
    """`p.m_d = None` (the default) -- the on/off gate -- must reproduce
    the pre-Step-36 fixed-`p.m`/`p.I` physics exactly, regardless of what
    `state.m` (the now-added 7th component, unused on this path) happens
    to hold. Two states differing *only* in `m` (0.0, State's own default,
    vs. a deliberately wrong 999.0) must give bit-for-bit identical
    derivatives.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv", A_x=0.5)
    s_default_m = State(x=0.0, z=0.0, vx=0.0, vz=-10.0, theta=math.pi / 2, omega=0.1)
    s_garbage_m = State(x=0.0, z=0.0, vx=0.0, vz=-10.0, theta=math.pi / 2, omega=0.1, m=999.0)

    dydt_default = derivatives(0.5, np.array(s_default_m), p)
    dydt_garbage = derivatives(0.5, np.array(s_garbage_m), p)

    assert np.array_equal(dydt_default, dydt_garbage)


def test_mass_reaches_dry_mass_at_burnout():
    """Check text, first clause: integrating `dm/dt = -T_ref(t)/(I_sp*g0)`
    over the placeholder curve's whole burn (total impulse 162.75 N*s,
    burnout at t=2.0 s) must bring `m` down to `m_d` -- `_M_P0` above is
    exactly the propellant mass that curve's impulse consumes.
    """
    p = Params(
        m=_M0, I=0.05, l1=0.3, l2=0.4,
        motor_curve="placeholder.csv",
        m_d=_M_D, l_d=0.3, l_p=0.3, I_d=0.05, I_sp=_ISP_S,
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=_M0)

    result = run_sim(p, s0, t_max=2.5)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    m_at_burnout = result.raw.sol(t_burnout)[M]
    m_at_end = result.raw.sol(2.5)[M]

    assert math.isclose(m_at_burnout, p.m_d, abs_tol=1e-3)
    # dm/dt == 0 once T_ref == 0 (thrust_curve.thrust returns 0 past the
    # curve's last point) -- mass must stay pinned at m_d, not drift.
    assert math.isclose(m_at_end, p.m_d, abs_tol=1e-3)


def test_cog_position_stays_at_l_d_when_l_p_equals_l_d():
    """models.tex's l_B(t) = (m_d*l_d + m_p*l_p)/(m_d+m_p): when l_p == l_d
    every term shares the same centroid, so l_B(t) == l_d identically for
    every m_p, and I(t)'s parallel-axis terms vanish -- "no CoG shift",
    the regression check's own phrase.
    """
    p = Params(m=_M0, I=0.05, l1=0.3, l2=0.4, m_d=_M_D, l_d=0.3, l_p=0.3, I_d=0.05, I_sp=_ISP_S)

    for m in (p.m, 0.6, 0.5, p.m_d + 0.01, p.m_d):
        m_p = _propellant_mass(m, p)
        l_B = _cog_position(m_p, p)
        assert math.isclose(l_B, p.l_d, rel_tol=1e-12, abs_tol=1e-12)

        I = _moment_of_inertia(m_p, l_B, p)
        expected_I = p.I_d + (p.I_d / p.m_d) * m_p  # I_p(t) only, zero parallel-axis term
        assert math.isclose(I, expected_I, rel_tol=1e-12)


def test_cog_shifts_and_inertia_grows_when_l_p_differs_from_l_d():
    """With a real offset (l_p != l_d) the CoG sits strictly between l_d
    and l_p (mass-weighted average) whenever propellant remains, and the
    parallel-axis terms make I(t) strictly larger than the "no CoG shift"
    case at the same mass -- isolating the effect of l_B(t) != l_d that
    the regression check asks for.
    """
    p = Params(m=_M0, I=0.05, l1=0.3, l2=0.4, m_d=_M_D, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=_ISP_S)
    m_p_wet = p.m - p.m_d
    assert m_p_wet > 0.0

    l_B = _cog_position(m_p_wet, p)
    assert p.l_d < l_B < p.l_p

    I_shifted = _moment_of_inertia(m_p_wet, l_B, p)
    I_noshift = p.I_d + (p.I_d / p.m_d) * m_p_wet  # what Step 36 gives when l_p == l_d
    assert I_shifted > I_noshift


def test_real_cog_offset_changes_pitch_trajectory():
    """Trajectory-level version of the isolation check above: same burn,
    same constant aero pitching moment (A_m, so the moment equation's only
    time-dependence is `I(t)` itself), only `l_p` differs. `l_p == l_d`
    ("no CoG shift") must give a different `theta(t)` than a real offset
    `l_p != l_d`, since `I(t)` -- and therefore `domega/dt = M_y/I(t)` --
    differs between the two runs (main.tex SSModels > Mass and moment of
    inertia; `p.l1`/`p.l2` are unchanged in both runs -- see this file's
    module docstring).
    """
    common = dict(
        m=_M0, I=0.05, l1=0.3, l2=0.4,
        motor_curve="placeholder.csv",
        m_d=_M_D, I_d=0.05, I_sp=_ISP_S,
        A_m=0.05,  # constant pitching moment -- the only moment source here
    )
    p_noshift = Params(l_d=0.3, l_p=0.3, **common)
    p_shift = Params(l_d=0.3, l_p=0.5, **common)
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=_M0)

    r_noshift = run_sim(p_noshift, s0, t_max=2.5)
    r_shift = run_sim(p_shift, s0, t_max=2.5)

    theta_noshift = r_noshift.raw.sol(2.0)[THETA]
    theta_shift = r_shift.raw.sol(2.0)[THETA]

    assert not math.isclose(theta_noshift, theta_shift, rel_tol=1e-6, abs_tol=1e-6)

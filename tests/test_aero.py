"""Tests for sim/aero.py -- table-driven C_A/C_N/C_m and CoP-travel l1
(architecture.md SS19; roadmap.md Step 25).

Physics/algebra sanity checks only, per the project's testing philosophy
-- no fixtures, no conftest.py, plain `assert` + `math.isclose`/
`numpy.allclose` (see tests/test_forces.py, tests/test_thrust_curve.py).
"""

import math
import os

import numpy as np

from sim import aero
from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Params
from sim.state import OMEGA, State


# ----------------------------------------------------------------------
# Table lookup itself
# ----------------------------------------------------------------------


def test_table_lookup_interpolates_alpha_within_bracketed_M():
    """np.interp in alpha within each bracketing M row, then a linear
    blend across the M bracket (architecture.md SS19: "np.interp in
    alpha inside a bracketing interpolation in M"). Cross-checked here
    with an independent hand computation of the same bilinear formula
    from the raw values in data/aero/example.csv, not by calling
    aero.py's own internals.

    Table rows (data/aero/example.csv), alpha in {-10, 0, 10} deg:
      M=0.5: C_A=[0.35, 0.30, 0.35], C_N=[-0.5236, 0, 0.5236], l1=0.28
      M=1.0: C_A=[0.60, 0.55, 0.60], C_N=[-0.6981, 0, 0.6981], l1=0.35
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, aero_table="example.csv")
    alpha = math.radians(5.0)  # exactly halfway between the 0/10 deg columns
    M = 0.75                   # exactly halfway between the M=0.5/1.0 rows

    C_A_at_M05 = (0.30 + 0.35) / 2   # alpha=5deg, M=0.5 row
    C_A_at_M10 = (0.55 + 0.60) / 2   # alpha=5deg, M=1.0 row
    C_N_at_M05 = (0.0 + 0.5236) / 2
    C_N_at_M10 = (0.0 + 0.6981) / 2
    l1_at_M05 = 0.28
    l1_at_M10 = 0.35

    expected_C_A = (C_A_at_M05 + C_A_at_M10) / 2
    expected_C_N = (C_N_at_M05 + C_N_at_M10) / 2
    expected_l1 = (l1_at_M05 + l1_at_M10) / 2

    assert math.isclose(aero.C_A(alpha, M, p), expected_C_A, rel_tol=1e-9)
    assert math.isclose(aero.C_N(alpha, M, p), expected_C_N, rel_tol=1e-9)
    assert math.isclose(aero.cop_l1(alpha, M, p), expected_l1, rel_tol=1e-9)


def test_table_lookup_exact_grid_point():
    """At an exact (alpha, M) grid point, the lookup returns the raw
    table value with no interpolation error at all."""
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, aero_table="example.csv")
    alpha = math.radians(10.0)
    M = 1.0

    assert aero.C_A(alpha, M, p) == 0.60
    assert aero.C_N(alpha, M, p) == 0.6981
    assert aero.C_m(alpha, M, p) == -0.1396
    assert aero.cop_l1(alpha, M, p) == 0.35


def test_table_clamps_at_M_grid_edges_no_extrapolation():
    """Outside the table's M range, the result holds the nearest edge
    row's value -- this project's established "hold the edge value, no
    extrapolation" convention (thrust_curve.py holds the pre-ignition/
    post-burnout value; soundings.py holds wind constant outside its
    altitude range)."""
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, aero_table="example.csv")
    alpha = 0.0

    assert aero.cop_l1(alpha, 0.1, p) == 0.28  # below M=0.5 -> clamped low
    assert aero.cop_l1(alpha, 0.5, p) == 0.28  # exactly at the low edge
    assert aero.cop_l1(alpha, 5.0, p) == 0.32  # above M=2.0 -> clamped high
    assert aero.cop_l1(alpha, 2.0, p) == 0.32  # exactly at the high edge


def test_table_rejects_non_rectangular_grid():
    """The loader requires every M value to repeat the exact same set of
    alpha_deg values (a full rectangular grid) -- architecture.md SS20's
    "no input validation beyond a clear error" philosophy: a malformed
    table raises ValueError with the offending file name, not a silent
    misinterpretation.
    """
    bad_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "aero", "test_bad_grid.csv"
    )
    with open(bad_path, "w") as f:
        f.write("# malformed: M=1.0 is missing the alpha=10 row\n")
        f.write("alpha_deg,M,C_A,C_N,C_m,l1_m\n")
        f.write("-10,0.5,0.35,-0.5236,0.0873,0.28\n")
        f.write("0,0.5,0.30,0.0,0.0,0.28\n")
        f.write("10,0.5,0.35,0.5236,-0.0873,0.28\n")
        f.write("-10,1.0,0.60,-0.6981,0.1396,0.35\n")
        f.write("0,1.0,0.55,0.0,0.0,0.35\n")

    try:
        p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, aero_table="test_bad_grid.csv")
        try:
            aero.C_A(0.0, 0.5, p)
            assert False, "expected ValueError for a non-rectangular table"
        except ValueError:
            pass
    finally:
        aero._load_table.cache_clear()
        if os.path.exists(bad_path):
            os.remove(bad_path)


# ----------------------------------------------------------------------
# Constant-fallback regression: no table configured
# ----------------------------------------------------------------------


def test_no_table_reproduces_pre_step25_coefficients_exactly():
    """Params field discipline (architecture.md SS20: every new field's
    default reproduces the previous step exactly): with `p.aero_table ==
    ""` (the default), aero.py's C_A/C_N/C_m/cop_l1 reduce to exactly
    the pre-Step-25 `forces.py` "coefficients" formulas, and
    `dynamics.derivatives()`'s aA uses exactly the constant `p.l1` --
    bit-for-bit the same `dydt` as before this step existed.
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.1, C_N_alpha=2.0, C_m_alpha=-0.3,
    )
    alpha_probe, M_probe = 0.12, 0.9

    assert aero.C_A(alpha_probe, M_probe, p) == p.C_A0
    assert aero.C_N(alpha_probe, M_probe, p) == p.C_N_alpha * alpha_probe
    assert aero.C_m(alpha_probe, M_probe, p) == p.C_m_alpha * alpha_probe
    assert aero.cop_l1(alpha_probe, M_probe, p) == p.l1

    s = State(x=0.0, z=0.0, vx=0.0, vz=-60.0, theta=math.pi / 2 - 0.1, omega=0.3)
    y = np.array(s)
    dydt = derivatives(0.0, y, p)

    # Manually reconstruct dynamics.derivatives()'s pre-Step-25 aA
    # (constant p.l1) and forces.py's pre-Step-25 A_x/A_z/A_m formulas,
    # and confirm identical dydt[OMEGA].
    flow = flow_state(0.0, y, p)
    A_x = flow.q * p.S * p.C_A0
    A_z = flow.q * p.S * p.C_N_alpha * flow.alpha
    A_m = flow.q * p.S * p.d_ref * p.C_m_alpha * flow.alpha
    aA = np.array([-p.l1, 0.0])
    aero_force = -A_x * flow.u_hat - A_z * flow.n_hat

    def _cross_y(a, b):
        return -(a[0] * b[1] - a[1] * b[0])

    M_aero = _cross_y(aA, aero_force)
    M_moment = -A_m
    expected_omega_dot = (M_aero + M_moment) / p.I  # p.T == 0.0: no thrust term

    assert math.isclose(dydt[OMEGA], expected_omega_dot, rel_tol=1e-12, abs_tol=1e-12)


# ----------------------------------------------------------------------
# CoP travel actually reaches dynamics.py's moment equation
# ----------------------------------------------------------------------


def test_cop_travel_moment_uses_table_l1_not_constant_pl1():
    """architecture.md SS19's "CoP travel makes l1 a function of (alpha,
    M), which couples straight back into the moment": with a table
    configured, dynamics.derivatives()'s aA must use
    aero.cop_l1(alpha, M, p) -- here the table's exact M=1.0, alpha=10deg
    row, l1=0.35 m -- not the Params constant p.l1, deliberately set to
    an unmistakably different 999.0 m so a stale read could not be
    missed.

    alpha and M are driven to exact table grid values (alpha=10deg via
    a vz-only launch with theta offset by exactly alpha, main.tex's
    "alpha = theta - pi/2" identity used throughout tests/test_forces.py;
    M=1.0 via V0 = the ISA sea-level speed of sound exactly) so the
    coefficient lookups have zero interpolation error, isolating the
    l1-wiring check from any table-interpolation error.
    """
    p = Params(
        m=0.5, I=0.05, l1=999.0, l2=0.4,
        aero_model="coefficients", S=0.02, d_ref=0.08,
        aero_table="example.csv",
    )
    alpha0 = math.radians(10.0)
    theta0 = math.pi / 2 + alpha0

    from sim import atmosphere

    y_rest = np.array(State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=theta0, omega=0.0))
    a0 = atmosphere.air_state(0.0, y_rest, p).a
    V0 = a0  # M = V0 / a0 = 1.0 exactly

    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-V0, theta=theta0, omega=0.0)
    y0 = np.array(s0)

    flow = flow_state(0.0, y0, p)
    assert math.isclose(flow.alpha, alpha0, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(flow.M, 1.0, rel_tol=0, abs_tol=1e-9)

    # Confirm the probe lands exactly on the table's grid point used below.
    C_A = aero.C_A(flow.alpha, flow.M, p)
    C_N = aero.C_N(flow.alpha, flow.M, p)
    C_m = aero.C_m(flow.alpha, flow.M, p)
    l1_table = aero.cop_l1(flow.alpha, flow.M, p)
    assert math.isclose(C_A, 0.60, rel_tol=1e-9)
    assert math.isclose(C_N, 0.6981, rel_tol=1e-9)
    assert math.isclose(C_m, -0.1396, rel_tol=1e-9)
    assert math.isclose(l1_table, 0.35, rel_tol=1e-9)

    dydt = derivatives(0.0, y0, p)

    # Closed-form re-derivation (tests/test_forces.py's _cross_y algebra,
    # generalised to nonzero alpha): with aA = (-l1, 0) and
    # aero_force_body = -A_x*u_hat - A_z*n_hat, u_hat=(cos a, sin a),
    # n_hat=(-sin a, cos a):
    #   _cross_y(aA, aero_force) = -l1*(A_x*sin(a) + A_z*cos(a))
    # No thrust (p.T defaults to 0.0, no motor_curve), so M_thrust = 0;
    # M_moment = aero_moment_y = -A_m.
    q = flow.q
    A_x = q * p.S * C_A
    A_z = q * p.S * C_N
    A_m = q * p.S * p.d_ref * C_m
    expected_M_y = -l1_table * (A_x * math.sin(alpha0) + A_z * math.cos(alpha0)) - A_m

    assert math.isclose(dydt[OMEGA] * p.I, expected_M_y, rel_tol=1e-9)

    # And decisively NOT the constant p.l1 = 999.0 (l1_table/p.l1 ~ 2.8e-4
    # -- if dynamics.py had stayed on the constant, M_y would be off by
    # nearly 4 orders of magnitude).
    wrong_M_y = -p.l1 * (A_x * math.sin(alpha0) + A_z * math.cos(alpha0)) - A_m
    assert not math.isclose(dydt[OMEGA] * p.I, wrong_M_y, rel_tol=1e-2)


# ----------------------------------------------------------------------
# Full-trajectory weathercocking check with the real table wired in
# ----------------------------------------------------------------------


def test_offaxis_alpha_stays_bounded_with_table_driven_coefficients():
    """Extends tests/test_forces.py's
    test_offaxis_alpha_stays_bounded_with_corrected_sign_but_diverges_with_old_sign
    (same off-axis perturbation, same corrected sign) to the real
    Step-25 machinery: aero_model="coefficients" with a real
    `aero_table`, so C_A/C_N/C_m *and* the CoP-travel l1(alpha, M) all
    flow through sim/aero.py's table lookup on every RHS call, not the
    Params constants.

    Honesty check, verified numerically (not assumed) before writing
    this assertion, per this step's explicit instruction not to claim
    decay this model cannot produce: this model still has no pitch-rate
    damping term (neither C_N/C_m nor the new l1(alpha, M) table act on
    omega, only on alpha) -- table-driven coefficients do not add
    damping just by being nonlinear/Mach-dependent. Sampled directly at
    t in {0, 1, 2, 3, 4, 5} s (same scenario as test_forces.py's V0=60
    m/s, alpha0=-0.15 rad, pre-apogee window): alpha(t) is
    [-0.150, -0.0998, 0.0548, 0.0433, -0.0930, -0.0636] rad -- bounded
    (never exceeding the initial 0.15 rad magnitude) and oscillatory
    (sign-flipping, non-monotonic), exactly the same "restoring, not
    growing" character as the sign-fix commit's own finding, not literal
    decay to zero.
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        aero_table="example.csv",
    )
    alpha0 = -0.15
    theta0 = math.pi / 2 + alpha0
    V0 = 60.0
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-V0, theta=theta0, omega=0.0)

    r = run_sim(p, s0, t_max=5.0, method="RK45")
    assert r.events["apogee"] is None  # confirms t_max=5.0 stays pre-apogee

    sample_times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    alphas = []
    for t in sample_times:
        y = r.raw.sol(t)
        alphas.append(flow_state(t, y, p).alpha)

    assert math.isclose(alphas[0], alpha0, abs_tol=1e-9)
    for a in alphas:
        assert abs(a) <= 0.16, alphas  # bounded, comfortably >= the initial 0.15
    # Not monotonically diverging away from the trim condition.
    assert abs(alphas[-1]) <= 2.0 * abs(alpha0), alphas

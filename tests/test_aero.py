"""Tests for sim/aero.py -- table-driven C_A/C_N/C_m and CoP-travel l1
(architecture.md SS19; roadmap.md Step 25).

Physics/algebra sanity checks only, per the project's testing philosophy
-- no fixtures, no conftest.py, plain `assert` + `math.isclose`/
`numpy.allclose` (see tests/test_forces.py, tests/test_thrust_curve.py).
"""

import math
import os

import numpy as np

from apps.sim.engine import aero
from apps.sim.engine.dynamics import derivatives
from apps.sim.engine.flow import flow_state
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Aero, Lengths, Params, Thrust, Weight, with_solver
from apps.sim.engine.state import OMEGA, State
from tests.datadir import AERO_DIR


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
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="table", table="example.csv"),
    )
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
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="table", table="example.csv"),
    )
    alpha = math.radians(10.0)
    M = 1.0

    assert aero.C_A(alpha, M, p) == 0.60
    assert aero.C_N(alpha, M, p) == 0.6981
    assert aero.C_m_code(alpha, M, p) == -0.1396
    assert aero.cop_l1(alpha, M, p) == 0.35


def test_table_clamps_at_M_grid_edges_no_extrapolation():
    """Outside the table's M range, the result holds the nearest edge
    row's value -- this project's established "hold the edge value, no
    extrapolation" convention (thrust_curve.py holds the pre-ignition/
    post-burnout value; soundings.py holds wind constant outside its
    altitude range)."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="table", table="example.csv"),
    )
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
    bad_path = os.path.join(AERO_DIR, "test_bad_grid.csv")
    with open(bad_path, "w") as f:
        f.write("# malformed: M=1.0 is missing the alpha=10 row\n")
        f.write("alpha_deg,M,C_A,C_N,C_m,l1_m\n")
        f.write("-10,0.5,0.35,-0.5236,0.0873,0.28\n")
        f.write("0,0.5,0.30,0.0,0.0,0.28\n")
        f.write("10,0.5,0.35,0.5236,-0.0873,0.28\n")
        f.write("-10,1.0,0.60,-0.6981,0.1396,0.35\n")
        f.write("0,1.0,0.55,0.0,0.0,0.35\n")

    try:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            aero=Aero(model="table", table="test_bad_grid.csv"),
        )
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
    the current `forces.py` "coefficients" formulas, and
    `dynamics.derivatives()`'s aA uses exactly the constant `p.l1` --
    bit-for-bit the same `dydt` as computed by hand here.

    C_N/C_m use `sin(alpha)`, not raw `alpha`, since Phase 2.5 Step 35
    (aero.py's module docstring: smoothing the branch-cut discontinuity at
    `alpha = +-pi`) -- this test's own probe `alpha_probe = 0.12` is
    comfortably in the small-angle range where the two are almost
    indistinguishable, but the assertions below use `sin` explicitly so
    they stay exact rather than merely "close".
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.1, C_N_alpha=2.0, C_m_alpha=-0.3),
    )
    alpha_probe, M_probe = 0.12, 0.9

    assert aero.C_A(alpha_probe, M_probe, p) == p.aero.C_A0
    assert aero.C_N(alpha_probe, M_probe, p) == p.aero.C_N_alpha * math.sin(alpha_probe)
    assert aero.C_m_code(alpha_probe, M_probe, p) == p.aero.C_m_alpha * math.sin(alpha_probe)
    assert aero.cop_l1(alpha_probe, M_probe, p) == p.lengths.l1

    s = State(x=0.0, z=0.0, vx=0.0, vz=-60.0, theta=math.pi / 2 - 0.1, omega=0.3)
    y = np.array(s)
    dydt = derivatives(0.0, y, p)

    # Manually reconstruct dynamics.derivatives()'s aA (constant p.lengths.l1)
    # and forces.py's current A_x/A_z/A_m formulas, and confirm identical
    # dydt[OMEGA].
    flow = flow_state(0.0, y, p)
    A_x = flow.q * p.aero.S * p.aero.C_A0
    A_z = flow.q * p.aero.S * p.aero.C_N_alpha * math.sin(flow.alpha)
    A_m = flow.q * p.aero.S * p.aero.d_ref * p.aero.C_m_alpha * math.sin(flow.alpha)
    aA = np.array([-p.lengths.l1, 0.0])
    # Body axis, not wind axis (Step 35, Phase 2.5) -- see forces.py's
    # aero_force_body docstring.
    aero_force = np.array([-A_x, -A_z])

    def _cross_y(a, b):
        return -(a[0] * b[1] - a[1] * b[0])

    M_aero = _cross_y(aA, aero_force)
    M_moment = -A_m
    expected_omega_dot = (M_aero + M_moment) / p.weight.I  # p.T == 0.0: no thrust term

    assert math.isclose(dydt[OMEGA], expected_omega_dot, rel_tol=1e-12, abs_tol=1e-12)


# ----------------------------------------------------------------------
# CoP travel actually reaches dynamics.py's moment equation
# ----------------------------------------------------------------------


def test_cop_travel_moment_uses_table_l1_not_constant_pl1():
    """architecture.md SS19's "CoP travel makes l1 a function of (alpha,
    M), which couples straight back into the moment": with `model="table"`,
    dynamics.derivatives()'s aA must use the table's l1 (via
    aero.coefficients(...).l1) -- here the table's exact M=1.0,
    alpha=10deg row, l1=0.35 m -- not the Params constant p.l1,
    deliberately set to an unmistakably different 999.0 m so a stale read
    could not be missed.

    Step 55 (architecture-28-rewrite.md SS28.5): this scenario used to set
    `model="coefficients"` (today's "linearized") *together with* a table,
    relying on the pre-Step-55 leak where `p.aero.table` being set drove
    `C_A`/`C_N`/`C_m`/`cop_l1` regardless of `model` (F2) -- that leak is
    exactly what this step closes, so the test now says what it actually
    means: `model="table"`.

    alpha and M are driven to exact table grid values (alpha=10deg via
    a vz-only launch with theta offset by exactly alpha, main.tex's
    "alpha = theta - pi/2" identity used throughout tests/test_forces.py;
    M=1.0 via V0 = the ISA sea-level speed of sound exactly) so the
    coefficient lookups have zero interpolation error, isolating the
    l1-wiring check from any table-interpolation error.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=999.0, l2=0.4),
        aero=Aero(model="table", S=0.02, d_ref=0.08, table="example.csv"),
    )
    alpha0 = math.radians(10.0)
    theta0 = math.pi / 2 + alpha0

    from apps.sim.engine import atmosphere

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
    C_m = aero.C_m_code(flow.alpha, flow.M, p)
    l1_table = aero.cop_l1(flow.alpha, flow.M, p)
    assert math.isclose(C_A, 0.60, rel_tol=1e-9)
    assert math.isclose(C_N, 0.6981, rel_tol=1e-9)
    assert math.isclose(C_m, -0.1396, rel_tol=1e-9)
    assert math.isclose(l1_table, 0.35, rel_tol=1e-9)

    dydt = derivatives(0.0, y0, p)

    # Closed-form re-derivation (tests/test_forces.py's _cross_y algebra):
    # with aA = (-l1, 0) and aero_force_body = (-A_x, -A_z) in body axis,
    # unconditionally (Step 35, Phase 2.5 -- no more u_hat/n_hat rotation):
    #   _cross_y(aA, aero_force) = -l1*A_z
    # exactly, for every alpha -- the same closed form
    # tests/test_forces.py::test_moment_matches_closed_form_minus_l1_Az_minus_Am
    # uses for the constant-model case, now also exact here at nonzero
    # alpha. No thrust (p.T defaults to 0.0, no motor_curve), so
    # M_thrust = 0; M_moment = aero_moment_y = -A_m.
    q = flow.q
    A_z = q * p.aero.S * C_N
    A_m = q * p.aero.S * p.aero.d_ref * C_m
    expected_M_y = -l1_table * A_z - A_m

    assert math.isclose(dydt[OMEGA] * p.weight.I, expected_M_y, rel_tol=1e-9)

    # And decisively NOT the constant p.lengths.l1 = 999.0 (l1_table/p.l1 ~
    # 2.8e-4 -- if dynamics.py had stayed on the constant, M_y would be off
    # by nearly 4 orders of magnitude).
    wrong_M_y = -p.lengths.l1 * A_z - A_m
    assert not math.isclose(dydt[OMEGA] * p.weight.I, wrong_M_y, rel_tol=1e-2)


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

    Re-verified numerically (not assumed) after Step 35 (Phase 2.5) put
    the aero force back in body axis instead of the relative-wind frame:
    the previous trace pinned here relied in part on `sin(alpha)*A_x`
    leaking into the moment through the old `u_hat`/`n_hat` rotation --
    a real, if small, phantom restoring contribution from the *axial*
    (drag) coefficient, which has no business affecting the pitching
    moment when `aA` has no z-component. With that leak gone, the
    scenario's apogee moves to ~5.03 s (was ~6.1 s in
    tests/test_forces.py's simpler, C_A0=0 scenario, where A_x is exactly
    zero and this leak never applied), so the sampling window is pulled
    in to `t_max=4.5` to keep the same safe margin before the apogee/
    near-zero-V singularity that test_forces.py's own docstring already
    flags and tests/test_flow.py's `test_alpha_near_pi_on_tail_first_descent`
    separately covers -- not a new failure mode, just closer to this
    scenario's own apogee than before.

    Honesty check, verified numerically before writing this assertion,
    per this step's explicit instruction not to claim decay this model
    cannot produce: this model still has no pitch-rate damping term
    (neither C_N/C_m nor the l1(alpha, M) table act on omega, only on
    alpha) -- table-driven coefficients do not add damping just by being
    nonlinear/Mach-dependent. Sampled at t in {0, 0.8, 1.6, 2.4, 3.2, 4.0} s
    (V0=60 m/s, alpha0=-0.15 rad, pre-apogee window): alpha(t) is
    [-0.1500, +0.1193, +0.0418, +0.0877, -0.0247, +0.0916] rad -- bounded
    (never exceeding the initial 0.15 rad magnitude) and oscillatory
    (sign-flipping, non-monotonic) -- restoring, not growing.

    Step 55 (architecture-28-rewrite.md SS28.5): `model="table"`, not the
    pre-Step-55 `model="coefficients"` + a table together -- same F2-leak
    correction as `test_cop_travel_moment_uses_table_l1_not_constant_pl1`
    above.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="table", S=0.005, d_ref=0.08, table="example.csv"),
    )
    alpha0 = -0.15
    theta0 = math.pi / 2 + alpha0
    V0 = 60.0
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-V0, theta=theta0, omega=0.0)

    r = run_sim(with_solver(p, t_max=4.5), s0)
    assert r.events["apogee"] is None  # confirms t_max=4.5 stays pre-apogee

    sample_times = [0.0, 0.8, 1.6, 2.4, 3.2, 4.0]
    alphas = []
    for t in sample_times:
        y = r.raw.sol(t)
        alphas.append(flow_state(t, y, p).alpha)

    assert math.isclose(alphas[0], alpha0, abs_tol=1e-9)
    for a in alphas:
        assert abs(a) <= 0.16, alphas  # bounded, comfortably >= the initial 0.15
    # Not monotonically diverging away from the trim condition.
    assert abs(alphas[-1]) <= 2.0 * abs(alpha0), alphas


# ----------------------------------------------------------------------
# Step 44: pitch-damping C_mq scaffold (architecture.md SS24.4) -- the
# optional `c_mq` column, one seam past `C_m`'s own dispatch pattern.
# ----------------------------------------------------------------------


def test_C_mq_no_table_returns_constant_regardless_of_alpha_M():
    """No table configured (`p.aero_table == ""`, the default): `C_mq`
    returns the constant `p.c_mq` unconditionally, ignoring `alpha`/`M`
    entirely -- same fallback shape as `C_A`/`C_N`/`C_m`/`cop_l1`.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(c_mq=12.5),
    )
    for alpha, M in [(0.0, 0.5), (0.3, 1.0), (-0.2, 2.5)]:
        assert aero.C_mq_code(alpha, M, p) == 12.5


def test_C_mq_table_without_column_falls_back_to_params_constant():
    """`data/aero/example.csv` predates Step 44 and has no `c_mq` column:
    `_load_table` must set `_AeroTable.C_mq_code` to `None` for it, and
    `aero.C_mq_code` must then fall back to `p.c_mq` (not to a literal `0.0`) --
    architecture.md SS24.4's deliberate exception to "table wins
    completely". Set `p.c_mq` to an unmistakable nonzero value so a stray
    `0.0` fallback could not be missed.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="table", table="example.csv", c_mq=7.0),
    )

    table = aero._load_table("example.csv")
    assert table.C_mq_code is None

    for alpha, M in [(0.0, 0.5), (math.radians(10.0), 1.0), (0.05, 2.0)]:
        assert aero.C_mq_code(alpha, M, p) == 7.0


def test_C_mq_table_with_column_interpolates_like_C_m_and_ignores_params_constant():
    """With a `c_mq` column present, `C_mq` interpolates it exactly like
    `C_m` does (bracket-and-clamp in `M`, `np.interp` in `alpha`) and
    ignores `p.c_mq` entirely -- checked both at an exact grid point (no
    interpolation error) and at a bracketed, interpolated point, against
    `p.c_mq` set to a deliberately wrong sentinel value.
    """
    test_path = os.path.join(AERO_DIR, "test_c_mq_table.csv")
    with open(test_path, "w") as f:
        f.write("# test fixture: same grid as example.csv, plus a c_mq column\n")
        f.write("alpha_deg,M,C_A,C_N,C_m,l1_m,c_mq\n")
        f.write("-10,0.5,0.35,-0.5236,0.0873,0.28,10.0\n")
        f.write("0,0.5,0.30,0.0,0.0,0.28,20.0\n")
        f.write("10,0.5,0.35,0.5236,-0.0873,0.28,30.0\n")
        f.write("-10,1.0,0.60,-0.6981,0.1396,0.35,40.0\n")
        f.write("0,1.0,0.55,0.0,0.0,0.35,50.0\n")
        f.write("10,1.0,0.60,0.6981,-0.1396,0.35,60.0\n")

    try:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            aero=Aero(model="table", table="test_c_mq_table.csv", c_mq=-999.0),
        )

        table = aero._load_table("test_c_mq_table.csv")
        assert table.C_mq_code is not None

        # Exact grid point: alpha=0deg, M=1.0 -> c_mq = 50.0, no interpolation.
        assert aero.C_mq_code(0.0, 1.0, p) == 50.0

        # Bracketed/interpolated point: alpha=5deg (halfway 0/10deg), M=0.75
        # (halfway 0.5/1.0) -- same bilinear blend test_table_lookup_
        # interpolates_alpha_within_bracketed_M uses for C_A/C_N/l1 above.
        alpha = math.radians(5.0)
        M = 0.75
        c_mq_at_M05 = (20.0 + 30.0) / 2  # alpha=5deg, M=0.5 row
        c_mq_at_M10 = (50.0 + 60.0) / 2  # alpha=5deg, M=1.0 row
        expected = (c_mq_at_M05 + c_mq_at_M10) / 2
        assert math.isclose(aero.C_mq_code(alpha, M, p), expected, rel_tol=1e-9)

        # Decisively not the Params sentinel -- confirms the table, not
        # p.aero.c_mq, is what answered both queries above.
        assert aero.C_mq_code(0.0, 1.0, p) != p.aero.c_mq
    finally:
        aero._load_table.cache_clear()
        if os.path.exists(test_path):
            os.remove(test_path)


def test_pitch_damping_default_reproduces_derivatives_bit_for_bit_with_and_without_table():
    """`c_mq = 0.0` (the default), no column: every prior `derivatives()`
    result bit-for-bit, including with a table configured (architecture.md
    SS24.4's "Checks for the step").

    Step 55 (architecture-28-rewrite.md SS28.5): the two cases below used
    to both say `model="coefficients"`, relying on the pre-Step-55 leak
    where `p.aero.table` being set drove the table path regardless of
    `model` (F2). With `model` now the sole selector, "no table" is
    `model="linearized"` and "table configured" is `model="table"` --
    the underlying C_A0/C_N_alpha/C_m_alpha fallback values are unused in
    the table case (the table itself supplies C_A/C_N/C_m/l1), kept here
    only because `Aero` is a single frozen dataclass shared between both
    branches via `aero_common`.
    """
    weight = Weight(m=0.5, I=0.05)
    lengths = Lengths(l1=0.3, l2=0.4)
    thrust = Thrust(motor_curve="placeholder.csv")
    aero_common = dict(
        S=0.005, d_ref=0.08,
        C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3,
    )
    s = State(x=10.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.05)
    y = np.array(s)
    t = 0.5

    for extra in ({"model": "linearized"}, {"model": "table", "table": "example.csv"}):
        p_implicit = Params(
            weight=weight, lengths=lengths, thrust=thrust,
            aero=Aero(**aero_common, **extra),
        )
        p_explicit = Params(
            weight=weight, lengths=lengths, thrust=thrust,
            aero=Aero(c_mq=0.0, **aero_common, **extra),
        )
        assert np.array_equal(derivatives(t, y, p_implicit), derivatives(t, y, p_explicit))


# ----------------------------------------------------------------------
# Step 55 (architecture-28-rewrite.md SS28.5): the unified AeroCoeffs
# dispatch seam itself -- aero.coefficients()/_AERO_MODELS, and the
# project's "unknown model string raises KeyError" convention (SS12/SS20)
# now applying to p.aero.model too.
# ----------------------------------------------------------------------


def test_coefficients_bundle_matches_the_five_thin_wrappers():
    """`aero.coefficients(t, y, p, flow)` must return exactly the same
    five values the thin per-coefficient wrappers (`C_A`/`C_N`/`C_m`/
    `C_mq`/`cop_l1`) give individually -- the whole point of D-7 keeping
    both: one dispatch, two ways to read it.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.1, C_N_alpha=2.0, C_m_alpha=-0.3, c_mq=1.5),
    )
    s = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.05)
    y = np.array(s)
    t = 0.5
    flow = flow_state(t, y, p)

    c = aero.coefficients(t, y, p, flow)
    assert c.C_x == aero.C_A(flow.alpha, flow.M, p)
    assert c.C_z == aero.C_N(flow.alpha, flow.M, p)
    assert c.C_m_code == aero.C_m_code(flow.alpha, flow.M, p)
    assert c.C_mq_code == aero.C_mq_code(flow.alpha, flow.M, p)
    assert c.l1 == aero.cop_l1(flow.alpha, flow.M, p)


def test_unknown_aero_model_raises_keyerror_not_valueerror():
    """architecture.md SS12's established convention ("unknown strings
    raise KeyError at the first call -- no input validation"), now
    applying to `p.aero.model` too (Step 55, architecture-28-rewrite.md
    SS28.5.1, consequence 2) -- matching `gravity_model="linear"`'s
    removal at Step 34, not a new `ValueError` branch.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="coefficients"),  # the old, now-removed model name
    )
    s = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.05)

    try:
        derivatives(0.5, np.array(s), p)
        assert False, "expected KeyError for an unknown aero.model string"
    except KeyError:
        pass


# ----------------------------------------------------------------------
# Step 57 (architecture-28-rewrite.md SS28.6): the control-coefficient
# seam, applied inside `coefficients` itself. No controller is written
# here -- see tests/test_control.py for the test-only dummy variant that
# proves a delta reaches the four downstream consumers; this module only
# proves the default ("none") is the identity.
# ----------------------------------------------------------------------


def test_coefficients_is_identity_for_the_default_control_model():
    """`p.control.aero_coeff_model` defaults to `"none"`, and
    `control._no_aero_delta` returns `base` unchanged -- not a
    reconstructed copy. `aero.coefficients(...)` must therefore return
    the *same object* the base model itself produced: `is`-identity, the
    stronger-than-equality check architecture-28-rewrite.md SS28.6 calls
    out as legitimate here specifically because this one variant is a
    pass-through, not a computation that merely happens to produce an
    equal value.

    `_AERO_MODELS["linearized"]` is monkeypatched (save original,
    substitute, restore in `finally` -- same precedent as
    tests/test_wind.py's `flow_mod._wind_inertial` swap) to return one
    fixed sentinel `AeroCoeffs` object, so this isolates the control
    hook's own pass-through behaviour from whatever the base model
    actually computes: two independent calls to even a perfectly pure
    base-model function would return two separate (merely equal, not
    identical) `AeroCoeffs` instances, which `is` would wrongly fail.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.1, C_N_alpha=2.0, C_m_alpha=-0.3, c_mq=1.5),
    )
    s = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.05)
    y = np.array(s)
    t = 0.5
    flow = flow_state(t, y, p)

    sentinel = aero.AeroCoeffs(C_x=0.1, C_z=0.2, C_m_code=0.3, C_mq_code=0.4, l1=0.5)
    original = aero._AERO_MODELS["linearized"]
    aero._AERO_MODELS["linearized"] = lambda alpha, M, p: sentinel
    try:
        assert aero.coefficients(t, y, p, flow) is sentinel
    finally:
        aero._AERO_MODELS["linearized"] = original


# ----------------------------------------------------------------------
# Step 93 (Phase 2.16, D-91..D-93), reshaped Step 118 (D-127): the axial
# coefficient follows the flow direction -- f(alpha) = clip(r*|r|, -1, 1)
# with r = cos(alpha)/cos(85 deg) (cos^2-shaped outside the 85 deg plateau,
# exactly 1.0 for |alpha| <= 85 deg).
# ----------------------------------------------------------------------


def test_axial_flow_factor_is_one_inside_85_deg_exactly():
    for deg in (0.0, 10.0, -30.0, 80.0, 85.0, -85.0):
        assert aero.axial_flow_factor(math.radians(deg)) == 1.0


def test_axial_flow_factor_zero_at_90_and_minus_one_beyond_95():
    assert abs(aero.axial_flow_factor(math.pi / 2)) < 1e-12
    assert abs(aero.axial_flow_factor(-math.pi / 2)) < 1e-12
    for deg in (95.0, -95.0, 120.0, 180.0, -180.0):
        assert aero.axial_flow_factor(math.radians(deg)) == -1.0


def test_axial_flow_factor_is_continuous_across_the_ramp():
    """Step 118 (D-127): the cos^2-shaped transition's slope at the 85/95 deg
    edges is exactly double the old linear ramp's (d(r^2)/dalpha = 2*r*dr/dalpha,
    r=1 at the edge) -- empirically ~22.86/rad vs. ~11.43/rad, so this test's
    tolerance doubles too (3e-3 -> 6e-3, same ~1.5x safety margin over the
    theoretical per-step bound, ~3.99e-3, that the old tolerance used over its
    own ~1.99e-3 bound)."""
    prev = aero.axial_flow_factor(math.radians(84.0))
    for deg in np.linspace(84.0, 96.0, 1201)[1:]:
        cur = aero.axial_flow_factor(math.radians(deg))
        assert abs(cur - prev) < 6e-3  # slope <= 23/rad * 0.01 deg step
        prev = cur


def _tail_first_params(**aero_kw):
    return Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(S=0.005, d_ref=0.08, **aero_kw),
    )


def test_constant_and_linearized_axial_coefficient_flips_tail_first():
    pc = _tail_first_params(model="constant", C_x=0.75)
    pl = _tail_first_params(model="linearized", C_A0=0.6)
    assert aero.C_A(math.pi, 0.3, pc) == -0.75
    assert aero.C_A(0.0, 0.3, pc) == 0.75
    assert aero.C_A(math.pi, 0.3, pl) == -0.6
    assert aero.C_A(0.0, 0.3, pl) == 0.6


def test_example_table_axial_coefficient_flips_at_180_deg():
    p = _tail_first_params(model="table", table="example.csv")
    nose = aero.C_A(0.0, 0.5, p)
    # example.csv spans +-10 deg, so np.interp clamps at 180 deg to the edge value.
    tail = aero.C_A(math.pi, 0.5, p)
    edge = aero.C_A(math.radians(10.0), 0.5, p)
    assert nose > 0.0
    assert tail == -edge


def test_full_range_table_is_authoritative_and_not_flipped():
    test_path = os.path.join(AERO_DIR, "test_full_range_table.csv")
    with open(test_path, "w") as f:
        f.write("# test fixture: alpha grid reaches reversed flow\n")
        f.write("alpha_deg,M,C_A,C_N,C_m,l1_m\n")
        for a, ca in ((-180, -0.4), (0, 0.3), (180, -0.4)):
            f.write(f"{a},0.5,{ca},0.0,0.0,0.28\n")
            f.write(f"{a},1.0,{ca},0.0,0.0,0.35\n")
    try:
        p = _tail_first_params(model="table", table="test_full_range_table.csv")
        assert aero.C_A(math.pi, 0.5, p) == -0.4  # table value, no second flip
        assert aero.C_A(0.0, 0.5, p) == 0.3
    finally:
        aero._load_table.cache_clear()
        if os.path.exists(test_path):
            os.remove(test_path)

"""Tests for the static-margin diagnostics in sim/report.py (Step 99,
architecture-35 SS35.4.3)."""

import contextlib
import math
import os
import warnings

import numpy as np
import pytest

from apps.sim.engine import aero
from apps.sim.engine.integrate import run_sim, run_sim_3d
from apps.sim.engine.params import Aero, Lengths, Params, Solver, Thrust, Weight, with_solver
from apps.sim.engine.report import (
    _CM_SLOPE_STEP,
    flight_summary,
    flight_summary_3d,
    stability_check,
    static_margin_cal,
)
from apps.sim.engine.quaternion import from_euler
from apps.sim.engine.state import State
from apps.sim.engine.state3d import State3D, to_vector as to_vector_3d
from tests.datadir import AERO_DIR as _AERO_DIR


@contextlib.contextmanager
def _flipped_copy(src, dst, convention):
    """Copy a v2 table, replacing its declared `# cm_convention:` line."""
    with open(os.path.join(_AERO_DIR, src)) as f:
        lines = [ln for ln in f if not ln.lstrip("#").strip().startswith("cm_convention")]
    path = os.path.join(_AERO_DIR, dst)
    with open(path, "w") as f:
        f.write(f"# cm_convention: {convention}\n")
        f.writelines(lines)
    aero._load_table.cache_clear()
    try:
        yield dst
    finally:
        aero._load_table.cache_clear()
        os.remove(path)


def _params(table):
    return Params(
        weight=Weight(m=2.0, I=0.1, m_d=1.5, l_d=0.8, l_p=1.3, I_d=0.08, I_sp=200.0),
        lengths=Lengths(l2=0.4),
        aero=Aero(model="table", S=0.01, d_ref=0.1, table=table),
        solver=Solver(method="rk4", dt=0.01, t_max=2.0),
    )


def _run(p):
    s0 = State(x=0.0, z=0.0, vx=3.0, vz=-150.0, theta=math.pi / 2 - 0.1, omega=0.0, m=2.0)
    return run_sim(p, s0)


def test_static_margin_series_matches_cg_travel():
    p = _params("example_v2.csv")
    r = _run(p)
    t, margin = static_margin_cal(r, p, np.linspace(0.0, 1.0, 5))
    assert margin.shape == t.shape
    assert np.all(np.isfinite(margin))
    assert np.all(margin > 0.0)
    # Step 116 (D-125): the derived-CP arm (l1 corrected by the local C_m/C_N slope ratio),
    # divided by d_ref -- cross-check the first point against the same formula computed
    # independently via aero's own per-coefficient slope helpers (not a hand-typed literal:
    # the correction term is new with this step, see sim/report.py S116.3).
    from apps.sim.engine import mass
    from apps.sim.engine.flow import flow_state
    y0 = r.raw.sol(0.0)
    l_g0 = mass.cog_position(mass.propellant_mass(y0[6], p), p)
    flow0 = flow_state(0.0, y0, p)
    step = _CM_SLOPE_STEP
    dcm = (aero.C_m_code(flow0.alpha + step, flow0.M, p) - aero.C_m_code(flow0.alpha - step, flow0.M, p)) / (2 * step)
    dcz = (aero.C_N(flow0.alpha + step, flow0.M, p) - aero.C_N(flow0.alpha - step, flow0.M, p)) / (2 * step)
    expected = (1.18 - l_g0) / 0.1 - dcm / dcz
    assert margin[0] == pytest.approx(expected, rel=1e-6)


def test_stable_table_reports_no_warning():
    p = _params("example_v2.csv")
    r = _run(p)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = stability_check(r, p)
    assert out["stable"] is True
    assert out["min_cm_slope"] > 0.0


def test_flipping_declared_convention_reports_instability():
    with _flipped_copy("example_v2.csv", "test_v2_flipped.csv", "code") as name:
        # Step 116 (D-125): a thinner margin than _params()'s default geometry -- needed so a
        # wrongly-declared cm_convention actually flips the *combined* stability criterion, not
        # just the standalone cm_slope. At the default geometry (l_d=0.8, l_p=1.3) this table's
        # ample margin term dominates the C_m contribution regardless of its sign (verified
        # numerically: combined stays at a constant -0.715, still "stable" under the unified
        # criterion even with the wrong convention declared) -- this geometry is deliberately
        # thinned so the flip crosses zero (verified: -0.065 declared correctly vs +0.035
        # declared wrong).
        p = Params(
            weight=Weight(m=2.0, I=0.1, m_d=1.5, l_d=1.05, l_p=1.55, I_d=0.08, I_sp=200.0),
            lengths=Lengths(l2=0.4),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name),
            solver=Solver(method="rk4", dt=0.01, t_max=2.0),
        )
        r = _run(p)
        with pytest.warns(UserWarning, match="unstable"):
            out = stability_check(r, p)
        assert out["stable"] is False
        assert out["min_cm_slope"] < 0.0


def test_negative_geometric_margin_warns():
    # CP ahead of the CG (l_p_m < l_g): negative margin
    with _flipped_copy("example_v2.csv", "test_v2_fwdcp.csv", "standard") as name:
        p = _params(name)
        p = Params(
            weight=Weight(m=2.0, I=0.1, m_d=1.5, l_d=1.6, l_p=1.7, I_d=0.08, I_sp=200.0),
            lengths=p.lengths, aero=p.aero, solver=p.solver,
        )
        r = _run(p)
        with pytest.warns(UserWarning, match="margin"):
            out = stability_check(r, p)
        assert out["min_margin_cal"] < 0.0


# ----------------------------------------------------------------------
# Step 32 (Phase 3; architecture-37-step32-3d-integration-harness.md
# SS37.3/D-32.3, option O2): `flight_summary_3d` -- additive, routes
# every state read through `forces3d._s2d` (the same projection
# `run_sim_3d`'s own events/Mach diagnostic use). `flight_summary` itself
# (the 2D function above) is unedited.
# ----------------------------------------------------------------------

_P32 = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
)
_THETA0_32 = math.radians(45.0)


def test_flight_summary_3d_matches_flight_summary_on_a_planar_run():
    """`flight_summary_3d` must agree with the 2D `flight_summary` on the
    same planar scenario -- both read the same physics through the same
    `_s2d` projection run_sim_3d's own harness already uses. Tight solver
    tolerance (same `rtol=1e-11, atol=1e-13` precedent as
    `tests/test_integrate3d.py`'s own equivalence tests) -- at the
    DEFAULT solver tolerance the two independent adaptive-step grids
    land on slightly different dense-output polynomials near apogee
    (measured directly: ~2.7e-6 relative, just over a naive 1e-6
    tolerance), a numerical-integration artifact, not a `flight_summary_3d`
    bug."""
    tight_p = with_solver(_P32, rtol=1e-11, atol=1e-13)
    s0_2d = State(x=0.0, z=0.0, vx=10.0, vz=-5.0, theta=_THETA0_32, omega=0.0)
    result_2d = run_sim(tight_p, s0_2d)
    summary_2d = flight_summary(result_2d, tight_p)

    q0 = from_euler(0.0, _THETA0_32, 0.0)
    s0_3d = State3D(r=np.zeros(3), v=np.array([10.0, 0.0, -5.0]), q=q0, omega=np.zeros(3))
    y0_3d = to_vector_3d(s0_3d)
    result_3d = run_sim_3d(tight_p, y0_3d)
    summary_3d = flight_summary_3d(result_3d, tight_p)

    assert math.isclose(summary_3d["apogee_altitude"], summary_2d["apogee_altitude"], rel_tol=1e-6)
    assert math.isclose(summary_3d["apogee_time"], summary_2d["apogee_time"], rel_tol=1e-6)
    assert math.isclose(summary_3d["impact_time"], summary_2d["impact_time"], rel_tol=1e-6)
    assert math.isclose(summary_3d["max_q"], summary_2d["max_q"], rel_tol=1e-6)


def test_flight_summary_3d_apogee_altitude_equals_helper_directly():
    """The 3D analogue of `test_flight_summary_apogee_altitude_equals_
    helper_directly` (tests/test_plotting.py): `flight_summary_3d`'s
    `apogee_altitude` equals `altitude_agl(forces3d._s2d(sol(t_apogee)), p)`
    exactly -- the same projection, called directly."""
    from apps.sim.engine import forces3d
    from apps.sim.engine.gravity import altitude_agl

    q0 = from_euler(0.0, _THETA0_32, 0.0)
    s0_3d = State3D(r=np.zeros(3), v=np.array([10.0, 0.0, -5.0]), q=q0, omega=np.zeros(3))
    y0_3d = to_vector_3d(s0_3d)
    result_3d = run_sim_3d(_P32, y0_3d)
    summary_3d = flight_summary_3d(result_3d, _P32)

    t_apogee = result_3d.events["apogee"]
    expected = altitude_agl(forces3d._s2d(result_3d.raw.sol(t_apogee)), _P32)
    assert summary_3d["apogee_altitude"] == expected

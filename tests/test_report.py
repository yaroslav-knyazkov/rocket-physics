"""Tests for the static-margin diagnostics in sim/report.py (Step 99,
architecture-35 SS35.4.3)."""

import contextlib
import math
import os
import warnings

import numpy as np
import pytest

from sim import aero
from sim.integrate import run_sim
from sim.params import Aero, Lengths, Params, Solver, Weight
from sim.report import _CM_SLOPE_STEP, stability_check, static_margin_cal
from sim.state import State

_AERO_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "aero")


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
    from sim import mass
    from sim.flow import flow_state
    y0 = r.raw.sol(0.0)
    l_g0 = mass.cog_position(mass.propellant_mass(y0[6], p), p)
    flow0 = flow_state(0.0, y0, p)
    step = _CM_SLOPE_STEP
    dcm = (aero.C_m(flow0.alpha + step, flow0.M, p) - aero.C_m(flow0.alpha - step, flow0.M, p)) / (2 * step)
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

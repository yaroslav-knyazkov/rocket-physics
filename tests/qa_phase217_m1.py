"""QA reproducers for Phase 2.17 M1 (Steps 97, 98, 99, 100, 112); report:
dev/docs/qa-report-2.17-m1.md.

Not collected by a bare `pytest` (name does not match `test_*.py`); run explicitly:
`python -m pytest tests/qa_phase217_m1.py -q`.

`xfail(strict=True)` marks a reproducer of an open defect: it flips to a failure
(XPASS) once the defect is fixed, which is the cue to drop the marker.
"""

import contextlib
import dataclasses
import math
import os
import warnings

import numpy as np
import pytest

from configs.scenarios.demo import SCENARIO as DEMO
from configs.schema import assemble
from sim import aero, thrust_curve
from sim.dynamics import derivatives
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.state import M, State

_AERO_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "aero")
_HDR = "alpha_deg,M,C_A,C_N,C_m,l_p_m\n"
_BODY = "-10,0.5,0.35,-0.5,0.1,1.0\n0,0.5,0.3,0.0,0.0,1.0\n10,0.5,0.35,0.5,-0.1,1.0\n"


@contextlib.contextmanager
def _table(name, text):
    path = os.path.join(_AERO_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    aero._load_table.cache_clear()
    try:
        yield name
    finally:
        aero._load_table.cache_clear()
        os.remove(path)


# ----------------------------------------------------------------------
# Passing probes (edge cases that hold)
# ----------------------------------------------------------------------


def test_mass_flow_default_matches_legacy_expression_through_derivatives():
    """Default k_J = k_t = 1: dm/dt in `derivatives` is bit-for-bit the pre-Step-98
    `-T_curve(t) / (I_sp g0)` before the mass floor is reached."""
    p = Params(
        weight=Weight(m=1.0, I=0.05, m_d=0.5, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=200.0),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng"),
    )
    times, thrusts = thrust_curve._load_motor_curve("Cesaroni_2060K570-17A.eng")
    for t in np.linspace(0.0, times[-1], 41):
        y = np.array(State(x=0.0, z=-10.0, vx=0.0, vz=-20.0, theta=math.pi / 2, omega=0.0, m=0.9))
        raw = float(np.interp(t, times, thrusts, left=thrusts[0], right=0.0))
        assert derivatives(t, y, p)[M] == -raw / (p.weight.I_sp * p.g0)


def test_pad_state_zero_velocity_is_finite_for_clamp_and_jorgensen():
    from tests.test_aero_oob import _aero, _cfg, _jorg

    for grp in (_aero(), _jorg()):
        cfg = _cfg(grp, t_max=5.0)
        y = np.array(cfg.s0, dtype=float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert np.all(np.isfinite(derivatives(0.0, y, cfg.params)))


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_jorgensen_exactly_pm_180_is_finite_and_even_odd(sign):
    from tests.test_aero_oob import _jorg, _params

    p = _params(_jorg())
    c = aero._table_coeffs(sign * math.pi, 0.5, p)
    assert np.all(np.isfinite([c.C_x, c.C_z, c.C_m]))
    assert abs(c.C_z) < 1e-9 and abs(c.C_m) < 1e-9


# ----------------------------------------------------------------------
# Open defects (see the report)
# ----------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="QA-1: malformed cm_convention comment is silently ignored (-> 'code')")
@pytest.mark.parametrize(
    "line",
    [
        "# cm_convention: standard  (textbook)\n",
        "#cm_convention=standard\n",
        "# CM_CONVENTION: standard\n",
    ],
)
def test_malformed_cm_convention_line_is_not_silently_ignored(line):
    with _table("qa_cmconv.csv", line + _HDR + _BODY) as name:
        try:
            t = aero._load_table(name)
        except ValueError:
            return  # rejecting is acceptable
        assert t.C_m[0, 0] == -0.1  # or honoured: 'standard' flips 0.1 -> -0.1


@pytest.mark.xfail(strict=True, reason="QA-2: duplicate column header silently renamed by genfromtxt")
def test_duplicate_column_header_is_rejected():
    text = "alpha_deg,M,C_A,C_N,C_m,C_m,l_p_m\n-10,0.5,0.35,-0.5,0.1,9,1.0\n0,0.5,0.3,0,0,9,1.0\n10,0.5,0.35,0.5,-0.1,9,1.0\n"
    with _table("qa_dupcol.csv", text) as name:
        with pytest.raises(ValueError):
            aero._load_table(name)


@pytest.mark.xfail(strict=True, reason="QA-3: NaN / non-numeric cell loaded as NaN without error")
def test_nan_or_non_numeric_cell_is_rejected():
    for bad in ("nan", "abc"):
        text = _HDR + f"-10,0.5,0.35,-0.5,{bad},1.0\n0,0.5,0.3,0.0,0.0,1.0\n10,0.5,0.35,0.5,-0.1,1.0\n"
        with _table("qa_nan.csv", text) as name:
            with pytest.raises(ValueError):
                aero._load_table(name)


@pytest.mark.xfail(strict=True, reason="QA-4: no validation of Thrust.k_J / k_t (k_t = 0 -> ZeroDivisionError inside the RHS)")
@pytest.mark.parametrize("kw", [dict(k_t=0.0), dict(k_t=-1.0), dict(k_J=0.0), dict(k_J=-1.0)])
def test_nonpositive_scatter_factors_fail_fast_at_assemble(kw):
    th = dataclasses.replace(DEMO.motor.thrust, **kw)
    sc = dataclasses.replace(DEMO, motor=dataclasses.replace(DEMO.motor, thrust=th))
    with pytest.raises(ValueError):
        assemble(sc)


@pytest.mark.xfail(strict=True, reason="QA-5: negative Motor.d_exit silently squared into a positive A_e")
def test_negative_d_exit_is_rejected():
    sc = dataclasses.replace(DEMO, motor=dataclasses.replace(DEMO.motor, d_exit=-0.05))
    with pytest.raises(ValueError):
        assemble(sc)


@pytest.mark.xfail(strict=True, reason="QA-6: duplicate motor names collapse in SweepResult.results (keyed by name)")
def test_sweep_duplicate_motor_names_do_not_collide():
    from apps.motor_selection import scenario_sweep as ss
    from tests.test_scenario_sweep import LARGE, _scn

    out = ss.sweep_scenario(_scn(), [LARGE, LARGE])
    assert len(out.rows) == 2
    assert len(out.results) == 2


@pytest.mark.xfail(strict=True, reason="QA-7: empty --motors list writes an empty table and exits 0")
def test_cli_empty_motor_list_is_an_error(tmp_path):
    from apps.motor_selection import scenario_sweep as ss

    with pytest.raises((SystemExit, ValueError)):
        ss.main(["--scenario", "demo", "--motors", ",", "--out-dir", str(tmp_path)])

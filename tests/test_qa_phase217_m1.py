"""Regression tests for the QA findings of Phase 2.17 M1 (Steps 97, 98, 99, 100, 112);
report: dev/docs/qa-report-2.17-m1.md (QA-1 ... QA-10).
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
    assert np.all(np.isfinite([c.C_x, c.C_z, c.C_m_code]))
    assert abs(c.C_z) < 1e-9 and abs(c.C_m_code) < 1e-9


# ----------------------------------------------------------------------
# QA-1 ... QA-10 fixes
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "# cm_convention: standard  (textbook)\n",
        "#cm_convention=standard\n",
        "# CM_CONVENTION: standard\n",
        "# cm-convention: standard\n",
        "# cm_convention: Standard\n",
        "# cm_convention: textbook\n",
    ],
)
def test_malformed_cm_convention_line_fails_fast(line):  # QA-1
    with _table("qa_cmconv.csv", line + _HDR + _BODY) as name:
        with pytest.raises(ValueError, match="cm_convention"):
            aero._load_table(name)


def test_well_formed_cm_convention_line_is_honoured():  # QA-1 control
    with _table("qa_cmconv_ok.csv", "# cm_convention: standard\n" + _HDR + _BODY) as name:
        assert aero._load_table(name).C_m_code[0, 0] == -0.1


def test_duplicate_column_header_is_rejected():  # QA-2
    text = "alpha_deg,M,C_A,C_N,C_m,C_m,l_p_m\n-10,0.5,0.35,-0.5,0.1,9,1.0\n0,0.5,0.3,0,0,9,1.0\n10,0.5,0.35,0.5,-0.1,9,1.0\n"
    with _table("qa_dupcol.csv", text) as name:
        with pytest.raises(ValueError, match="duplicate"):
            aero._load_table(name)


def test_nan_or_non_numeric_cell_is_rejected():  # QA-3
    for bad in ("nan", "abc"):
        text = _HDR + f"-10,0.5,0.35,-0.5,{bad},1.0\n0,0.5,0.3,0.0,0.0,1.0\n10,0.5,0.35,0.5,-0.1,1.0\n"
        with _table("qa_nan.csv", text) as name:
            with pytest.raises(ValueError, match="non-finite"):
                aero._load_table(name)


@pytest.mark.parametrize(
    "text, match",
    [
        ("alpha_deg,M,C_A,C_N,l_p_m\n" + "0,0.5,0.3,0.0,1.0\n", "missing required"),
        (_HDR, "no data rows"),
    ],
)
def test_malformed_table_structure_gives_clear_error(text, match):  # QA-10
    with _table("qa_struct.csv", text) as name:
        with pytest.raises(ValueError, match=match):
            aero._load_table(name)


def _scenario_with_thrust(**kw):
    th = dataclasses.replace(DEMO.motor.thrust, **kw)
    return dataclasses.replace(DEMO, motor=dataclasses.replace(DEMO.motor, thrust=th))


@pytest.mark.parametrize("kw", [dict(k_t=0.0), dict(k_t=-1.0), dict(k_J=0.0), dict(k_J=-1.0)])
def test_nonpositive_scatter_factors_fail_fast_at_assemble(kw):  # QA-4
    with pytest.raises(ValueError, match="Thrust.k_"):
        assemble(_scenario_with_thrust(**kw))


def test_positive_scatter_factors_still_assemble():  # QA-4 control
    assemble(_scenario_with_thrust(k_J=0.9, k_t=1.1))


@pytest.mark.parametrize("d", [-0.05, float("nan")])
def test_bad_d_exit_is_rejected(d):  # QA-5
    sc = dataclasses.replace(DEMO, motor=dataclasses.replace(DEMO.motor, d_exit=d))
    with pytest.raises(ValueError, match="d_exit"):
        assemble(sc)


def test_negative_l_ref_is_rejected():  # QA-10
    sc = dataclasses.replace(
        DEMO, rocket=dataclasses.replace(DEMO.rocket, aero=dataclasses.replace(DEMO.rocket.aero, l_ref=-0.1))
    )
    with pytest.raises(ValueError, match="l_ref"):
        assemble(sc)


def test_sweep_duplicate_motor_names_are_rejected():  # QA-6
    from apps.motor_selection import scenario_sweep as ss
    from tests.test_scenario_sweep import LARGE, _scn

    with pytest.raises(ValueError, match="duplicate"):
        ss.sweep_scenario(_scn(), [LARGE, LARGE])


def test_cli_empty_motor_list_is_an_error(tmp_path):  # QA-7
    from apps.motor_selection import scenario_sweep as ss

    with pytest.raises((SystemExit, ValueError)):
        ss.main(["--scenario", "demo", "--motors", ",", "--out-dir", str(tmp_path)])

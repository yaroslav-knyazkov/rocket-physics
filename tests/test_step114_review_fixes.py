"""Step 114 (Phase 2.17): code-review findings 1-6."""

import contextlib
import dataclasses
import math
import os
from types import SimpleNamespace

import numpy as np
import pytest

from apps.input.demo_scenario import DEMO_SCENARIO as DEMO
from apps.motor_selection import scenario_sweep as ss
from configs.schema import assemble
from sim import aero, dynamics, thrust_curve
from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.forces import aero_moment_y
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.state import State
from tests.datadir import AERO_DIR as _AERO_DIR
from tests.test_scenario_sweep import LARGE


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
        if os.path.exists(path):
            os.remove(path)


_BODY = (
    "alpha_deg,M,C_A,C_N,C_m,l_p_m,c_mq\n"
    "-10,0.5,0.35,-0.5,0.08,1.1,{q}\n"
    "0,0.5,0.30,0.0,0.0,1.1,{q}\n"
    "10,0.5,0.35,0.5,-0.08,1.1,{q}\n"
)


# 1 ---------------------------------------------------------------------------


def test_inconsistent_isp_fails_fast_at_assemble():
    bad = dataclasses.replace(LARGE, mass_model="isp", I_sp=1.0)  # absurdly low I_sp
    with pytest.raises(ValueError, match=r"large_I.*I_sp.*m_prop"):
        assemble(dataclasses.replace(DEMO, motor=bad))


def test_consistent_motors_still_assemble():
    assemble(dataclasses.replace(DEMO, motor=LARGE))  # 'endpoints': consistent by construction
    assemble(DEMO)


# 2 ---------------------------------------------------------------------------


def test_standard_table_flips_c_mq_column_and_damps_pitch():
    text = "# cm_convention: standard\n" + _BODY.format(q=-8.0)  # textbook: C_mq < 0 damps
    with _table("test_s114_std.csv", text) as name:
        t = aero._load_table(name)
        assert np.all(t.C_mq_code == 8.0)
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4, l_g=0.9),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name),
        )
        y = np.array(State(x=0.0, z=-50.0, vx=0.0, vz=-80.0, theta=math.pi / 2, omega=0.5))
        flow = flow_state(0.0, y, p)
        M_y = aero_moment_y(0.0, y, p, flow)
        # alpha ~ 0 -> static term ~ 0; the damping moment must oppose omega
        assert M_y * y[5] < 0.0


def test_code_table_c_mq_column_is_untouched():
    with _table("test_s114_code.csv", _BODY.format(q=8.0)) as name:
        assert np.all(aero._load_table(name).C_mq_code == 8.0)


# 3 ---------------------------------------------------------------------------


def test_jorgensen_rejects_near_zero_alpha_edge():
    text = (
        "alpha_deg,M,C_A,C_N,C_m,l_p_m\n"
        "-1,0.5,0.35,-0.05,0.008,1.1\n"
        "1,0.5,0.35,0.05,-0.008,1.1\n"
    )
    with _table("test_s114_edge.csv", text) as name:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4, l_g=0.9),
            aero=Aero(model="table", S=0.01, d_ref=0.1, table=name, table_oob="jorgensen",
                      S_p=0.05, l_pc=0.7),
        )
        with pytest.raises(ValueError, match="2 deg"):
            aero.validate(p)


# 4 ---------------------------------------------------------------------------


def test_coefficients_evaluated_once_per_rhs(monkeypatch):
    cfg = assemble(DEMO)
    y = np.array(cfg.s0)
    calls = []
    orig = aero.coefficients
    monkeypatch.setattr(aero, "coefficients", lambda *a, **k: calls.append(1) or orig(*a, **k))
    derivatives(0.5, y, cfg.params)
    assert len(calls) == 1


def test_at_fb_on_a_grid_node_returns_the_stored_plane():
    planes = tuple(
        aero._AeroTable(M=np.array([0.5]), alpha=np.array([0.0, 0.1]), C_A=np.full((1, 2), v),
                        C_N=np.zeros((1, 2)), C_m_code=np.zeros((1, 2)), l1=None, C_mq_code=None,
                        l_p=np.ones((1, 2)))
        for v in (0.3, 0.5, 0.9)
    )
    grid = np.array([0.0, 0.5, 1.0])
    t = planes[0]._replace(f_b=grid, planes=planes)
    assert aero._at_fb(t, 0.5) is planes[1]
    assert aero._at_fb(t, 1.0) is planes[2]
    mid = aero._at_fb(t, 0.25)
    assert np.allclose(mid.C_A, 0.4)


# 5 ---------------------------------------------------------------------------


@pytest.mark.parametrize("field,val", [("k_J", 0.0), ("k_t", -1.0)])
def test_derive_history_rejects_nonpositive_scatter(field, val):
    m = dataclasses.replace(LARGE, thrust=dataclasses.replace(LARGE.thrust, **{field: val}))
    with pytest.raises(ValueError, match=field):
        ss.derive_history(m)


# 6 ---------------------------------------------------------------------------


def test_thrust_stand_array_matches_scalar_bitwise():
    p = assemble(dataclasses.replace(DEMO, motor=LARGE)).params
    p = dataclasses.replace(p, thrust=dataclasses.replace(p.thrust, k_J=1.1, k_t=0.9))
    t = np.linspace(0.0, 2.0, 257)
    assert np.array_equal(thrust_curve.thrust_stand_array(t, p),
                          np.array([thrust_curve.thrust_stand(float(x), p) for x in t]))


def test_tw_liftoff_uses_flown_thrust_with_exit_pressure_term():
    cfg = assemble(dataclasses.replace(DEMO, motor=LARGE))
    p = dataclasses.replace(cfg.params, thrust=dataclasses.replace(cfg.params.thrust, A_e=1e-3))
    y0 = np.array(cfg.s0)
    res = SimpleNamespace(events={"burnout": 0.4}, t=np.array([0.0, 1.0]), y=y0.reshape(-1, 1))
    t = np.linspace(0.0, 0.4, 2000)
    peak = max(thrust_curve.thrust(float(ti), y0, p) for ti in t)
    assert ss._tw_liftoff(res, p) == pytest.approx(peak / (p.weight.m * p.g0), rel=1e-12)
    p0 = dataclasses.replace(p, thrust=dataclasses.replace(p.thrust, A_e=0.0))
    peak0 = max(thrust_curve.thrust_stand(float(ti), p0) for ti in t)
    assert ss._tw_liftoff(res, p0) == pytest.approx(peak0 / (p.weight.m * p.g0), rel=1e-15)

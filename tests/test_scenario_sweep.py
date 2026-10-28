"""Tests for apps/optimization/motor_selection/scenario_sweep.py (Step 100, Phase 2.17,
architecture-35 SS35.4.5, D-113): motor sweep v2 on Motor/Scenario, plus the
B26 thin slice (`derive_history` + provenance)."""

import contextlib
import dataclasses
import hashlib
import os

import numpy as np
import pytest

from apps._shared.flight_stats import flight_stats
from apps.input.demo_scenario import DEMO_SCENARIO as DEMO
from apps.optimization.motor_selection import scenario_sweep as ss
from configs.schema import Motor, assemble
from apps.sim.engine import aero, motor_file
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Aero, Solver, Thrust
from tests.datadir import AERO_DIR as _AERO_DIR


def _csv_motor(name, curve, m_prop, m_total, **kw):
    """Synthetic CSV motor: a CSV has no header, so masses/geometry are spelled out."""
    return Motor(
        name=name,
        thrust=Thrust(motor_curve=curve),
        mass_model="endpoints",
        m_total=m_total, m_prop=m_prop, length=0.30, diameter=0.054,
        **kw,
    )


LARGE = _csv_motor("large_I", "synthetic_large.csv", 0.15, 0.35)
PUNCHY = _csv_motor("punchy_H", "synthetic_medium_punchy.csv", 0.09, 0.25)
SMALL = _csv_motor("small_E", "synthetic_small.csv", 0.02, 0.10)  # peak 60 N: T/W < 5


def _scn(**kw):
    """Demo scenario, short horizon (the ascent is all the sweep reads)."""
    kw.setdefault("solver", Solver(t_max=90.0))
    return dataclasses.replace(DEMO, **kw)


@contextlib.contextmanager
def _temp_table(name, text):
    path = os.path.join(_AERO_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    aero._load_table.cache_clear()
    try:
        yield name
    finally:
        aero._load_table.cache_clear()
        os.remove(path)


_LOW_M_TABLE = """# cm_convention: standard
alpha_deg,M,C_A,C_N,C_m,l_p_m
-10,0.05,0.35,0.0,0.0,1.0
0,0.05,0.30,0.0,0.0,1.0
10,0.05,0.35,0.0,0.0,1.0
-10,0.2,0.35,0.0,0.0,1.0
0,0.2,0.30,0.0,0.0,1.0
10,0.2,0.35,0.0,0.0,1.0
"""


@pytest.fixture(scope="module")
def sweep():
    return ss.sweep_scenario(_scn(), [SMALL, LARGE, PUNCHY], target=1500.0)


def test_row_fields_present_and_ordered(sweep):
    names = tuple(f.name for f in dataclasses.fields(ss.SweepRow))
    assert names == ss.ROW_FIELDS
    assert ss.ROW_FIELDS[:3] == ("motor", "J_total", "t_burn")
    row = sweep.rows[0]
    for f in ("tw_liftoff", "v_rail_exit", "h_apogee", "v_max", "M_max", "q_max", "a_max",
              "margin_rail_exit", "margin_burnout", "margin_min", "m_burnout", "dist_target"):
        assert hasattr(row, f)
    assert row.h_apogee > 100.0
    assert row.J_total == pytest.approx(motor_file.load("synthetic_large.csv").total_impulse
                                        if row.motor == "large_I"
                                        else motor_file.load("synthetic_medium_punchy.csv").total_impulse)


def test_infeasible_motor_flagged_and_ranked_last(sweep):
    assert [r.motor for r in sweep.rows][-1] == "small_E"
    small = sweep.rows[-1]
    assert not small.feasible and "tw_liftoff" in small.failed
    assert all(r.feasible for r in sweep.rows[:-1])
    # feasible rows ordered by distance to target
    d = [r.dist_target for r in sweep.rows[:-1]]
    assert d == sorted(d)


def test_mach_beyond_table_range_is_flagged():
    with _temp_table("test_sweep_lowM.csv", _LOW_M_TABLE) as tbl:
        rocket = dataclasses.replace(
            DEMO.rocket,
            aero=Aero(model="table", S=0.00229, d_ref=0.054, table=tbl),
        )
        out = ss.sweep_scenario(_scn(rocket=rocket), [LARGE], target=1500.0)
    row = out.rows[0]
    assert "mach_range" in row.failed and not row.feasible
    assert row.M_max > 0.2


def test_margin_below_threshold_is_flagged():
    out = ss.sweep_scenario(
        _scn(), [LARGE], constraints=ss.Constraints(min_margin_cal=1000.0)
    )
    assert "static_margin" in out.rows[0].failed
    assert out.rows[0].margin_min < 1000.0


def test_works_with_v2_table_and_margin_series():
    rocket = dataclasses.replace(
        DEMO.rocket, aero=Aero(model="table", S=0.00229, d_ref=0.054, table="example_v2.csv")
    )
    # RK45 stalls after apogee here: the table lookup clamps C_N/C_m at alpha ~ 180 deg (sliding mode),
    # not stiffness or missing damping (dev/docs/diagnosis-rk45-v2-table.md; fix: Step 112). Fixed-step RK4
    out = ss.sweep_scenario(
        _scn(rocket=rocket, solver=Solver(method="rk4", dt=0.005, t_max=20.0)), [LARGE], target=1500.0
    )
    r = out.rows[0]
    assert np.isfinite(r.margin_rail_exit) and np.isfinite(r.margin_burnout)
    assert r.margin_burnout != pytest.approx(r.margin_rail_exit)  # the CG (and M) move during the burn
    assert r.margin_min == pytest.approx(min(r.margin_rail_exit, r.margin_burnout), rel=1e-6, abs=1e-6)


def test_brake_open_apogee_is_reported_when_overrides_given():
    out = ss.sweep_scenario(_scn(), [LARGE], brake_overrides={"aero.C_x": 1.5})
    r = out.rows[0]
    assert r.h_apogee_brake is not None and r.h_apogee_brake < r.h_apogee
    out0 = ss.sweep_scenario(_scn(), [LARGE])
    assert out0.rows[0].h_apogee_brake is None


def test_flight_stats_additive_fields():
    cfg = assemble(_scn(motor=LARGE))
    res = run_sim(cfg.params, cfg.s0)
    st = flight_stats(res, cfg.params)
    assert st.max_mach > 0.0
    assert st.rail_exit_speed is None  # demo site has no rail


# --- B26 thin slice -----------------------------------------------------


def test_history_matches_endpoints_at_launch_and_burnout():
    m = _csv_motor("ep", "synthetic_large.csv", 0.15, 0.35,
                   l_cog_0=0.14, l_cog_f=0.16, I_0=2.0e-3, I_f=1.0e-3)
    h = ss.derive_history(m)
    assert h.t[0] == 0.0
    assert h.m[0] == pytest.approx(0.35, abs=1e-12)
    assert h.l_cg[0] == pytest.approx(0.14, abs=1e-12)
    assert h.I[0] == pytest.approx(2.0e-3, abs=1e-12)
    assert h.m[-1] == pytest.approx(0.20, abs=1e-12)
    assert h.l_cg[-1] == pytest.approx(0.16, abs=1e-12)
    assert h.I[-1] == pytest.approx(1.0e-3, abs=1e-12)
    assert np.all(np.diff(h.m) <= 1e-15)


def test_history_matches_simulated_burn_state_mass():
    # default rtol=1e-8 leaves ~1e-6 kg of integration error across the thrust-curve kinks;
    # the 1e-9 comparison needs a tight solver (the derived history itself is exact)
    cfg = assemble(dataclasses.replace(DEMO, solver=Solver(t_max=10.0, rtol=1e-12, atol=1e-13)))
    p = cfg.params
    res = run_sim(p, cfg.s0)
    t_b = res.events["burnout"]
    t = np.linspace(0.0, t_b, 25)
    h = ss.derive_history(DEMO.motor, t=t, g0=p.g0)
    m_sim = res.raw.sol(t)[6] - DEMO.rocket.airframe.m
    assert np.max(np.abs(h.m - m_sim)) < 1e-9
    # vehicle CG from airframe + motor history == the dynamics' CG
    from apps.sim.engine import mass
    l_fwd = DEMO.rocket.sections.l_motor_aft - motor_file.load(DEMO.motor.thrust.motor_curve).length
    af = DEMO.rocket.airframe
    l_veh = (af.m * af.l + h.m * (l_fwd + h.l_cg)) / (af.m + h.m)
    l_dyn = np.array([mass.cog_position(mass.propellant_mass(y[6] , p), p)
                      for y in res.raw.sol(t).T])
    assert np.max(np.abs(l_veh - l_dyn)) < 1e-9


def test_history_respects_time_scaling():
    k = dataclasses.replace(LARGE, thrust=Thrust(motor_curve="synthetic_large.csv", k_t=1.1))
    h = ss.derive_history(k)
    h1 = ss.derive_history(LARGE)
    assert h.t[-1] == pytest.approx(1.1 * h1.t[-1])
    assert h.m[-1] == pytest.approx(h1.m[-1], abs=1e-12)


def test_history_requires_a_mass_model():
    with pytest.raises(ValueError):
        ss.derive_history(dataclasses.replace(LARGE, mass_model="none"))


def test_provenance_carries_model_inputs_and_file_hash():
    h = ss.derive_history(DEMO.motor)
    prov = h.provenance
    assert prov["model"] == "endpoints"
    path = motor_file._motors_path("Cesaroni_2060K570-17A.eng")
    with open(path, "rb") as f:
        assert prov["source_sha256"] == hashlib.sha256(f.read()).hexdigest()
    for k in ("m_total", "m_prop", "I_sp", "J", "k_J", "k_t"):
        assert k in prov["inputs"]
    assert prov["inputs"]["m_prop"] == pytest.approx(0.99)
    # sweep rows carry it too
    out = ss.sweep_scenario(_scn(), [LARGE])
    assert out.rows[0].provenance["model"] == "endpoints"
    assert len(out.rows[0].provenance["source_sha256"]) == 64


# --- CLI ----------------------------------------------------------------


def test_cli_saves_table_and_overlay(tmp_path, capsys):
    ss.main(["--motors", "Cesaroni_2060K570-17A.eng", "--target", "5000",
             "--out-dir", str(tmp_path)])
    assert (tmp_path / "motor_sweep_demo.csv").exists()
    assert (tmp_path / "motor_sweep_demo_overlay.png").exists()
    # `resolve_motor`'s ad-hoc-from-RASP-file branch sets Motor.name = spec
    # (Step 124, D-139/CLI-1: no registered motor *name* to resolve to any
    # more), so the printed table shows the file name itself.
    assert "Cesaroni_2060K570-17A.eng" in capsys.readouterr().out


def test_cli_unknown_motor_lists_available():
    with pytest.raises(KeyError, match="unknown motor 'nope'"):
        ss.resolve_motor("nope")

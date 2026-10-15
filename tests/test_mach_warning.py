"""Tests for sim/mach_warning.py (Phase 2.16, Step 92, D-83): a run whose
peak Mach exceeds 0.8 under a Mach-independent drag model warns; a
subsonic run and a "table" run do not; the result is untouched."""

import warnings

import pytest

from apps.common import study_vehicle
from sim.integrate import run_sim
from sim.mach_warning import MachRangeWarning, peak_mach
from sim.params import replace as params_replace


def _demo():
    import configs

    return configs.get("demo")


def test_demo_run_warns_with_peak_mach_time_and_model():
    cfg = _demo()
    with pytest.warns(MachRangeWarning, match=r'peak Mach \d\.\d\d at t=.*"constant"') as rec:
        run_sim(cfg.params, cfg.s0)
    assert len([w for w in rec if issubclass(w.category, MachRangeWarning)]) == 1


def test_demo_peak_mach_is_supersonic():
    cfg = _demo()
    with pytest.warns(MachRangeWarning):
        result = run_sim(cfg.params, cfg.s0)
    m, t = peak_mach(result)
    assert 2.0 < m < 3.0
    assert 0.0 < t <= result.events["ground"]  # peak is the ballistic descent (~Mach 2.57 at impact); ascent peak is ~Mach 1.73


def test_subsonic_study_vehicle_does_not_warn():
    cfg = study_vehicle.CONFIG
    with warnings.catch_warnings():
        warnings.simplefilter("error", MachRangeWarning)
        result = run_sim(cfg.params, cfg.s0)
    assert peak_mach(result)[0] < 0.8


def test_linearized_model_above_limit_also_warns():
    cfg = _demo()
    p = params_replace(
        cfg.params, {"aero.model": "linearized", "aero.C_A0": 0.5, "aero.C_N_alpha": 2.0, "aero.C_m_alpha": -0.5}
    )
    with pytest.warns(MachRangeWarning, match='"linearized"'):
        run_sim(p, cfg.s0)


def test_table_model_above_limit_is_exempt(monkeypatch):
    cfg = _demo()
    result_constant = None
    with pytest.warns(MachRangeWarning):
        result_constant = run_sim(cfg.params, cfg.s0)
    # Same fast flight, but labelled "table": the check must stay silent.
    # (Only the model label is swapped on the finished Result's params --
    # the check reads nothing else from the aero group.)
    from sim.mach_warning import warn_if_mach_blind

    table_params = params_replace(result_constant.params, {"aero.model": "table"})
    table_result = result_constant._replace(params=table_params)
    with warnings.catch_warnings():
        warnings.simplefilter("error", MachRangeWarning)
        warn_if_mach_blind(table_result)


def test_warning_does_not_change_the_result():
    cfg = _demo()
    with pytest.warns(MachRangeWarning):
        a = run_sim(cfg.params, cfg.s0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MachRangeWarning)
        b = run_sim(cfg.params, cfg.s0)
    assert (a.y == b.y).all() and (a.t == b.t).all() and a.events == b.events

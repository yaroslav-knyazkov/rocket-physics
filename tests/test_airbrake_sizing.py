"""Tests for apps/airbrake_sizing/ -- App 4, airbrake C_dA determination
against the real solver (roadmap.md Step 66,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.6/SS30.8).

Same testing philosophy as `tests/test_control.py`/`test_motor_selection.py`:
no fixtures, no conftest.py, plain `assert` + `math.isclose`. The primary
checks are the round-trip pin (needs no external ground truth: solve
recovers the value a direct evaluation itself produced) and the
`after_apogee` refusal (F19) -- everything else is a structural/property
check around those two.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from apps.airbrake_sizing import solve_cda
from apps.airbrake_sizing.solve_cda import (
    AirbrakeSpec,
    apogee_for_cda,
    apogee_for_deploy_time,
    brake_overrides,
    evaluate_airbrake,
    save_overlay,
    save_solution_csv,
    solve_airbrake,
)
from apps.airbrake_sizing.targets import SPECS
from apps.common import study_vehicle
from apps.common.artifacts import OUTPUT_DIR, ensure_dir
from sim import control
from sim.integrate import Result
from sim.params import replace as params_replace
from sim.state import VZ

_CFG = study_vehicle.CONFIG

# ----------------------------------------------------------------------
# Monotonicity (the premise the whole method rests on, F6/F18) + round-trip
# ----------------------------------------------------------------------


def test_apogee_for_cda_is_strictly_decreasing_across_the_bounds():
    """F6's shape, asserted as an ordering (not pinned values): apogee
    strictly decreases as the brake's C_dA grows, under after_burnout."""
    spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout")
    cdas = [0.0, 0.001, 0.01, 0.1, 1.0, 10.0]
    apogees = [apogee_for_cda(c, _CFG, spec)[0] for c in cdas]
    assert all(a is not None for a in apogees)
    assert all(apogees[i] > apogees[i + 1] for i in range(len(apogees) - 1))


def test_apogee_for_deploy_time_is_strictly_increasing_across_the_bounds():
    """F18's shape: apogee strictly increases with deploy time at a fixed
    C_dA, under after_time."""
    spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_time")
    cda = 0.02
    deploy_times = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0]
    apogees = [apogee_for_deploy_time(t, cda, _CFG, spec)[0] for t in deploy_times]
    assert all(a is not None for a in apogees)
    assert all(apogees[i] < apogees[i + 1] for i in range(len(apogees) - 1))


def test_round_trip_cda_solve_recovers_the_value_that_produced_the_target():
    """The primary check: pick a C_dA*, run it directly, take its own
    apogee as the target, solve -- the solver must recover C_dA* to a
    stated tolerance. Catches a wrong override key, a sign error or a
    units error immediately (needs no external ground truth)."""
    cda_star = 0.02
    probe_spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout")
    apogee_star, _, _ = apogee_for_cda(cda_star, _CFG, probe_spec)
    assert apogee_star is not None

    sol = solve_airbrake(_CFG, AirbrakeSpec(target_apogee_m=apogee_star, trigger="after_burnout"))

    assert sol.reachable
    assert sol.converged
    assert math.isclose(sol.cda_airbrake, cda_star, rel_tol=1e-4)
    assert math.isclose(sol.apogee_m, apogee_star, abs_tol=1e-2)


def test_round_trip_deploy_time_solve_recovers_the_value_that_produced_the_target():
    """The same round-trip pin for the mirror solve (solve_for="deploy_time"):
    pick a deploy time, run it at a fixed C_dA, take its apogee as the
    target, solve for deploy time -- recover the original instant."""
    cda_fixed = 0.02
    t_star = 3.0
    probe_spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_time")
    apogee_star, _, _ = apogee_for_deploy_time(t_star, cda_fixed, _CFG, probe_spec)
    assert apogee_star is not None

    sol = solve_airbrake(
        _CFG,
        AirbrakeSpec(
            target_apogee_m=apogee_star,
            trigger="after_time",
            solve_for="deploy_time",
            cda_bounds=(cda_fixed, cda_fixed),
            deploy_time_bounds=(0.0, 8.0),
        ),
    )

    assert sol.reachable
    assert sol.converged
    assert math.isclose(sol.deploy_time_s, t_star, rel_tol=1e-4)
    assert math.isclose(sol.apogee_m, apogee_star, abs_tol=1e-2)
    assert math.isclose(sol.cda_airbrake, cda_fixed)   # fixed, not solved, under solve_for="deploy_time"


# ----------------------------------------------------------------------
# brake_overrides + airbrake_deploy_fraction, each of the three triggers
# ----------------------------------------------------------------------


def _zero_state(vz: float = 0.0) -> np.ndarray:
    y = np.zeros(7)
    y[VZ] = vz
    return y


@pytest.mark.parametrize(
    "trigger, deploy_time_s, t_before, t_after",
    [
        ("after_burnout", 0.0, 1.0, 2.5),     # placeholder.csv burnout at t=2.0s
        ("after_time", 4.0, 3.9, 4.0),
    ],
)
def test_brake_overrides_deploy_fraction_is_0_before_1_after_time_based_triggers(
    trigger, deploy_time_s, t_before, t_after
):
    spec = AirbrakeSpec(target_apogee_m=0.0, trigger=trigger, deploy_time_s=deploy_time_s)
    p = params_replace(_CFG.params, brake_overrides(0.01, spec))
    y = _zero_state()
    assert control.airbrake_deploy_fraction(t_before, y, p) == 0.0
    assert control.airbrake_deploy_fraction(t_after, y, p) == 1.0


def test_brake_overrides_deploy_fraction_is_0_before_1_after_apogee_trigger():
    spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_apogee")
    p = params_replace(_CFG.params, brake_overrides(0.01, spec))
    assert control.airbrake_deploy_fraction(5.0, _zero_state(vz=-5.0), p) == 0.0   # rising
    assert control.airbrake_deploy_fraction(5.0, _zero_state(vz=5.0), p) == 1.0    # descending


# ----------------------------------------------------------------------
# F1's product-only property
# ----------------------------------------------------------------------


def test_s_max_equals_cda_over_cd_brake_for_a_non_unity_cd():
    spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout", cd_brake=2.0)
    sol = evaluate_airbrake(0.04, _CFG, spec)
    assert math.isclose(sol.s_max_m2, sol.cda_airbrake / spec.cd_brake)
    assert math.isclose(sol.s_max_m2, 0.02)


def test_two_cd_brake_s_max_pairs_with_equal_product_give_the_same_apogee():
    """F1: the model only ever uses the product Cd * S_max."""
    cda_target = 0.04
    probe_spec = AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout")
    apogee_a, _, _ = apogee_for_cda(cda_target, _CFG, probe_spec)

    # Build the same C_dA via a different (Cd, S_max) decomposition by
    # using evaluate_airbrake with a non-unity cd_brake -- same product.
    spec_b = AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout", cd_brake=4.0)
    sol_b = evaluate_airbrake(cda_target, _CFG, spec_b)   # s_max = cda/4 internally

    assert math.isclose(sol_b.cda_airbrake, cda_target)
    assert math.isclose(sol_b.apogee_m, apogee_a, abs_tol=1e-6)


# ----------------------------------------------------------------------
# The after_apogee refusal (F19) -- the second primary check
# ----------------------------------------------------------------------


def test_after_apogee_refusal_raises_without_running_a_search(monkeypatch):
    """solve_airbrake must raise ValueError naming the flat-objective
    reason -- and must do so *before* running a single simulation."""

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called under the after_apogee refusal")

    monkeypatch.setattr(solve_cda, "run_sim", _must_not_be_called)

    with pytest.raises(ValueError, match="after_apogee"):
        solve_airbrake(_CFG, AirbrakeSpec(target_apogee_m=300.0, trigger="after_apogee"))


def test_evaluate_airbrake_after_apogee_is_independent_of_cda():
    """F19's measured independence, asserted as the property it is: for
    any C_dA, the after_apogee trigger's achieved apogee equals the
    brake-stowed apogee to within 1e-2 m."""
    stowed_apogee, _, _ = apogee_for_cda(0.0, _CFG, AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout"))
    assert stowed_apogee is not None

    for cda in (0.0, 0.01, 0.1, 1.0, 10.0):
        sol = evaluate_airbrake(cda, _CFG, AirbrakeSpec(target_apogee_m=0.0, trigger="after_apogee", solve_for="none"))
        assert math.isclose(sol.apogee_m, stowed_apogee, abs_tol=1.0e-2), (cda, sol.apogee_m, stowed_apogee)
        assert sol.reachable is True
        assert sol.converged is None


# ----------------------------------------------------------------------
# The flat-objective detector -- the *other* message (after_time too late)
# ----------------------------------------------------------------------


def test_flat_objective_detector_fires_a_distinct_message_for_after_time_too_late():
    """An after_time spec whose deploy_time is past the brake-closed
    apogee time (~9.19 s on this vehicle) is refused too, but with a
    message distinct from the after_apogee one -- it never says
    "after_apogee" and names the deploy_time cause instead."""
    with pytest.raises(ValueError) as exc_info:
        solve_airbrake(_CFG, AirbrakeSpec(target_apogee_m=300.0, trigger="after_time", deploy_time_s=9.3))

    message = str(exc_info.value)
    assert "after_apogee" not in message
    assert "flat" in message
    assert "deploy_time" in message


# ----------------------------------------------------------------------
# Unreachable targets -- reachable=False, clamped, no exception
# ----------------------------------------------------------------------


def test_unreachable_target_above_brake_closed_apogee_clamps_with_no_exception():
    closed_apogee, _, _ = apogee_for_cda(0.0, _CFG, AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout"))
    sol = solve_airbrake(_CFG, AirbrakeSpec(target_apogee_m=closed_apogee + 500.0, trigger="after_burnout"))

    assert sol.reachable is False
    assert sol.cda_airbrake == 0.0   # clamped to the stowed/closed bound
    assert math.isclose(sol.apogee_m, closed_apogee, abs_tol=1e-6)


def test_unreachable_target_below_brake_open_apogee_clamps_with_no_exception():
    spec_probe = AirbrakeSpec(target_apogee_m=0.0, trigger="after_burnout")
    open_apogee, _, _ = apogee_for_cda(10.0, _CFG, spec_probe)
    sol = solve_airbrake(_CFG, AirbrakeSpec(target_apogee_m=open_apogee - 50.0, trigger="after_burnout"))

    assert sol.reachable is False
    assert sol.cda_airbrake == 10.0   # clamped to the fully-open bound
    assert math.isclose(sol.apogee_m, open_apogee, abs_tol=1e-6)


# ----------------------------------------------------------------------
# Degenerate flight / solver guards
# ----------------------------------------------------------------------


def test_config_that_never_leaves_the_pad_raises_naming_the_config(monkeypatch):
    """A degenerate run (`events["apogee"] is None`) at the solve's own
    endpoint runs must raise ValueError naming the config, not silently
    root-find against a None. Exercised by monkeypatching `run_sim` to
    reproduce the degenerate-flight event shape directly (the same
    technique `test_motor_selection.py`'s fake-`Result` tests use), since
    reliably constructing a *physically* never-leaves-the-pad scenario
    through this simulator's own apogee-event guard is a separate, known
    gotcha (architecture-29-motor-selection.md SS29.4.6) orthogonal to
    this guard's own logic."""

    def _fake_run_sim(p, s0):
        return Result(
            t=np.array([0.0, 1.0]),
            y=np.zeros((7, 2)),
            events={"apogee": None, "ground": None, "burnout": None, "rail_exit": None, "parachute_deploy": None},
            raw=None,
            params=p,
        )

    monkeypatch.setattr(solve_cda, "run_sim", _fake_run_sim)

    with pytest.raises(ValueError, match=_CFG.name):
        solve_airbrake(_CFG, AirbrakeSpec(target_apogee_m=200.0, trigger="after_burnout"))


def test_sample_rate_hz_raises_before_the_first_run_sim(monkeypatch):
    """The inherited F8 guard (`apps.common.flight_stats`): a sampled-data
    `Params` must be rejected before `run_sim` is ever called."""

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called once the sample_rate_hz guard fires")

    monkeypatch.setattr(solve_cda, "run_sim", _must_not_be_called)

    sampled_cfg = _CFG.derive(name="sampled", overrides={"solver.sample_rate_hz": 1000.0, "solver.method": "rk4"})
    with pytest.raises(ValueError):
        solve_airbrake(sampled_cfg, AirbrakeSpec(target_apogee_m=200.0, trigger="after_burnout"))
    with pytest.raises(ValueError):
        evaluate_airbrake(0.01, sampled_cfg, AirbrakeSpec(target_apogee_m=200.0, trigger="after_apogee", solve_for="none"))


# ----------------------------------------------------------------------
# End to end: all four named SPECS against demo_75mm_airbrake
# ----------------------------------------------------------------------


def test_end_to_end_against_demo_75mm_airbrake_for_every_named_spec():
    """Runs every spec in targets.SPECS against the app's own default
    vehicle and writes both artifacts. No apogee value is pinned here by
    design (roadmap.md Step 66) -- this is a smoke/wiring test, the
    numbers are reported in the developer's own step report."""
    ensure_dir(OUTPUT_DIR)
    csv_path = OUTPUT_DIR / "airbrake_sizing.csv"
    png_path = OUTPUT_DIR / "airbrake_sizing_overlay.png"

    for name, spec in SPECS.items():
        if spec.solve_for == "none":
            sol = evaluate_airbrake(spec.cda_bounds[1], _CFG, spec)
        else:
            sol = solve_airbrake(_CFG, spec)

        assert sol.n_sim_runs >= 1
        assert sol.trigger == spec.trigger

        save_solution_csv(sol, csv_path)
        save_overlay(sol, png_path)
        assert csv_path.exists() and csv_path.stat().st_size > 0
        assert png_path.exists() and png_path.stat().st_size > 0

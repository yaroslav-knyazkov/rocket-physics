"""Tests for apps/analysis/ensemble/ensemble.py (Step 105, Phase 2.17,
dev/docs/architecture-35-paper-alignment.md SS35.4.5; moved here from
apps/common/ensemble.py at Phase 2.19 Step 131,
dev/docs/architecture-apps-sim-restructure.md): dispersion hooks
(`Aero.cx_scale`, `Atmosphere.dT_K`) + the Monte-Carlo ensemble runner.

`cx_scale`'s own pin/monotonicity test lives here (not tests/test_aero.py):
the field exists solely to support this ticket's dispersion mechanism, and
this is the ticket's one declared new test file (`dT_K`'s equivalent test
lives in tests/test_atmosphere.py per the ticket's own file boundary).

Every `evaluate` callable handed to `run_ensemble` with `workers != 1` must
be a top-level function, not a closure or a lambda defined inside a test --
`ProcessPoolExecutor` on Windows always `spawn`s, which can only re-import a
picklable top-level name into the worker process.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from apps.analysis.ensemble import ensemble as ens
from apps._shared.flight_stats import flight_stats
from configs.schema import Airframe, LaunchSite, Motor, Rocket, Scenario, Weather, assemble
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Aero, Lengths, Params, Solver, Thrust, Weight
from apps.sim.engine.params import replace as params_replace
from apps.sim.engine.state import State

_BASE_SCENARIO = Scenario(
    name="ensemble_test",
    rocket=Rocket(name="r", airframe=Airframe(m=1.5, I=0.08)),
    motor=Motor(name="m", thrust=Thrust(motor_curve="placeholder.csv")),
    site=LaunchSite(name="s"),
    weather=Weather(name="w"),
    solver=Solver(t_max=5.0),
)


# ----------------------------------------------------------------------
# Top-level (spawn-picklable) `evaluate` callables -- see module docstring.
# ----------------------------------------------------------------------


def _eval_cx_scale(cfg):
    return {"cx_scale": float(cfg.params.aero.cx_scale)}


def _eval_flaky_above_threshold(cfg):
    v = cfg.params.aero.cx_scale
    if v > 1.05:
        raise ValueError(f"cx_scale too large: {v:g}")
    return {"cx_scale": float(v)}


# ----------------------------------------------------------------------
# Aero.cx_scale (sim/aero.py's single-choke-point multiply)
# ----------------------------------------------------------------------


def _const_drag_params(**over) -> Params:
    p = Params(
        weight=Weight(m=1.5, I=0.08),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(model="constant", S=0.01, d_ref=0.1, C_x=0.5),
        thrust=Thrust(motor_curve="placeholder.csv"),
        solver=Solver(t_max=40.0),
    )
    return params_replace(p, over) if over else p


def _s0() -> State:
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2.0, omega=0.0)


def test_cx_scale_default_is_bit_identical_to_the_legacy_flight():
    """`cx_scale == 1.0` must be SKIPPED entirely (sim/aero.py's guard),
    not multiplied by 1.0 -- same convention as every other Step 97-115
    no-op field."""
    p0 = _const_drag_params()
    p1 = _const_drag_params(**{"aero.cx_scale": 1.0})
    r0 = run_sim(p0, _s0())
    r1 = run_sim(p1, _s0())
    assert np.array_equal(r0.y, r1.y)
    assert np.array_equal(r0.t, r1.t)
    assert r0.events == r1.events


def test_cx_scale_scales_apogee_loss_monotonically():
    """Higher `cx_scale` -> more axial drag -> strictly lower apogee."""
    apogees = []
    for scale in (1.0, 1.1, 1.3, 1.6):
        p = _const_drag_params(**{"aero.cx_scale": scale})
        r = run_sim(p, _s0())
        apogees.append(flight_stats(r, p).apogee_altitude)
    assert all(a is not None for a in apogees)
    assert all(a > b for a, b in zip(apogees, apogees[1:]))


# ----------------------------------------------------------------------
# Dispersion constructors
# ----------------------------------------------------------------------


def test_normal_path_scenario_stage_sets_the_nested_field_exactly():
    d = ens.normal_path("rocket.airframe.m", 2.0, 0.0, stage="scenario", name="m")
    rng = np.random.default_rng(0)
    v = d.draw(rng)
    assert v == 2.0  # sigma == 0 -> deterministic draw
    sc2 = d.apply(_BASE_SCENARIO, v)
    assert sc2.rocket.airframe.m == 2.0
    assert _BASE_SCENARIO.rocket.airframe.m == 1.5  # frozen dataclasses: original untouched


def test_normal_path_params_stage_routes_through_scenario_overrides():
    """`assemble`'s own dotted-path mechanism (`Scenario.overrides` ->
    `sim.params.replace`), not a second, independent one (see module
    docstring / configs/schema.py's "s0 AFTER overrides" ordering note)."""
    d = ens.normal_path("aero.cx_scale", 1.3, 0.0, stage="params", name="cx")
    sc2 = d.apply(_BASE_SCENARIO, 1.3)
    assert sc2.overrides == {"aero.cx_scale": 1.3}
    assert assemble(sc2).params.aero.cx_scale == 1.3


def test_uniform_path_draws_stay_within_bounds():
    d = ens.uniform_path("aero.cx_scale", 0.8, 1.2, name="cx")
    rng = np.random.default_rng(1)
    draws = [d.draw(rng) for _ in range(200)]
    assert all(0.8 <= v <= 1.2 for v in draws)


def test_lognormal_path_draws_are_strictly_positive():
    d = ens.lognormal_path("aero.cx_scale", 0.0, 0.3, name="cx")
    rng = np.random.default_rng(2)
    draws = [d.draw(rng) for _ in range(200)]
    assert all(v > 0.0 for v in draws)


def test_lognormal_path_clip_min_is_honoured():
    d = ens.lognormal_path("aero.cx_scale", 0.0, 2.0, name="cx", clip_min=0.5)
    rng = np.random.default_rng(3)
    draws = [d.draw(rng) for _ in range(500)]
    assert min(draws) >= 0.5


def test_airframe_mass_clips_at_a_small_positive_floor():
    d = ens.airframe_mass(mean_kg=0.0, sigma_kg=0.0)  # degenerate draw of 0.0 -> clipped
    assert d.stage == "scenario"
    rng = np.random.default_rng(0)
    assert d.draw(rng) > 0.0


def test_airframe_cg_sets_the_nested_station():
    d = ens.airframe_cg(mean_m=0.4, sigma_m=0.0)
    sc2 = d.apply(_BASE_SCENARIO, 0.4)
    assert sc2.rocket.airframe.l == 0.4


def test_wind_speed_dir_returns_two_params_stage_dispersions():
    speed, direction = ens.wind_speed_dir(5.0, 1.0, 270.0, 10.0)
    assert speed.stage == "params"
    assert direction.stage == "params"
    sc2 = speed.apply(_BASE_SCENARIO, 6.0)
    sc2 = direction.apply(sc2, 280.0)
    cfg = assemble(sc2)
    assert cfg.params.wind.ref_ms == 6.0
    assert cfg.params.wind.dir_deg == 280.0


def test_wind_speed_dir_clips_speed_at_zero():
    speed, _direction = ens.wind_speed_dir(0.0, 0.0, 0.0, 0.0)
    rng = np.random.default_rng(0)
    assert speed.draw(rng) >= 0.0


# ----------------------------------------------------------------------
# run_ensemble: reproducibility, worker-count independence, statistics,
# failure handling.
# ----------------------------------------------------------------------


def test_same_seed_gives_the_same_table():
    d = ens.normal_path("aero.cx_scale", 1.0, 0.05, name="cx")
    r1 = ens.run_ensemble(_BASE_SCENARIO, [d], n=10, seed=42, evaluate=_eval_cx_scale, workers=1)
    r2 = ens.run_ensemble(_BASE_SCENARIO, [d], n=10, seed=42, evaluate=_eval_cx_scale, workers=1)
    assert np.array_equal(r1.table, r2.table)


def test_different_seed_gives_a_different_table():
    d = ens.normal_path("aero.cx_scale", 1.0, 0.05, name="cx")
    r1 = ens.run_ensemble(_BASE_SCENARIO, [d], n=10, seed=42, evaluate=_eval_cx_scale, workers=1)
    r2 = ens.run_ensemble(_BASE_SCENARIO, [d], n=10, seed=43, evaluate=_eval_cx_scale, workers=1)
    assert not np.array_equal(r1.table["cx"], r2.table["cx"])


def test_workers_1_equals_workers_4():
    """The ticket's own reproducibility test: splitting the SAME samples
    across worker processes must not change which random stream backs which
    sample index (spawn-safe: `_eval_cx_scale` is a top-level function)."""
    d = ens.normal_path("aero.cx_scale", 1.0, 0.05, name="cx")
    r1 = ens.run_ensemble(_BASE_SCENARIO, [d], n=8, seed=7, evaluate=_eval_cx_scale, workers=1)
    r4 = ens.run_ensemble(_BASE_SCENARIO, [d], n=8, seed=7, evaluate=_eval_cx_scale, workers=4)
    assert np.array_equal(r1.table, r4.table)


def test_spawn_safe_process_pool_executor():
    """Explicit `workers=2` exercise of the `ProcessPoolExecutor` path with
    a module-level `evaluate` (Windows `spawn`-safe, see module docstring)."""
    d = ens.normal_path("aero.cx_scale", 1.0, 0.02, name="cx")
    r = ens.run_ensemble(_BASE_SCENARIO, [d], n=6, seed=5, evaluate=_eval_cx_scale, workers=2)
    assert r.table.shape == (6,)
    assert not np.any(r.table["error"])


def test_sample_statistics_match_the_requested_mean_and_sigma():
    mean, sigma, n = 2.0, 0.3, 2000
    d = ens.normal_path("aero.cx_scale", mean, sigma, name="cx")
    r = ens.run_ensemble(_BASE_SCENARIO, [d], n=n, seed=123, evaluate=_eval_cx_scale, workers=1)
    drawn = r.table["cx"]
    se_mean = sigma / math.sqrt(n)
    se_std = sigma / math.sqrt(2.0 * (n - 1))
    assert abs(float(drawn.mean()) - mean) < 3.0 * se_mean
    assert abs(float(drawn.std(ddof=1)) - sigma) < 3.0 * se_std


def test_failed_sample_is_recorded_as_nan_not_fatal():
    d = ens.uniform_path("aero.cx_scale", 0.9, 1.2, name="cx")
    r = ens.run_ensemble(_BASE_SCENARIO, [d], n=40, seed=99, evaluate=_eval_flaky_above_threshold, workers=1)
    failed = r.table["error"] != ""
    assert failed.any()       # some draws in (1.05, 1.2] must have failed
    assert not failed.all()   # and some in [0.9, 1.05] must have succeeded
    assert np.all(np.isnan(r.table["cx_scale"][failed]))
    assert np.all(~np.isnan(r.table["cx_scale"][~failed]))
    assert r.n_failed == int(failed.sum())


def test_duplicate_dispersion_name_raises():
    d1 = ens.normal_path("aero.cx_scale", 1.0, 0.01, name="x")
    d2 = ens.uniform_path("thrust.k_J", 0.9, 1.1, name="x")
    with pytest.raises(ValueError):
        ens.run_ensemble(_BASE_SCENARIO, [d1, d2], n=3, seed=1, evaluate=_eval_cx_scale, workers=1)


def test_dispersion_name_colliding_with_reserved_column_raises():
    d = ens.normal_path("aero.cx_scale", 1.0, 0.01, name="sample")
    with pytest.raises(ValueError):
        ens.run_ensemble(_BASE_SCENARIO, [d], n=3, seed=1, evaluate=_eval_cx_scale, workers=1)


def test_dispersion_name_colliding_with_a_metric_name_raises():
    d = ens.normal_path("aero.cx_scale", 1.0, 0.01, name="cx_scale")  # same key _eval_cx_scale returns
    with pytest.raises(ValueError):
        ens.run_ensemble(_BASE_SCENARIO, [d], n=3, seed=1, evaluate=_eval_cx_scale, workers=1)


def test_result_shape_and_percentile_summary():
    d = ens.normal_path("aero.cx_scale", 1.0, 0.1, name="cx")
    r = ens.run_ensemble(_BASE_SCENARIO, [d], n=50, seed=3, evaluate=_eval_cx_scale, workers=1)
    assert r.table.shape == (50,)
    assert r.dispersion_names == ("cx",)
    assert r.metric_names == ("cx_scale",)
    assert set(r.percentiles["cx_scale"].keys()) == set(ens._DEFAULT_PERCENTILES)
    assert r.percentiles["cx_scale"][50.0] == pytest.approx(float(np.median(r.table["cx_scale"])), rel=1e-9)


def test_save_csv_writes_a_header_and_one_row_per_sample(tmp_path):
    d = ens.normal_path("aero.cx_scale", 1.0, 0.05, name="cx")
    r = ens.run_ensemble(_BASE_SCENARIO, [d], n=4, seed=11, evaluate=_eval_cx_scale, workers=1)
    path = tmp_path / "ensemble.csv"
    ens.save_csv(r, path)
    lines = path.read_text().strip().splitlines()
    assert lines[0].split(",") == list(r.table.dtype.names)
    assert len(lines) == 1 + 4


# ----------------------------------------------------------------------
# End-to-end sanity on a real (fast) assembled scenario, multiple
# dispersions mixing both stages.
# ----------------------------------------------------------------------


def test_scenario_and_params_stage_dispersions_compose_in_one_sample():
    mass_d = ens.airframe_mass(mean_kg=1.5, sigma_kg=0.0)        # stage="scenario"
    cx_d = ens.normal_path("aero.cx_scale", 1.0, 0.0, name="cx")  # stage="params"
    r = ens.run_ensemble(_BASE_SCENARIO, [mass_d, cx_d], n=3, seed=1, evaluate=_eval_cx_scale, workers=1)
    assert r.table.shape == (3,)
    assert np.all(r.table[mass_d.name] == 1.5)
    assert np.all(r.table["cx"] == 1.0)
    assert np.all(r.table["cx_scale"] == 1.0)
    assert not np.any(r.table["error"])

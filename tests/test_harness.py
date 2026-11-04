"""Tests for apps/control/flight_software/harness.py (Step 146, Phase
2.17, continuation of Milestone M3 -- Steps 103/107/108; dev/docs/
architecture-controller-reconciliation.md S3/S4): the first scripted,
closed-loop flight that runs a Tier-1 sampled law
(`proportional_drag`/`pi_apogee`), the real alpha-beta estimator, noisy/
lagged baro `Sensors`, and the rate-limited `Actuator(model="full")`
together, through one `harness.run_closed_loop` call.

Reuses tests.test_control's shared launch scenario (`_launch_params`/
`_launch_state`/`_LAUNCH_WEIGHT`/`_LAUNCH_AERO`) via a plain cross-test-file
import, the same house precedent tests/test_controllers.py's own module
docstring already documents.
"""

import math

import numpy as np
import pytest

import apps.control.flight_software  # noqa: F401  (import-time side effect: registers the two laws)
from apps.control.flight_software import harness
from apps.sim.engine.params import Params, with_solver
from apps.sim.engine.params import replace as params_replace
from tests.test_control import _launch_params, _launch_state, _LAUNCH_AERO, _LAUNCH_WEIGHT

# Step 107's own oracle (tests/test_controllers.py::test_full_traceability_
# comparison_table, printed values at HEAD): same demo flight, same gains,
# target=500.0, estimator_model="stub" (the default there). This module's
# test_closed_loop_matches_step107_oracle_under_noiseless_sensors cross-
# checks against these -- NOT a new pin this module invents independently.
_ORACLE_APOGEE_M = {"proportional_drag": 513.165, "pi_apogee": 490.870}
_TARGET_M = 500.0
_KP = 0.001

_LAW_EXTRA = {
    "proportional_drag": {},
    "pi_apogee": {"airbrake_ki": 0.0005},
}


def _closed_loop_params(
    airbrake_model: str,
    *,
    estimator_model: str = "alpha_beta",
    airbrake_kp: float = _KP,
    airbrake_target_apogee_m: float = _TARGET_M,
    sensors_kw: "dict | None" = None,
    actuator_kw: "dict | None" = None,
    sample_rate_hz: float = 20.0,
) -> Params:
    """The shared demo flight (tests.test_control's launch scenario) plus
    `airbrake_model`'s own oracle gains by default (`_KP`/`_TARGET_M`/
    `_LAW_EXTRA`, matching tests/test_controllers.py::test_full_
    traceability_comparison_table's own rows) and an actuator forced to
    `model="full"` (defaults: infinite rates, i.e. the SAME zero-order
    hold `model="ideal"` gives, per tests/test_actuator.py's own
    test_full_actuator_with_infinite_rates_reproduces_the_legacy_sampled_
    flight) -- `actuator_kw` overrides individual fields (e.g. a tight
    `rate_open`). `sensors_kw` is `None` by default (every `Sensors` field
    stays at its own all-zero/noiseless default, D-115) -- fields are only
    set when a test explicitly wants noise/lag/quantisation active.
    `airbrake_kp`/`airbrake_target_apogee_m` can be overridden away from
    the oracle's own gentle gain -- e.g. an engineered, always-saturating
    command (`kp=1.0, target=0.0`) that keeps the predicted-apogee error
    unambiguously huge and positive for the whole coast, used by the
    rate-limit regression tests below to get a clean step instead of the
    oracle's own small, non-saturating command.
    """
    control_kw = dict(
        airbrake_kp=airbrake_kp, airbrake_target_apogee_m=airbrake_target_apogee_m,
        airbrake_Cd=1.0, airbrake_S_max=0.05, onboard_mass=_LAUNCH_WEIGHT.m,
        onboard_CdA0=_LAUNCH_AERO.S * _LAUNCH_AERO.C_x, onboard_rho0=1.225,
        estimator_model=estimator_model, **_LAW_EXTRA[airbrake_model],
    )
    p = _launch_params(airbrake_model=airbrake_model, **control_kw)
    changes = {"actuator.model": "full"}
    changes.update({f"actuator.{k}": v for k, v in (actuator_kw or {}).items()})
    changes.update({f"sensors.{k}": v for k, v in (sensors_kw or {}).items()})
    p = params_replace(p, changes)
    return with_solver(p, method="rk4", sample_rate_hz=sample_rate_hz)


# ----------------------------------------------------------------------
# Test 1 (S4 Tests-first, item 1): all four pieces active, completes
# without error, finite apogee -- for BOTH registered laws.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("law", ["proportional_drag", "pi_apogee"])
def test_closed_loop_with_all_four_pieces_active_completes_and_reports_finite_apogee(law):
    s0 = _launch_state()
    p = _closed_loop_params(
        law,
        sensors_kw=dict(baro_sigma_m=0.3, baro_tau_s=0.05, baro_resolution_m=0.1),
        actuator_kw=dict(rate_open=2.0, rate_close=2.0),
    )
    result = harness.run_closed_loop(p, s0)
    assert result.result.events["apogee"] is not None
    assert math.isfinite(result.metrics["apogee_m"])
    assert math.isfinite(result.metrics["apogee_error_m"])


# ----------------------------------------------------------------------
# Test 2 (S4 Tests-first, item 2): Sensors() all-zero (noiseless) is close
# to Step 107's own oracle for the same law -- a sanity cross-check, not a
# new pin.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("law", ["proportional_drag", "pi_apogee"])
def test_closed_loop_matches_step107_oracle_under_noiseless_sensors(law):
    s0 = _launch_state()
    # sensors_kw=None -> Sensors() all-zero defaults; actuator_kw=None ->
    # "full" with the default infinite rates, bit-for-bit equivalent to
    # "ideal" (test_actuator.py's own acceptance test) -- isolates the one
    # variable this cross-check is actually about: estimator_model=
    # "alpha_beta" in place of Step 107's own "stub" default.
    p = _closed_loop_params(law)
    result = harness.run_closed_loop(p, s0)
    assert result.metrics["apogee_m"] == pytest.approx(_ORACLE_APOGEE_M[law], abs=15.0)


# ----------------------------------------------------------------------
# Test 3 (S4 Tests-first, item 3): a deliberately tight actuator rate
# visibly lags the commanded fraction -- a real rate-limit/saturation
# regression through the harness, not just "it runs".
# ----------------------------------------------------------------------


def test_tight_actuator_rate_lags_behind_a_fast_actuator_on_the_same_flight():
    """`kp=1.0, target=0.0` (see `_closed_loop_params`'s own docstring)
    makes the predicted-apogee error unambiguously huge and positive for
    the whole coast window, so the registered law's own raw command clips
    to exactly `1.0` throughout -- a clean step, the simplest input that
    makes "the rate-limited actuator lags the commanded fraction" directly
    observable through the harness (not `apps/sim/engine/`'s own built-in
    `"full"` law, which test_actuator.py already covers)."""
    s0 = _launch_state()
    saturating = dict(airbrake_kp=1.0, airbrake_target_apogee_m=0.0)
    tight = harness.run_closed_loop(
        _closed_loop_params("proportional_drag", actuator_kw=dict(rate_open=0.2, rate_close=0.2), **saturating), s0,
    )
    fast = harness.run_closed_loop(
        _closed_loop_params("proportional_drag", actuator_kw=dict(rate_open=1.0e6, rate_close=1.0e6), **saturating),
        s0,
    )

    # The fast (near-instant) actuator reaches the f_max=1.0 ceiling; the
    # tight (rate_open=0.2 fraction/s) one never does on this flight -- a
    # direct, deterministic consequence of `control._ramp`'s own closed
    # form (D-114), not an empirical tuning accident.
    assert fast.metrics["actuator_saturation_fraction"] == pytest.approx(1.0)
    assert np.max(fast.actuator_f) == pytest.approx(1.0)
    assert np.max(tight.actuator_f) < 1.0
    assert tight.metrics["actuator_saturation_fraction"] < fast.metrics["actuator_saturation_fraction"]
    # (NOT asserting tight's "actuator_travel" < fast's here: the fast
    # actuator's own opening transition completes within a single sample
    # tick, and that one tick can land just outside the metrics' own
    # `[burnout, apogee]` window depending on exactly where the window's
    # continuous boundary falls on the discrete tick grid -- a real,
    # documented edge effect of this specific "near-instantaneous open"
    # scenario, not a rate-limit regression. `actuator_travel`'s own
    # monotonicity-in-rate is covered on the GENTLE gain instead, in
    # test_comparison_table_across_gain_noise_and_actuator_rate_is_
    # reproducible below, where the opening transition spans many ticks.)

    # Pointwise, up to the EARLIER of the two runs' own apogee times (the
    # brake's own drag changes the trajectory, so the two runs' apogee
    # times are not identical -- comparing beyond the earlier one would
    # compare "still opening" against "already closing again"): the fast
    # trajectory is never behind the tight one, and is strictly ahead
    # somewhere -- the lag itself, directly observed.
    t_cmp = min(tight.result.events["apogee"], fast.result.events["apogee"])
    n = min(tight.actuator_f.size, fast.actuator_f.size)
    mask = tight.actuator_t[:n] <= t_cmp
    tight_f, fast_f = tight.actuator_f[:n][mask], fast.actuator_f[:n][mask]
    assert bool(np.all(fast_f >= tight_f - 1e-9))
    assert np.any(fast_f > tight_f + 1e-6)


# ----------------------------------------------------------------------
# Test 4 (S4 Tests-first, item 4): the metrics dict's own shape --
# apogee error vs target, saturation fraction, total travel -- reusing
# apps.analysis.ensemble's flat dict[str, float] convention.
# ----------------------------------------------------------------------


def test_metrics_dict_has_the_four_documented_keys_in_the_ensemble_evaluate_shape():
    s0 = _launch_state()
    p = _closed_loop_params(
        "pi_apogee",
        sensors_kw=dict(baro_sigma_m=0.2),
        actuator_kw=dict(rate_open=1.5, rate_close=1.5),
    )
    result = harness.run_closed_loop(p, s0)
    m = result.metrics

    assert set(m) == {"apogee_m", "apogee_error_m", "actuator_saturation_fraction", "actuator_travel"}
    assert all(isinstance(v, float) for v in m.values())
    assert m["apogee_error_m"] == pytest.approx(m["apogee_m"] - _TARGET_M)
    assert 0.0 <= m["actuator_saturation_fraction"] <= 1.0
    assert m["actuator_travel"] >= 0.0


# ----------------------------------------------------------------------
# Acceptance (S4): a documented, reproducible comparison table -- gain
# (fixed here, both registered laws instead), noise level, and actuator
# rate -> apogee error, saturation fraction -- on the existing demo
# flight. Noise rows use a fixed seed (`Sensors.baro_seed`, the default
# 0) so this table is reproducible run to run, same as every other
# printed-table test in this suite (e.g.
# tests/test_controllers.py::test_full_traceability_comparison_table).
# ----------------------------------------------------------------------


def test_comparison_table_across_gain_noise_and_actuator_rate_is_reproducible():
    """S4's own acceptance bullet: "gain / noise level / actuator rate ->
    apogee error, saturation fraction" on the existing demo flight. Two
    `(kp, target)` points: the oracle's own gentle gain (`_KP`/`_TARGET_M`)
    and the engineered always-saturating one `test_tight_actuator_rate_
    lags_behind...` above uses -- the latter is also where the rate
    dimension's effect on `saturation_fraction`/`actuator_travel` is
    deterministic enough to assert on directly (see that test's own
    docstring for why the gentle gain alone does not saturate the brake on
    this flight, so comparing rates there would mostly be comparing noise,
    not the rate limit itself).
    """
    s0 = _launch_state()
    gains = {"gentle (oracle)": dict(airbrake_kp=_KP, airbrake_target_apogee_m=_TARGET_M),
              "saturating (engineered)": dict(airbrake_kp=1.0, airbrake_target_apogee_m=0.0)}
    rows = []
    for law in ("proportional_drag", "pi_apogee"):
        for gain_name, gain_kw in gains.items():
            for baro_sigma_m in (0.0, 0.5):
                for rate in (0.2, 50.0):
                    p = _closed_loop_params(
                        law, sensors_kw=dict(baro_sigma_m=baro_sigma_m),
                        actuator_kw=dict(rate_open=rate, rate_close=rate), **gain_kw,
                    )
                    m = harness.run_closed_loop(p, s0).metrics
                    rows.append((law, gain_name, baro_sigma_m, rate, m["apogee_error_m"],
                                 m["actuator_saturation_fraction"], m["actuator_travel"]))

    print("\nStep 146 comparison table (law, gain, baro_sigma_m, actuator_rate -> "
          "apogee_error_m, saturation_fraction, actuator_travel):")
    for law, gain_name, sigma, rate, err, sat, travel in rows:
        print(f"  {law:<18s} {gain_name:<24s} sigma={sigma:4.1f}  rate={rate:6.1f}"
              f"  err={err:9.3f}  sat={sat:5.3f}  travel={travel:5.3f}")

    for _law, _gain, _sigma, _rate, err, sat, travel in rows:
        assert math.isfinite(err)
        assert 0.0 <= sat <= 1.0
        assert travel >= 0.0

    # The engineered-saturating gain's own rate dimension is deterministic
    # (same always-1.0 command, `_ramp`'s own bound): the tighter rate_open
    # never saturates MORE than the looser one, same law, same noise. (Not
    # comparing `actuator_travel` on this gain -- see
    # test_tight_actuator_rate_lags_behind...'s own docstring for why its
    # near-instant opening transition makes that specific comparison
    # sensitive to the tick grid, not a rate-limit regression.)
    by_key = {(law, gain, sigma, rate): (sat, travel) for law, gain, sigma, rate, _err, sat, travel in rows}
    for law in ("proportional_drag", "pi_apogee"):
        for sigma in (0.0, 0.5):
            sat_tight, _ = by_key[(law, "saturating (engineered)", sigma, 0.2)]
            sat_fast, _ = by_key[(law, "saturating (engineered)", sigma, 50.0)]
            assert sat_tight <= sat_fast

            # The gentle (oracle) gain's own opening transition spans many
            # ticks at either rate, so BOTH metrics are monotonic in rate
            # there -- the comparison `actuator_travel` is meaningful for.
            _, travel_tight_gentle = by_key[(law, "gentle (oracle)", sigma, 0.2)]
            _, travel_fast_gentle = by_key[(law, "gentle (oracle)", sigma, 50.0)]
            assert travel_tight_gentle <= travel_fast_gentle

    # Reproducibility: re-running the exact same (fixed-seed) noisy
    # configuration twice gives the identical apogee error, bit-for-bit --
    # no hidden wall-clock/process-order dependence (the module docstring's
    # own claim about `sensors.measure`'s RNG keying).
    p_noisy = _closed_loop_params(
        "pi_apogee", sensors_kw=dict(baro_sigma_m=0.5), actuator_kw=dict(rate_open=0.2, rate_close=0.2),
    )
    err1 = harness.run_closed_loop(p_noisy, s0).metrics["apogee_error_m"]
    err2 = harness.run_closed_loop(p_noisy, s0).metrics["apogee_error_m"]
    assert err1 == err2

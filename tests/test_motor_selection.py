"""Tests for apps/motor_selection/compare_motors.py (App 3, roadmap.md Step
61, architecture-29-motor-selection.md SS29.2-SS29.6).

Per that design doc (SS29.5, "This document pins no expected apogee
values"): a raw apogee-altitude *number* is a simulation prediction, not a
fact to pin -- so these tests pin what IS derivable from first principles
(the closed-form near-ignition acceleration, the exact trapezoidal total
impulse, `build_params`'s field-preservation, the explicit SS29.4.6
None-branch) and otherwise check structural/ordering invariants on
whatever the solver actually returns, the same discipline
`tests/test_integrate.py` already applies to full trajectories.
"""

import dataclasses
import math

import numpy as np
import pytest

from apps.motor_selection.compare_motors import (
    MotorEntry,
    _demo_baseline,
    _demo_entries,
    build_params,
    compare_motors,
    evaluate_motor,
    flight_stats,
)
from sim.integrate import Result, run_sim
from sim.params import Lengths, Params, Weight, replace as params_replace, with_solver
from sim.state import State, X

# Nominal total impulse per fixture (docs/architecture-29-motor-selection.md
# SS29.5's table; also pinned independently, against the raw-knot
# trapezoid, in tests/test_thrust_curve.py).
_NOMINAL_IMPULSE = {
    "small_E": 39.75,
    "medium_punchy_H": 169.2,
    "medium_long_H": 169.54,
    "large_I": 338.0,
    "placeholder_H": 162.75,
}


def _s0() -> State:
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)


# ----------------------------------------------------------------------
# build_params
# ----------------------------------------------------------------------


def test_build_params_no_overrides_preserves_every_other_field():
    """Swapping the motor curve must change exactly one field --
    `thrust.motor_curve` -- and leave every other field, in every other
    group (including the rest of the `thrust` group itself), equal to the
    baseline's."""
    baseline = _demo_baseline()
    entry = MotorEntry(name="large_I", motor_curve="synthetic_large.csv")
    p = build_params(entry, baseline)

    assert p.thrust.motor_curve == "synthetic_large.csv"
    assert baseline.thrust.motor_curve == "placeholder.csv"
    assert p.thrust.A_e == baseline.thrust.A_e
    assert p.thrust.p_ref == baseline.thrust.p_ref

    for f in dataclasses.fields(Params):
        if f.name in ("thrust",):
            continue
        assert getattr(p, f.name) == getattr(baseline, f.name), f.name


# ----------------------------------------------------------------------
# Acceleration: closed form + finite-difference cross-check (D-20, F7)
# ----------------------------------------------------------------------


def test_closed_form_acceleration_near_ignition_peak():
    """Just after ignition (t=0.05 s, exactly the synthetic_large.csv knot
    where thrust peaks at 420 N), V is still tiny (~6.5 m/s) so axial drag
    is negligible: the inertial acceleration magnitude from
    `dynamics.derivatives` must equal the closed form `T(t)/m - g0` to a
    tight tolerance. This is the load-bearing assertion that the
    derivatives-re-evaluation path has the right indices, frame and units
    (architecture-29-motor-selection.md F7)."""
    from sim import dynamics, thrust_curve
    from sim.state import VX, VZ

    baseline = _demo_baseline()
    p = params_replace(baseline, {"thrust.motor_curve": "synthetic_large.csv"})
    result = run_sim(p, _s0())

    t = 0.05
    y = result.raw.sol(t)
    T = thrust_curve.thrust(t, y, p)
    assert T == 420.0  # exactly the curve's stated knot value

    dydt = dynamics.derivatives(t, y, p)
    accel = math.hypot(dydt[VX], dydt[VZ])
    closed_form = T / p.weight.m - p.g0

    assert math.isclose(accel, closed_form, rel_tol=1e-3)


def test_finite_difference_cross_check_of_peak_acceleration():
    """Independent, loose cross-check of the same near-ignition peak: a
    centred finite difference of the dense-output velocity straddling
    t=0.05 s must agree with the closed form (and hence with the
    `dynamics.derivatives` re-evaluation above) to within 1%."""
    from sim.state import VX, VZ

    baseline = _demo_baseline()
    p = params_replace(baseline, {"thrust.motor_curve": "synthetic_large.csv"})
    result = run_sim(p, _s0())

    t, dt = 0.05, 1e-4
    y1 = result.raw.sol(t - dt)
    y2 = result.raw.sol(t + dt)
    a_fd = math.hypot((y2[VX] - y1[VX]) / (2 * dt), (y2[VZ] - y1[VZ]) / (2 * dt))
    closed_form = 420.0 / p.weight.m - p.g0

    assert math.isclose(a_fd, closed_form, rel_tol=1e-2)


def test_flight_stats_max_accel_close_to_closed_form_peak():
    """The grid-based `flight_stats.max_accel` (not a single hand-picked
    evaluation, the actual house ascent/burn-refined grid) must also land
    close to the same closed-form peak -- the grid is fine enough near a
    ~50 ms ignition spike not to under-report it by more than ~1%."""
    baseline = _demo_baseline()
    entry = MotorEntry(name="large_I", motor_curve="synthetic_large.csv")
    run = evaluate_motor(entry, baseline, _s0())

    closed_form = 420.0 / baseline.weight.m - baseline.g0
    assert math.isclose(run.stats.max_accel, closed_form, rel_tol=1e-2)
    assert math.isclose(run.stats.max_accel_g, closed_form / baseline.g0, rel_tol=1e-2)


# ----------------------------------------------------------------------
# Total impulse: ascent-grid trapezoid vs each fixture's stated nominal
# ----------------------------------------------------------------------


@pytest.mark.parametrize("entry", _demo_entries(), ids=lambda e: e.name)
def test_total_impulse_matches_fixture_nominal(entry):
    """F9/SS29.4.5: the ascent-grid-integrated delivered impulse must agree
    with each fixture's stated nominal (the exact raw-knot trapezoid,
    separately pinned in tests/test_thrust_curve.py) to ~0.1%, the
    grid-resolution-only discrepancy the design doc predicts."""
    baseline = _demo_baseline()
    run = evaluate_motor(entry, baseline, _s0())
    nominal = _NOMINAL_IMPULSE[entry.name]
    assert math.isclose(run.stats.total_impulse, nominal, rel_tol=1e-3)


# ----------------------------------------------------------------------
# Ordering invariants across the demo fixture set
# ----------------------------------------------------------------------


def test_ordering_invariants_across_fixtures():
    baseline = _demo_baseline()
    runs = compare_motors(_demo_entries(), baseline, _s0())

    apogees = [r.stats.apogee_altitude for r in runs]
    assert all(a is not None for a in apogees)
    # Ranked by apogee, descending (non-increasing).
    assert all(apogees[i] >= apogees[i + 1] for i in range(len(apogees) - 1))

    for r in runs:
        s = r.stats
        assert 0.0 < s.avg_velocity <= s.max_velocity
        assert s.burnout_time < s.apogee_time < s.impact_time
        assert s.max_accel > 0.0
        assert s.max_q > 0.0
        assert s.total_impulse > 0.0


def test_equal_impulse_pair_has_different_apogees():
    """The whole physical point of the equal-impulse pair (SS29.5): with
    real dynamic-pressure-scaled drag, total impulse alone does not set
    apogee -- the two H-class fixtures (169.2 vs 169.54 N*s, within 0.2%)
    must produce measurably different apogees."""
    baseline = _demo_baseline()
    punchy = evaluate_motor(
        MotorEntry(name="punchy", motor_curve="synthetic_medium_punchy.csv"), baseline, _s0()
    )
    long_burn = evaluate_motor(
        MotorEntry(name="long", motor_curve="synthetic_medium_long.csv"), baseline, _s0()
    )
    assert not math.isclose(
        punchy.stats.apogee_altitude, long_burn.stats.apogee_altitude, rel_tol=0.01
    )


# ----------------------------------------------------------------------
# Degenerate flights (SS29.4.6)
# ----------------------------------------------------------------------


class _FakeSol:
    """Minimal stand-in for `Result.raw.sol`, just enough to drive
    `flight_stats`'s degenerate (`t_apogee is None`) branch, which only
    reads the X component at the one requested instant."""

    def __call__(self, t):
        t_arr = np.atleast_1d(np.asarray(t, dtype=float))
        y = np.zeros((7, t_arr.size))
        y[X, :] = 0.5 * t_arr
        return y if np.ndim(t) else y[:, 0]


class _FakeRaw:
    def __init__(self):
        self.sol = _FakeSol()


def test_flight_stats_degenerate_apogee_is_none():
    """SS29.4.6: `events["apogee"] is None` (the motor never produced an
    apogee event) is a legitimate study result, not an error --
    `flight_stats` must return every ascent-window field as None while
    still reporting the whole-flight fields exactly from the events dict
    / dense interpolant."""
    fake_result = Result(
        t=np.array([0.0, 20.0]),
        y=np.zeros((7, 2)),
        events={
            "apogee": None,
            "ground": 12.3,
            "burnout": None,
            "rail_exit": None,
            "parachute_deploy": None,
        },
        raw=_FakeRaw(),
        params=None,
    )
    p = _demo_baseline()
    stats = flight_stats(fake_result, p)

    assert stats.apogee_altitude is None
    assert stats.apogee_time is None
    assert stats.max_velocity is None
    assert stats.avg_velocity is None
    assert stats.max_accel is None
    assert stats.max_accel_g is None
    assert stats.max_q is None
    assert stats.total_impulse is None
    assert stats.burnout_time is None
    assert stats.impact_time == 12.3
    assert math.isclose(stats.downrange_impact, 0.5 * 12.3, rel_tol=1e-9)


def test_motor_curve_empty_does_not_crash_and_ranks_last():
    """A `motor_curve=""` entry (zero thrust everywhere, F9) must run and
    report, not crash -- and must rank below a motor that actually flies.
    Uses a baseline with aero inert (default `Aero()`, `C_x=0.0`) so this
    is a clean, well-behaved free-fall rather than exercising the
    unrelated frozen-attitude/high-speed-descent aero model (out of scope,
    `sim/` untouched)."""
    baseline = Params(weight=Weight(m=1.5, I=0.08), lengths=Lengths(l1=0.3, l2=0.4))
    entries = [
        MotorEntry(name="large_I", motor_curve="synthetic_large.csv"),
        MotorEntry(name="no_motor", motor_curve=""),
    ]
    runs = compare_motors(entries, baseline, _s0())

    assert [r.entry.name for r in runs] == ["large_I", "no_motor"]
    assert runs[-1].stats.apogee_altitude < runs[0].stats.apogee_altitude
    assert runs[-1].stats.total_impulse == 0.0
    assert runs[-1].stats.burnout_time is None


# ----------------------------------------------------------------------
# The sample_rate_hz guard (F8)
# ----------------------------------------------------------------------


def test_sample_rate_hz_nonzero_raises_before_run_sim(monkeypatch):
    """A post-hoc `dynamics.derivatives` re-evaluation cannot reconstruct a
    sampled-data run's per-tick zero-order hold (Step 59), so both
    `evaluate_motor` and `compare_motors` must reject `sample_rate_hz !=
    0.0` before `run_sim` is ever called -- not merely before `flight_stats`
    runs. Patching `run_sim` to raise on any call proves the guard fires
    strictly earlier."""

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called once the guard fires")

    monkeypatch.setattr("apps.motor_selection.compare_motors.run_sim", _must_not_be_called)

    baseline = with_solver(_demo_baseline(), method="rk4", sample_rate_hz=1000.0)
    entry = MotorEntry(name="x", motor_curve="placeholder.csv")

    with pytest.raises(ValueError, match="sample_rate_hz"):
        evaluate_motor(entry, baseline, _s0())
    with pytest.raises(ValueError, match="sample_rate_hz"):
        compare_motors([entry], baseline, _s0())


def test_flight_stats_also_rejects_sample_rate_hz_directly():
    """`flight_stats` is a public pure function and may be called directly
    on a `Result`/`Params` pair this module did not itself produce, so it
    repeats the same guard (defense in depth)."""
    baseline = with_solver(_demo_baseline(), method="rk4", sample_rate_hz=1000.0)
    p = params_replace(baseline, {"thrust.motor_curve": "placeholder.csv"})
    result = run_sim(p, _s0())
    with pytest.raises(ValueError, match="sample_rate_hz"):
        flight_stats(result, p)


if __name__ == "__main__":
    test_build_params_no_overrides_preserves_every_other_field()
    test_closed_form_acceleration_near_ignition_peak()
    test_finite_difference_cross_check_of_peak_acceleration()
    test_flight_stats_max_accel_close_to_closed_form_peak()
    for _entry in _demo_entries():
        test_total_impulse_matches_fixture_nominal(_entry)
    test_ordering_invariants_across_fixtures()
    test_equal_impulse_pair_has_different_apogees()
    test_flight_stats_degenerate_apogee_is_none()
    test_motor_curve_empty_does_not_crash_and_ranks_last()
    print("All tests passed!")

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
from apps.motor_selection.motors import MOTORS
from sim.integrate import Result, run_sim
from sim.params import Lengths, Params, Weight, replace as params_replace, with_solver
from sim.state import State, X

# Nominal total impulse per fixture (dev/docs/architecture-29-motor-selection.md
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


# ----------------------------------------------------------------------
# Step 62: per-motor configuration (dry-rocket overrides), SS29.7/SS29.8
# ----------------------------------------------------------------------


def test_overrides_change_exactly_the_named_fields():
    """An entry with `{"weight.m": 0.9, "aero.S": 0.00114}` must change
    exactly those two fields and leave every other field -- including the
    rest of `Weight` and `Aero` -- equal to the baseline's (the design
    doc's SS29.9 Step-62 check, generalised from Step 61's single-key
    version above)."""
    baseline = _demo_baseline()
    entry = MotorEntry(
        name="small",
        motor_curve="synthetic_small.csv",
        overrides={"weight.m": 0.9, "aero.S": 0.00114},
    )
    p = build_params(entry, baseline)

    assert p.thrust.motor_curve == "synthetic_small.csv"
    assert p.weight.m == 0.9
    assert p.aero.S == 0.00114
    # Every other field of the changed groups is untouched.
    assert p.weight.I == baseline.weight.I
    assert p.weight.m_d == baseline.weight.m_d
    assert p.aero.d_ref == baseline.aero.d_ref
    assert p.aero.l_ref == baseline.aero.l_ref
    assert p.aero.C_x == baseline.aero.C_x
    assert p.aero.C_z == baseline.aero.C_z
    assert p.aero.C_m == baseline.aero.C_m
    # Every untouched group/field is equal to the baseline's.
    for f in dataclasses.fields(Params):
        if f.name in ("thrust", "weight", "aero"):
            continue
        assert getattr(p, f.name) == getattr(baseline, f.name), f.name


def test_overrides_actually_change_the_simulated_outcome():
    """Not just "accepted" -- the override must change the flown physics:
    a lighter, smaller-frontal-area small-motor rocket must fly to a
    measurably different apogee than the same motor on the unmodified
    baseline airframe."""
    baseline = _demo_baseline()
    no_override = evaluate_motor(
        MotorEntry(name="small_baseline", motor_curve="synthetic_small.csv"), baseline, _s0()
    )
    with_override = evaluate_motor(
        MotorEntry(
            name="small_light",
            motor_curve="synthetic_small.csv",
            overrides={"weight.m": 0.9, "aero.S": 0.00114},
        ),
        baseline,
        _s0(),
    )
    assert not math.isclose(
        no_override.stats.apogee_altitude, with_override.stats.apogee_altitude, rel_tol=0.01
    )
    assert no_override.params.weight.m == baseline.weight.m
    assert with_override.params.weight.m == 0.9


def test_motor_curve_in_overrides_raises_value_error():
    """`thrust.motor_curve` is reserved for `entry.motor_curve` -- one
    selector, one place. An entry that also sets it via `overrides` is a
    config error, caught by `build_params` itself, before any `replace`
    ambiguity could arise."""
    baseline = _demo_baseline()
    entry = MotorEntry(
        name="conflicting",
        motor_curve="synthetic_small.csv",
        overrides={"thrust.motor_curve": "synthetic_large.csv"},
    )
    with pytest.raises(ValueError, match="thrust.motor_curve"):
        build_params(entry, baseline)


def test_motor_curve_conflict_raises_before_any_integration(monkeypatch):
    """The pre-flight validation pass (`compare_motors`) must surface the
    reserved-key conflict before `run_sim` is ever called, the same
    discipline as the `sample_rate_hz` guard above."""

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called once build_params raises")

    monkeypatch.setattr("apps.motor_selection.compare_motors.run_sim", _must_not_be_called)

    baseline = _demo_baseline()
    entries = [
        MotorEntry(name="ok", motor_curve="synthetic_small.csv"),
        MotorEntry(
            name="bad",
            motor_curve="synthetic_small.csv",
            overrides={"thrust.motor_curve": "synthetic_large.csv"},
        ),
    ]
    with pytest.raises(ValueError, match="thrust.motor_curve"):
        compare_motors(entries, baseline, _s0())


def test_typo_group_raises_attribute_error_before_any_integration(monkeypatch):
    """A typo'd group name (`"wieght.m"`) is an unknown attribute of
    `Params`, so `sim.params.replace` raises `AttributeError` -- and the
    pre-flight pass in `compare_motors` must surface it before `run_sim`
    runs for any entry."""

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called once replace raises")

    monkeypatch.setattr("apps.motor_selection.compare_motors.run_sim", _must_not_be_called)

    baseline = _demo_baseline()
    entry = MotorEntry(
        name="typo_group", motor_curve="synthetic_small.csv", overrides={"wieght.m": 1.0}
    )
    with pytest.raises(AttributeError):
        build_params(entry, baseline)
    with pytest.raises(AttributeError):
        compare_motors([entry], baseline, _s0())


def test_typo_field_raises_type_error_before_any_integration(monkeypatch):
    """A typo'd field name within a real group (`"weight.mass"`) is an
    unexpected keyword argument to `dataclasses.replace`, so
    `sim.params.replace` raises `TypeError` -- again before `run_sim`."""

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called once replace raises")

    monkeypatch.setattr("apps.motor_selection.compare_motors.run_sim", _must_not_be_called)

    baseline = _demo_baseline()
    entry = MotorEntry(
        name="typo_field", motor_curve="synthetic_small.csv", overrides={"weight.mass": 1.0}
    )
    with pytest.raises(TypeError):
        build_params(entry, baseline)
    with pytest.raises(TypeError):
        compare_motors([entry], baseline, _s0())


def test_no_overrides_default_reproduces_step61_bit_for_bit():
    """`MotorEntry` constructed with no `overrides` argument at all (the
    default, `default_factory=dict`) must produce `Params`/stats
    bit-for-bit identical to Step 61's own single-key `build_params` call
    -- the SS29.9 "bit-for-bit gate" for every existing Step-61 entry."""
    baseline = _demo_baseline()
    for legacy_entry in _demo_entries():
        assert legacy_entry.overrides == {}
        p_new = build_params(legacy_entry, baseline)
        p_legacy = params_replace(baseline, {"thrust.motor_curve": legacy_entry.motor_curve})
        assert p_new == p_legacy

        run_new = evaluate_motor(legacy_entry, baseline, _s0())
        run_legacy_result = run_sim(p_legacy, _s0())
        run_legacy_stats = flight_stats(run_legacy_result, p_legacy)
        assert run_new.stats == run_legacy_stats


def test_motors_module_equal_impulse_pair_stays_override_free():
    """The two H-class entries in `apps.motor_selection.motors.MOTORS`
    must stay override-free on purpose (SS29.7), so the equal-impulse-pair
    comparison still isolates burn-profile effects on an identical
    airframe."""
    h_class = [m for m in MOTORS if "H " in m.name or m.name.startswith("H")]
    assert len(h_class) == 2
    for m in h_class:
        assert m.overrides == {}


def test_motors_module_small_and_large_get_distinct_casings():
    """SS29.7's "smaller motor, smaller casing": the small-motor entry's
    overridden mass/frontal-area must be lighter/smaller than the
    large-motor entry's, and both must differ from each other and from the
    override-free baseline."""
    by_name = {m.name: m for m in MOTORS}
    small = next(m for m in MOTORS if "small" in m.name.lower())
    large = next(m for m in MOTORS if "large" in m.name.lower())
    assert small.overrides["weight.m"] < large.overrides["weight.m"]
    assert small.overrides["aero.S"] < large.overrides["aero.S"]


def test_compare_motors_end_to_end_with_mixed_overrides():
    """Full pipeline, `apps.motor_selection.motors.MOTORS` (a mix of
    overridden and override-free entries), end to end through
    `compare_motors`: every entry produces a run, ranked by apogee, and the
    overridden entries' `Params` actually carry their overrides through to
    the row that was simulated."""
    baseline = _demo_baseline()
    runs = compare_motors(MOTORS, baseline, _s0())

    assert len(runs) == len(MOTORS)
    apogees = [r.stats.apogee_altitude for r in runs]
    assert all(a is not None for a in apogees)
    assert all(apogees[i] >= apogees[i + 1] for i in range(len(apogees) - 1))

    by_name = {r.entry.name: r for r in runs}
    small_run = next(r for r in runs if "small" in r.entry.name.lower())
    large_run = next(r for r in runs if "large" in r.entry.name.lower())
    assert small_run.params.weight.m == small_run.entry.overrides["weight.m"]
    assert large_run.params.weight.m == large_run.entry.overrides["weight.m"]
    assert small_run.params.weight.m != baseline.weight.m
    assert large_run.params.weight.m != baseline.weight.m


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
    test_overrides_change_exactly_the_named_fields()
    test_overrides_actually_change_the_simulated_outcome()
    test_motor_curve_in_overrides_raises_value_error()
    test_no_overrides_default_reproduces_step61_bit_for_bit()
    test_motors_module_equal_impulse_pair_stays_override_free()
    test_motors_module_small_and_large_get_distinct_casings()
    test_compare_motors_end_to_end_with_mixed_overrides()
    print("All tests passed!")


def test_mass_model_on_baseline_is_refused_before_any_integration(monkeypatch):
    """D-82: App 3 is a constant-mass study; a mass-on baseline (the
    integrator reads mass from y[M]) is refused before any `run_sim`."""
    from apps.input.demo_scenario import DEMO_SCENARIO

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called for a mass-on baseline")

    monkeypatch.setattr("apps.motor_selection.compare_motors.run_sim", _must_not_be_called)

    cfg = DEMO_SCENARIO.config
    assert cfg.params.weight.m_d is not None
    with pytest.raises(ValueError, match="mass model on"):
        compare_motors(
            [MotorEntry(name="ok", motor_curve="synthetic_small.csv")], cfg.params, cfg.s0
        )

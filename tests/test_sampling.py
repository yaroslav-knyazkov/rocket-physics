"""Tests for sim/sampling.py -- the zero-order-hold (ZOH) mechanism itself
(architecture-28-rewrite.md SS28.8; Phase 2.11 rewrite pass, Step 59).

Physics/numerics sanity checks + wiring regressions, per the project's
testing philosophy -- no fixtures, no conftest.py, plain `assert` +
`math.isclose`/numpy comparisons.

`sim/integrate.py`'s own gate/raise behaviour (`p.solver.sample_rate_hz >
0.0` requiring `method == "rk4"`; the non-integer `T_s/dt` check) is tested
in tests/test_integrate.py, next to the rest of that module's `run_sim`/
`_run_rk4` tests. This module tests the hold itself: the channel registry
and `sample()`'s `prev`-threading contract (sim/sampling.py), and the
"consumption" seam the airbrake channel exercises end to end
(sim/control.py's `airbrake_deploy_fraction`/`sample_airbrake`).
"""

import math

import numpy as np

from apps.sim.engine import control, sampling
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Actuator, Aero, Control, Lengths, Params, Thrust, Weight, with_solver
from apps.sim.engine.state import State

_MOTOR_CURVE = "placeholder.csv"  # data/motors/placeholder.csv

# Same shared launch scenario as tests/test_control.py (vertical launch
# from rest, placeholder motor curve, constant q-scaled body-axial drag --
# see that module's own docstring for why S/d_ref are required for the
# "constant" model to produce nonzero drag, Step 55).
_LAUNCH_WEIGHT = Weight(m=0.5, I=0.05)
_LAUNCH_LENGTHS = Lengths(l1=0.3, l2=0.4)
_LAUNCH_THRUST = Thrust(motor_curve=_MOTOR_CURVE)
_LAUNCH_AERO = Aero(S=0.005, d_ref=0.08, C_x=0.5, C_z=0.0, C_m=0.0)


def _launch_params(**control_kw) -> Params:
    return Params(
        weight=_LAUNCH_WEIGHT, lengths=_LAUNCH_LENGTHS, thrust=_LAUNCH_THRUST,
        aero=_LAUNCH_AERO, control=Control(**control_kw),
    )


def _launch_params_with_actuator(control_kw: dict, actuator_kw: dict) -> Params:
    return Params(
        weight=_LAUNCH_WEIGHT, lengths=_LAUNCH_LENGTHS, thrust=_LAUNCH_THRUST,
        aero=_LAUNCH_AERO, control=Control(**control_kw), actuator=Actuator(**actuator_kw),
    )


def _launch_state():
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)


# ----------------------------------------------------------------------
# sample(): the channel registry + the prev-threading contract
# ----------------------------------------------------------------------


def test_sample_returns_a_hold_with_t_sample_and_one_value_per_channel():
    """`sample(t, y, p, prev)` must return a `Hold` whose `t_sample` is
    exactly the `t` it was called with, and whose `values` dict has one
    entry per registered channel -- today, just `"airbrake"`."""
    p = _launch_params(airbrake_model="none")
    y = np.array(_launch_state())
    hold = sampling.sample(5.0, y, p, prev=None)
    assert hold.t_sample == 5.0
    assert set(hold.values.keys()) == {"airbrake"}
    assert hold.values["airbrake"] == 0.0  # "none" model, inert


def test_held_value_equals_the_live_controller_evaluated_at_the_tick_start():
    """architecture-28-rewrite.md SS28.8.2, point 2 ("the sample is taken
    at the tick's start") and the ticket's own test 5: the held value at a
    tick must equal the live, continuously-evaluated controller
    (`control._AIRBRAKE_CONTROLLERS[...]`) called at exactly that tick's
    own `(t_k, y_k)` -- not at some other instant queried later.
    """
    # Modest (non-saturating) gain, same precedent as tests/test_control.py's
    # own "intermediate values" scenario -- chosen so the live law's output
    # genuinely differs between `(t_k, y_k)` and a later, much-faster-
    # ascending `(t_later, y_later)`, rather than both saturating at 1.0
    # (which would make the ZOH check pass "by accident": a saturated law
    # looks the same whether held or re-evaluated).
    p = _launch_params(
        airbrake_model="proportional", airbrake_kp=0.0005,
        airbrake_target_apogee_m=500.0, airbrake_Cd=1.0, airbrake_S_max=0.05,
    )
    # Unpowered, ascending state -- the window where "proportional" is
    # active (same gate as tests/test_control.py's own checks).
    t_k = 5.0
    y_k = np.array(State(x=0.0, z=-500.0, vx=10.0, vz=-20.0, theta=math.pi / 2, omega=0.0))

    expected = control._AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t_k, y_k, p)
    assert 0.0 < expected < 1.0  # genuinely proportional here, not saturated either way

    hold = sampling.sample(t_k, y_k, p, prev=None)
    assert hold.values["airbrake"] == expected

    # The ZOH consumer returns exactly that held value for ANY (t, y)
    # queried later in the same tick -- it does not re-evaluate the live
    # law at the new (t, y). `y_later` ascends far faster, which (were the
    # live law re-evaluated) would push the predicted apogee, and hence
    # the commanded fraction, markedly higher.
    t_later = t_k + 0.05
    y_later = np.array(State(x=0.0, z=-500.0, vx=10.0, vz=-200.0, theta=math.pi / 2, omega=0.0))
    live_later = control._AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t_later, y_later, p)
    assert live_later != expected  # the state change genuinely matters to the live law

    assert control.airbrake_deploy_fraction(t_later, y_later, p, hold) == expected
    assert control.airbrake_deploy_fraction(t_later, y_later, p, hold) != live_later


def test_airbrake_deploy_fraction_hold_none_is_bit_for_bit_the_live_law():
    """`hold=None` (the default, every pre-Step-59 call site) must call
    through to the live, continuously-evaluated law exactly -- the ZOH
    branch in `airbrake_deploy_fraction` must never engage."""
    p = _launch_params(
        airbrake_model="proportional", airbrake_kp=1.0,
        airbrake_target_apogee_m=0.0, airbrake_Cd=1.0, airbrake_S_max=0.05,
    )
    t = 5.0
    y = np.array(State(x=0.0, z=-500.0, vx=10.0, vz=-20.0, theta=math.pi / 2, omega=0.0))
    live = control._AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t, y, p)
    assert control.airbrake_deploy_fraction(t, y, p) == live
    assert control.airbrake_deploy_fraction(t, y, p, hold=None) == live


def test_prev_is_threaded_exactly_once_per_tick_not_per_substep_or_stage():
    """The single most important assertion in Step 59
    (architecture-28-rewrite.md SS28.11's [S59] ticket): a test-only
    channel that counts its own invocations, registered locally into
    `sampling._CHANNELS` (same monkeypatch-and-restore pattern
    tests/test_control.py's Step 57 `test_aero_coeff_delta_reaches_all_
    four_consumers` already established for `control._AERO_COEFF_
    CONTROLLERS`), must see exactly one call per tick -- not one call per
    RK4 substep (there are many substeps per tick, `dt=0.01` vs.
    `sample_rate_hz=10`, i.e. 10 substeps/tick) and not one call per RK4
    stage (4x more again). `prev` genuinely threads forward tick-to-tick
    (the recorded count strictly increments by exactly 1 each call),
    proving this is the recursive `f(t_k, y_k, p, prev)` contract the
    module docstring describes, not a fresh/reset evaluation each time.

    `t_max=0.45` is deliberately NOT an exact multiple of `T_s=0.1` (there
    are 5 tick-starts strictly inside `[0, 0.45)`: t=0.0, 0.1, 0.2, 0.3,
    0.4; the next would be t=0.5, outside the flight) so the expected tick
    count does not depend on hitting an exact floating-point boundary.
    """
    calls = []

    def _counting_channel(t, y, p, prev):
        count = (prev or 0) + 1
        calls.append((t, count))
        return count

    assert "test_s59_counter" not in sampling._CHANNELS
    sampling._CHANNELS["test_s59_counter"] = _counting_channel
    try:
        p = with_solver(
            _launch_params(airbrake_model="none"),
            method="rk4", dt=0.01, sample_rate_hz=10.0, t_max=0.45,
        )
        s0 = _launch_state()
        r = run_sim(p, s0)
    finally:
        del sampling._CHANNELS["test_s59_counter"]

    n_substeps = r.t.size - 1  # one fewer than the number of grid points
    assert n_substeps > 5 * len(calls)  # far more substeps than channel calls
    assert len(calls) == 5
    assert [count for _t, count in calls] == [1, 2, 3, 4, 5]  # prev genuinely threaded
    # Sampled at each tick's own start: t=0.0, 0.1, 0.2, 0.3, 0.4.
    assert [round(t, 9) for t, _count in calls] == [0.0, 0.1, 0.2, 0.3, 0.4]


def test_channel_value_can_be_a_non_scalar_threaded_through_prev_the_airbrake_channel():
    """Module docstring's own claim ("The value type is deliberately `Any`
    ... so a future channel can hold a tuple ... not just a scalar") is no
    longer just the locally-registered test double above -- the real
    `"airbrake"` channel does this too, as of Step 103
    (architecture-35-paper-alignment.md SS35.6): under `p.actuator.model
    == "full"`, `sample()` threads an `AirbrakeHold` NamedTuple (not a
    `float`) as this channel's own `prev`, tick to tick, and the channel
    reads its own previous `t_k`/`f_k`/`cmd_eff` back out of it correctly.
    """
    p = _launch_params_with_actuator(
        control_kw=dict(airbrake_model="none"), actuator_kw=dict(model="full"),
    )
    y = np.array(_launch_state())

    hold1 = sampling.sample(0.0, y, p, prev=None)
    v1 = hold1.values["airbrake"]
    assert isinstance(v1, control.AirbrakeHold)
    assert v1.t_k == 0.0

    hold2 = sampling.sample(0.1, y, p, prev=hold1)
    v2 = hold2.values["airbrake"]
    assert isinstance(v2, control.AirbrakeHold)
    assert v2.t_k == 0.1
    # `prev` genuinely threaded (not reset): tick 2's f_k is tick 1's ramp
    # carried a full sample period forward, not a fresh `0.0`.
    assert v2.f_k == v1.cmd_eff  # "none" law, rate_open=inf -- ramp reaches cmd exactly


# ----------------------------------------------------------------------
# End-to-end: a real airbrake gain under sample_rate_hz=10 is piecewise
# constant across each tick, and differs measurably from the continuously-
# evaluated (non-sampled) run (ticket's test 4).
# ----------------------------------------------------------------------


def test_sampled_airbrake_is_piecewise_constant_across_each_tick():
    """Instrument `control.airbrake_deploy_fraction` (the single consumer
    function, module docstring) during an actual sampled `run_sim`, and
    walk the recorded `(t, value)` calls IN CALL ORDER: whenever the value
    changes from one recorded call to the next, that change must land at
    (within one `dt` of) an exact tick boundary (a multiple of `T_s`) --
    never strictly inside a tick. This is a direct test of "piecewise
    constant across each tick, not continuously varying", robust to
    floating-point roundoff at a tick's own boundary (unlike bucketing
    samples by `floor(t/T_s)`, which can misattribute a boundary sample to
    the wrong tick by a roundoff hair and manufacture a false "two values
    in one tick" failure that has nothing to do with the mechanism under
    test).
    """
    p = with_solver(
        _launch_params(
            airbrake_model="proportional", airbrake_kp=1.0,
            airbrake_target_apogee_m=100.0, airbrake_Cd=1.0, airbrake_S_max=0.05,
        ),
        method="rk4", dt=1e-3, sample_rate_hz=10.0,
    )
    T_s = 1.0 / p.solver.sample_rate_hz
    dt = p.solver.dt
    s0 = _launch_state()

    recorded = []
    original = control.airbrake_deploy_fraction

    def _spy(t, y, pp, hold=None):
        val = original(t, y, pp, hold)
        recorded.append((t, val))
        return val

    control.airbrake_deploy_fraction = _spy
    try:
        r = run_sim(p, s0)
    finally:
        control.airbrake_deploy_fraction = original

    assert r.events["apogee"] is not None
    assert len(recorded) > 0

    change_ts = []
    prev_val = recorded[0][1]
    for t, val in recorded[1:]:
        if val != prev_val:
            change_ts.append(t)
            prev_val = val

    assert len(change_ts) > 0  # the brake command genuinely changes over the flight
    for t in change_ts:
        nearest_tick_boundary = round(t / T_s) * T_s
        assert math.isclose(t, nearest_tick_boundary, rel_tol=0.0, abs_tol=dt), (
            f"deploy fraction changed at t={t}, not at a tick boundary "
            f"(nearest multiple of T_s={T_s} is {nearest_tick_boundary})"
        )


def test_sampled_run_differs_measurably_from_the_continuous_run():
    """The same airbrake scenario, run once continuously (`sample_rate_hz
    = 0.0`, the default) and once sampled at 10 Hz (`method="rk4"`, same
    `dt`) -- the two trajectories must differ (the ZOH is a real, distinct
    approximation of the continuous law, not an identity under this
    scenario's particular numbers)."""
    base = _launch_params(
        airbrake_model="proportional", airbrake_kp=1.0,
        airbrake_target_apogee_m=100.0, airbrake_Cd=1.0, airbrake_S_max=0.05,
    )
    s0 = _launch_state()

    p_continuous = with_solver(base, method="rk4", dt=1e-3)
    p_sampled = with_solver(base, method="rk4", dt=1e-3, sample_rate_hz=10.0)

    r_continuous = run_sim(p_continuous, s0)
    r_sampled = run_sim(p_sampled, s0)

    assert not np.array_equal(r_continuous.y, r_sampled.y)
    assert r_continuous.events["apogee"] != r_sampled.events["apogee"]

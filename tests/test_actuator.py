"""Tests for the sampled-data airbrake actuator (rate/range/delay) --
architecture-35-paper-alignment.md SS35.6, Step 103, D-114.

Physics/numerics sanity checks + wiring regressions, per the project's
testing philosophy -- no fixtures, no conftest.py, plain `assert` +
`math.isclose`/numpy comparisons. Shares the launch scenario precedent of
tests/test_control.py and tests/test_sampling.py.

D-114 (approved 2026-10-18): actuator fidelity is rate + range + command
delay, closed form, exact in RK4, no lag -- no second-order servo model
(no parameters known yet), and not ideal-only.
"""

import math

import numpy as np
import pytest

from apps.sim.engine import control, sampling
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Actuator, Aero, Control, Lengths, Params, Thrust, Weight, with_solver
from apps.sim.engine.params import replace as params_replace
from apps.sim.engine.state import State, to_vector, width

_MOTOR_CURVE = "placeholder.csv"  # data/motors/placeholder.csv

# Same shared launch scenario as tests/test_control.py / tests/test_sampling.py.
_LAUNCH_WEIGHT = Weight(m=0.5, I=0.05)
_LAUNCH_LENGTHS = Lengths(l1=0.3, l2=0.4)
_LAUNCH_THRUST = Thrust(motor_curve=_MOTOR_CURVE)
_LAUNCH_AERO = Aero(S=0.005, d_ref=0.08, C_x=0.5, C_z=0.0, C_m=0.0)


def _launch_params(control_kw=None, actuator_kw=None) -> Params:
    return Params(
        weight=_LAUNCH_WEIGHT, lengths=_LAUNCH_LENGTHS, thrust=_LAUNCH_THRUST,
        aero=_LAUNCH_AERO, control=Control(**(control_kw or {})),
        actuator=Actuator(**(actuator_kw or {})),
    )


def _launch_state():
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)


# ----------------------------------------------------------------------
# sim/params.py: the Actuator group itself
# ----------------------------------------------------------------------


def test_actuator_defaults_are_ideal_with_unbounded_rates_and_unit_range():
    """`Actuator()`'s defaults: `model="ideal"` (the off switch), rate
    limits are unbounded (`inf`), the deployment range is the full
    `[0.0, 1.0]`, and no command delay -- so that a `Params()` built
    without ever mentioning `actuator=` reproduces every pre-Step-103
    scenario bit-for-bit (this group's own "pin impact: none" claim).
    """
    a = Actuator()
    assert a.model == "ideal"
    assert math.isinf(a.rate_open) and a.rate_open > 0.0
    assert math.isinf(a.rate_close) and a.rate_close > 0.0
    assert a.f_min == 0.0
    assert a.f_max == 1.0
    assert a.delay_ticks == 0


def test_params_default_actuator_group_is_the_same_default_instance():
    """`Params(weight=...)` without `actuator=` carries `Actuator()`'s
    defaults -- the group composes into `Params` the same way `Control`/
    `Solver` already do (sim/params.py SS28.3's "twelve groups" pattern,
    now thirteen)."""
    p = Params(weight=_LAUNCH_WEIGHT)
    assert p.actuator == Actuator()


# ----------------------------------------------------------------------
# sim/control.py: "full" actuator model -- command delay buffer
# ----------------------------------------------------------------------


def test_full_actuator_delays_the_command_by_delay_ticks_sample_periods():
    """`delay_ticks=2`: the effective command `sample_airbrake` feeds the
    actuator at tick k must be the RAW law output from tick `k - 2`, not
    tick k's own -- two ticks of "not yet arrived" (`0.0`, the stowed
    default) before the first real command reaches the actuator.

    Driven directly through `sampling.sample`/`sample_airbrake` (not a
    full `run_sim`) so the test exercises exactly the channel's own
    `prev`-threading contract, independent of integration numerics.
    `airbrake_model="full"`/`airbrake_trigger="after_time"` with
    `airbrake_deploy_time=0.0` makes the RAW command `1.0` from `t=0`
    onward (`_full_airbrake`'s own latch) -- a step input, the simplest
    one that makes "delayed by 2 ticks" observable.
    """
    p = _launch_params(
        control_kw=dict(airbrake_model="full", airbrake_trigger="after_time", airbrake_deploy_time=0.0),
        actuator_kw=dict(model="full", delay_ticks=2),
    )
    y = np.array(_launch_state())

    cmd_effs = []
    hold = None
    for k in range(5):
        hold = sampling.sample(float(k), y, p, prev=hold)
        cmd_effs.append(hold.values["airbrake"].cmd_eff)

    # Raw command is 1.0 from the very first tick (the "after_time" latch
    # at deploy_time=0.0); the effective (delayed) command only becomes
    # 1.0 starting at tick 2 (two whole sample periods later).
    assert cmd_effs == [0.0, 0.0, 1.0, 1.0, 1.0]


# ----------------------------------------------------------------------
# sim/control.py: "full" actuator model -- rate limit, analytic closed form
# ----------------------------------------------------------------------


def test_full_actuator_ramps_linearly_at_rate_open_evaluated_at_rk4_stage_times():
    """Ticket test 1: a command step `0 -> 1` at `t=0` (`airbrake_model=
    "full"`/`airbrake_trigger="after_time"`, `airbrake_deploy_time=0.0`)
    with `rate_open=2.0`/s gives `f_b(t) = 2*t` until it saturates at
    `1.0` (at `t=0.5`), evaluated at times that stand in for RK4's own
    stage times (not just tick starts): a quarter, a half, and
    three-quarters of the way through each of several ticks, plus every
    tick's own start.
    """
    T_s = 0.05
    p = _launch_params(
        control_kw=dict(airbrake_model="full", airbrake_trigger="after_time", airbrake_deploy_time=0.0),
        actuator_kw=dict(model="full", rate_open=2.0),
    )
    y = np.array(_launch_state())

    hold = None
    for k in range(12):  # ticks up to t=0.55s, past saturation at t=0.5
        t_k = k * T_s
        hold = sampling.sample(t_k, y, p, prev=hold)
        for frac in (0.0, 0.25, 0.5, 0.75):
            t = t_k + frac * T_s
            expected = min(2.0 * t, 1.0)
            got = control.airbrake_deploy_fraction(t, y, p, hold)
            assert got == pytest.approx(expected, abs=1e-12), (t, got, expected)


def test_full_actuator_clips_to_f_min_f_max_even_though_the_raw_law_saturates_at_0_1():
    """`f_min`/`f_max` are an independent clip on the ACTUATOR, narrower
    than the raw law's own `[0.0, 1.0]` output range (architecture-35-
    paper-alignment.md SS35.6's "Tests first" list): a saturating command
    (`"full"` law, immediately `1.0`) with `rate_open=inf` (so the ramp
    would otherwise reach `1.0` instantly, even at `dt=0`) must still be
    clipped to `f_max=0.6` at every stage time.
    """
    p = _launch_params(
        control_kw=dict(airbrake_model="full", airbrake_trigger="after_time", airbrake_deploy_time=0.0),
        actuator_kw=dict(model="full", rate_open=float("inf"), f_min=0.1, f_max=0.6),
    )
    y = np.array(_launch_state())

    hold = sampling.sample(0.0, y, p, prev=None)
    # At t=0.0 exactly (dt=0), the unclipped ramp would already jump to
    # the raw command (1.0, inf rate) -- clipped here to f_max=0.6.
    assert control.airbrake_deploy_fraction(0.0, y, p, hold) == pytest.approx(0.6)
    assert control.airbrake_deploy_fraction(0.01, y, p, hold) == pytest.approx(0.6)


# ----------------------------------------------------------------------
# sim/control.py: "ideal" (the default) -- the Step 59 legacy shape, unchanged
# ----------------------------------------------------------------------


def test_ideal_actuator_model_keeps_the_held_value_a_plain_float():
    """`p.actuator.model == "ideal"` (the default, every Step-59-era
    scenario): `sample_airbrake` must still return a plain `float` for the
    `"airbrake"` channel -- not an `AirbrakeHold` -- so
    `hold.values["airbrake"]` is bit-for-bit what it always was, and
    `airbrake_deploy_fraction`'s legacy branch (`isinstance(v,
    AirbrakeHold)` false) returns it as-is.
    """
    p = _launch_params(
        control_kw=dict(airbrake_model="full", airbrake_trigger="after_time", airbrake_deploy_time=0.0),
    )
    assert p.actuator.model == "ideal"  # the default, unmentioned above
    y = np.array(_launch_state())

    hold = sampling.sample(0.0, y, p, prev=None)
    v = hold.values["airbrake"]
    assert type(v) is float
    assert v == 1.0  # "full" law, triggered from t=0
    assert control.airbrake_deploy_fraction(0.3, y, p, hold) == 1.0  # held, not re-evaluated


# ----------------------------------------------------------------------
# sim/integrate.py: fail-fast guard for an unknown p.actuator.model
# ----------------------------------------------------------------------


def test_unknown_actuator_model_raises_valueerror_at_run_sim_entry():
    """architecture-35-paper-alignment.md SS35.6's "Tests first" list: an
    unregistered `p.actuator.model` must raise at `run_sim`'s own entry --
    before any integration is attempted -- unlike this project's usual
    lazy-KeyError-at-first-dispatch convention (SS7) for every other
    model-selection string (`airbrake_model`, `airbrake_trigger`, ...).
    """
    p = with_solver(
        _launch_params(
            control_kw=dict(airbrake_model="full", airbrake_trigger="after_time", airbrake_deploy_time=0.0),
            actuator_kw=dict(model="nope"),
        ),
        method="rk4", dt=1e-3, sample_rate_hz=10.0,
    )
    s0 = _launch_state()
    with pytest.raises(ValueError):
        run_sim(p, s0)


# ----------------------------------------------------------------------
# Ticket's own regression + acceptance checks
# ----------------------------------------------------------------------


def test_state_vector_length_is_unchanged_by_the_actuator():
    """Closed form, no extra state in `y` (architecture-35-paper-
    alignment.md SS35.6's own closed-form note): the actuator's rate/
    range/delay state lives entirely in the `AirbrakeHold` the sampled-
    data channel threads through `prev`, never in the integrated state
    vector -- the FLAT vector the integrator sees stays the same 7
    components (x, z, vx, vz, theta, omega, m) it already had before
    Step 103.

    Step 109 (task-109-roll-reaction-wheel.md SS109.2/SS109.5) grows the
    `State` NamedTuple itself to 10 fields (three more, gated, roll
    components) -- a deliberate, approved structural change unrelated to
    the actuator, so this pin now checks the actual invariant the test's
    own docstring states ("no extra state in `y`") via `sim.state.width`/
    `to_vector`, not the NamedTuple's raw field count.
    """
    p = _launch_params()
    assert p.roll.model == "none"
    assert width(p) == 7
    assert len(to_vector(_launch_state(), p)) == 7


def test_full_actuator_with_infinite_rates_reproduces_the_legacy_sampled_flight():
    """Acceptance (architecture-35-paper-alignment.md SS35.6): a `"full"`-
    law flight with `rate_open = inf` (the `Actuator` default; `rate_close`
    is also `inf` by default) must equal the legacy `"ideal"` sampled
    flight bit-for-bit -- `_ramp`'s own "infinite rate is unconditionally
    unbounded, never `rate*dt`" handling (not even at `dt=0`, the very
    first RK4 stage of each tick) is exactly what makes the two paths
    produce the identical discontinuous zero-order-hold step, tick for
    tick, not merely a close numerical match.
    """
    base = _launch_params(
        control_kw=dict(
            airbrake_model="proportional", airbrake_kp=1.0,
            airbrake_target_apogee_m=100.0, airbrake_Cd=1.0, airbrake_S_max=0.05,
        ),
    )
    s0 = _launch_state()

    p_ideal = with_solver(base, method="rk4", dt=1e-3, sample_rate_hz=10.0)
    p_full = with_solver(
        params_replace(base, {"actuator.model": "full"}),
        method="rk4", dt=1e-3, sample_rate_hz=10.0,
    )

    r_ideal = run_sim(p_ideal, s0)
    r_full = run_sim(p_full, s0)

    assert np.array_equal(r_ideal.y, r_full.y)
    assert r_ideal.events == r_full.events

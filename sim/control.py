"""Feedback control (architecture.md SS27.3). Every controller here is a
pure, memoryless function of (t, y, p) -- see SS27.3's determinism-contract
note for why: solve_ivp's RHS is evaluated at arbitrary/repeated/rejected
times, so no controller may carry state across calls (no integral term, no
fixed-rate sample-and-hold) without a different integration strategy
(backlog B12). A dispatch dict per controllable actuator, selected by a
Params string field -- same pattern as wind.py's _TURBULENCE_MODELS.

Only one actuator is implemented: the airbrake (apogee-targeting P control).
Direction/guidance control is Phase-3 scope (SS27.3) -- this module's shape
(a dict dispatch keyed on a Params string, one pure function per variant) is
the base the user asked for; a guidance controller adds a second dict here
when Phase 3 needs one, not before.

Step 57 (architecture-28-rewrite.md SS28.6): a second, structurally
identical dispatch dict, `_AERO_COEFF_CONTROLLERS`/`aero_coeff_delta`, lets
a future controller perturb the airframe's own aero coefficients (`C_x`/
`C_z`/`C_m_code`/`C_mq_code`/the CoP arm `l1`) instead of (or in addition to) the
Step-49 airbrake's separate additive drag area. `sim.aero.coefficients`
is the single choke point that calls through to it, after the base model
and before any consumer (forces.py's axial/normal force, its pitching
moment and damping term, dynamics.py's CoP moment arm) -- see that
function's docstring. Structure only: today's only registered variant is
`"none"`, the identity. How a future controller plugs in, so nothing
structural needs to change when one is written:

- Write `_my_law(t, y, p, flow, base) -> AeroCoeffs`, returning
  `base._replace(C_x=base.C_x + dC_x, C_m_code=..., l1=...)` -- `NamedTuple.
  _replace` makes "perturb two of five, pass the rest through" the
  default, cheapest thing to write.
- Register it in `_AERO_COEFF_CONTROLLERS` under a new
  `p.control.aero_coeff_model` string.
- It receives `flow` (so `V`, `M`, `q`, `rho`, `Re`, `alpha` are available
  without recomputing anything and without re-entering `aero`), the full
  state `y`, and `t` -- exactly the same inputs `_proportional_airbrake`
  above already gets, plus `flow` and `base`.
- A future sampled-data mode (architecture-28-rewrite.md SS28.8, backlog
  B12) would also pass it `hold`, letting it be a stateful (PID)
  controller. Not added here -- that step's job, strictly later.

Step 59 (architecture-28-rewrite.md SS28.8): the sampled-data/zero-order-
hold mode itself. `airbrake_deploy_fraction` gains an optional `hold`
parameter (default `None`, every pre-Step-59 call site unaffected) -- when
a `sim.sampling.Hold` is passed and carries an `"airbrake"` channel value,
that held value IS the deploy fraction for the whole current tick, and the
live `_AIRBRAKE_CONTROLLERS` law below is not re-evaluated (this module's
own "Consumption" contract, architecture-28-rewrite.md SS28.8.2). The
channel function that produces the held value, `sample_airbrake`, is
registered into `sim.sampling._CHANNELS` under the key `"airbrake"` -- it
just wraps today's existing pure/memoryless law, nothing more: no
controller is written here (`_proportional_airbrake`, above, is unchanged).
`aero_coeff_delta` also gains an optional `hold` parameter for the same
plumbing-completeness reason `sim/flow.py`'s/`sim/wind.py`'s do (accepted,
not forwarded to `_AERO_COEFF_CONTROLLERS`'s variants -- no registered
variant other than `"none"` exists yet, and threading it further would
change the per-variant contract test_control.py's own locally-registered
dummy variants already rely on; a future stateful coefficient controller
can accept it from this function directly when one is written).

Step 65 (architecture-30-apps-4-5-and-configs.md SS30.6.1, D-36-revised):
three airbrake deployment *triggers*, orthogonal to the deployment law
above -- `_AIRBRAKE_TRIGGERS`/`airbrake_triggered`, dispatching on
`p.control.airbrake_trigger` (`after_burnout`/`after_time`/`after_apogee`),
and a `"full"` law (`_full_airbrake`) registered as a third
`_AIRBRAKE_CONTROLLERS` entry beside the untouched `"none"`/
`"proportional"` (`_proportional_airbrake` itself is not edited). Each
trigger is a pure *onset* latch with no retraction (backlog B19) --
duration, retraction and rate limits are a separate, later step.
`after_apogee` uses the `y[VZ] > 0.0` state predicate, never the apogee
*event*, for `forces.parachute_deployed`'s own reason (the RHS runs before
any event is finalised, so it cannot read `Result.events`) and carries its
same documented caveat (a pre-apogee `v_z` transient would arm it early).
`airbrake_deploy_time == 0.0` under `"after_time"` means "deployed from
t=0", the same semantics `Recovery.deploy_time == 0.0` already carries.

Step 107 (architecture-35-paper-alignment.md SS35.4.4, task-107-sampled-
laws-registry.md): `register_sampled_law`/`known_sampled_laws` let a
STATEFUL law (estimator + controller, outside this module -- `controllers/
laws.py`) plug into the same `p.control.airbrake_model` dispatch key the
three memoryless laws already use, read only by `sample_airbrake` under
`p.solver.sample_rate_hz > 0.0` (`sim/integrate.py`'s eager guard rejects
any other combination before integration starts). `_proportional_airbrake`
and the other two memoryless laws are not edited by this step.
"""

import math
from typing import Any, Callable, NamedTuple, Optional

import numpy as np

from sim import gravity, thrust_curve
# `AeroCoeffs` is needed only for this module's own type hints (the Step 57
# seam below), never called into at import time -- safe to import at module
# level here. The opposite direction (sim.aero calling into this module)
# defers its own `from sim import control` to inside the function that
# needs it, breaking the cycle -- same precedent as sim/flow.py's
# `_wind_inertial` / sim/forces.py's `parachute_drag_inertial` deferring
# their own `from sim import wind` for the same reason.
from sim.aero import AeroCoeffs
from sim.state import VZ


def _no_airbrake(t: float, y: np.ndarray, p) -> float:
    """Variant "none" (the default): the brake never deploys. Reproduces
    every prior step bit-for-bit -- the primary off switch, same standing
    as `wind_model = "none"`/`parachute_model = "none"`.
    """
    return 0.0


def _proportional_airbrake(t: float, y: np.ndarray, p) -> float:
    """Variant "proportional": a pure P-control law on predicted apogee
    (architecture.md SS27.3).

    Gated to the unpowered-ascent window only -- post-burnout, pre-apogee:
    `thrust_curve.thrust(t, y, p) > 0.0` (still under power) and
    `y[VZ] >= 0.0` (already past apogee, descending -- z is DOWN-positive,
    so `vz >= 0` means falling) both return `0.0` unconditionally, deploying
    the brake neither during powered flight nor after apogee.

    `predicted_apogee` is the standard real-world estimator: the altitude
    the rocket would reach if drag vanished right now,
    `h + v_up^2/(2g)` (using `y[VZ]**2` since the sign is squared away) --
    a deliberate *upper-bound* prediction that ignores further drag
    (including the brake's own, which is exactly the quantity this
    controller is deciding whether to add). It is a pure function of the
    state being integrated, no different in kind from the thrust curve or
    the aero table -- no new determinism risk.

    `error = predicted_apogee - p.airbrake_target_apogee_m`: positive when
    the rocket is predicted to overshoot the target, in which case more
    brake is commanded. `p.airbrake_kp * error` is clipped to `[0.0, 1.0]`
    -- a deployment fraction, never negative (the brake cannot retract past
    stowed) and never more than fully deployed.
    """
    if thrust_curve.thrust(t, y, p) > 0.0 or y[VZ] >= 0.0:
        return 0.0   # only active during unpowered ascent (post-burnout, pre-apogee)
    predicted_apogee = gravity.altitude_agl(y, p) + y[VZ]**2 / (2.0 * gravity.g(t, y, p))
    error = predicted_apogee - p.control.airbrake_target_apogee_m
    return float(np.clip(p.control.airbrake_kp * error, 0.0, 1.0))


def _trigger_after_burnout(t: float, y: np.ndarray, p) -> bool:
    """Trigger "after_burnout": `thrust(t, y, p) <= 0.0` -- the negation
    framing of `_proportional_airbrake`'s own `thrust(t, y, p) > 0.0` gate
    above: "triggered" means "no longer under power", true from burnout
    onward.
    """
    return thrust_curve.thrust(t, y, p) <= 0.0


def _trigger_after_time(t: float, y: np.ndarray, p) -> bool:
    """Trigger "after_time": `t >= p.control.airbrake_deploy_time`.
    `airbrake_deploy_time == 0.0` (the default) means "deployed from t=0",
    the same semantics `Recovery.deploy_time == 0.0` already carries for
    the parachute's own "timer" trigger.
    """
    return t >= p.control.airbrake_deploy_time


def _trigger_after_apogee(t: float, y: np.ndarray, p) -> bool:
    """Trigger "after_apogee": `y[VZ] > 0.0` -- the same state predicate,
    and the same reasoning, as `forces.parachute_deployed`'s own "apogee"
    trigger (architecture.md SS27.2): the RHS runs before any event is
    finalised, so this cannot read `Result.events`, and "has apogee
    happened" has to be reconstructed from the state actually being
    integrated. `vz == 0.0` exactly (the pad, t=0) is `False`, not
    triggered -- strict inequality, matching `parachute_deployed`'s own.
    Known simplification, same standing as `parachute_deployed`'s: a
    pre-apogee transient dip in `vz` would arm this early. Not guarded
    against, documented here instead (same standing as B11).

    Step 97 (C1/B32.3): `t >= 0.1` pad guard, the same 0.1 s the apogee
    event itself uses (`integrate._apogee_event`), so a launch-instant
    `v_z` transient cannot arm the brake.
    """
    return t >= 0.1 and y[VZ] > 0.0


# Module-private dispatch dict (architecture.md SS12): which trigger is
# active is orthogonal to which deployment law is active (airbrake_model,
# below) -- a separate dict rather than three more _AIRBRAKE_CONTROLLERS
# entries, and the seam through which "proportional" could later be gated
# on a chosen trigger instead of its hardcoded window (a later step, not
# this one). Unknown strings raise KeyError at the first call -- no input
# validation (SS7).
_AIRBRAKE_TRIGGERS = {
    "after_burnout": _trigger_after_burnout,
    "after_time":    _trigger_after_time,
    "after_apogee":  _trigger_after_apogee,
}


def airbrake_triggered(t: float, y: np.ndarray, p) -> bool:
    """Has the brake's deployment condition fired by now -- a pure state
    predicate dispatching on `p.control.airbrake_trigger`, same shape as
    `forces.parachute_deployed`, and never a lookup of the trigger *event*
    itself. Each trigger is a pure *onset* latch with no retraction
    (backlog B19): duration, retraction and rate limits are out of scope
    here.
    """
    return _AIRBRAKE_TRIGGERS[p.control.airbrake_trigger](t, y, p)


def _full_airbrake(t: float, y: np.ndarray, p) -> float:
    """Variant "full": fully deployed from the trigger instant onward --
    `0.0` before `airbrake_triggered(t, y, p)`, `1.0` at and after it. The
    constant-C_dA model App 4 solves against.
    """
    return 1.0 if airbrake_triggered(t, y, p) else 0.0


# Module-private dispatch dict (architecture.md SS12), same pattern as
# wind.py's `_TURBULENCE_MODELS`/`_MODELS`: the public seam is
# `airbrake_deploy_fraction`; callers never learn variants exist. Unknown
# strings raise KeyError at the first call -- no input validation (SS7).
_AIRBRAKE_CONTROLLERS = {
    "none": _no_airbrake,
    "proportional": _proportional_airbrake,
    "full": _full_airbrake,
}


def airbrake_deploy_fraction(t: float, y: np.ndarray, p, hold=None) -> float:
    """Airbrake deployment fraction, `[0.0, 1.0]` (architecture.md SS27.3),
    dispatching on `p.airbrake_model`.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is an optional
    `sim.sampling.Hold`, default `None` -- every pre-Step-59 call site is
    unaffected, bit-for-bit. When `hold` is not `None` and already carries
    an `"airbrake"` channel value (computed once at the current tick's
    start by `sample_airbrake`, below), that held value is returned
    directly -- a zero-order hold, not a fresh evaluation of the law below.

    Step 103 (architecture-35-paper-alignment.md SS35.6, D-114): the held
    value is `float` under `p.actuator.model == "ideal"` (unchanged from
    Step 59 -- returned as-is, the branch above), or an `AirbrakeHold`
    under `"full"`, in which case the actual deploy fraction at this exact
    `t` is the rate/range-limited ramp evaluated `t - hold.t_k` seconds
    into the held actuator state (`_ramp`, below) -- continuous within a
    tick (every RK4 stage sees a different value as `t` advances across
    the tick's four stages), unlike the `"ideal"` branch's single constant.

    Step 107: a SampledLawHold's own actuator_hold is unwrapped first --
    the ramp/passthrough logic below is otherwise unaware a sampled law
    was involved. A registered sampled law has no memoryless/continuous
    evaluation of its own (it is stateful by construction) -- calling
    this function for one WITHOUT a `hold` (e.g. a hold-less diagnostic
    call made outside the sampled-data loop, such as sim/report.py's own
    brake-fraction report) raises a clear `ValueError` here instead of an
    opaque `KeyError` from `_AIRBRAKE_CONTROLLERS` (which never carries a
    sampled-law entry, SS107.3.1) -- found during this ticket's own
    code-review pass, not anticipated by the ticket text itself.
    """
    if hold is not None and "airbrake" in hold.values:
        v = hold.values["airbrake"]
        if isinstance(v, SampledLawHold):
            v = v.actuator_hold
        if isinstance(v, AirbrakeHold):
            a = p.actuator
            return _ramp(v.f_k, v.cmd_eff, t - v.t_k, a.rate_open, a.rate_close, a.f_min, a.f_max)
        return v
    name = p.control.airbrake_model
    if name in _SAMPLED_LAWS:
        raise ValueError(
            f"airbrake_deploy_fraction: p.control.airbrake_model={name!r} is a "
            "registered sampled law and has no memoryless/continuous evaluation -- "
            "it can only be evaluated through sample_airbrake's own zero-order-"
            "hold dispatch (a `hold` carrying a SampledLawHold must be passed "
            "here; task-107-sampled-laws-registry.md)."
        )
    return _AIRBRAKE_CONTROLLERS[name](t, y, p)


def sample_airbrake(t: float, y: np.ndarray, p, prev):
    """The airbrake channel function registered into
    `sim.sampling._CHANNELS` under `"airbrake"` (architecture-28-rewrite.md
    SS28.8.2): evaluates today's existing pure, memoryless
    `_AIRBRAKE_CONTROLLERS[p.control.airbrake_model]` law exactly once --
    the same law `airbrake_deploy_fraction` calls on every un-sampled RHS
    evaluation -- to get this tick's own RAW command, then dispatches that
    command through `p.actuator.model` (Step 103) to decide what value is
    actually held for the tick.

    `prev` (this channel's own held value from the previous tick, or
    `None` at the first tick, t=0) is threaded straight through to the
    actuator-model dispatch below; see `_actuator_ideal`/`_actuator_full`.

    Step 107: if p.control.airbrake_model names a REGISTERED sampled law
    instead, dispatch there (ctrl_state threaded via SampledLawHold) --
    see task-107-sampled-laws-registry.md.
    """
    name = p.control.airbrake_model
    if name in _SAMPLED_LAWS:
        prev_actuator_hold, prev_ctrl_state = (
            (prev.actuator_hold, prev.ctrl_state) if isinstance(prev, SampledLawHold) else (prev, None)
        )
        if _in_coast_window(t, y, p):
            meas = _ideal_measurement(t, y, p)  # Step 108 replaces this one call (SS107.3.2/SS107.12)
            cmd, ctrl_state = _SAMPLED_LAWS[name](t, meas, p, prev_ctrl_state)
        else:
            cmd, ctrl_state = 0.0, prev_ctrl_state  # outside the window: command 0, state frozen
        actuator_hold = _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev_actuator_hold)
        return SampledLawHold(actuator_hold=actuator_hold, ctrl_state=ctrl_state)

    cmd = _AIRBRAKE_CONTROLLERS[name](t, y, p)
    return _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev)


# ----------------------------------------------------------------------
# Step 103 (architecture-35-paper-alignment.md SS35.6, D-114): the
# actuator itself -- rate limit, deployment range, command delay, closed
# form. `model = "ideal"` (the default) is exactly the Step 59
# zero-order hold (bit-for-bit, the dispatch function below is the
# identity on the raw command); `model = "full"` is everything else.
# ----------------------------------------------------------------------


class AirbrakeHold(NamedTuple):
    """The `"full"` actuator model's own held state -- the value
    `sample_airbrake` returns for the `"airbrake"` channel, and the value
    `airbrake_deploy_fraction` reads back every RHS stage.

    `t_k`: this tick's own start time (the `t` `sample_airbrake` was
    called with) -- `airbrake_deploy_fraction` computes `t - t_k` from it,
    never a separately threaded tick period.
    `f_k`: the actuator's own continuous value AT `t_k` -- the previous
    tick's ramp, evaluated a full sample period in (`_ramp`, applied in
    `_actuator_full` below); `0.0` at the very first tick (`f_0 = 0`,
    stowed).
    `cmd_eff`: this tick's EFFECTIVE command -- the raw law output from
    `delay_ticks` ticks ago (or `0.0` if that many ticks haven't happened
    yet), what the ramp in `airbrake_deploy_fraction` actually ramps
    toward during this tick.
    `cmd_queue`: the raw (un-delayed) commands not yet delivered -- a
    `tuple[float, ...]` of length `delay_ticks`, oldest first; the FIFO
    `_actuator_full` reads `cmd_eff` out of and pushes this tick's own raw
    command onto.
    """
    t_k: float
    f_k: float
    cmd_eff: float
    cmd_queue: "tuple[float, ...]"


def _ramp(f0: float, cmd: float, dt: float, rate_open: float, rate_close: float,
          f_min: float, f_max: float) -> float:
    """The rate/range-limited actuator's closed form (D-114): the value
    reached after `dt` seconds of ramping from `f0` toward `cmd`, limited
    by `rate_open` (opening, `cmd > f0`) / `rate_close` (closing, `cmd <
    f0`), clipped to `[f_min, f_max]`.

    Infinite rates are treated as "no rate limit at all" -- the bound
    stays `+-inf` regardless of `dt`, including `dt == 0.0` -- rather than
    via `rate * dt`, which would be `inf * 0.0 == nan` at a tick's own
    first instant. This is what makes `rate_open = rate_close = inf` (the
    `Actuator` defaults even under `"full"`) reduce exactly to the Step 59
    zero-order hold, bit-for-bit, at every `t` in the tick including
    `t == t_k` itself (this module's own acceptance test,
    architecture-35-paper-alignment.md SS35.6).
    """
    delta = cmd - f0
    upper = np.inf if math.isinf(rate_open) else rate_open * dt
    lower = -np.inf if math.isinf(rate_close) else -rate_close * dt
    step = np.clip(delta, lower, upper)
    return float(np.clip(f0 + step, f_min, f_max))


def _actuator_ideal(t: float, cmd: float, p, prev) -> float:
    """Variant `"ideal"` (the default): the zero-order hold IS the
    actuator -- the Step 59 legacy behaviour, bit-for-bit. `t`/`p`/`prev`
    unused."""
    return cmd


def _actuator_full(t: float, cmd: float, p, prev) -> AirbrakeHold:
    """Variant `"full"`: rate + range + command delay (D-114).

    `prev` is this channel's own `AirbrakeHold` from the previous tick (or
    `None` at the very first tick). `f_k` is `prev`'s ramp evaluated a
    full sample period in (`t - prev.t_k`, the previous tick's own
    duration -- no separately threaded period needed); `cmd_eff` is pulled
    out of the delay FIFO (`prev.cmd_queue`), and this tick's raw `cmd` is
    pushed onto it.
    """
    a = p.actuator
    if prev is None:
        # f_0 = 0.0 is the spec's own literal initial condition
        # (architecture-35-paper-alignment.md SS35.4.4's closed form),
        # deliberately NOT a.f_min -- the actuator starts fully stowed
        # regardless of where its operating range's own floor sits; the
        # very first ramp (above, once a command arrives) travels from
        # 0.0, not from f_min, same as a real actuator's physical rest
        # position would.
        f_k = 0.0
        queue: "tuple[float, ...]" = ()
    else:
        f_k = _ramp(prev.f_k, prev.cmd_eff, t - prev.t_k, a.rate_open, a.rate_close, a.f_min, a.f_max)
        queue = prev.cmd_queue

    if a.delay_ticks <= 0:
        cmd_eff, new_queue = cmd, ()
    elif len(queue) >= a.delay_ticks:
        cmd_eff, new_queue = queue[0], queue[1:] + (cmd,)
    else:
        cmd_eff, new_queue = 0.0, queue + (cmd,)

    return AirbrakeHold(t_k=t, f_k=f_k, cmd_eff=cmd_eff, cmd_queue=new_queue)


# Module-private dispatch dict (architecture.md SS12), same pattern as
# `_AIRBRAKE_CONTROLLERS`/`_AIRBRAKE_TRIGGERS` above. Unknown strings
# raise `KeyError` at the first call here -- but `sim.integrate.run_sim`
# validates `p.actuator.model` against this same dict eagerly, at entry,
# before any integration is attempted (architecture-35-paper-alignment.md
# SS35.6: "unknown law name raises at run_sim entry", a deliberate
# exception to the project's usual lazy-KeyError convention, SS7).
_ACTUATOR_MODELS = {
    "ideal": _actuator_ideal,
    "full": _actuator_full,
}


def known_actuator_models() -> "tuple[str, ...]":
    """The registered `p.actuator.model` names. `sim.integrate.run_sim`'s
    own eager-validation guard (Step 103, SS35.6) calls this instead of
    reaching into `_ACTUATOR_MODELS` directly, so that dict stays
    module-private like every other dispatch dict in this file -- the
    one place outside this module that needs to know a name is valid
    gets a named, stable entry point for it instead of a cross-module
    reach into another module's internals.
    """
    return tuple(_ACTUATOR_MODELS)


# ----------------------------------------------------------------------
# Step 107 (architecture-35-paper-alignment.md SS35.4.4, task-107-
# sampled-laws-registry.md): the sampled-law registry -- any STATEFUL
# estimator+law pair (controllers/laws.py) can plug into the same
# p.control.airbrake_model dispatch key the three memoryless laws above
# already use. No law is written in this module -- see controllers/.
# ----------------------------------------------------------------------


_SAMPLED_LAWS: "dict[str, Callable]" = {}


def register_sampled_law(name: str, fn: "Callable") -> None:
    """Register fn(t_k, meas, p, state) -> (cmd, state) under `name`, read
    by sample_airbrake's dispatch (below) whenever p.control.airbrake_model
    == name. Collides only with the three BUILT-IN memoryless names (none/
    proportional/full) -- raises ValueError there (silently shadowing one
    of this project's off-switch/legacy names would be a nasty, hard-to-
    debug mistake for every subsequent call in the same process). Any
    other name, including re-registering the SAME name a second time, is a
    plain overwrite -- no raise -- the simplest, most dict-assignment-like
    behaviour, consistent with every other dispatch dict in this codebase
    being a bare literal (this is the first RUNTIME registration API this
    project has had; there is no stricter precedent to match).
    """
    if name in _AIRBRAKE_CONTROLLERS:
        raise ValueError(
            f"register_sampled_law: {name!r} collides with a built-in "
            f"airbrake_model name (known: {sorted(_AIRBRAKE_CONTROLLERS)})."
        )
    _SAMPLED_LAWS[name] = fn


def known_sampled_laws() -> "tuple[str, ...]":
    """The registered sampled-law names -- sim.integrate.run_sim's own
    eager-validation guard (Step 107, mirroring known_actuator_models())
    calls this instead of reaching into _SAMPLED_LAWS directly."""
    return tuple(_SAMPLED_LAWS)


class Measurement(NamedTuple):
    """What a registered sampled law is allowed to see -- never `y`
    (architecture-35-paper-alignment.md SS35.4.4: "the controller never
    sees y"). `a_imu` is `None` until Step 108 wires an IMU channel (D-115
    only commits to baro + alpha-beta; IMU is option (c), not taken)."""
    h_baro: float
    a_imu: "Optional[float]" = None


def _ideal_measurement(t: float, y: np.ndarray, p) -> Measurement:
    """Step 107's own stub sensor: truth-equals-measurement, no noise, no
    lag, no quantisation -- exactly what the roadmap's own "ideal sensor"
    test wording (Step 107's acceptance bullet) requires to be testable
    BEFORE Step 108's real sim/sensors.py exists. Reads gravity.altitude_
    agl (the same primitive _proportional_airbrake's own predictor already
    reads), never atmosphere.py or any noise model.

    SUPERSEDED BY STEP 108 (does not change this ticket's own tests, see
    SS107.12): sample_airbrake's sampled-law branch (SS107.4) calls this
    function by name, in exactly one place. Step 108 replaces that ONE
    call site with `sensors.measure(t, y, p, prev_sens_state)` (returning
    a `(Measurement, sens_state)` pair instead of a bare `Measurement`),
    and threads the returned `sens_state` into `SampledLawHold.sens_state`
    (already present, default None, SS107.3.3) -- `_ideal_measurement`
    itself is then dead code Step 108 may delete, but nothing in THIS
    ticket's tests calls it directly (they go through run_sim/
    sample_airbrake), so deleting it breaks no Step 107 test.
    """
    return Measurement(h_baro=gravity.altitude_agl(y, p))


class SampledLawHold(NamedTuple):
    """The channel's own `prev` (sim.sampling's sense) when p.control.
    airbrake_model is a REGISTERED sampled law -- wraps the actuator's own
    held value (float under actuator.model=="ideal", AirbrakeHold -- Step
    103's own type, UNTOUCHED -- under "full") together with the LAW's own
    ctrl_state (opaque, law-specific: None for a stateless law, a small
    NamedTuple with an integrator for pi_apogee). `sens_state` is a Step-
    108 placeholder (always None here, Step 107 never writes anything
    else into it) -- present now so Step 108 does not need to change this
    NamedTuple's SHAPE, only what it puts in that one field (no API break,
    per the task brief's own requirement).
    """
    actuator_hold: "float | AirbrakeHold"
    ctrl_state: Any
    sens_state: Any = None


def _in_coast_window(t: float, y: np.ndarray, p) -> bool:
    """Unpowered-ascent, pre-apogee -- a SEPARATE copy of the exact
    condition _proportional_airbrake applies inline (that function is NOT
    touched/refactored here, SS107.1), used only by sample_airbrake's new
    sampled-law branch, below. A registered law never sees `y`
    (architecture-35-paper-alignment.md SS35.4.4), so the window has to be
    decided at the channel level, which legitimately has `y` (the plant
    truth sampled once per tick) -- not inside the law itself.

    Known, documented simplification (same standing as `_trigger_after_
    apogee`'s own "pre-apogee vz dip" caveat, this module's docstring):
    outside this window the law is not called at all this tick (SS107.4),
    so a stateful law's internal filter/integrator does not warm up until
    the window opens -- not fixed here, not a regression (the legacy
    laws have no state to warm up in the first place, so this is a new
    kind of simplification specific to a stateful law, not a narrowing of
    an existing guarantee).
    """
    return not (thrust_curve.thrust(t, y, p) > 0.0 or y[VZ] >= 0.0)


# ----------------------------------------------------------------------
# Step 57 (architecture-28-rewrite.md SS28.6): the control-coefficient
# seam -- structure only, identity by default. No controller is written
# here; see this module's own docstring for the full plug-in contract.
# ----------------------------------------------------------------------


def _no_aero_delta(t: float, y: np.ndarray, p, flow, base: AeroCoeffs) -> AeroCoeffs:
    """Variant `"none"` (the default): returns `base` unchanged -- the
    identity, bit-for-bit every prior step. Returns the same object (not a
    reconstructed copy), so `aero.coefficients(...) is <the base model's
    own returned bundle>` holds under this variant -- a legitimate,
    stronger-than-equality check precisely because this one variant is a
    pass-through, not a computation that happens to produce an equal value.
    """
    return base


# Module-private dispatch dict (architecture.md SS12), same pattern as
# `_AIRBRAKE_CONTROLLERS` above and wind.py's `_TURBULENCE_MODELS`: the
# public seam is `aero_coeff_delta`; callers never learn variants exist.
# Unknown strings raise KeyError at the first call -- no input validation
# (SS7).
_AERO_COEFF_CONTROLLERS = {
    "none": _no_aero_delta,
}


def aero_coeff_delta(t: float, y: np.ndarray, p, flow, base: AeroCoeffs, hold=None) -> AeroCoeffs:
    """The control-coefficient seam's public entry point, dispatching on
    `p.control.aero_coeff_model` -- called from inside `aero.coefficients`
    (architecture-28-rewrite.md SS28.6), the single choke point after the
    base model and before any consumer. See this module's own docstring
    for how a future controller registers a new variant here.

    Step 59 (architecture-28-rewrite.md SS28.8): `hold` is accepted
    (default `None`) for the same "thread the seam everywhere now" reason
    `sim/flow.py`'s/`sim/wind.py`'s functions do, but is not forwarded to
    the dispatched variant below -- no registered variant other than
    `"none"` exists yet, and today's variant functions (including
    `tests/test_control.py`'s own locally-registered dummy ones) have the
    5-argument `(t, y, p, flow, base)` shape; changing that contract is a
    future stateful controller's job (B12), not this step's.
    """
    return _AERO_COEFF_CONTROLLERS[p.control.aero_coeff_model](t, y, p, flow, base)

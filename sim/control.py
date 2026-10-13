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
`C_z`/`C_m`/`C_mq`/the CoP arm `l1`) instead of (or in addition to) the
Step-49 airbrake's separate additive drag area. `sim.aero.coefficients`
is the single choke point that calls through to it, after the base model
and before any consumer (forces.py's axial/normal force, its pitching
moment and damping term, dynamics.py's CoP moment arm) -- see that
function's docstring. Structure only: today's only registered variant is
`"none"`, the identity. How a future controller plugs in, so nothing
structural needs to change when one is written:

- Write `_my_law(t, y, p, flow, base) -> AeroCoeffs`, returning
  `base._replace(C_x=base.C_x + dC_x, C_m=..., l1=...)` -- `NamedTuple.
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
"""

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
    """
    return y[VZ] > 0.0


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
    """
    if hold is not None and "airbrake" in hold.values:
        return hold.values["airbrake"]
    return _AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t, y, p)


def sample_airbrake(t: float, y: np.ndarray, p, prev) -> float:
    """The airbrake channel function registered into
    `sim.sampling._CHANNELS` under `"airbrake"` (architecture-28-rewrite.md
    SS28.8.2): evaluates today's existing pure, memoryless
    `_AIRBRAKE_CONTROLLERS[p.control.airbrake_model]` law exactly once --
    the same law `airbrake_deploy_fraction` calls on every un-sampled RHS
    evaluation -- and returns the value to be held for the whole tick.

    `prev` (this channel's own held value from the previous tick, or
    `None` at the first tick, t=0) is accepted, per the channel signature
    every registered channel must have, but unused here: today's only
    registered airbrake law, `_proportional_airbrake`, is itself
    memoryless and needs no previous value to compute its own next one. A
    future stateful law (a fixed-rate PID, backlog B12) would read `prev`
    instead of ignoring it -- that is B12's job, not this step's.
    """
    return _AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t, y, p)


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

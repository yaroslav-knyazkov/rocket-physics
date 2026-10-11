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


# Module-private dispatch dict (architecture.md SS12), same pattern as
# wind.py's `_TURBULENCE_MODELS`/`_MODELS`: the public seam is
# `airbrake_deploy_fraction`; callers never learn variants exist. Unknown
# strings raise KeyError at the first call -- no input validation (SS7).
_AIRBRAKE_CONTROLLERS = {
    "none": _no_airbrake,
    "proportional": _proportional_airbrake,
}


def airbrake_deploy_fraction(t: float, y: np.ndarray, p) -> float:
    """Airbrake deployment fraction, `[0.0, 1.0]` (architecture.md SS27.3),
    dispatching on `p.airbrake_model`.
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


def aero_coeff_delta(t: float, y: np.ndarray, p, flow, base: AeroCoeffs) -> AeroCoeffs:
    """The control-coefficient seam's public entry point, dispatching on
    `p.control.aero_coeff_model` -- called from inside `aero.coefficients`
    (architecture-28-rewrite.md SS28.6), the single choke point after the
    base model and before any consumer. See this module's own docstring
    for how a future controller registers a new variant here.
    """
    return _AERO_COEFF_CONTROLLERS[p.control.aero_coeff_model](t, y, p, flow, base)

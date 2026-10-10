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
"""

import numpy as np

from sim import gravity, thrust_curve
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

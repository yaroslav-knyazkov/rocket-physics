"""Sampled, stateful airbrake laws (Phase 2.17 Milestone M3, architecture-
35-paper-alignment.md SS35.4.4) -- registered into sim.control at
controllers/__init__.py's own import time, never called directly by
sim/. Each law has the signature fn(t_k, meas, p, state) -> (cmd, state)
sim.control.register_sampled_law documents.
"""

import math
from typing import NamedTuple, Optional

import numpy as np

from controllers import estimator


def drag_aware_predicted_apogee(h: float, v: float, g: float, m: float, k: float) -> float:
    """Closed form for a drag-only vertical ballistic coast (model-
    proposals.md line 88; architecture-35-paper-alignment.md SS35.4.4):

        h_a = h + (m / (2*k)) * ln(1 + k*v**2 / (m*g))

    `k` is the drag "area coefficient", 0.5*rho_hat*(C_dA0 + C_dA_brake*
    f_b) [kg/m] -- NOT the raw C_x or S alone. `v` enters squared, so its
    sign is irrelevant (works for either up- or down-positive velocity
    conventions, matching how _proportional_airbrake's own `y[VZ]**2`
    already sidesteps the same question).

    `k <= 0.0` -- the vacuum limit, `h + v**2/(2*g)` (the Taylor expansion
    of `ln(1+x)/x -> 1` as `x -> 0`; computed directly, not by evaluating
    the log formula at k=0, which would be a 0/0 division) -- this is also
    what every registered law's own onboard model reduces to under the
    Control defaults (onboard_CdA0=0.0, onboard_CdA_brake=0.0), so a user
    who registers a new law but forgets to set an onboard drag model gets
    the same upper-bound prediction _proportional_airbrake's own legacy
    formula already uses, not a crash.

    No guard against `m <= 0.0` with `k > 0.0` (division by zero/nan) --
    house no-validation convention (SS7), same standing as every other
    model-selection/physical-parameter field in this codebase; documented
    here, not defended against: `onboard_mass` must be set together with
    `onboard_CdA0`/`onboard_CdA_brake` whenever either is nonzero.
    """
    if k <= 0.0:
        return h + v**2 / (2.0 * g)
    return h + (m / (2.0 * k)) * math.log(1.0 + k * v**2 / (m * g))


def _k(c, f_b: float) -> float:
    """0.5*rho_hat*(C_dA0 + C_dA_brake*f_b) -- the predictor's own `k`,
    built from the onboard model's Control fields (SS107.6). `f_b` is the
    LAST tick's own commanded fraction (the law's own previous `cmd`,
    carried in its state) -- a one-tick-delayed self-consistency, same
    spirit as the legacy predictor's own "if drag vanished right now"
    simplification, documented not fixed."""
    return 0.5 * c.onboard_rho0 * (c.onboard_CdA0 + c.onboard_CdA_brake * f_b)


class ProportionalDragState(NamedTuple):
    # Step 108: `est` holds an `estimator.EstimatorState` under the
    # default `estimator_model="stub"`, or an `estimator.AlphaBetaState`
    # under `"alpha_beta"` -- `estimator.step`'s own `model=` dispatch
    # decides which; this law never reaches into either's own fields
    # (threads `prev.est` back opaquely), so the type hint below is
    # honest about both possibilities rather than only the pre-Step-108
    # one. Found during this ticket's own code-review pass.
    est: "Optional[estimator.EstimatorState | estimator.AlphaBetaState]" = None
    f_b_prev: float = 0.0


def proportional_drag(t_k, meas, p, state):
    c = p.control
    prev = state if state is not None else ProportionalDragState()
    h_hat, v_hat, est_new = estimator.step(t_k, meas.h_baro, prev.est, model=c.estimator_model, p=p)
    k = _k(c, prev.f_b_prev)
    h_a = drag_aware_predicted_apogee(h_hat, v_hat, p.g0, c.onboard_mass, k)
    error = h_a - c.airbrake_target_apogee_m
    cmd = float(np.clip(c.airbrake_kp * error, 0.0, 1.0))
    return cmd, ProportionalDragState(est=est_new, f_b_prev=cmd)


class PiApogeeState(NamedTuple):
    # See ProportionalDragState.est's own comment above -- same honest
    # either-model type hint, same reason.
    est: "Optional[estimator.EstimatorState | estimator.AlphaBetaState]" = None
    integral: float = 0.0
    f_b_prev: float = 0.0


def pi_apogee(t_k, meas, p, state):
    c = p.control
    prev = state if state is not None else PiApogeeState()
    dt = 0.0 if prev.est is None or prev.est.t_prev is None else t_k - prev.est.t_prev
    h_hat, v_hat, est_new = estimator.step(t_k, meas.h_baro, prev.est, model=c.estimator_model, p=p)
    k = _k(c, prev.f_b_prev)
    h_a = drag_aware_predicted_apogee(h_hat, v_hat, p.g0, c.onboard_mass, k)
    error = h_a - c.airbrake_target_apogee_m
    unsat = c.airbrake_kp * error + c.airbrake_ki * prev.integral
    cmd = float(np.clip(unsat, 0.0, 1.0))
    # Anti-windup (conditional/clamping integration, no new gain field):
    # stop integrating further in the direction that is ALREADY saturated.
    saturated_high = cmd >= 1.0 and error > 0.0
    saturated_low = cmd <= 0.0 and error < 0.0
    new_integral = prev.integral if (saturated_high or saturated_low) else prev.integral + error * dt
    return cmd, PiApogeeState(est=est_new, integral=new_integral, f_b_prev=cmd)

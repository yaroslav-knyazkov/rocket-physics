"""Two estimator models for a registered sampled law's own state:
"stub" (Step 107, default) -- a trivial two-point backward difference,
exact whenever the measurement itself is exact; "alpha_beta" (Step 108,
opt-in via Control.estimator_model) -- a real constant-velocity
alpha-beta (g-h) filter: position+velocity recursively updated from a
single noisy/lagged altitude measurement per tick.

laws.py calls only `step(...)`, never reaches into either state type's
own fields (Step 107's own docstring already established this contract;
Step 108 does not change it) -- so this module's body can be replaced/
extended without laws.py changing shape, only ONE call-site keyword.
"""

from typing import NamedTuple, Optional


class EstimatorState(NamedTuple):
    """"stub" model's own state -- UNCHANGED from Step 107, bit-for-bit."""
    t_prev: Optional[float] = None
    h_prev: Optional[float] = None


class AlphaBetaState(NamedTuple):
    """"alpha_beta" model's own state: the filter's own last position/
    velocity ESTIMATE (not the raw measurement) plus the tick time it was
    produced at."""
    t_prev: Optional[float] = None
    h_hat: float = 0.0
    v_hat: float = 0.0


def _step_stub(t: float, h_baro: float, prev: "Optional[EstimatorState]"):
    """Step 107's own body, UNCHANGED."""
    if prev is None or prev.t_prev is None:
        return h_baro, 0.0, EstimatorState(t_prev=t, h_prev=h_baro)
    dt = t - prev.t_prev
    v_hat = (h_baro - prev.h_prev) / dt if dt > 0.0 else 0.0
    return h_baro, v_hat, EstimatorState(t_prev=t, h_prev=h_baro)


def _step_alpha_beta(t: float, h_baro: float, prev: "Optional[AlphaBetaState]", alpha: float, beta: float):
    """Constant-velocity alpha-beta (g-h) filter, Kalata's own
    parameterisation: predict `h_pred = h_hat_prev + v_hat_prev*dt`, then
    correct both states from the residual `r = h_baro - h_pred`:
    `h_hat = h_pred + alpha*r`, `v_hat = v_hat_prev + (beta/dt)*r`. Same
    "nothing to predict from yet" first-call convention as the stub
    (`v_hat = 0.0`, `h_hat = h_baro`) -- and same `dt <= 0.0` guard
    (returns the PREVIOUS estimate unchanged rather than dividing by
    zero/a negative dt, which a repeated or out-of-order tick could in
    principle produce).
    """
    if prev is None or prev.t_prev is None:
        return h_baro, 0.0, AlphaBetaState(t_prev=t, h_hat=h_baro, v_hat=0.0)
    dt = t - prev.t_prev
    if dt <= 0.0:
        return prev.h_hat, prev.v_hat, AlphaBetaState(t_prev=t, h_hat=prev.h_hat, v_hat=prev.v_hat)
    h_pred = prev.h_hat + prev.v_hat * dt
    r = h_baro - h_pred
    h_hat = h_pred + alpha * r
    v_hat = prev.v_hat + (beta / dt) * r
    return h_hat, v_hat, AlphaBetaState(t_prev=t, h_hat=h_hat, v_hat=v_hat)


def step(t: float, h_baro: float, prev, *, model: str = "stub", p=None):
    """`(h_hat, v_hat, new_state)`. `model="stub"` (default) is Step
    107's own body, bit-for-bit, for every existing 3-positional-arg
    caller (laws.py before this ticket; tests/test_controllers.py's own
    direct unit tests) -- `p` is ignored in that branch. `model=
    "alpha_beta"` reads its two gains from `p.control.estimator_alpha`/
    `p.control.estimator_beta` -- `p` is REQUIRED (AttributeError on
    `None`, no extra validation, SS7) in that branch only.

    Unknown `model` raises ValueError here -- the one validation point
    for this field (sim/integrate.py cannot eagerly guard it without
    importing apps/control/flight_software/, which sim/ never does; see
    the ticket's own §108.8.2 for why this is a deliberate, documented
    asymmetry with airbrake_model/actuator.model's eager guards).
    """
    if model == "stub":
        return _step_stub(t, h_baro, prev)
    if model == "alpha_beta":
        return _step_alpha_beta(t, h_baro, prev, p.control.estimator_alpha, p.control.estimator_beta)
    raise ValueError(f"estimator.step: unknown model {model!r} (known: 'stub', 'alpha_beta')")

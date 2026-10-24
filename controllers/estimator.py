"""Stub only (Step 107, task-107-sampled-laws-registry.md) -- the REAL
alpha-beta filter (h_hat, v_hat from noisy/lagged baro altitude) is Step
108's job (architecture-35-paper-alignment.md SS35.4.4, D-115). This stub
gives Step 107's own laws (controllers/laws.py) something state-shaped to
carry between ticks without inventing an ad hoc shape each law would
otherwise duplicate: a trivial two-point backward-difference estimator,
exact (zero error) whenever the measurement itself is exact (Step 107's
own sim.control._ideal_measurement) -- see SS107.12 for exactly what Step
108 replaces here and why no Step 107 test breaks when it does.

laws.py calls only `step(...)`, never reaches into EstimatorState's own
fields -- so Step 108 replacing this module's body entirely (a real
filter needs gains, not just two numbers) cannot break a law that only
ever treats EstimatorState as opaque state threaded back in next tick.
"""

from typing import NamedTuple, Optional


class EstimatorState(NamedTuple):
    t_prev: Optional[float] = None
    h_prev: Optional[float] = None


def step(t: float, h_baro: float, prev: "Optional[EstimatorState]"):
    """`(h_hat, v_hat, new_state)`. `v_hat = 0.0` at the very first call
    (`prev is None`, or a freshly-constructed `EstimatorState()` with
    `t_prev is None`) -- the same "nothing to difference against yet"
    convention `sim.control._actuator_full`'s own `f_0 = 0.0` literal
    uses for its own first tick.
    """
    if prev is None or prev.t_prev is None:
        return h_baro, 0.0, EstimatorState(t_prev=t, h_prev=h_baro)
    dt = t - prev.t_prev
    v_hat = (h_baro - prev.h_prev) / dt if dt > 0.0 else 0.0
    return h_baro, v_hat, EstimatorState(t_prev=t, h_prev=h_baro)

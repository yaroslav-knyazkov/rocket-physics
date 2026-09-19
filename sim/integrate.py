"""solve_ivp wrapper, events, Result (architecture.md SS5).

Owns all `scipy.integrate.solve_ivp` machinery -- event functions,
dense output. The equations of motion themselves live in dynamics.py;
this module only drives the numerics.
"""

from typing import Any, NamedTuple, Optional

import numpy as np
from scipy.integrate import solve_ivp

from sim.dynamics import derivatives
from sim.state import State, Z, VZ


class Result(NamedTuple):
    t: np.ndarray                     # time samples [s]
    y: np.ndarray                     # state history, shape (6, N)
    events: dict[str, Optional[float]]  # {"apogee": t | None, "ground": t | None}
    raw: Any                          # the scipy OdeResult (e.g. for sol.sol(t))


def _ground_event(t, y, p):
    # Gotcha (architecture.md SS1): z is 0 at launch (t=0), which can be
    # picked up as a spurious root immediately -- e.g. if thrust never
    # exceeded gravity the rocket would start "falling" from z=0 right
    # away. Guard the first 0.1 s.
    if t < 0.1:
        return 1.0
    return y[Z]


_ground_event.terminal = True
_ground_event.direction = 1  # z increasing through 0 == falling (z is down-positive)


def _apogee_event(t, y, p):
    # Same gotcha as the ground event: vz is exactly 0 at t=0 (launch from
    # rest). Guard the first 0.1 s so an under-thrust scenario cannot be
    # mistaken for an instantaneous apogee.
    if t < 0.1:
        return -1.0
    return y[VZ]


_apogee_event.terminal = False
_apogee_event.direction = 1  # vz: negative (rising) -> positive (falling) == apogee


def run_sim(
    p,
    s0: State,
    t_max: float = 300.0,
    method: str = "RK45",
    rtol: float = 1e-8,
    atol: float = 1e-10,
) -> Result:
    """Integrate the equations of motion from `s0` until ground impact or
    `t_max`, whichever comes first."""
    y0 = np.array(s0, dtype=float)

    sol = solve_ivp(
        derivatives,
        (0.0, t_max),
        y0,
        method=method,
        args=(p,),
        events=[_ground_event, _apogee_event],
        dense_output=True,
        rtol=rtol,
        atol=atol,
    )

    t_ground = sol.t_events[0][0] if len(sol.t_events[0]) else None
    t_apogee = sol.t_events[1][0] if len(sol.t_events[1]) else None

    return Result(
        t=sol.t,
        y=sol.y,
        events={"apogee": t_apogee, "ground": t_ground},
        raw=sol,
    )

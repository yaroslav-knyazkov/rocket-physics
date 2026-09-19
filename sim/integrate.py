"""solve_ivp wrapper, events, Result (architecture.md SS5).

Owns all `scipy.integrate.solve_ivp` machinery -- event functions,
dense output. The equations of motion themselves live in dynamics.py;
this module only drives the numerics.

Step 8 (roadmap.md, optional): a small hand-written fixed-step RK4
integrator lives here too, selected via `method="rk4"`. It calls
`sim.dynamics.derivatives` exactly like `solve_ivp` does, with no
special-casing -- the point is to prove the physics module is genuinely
solver-agnostic, not to replace RK45 (architecture.md SS1/SS8: "No event
location, no step control" is an accepted, documented limitation of this
path, not a bug).
"""

from typing import Any, NamedTuple, Optional

import numpy as np
from scipy.integrate import solve_ivp

from sim.dynamics import derivatives
from sim.state import State, VZ, Z


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


class _LinearInterpolant:
    """Minimal stand-in for scipy's dense-output `OdeSolution`, so that RK4's
    `raw.sol(t)` can be called the same way RK45's is (e.g. by run.py). It
    is plain linear interpolation between the fixed-step grid points RK4
    already produced -- accurate to the grid resolution `dt`, nothing more.
    Do not expect RK45-dense-output-grade precision from it; it exists so
    that code written against `Result.raw.sol(...)` doesn't have to special-
    case which integrator produced the `Result`.
    """

    def __init__(self, t: np.ndarray, y: np.ndarray):
        self._t = t
        self._y = y

    def __call__(self, t):
        t_arr = np.atleast_1d(np.asarray(t, dtype=float))
        out = np.empty((self._y.shape[0], t_arr.size))
        for i in range(self._y.shape[0]):
            out[i] = np.interp(t_arr, self._t, self._y[i])
        return out if np.ndim(t) else out[:, 0]


class _RK4Raw(NamedTuple):
    sol: _LinearInterpolant


def _run_rk4(p, s0: State, t_max: float, dt: float) -> Result:
    """Fixed-step classical RK4 (roadmap.md Step 8, architecture.md SS1/SS8).

    Standard update:
        k1 = f(t, y)
        k2 = f(t + dt/2, y + dt/2*k1)
        k3 = f(t + dt/2, y + dt/2*k2)
        k4 = f(t + dt, y + dt*k3)
        y_next = y + dt/6*(k1 + 2*k2 + 2*k3 + k4)

    Unlike RK45 there is no adaptive step control and no event location:
    ground impact and apogee are found after the fact from a sign change
    between two consecutive grid points (z crossing 0 for impact, vz
    crossing from negative to positive for apogee), refined by linear
    interpolation within that one step -- same physical events as
    `_ground_event`/`_apogee_event` above, located to within roughly one
    `dt` of resolution rather than to solver tolerance. That is the known,
    documented limitation of this path (architecture.md SS8's decision
    table): it is a cross-check on `dynamics.py`, not a replacement for
    RK45.
    """
    y0 = np.array(s0, dtype=float)

    ts = [0.0]
    ys = [y0]

    t_apogee = None
    t_ground = None

    t = 0.0
    y = y0
    while t < t_max:
        dt_step = min(dt, t_max - t)

        k1 = derivatives(t, y, p)
        k2 = derivatives(t + dt_step / 2, y + dt_step / 2 * k1, p)
        k3 = derivatives(t + dt_step / 2, y + dt_step / 2 * k2, p)
        k4 = derivatives(t + dt_step, y + dt_step * k3, p)
        y_next = y + dt_step / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t_next = t + dt_step

        # Apogee: vz crosses from negative (rising) to positive (falling).
        # Guard the first 0.1 s exactly like _apogee_event -- vz is exactly
        # 0 at t=0 (launch from rest) and must not be mistaken for apogee.
        if t_apogee is None and t_next >= 0.1 and y[VZ] < 0.0 <= y_next[VZ]:
            frac = -y[VZ] / (y_next[VZ] - y[VZ])
            t_apogee = t + frac * dt_step

        # Ground impact: z crosses from negative to positive (z is
        # down-positive, so this is the rocket returning to launch
        # altitude). Guard the first 0.1 s exactly like _ground_event --
        # z is exactly 0 at t=0 and must not be mistaken for impact.
        if t_next >= 0.1 and y[Z] < 0.0 <= y_next[Z]:
            frac = -y[Z] / (y_next[Z] - y[Z])
            t_ground = t + frac * dt_step
            y_ground = y + frac * (y_next - y)
            ts.append(t_ground)
            ys.append(y_ground)
            t, y = t_ground, y_ground
            break

        ts.append(t_next)
        ys.append(y_next)
        t, y = t_next, y_next

    t_arr = np.array(ts)
    y_arr = np.array(ys).T  # shape (6, N), matches solve_ivp's sol.y

    return Result(
        t=t_arr,
        y=y_arr,
        events={"apogee": t_apogee, "ground": t_ground},
        raw=_RK4Raw(sol=_LinearInterpolant(t_arr, y_arr)),
    )


def run_sim(
    p,
    s0: State,
    t_max: float = 300.0,
    method: str = "RK45",
    rtol: float = 1e-8,
    atol: float = 1e-10,
    dt: float = 0.001,
) -> Result:
    """Integrate the equations of motion from `s0` until ground impact or
    `t_max`, whichever comes first.

    `method="rk4"` routes to the hand-written fixed-step integrator
    (`_run_rk4`) instead of `scipy.integrate.solve_ivp`; `dt` is only used
    in that path and ignored otherwise (roadmap.md Step 8). Every other
    `method` value (the default `"RK45"`, or any other scipy method name)
    is unchanged from before Step 8.
    """
    if method == "rk4":
        return _run_rk4(p, s0, t_max, dt)

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

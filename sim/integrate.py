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

Step 14: Adds burnout event detection for thrust curve cutoff.

Step 42 (Phase 2.7; main.tex/models.tex SSGravity > Direction, eq. `h_true`;
architecture.md SS24.2): the ground-impact event -- both the RK45 event
function `_ground_event` and `_run_rk4`'s manual crossing detection -- reads
`sim.gravity.ground_depth(t, y, p)` instead of the literal `y[Z]`.
`ground_depth` returns `y[Z]` unchanged (bit-for-bit) when
`p.gravity_direction == "parallel"`, and the curved-ground depth otherwise
(`gravity_direction in {"radial", "elliptical"}`). `_ground_event.direction`
and `.terminal` are unchanged -- `ground_depth` is built DOWN-positive
specifically so the existing sign convention still applies (see that
function's own docstring for why a literal `h_true` substitution would be
wrong). `_apogee_event`/`_burnout_event` are untouched -- this is an
impact/ground-event-only change (architecture.md SS24.2's scope note).

Step 45 (Phase 2.8; architecture.md SS25.5): `Result` gains a fifth field,
`params`, set in both `Result(...)` constructions below -- the `Params`
that produced the run, so `sim/plotting.py` can read `r.params` for the
curved altitude without a `p` argument on every plotting function (one
`Params` per `Result`, right even for a sweep's `dict[str, Result]`). No
event function is touched by this: `_ground_event`/`_apogee_event`/
`_burnout_event` are exactly as Step 42/14 left them.

Step 47 (Phase 2.10; architecture.md SS27.1): a non-terminal `rail_exit`
event, both integration paths -- purely informational (`dynamics.py`'s
`on_rail` branch already handles the on-rail/off-rail transition smoothly
inside the RHS; this event exists only so `Result.events` can report the
rail-exit time, mirroring `_burnout_event`'s role for the thrust cutoff).

Step 48 (Phase 2.10; architecture.md SS27.2): a non-terminal
`parachute_deploy` event, same shape/role as `rail_exit` above --
`dynamics.py`'s new parachute branch already handles the deployed/not-
deployed transition smoothly inside the RHS; this event exists only so
`Result.events` can report the deployment time.
"""

from typing import Any, NamedTuple, Optional

import numpy as np
from scipy.integrate import solve_ivp

from sim import dynamics, forces
from sim.dynamics import derivatives
from sim.state import State, VZ, Z
from sim import gravity, thrust_curve


class Result(NamedTuple):
    t: np.ndarray                     # time samples [s]
    y: np.ndarray                     # state history, shape (6, N)
    events: dict[str, Optional[float]]  # {"apogee": t | None, "ground": t | None, "burnout": t | None, "rail_exit": t | None, "parachute_deploy": t | None}
    raw: Any                          # the scipy OdeResult (e.g. for sol.sol(t))
    params: Any                       # the Params that produced this run -- Step 45, architecture.md SS25.5


def _ground_event(t, y, p):
    # Gotcha (architecture.md SS1): z is 0 at launch (t=0), which can be
    # picked up as a spurious root immediately -- e.g. if thrust never
    # exceeded gravity the rocket would start "falling" from z=0 right
    # away. Guard the first 0.1 s.
    if t < 0.1:
        return 1.0
    # Step 42 (architecture.md SS24.2): ground_depth is y[Z] itself for
    # "parallel" (bit-for-bit), and the curved-ground depth otherwise.
    return gravity.ground_depth(t, y, p)


_ground_event.terminal = True
_ground_event.direction = 1  # z increasing through 0 == falling (z is down-positive)


def _apogee_event(t, y, p):
    """Apogee event: `y[VZ]` crosses from negative (rising) to positive
    (falling), in the launch-frame vertical velocity -- unchanged by
    Step 45 (Phase 2.8; architecture.md SS25.5/SS25.8), deliberately.
    Apogee still means "the top of the trajectory in the launch frame";
    what Step 45 changes is only the *altitude value* reported at that
    instant (`run.py`, now `gravity.altitude_agl`), never *which instant*
    is apogee. On a curved (`gravity_direction != "parallel"`) run the
    reported curved altitude at this event's time is consequently *not*
    the maximum of the curved altitude over the flight
    (`dh_true/dt = +0.47 m/s` at `vx=300 m/s, x=10 km` where `vz=0`,
    architecture.md SS24.2/SS25.5) -- a documented property of reporting a
    surface-referenced altitude at a launch-frame apogee, not a defect.
    Redefining apogee as `max h_true` is a separate modelling decision with
    its own tests (architecture.md SS25.8) -- do not "finish the job" here.
    """
    # Same gotcha as the ground event: vz is exactly 0 at t=0 (launch from
    # rest). Guard the first 0.1 s so an under-thrust scenario cannot be
    # mistaken for an instantaneous apogee.
    if t < 0.1:
        return -1.0
    return y[VZ]


_apogee_event.terminal = False
_apogee_event.direction = 1  # vz: negative (rising) -> positive (falling) == apogee


_BURNOUT_EPS = 1e-9  # [N], see _burnout_event's docstring


def _burnout_event(t, y, p):
    """Burnout event: triggers when thrust drops to zero after burnout.

    Returns `thrust(t) - _BURNOUT_EPS` so that zero crossings of the
    *shifted* function indicate burnout. `direction = -1` below restricts
    detection to falling edges (positive to negative) only.

    No t=0 guard is needed here, unlike `_ground_event`/`_apogee_event`: a
    motor curve starts at zero thrust and rises (ignition), so the
    crossing at t=0 is rising, not falling, and `direction=-1` already
    excludes it.

    The `_BURNOUT_EPS` shift exists for a different, real reason: after
    burnout (or when `p.motor_curve == ""` and thrust is zero for the
    whole flight) the event function is *exactly* zero over an extended
    interval, not just momentarily. `solve_ivp` classifies a step as a
    "falling" (or "rising") edge using `<=`/`>=` comparisons, so two
    consecutive samples that are both exactly 0.0 satisfy *both* the
    falling and rising conditions -- every accepted step in a flat-zero
    region gets reported as a spurious event (verified directly: with
    `p.motor_curve == ""`, the unshifted event fires at t=0.0 every time,
    even though thrust is never positive to begin with). Subtracting a
    tiny epsilon makes the "thrust is off" region strictly negative
    instead of exactly zero, which removes the ambiguity: a real burnout
    still crosses through -_BURNOUT_EPS (shifting the detected time by
    much less than any physically meaningful resolution), while a
    genuinely-always-zero curve now stays strictly negative and never
    triggers at all.
    """
    return thrust_curve.thrust(t, y, p) - _BURNOUT_EPS


_burnout_event.terminal = False  # Simulation continues past burnout (coast/descent)
_burnout_event.direction = -1    # Trigger on falling edge (positive to negative)


def _rail_exit_event(t, y, p):
    """Rail-exit event: triggers when `dynamics.rail_distance` crosses
    `p.L_rail` (architecture.md SS27.1). Non-terminal -- `dynamics.py`'s
    `on_rail` branch already handles the on-rail/off-rail transition
    smoothly inside the RHS; this event exists purely so `Result.events`
    can report the rail-exit time/speed, the same informational role as
    `_burnout_event`.

    Same t=0/off-switch guard as `_ground_event`/`_burnout_event`:
    `p.L_rail <= 0.0` (the default) means the rocket is never on the rail
    (see `dynamics.on_rail`), so this event must never fire.
    """
    if t < 0.1 or p.site.L_rail <= 0.0:
        return -1.0
    return dynamics.rail_distance(y, p) - p.site.L_rail


_rail_exit_event.terminal = False
_rail_exit_event.direction = 1  # rail_distance - L_rail: negative -> positive == leaving the rail


def _parachute_deploy_event(t, y, p):
    """Parachute-deploy event: triggers when `forces.parachute_deployed`
    flips from false to true (architecture.md SS27.2). Non-terminal, same
    purely-informational role as `_rail_exit_event` above -- `dynamics.py`'s
    parachute branch already handles the transition smoothly inside the
    RHS; this event exists only so `Result.events` can report the
    deployment time.

    `p.parachute_model == "none"` (the default) makes `parachute_deployed`
    always `False`, so this never fires -- the same off-switch guarantee
    every other model-selection event in this module gives.
    """
    return 1.0 if forces.parachute_deployed(t, y, p) else -1.0


_parachute_deploy_event.terminal = False
_parachute_deploy_event.direction = 1  # false (-1) -> true (+1) == deployment


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
    t_burnout = None
    t_rail_exit = None
    t_parachute_deploy = None

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

        # Ground impact: ground_depth crosses from negative to positive
        # (DOWN-positive, so this is the rocket returning to/through the
        # ground surface -- Step 42, architecture.md SS24.2). Guard the
        # first 0.1 s exactly like _ground_event -- ground_depth is exactly
        # 0 at t=0 and must not be mistaken for impact. `d_now`/`d_next`
        # replace the old literal `y[Z]`/`y_next[Z]`, bit-for-bit identical
        # to them when `p.gravity_direction == "parallel"`.
        d_now = gravity.ground_depth(t, y, p)
        d_next = gravity.ground_depth(t_next, y_next, p)
        if t_next >= 0.1 and d_now < 0.0 <= d_next:
            frac = -d_now / (d_next - d_now)
            t_ground = t + frac * dt_step
            y_ground = y + frac * (y_next - y)
            ts.append(t_ground)
            ys.append(y_ground)
            t, y = t_ground, y_ground
            break

        # Burnout: thrust crosses from positive to negative (engine cutoff).
        # No t=0 guard needed here -- see _burnout_event's docstring above:
        # a motor curve starts at zero and rises, so `thrust_now > 0.0` is
        # false at t=0 and this cannot fire on ignition, only on cutoff.
        if t_burnout is None:
            thrust_now = thrust_curve.thrust(t, y, p)
            thrust_next = thrust_curve.thrust(t_next, y_next, p)
            if thrust_now > 0.0 and thrust_next <= 0.0:
                frac = -thrust_now / (thrust_next - thrust_now)
                t_burnout = t + frac * dt_step

        # Rail exit: `rail_distance - L_rail` crosses from negative to
        # positive (Step 47, architecture.md SS27.1), same t=0/off-switch
        # guard as `_rail_exit_event`.
        if t_rail_exit is None and p.site.L_rail > 0.0 and t_next >= 0.1:
            r_now = dynamics.rail_distance(y, p) - p.site.L_rail
            r_next = dynamics.rail_distance(y_next, p) - p.site.L_rail
            if r_now < 0.0 <= r_next:
                frac = -r_now / (r_next - r_now)
                t_rail_exit = t + frac * dt_step

        # Parachute deploy: `forces.parachute_deployed` flips from false to
        # true (Step 48, architecture.md SS27.2), mirroring `_rail_exit`'s
        # manual-detection shape above.
        if t_parachute_deploy is None:
            dep_now = 1.0 if forces.parachute_deployed(t, y, p) else -1.0
            dep_next = 1.0 if forces.parachute_deployed(t_next, y_next, p) else -1.0
            if dep_now < 0.0 <= dep_next:
                frac = -dep_now / (dep_next - dep_now)
                t_parachute_deploy = t + frac * dt_step

        ts.append(t_next)
        ys.append(y_next)
        t, y = t_next, y_next

    t_arr = np.array(ts)
    y_arr = np.array(ys).T  # shape (6, N), matches solve_ivp's sol.y

    return Result(
        t=t_arr,
        y=y_arr,
        events={"apogee": t_apogee, "ground": t_ground, "burnout": t_burnout, "rail_exit": t_rail_exit, "parachute_deploy": t_parachute_deploy},
        raw=_RK4Raw(sol=_LinearInterpolant(t_arr, y_arr)),
        params=p,
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
        events=[_ground_event, _apogee_event, _burnout_event, _rail_exit_event, _parachute_deploy_event],
        dense_output=True,
        rtol=rtol,
        atol=atol,
    )

    t_ground = sol.t_events[0][0] if len(sol.t_events[0]) else None
    t_apogee = sol.t_events[1][0] if len(sol.t_events[1]) else None
    t_burnout = sol.t_events[2][0] if len(sol.t_events[2]) else None
    t_rail_exit = sol.t_events[3][0] if len(sol.t_events[3]) else None
    t_parachute_deploy = sol.t_events[4][0] if len(sol.t_events[4]) else None

    return Result(
        t=sol.t,
        y=sol.y,
        events={"apogee": t_apogee, "ground": t_ground, "burnout": t_burnout, "rail_exit": t_rail_exit, "parachute_deploy": t_parachute_deploy},
        raw=sol,
        params=p,
    )

"""apps/sim/engine/integrate.py -- solve_ivp wrapper, events, Result (architecture.md SS5).

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

Step 59 (Phase 2.11 rewrite pass; architecture-28-rewrite.md SS28.8): an
opt-in sampled-data/zero-order-hold mode, gated by `p.solver.sample_rate_hz
> 0.0` (the project's standard unset-sentinel convention) and requiring
`p.solver.method == "rk4"` -- `run_sim` raises `ValueError` immediately for
any other method, since an adaptive solver cannot honour a hold boundary.
`_run_rk4` gains an optional `sample_rate_hz` parameter (default `0.0`,
every pre-Step-59 call site unaffected): when it is positive, a `Hold`
(`sim/sampling.py`) is recomputed once at the start of every fixed-rate
tick and held constant across every RK4 substep inside that tick, instead
of `derivatives` being called with `hold=None` throughout (the unsampled,
bit-for-bit-unchanged default). This is a single refactor of the existing
while-loop, not a second event-detection implementation: the event
crossings below (apogee/ground/burnout/rail-exit/parachute-deploy) are
read from exactly the same code, whether or not sampling is active --
only whether/when a fresh `Hold` is computed differs, via one small
counter. `sim/sampling.py` is imported locally, only inside the
`sample_rate_hz > 0.0` branch, so the default `RK45` path (and the
`rk4` path with sampling off) never imports or touches it at all.

Step 104 (Phase 2.17; D-116/D-128; task-104-segmented-rk45.md): a second,
also opt-in sampled-data path -- `p.solver.method == "rk45_seg"` -- for
when the fixed-step `rk4` + ZOH path (Step 59) is too slow for a large
sampled-data ensemble (measured in qa-report-2.17-step105.md SS7: a
100-sample ascent-to-apogee ensemble landed at the D-116 "~5 min"
threshold under rk4; a full-flight ensemble, ~2.5 hours). One
`solve_ivp(method="RK45", ...)` call per sampling tick, instead of one
hand-written RK4 substep per tick -- the adaptive solver's own step
control runs freely inside a tick, and the hold boundary between ticks
is a segment boundary, never a mid-step discontinuity, so it is honoured
exactly, the same ZOH correctness argument Step 59's own docstring makes
for its RK4 stages. Gated the same way Step 59's `rk4` path is
(`sample_rate_hz > 0.0` required), PLUS a new, symmetric gate:
`method == "rk45_seg"` itself requires `sample_rate_hz > 0.0` (this
method exists only to serve the ZOH mode; an un-sampled run has no
reason to ask for it). `_run_rk4` is NOT touched by this step -- zero
diff, confirmed by construction: the new path is dispatched on a
brand-new `method` string no existing call can reach.
"""

import math
from typing import Any, NamedTuple, Optional

import numpy as np
from scipy.integrate import solve_ivp

from apps.sim.engine import aero, control, dynamics, forces, roll
from apps.sim.engine.dynamics import derivatives
from apps.sim.engine.state import State, VZ, Z, to_vector
from apps.sim.engine import gravity, thrust_curve

# Step 32 (Phase 3; architecture-37-step32-3d-integration-harness.md
# SS37.7/32.2, D-32.8): the 3D driver's own imports. Verified acyclic
# (SS37.7/32.2's own note): `forces3d` imports `aero, control, dynamics,
# forces, quaternion, flow, state3d`; it does NOT import `integrate`, so
# the new edge `integrate -> forces3d` (and `-> dynamics3d`, `-> state3d`,
# `-> quaternion`, `-> inertia`) closes no cycle.
from apps.sim.engine import dynamics3d, forces3d, inertia, quaternion, state3d


class Result(NamedTuple):
    t: np.ndarray                     # time samples [s]
    y: np.ndarray                     # state history, shape (width, N); width is 7 or 10, sim/state.py
    events: dict[str, Optional[float]]  # {"apogee": t | None, "ground": t | None, "burnout": t | None, "rail_exit": t | None, "parachute_deploy": t | None}
    raw: Any                          # the scipy OdeResult (e.g. for sol.sol(t))
    params: Any                       # the Params that produced this run -- Step 45, architecture.md SS25.5


# ----------------------------------------------------------------------
# Step 32 (Phase 3; architecture-37-step32-3d-integration-harness.md
# SS37.2/D-32.1, option C -- "projection seam + thin 3D drivers"):
# `_project_identity`/`_events_for` below are ADDITIVE, placed above the
# five event functions so the seam is visible as a seam, and touch no
# pinned function body. The five event predicates below were measured
# (SS37.1) to read only `y[X]`, `y[Z]`, `y[VZ]` out of the state they are
# given -- all three also recoverable from a 13-component 3D state via
# `apps.sim.engine.forces3d._s2d`. Rather than duplicate the five
# predicates for 3D (option A) or rewrite the whole integration loop
# behind a generic state-layout abstraction (option B, the deeper but far
# more expensive end state -- SS37.2), `_events_for(project)` reuses each
# predicate's BODY verbatim, wrapping it so that the state it receives is
# first run through `project`. For the 2D path `project` is
# `_project_identity`, a true no-op (`run_sim`/`_run_rk4`/
# `_run_segmented_rk45` keep calling the five module-level functions
# directly -- they never go through this factory; its only 2D-side
# consumer is this module's own self-test, proving the seam is faithful
# before any 3D driver exists to use it for real). For the 3D path
# (sub-step 32.2 on), `project = apps.sim.engine.forces3d._s2d`.
def _project_identity(y: np.ndarray) -> np.ndarray:
    """The 2D path's projection: a true no-op, `y` unchanged."""
    return y


def _events_for(project):
    """Build the five event callables against a state first run through
    `project` -- D-32.1/C. Each wrapper calls the matching module-level
    predicate UNCHANGED (`fn(t, project(y), p)`), and carries over that
    predicate's own `.terminal`/`.direction` attributes, since
    `scipy.integrate.solve_ivp`'s `events=` protocol reads those
    attributes off the callable it is given, not off some separate
    registry. Returns a 5-tuple in the same order `run_sim`'s own
    `events=[...]` list uses: `(ground, apogee, burnout, rail_exit,
    parachute_deploy)`.
    """

    def _wrap(fn):
        def _wrapped(t, y, p):
            return fn(t, project(y), p)

        _wrapped.terminal = fn.terminal
        _wrapped.direction = fn.direction
        return _wrapped

    return (
        _wrap(_ground_event),
        _wrap(_apogee_event),
        _wrap(_burnout_event),
        _wrap(_rail_exit_event),
        _wrap(_parachute_deploy_event),
    )


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


def _run_rk4(p, s0: State, t_max: float, dt: float, sample_rate_hz: float = 0.0) -> Result:
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

    Step 59 (architecture-28-rewrite.md SS28.8): `sample_rate_hz` (default
    `0.0`, off) adds an opt-in zero-order-hold mode on top of the same
    fixed-step loop, rather than a second implementation of it:

        for each tick k:                     # period T_s = 1/sample_rate_hz
            hold = sampling.sample(t_k, y_k, p, prev=hold)
            for each of n_sub = T_s/dt substeps:
                y <- RK4(derivatives, t, y, p, hold)   # hold constant all 4 stages
                ... the same apogee/ground/burnout/rail/parachute crossing
                    detection below, unchanged ...

    Implemented here as a single counter, `substep_in_tick`, that resets to
    0 (triggering a fresh `sampling.sample(...)` call) exactly every
    `n_sub` passes through the loop below -- not by nesting a second loop,
    so the event-detection code is written exactly once, serving both the
    sampled and the un-sampled paths. `n_sub = T_s/dt` must be an exact
    integer multiple (checked below with a tolerance tight enough to catch
    any genuine mismatch while tolerating ordinary floating-point roundoff
    in the division itself); a non-integer ratio raises rather than
    silently rounding, because silently rounding would change the
    effective sample rate from the one configured. `sample_rate_hz = 0.0`
    (the default) never imports `sim.sampling`, never constructs a `Hold`,
    and calls `derivatives(t, y, p, None)` throughout -- bit-for-bit
    identical to every pre-Step-59 call (`hold=None` is the default
    `derivatives` already had to honour for the RK45 path).
    """
    y0 = to_vector(s0, p)

    ts = [0.0]
    ys = [y0]

    t_apogee = None
    t_ground = None
    t_burnout = None
    t_rail_exit = None
    t_parachute_deploy = None

    sampling_on = sample_rate_hz > 0.0
    if sampling_on:
        # Local import (module docstring): the default RK45 path, and the
        # un-sampled rk4 path, must never import/touch sim.sampling at all.
        from apps.sim.engine import sampling

        T_s = 1.0 / sample_rate_hz
        n_sub_f = T_s / dt
        n_sub = round(n_sub_f)
        if not math.isclose(T_s, n_sub * dt, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError(
                f"p.solver.sample_rate_hz={sample_rate_hz} gives a sample "
                f"period T_s={T_s}s that is not an exact integer multiple "
                f"of p.solver.dt={dt}s (T_s/dt={n_sub_f}): the sampled-data "
                "mode requires every tick to span a whole number of RK4 "
                "substeps, or the effective sample rate would silently "
                "differ from the one configured (architecture-28-rewrite.md "
                "SS28.8.2, point 3)."
            )
    else:
        n_sub = None

    t = 0.0
    y = y0
    hold = None
    substep_in_tick = 0  # 0 on entry forces a fresh sample on the very first substep
    while t < t_max:
        if sampling_on and substep_in_tick == 0:
            # Sampled at the tick's own start, (t, y) -- the causally
            # correct flight-computer model (architecture-28-rewrite.md
            # SS28.8.2, point 2): measure, compute, hold until the next tick.
            hold = sampling.sample(t, y, p, prev=hold)

        dt_step = min(dt, t_max - t)

        # `hold` is held constant across all four stages of this one
        # substep (architecture-28-rewrite.md SS28.8.2, point 1) -- inside
        # a substep the RHS is again a smooth function of (t, y), so RK4's
        # order is preserved, and the hold discontinuity lands exactly on
        # a step boundary, never inside one. `hold is None` throughout
        # whenever sampling is off, reproducing every pre-Step-59 call.
        k1 = derivatives(t, y, p, hold)
        k2 = derivatives(t + dt_step / 2, y + dt_step / 2 * k1, p, hold)
        k3 = derivatives(t + dt_step / 2, y + dt_step / 2 * k2, p, hold)
        k4 = derivatives(t + dt_step, y + dt_step * k3, p, hold)
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

        if sampling_on:
            substep_in_tick = (substep_in_tick + 1) % n_sub

    t_arr = np.array(ts)
    y_arr = np.array(ys).T  # shape (6, N), matches solve_ivp's sol.y

    return Result(
        t=t_arr,
        y=y_arr,
        events={"apogee": t_apogee, "ground": t_ground, "burnout": t_burnout, "rail_exit": t_rail_exit, "parachute_deploy": t_parachute_deploy},
        raw=_RK4Raw(sol=_LinearInterpolant(t_arr, y_arr)),
        params=p,
    )


_NON_TERMINAL_EVENTS = (
    ("apogee", _apogee_event),
    ("burnout", _burnout_event),
    ("rail_exit", _rail_exit_event),
    ("parachute_deploy", _parachute_deploy_event),
)


def _pending_events(found: "dict[str, Optional[float]]"):
    """Which events still need watching in the NEXT segment (Step 104,
    task-104-segmented-rk45.md SS104.5). `_ground_event` is unconditionally
    always included (terminal, stops the whole run, not first-occurrence-
    tracked). Each of the other four is dropped the moment `found[name]` is
    no longer `None` -- it has already fired once, and `Result.events` can
    only ever record one time per key (never a list), so re-including an
    already-fired event risks a LATER segment's spurious/second crossing
    (e.g. floating-point noise sitting exactly at `thrust == 0` well after
    burnout) silently overwriting the correct first-occurrence time. Pure
    function of `found` alone -- no `solve_ivp` call, no segment state --
    independently unit-testable."""
    pending = [(name, fn) for name, fn in _NON_TERMINAL_EVENTS if found[name] is None]
    names = ["ground"] + [name for name, _ in pending]
    fns = [_ground_event] + [fn for _, fn in pending]
    return names, fns


class _SegmentedSol:
    """Stitches per-segment scipy dense `OdeSolution` callables
    (`solve_ivp(..., dense_output=True).sol`) into one seamless `raw.sol(t)`
    spanning the WHOLE run -- the exact same call shape `_LinearInterpolant`
    and the real single-call RK45 path's `OdeSolution` already give every
    caller (scalar t -> shape-(6,) array; array t -> shape-(6, N) array), so
    `Result.raw.sol(...)` needs no special-casing per integrator anywhere
    outside this module (task-104-segmented-rk45.md SS104.6). Each
    segment's own `sol` IS scipy's exact dense interpolant for that segment
    -- this class only decides WHICH segment's `sol` to delegate to for a
    given `t`, by binary search over `starts` (each segment's own
    `t_start`, strictly increasing, absolute time -- SS104.4). A `t`
    landing exactly on a shared segment boundary is served by the segment
    whose OWN `t_start` equals that `t` (`searchsorted(..., side="right")`
    semantics -- confirmed directly against the formula, not assumed: for
    `starts=[0, 1, 2]` and `t=1.0` this resolves to segment index 1, not 0);
    `t` outside `[starts[0], run end]` is clamped to the nearest edge
    segment, same "caller's responsibility to stay in range" contract every
    other `raw.sol` implementation in this codebase already has.
    """

    def __init__(self, starts: "list[float]", sols: "list"):
        self._starts = np.asarray(starts, dtype=float)
        self._sols = sols

    def __call__(self, t):
        t_arr = np.atleast_1d(np.asarray(t, dtype=float))
        idx = np.searchsorted(self._starts, t_arr, side="right") - 1
        idx = np.clip(idx, 0, len(self._sols) - 1)
        # State width read from the first delegate call rather than
        # hardcoded -- `State` grew a 7th component (mass, Step 36) after
        # this class's own design sketch (task-104-segmented-rk45.md
        # SS104.6) assumed 6; staying generic here means a future State
        # width change needs no edit in this module.
        out = None
        for seg_idx in np.unique(idx):
            mask = idx == seg_idx
            vals = self._sols[seg_idx](t_arr[mask])
            if out is None:
                out = np.empty((vals.shape[0], t_arr.size))
            out[:, mask] = vals
        return out if np.ndim(t) else out[:, 0]


class _SegRK45Raw(NamedTuple):
    # `_SegmentedSol` in the normal (>=1 segment) case; `_LinearInterpolant`
    # in the degenerate `t_max <= 0.0` case (see `_run_segmented_rk45`'s own
    # fallback) -- both satisfy the same `sol(t)` call contract.
    sol: Any


def _run_segmented_rk45(p, s0: State, t_max: float, sample_rate_hz: float,
                         rtol: float, atol: float) -> Result:
    """Segmented RK45 + zero-order hold (Step 104, D-116/D-128) -- see
    task-104-segmented-rk45.md SS104.4-SS104.6 for the full design
    rationale. One `solve_ivp(method="RK45", ...)` call per sampling tick;
    each segment's own `t_span` is ABSOLUTE time (no 0-reset, no offset
    arithmetic needed when stitching -- SS104.4). Event functions are the
    same five module-level callables the plain-RK45 path uses, reused
    verbatim: `_ground_event` (terminal) every segment; the other four
    first-occurrence-only across the whole run via `_pending_events`.
    """
    from apps.sim.engine import sampling  # local import -- Step 59's own precedent;
                               # never imported on the default RK45 path
                               # or the un-sampled rk4 path.

    y0 = to_vector(s0, p)
    T_s = 1.0 / sample_rate_hz

    t_chunks = [np.array([0.0])]
    y_chunks = [y0.reshape(-1, 1)]  # State width, not hardcoded (see _SegmentedSol's own note)
    seg_starts: list = []
    seg_sols: list = []

    found = {"apogee": None, "burnout": None, "rail_exit": None, "parachute_deploy": None}
    t_ground = None

    t = 0.0
    y = y0
    hold = None
    while t < t_max:
        hold = sampling.sample(t, y, p, prev=hold)
        t_end = min(t + T_s, t_max)
        if t_end <= t:
            break  # floating-point edge at the very last tick; nothing left to integrate

        names, fns = _pending_events(found)

        # Deviation from task-104-segmented-rk45.md SS104.4's literal code
        # sketch, found while implementing (not guessed around): scipy's
        # `solve_ivp(..., args=...)` passes the SAME `args` tuple to `fun`
        # AND every function in `events=` (documented scipy behaviour,
        # confirmed directly against the installed scipy 1.18.1). The
        # sketch's own `args=(p, hold)` would therefore call
        # `_ground_event(t, y, p, hold)` -- 4 args into a 3-arg function,
        # a TypeError on the very first tick. Fixed by keeping `args=(p,)`
        # (bit-for-bit what the event functions -- reused verbatim,
        # SS104.4's own non-goal -- already expect) and threading `hold`
        # into the RHS only, via a closure fresh each tick (`_hold=hold`
        # default-argument binding avoids any late-binding surprise, even
        # though this tick's `sol` is always fully consumed before `hold`
        # is reassigned next iteration).
        def _rhs(tt, yy, pp, _hold=hold):
            return derivatives(tt, yy, pp, _hold)

        sol = solve_ivp(
            _rhs, (t, t_end), y, method="RK45",
            args=(p,), events=fns, dense_output=True,
            rtol=rtol, atol=atol,
        )
        if sol.status == -1:
            raise RuntimeError(f"segmented RK45 tick at t={t} failed: {sol.message}")

        for idx, name in enumerate(names):
            if name != "ground" and len(sol.t_events[idx]):
                found[name] = float(sol.t_events[idx][0])

        seg_starts.append(t)
        seg_sols.append(sol.sol)
        t_chunks.append(sol.t[1:])
        y_chunks.append(sol.y[:, 1:])

        t, y = float(sol.t[-1]), sol.y[:, -1]

        if sol.status == 1:
            # The only terminal event ever passed is _ground_event
            # (SS104.5) -- confirmed by construction via _pending_events.
            t_ground = float(sol.t_events[0][0])
            break

    t_arr = np.concatenate(t_chunks)
    y_arr = np.concatenate(y_chunks, axis=1)

    # Degenerate input (`t_max <= 0.0`): the `while` loop above never ran,
    # so `seg_sols` is empty -- found during code-review, not anticipated
    # by task-104-segmented-rk45.md's own SS104.9 ("no new guard needed"
    # reasoning, which only holds because the SIBLING paths don't crash on
    # this input either). `_SegmentedSol([], [])` would `IndexError` on
    # any later `raw.sol(t)` call (`self._sols[-1]` on an empty list);
    # fall back to the same single-point constant-extrapolation
    # `_LinearInterpolant` `_run_rk4` already relies on for this exact
    # degenerate case, rather than leaving a crash-on-first-use landmine.
    sol_impl = _SegmentedSol(seg_starts, seg_sols) if seg_sols else _LinearInterpolant(t_arr, y_arr)

    return Result(
        t=t_arr,
        y=y_arr,
        events={
            "apogee": found["apogee"], "ground": t_ground,
            "burnout": found["burnout"], "rail_exit": found["rail_exit"],
            "parachute_deploy": found["parachute_deploy"],
        },
        raw=_SegRK45Raw(sol=sol_impl),
        params=p,
    )


def run_sim(p, s0: State) -> Result:
    """Integrate the equations of motion from `s0` until ground impact or
    `p.solver.t_max`, whichever comes first.

    Step 53 (architecture.md SS28.7, decision D-10): strict `run_sim(p, s0)`
    signature, no solver override kwargs. All solver settings are read from
    `p.solver` (`sim/params.py`'s `Solver` group) so that `Result.params` is
    always the true record of what produced the run -- a `Result` can no
    longer carry `solver.method == "RK45"` while having actually been
    integrated with `rk4`. Callers that want non-default solver settings
    build the `Params` first, e.g. `params.with_solver(p, method="rk4",
    dt=1e-3)`, then call `run_sim(p, s0)`.

    `p.solver.method == "rk4"` routes to the hand-written fixed-step
    integrator (`_run_rk4`) instead of `scipy.integrate.solve_ivp`;
    `p.solver.dt` is only used in that path and ignored otherwise
    (roadmap.md Step 8). Every other `method` value (the default `"RK45"`,
    or any other scipy method name) is unchanged from before Step 8.

    Step 59 (architecture-28-rewrite.md SS28.8, decision D-11):
    `p.solver.sample_rate_hz > 0.0` opts into the sampled-data/zero-order-
    hold mode (`sim/sampling.py`), and REQUIRES `p.solver.method == "rk4"`
    -- an adaptive method cannot honour a hold boundary, so any other
    `method` with a nonzero `sample_rate_hz` raises `ValueError`
    immediately, before any integration is attempted. `sample_rate_hz =
    0.0` (the default) is the off switch on both integration paths,
    bit-for-bit: this check cannot fire, and `_run_rk4` never imports
    `sim.sampling` or constructs a `Hold`.

    Step 104 (D-116/D-128): `p.solver.method == 'rk45_seg'` opts into a
    second sampled-data path, segmented RK45, gated the same way plus its
    own sample_rate_hz>0.0 requirement -- see task-104-segmented-rk45.md.

    Step 103 (architecture-35-paper-alignment.md SS35.6, D-114): an
    unregistered `p.actuator.model` also raises `ValueError` here,
    immediately -- a deliberate exception to this project's usual lazy-
    KeyError-at-first-dispatch convention for model-selection strings
    (SS7), because the actuator dispatch only happens deep inside the
    sampled-data loop (`sim/sampling.py`'s `sample()`, called once per
    tick), where a typo would otherwise only surface after however many
    ticks of a potentially long integration had already run.

    Step 107: a registered sampled law (sim.control.known_sampled_laws())
    also raises here, immediately, if sample_rate_hz <= 0.0 -- same
    eager-validation rationale as the actuator-model guard above
    (task-107-sampled-laws-registry.md).

    Step 109 (task-109-roll-reaction-wheel.md SS109.7.2): an unregistered
    `p.roll.model`/`p.roll.law`, or `p.roll.I_x <= p.roll.I_w` while the
    roll model is on, also raise here, immediately -- `sim/roll.py`
    deliberately has no defensive fallback for the inertia check (its own
    SS109.4.4 docstring note).
    """
    aero.reset_oob_warning()  # Step 112: once-per-run out-of-range alpha warning
    method = p.solver.method
    t_max = p.solver.t_max
    rtol = p.solver.rtol
    atol = p.solver.atol
    dt = p.solver.dt
    sample_rate_hz = p.solver.sample_rate_hz

    if p.actuator.model not in control.known_actuator_models():
        raise ValueError(
            f"p.actuator.model={p.actuator.model!r} is not a registered "
            f"actuator model (known: {sorted(control.known_actuator_models())}) "
            "(architecture-35-paper-alignment.md SS35.6)."
        )

    if p.control.airbrake_model in control.known_sampled_laws() and sample_rate_hz <= 0.0:
        raise ValueError(
            f"p.control.airbrake_model={p.control.airbrake_model!r} is a "
            f"registered sampled law (known: {sorted(control.known_sampled_laws())}) "
            "and requires p.solver.sample_rate_hz > 0.0 (architecture-35-"
            "paper-alignment.md SS35.4.4, task-107-sampled-laws-registry.md): "
            "a sampled law carries state across ticks and only makes sense "
            "under the sampled-data/ZOH mode."
        )

    if sample_rate_hz > 0.0 and method not in ("rk4", "rk45_seg"):
        raise ValueError(
            f"p.solver.sample_rate_hz={sample_rate_hz} requires "
            f"p.solver.method in {{'rk4', 'rk45_seg'}} (got method={method!r}): "
            "a plain adaptive integrator cannot honour a zero-order-hold "
            "boundary (architecture-28-rewrite.md SS28.8.2; Step 104 adds "
            "'rk45_seg' as the second, segmented-adaptive option, "
            "task-104-segmented-rk45.md)."
        )

    if method == "rk45_seg" and sample_rate_hz <= 0.0:
        raise ValueError(
            f"p.solver.method='rk45_seg' requires sample_rate_hz > 0.0 "
            f"(got sample_rate_hz={sample_rate_hz}): segmented RK45 exists "
            "only to serve the sampled-data/ZOH mode -- for an un-sampled "
            "run use method='RK45' instead (task-104-segmented-rk45.md "
            "SS104.2)."
        )

    # Step 109 (task-109-roll-reaction-wheel.md SS109.7.2): eager validation
    # of the roll model/law, before any integration is attempted -- same
    # rationale as the actuator-model guard above (a typo in a model-
    # selection string that only dispatches deep inside the integration
    # loop must fail before any integration starts). Ordering is load-
    # bearing: the `roll.model` check comes FIRST, so an unregistered model
    # name reports itself rather than producing a confusing inertia
    # complaint from the checks below it.
    if p.roll.model not in roll.known_roll_models():
        raise ValueError(
            f"p.roll.model={p.roll.model!r} is not a registered roll model "
            f"(known: {sorted(roll.known_roll_models())}) "
            "(task-109-roll-reaction-wheel.md SS109.3.1)."
        )

    if p.roll.model != "none":
        if p.roll.law not in roll.known_roll_laws():
            raise ValueError(
                f"p.roll.law={p.roll.law!r} is not a registered roll law "
                f"(known: {sorted(roll.known_roll_laws())}) "
                "(task-109 SS109.4.2)."
            )
        if p.roll.I_x <= p.roll.I_w:
            raise ValueError(
                f"p.roll.I_x={p.roll.I_x} must exceed p.roll.I_w={p.roll.I_w}: "
                "I_x is the vehicle's axial inertia with the wheel INCLUDED and "
                "locked, so the airframe-alone inertia I_x - I_w (the denominator "
                "of eq. (2)) must be positive (task-109 SS109.1.1). I_x = 0.0 is "
                "the unset default and is never valid with the roll model on."
            )

    if method == "rk4":
        result = _run_rk4(p, s0, t_max, dt, sample_rate_hz)
        _warn_if_mach_blind(result)
        return result

    if method == "rk45_seg":
        result = _run_segmented_rk45(p, s0, t_max, sample_rate_hz, rtol, atol)
        _warn_if_mach_blind(result)
        return result

    y0 = to_vector(s0, p)

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

    result = Result(
        t=sol.t,
        y=sol.y,
        events={"apogee": t_apogee, "ground": t_ground, "burnout": t_burnout, "rail_exit": t_rail_exit, "parachute_deploy": t_parachute_deploy},
        raw=sol,
        params=p,
    )
    _warn_if_mach_blind(result)
    return result


def _warn_if_mach_blind(result: Result) -> None:
    """Step 92 (D-83): pure diagnostic, never alters `result`. Imported
    lazily -- `sim.mach_warning` pulls in `sim.flow`."""
    from apps.sim.engine.mach_warning import warn_if_mach_blind

    warn_if_mach_blind(result, stacklevel=4)


# ----------------------------------------------------------------------
# Step 32 (Phase 3; architecture-37-step32-3d-integration-harness.md) --
# the 3D integration harness. D-32.1/C: `run_sim_3d` reuses `Result`,
# `_LinearInterpolant`, `_pending_events` (not needed here -- see D-32.2)
# and the five event predicates UNCHANGED, via `_events_for(forces3d.
# _s2d)`. Nothing above this comment, and nothing inside `run_sim`/
# `_run_rk4`/`_run_segmented_rk45`/the five event-function bodies, is
# touched by any of what follows.
# ----------------------------------------------------------------------


def _project_result_for_mach(result: Result) -> Result:
    """D-32.7: `_warn_if_mach_blind` -> `mach_warning.peak_mach` reads
    `result.y` through `sim.flow.flow_state`, which is 2D-only. Project
    every column of a 3D `Result.y` through `forces3d._s2d` first, so
    `apps/sim/engine/mach_warning.py` itself stays untouched and keeps
    seeing only 2D-shaped data -- peak Mach of a planar 3D flight is then
    identical to the 2D answer by construction, not a separate 3D
    computation."""
    y2d = np.array([forces3d._s2d(result.y[:, i]) for i in range(result.y.shape[1])]).T
    return result._replace(y=y2d)


def _run_rk4_3d(p, y0: np.ndarray, t_max: float, dt: float) -> Result:
    """Fixed-step classical RK4 on the 13-component 3D state (Step 32,
    sub-step 32.3; architecture-37-step32-3d-integration-harness.md
    SS37.7/32.3). MIRROR of `_run_rk4:364-418`'s crossing-detection block
    (D-32.1/C): the five event predicates are reused verbatim via the
    `forces3d._s2d` projection built fresh each half-step below; only
    this ~55-line crossing arithmetic is duplicated, not the predicates
    themselves.

    Quaternion renormalisation (D-32.4): once per accepted step, right
    after the RK4 update produces `y_next` and BEFORE anything below
    reads it through the projection -- a step boundary is the only point
    a projection is consistent with a fixed-step method (unlike the RK45
    path above, which has no accessible accepted-step hook scipy
    exposes: `derivatives_3d` itself keeps NOT renormalising either way,
    task-30 SS30.6 reason 1).

    Does NOT support `sample_rate_hz > 0.0` or any `Hold` -- `run_sim_3d`
    raises eagerly before this function is ever reached with sampling on
    (D-32.2/S2); there is no 3D hold contract to thread through yet.
    """
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

        k1 = dynamics3d.derivatives_3d(t, y, p)
        k2 = dynamics3d.derivatives_3d(t + dt_step / 2, y + dt_step / 2 * k1, p)
        k3 = dynamics3d.derivatives_3d(t + dt_step / 2, y + dt_step / 2 * k2, p)
        k4 = dynamics3d.derivatives_3d(t + dt_step, y + dt_step * k3, p)
        y_next = y + dt_step / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t_next = t + dt_step

        # D-32.4: renormalise the quaternion of the newly accepted step,
        # before the crossing-detection block below (which reads y_next
        # only through the _s2d projection) and before ys.append.
        y_next[state3d.Q] = quaternion.normalise(y_next[state3d.Q])

        y2d = forces3d._s2d(y)
        y2d_next = forces3d._s2d(y_next)

        # Apogee: mirrors _run_rk4:364-369, reading the PROJECTED state.
        if t_apogee is None and t_next >= 0.1 and y2d[VZ] < 0.0 <= y2d_next[VZ]:
            frac = -y2d[VZ] / (y2d_next[VZ] - y2d[VZ])
            t_apogee = t + frac * dt_step

        # Ground impact: mirrors _run_rk4:371-387.
        d_now = gravity.ground_depth(t, y2d, p)
        d_next = gravity.ground_depth(t_next, y2d_next, p)
        if t_next >= 0.1 and d_now < 0.0 <= d_next:
            frac = -d_now / (d_next - d_now)
            t_ground = t + frac * dt_step
            y_ground = y + frac * (y_next - y)
            ts.append(t_ground)
            ys.append(y_ground)
            t, y = t_ground, y_ground
            break

        # Burnout: mirrors _run_rk4:389-398.
        if t_burnout is None:
            thrust_now = thrust_curve.thrust(t, y2d, p)
            thrust_next = thrust_curve.thrust(t_next, y2d_next, p)
            if thrust_now > 0.0 and thrust_next <= 0.0:
                frac = -thrust_now / (thrust_next - thrust_now)
                t_burnout = t + frac * dt_step

        # Rail exit: mirrors _run_rk4:400-408.
        if t_rail_exit is None and p.site.L_rail > 0.0 and t_next >= 0.1:
            r_now = dynamics.rail_distance(y2d, p) - p.site.L_rail
            r_next = dynamics.rail_distance(y2d_next, p) - p.site.L_rail
            if r_now < 0.0 <= r_next:
                frac = -r_now / (r_next - r_now)
                t_rail_exit = t + frac * dt_step

        # Parachute deploy: mirrors _run_rk4:410-418.
        if t_parachute_deploy is None:
            dep_now = 1.0 if forces.parachute_deployed(t, y2d, p) else -1.0
            dep_next = 1.0 if forces.parachute_deployed(t_next, y2d_next, p) else -1.0
            if dep_now < 0.0 <= dep_next:
                frac = -dep_now / (dep_next - dep_now)
                t_parachute_deploy = t + frac * dt_step

        ts.append(t_next)
        ys.append(y_next)
        t, y = t_next, y_next

    t_arr = np.array(ts)
    y_arr = np.array(ys).T  # shape (13, N), matches state3d's flat layout

    return Result(
        t=t_arr,
        y=y_arr,
        events={
            "apogee": t_apogee, "ground": t_ground, "burnout": t_burnout,
            "rail_exit": t_rail_exit, "parachute_deploy": t_parachute_deploy,
        },
        raw=_RK4Raw(sol=_LinearInterpolant(t_arr, y_arr)),
        params=p,
    )


def run_sim_3d(p, s0_3d: np.ndarray) -> Result:
    """3D analogue of `run_sim` (Step 32, Phase 3;
    architecture-37-step32-3d-integration-harness.md SS37.2/D-32.1 option
    C, SS37.3/D-32.2 option S2). Integrates the 13-component 3D state
    (`apps.sim.engine.state3d`) from `s0_3d` until ground impact or
    `p.solver.t_max`, exactly like `run_sim` does for the 2D `State` --
    the same five events (ground/apogee/burnout/rail_exit/
    parachute_deploy), reused VERBATIM via `_events_for(forces3d._s2d)`
    (D-32.1/C): nothing inside the five event-predicate bodies, or inside
    `run_sim`/`_run_rk4`/`_run_segmented_rk45`, is touched by this
    function.

    `s0_3d` is a flat 13-component array
    (`apps.sim.engine.state3d.to_vector(State3D(...))`), not a `State3D`
    NamedTuple -- mirrors `run_sim`'s own internal `to_vector(s0, p)`
    call, just with the flattening left to the caller (the 3D layout has
    no `p`-dependent width/trim the way the 2D roll block does, so there
    is nothing for this function itself to do with `p` at that step).

    Supports `p.solver.method in {"rk4", "RK45"}` only (D-32.2/S2); the
    sampled-data/zero-order-hold paths (`method == "rk45_seg"`, or
    `sample_rate_hz > 0.0` with any method) are out of scope and rejected
    EAGERLY below, before any integration starts -- `forces3d` hardcodes
    `hold = None` in two places (SS37.0.2 point 6), so there is no 3D hold
    contract to integrate against yet.

    IMPORTANT (D-32.1/C's own boundary, SS37.8): `forces3d._s2d` is valid
    for a PLANAR 3D attitude only (zero roll, zero yaw about the pitch
    axis -- that module's own docstring). A non-planar 3D run is RUNNABLE
    through this function (nothing here checks for it), but the
    aerodynamic forces it computes are not yet physically meaningful for
    one; replacing `_s2d` with a true 3D relative-wind model is Step 31's
    job. Every test this step adds is a planar one -- treat a non-planar
    result as exploratory, not validated.
    """
    method = p.solver.method
    t_max = p.solver.t_max
    rtol = p.solver.rtol
    atol = p.solver.atol
    dt = p.solver.dt
    sample_rate_hz = p.solver.sample_rate_hz

    # D-32.6 guard 5: reused verbatim from run_sim (SS35.6).
    if p.actuator.model not in control.known_actuator_models():
        raise ValueError(
            f"p.actuator.model={p.actuator.model!r} is not a registered "
            f"actuator model (known: {sorted(control.known_actuator_models())}) "
            "(architecture-35-paper-alignment.md SS35.6)."
        )

    # D-32.2/S2: only the un-sampled rk4/RK45 paths are supported. Unlike
    # run_sim's own paired (sample_rate_hz, method) guards -- which allow
    # the two together for 2D -- run_sim_3d has no hold contract at all
    # (see docstring), so EITHER condition alone is already out of scope;
    # the two checks below are therefore independent, not paired.
    if sample_rate_hz > 0.0:
        raise ValueError(
            f"p.solver.sample_rate_hz={sample_rate_hz} is not supported by "
            "run_sim_3d: the sampled-data/zero-order-hold path has no 3D "
            "hold contract yet (forces3d.py hardcodes hold=None throughout "
            "-- architecture-37-step32-3d-integration-harness.md SS37.3/"
            "D-32.2). Use run_sim (2D) for sampled-data runs, or leave "
            "sample_rate_hz=0.0 for a 3D run."
        )
    if method == "rk45_seg":
        raise ValueError(
            "p.solver.method='rk45_seg' is not supported by run_sim_3d "
            "(architecture-37-step32-3d-integration-harness.md SS37.3/"
            "D-32.2): run_sim_3d supports only 'rk4' and 'RK45'."
        )

    # D-32.6 guard 2: the 2D decoupled roll degree of freedom (Step 109)
    # and the 3D state's own omega[0] are the SAME physical quantity
    # (the research note's own SS5.1 proof that the roll equation is
    # identical in both) -- running the 2D roll model alongside a 3D
    # integration would double-count roll.
    if p.roll.model != "none":
        raise ValueError(
            f"p.roll.model={p.roll.model!r} is not supported by "
            "run_sim_3d: the 2D decoupled roll degree of freedom "
            "(task-109-roll-reaction-wheel.md) and the 3D state's own "
            "omega[0] are the SAME physical degree of freedom, so running "
            "both at once would double-count roll. The 3D home for roll "
            "inertia is p.inertia.I_xx, not p.roll."
        )

    # D-32.6 guard 3: the 13-component layout has no mass slot --
    # forces3d._s2d always passes M=0.0 through, and weight_inertial only
    # ever reads s[M] when p.weight.m_d is set, so a set m_d would
    # silently make weight_inertial read that 0.0 as the vehicle's mass.
    if p.weight.m_d is not None:
        raise ValueError(
            f"p.weight.m_d={p.weight.m_d} is not supported by run_sim_3d: "
            "there is no 3D variable-mass model yet -- the 13-component "
            "state has no mass slot, and forces3d._s2d always passes "
            "M=0.0 through to weight_inertial, which would silently read "
            "that as the vehicle's true mass. Leave p.weight.m_d=None for "
            "a 3D run."
        )

    # D-32.6 guard 1: closes task-30 SS30.15's "call inertia.validate from
    # a 3D run entry point" -- apps/sim/schema.py's assemble() call does
    # not reach a hand-built Params (i.e. every test). `p.roll.model` is
    # always "none" by the time this runs (guard 2 above already raised
    # otherwise), so the roll cross-check inside inertia.validate is inert
    # here; passed through anyway for the same call shape
    # apps/sim/schema.py:407 uses.
    inertia.validate(p.inertia, roll=p.roll)

    y0 = np.asarray(s0_3d, dtype=float)

    if method == "rk4":
        result = _run_rk4_3d(p, y0, t_max, dt)
        _warn_if_mach_blind(_project_result_for_mach(result))
        return result

    ground3d, apogee3d, burnout3d, rail3d, chute3d = _events_for(forces3d._s2d)
    sol = solve_ivp(
        dynamics3d.derivatives_3d,
        (0.0, t_max),
        y0,
        method=method,
        args=(p,),
        events=[ground3d, apogee3d, burnout3d, rail3d, chute3d],
        dense_output=True,
        rtol=rtol,
        atol=atol,
    )

    t_ground = sol.t_events[0][0] if len(sol.t_events[0]) else None
    t_apogee = sol.t_events[1][0] if len(sol.t_events[1]) else None
    t_burnout = sol.t_events[2][0] if len(sol.t_events[2]) else None
    t_rail_exit = sol.t_events[3][0] if len(sol.t_events[3]) else None
    t_parachute_deploy = sol.t_events[4][0] if len(sol.t_events[4]) else None

    result = Result(
        t=sol.t,
        y=sol.y,
        events={
            "apogee": t_apogee, "ground": t_ground, "burnout": t_burnout,
            "rail_exit": t_rail_exit, "parachute_deploy": t_parachute_deploy,
        },
        raw=sol,
        params=p,
    )
    _warn_if_mach_blind(_project_result_for_mach(result))
    return result

    warn_if_mach_blind(result, stacklevel=4)

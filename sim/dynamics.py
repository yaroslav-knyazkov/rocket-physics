"""Equations of motion -- the ONLY place the EOM appear (architecture.md SS3).

Step 5 scope note (translation): `theta` no longer has to be pi/2 -- the
body-to-inertial rotation lives in `frames.py` (architecture.md SS2, "The
single rotation function") instead of being written out inline here (that
was Step 4's explicitly-deferred shortcut).

Frame convention: single NED-like inertial frame, z DOWN (architecture.md
SS2). Forces are summed per architecture.md SS2 "How mixed-frame forces are
summed":

    F_i = weight_inertial + R_body_to_inertial(theta) @ (thrust_body + aero_force_body)
    a_i = F_i / m

At theta = pi/2 (vertical, nose-up): R = [[0, 1], [-1, 0]]. Body thrust
`(T, 0)` rotates to inertial `(0, -T)` -- straight up, decreasing z, i.e.
`dvz/dt` gets a `-T/m` term. Body aero force `(-A_x, -A_z)` rotates to
inertial `(-A_z, A_x)` -- with `A_z = 0` (still purely vertical flight,
architecture.md SS4 / roadmap.md Step 4 note) that's `(0, A_x)`: a positive
addition to `dvz/dt`, i.e. axial drag opposes the climb, exactly as
expected. `A_z`'s contribution would land on the x-channel (downrange) --
it has no effect for a vertical launch, but for any other fixed `theta` it
now correctly produces downrange motion (roadmap.md Step 5).

Step 6 scope (rotation): `theta` and `omega` become real integrated states.
`dtheta/dt = omega`. `domega/dt = M_y / I`, with the pitching moment about
the CoG per main.tex SSEquations of motion:

    I*theta_ddot = [aB x T + aA x A_f + A_m] . y_hat

architecture.md SS2 ("Moments need no rotation at all") shows every term
here is already in the body frame -- no `to_inertial`/`to_body` call is
needed for moments, only for the translational forces above.

`aB x T` and `aA x A_f` are 2D cross products of body-frame vectors lying
in the (x_hat_r, z_hat_r) plane. With `x_hat_r x z_hat_r = -y_hat_r`
(architecture.md SS2), the y-component of `a x b` for `a = (a_x, a_z)`,
`b = (b_x, b_z)` is `-(a_x*b_z - a_z*b_x)`. Both cross products are written
out explicitly (rather than only the pre-simplified scalar
`-l1*A_z - A_m`, per the corrected geometry below) so that a future gimbal
or thrust-misalignment model drops in without touching this function's
structure.

Step 36 (roadmap.md; main.tex SSModels > Mass and moment of inertia): `m`
becomes the 7th state component (`state.M`), integrated via
`dm/dt = -T_ref(t)/(I_sp*g0)`, and `p.I` is replaced by the instantaneous
`I(t)` (two-lumped-mass model, dry structure + remaining propellant,
parallel-axis theorem) -- gated by `p.m_d` (params.py: `None` = off,
reproduces every prior step bit-for-bit, `p.m`/`p.I` used exactly as
before). `p.l1`/`p.l2` (the CoP-to-CoG and CoP-to-thrust moment arms,
`aA`/`aB` below) are deliberately left untouched by this step -- main.tex's
Mass and moment of inertia section gives a formula for `l_B(t)` and `I(t)`
only, not for how the aerodynamic/thrust attachment points travel relative
to a moving CoG (that is exactly the still-open question architecture.md
SS19 flags: "still blocked on a main.tex update ... contradicts I(t),
l1(t), l2(t)"; main.tex's own SSCurrent assumptions still lists `l_1`,
`l_2` as held fixed). Since `I(t)`'s parallel-axis terms already depend on
`l_B(t)` on their own, this is enough to make a real `l_p != l_d` offset
change the rotational dynamics (the "Check" this step's roadmap entry
asks for) without inventing an unstated `l1(t)`/`l2(t)` formula.

Step 37 (roadmap.md; main.tex SSModels > Non-inertial frame corrections):
`a_i` gains `sim.rotation`'s in-plane Coriolis acceleration when
`p.earth_rotation` is `True` (default `False`, bit-for-bit pre-Step-37
otherwise). This is a purely translational correction -- zero moment
about the CoG (sim/rotation.py's module docstring, "Moment") -- so it
touches only `dvx/dt`/`dvz/dt` below, never `M_y`/`domega/dt`, and does
not interact with `l1`/`l2`/`aA`/`aB` at all.

Step 39 (roadmap.md; main.tex SSForces eq:thrust_vector, SSAnalysis
eq:moment_misaligned; architecture.md SS23.2): needs **no functional
change here at all**. `sim/forces.py`'s `thrust_body` now returns a
general body-frame vector `T*(cos(delta), sin(delta))` instead of the
on-axis `(T, 0)`, and `M_thrust = _cross_y(aB, thrust)` below was already
written out as a general 2D cross product for exactly this reason (see
Step 6's note above) -- it evaluates to `(l1 + l2)*T*sin(delta)` with no
edit. Only the stale inline comment next to that line ("intentionally
zero today") needed rewording.

Step 47 (roadmap.md; architecture.md SS27.1): a launch rail constraint.
While `on_rail(y, p)` is true (params.py's `L_rail`, `rail_angle_deg`),
the already-computed `a_i` -- unchanged above this point, Coriolis
included -- is projected onto the fixed rail direction `_e_rail(p)`
instead of being used directly, and `dtheta/dt`/`domega/dt` are frozen at
0 instead of the usual `y[OMEGA]`/`M_y / I`. This is a kinematic
constraint on the same force sum every other step already computes, not
a new force -- `M_y`/`I` are still evaluated every call (cheap, and keeps
the function's structure), only the final assignment branches. `L_rail =
0.0` (the default) is the off switch: `rail_distance` is 0 at t=0, so
`on_rail` is false from the first call, bit-for-bit pre-Step-47.

Step 48 (roadmap.md; architecture.md SS27.2): a second branch in the same
final-assembly block, between `on_rail` and the free-flight `else` -- while
`forces.parachute_deployed(t, y, p)` is true, `theta`/`omega` are frozen at
0 exactly like the rail branch (the same "a mechanical constraint freezes
the attitude state" mechanism, re-used rather than invented), and the
translational acceleration is recomputed as `(F_i + F_chute) / m` rather
than reusing the already-computed `a_i` -- `a_i` may already include the
Step 37 Coriolis term, so adding `F_chute/m` to it a second time via
`a_i + F_chute/m` would be arithmetically identical but written in a way
that invites a future edit to silently drop the Coriolis contribution by
reusing a stale `a_i`; recomputing from `F_i + F_chute` keeps it included
exactly once, explicitly. Rail takes priority over parachute in the branch
order (defensive only -- `on_rail` is false long before `parachute_deployed`
can be true on any realistic flight). `p.parachute_model == "none"` (the
default) or `p.parachute_S == 0.0` (also the default) are independent off
switches: `forces.parachute_deployed` returns `False`/the chute force is
zero, so this branch is bit-for-bit unreachable or inert, reproducing every
prior step.
"""

import numpy as np

from sim import aero, forces, thrust_curve
from sim.flow import flow_state
from sim.forces import aero_force_body, aero_moment_y, thrust_body, weight_inertial
from sim.frames import to_inertial
from sim.rotation import coriolis_inplane
from sim.state import M, OMEGA, THETA, VX, VZ, X, Z


def _cross_y(a: np.ndarray, b: np.ndarray) -> float:
    """y-component of the 2D cross product `a x b` in the (x_hat_r, z_hat_r)
    plane, i.e. the scalar `c` such that `a x b = c*y_hat_r` (architecture.md
    SS2: `x_hat_r x z_hat_r = -y_hat_r`).
    """
    a_x, a_z = a
    b_x, b_z = b
    return -(a_x * b_z - a_z * b_x)


def _propellant_mass(m: float, p) -> float:
    """m_p(t) = m(t) - m_d (main.tex SSModels > Mass and moment of inertia),
    clamped at 0. The adaptive solver overshoots the true burnout
    zero-crossing by a floating-point sliver on either side (the same
    reason `integrate.py`'s `_burnout_event` needs its own epsilon shift)
    -- a stray negative `m_p` right after burnout would flip the sign of
    every term below instead of just settling at the dry-mass endpoint.
    """
    return max(m - p.weight.m_d, 0.0)


def _cog_position(m_p: float, p) -> float:
    """l_B(t): mass-weighted centroid of the two-lumped-mass model -- dry
    structure (mass m_d, fixed centroid l_d) and remaining propellant
    (mass m_p, centroid l_p) -- main.tex SSModels > Mass and moment of
    inertia.
    """
    return (p.weight.m_d * p.weight.l_d + m_p * p.weight.l_p) / (p.weight.m_d + m_p)


def _moment_of_inertia(m_p: float, l_B: float, p) -> float:
    """I(t): parallel-axis theorem, dry structure + remaining propellant,
    each shifted from its own centroid to the instantaneous CoG l_B(t)
    (main.tex SSModels > Mass and moment of inertia):

        I(t) = I_d + m_d*(l_B-l_d)^2 + I_p(t) + m_p*(l_B-l_p)^2

    `I_p(t)`, the remaining propellant's own moment of inertia about its
    own centroid, is main.tex's own placeholder `\\todo` ("uniform
    density, fixed shape" until the grain geometry is known) -- taken
    proportional to `m_p(t)` via the dry structure's own specific moment
    of inertia `I_d/m_d` (i.e. propellant assumed to have the same
    mass-normalised MOI/radius of gyration as the dry structure): the
    simplest closed form that needs no geometry constant beyond the four
    this step introduces (`m_d, l_d, l_p, I_d`). Revisit once real grain
    geometry is available (main.tex's own note).
    """
    I_p = (p.weight.I_d / p.weight.m_d) * m_p
    return p.weight.I_d + p.weight.m_d * (l_B - p.weight.l_d) ** 2 + I_p + m_p * (l_B - p.weight.l_p) ** 2


def _e_rail(p) -> np.ndarray:
    """Fixed unit vector along the launch rail, inertial frame (architecture.md
    SS27.1): the rail points the way the nose initially points.
    """
    return to_inertial(np.array([1.0, 0.0]), np.radians(p.site.rail_angle_deg))


def rail_distance(y: np.ndarray, p) -> float:
    """Signed distance travelled along the rail from the launch point
    (assumed to be the origin -- every scenario in this repo already
    launches from x=0, z=0). No leading underscore: `integrate.py`'s
    rail-exit event reads this directly (architecture.md SS27.1).
    """
    return float(np.dot(np.array([y[X], y[Z]]), _e_rail(p)))


def on_rail(y: np.ndarray, p) -> bool:
    """`p.L_rail <= 0.0` is the off switch (params.py): `rail_distance` is
    0 at t=0, so `0 < 0.0` is false and the rocket is never on the rail,
    reproducing every prior step bit-for-bit."""
    return p.site.L_rail > 0.0 and rail_distance(y, p) < p.site.L_rail


def derivatives(t: float, y: np.ndarray, p) -> np.ndarray:
    """dy/dt for the state vector [x, z, vx, vz, theta, omega, m].

    Translation: `dx/dt = vx`, `dz/dt = vz`,
    `[dvx/dt, dvz/dt] = (weight_inertial + to_inertial(thrust_body + aero_force_body, theta)) / m`.

    Rotation (Step 6): `dtheta/dt = omega`,
    `domega/dt = M_y / I` where
    `M_y = cross_y(aB, thrust_body) + cross_y(aA, aero_force_body) + aero_moment_y`.

    Mass (Step 36): `dm/dt = -T_ref(t)/(I_sp*g0)` while the variable-mass
    model is on (`p.m_d` set); `I` above is then the instantaneous `I(t)`
    from the two-lumped-mass model instead of the fixed `p.I` (see module
    docstring). Both are exactly `dm/dt = 0`, `I = p.I` when `p.m_d` is
    `None` (the default) -- bit-for-bit the pre-Step-36 behaviour.
    """
    theta = y[THETA]

    # Step 9 tidy (architecture.md SS15 "Performance note"): each of these
    # is now backed by flow_state (and, from Step 12 on, the atmosphere
    # model), so computing them once and reusing them for both the force
    # sum and the moment halves the model evaluations per RHS call.
    # Behaviour-preserving -- identical numbers to calling them twice.
    #
    # Step 56 (architecture-28-rewrite.md SS28.11, closing F8): `flow_state`
    # itself is now computed exactly once here and threaded down into
    # `aero_force_body`/`aero_moment_y` (and the `l1_aero` lookup below,
    # which already reused this same `flow` before this step) instead of
    # each of the three call sites independently recomputing an identical
    # `Flow` bundle -- 3 atmosphere/wind evaluations per RHS call collapse
    # to 1. `flow_state` is a pure, deterministic function of `(t, y, p)`
    # alone (sim/flow.py's docstring; the Dryden turbulence realization it
    # may call through is itself frozen per seed via `lru_cache`, so
    # repeated calls with identical arguments are bit-identical), so this
    # is a pure call-count reduction, not a behaviour change.
    flow = flow_state(t, y, p)
    thrust = thrust_body(t, y, p)
    aero_force = aero_force_body(t, y, p, flow)

    body_forces = thrust + aero_force
    F_i = weight_inertial(t, y, p) + to_inertial(body_forces, theta)

    # Step 36: mass model gate (params.py's `m_d`). Off (`None`, the
    # default) -> `m`, `I` are the fixed Phase 1 constants, `dm/dt = 0`,
    # bit-for-bit pre-Step-36. On -> `m` is the integrated state
    # `y[M]`, `I` is the instantaneous `I(t)` from the two-lumped-mass
    # model (main.tex SSModels > Mass and moment of inertia), and
    # `dm/dt = -T_ref(t)/(I_sp*g0)`. `thrust_curve.thrust` (not the raw
    # curve lookup) stands in for `T_ref(t)` here -- identical to it
    # whenever `p.A_e == 0.0` (the default, and every scenario below),
    # and only differs by the Step-16 nozzle-exit pressure term
    # otherwise, which is a thrust correction, not a mass-flow one.
    if p.weight.m_d is None:
        m = p.weight.m
        I = p.weight.I
        dm_dt = 0.0
    else:
        m = y[M]
        m_p = _propellant_mass(m, p)
        l_B = _cog_position(m_p, p)
        I = _moment_of_inertia(m_p, l_B, p)
        dm_dt = -thrust_curve.thrust(t, y, p) / (p.weight.I_sp * p.g0)

    a_i = F_i / m

    # Step 37: non-inertial (Coriolis) frame correction (main.tex SSModels >
    # Non-inertial frame corrections; sim/rotation.py). Off by default
    # (`p.earth_rotation = False`) -- `a_i` unchanged, bit-for-bit
    # pre-Step-37. On -> add the in-plane Coriolis acceleration only (the
    # residual centrifugal term and the out-of-plane Coriolis component
    # are deliberately not implemented; see sim/rotation.py's module
    # docstring). Purely translational -- no effect on M_y/domega/dt below.
    if p.gravity.earth_rotation:
        a_i = a_i + coriolis_inplane(t, y, p)

    # Geometry (main.tex SSGeometry, corrected 2026-09-20): both points lie
    # along the body x-axis, relative to the CoG. `l1`, `l2` are positive,
    # nose-tip-referenced distances; `x_hat_r` points toward the nose. A
    # statically stable rocket has its CoP (A) farther from the nose tip
    # than its CoG (a) -- i.e. aft of the CoG along `x_hat_r` -- so `aA`
    # (the CoG-to-CoP vector) points in the *negative* `x_hat_r` direction:
    # `aA = -l1*x_hat_r`. (The previous `aA = +l1*x_hat_r` put the CoP
    # forward of the CoG for any positive `l1`, which is aerodynamically
    # divergent rather than restoring for a linear normal force
    # `A_z ~ alpha` -- see main.tex SSGeometry's correction note.)
    # `aB = aA + AB` with the unchanged `AB = -l2*x_hat_r` (thrust point at
    # the tail): `aB = -(l1 + l2)*x_hat_r`.
    #
    # Step 25 (architecture.md SS19, "CoP travel"): `aA`'s `l1` is no
    # longer necessarily the constant `p.l1` -- it comes from the table
    # when `p.aero.model == "table"`, falling back to the constant
    # `p.lengths.l1` under "constant"/"linearized" otherwise (bit-for-bit
    # the line this replaces).
    #
    # Step 55 (architecture-28-rewrite.md SS28.5, closing F2's leak): `l1`
    # now comes out of the same `aero.coefficients(...)` bundle every
    # other aero consumer reads, instead of a separate `aero.cop_l1(...)`
    # call -- the table can no longer drive the moment arm while a
    # different model drives the force/moment, which was possible before
    # this step (the two selectors, `aero_model` and `aero_table`, could
    # disagree).
    #
    # Step 56 (architecture-28-rewrite.md SS28.11, closing F8): `flow` is
    # the single `flow_state(t, y, p)` computed once above and reused here
    # (and by `aero_force_body`/`aero_moment_y` below) -- this call site no
    # longer recomputes it a second time.
    #
    # `aB` deliberately keeps the constant `p.l1` (not the dynamic CoP
    # location): B is the thrust exit point, a fixed mechanical point on
    # the body that does not move just because the CoP does. Only `aA`
    # (the CoP's own position) is meant to travel -- architecture.md SS19
    # says "l1 [the aero moment arm] becomes a function of (alpha, M)",
    # nothing about the thrust attachment point. Coupling `aB` to the
    # moving CoP too would invent an unspecified thrust-misalignment
    # effect (that is explicitly a *future* gimbal-model concern, per the
    # "on-axis thrust ... intentionally zero today" comment below) rather
    # than model the CoP travel this step actually asks for.
    # Step 43 (roadmap.md; architecture.md SS24.3; rocket-2d.tex SSGeometry):
    # lateral (off-axis) offsets `u_B` (CoG), `u_C` (thrust point) along
    # +z_hat_r. `u_D == 0` by definition, so `aA`'s lateral component is
    # `u_B` alone (from `BD = AD - AB`, `AB = -l_B*x_hat_r - u_B*z_hat_r`);
    # `aB`'s is `u_B - u_C` (from `BC = AC - AB`). Both default to 0.0, so
    # both arrays are bitwise identical to the pre-Step-43 literals below.
    l1_aero = aero.coefficients(t, y, p, flow).l1
    aA = np.array([-l1_aero, p.lengths.u_B])                     # CoP position
    aB = np.array([-(p.lengths.l1 + p.lengths.l2), p.lengths.u_B - p.lengths.u_C])  # thrust application point

    # aB x T: on-axis thrust (T, 0) applied at an on-axis point (aB parallel
    # to T) produces zero pitching moment -- that was the only case here
    # before Step 39. It is written out (not simplified away) so a thrust
    # misalignment (T with a nonzero z-component, `sim/forces.py`'s
    # `thrust_body` when `p.thrust_misalign_deg != 0`) produces a nonzero
    # moment with no change to this function's structure: `_cross_y(aB,
    # thrust) = (p.l1 + p.l2) * T * sin(delta)` exactly (main.tex SSAnalysis
    # eq:moment_misaligned's M_delta, architecture.md SS23.2), since
    # `aB = -(p.l1+p.l2)*x_hat_r` and `_cross_y(a, b) = -(a_x*b_z - a_z*b_x)`.
    # Still zero whenever T = 0 (T=0 scales both cos(delta) and sin(delta)
    # away) or delta = 0 (the default -- bit-for-bit unchanged). A future
    # gimbal model (aB off-axis, or a commanded delta(t)) drops in the same
    # way.
    M_thrust = _cross_y(aB, thrust)
    M_aero = _cross_y(aA, aero_force)
    M_moment = aero_moment_y(t, y, p, flow)
    M_y = M_thrust + M_aero + M_moment

    dydt = np.zeros(7)
    dydt[X] = y[VX]
    dydt[Z] = y[VZ]

    # Step 47 (architecture.md SS27.1): while on the launch rail, the rail
    # buttons mechanically react every transverse force component and
    # prevent rotation -- the already-computed `a_i` (gravity/thrust/aero,
    # Coriolis included) is projected onto the fixed rail direction, and
    # `theta`/`omega` are frozen. `on_rail` is false whenever `p.L_rail <=
    # 0.0` (the default), so the `else` branch is bit-for-bit every prior
    # step.
    if on_rail(y, p):
        e = _e_rail(p)
        a_parallel = np.dot(a_i, e) * e
        dydt[VX], dydt[VZ] = a_parallel
        dydt[THETA] = 0.0
        dydt[OMEGA] = 0.0
    elif forces.parachute_deployed(t, y, p):
        # Step 48 (architecture.md SS27.2): the canopy holds the body in a
        # fixed hang attitude (frozen theta/omega, same mechanism as the
        # rail above), and the chute drag is a natively-inertial force
        # (forces.parachute_drag_inertial) added directly to F_i -- NOT
        # routed through the already-computed a_i, so the Coriolis term
        # folded into a_i (Step 37) is included exactly once, not dropped.
        F_chute = forces.parachute_drag_inertial(t, y, p)
        a_chute = (F_i + F_chute) / m
        dydt[VX], dydt[VZ] = a_chute
        dydt[THETA] = 0.0
        dydt[OMEGA] = 0.0
    else:
        dydt[VX] = a_i[0]
        dydt[VZ] = a_i[1]
        dydt[THETA] = y[OMEGA]
        dydt[OMEGA] = M_y / I

    dydt[M] = dm_dt
    return dydt

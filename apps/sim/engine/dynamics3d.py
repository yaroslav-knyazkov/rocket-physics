"""apps/sim/engine/dynamics3d.py -- 3D equations of motion -- translation (roadmap.md Step 29) and rotation
(Step 30, task-30-3d-rotational-dynamics.md). The 3D analogue of
sim/dynamics.py's `derivatives`, one dimension up, for the 13-component
state `[r(3), v(3), q(4), omega(3)]` (sim/state3d.py).

Frame convention: same single NED-like inertial frame as the 2D code, z
DOWN (sim/state3d.py's own docstring), with y completing a right-handed
triad.

`m*v_dot = W + R(q)@(T_body + A_body)` (main.tex SSEquations of motion,
generalised to 3D with the quaternion DCM `sim.quaternion.to_dcm(q)` in
place of the 2D `frames.R_body_to_inertial(theta)`):

    dr/dt     = v
    dv/dt     = (weight_inertial_3d + to_dcm(q) @ (thrust_body_3d + aero_force_body_3d)) / m
    dq/dt     = q_dot(q, omega)                           (eq:quat_kinematics_components)
    domega/dt = 0.0                                       if p.inertia.model == "none"
              = I^-1 (M - omega x (I @ omega))             otherwise (eq:eom_rot_3d_expanded)

`m` is the fixed `p.weight.m`: there is no 3D variable-mass model yet (the
13-component layout has no mass field; forces3d.py's 2D-state adapter
always passes mass `0.0` through, which is inert since `weight_inertial`
only reads it when `p.weight.m_d` is set -- off for every scenario this
module can run today).

Step 30 (SS30.5.2): `dq/dt` is NEVER gated on `p.inertia.model` -- `q_dot`
is pure kinematics (reads `q`/`omega`, no inertia at all), so gating it on
an *inertia* parameter would be a non-sequitur, and worse, a wrong model:
with `model == "none"` and `omega != 0` it would hold the attitude fixed
while the body is stated to be rotating. So `p.inertia.model == "none"`
(the default) means PRESCRIBED-RATE kinematics: `omega` is exactly
constant (no rotational dynamics computed), and `q` integrates under it --
well defined, and how a commanded tumble or a frozen-dynamics sanity run
is expressed. `p.inertia.model == "tensor"` is full rotational dynamics
(Euler's equations, general form, `sim.inertia.omega_dot`).

Retired at Step 30: Step 29's "`dq/dt = 0` identically" / "attitude held
fixed" no longer holds for the whole module -- `dq/dt` is always live
(the two bullets above); only `domega/dt` has an off switch, and it is a
*physical* one (no moments computed, prescribed-rate kinematics), not the
old "nothing rotates" statement. See sim/state3d.py's module docstring for
the matching correction.

Step 29's own "Check" (roadmap.md), still exercised (now via
`p.inertia.model == "none"`, the default, rather than by `dq/dt`/
`domega/dt` being hardwired to zero): planar initial conditions (`r[1] = 0`,
`v[1] = 0`, `q` pitch-only, `omega = 0`) must reproduce the Phase 1 2D
trajectory to solver tolerance, with `r[1]`/`v[1]` staying exactly `0.0`
throughout. Step 30's own stronger check (task-30 SS30.10.3): the same
holds for a genuinely rotating, non-zero-moment flight once
`p.inertia.model == "tensor"` with a diagonal tensor -- see
tests/test_dynamics3d.py.

Step 32, sub-step 32.4 (architecture-37-step32-3d-integration-harness.md
D-32.5): the rail and parachute attitude freeze -- the 3D twin of
`sim.dynamics.derivatives`'s own `on_rail`/`chuted` branch
(`dynamics.py:394-432`). The freeze is a property of the equations of
motion (a mechanical constraint: rail buttons / canopy risers prevent
rotation), so it lives HERE, not in the integrator -- exactly as it does
in 2D, and splitting one physical constraint across two modules would be
wrong. The two predicates are reused VERBATIM on this module's own
`forces3d._s2d` projection: `dynamics.on_rail(_s2d(y), p)`,
`forces.parachute_deployed(t, _s2d(y), p)`. While on the rail OR under
canopy: `dydt[Q] = 0.0` AND `dydt[OMEGA] = 0.0` (both halves of the
attitude state frozen -- the 3D twin of 2D's `dydt[THETA] = 0` plus
`dydt[OMEGA] = 0`, since in 3D the attitude derivative is `q_dot`, not a
scalar). Translation is NOT frozen in either case: on the rail,
acceleration is projected onto the exact 3D rail embedding `e_rail_3d =
(cos eps, 0, -sin eps)` (`_e_rail_3d` below, built from
`dynamics._e_rail(p)` by inserting a zero y-component -- exact, since
`Site` carries no rail azimuth relative to `+x`, the same argument this
module's force wrappers make for gravity/thrust); under the canopy,
`forces.parachute_drag_inertial` is evaluated on the same 2D projection
and embedded `(Fx, 0, Fz)` -- exact, since a round canopy's drag does
not depend on body attitude (axisymmetric).

`p.site.L_rail <= 0.0` (default) and `p.recovery.model == "none"`
(default) make both predicates false from the first call, so this branch
is unreachable for every existing 3D test -- `tests/test_dynamics3d.py`'s
8 tests must not move, and the Step 32 sub-step 32.3 `rk4` pin (both
defaults) must not move either; if either moves, the freeze branch is
leaking into the unconstrained path.
"""

import numpy as np

from apps.sim.engine import dynamics, forces, inertia, quaternion
from apps.sim.engine import forces3d
from apps.sim.engine.forces3d import (
    aero_force_body_3d,
    flow_fb_coeffs_3d,
    moment_body_3d,
    thrust_body_3d,
    weight_inertial_3d,
)
from apps.sim.engine.state3d import N, OMEGA, Q, R, V


def _e_rail_3d(p) -> np.ndarray:
    """`(cos eps, 0, -sin eps)` -- the exact 3D embedding of
    `dynamics._e_rail(p)` (module docstring, D-32.5): insert a zero
    y-component into the 2D rail unit vector `(cos eps, -sin eps)`. No
    new parameter, no new physics -- `Site` has no rail-azimuth field, so
    an out-of-plane rail is not expressible."""
    e2d = dynamics._e_rail(p)
    return np.array([e2d[0], 0.0, e2d[1]])


def derivatives_3d(t: float, y: np.ndarray, p) -> np.ndarray:
    """dy/dt for the 13-component 3D state (module docstring;
    eq:state_vector_3d)."""
    v = y[V]
    q = y[Q]
    omega = y[OMEGA]

    W_i = weight_inertial_3d(t, y, p)
    T_b = thrust_body_3d(t, y, p)

    dydt = np.empty(N)
    dydt[R] = v

    # Step 30 (task-30-3d-rotational-dynamics.md SS30.5.1): the rotational
    # block. `model == "none"` (the default) is prescribed-rate kinematics
    # -- see module docstring; `model == "tensor"` is Euler's rotational
    # equation, general form (eq:eom_rot_3d_expanded). Two branches -> an
    # `if`, not a dict-dispatch registry (Roll/Aero's `_ROLL_LAWS`-style
    # dispatch is reserved for 3+ real models, SS30.5.1).
    #
    # code-review finding (2026-10-25): `aero_force_body_3d` (needed for
    # translation, every call) and `moment_body_3d` (needed for rotation,
    # only here) used to each independently recompute `flow`/`fb`/`coeffs`
    # from the same `_s2d(y)` view -- a redundant atmosphere/aero
    # evaluation on every RHS call with the rotational model on. The
    # `model == "tensor"` branch now computes that bundle ONCE
    # (`flow_fb_coeffs_3d`) and threads it into both calls; bit-for-bit
    # identical (same pure functions, same inputs), just not paid for
    # twice. The `model == "none"` branch is unaffected -- `moment_body_3d`
    # is never called there, so there is nothing to share.
    #
    # `domega_dt` is computed unconditionally here (not assigned straight
    # into `dydt[OMEGA]`) because Step 32's rail/parachute freeze below
    # may discard it -- the same shape the 2D `derivatives` has always
    # had: `M_y`/`pitch_moment` is computed every call, and only the
    # unconstrained branch actually uses it.
    if p.inertia.model == "none":
        A_b = aero_force_body_3d(t, y, p)
        domega_dt = np.zeros(3)
    else:
        flow, fb, coeffs = flow_fb_coeffs_3d(t, y, p)
        A_b = aero_force_body_3d(t, y, p, flow, fb, coeffs)
        I_b = inertia.tensor(p.inertia)
        M_b = moment_body_3d(t, y, p, flow, fb, coeffs)
        domega_dt = inertia.omega_dot(I_b, omega, M_b)

    F_i = W_i + quaternion.to_dcm(q) @ (T_b + A_b)

    # Step 32 (D-32.5, module docstring): the rail/parachute attitude
    # freeze. One shared `_s2d` projection (`flow_fb_coeffs_3d`'s own
    # sharing precedent); `on_the_rail` short-circuits `chuted`, the same
    # order `dynamics.derivatives`'s own `elif` uses. Both predicates are
    # false from the first call whenever `p.site.L_rail <= 0.0` (default)
    # and `p.recovery.model == "none"` (default), so everything below is
    # bit-for-bit the pre-32.4 behaviour for every existing 3D test/pin.
    s2d = forces3d._s2d(y)
    on_the_rail = dynamics.on_rail(s2d, p)
    chuted = (not on_the_rail) and forces.parachute_deployed(t, s2d, p)

    if on_the_rail:
        # Rail buttons react every transverse force component and
        # prevent rotation (2D's own SS27.1 argument, one dimension up):
        # project the already-computed inertial force onto the exact 3D
        # rail embedding.
        e = _e_rail_3d(p)
        a_i = F_i / p.weight.m
        dydt[V] = np.dot(a_i, e) * e
    elif chuted:
        # The canopy drag is natively inertial (module docstring) and is
        # ADDED to F_i, not routed through it -- mirrors 2D's
        # `a_chute = (F_i + F_chute) / m` exactly.
        F_chute_2d = forces.parachute_drag_inertial(t, s2d, p, None)
        F_chute_3d = np.array([F_chute_2d[0], 0.0, F_chute_2d[1]])
        dydt[V] = (F_i + F_chute_3d) / p.weight.m
    else:
        dydt[V] = F_i / p.weight.m

    if on_the_rail or chuted:
        dydt[Q] = 0.0
        dydt[OMEGA] = 0.0
    else:
        dydt[Q] = quaternion.q_dot(q, omega)
        dydt[OMEGA] = domega_dt

    return dydt

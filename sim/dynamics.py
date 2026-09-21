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
"""

import numpy as np

from sim import aero
from sim.flow import flow_state
from sim.forces import aero_force_body, aero_moment_y, thrust_body, weight_inertial
from sim.frames import to_inertial
from sim.state import OMEGA, THETA, VX, VZ, X, Z


def _cross_y(a: np.ndarray, b: np.ndarray) -> float:
    """y-component of the 2D cross product `a x b` in the (x_hat_r, z_hat_r)
    plane, i.e. the scalar `c` such that `a x b = c*y_hat_r` (architecture.md
    SS2: `x_hat_r x z_hat_r = -y_hat_r`).
    """
    a_x, a_z = a
    b_x, b_z = b
    return -(a_x * b_z - a_z * b_x)


def derivatives(t: float, y: np.ndarray, p) -> np.ndarray:
    """dy/dt for the 6-vector state [x, z, vx, vz, theta, omega].

    Translation: `dx/dt = vx`, `dz/dt = vz`,
    `[dvx/dt, dvz/dt] = (weight_inertial + to_inertial(thrust_body + aero_force_body, theta)) / m`.

    Rotation (Step 6): `dtheta/dt = omega`,
    `domega/dt = M_y / I` where
    `M_y = cross_y(aB, thrust_body) + cross_y(aA, aero_force_body) + aero_moment_y`.
    """
    theta = y[THETA]

    # Step 9 tidy (architecture.md SS15 "Performance note"): each of these
    # is now backed by flow_state (and, from Step 12 on, the atmosphere
    # model), so computing them once and reusing them for both the force
    # sum and the moment halves the model evaluations per RHS call.
    # Behaviour-preserving -- identical numbers to calling them twice.
    thrust = thrust_body(t, y, p)
    aero_force = aero_force_body(t, y, p)

    body_forces = thrust + aero_force
    F_i = weight_inertial(t, y, p) + to_inertial(body_forces, theta)
    a_i = F_i / p.m

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
    # longer necessarily the constant `p.l1` -- `aero.cop_l1(alpha, M, p)`
    # looks it up from `p.aero_table` when one is configured, falling
    # back to the constant `p.l1` otherwise (bit-for-bit the line this
    # replaces). This is the one seam through which a table-driven CoP
    # location reaches the moment equation without otherwise
    # restructuring this function -- an extra `flow_state` call, matching
    # the existing (already-not-cached, per architecture.md SS21)
    # `aero_moment_y` call below, which recomputes `flow_state` a second
    # time on its own.
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
    flow = flow_state(t, y, p)
    l1_aero = aero.cop_l1(flow.alpha, flow.M, p)
    aA = np.array([-l1_aero, 0.0])         # CoP position
    aB = np.array([-(p.l1 + p.l2), 0.0])   # thrust application point

    # aB x T: on-axis thrust (T, 0) applied at an on-axis point (aB parallel
    # to T) produces zero pitching moment -- this term is intentionally zero
    # today. It is written out (not omitted) so a future gimbal or thrust
    # misalignment (T with a nonzero z-component, or aB off-axis) produces a
    # nonzero moment here with no change to this function's structure.
    M_thrust = _cross_y(aB, thrust)
    M_aero = _cross_y(aA, aero_force)
    M_moment = aero_moment_y(t, y, p)
    M_y = M_thrust + M_aero + M_moment

    dydt = np.zeros(6)
    dydt[X] = y[VX]
    dydt[Z] = y[VZ]
    dydt[VX] = a_i[0]
    dydt[VZ] = a_i[1]
    dydt[THETA] = y[OMEGA]
    dydt[OMEGA] = M_y / p.I
    return dydt

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
out explicitly (rather than only the pre-simplified scalar `l1*A_z - A_m`)
so that a future gimbal or thrust-misalignment model drops in without
touching this function's structure.
"""

import numpy as np

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

    body_forces = thrust_body(t, y, p) + aero_force_body(t, y, p)
    F_i = weight_inertial(t, y, p) + to_inertial(body_forces, theta)
    a_i = F_i / p.m

    # Geometry (main.tex SSGeometry): both points lie along the body x-axis,
    # relative to the CoG.
    aA = np.array([p.l1, 0.0])         # CoP position
    aB = np.array([p.l1 - p.l2, 0.0])  # thrust application point

    # aB x T: on-axis thrust (T, 0) applied at an on-axis point (aB parallel
    # to T) produces zero pitching moment -- this term is intentionally zero
    # today. It is written out (not omitted) so a future gimbal or thrust
    # misalignment (T with a nonzero z-component, or aB off-axis) produces a
    # nonzero moment here with no change to this function's structure.
    M_thrust = _cross_y(aB, thrust_body(t, y, p))
    M_aero = _cross_y(aA, aero_force_body(t, y, p))
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

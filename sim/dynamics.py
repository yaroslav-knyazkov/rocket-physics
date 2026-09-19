"""Equations of motion -- the ONLY place the EOM appear (architecture.md SS3).

Step 5 scope: `theta` is still a fixed constant from `Params` (rotation isn't
integrated until Step 6), but it no longer has to be pi/2 -- the
body-to-inertial rotation now lives in `frames.py` (architecture.md SS2,
"The single rotation function") instead of being written out inline here
(that was Step 4's explicitly-deferred shortcut).

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
"""

import numpy as np

from sim.forces import aero_force_body, thrust_body, weight_inertial
from sim.frames import to_inertial
from sim.state import OMEGA, THETA, VX, VZ, X, Z


def derivatives(t: float, y: np.ndarray, p) -> np.ndarray:
    """dy/dt for the 6-vector state [x, z, vx, vz, theta, omega].

    Step 5: theta and omega are still frozen (dtheta/dt = domega/dt = 0).
    Translation is `dx/dt = vx`, `dz/dt = vz`,
    `[dvx/dt, dvz/dt] = (weight_inertial + to_inertial(thrust_body + aero_force_body, theta)) / m`.
    """
    theta = y[THETA]

    body_forces = thrust_body(t, y, p) + aero_force_body(t, y, p)
    F_i = weight_inertial(t, y, p) + to_inertial(body_forces, theta)
    a_i = F_i / p.m

    dydt = np.zeros(6)
    dydt[X] = y[VX]
    dydt[Z] = y[VZ]
    dydt[VX] = a_i[0]
    dydt[VZ] = a_i[1]
    dydt[THETA] = 0.0
    dydt[OMEGA] = 0.0
    return dydt

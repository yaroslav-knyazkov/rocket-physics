"""Equations of motion -- the ONLY place the EOM appear (architecture.md SS3).

Step 2 scope: vertical point mass under gravity and constant thrust.
`theta` is frozen at pi/2 (vertical, nose-up) and there is no aerodynamic
force yet (that's forces.py / Step 4) -- pure translation in z.

Frame convention: single NED-like inertial frame, z DOWN (architecture.md
SS2). Weight is `W = m*g*z_hat` with g = +9.80665, no sign fixups. At
theta = pi/2 the body x-axis (thrust direction, main.tex `T = T*x_hat_r`)
maps to the inertial frame as `R_body_to_inertial(pi/2) @ (1, 0) = (0, -1)`
-- i.e. straight up, decreasing z. So the net vertical acceleration is
`az = g - T/m`: gravity pulls down (+z), thrust pushes up (-z).
"""

import numpy as np

from sim.state import X, Z, VX, VZ, THETA, OMEGA

# Hardcoded constant-thrust burn duration for this step only. There is no
# thrust-curve or burnout-event model yet (that arrives in Phase 2 /
# Step 11); this is the minimal "constant thrust for a fixed duration"
# needed to make the analytic apogee check in architecture.md/roadmap.md
# Step 2 computable at all. With the placeholder T=50 N, m=0.5 kg in
# run.py, T/m = 100 m/s^2 >> g, so thrust that never turned off would mean
# the rocket never reaches apogee under thrust alone.
T_BURN = 2.0  # [s]


def derivatives(t: float, y: np.ndarray, p) -> np.ndarray:
    """dy/dt for the 6-vector state [x, z, vx, vz, theta, omega].

    Step 2: theta and omega are frozen (dtheta/dt = domega/dt = 0), x/vx
    just carry through unchanged (they stay 0 for a vertical launch), and
    the vertical channel is `dz/dt = vz`, `dvz/dt = g - T/m` while
    `t < T_BURN`, else `dvz/dt = g` (free fall).
    """
    thrust = p.T if t < T_BURN else 0.0

    dydt = np.zeros(6)
    dydt[X] = y[VX]
    dydt[Z] = y[VZ]
    dydt[VX] = 0.0
    dydt[VZ] = p.g - thrust / p.m
    dydt[THETA] = 0.0
    dydt[OMEGA] = 0.0
    return dydt

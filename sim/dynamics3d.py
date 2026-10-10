"""3D equations of motion -- translation only (roadmap.md Step 29;
architecture.md Phase 3). The 3D analogue of sim/dynamics.py's
`derivatives`, one dimension up, for the 13-component state
`[r(3), v(3), q(4), omega(3)]` (sim/state3d.py).

Frame convention: same single NED-like inertial frame as the 2D code, z
DOWN (sim/state3d.py's own docstring), with y completing a right-handed
triad.

`m*v_dot = W + R(q)@(T_body + A_body)` (main.tex SSEquations of motion,
generalised to 3D with the quaternion DCM `sim.quaternion.to_dcm(q)` in
place of the 2D `frames.R_body_to_inertial(theta)`):

    dr/dt     = v
    dv/dt     = (weight_inertial_3d + to_dcm(q) @ (thrust_body_3d + aero_force_body_3d)) / m
    dq/dt     = 0   (constant -- Step 29 holds attitude fixed; see state3d.py)
    domega/dt = 0   (constant -- no moments computed yet; Step 30's job)

`m` is the fixed `p.weight.m`: there is no 3D variable-mass model yet (the
13-component layout has no mass field; forces3d.py's 2D-state adapter
always passes mass `0.0` through, which is inert since `weight_inertial`
only reads it when `p.weight.m_d` is set -- off for every Step-29
scenario).

Step 29's own "Check" (roadmap.md): planar initial conditions (`r[1] = 0`,
`v[1] = 0`, `q` pitch-only) must reproduce the Phase 1 2D trajectory to
solver tolerance, with `r[1]`/`v[1]` staying exactly `0.0` throughout --
see tests/test_dynamics3d.py.
"""

import numpy as np

from sim import quaternion
from sim.forces3d import aero_force_body_3d, thrust_body_3d, weight_inertial_3d
from sim.state3d import N, OMEGA, Q, R, V


def derivatives_3d(t: float, y: np.ndarray, p) -> np.ndarray:
    """dy/dt for the 13-component 3D state (module docstring)."""
    v = y[V]
    q = y[Q]

    W_i = weight_inertial_3d(t, y, p)
    T_b = thrust_body_3d(t, y, p)
    A_b = aero_force_body_3d(t, y, p)

    dvdt = (W_i + quaternion.to_dcm(q) @ (T_b + A_b)) / p.weight.m

    dydt = np.empty(N)
    dydt[R] = v
    dydt[V] = dvdt
    dydt[Q] = 0.0
    dydt[OMEGA] = 0.0
    return dydt

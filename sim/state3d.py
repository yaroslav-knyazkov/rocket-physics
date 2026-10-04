"""3D state vector (roadmap.md Step 29; architecture.md Phase 3).

13-component layout `[r(3), v(3), q(4), omega(3)]` -- same NED-like inertial
frame as sim/state.py (z DOWN, architecture.md SS2), extended to 3D with y
completing a right-handed triad (sim/quaternion.py's own frame convention,
Step 28). `q` is the attitude quaternion (body -> inertial, scalar-first,
sim.quaternion's convention); `omega` is the body-frame angular velocity.

Step 29 scope: `q` and `omega` are both held exactly constant for the whole
integration -- `dq/dt = 0`, `domega/dt = 0` identically (sim/dynamics3d.py).
This mirrors Phase 1's own staging (Step 4: "translation only, theta fixed
at a constant", before real rotation arrived at Step 6) one dimension up --
not a step that partially wires in rotational kinematics. Both fields are
still part of the state vector here, rather than passed around separately,
because the roadmap's own 13-component layout names them as integrated
state from the start: Step 30 (full rotational dynamics, `q_dot`/Euler's
equations) needs them already wired into the vector `solve_ivp` sees, not
retrofitted into a smaller layout later.

`State3D` mirrors sim/state.py's NamedTuple-plus-index-constants style,
generalised from scalar fields to vector slices of the flat array.
"""

from typing import NamedTuple

import numpy as np


class State3D(NamedTuple):
    r: np.ndarray      # inertial position (x, y, z), z DOWN-positive [m]
    v: np.ndarray      # inertial velocity (vx, vy, vz) [m/s]
    q: np.ndarray      # attitude quaternion, body->inertial, scalar-first [-]
    omega: np.ndarray  # body-frame angular velocity (wx, wy, wz) [rad/s]


# Slice constants for the flat 13-component state vector the integrator
# sees, e.g. `dynamics3d.derivatives_3d(t, y, p)` and sim/forces3d.py's
# force functions. Kept in sync with the field order of State3D above.
R = slice(0, 3)
V = slice(3, 6)
Q = slice(6, 10)
OMEGA = slice(10, 13)
N = 13  # total length of the flat state vector


def to_vector(s: State3D) -> np.ndarray:
    """Flatten a State3D into the 13-component array `solve_ivp` expects."""
    return np.concatenate([np.asarray(s.r, dtype=float),
                            np.asarray(s.v, dtype=float),
                            np.asarray(s.q, dtype=float),
                            np.asarray(s.omega, dtype=float)])


def from_vector(y: np.ndarray) -> State3D:
    """Inverse of `to_vector`: unpack a flat 13-component array into a
    State3D. The vector fields are views into `y`, not copies -- cheap for
    read-only access; a caller that needs to mutate one independently of
    `y` should copy explicitly."""
    y = np.asarray(y)
    return State3D(r=y[R], v=y[V], q=y[Q], omega=y[OMEGA])

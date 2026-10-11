"""3D-vector wrappers around the existing Phase-1/2D force functions
(sim/forces.py) -- roadmap.md Step 29, architecture.md Phase 3.

Every force here is returned in its *natural* frame, same discipline as
sim/forces.py's own module docstring: `weight_inertial_3d` in the inertial
frame, `thrust_body_3d`/`aero_force_body_3d` in the body frame.

### The one real design decision: adapting a 13-component 3D state into
### the existing 2D force functions, instead of re-deriving the physics

`sim.forces.weight_inertial`/`thrust_body`/`aero_force_body` all take
`(t, s, p)` where `s` is a plain array indexable by sim.state's
X/Z/VX/VZ/THETA/OMEGA/M constants. Internally they call:

  * `sim.flow.flow_state(t, s, p)`, which reads `s[VX]`, `s[VZ]`,
    `s[THETA]` directly, plus `s[X]`/`s[Z]` indirectly via
    `sim.atmosphere.air_state`/`sim.wind.wind_inertial` (altitude- and
    ground-range-dependent atmosphere/wind models) and
    `sim.gravity.z_hat_g`/`sim.gravity.g` (direction/magnitude models
    that can depend on downrange position for the curved-ground
    variants);
  * `sim.thrust_curve.thrust(t, s, p)`, which reads `s[Z]`/`s[X]` the
    same way, for the altitude-dependent nozzle-exit pressure
    correction.

Step 29's own physics is explicitly confined to the x-z plane (per the
roadmap: translation only, attitude held fixed, every force embedded with
a zero y-component below) -- so every 3D state this step actually
integrates keeps `r[1] == v[1] == 0` and carries a pitch-only quaternion
`q = quaternion.from_euler(0, theta, 0)` (Step 28's own load-bearing
check: this reproduces the 2D `R_body_to_inertial(theta)` exactly). Given
that, the cleanest way to reuse the 2D functions *verbatim* -- rather than
duplicating their formulas by hand, which is exactly what this step is
not supposed to do -- is to build a compatible 2D-style state array fresh
on every call:

    s2d = [ r[0], r[2], v[0], v[2], theta, omega[1], 0.0 ]
            (X)    (Z)   (VX)  (VZ)  (THETA)  (OMEGA)   (M)

`theta` (the 2D pitch angle) is recovered from the quaternion via
`quaternion.to_euler(q)[1]`: exact and round-trip-safe for any pitch-only
`q`, by Step 28's own round-trip check. `omega[1]` (the body-frame
y-component) is the 3D analogue of the 2D scalar pitch rate, since the
x-z plane's only rotation axis is y. `M` (mass) is left at `0.0`: the
13-component layout has no mass field of its own (no 3D variable-mass
model exists yet), and `weight_inertial` only ever reads `s[M]` when
`p.weight.m_d` is set -- every Step-29 scenario leaves that off, so this is
an inert placeholder, not a silently wrong value.

This adapter array is a disposable *view* built fresh per call, not a
stored/cached conversion, and it is only ever handed to the 2D force
functions above -- nothing here claims validity for a general
(non-planar) 3D attitude. That is explicitly out of scope until Step 31
(3D aerodynamics), which is expected to replace `aero_force_body_3d`'s
body with a true 3D relative-wind/sideslip model instead of routing
through this adapter at all.

### Embeddings

  * `weight_inertial_3d`: `sim.forces.weight_inertial`'s 2D `(Wx, Wz)`
    embedded as `(Wx, 0, Wz)` -- gravity direction never rotates out of
    the launch vertical plane in this project (`gravity.z_hat_g`'s
    existing (x, z) pair), so this is an exact embedding, not an
    approximation.
  * `thrust_body_3d`: `sim.forces.thrust_body`'s 2D
    `(T*cos(delta), T*sin(delta))` embedded as
    `(T*cos(delta), 0, T*sin(delta))` -- on-axis thrust plus the existing
    in-plane nozzle cant; no new out-of-plane thrust misalignment is
    modelled here (that would be new physics, out of this step's scope).
  * `aero_force_body_3d`: `sim.forces.aero_force_body`'s 2D
    `(-A_x, -A_z)` embedded as `(-A_x, 0, -A_z)`.
"""

import numpy as np

from sim import forces as forces2d
from sim import quaternion
from sim.flow import flow_state
from sim.state3d import OMEGA, Q, R, V


def _s2d(s: np.ndarray) -> np.ndarray:
    """Build the 2D-compatible state array described in the module
    docstring, from a 13-component 3D state `s`."""
    r = s[R]
    v = s[V]
    q = s[Q]
    omega = s[OMEGA]
    _yaw, theta, _roll = quaternion.to_euler(q)
    return np.array([r[0], r[2], v[0], v[2], theta, omega[1], 0.0])


def weight_inertial_3d(t: float, s: np.ndarray, p) -> np.ndarray:
    """W, inertial frame, 3-vector -- `sim.forces.weight_inertial`'s 2D
    `(Wx, Wz)` embedded with a zero y-component (module docstring)."""
    Wx, Wz = forces2d.weight_inertial(t, _s2d(s), p)
    return np.array([Wx, 0.0, Wz])


def thrust_body_3d(t: float, s: np.ndarray, p) -> np.ndarray:
    """T_body, body frame, 3-vector -- `sim.forces.thrust_body`'s 2D
    `(T*cos(delta), T*sin(delta))` embedded with a zero y-component
    (module docstring)."""
    Tx, Tz = forces2d.thrust_body(t, _s2d(s), p)
    return np.array([Tx, 0.0, Tz])


def aero_force_body_3d(t: float, s: np.ndarray, p) -> np.ndarray:
    """A_body, body frame, 3-vector -- `sim.forces.aero_force_body`'s 2D
    `(-A_x, -A_z)` embedded with a zero y-component (module docstring).

    Step 56 (architecture-28-rewrite.md SS28.11): `aero_force_body` now
    requires its caller's own `flow_state(t, s, p)` result instead of
    computing it internally (closing F8) -- this adapter computes it once,
    on the same disposable 2D-compatible state view `_s2d(s)` it already
    builds for the force call itself, and passes it through. Purely
    mechanical signature-compatibility follow-through, not new 3D physics
    (Step 30's rotational EOM, which would add a 3D `aero_moment` call
    here, remains out of scope)."""
    s2d = _s2d(s)
    flow = flow_state(t, s2d, p)
    Ax, Az = forces2d.aero_force_body(t, s2d, p, flow)
    return np.array([Ax, 0.0, Az])

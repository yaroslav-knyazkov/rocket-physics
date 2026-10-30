"""apps/sim/engine/forces3d.py -- 3D-vector wrappers around the existing Phase-1/2D force functions
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

`theta` (the 2D pitch angle) is recovered from the quaternion with a
direct DCM extraction, `atan2(-R[2,0], R[0,0])` where
`R = quaternion.to_dcm(q)` -- exact and round-trip-safe for any
pitch-only `q`, over the full `(-pi, pi]` range. **Not**
`quaternion.to_euler(q)[1]`: Step 32 finding (architecture-37-step32-3d-
integration-harness.md SS37.0.4/D-32.9) -- `to_euler`'s pitch comes from
`arcsin`, range `[-90, +90] deg`, and folds any angle outside that range
back into it (135 deg -> 45 deg, etc.), silently reporting the nose
pointing downrange no matter where it actually points. `_s2d` calls this
on every RHS evaluation, including past a vertical launch
(`rail_angle_deg = 90.0`, the project default) and through ballistic
descent, both of which routinely leave `arcsin`'s range -- so the
`atan2` form is not a precision nicety, it is required for `_s2d` to be
meaningful at all past Step 29's narrow boost-phase test span.
`quaternion.to_euler` itself is unchanged and keeps its documented
"plotting-style output only" contract; `_s2d` no longer violates it.
`omega[1]` (the body-frame y-component) is the 3D analogue of the 2D
scalar pitch rate, since the x-z plane's only rotation axis is y. `M`
(mass) is left at `0.0`: the 13-component layout has no mass field of
its own (no 3D variable-mass model exists yet), and `weight_inertial`
only ever reads `s[M]` when `p.weight.m_d` is set -- every Step-29
scenario leaves that off, so this is an inert placeholder, not a
silently wrong value.

This adapter array is a disposable *view* built fresh per call, not a
stored/cached conversion, and it is only ever handed to the 2D force
functions above -- nothing here claims validity for a general
(non-planar) 3D attitude (the `atan2` fix corrects the *planar* pitch
recovery only; a non-zero roll/yaw quaternion still has no valid 2D
embedding). That is explicitly out of scope until Step 31
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

import math

import numpy as np

from apps.sim.engine import aero, control, dynamics
from apps.sim.engine import forces as forces2d
from apps.sim.engine import quaternion
from apps.sim.engine.flow import flow_state
from apps.sim.engine.state3d import OMEGA, Q, R, V


def _s2d(s: np.ndarray) -> np.ndarray:
    """Build the 2D-compatible state array described in the module
    docstring, from a 13-component 3D state `s`.

    `theta` (the 2D pitch angle) is recovered with a direct DCM
    extraction, `atan2(-R[2,0], R[0,0])`, **not**
    `quaternion.to_euler(q)[1]` -- Step 32 finding (architecture-37-
    step32-3d-integration-harness.md SS37.0.4/D-32.9): `to_euler`'s pitch
    comes from `arcsin`, range `[-90, +90] deg`, and folds any angle past
    that back into range (e.g. 135 deg -> 45 deg, 170 deg -> 10 deg) --
    silently reporting the nose pointing downrange no matter where it
    actually points. `to_euler`'s own docstring says the integrated state
    is never supposed to call it at that attitude; `_s2d` was doing
    exactly that on every RHS evaluation, and the project's default
    launch (`rail_angle_deg = 90.0`) plus any ballistic descent sit
    squarely in the broken range. `atan2(-R[2,0], R[0,0])` is the full
    `(-pi, pi]` extraction and is exact for any pitch-only `q` (no roll,
    no yaw) -- precisely `_s2d`'s documented contract; it is *not* a fix
    for non-planar attitude recovery in general, which stays Step 31's
    job (replacing this whole adapter). Wrapped at +-pi like any `atan2`,
    so it still cannot represent a multi-revolution tumble the way 2D's
    integrated, unwrapped `theta` can -- immaterial here, since every
    downstream consumer of this `theta` reads it through `sin`/`cos`."""
    r = s[R]
    v = s[V]
    q = s[Q]
    omega = s[OMEGA]
    R_dcm = quaternion.to_dcm(q)
    theta = math.atan2(-R_dcm[2, 0], R_dcm[0, 0])
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


def flow_fb_coeffs_3d(t: float, s: np.ndarray, p):
    """Shared `(flow, fb, coeffs)` bundle for a 3D state `s`, on the same
    disposable `_s2d(s)` view every function below builds. code-review
    finding (2026-10-25): `aero_force_body_3d` and `moment_body_3d` each
    used to recompute this bundle independently, so a `derivatives_3d`
    call with `p.inertia.model == "tensor"` paid for it TWICE per RHS
    evaluation -- exactly the redundant atmosphere/aero work Step 56/114
    eliminated on the 2D path (`sim/dynamics.py`'s own `flow`/`fb`/`coeffs`
    locals, computed once and threaded through). This helper is the single
    place that computation happens now; `sim.dynamics3d.derivatives_3d`
    calls it once and passes the result to both `aero_force_body_3d` and
    `moment_body_3d` when both are needed in the same call."""
    s2d = _s2d(s)
    flow = flow_state(t, s2d, p)
    hold = None
    fb = control.airbrake_deploy_fraction(t, s2d, p, hold)
    coeffs = aero.coefficients(t, s2d, p, flow, hold, fb)
    return flow, fb, coeffs


def aero_force_body_3d(t: float, s: np.ndarray, p, flow=None, fb=None, coeffs=None) -> np.ndarray:
    """A_body, body frame, 3-vector -- `sim.forces.aero_force_body`'s 2D
    `(-A_x, -A_z)` embedded with a zero y-component (module docstring).

    Step 56 (architecture-28-rewrite.md SS28.11): `aero_force_body` now
    requires its caller's own `flow_state(t, s, p)` result instead of
    computing it internally (closing F8) -- this adapter computes it once,
    on the same disposable 2D-compatible state view `_s2d(s)` it already
    builds for the force call itself, and passes it through. Purely
    mechanical signature-compatibility follow-through, not new 3D physics.
    The 3D moment vector (Step 30's rotational EOM) is `moment_body_3d`
    below, a separate function -- not added here, since this function's
    contract is a force, not a moment.

    `flow`/`fb`/`coeffs`, all optional (default `None`): when the caller
    already has them (`flow_fb_coeffs_3d`'s own bundle, SS30.4's sibling
    fix), pass them through instead of recomputing -- bit-for-bit
    identical either way, since these are pure functions of `(t, s2d, p)`.
    `None` (every pre-existing call site, including every test) recomputes
    internally, unchanged."""
    s2d = _s2d(s)
    if flow is None:
        flow, fb, coeffs = flow_fb_coeffs_3d(t, s, p)
    Ax, Az = forces2d.aero_force_body(t, s2d, p, flow, fb=fb, c=coeffs)
    return np.array([Ax, 0.0, Az])


def moment_body_3d(t: float, s: np.ndarray, p, flow=None, fb=None, coeffs=None) -> np.ndarray:
    """M about the CoG, body frame, 3-vector -- the 2D pitching moment
    `M_y` embedded with zero roll and yaw components (module docstring;
    task-30-3d-rotational-dynamics.md SS30.4, eq:moment_3d).

    `M_y` is assembled by calling `sim.dynamics.pitch_moment` on this
    adapter's own `_s2d(s)` view -- the EXACT same extracted formula
    `derivatives` itself calls (D-30.7), not a hand-copied duplicate
    (`forces3d.py`'s own module docstring states that philosophy).
    `M_x = M_z = 0.0`: no roll moment (fin cant) and no yaw moment
    (sideslip) are modelled yet -- Step 31's scope, and the research note
    `3d_equations_of_motion.md` SS5 and `rocket-3d.tex`'s simtodo note on
    `eq:moment_3d` state the same staging.

    Note 1 (task-30 SS30.4.2): no sign conversion is needed. `_cross_y`
    (`sim.dynamics`) computes exactly the y-component of the standard
    right-handed 3D cross product for in-plane vectors, so `M_y` drops
    straight into this vector's middle slot.

    Note 3: inherits `_s2d`'s documented limits (module docstring) --
    correct for planar attitude, an approximation otherwise, exactly like
    the three force wrappers above. Step 31 replaces the whole adapter.

    `flow`/`fb`/`coeffs`, all optional (default `None`): see
    `aero_force_body_3d`'s matching note -- same sharing mechanism,
    `flow_fb_coeffs_3d`, same bit-for-bit guarantee."""
    s2d = _s2d(s)
    if flow is None:
        flow, fb, coeffs = flow_fb_coeffs_3d(t, s, p)
    hold = None
    M_y = dynamics.pitch_moment(t, s2d, p, flow, hold, fb, coeffs)
    return np.array([0.0, M_y, 0.0])

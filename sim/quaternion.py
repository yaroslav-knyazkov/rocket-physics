"""Quaternion algebra for Phase 3 attitude (roadmap.md Step 28; architecture.md
"Phase 3"; docs/latex/research/3d_equations_of_motion.md SS2).

Pure algebra: no `Params`/`State` dependency, no dynamics, nothing imported
from the rest of `sim/`. Everything downstream (Step 29 state3d.py, Step 30
dynamics3d.py) builds on the conventions fixed here.

### Why quaternions (not Euler angles) for the integrated state

The standard aerospace 3-2-1 Euler sequence is singular at pitch +-90 deg --
exactly where a vertically-launched rocket sits for the whole boost phase.
Quaternions have no such singularity; `from_euler`/`to_euler` below exist
only for human-readable I/O (e.g. `plotting.py`), never for the integrated
state itself.

### Representation

`q = (q0, q1, q2, q3)`, **scalar-first**, a plain length-4 `np.ndarray`.
`q0` is the scalar part, `(q1, q2, q3)` the vector part. `q` represents the
rotation from the inertial frame to the body frame in the sense that
`rotate_vector(q, v_body) == to_dcm(q) @ v_body == v_inertial` -- i.e. `q`
carries the same "body -> inertial" meaning as `sim/frames.py`'s
`R_body_to_inertial(theta)`, generalised from one angle to three. Frame
convention is this project's usual single NED-like frame, z DOWN
(architecture.md SS2), now with y completing a right-handed triad.

### Quaternion product (Hamilton convention)

`multiply(q1, q2)` is the Hamilton product `q1 (x) q2`:
```
w = w1*w2 - x1*x2 - y1*y2 - z1*z2
x = w1*x2 + x1*w2 + y1*z2 - z1*y2
y = w1*y2 - x1*z2 + y1*w2 + z1*x2
z = w1*z2 + x1*y2 - y1*x2 + z1*w2
```
(`w` <-> `q0`, `(x, y, z)` <-> `(q1, q2, q3)`.) This is the same convention
docs/latex/research/3d_equations_of_motion.md SS2 uses for the kinematics
below -- `q_dot`'s component form there was derived from exactly this
product, not a different textbook sign/order convention.

### Kinematics

`q_dot(q, omega_body) = 0.5 * q (x) (0, omega_body)` (research note SS2,
reproduced here in the same explicit component form so it is directly
checkable against that note):
```
q0_dot = -0.5*(q1*wx + q2*wy + q3*wz)
q1_dot =  0.5*(q0*wx + q2*wz - q3*wy)
q2_dot =  0.5*(q0*wy + q3*wx - q1*wz)
q3_dot =  0.5*(q0*wz + q1*wy - q2*wx)
```
`|q| = 1` is preserved only in exact arithmetic; `normalise` below is how a
caller (Step 30's `dynamics3d.py`) corrects numerical drift -- every RHS
call or as a solver event, a pure implementation-cost choice left to that
step, not this one.

### Euler angles: 3-2-1 (yaw-pitch-roll), for `from_euler`/`to_euler` only

`from_euler(yaw, pitch, roll)` builds the body-to-inertial quaternion by
composing three elemental rotations in the standard aerospace order --
yaw about inertial z, then pitch about the new y, then roll about the new
x (intrinsic z-y'-x''), i.e. `q = q_z(yaw) (x) q_y(pitch) (x) q_x(roll)`,
equivalently `R_body_to_inertial = Rz(yaw) @ Ry(pitch) @ Rx(roll)`. This
reduces to the project's existing pitch-only 2D case exactly when
`yaw = roll = 0`: `q = (cos(pitch/2), 0, sin(pitch/2), 0)`, the same
quaternion `architecture.md`'s Phase 3 section and the research note both
name as the load-bearing check for this step. Singular at `pitch = +-90
deg` (yaw and roll become degenerate there) -- expected and the whole
reason the integrated state uses quaternions instead, per the module
docstring above. `to_euler` inverts the same convention via the standard
2-1 extraction from the DCM; both round-trip exactly away from that
singularity.
"""

import numpy as np

# Scalar-first component indices, for callers that prefer names over
# `q[0]`/`q[1]`/... .
W, X, Y, Z = 0, 1, 2, 3


def multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """Hamilton product `q1 (x) q2` (module docstring). Not commutative in
    general; associative (`(q1*q2)*q3 == q1*(q2*q3)`, exercised by
    tests/test_quaternion.py)."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


def conjugate(q: np.ndarray) -> np.ndarray:
    """`(q0, -q1, -q2, -q3)`. For a unit `q`, `multiply(q, conjugate(q))`
    is the identity quaternion `(1, 0, 0, 0)` -- the conjugate is the
    inverse rotation."""
    q0, q1, q2, q3 = q
    return np.array([q0, -q1, -q2, -q3])


def norm(q: np.ndarray) -> float:
    """Euclidean norm of the 4-vector (1.0 for a unit quaternion)."""
    return float(np.sqrt(np.dot(q, q)))


def normalise(q: np.ndarray) -> np.ndarray:
    """Rescale `q` to unit norm. A no-op (within floating-point tolerance)
    if `q` is already unit; preserves the rotation `q` represents for any
    nonzero scale (`rotate_vector` is unchanged by a positive rescale --
    the sandwich product `q v q*` scales as `|q|**2`, matched exactly by
    one normalisation)."""
    return q / norm(q)


def rotate_vector(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate the 3-vector `v` by the (assumed-unit) quaternion `q`:
    `q (x) (0, v) (x) conjugate(q)`, vector part of the result. Body ->
    inertial when `q` is the body attitude (module docstring); matches
    `to_dcm(q) @ v` exactly for unit `q` (tests/test_quaternion.py), via an
    independent closed-form DCM rather than routing through this function,
    so that test is a genuine cross-check and not a tautology."""
    v_pure = np.array([0.0, v[0], v[1], v[2]])
    rotated = multiply(multiply(q, v_pure), conjugate(q))
    return rotated[1:]


def to_dcm(q: np.ndarray) -> np.ndarray:
    """3x3 direction-cosine matrix, body -> inertial, from the closed-form
    quaternion formula (standard result, e.g. Wertz; independent of
    `rotate_vector`'s sandwich-product route -- see that function's
    docstring)."""
    q0, q1, q2, q3 = q
    return np.array(
        [
            [
                q0 * q0 + q1 * q1 - q2 * q2 - q3 * q3,
                2.0 * (q1 * q2 - q0 * q3),
                2.0 * (q1 * q3 + q0 * q2),
            ],
            [
                2.0 * (q1 * q2 + q0 * q3),
                q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3,
                2.0 * (q2 * q3 - q0 * q1),
            ],
            [
                2.0 * (q1 * q3 - q0 * q2),
                2.0 * (q2 * q3 + q0 * q1),
                q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3,
            ],
        ]
    )


def from_euler(yaw: float, pitch: float, roll: float) -> np.ndarray:
    """Body-to-inertial quaternion from 3-2-1 (yaw-pitch-roll) Euler
    angles, radians (module docstring: convention, composition order,
    gimbal-lock location)."""
    q_yaw = np.array([np.cos(yaw / 2.0), 0.0, 0.0, np.sin(yaw / 2.0)])
    q_pitch = np.array([np.cos(pitch / 2.0), 0.0, np.sin(pitch / 2.0), 0.0])
    q_roll = np.array([np.cos(roll / 2.0), np.sin(roll / 2.0), 0.0, 0.0])
    return multiply(multiply(q_yaw, q_pitch), q_roll)


def to_euler(q: np.ndarray) -> tuple[float, float, float]:
    """Inverse of `from_euler`: `(yaw, pitch, roll)` radians, 3-2-1
    convention, extracted from the DCM (standard 2-1 formula). Singular at
    `pitch = +-90 deg` (module docstring) -- not handled specially here,
    since the integrated state never calls this function at that attitude
    (it uses the quaternion directly); `plotting.py`-style human-readable
    output is this function's only intended caller."""
    R = to_dcm(q)
    pitch = np.arcsin(np.clip(-R[2, 0], -1.0, 1.0))
    roll = np.arctan2(R[2, 1], R[2, 2])
    yaw = np.arctan2(R[1, 0], R[0, 0])
    return float(yaw), float(pitch), float(roll)


def q_dot(q: np.ndarray, omega_body: np.ndarray) -> np.ndarray:
    """Attitude kinematics `q_dot = 0.5 * q (x) (0, omega_body)`, explicit
    component form (module docstring; docs/latex/research/
    3d_equations_of_motion.md SS2, reproduced verbatim). `omega_body` is
    the body-frame angular velocity `(wx, wy, wz)` [rad/s]."""
    q0, q1, q2, q3 = q
    wx, wy, wz = omega_body
    return np.array(
        [
            -0.5 * (q1 * wx + q2 * wy + q3 * wz),
            0.5 * (q0 * wx + q2 * wz - q3 * wy),
            0.5 * (q0 * wy + q3 * wx - q1 * wz),
            0.5 * (q0 * wz + q1 * wy - q2 * wx),
        ]
    )

"""apps/sim/engine/frames.py -- Body <-> inertial rotation -- the ONLY place `sin`/`cos` appear
(architecture.md SS2, "The single rotation function").

Frame convention: single NED-like inertial frame, z DOWN (architecture.md
SS2). Attitude `theta` is pitch, positive nose-up, measured from the
inertial x_hat (horizontal).

    R_body_to_inertial(theta) = [[cos theta,  sin theta],
                                 [-sin theta, cos theta]]

Sign checks (architecture.md SS2, reproduced as tests/test_frames.py):
    x_hat_r = (1, 0)_b -> (cos theta, -sin theta)_i; at theta = pi/2 this is
    (0, -1)_i, i.e. straight up. z_hat_r = (0, 1)_b -> (sin theta, cos
    theta)_i; at theta = 0 this is z_hat_i (down).

`R_body_to_inertial` is a rotation matrix, hence orthogonal: its inverse
(inertial -> body) is just its transpose, no separate derivation needed.
"""

import numpy as np


def R_body_to_inertial(theta: float) -> np.ndarray:
    """2x2 rotation matrix, body frame -> inertial frame, acting on (x, z)
    components (architecture.md SS2)."""
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return np.array([[cos_t, sin_t], [-sin_t, cos_t]])


def to_inertial(v_body: np.ndarray, theta: float) -> np.ndarray:
    """Rotate a body-frame (x, z) vector into the inertial frame."""
    return R_body_to_inertial(theta) @ v_body


def to_body(v_inertial: np.ndarray, theta: float) -> np.ndarray:
    """Rotate an inertial-frame (x, z) vector into the body frame.

    The inverse of `to_inertial`: since `R_body_to_inertial` is orthogonal,
    its inverse is its transpose.
    """
    return R_body_to_inertial(theta).T @ v_inertial

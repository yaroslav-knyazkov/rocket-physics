"""Tests for apps/sim/engine/forces3d.py's `_s2d` pitch recovery (Step 32,
sub-step 32.0; architecture-37-step32-3d-integration-harness.md SS37.0.4/
D-32.9).

`_s2d` used to recover the 2D-compatible pitch angle via
`quaternion.to_euler(q)[1]`, whose `arcsin` folds any `|pitch| > 90 deg`
back into `[-90, 90]` deg -- a silent violation of `to_euler`'s own
documented precondition ("the integrated state never calls this function
at that attitude"). This file pins the SS37.0.4 round-trip table directly:
a pitch-only quaternion built at angles both inside and outside `arcsin`'s
range must round-trip through `_s2d` to the *original* angle, not the
folded one.
"""

import math

import numpy as np

from apps.sim.engine.forces3d import _s2d
from apps.sim.engine.quaternion import from_euler
from apps.sim.engine.state3d import N, OMEGA, Q, R, V


def _pitch_only_state(theta_rad: float) -> np.ndarray:
    """A 13-component 3D state with zero position/velocity/omega and a
    pitch-only attitude quaternion at `theta_rad` -- exactly `_s2d`'s
    documented contract (forces3d.py module docstring)."""
    y = np.zeros(N)
    y[R] = 0.0
    y[V] = 0.0
    y[Q] = from_euler(0.0, theta_rad, 0.0)
    y[OMEGA] = 0.0
    return y


# SS37.0.4's measured table: angles both inside and outside the old
# `arcsin` range `[-90, 90]` deg. Each must round-trip to itself, not the
# folded value the old `to_euler`-based recovery produced (e.g. 135 -> 45).
_ROUND_TRIP_ANGLES_DEG = [45.0, 85.0, 89.9, 90.0, 95.0, 135.0, 170.0, -135.0]


def test_s2d_recovers_pitch_without_arcsin_folding():
    """SS37.0.4's round-trip table, pinned as a test: `_s2d(y)[4]`
    (the recovered 2D theta) must match the original pitch angle to
    `1e-12`, for angles that the old `arcsin`-based recovery folded
    (95, 135, 170, -135 deg) as well as ones it happened to get right
    (45, 85, 89.9, 90 deg)."""
    for theta_deg in _ROUND_TRIP_ANGLES_DEG:
        theta_rad = math.radians(theta_deg)
        y = _pitch_only_state(theta_rad)
        s2d = _s2d(y)
        recovered = s2d[4]
        assert math.isclose(recovered, theta_rad, rel_tol=1e-12, abs_tol=1e-12), (
            f"theta={theta_deg} deg: expected {theta_rad}, got {recovered} "
            f"({math.degrees(recovered)} deg) -- looks like arcsin folding"
        )


def test_s2d_recovery_matches_atan2_directly():
    """Independent cross-check of the fix itself (not just the round
    trip): `_s2d`'s recovered theta must equal `atan2(-R[2,0], R[0,0])`
    computed directly from the DCM, for every angle in the table."""
    from apps.sim.engine.quaternion import to_dcm

    for theta_deg in _ROUND_TRIP_ANGLES_DEG:
        theta_rad = math.radians(theta_deg)
        y = _pitch_only_state(theta_rad)
        s2d = _s2d(y)
        q = y[Q]
        R_dcm = to_dcm(q)
        expected = math.atan2(-R_dcm[2, 0], R_dcm[0, 0])
        assert math.isclose(s2d[4], expected, rel_tol=1e-12, abs_tol=1e-12)


def test_s2d_other_fields_unchanged():
    """The fix touches only the pitch recovery -- r[0]/r[2]/v[0]/v[2]/
    omega[1]/M must still come through `_s2d` exactly as before."""
    y = np.zeros(N)
    y[R] = [1.5, 0.0, -2.5]
    y[V] = [3.0, 0.0, -4.0]
    y[Q] = from_euler(0.0, math.radians(30.0), 0.0)
    y[OMEGA] = [0.0, 0.7, 0.0]
    s2d = _s2d(y)
    assert s2d[0] == 1.5
    assert s2d[1] == -2.5
    assert s2d[2] == 3.0
    assert s2d[3] == -4.0
    assert s2d[5] == 0.7
    assert s2d[6] == 0.0

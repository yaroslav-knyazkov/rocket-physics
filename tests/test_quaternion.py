"""Sign-check / algebraic tests for sim/quaternion.py (roadmap.md Step 28).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np

from sim.frames import R_body_to_inertial
from sim.quaternion import (
    conjugate,
    from_euler,
    multiply,
    norm,
    normalise,
    q_dot,
    rotate_vector,
    to_dcm,
    to_euler,
)

IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])


def _q(yaw_deg, pitch_deg, roll_deg):
    return from_euler(
        math.radians(yaw_deg), math.radians(pitch_deg), math.radians(roll_deg)
    )


# ---------------------------------------------------------------------------
# Check 1: Euler round-trip
# ---------------------------------------------------------------------------


def test_euler_roundtrip_away_from_gimbal_lock():
    """euler -> q -> euler recovers the original angles, for several
    non-singular (pitch != +-90 deg) combinations."""
    cases = [
        (0.0, 0.0, 0.0),
        (30.0, 10.0, 0.0),
        (-45.0, 20.0, 15.0),
        (10.0, -30.0, 60.0),
        (170.0, 5.0, -80.0),
        (-120.0, -40.0, 25.0),
    ]
    for yaw_deg, pitch_deg, roll_deg in cases:
        yaw, pitch, roll = (
            math.radians(yaw_deg),
            math.radians(pitch_deg),
            math.radians(roll_deg),
        )
        q = from_euler(yaw, pitch, roll)
        yaw2, pitch2, roll2 = to_euler(q)
        assert np.allclose([yaw, pitch, roll], [yaw2, pitch2, roll2], atol=1e-9)


# ---------------------------------------------------------------------------
# Check 2: pitch-only quaternion reproduces sim/frames.py's
# R_body_to_inertial exactly (the load-bearing check).
# ---------------------------------------------------------------------------


def test_pitch_only_quaternion_matches_2d_R_body_to_inertial():
    """q = (cos(theta/2), 0, sin(theta/2), 0) restricted to the (x, z)
    plane at zero roll/yaw must match sim/frames.py's
    R_body_to_inertial(theta) exactly (architecture.md Phase 3; research
    note SS2)."""
    for theta in (0.0, math.pi / 6, math.pi / 3, math.pi / 2, -math.pi / 4, math.pi):
        q = np.array([math.cos(theta / 2.0), 0.0, math.sin(theta / 2.0), 0.0])
        R_2d = R_body_to_inertial(theta)

        R_3d = to_dcm(q)
        # x-z plane components only: rows/cols 0 (x) and 2 (z) of the 3x3
        # DCM, matching the 2x2 layout of R_body_to_inertial.
        R_3d_xz = R_3d[np.ix_([0, 2], [0, 2])]
        assert np.allclose(R_3d_xz, R_2d)

        # Same check via rotate_vector on the body basis vectors.
        x_hat_i = rotate_vector(q, np.array([1.0, 0.0, 0.0]))
        z_hat_i = rotate_vector(q, np.array([0.0, 0.0, 1.0]))
        expected_x = R_2d @ np.array([1.0, 0.0])
        expected_z = R_2d @ np.array([0.0, 1.0])
        assert np.allclose([x_hat_i[0], x_hat_i[2]], expected_x)
        assert np.allclose([z_hat_i[0], z_hat_i[2]], expected_z)


# ---------------------------------------------------------------------------
# Check 3: associative, not commutative.
# ---------------------------------------------------------------------------


def test_multiply_is_associative_not_commutative():
    q1 = _q(20.0, 10.0, 5.0)
    q2 = _q(-15.0, 40.0, 0.0)
    q3 = _q(60.0, -25.0, 30.0)

    assert np.allclose(multiply(multiply(q1, q2), q3), multiply(q1, multiply(q2, q3)))
    assert not np.allclose(multiply(q1, q2), multiply(q2, q1))


# ---------------------------------------------------------------------------
# Check 4: rotate_vector and the DCM from the same q agree.
# ---------------------------------------------------------------------------


def test_rotate_vector_matches_dcm():
    quaternions = [
        _q(0.0, 0.0, 0.0),
        _q(30.0, 10.0, 0.0),
        _q(-45.0, 20.0, 15.0),
        _q(170.0, 5.0, -80.0),
    ]
    vectors = [
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
        np.array([2.0, -3.0, 5.0]),
    ]
    for q in quaternions:
        R = to_dcm(q)
        for v in vectors:
            assert np.allclose(R @ v, rotate_vector(q, v))


# ---------------------------------------------------------------------------
# Check 5: normalise is a no-op on a unit quaternion; a non-unit quaternion
# normalises to the same rotation.
# ---------------------------------------------------------------------------


def test_normalise_noop_on_unit_quaternion():
    q = _q(25.0, -30.0, 10.0)
    assert np.allclose(norm(q), 1.0)
    assert np.allclose(normalise(q), q)


def test_normalise_nonunit_preserves_rotation():
    q_unit = _q(25.0, -30.0, 10.0)
    v = np.array([1.5, -2.0, 0.5])
    for scale in (2.0, 0.1, 5.0):
        q_scaled = q_unit * scale
        assert not np.allclose(norm(q_scaled), 1.0)
        q_renorm = normalise(q_scaled)
        assert np.allclose(norm(q_renorm), 1.0)
        assert np.allclose(rotate_vector(q_renorm, v), rotate_vector(q_unit, v))


# ---------------------------------------------------------------------------
# Check 6: conjugate(q) * q == identity, for unit q.
# ---------------------------------------------------------------------------


def test_conjugate_times_q_is_identity():
    for q in (
        _q(0.0, 0.0, 0.0),
        _q(20.0, 10.0, 5.0),
        _q(-15.0, 40.0, 0.0),
        _q(60.0, -25.0, 30.0),
    ):
        assert np.allclose(multiply(conjugate(q), q), IDENTITY)
        assert np.allclose(multiply(q, conjugate(q)), IDENTITY)


# ---------------------------------------------------------------------------
# Kinematics: q_dot reduces to the 2D half-angle pitch rate for a pure
# pitch rotation (research note SS2's own stated reduction).
# ---------------------------------------------------------------------------


def test_q_dot_reduces_to_2d_pitch_kinematics():
    theta = math.pi / 5
    omega_y = 0.37  # rad/s, arbitrary nonzero pitch rate
    q = np.array([math.cos(theta / 2.0), 0.0, math.sin(theta / 2.0), 0.0])
    omega_body = np.array([0.0, omega_y, 0.0])

    qd = q_dot(q, omega_body)

    # Research note SS2: q1 and q3 stay at zero (the pure-pitch family
    # (cos(theta/2), 0, sin(theta/2), 0) is preserved), while q0 and q2
    # evolve exactly as d/dt[cos(theta/2)] and d/dt[sin(theta/2)] under
    # dtheta/dt = omega_y -- the half-angle form of the 2D pitch kinematics.
    assert np.allclose(qd[0], -0.5 * math.sin(theta / 2.0) * omega_y)
    assert np.allclose(qd[1], 0.0, atol=1e-12)
    assert np.allclose(qd[2], 0.5 * math.cos(theta / 2.0) * omega_y)
    assert np.allclose(qd[3], 0.0, atol=1e-12)

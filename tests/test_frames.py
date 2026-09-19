"""Sign-check / algebraic tests for sim/frames.py (architecture.md SS2, SS5).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np

from sim.frames import R_body_to_inertial, to_body, to_inertial


def test_R_body_to_inertial_zero_is_identity():
    """theta = 0: body and inertial axes coincide, R(0) == I."""
    assert np.allclose(R_body_to_inertial(0.0), np.eye(2))


def test_R_body_to_inertial_maps_nose_to_up_at_quarter_turn():
    """theta = pi/2 (vertical, nose-up): the body nose axis (1, 0)_b maps to
    inertial (0, -1)_i, i.e. straight up (z is down-positive).
    """
    nose_inertial = to_inertial(np.array([1.0, 0.0]), math.pi / 2)
    assert np.allclose(nose_inertial, np.array([0.0, -1.0]))


def test_R_body_to_inertial_is_orthogonal():
    """R is a rotation matrix, hence orthogonal: R @ R.T == I for any theta."""
    for theta in (0.0, math.pi / 6, math.pi / 3, math.pi / 2, math.pi, -math.pi / 4):
        R = R_body_to_inertial(theta)
        assert np.allclose(R @ R.T, np.eye(2))


def test_to_body_is_inverse_of_to_inertial():
    """Round-trip: to_body(to_inertial(v, theta), theta) == v."""
    vectors = [np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([3.0, -2.5])]
    thetas = (0.0, math.pi / 6, math.pi / 3, math.pi / 2, math.pi)
    for v in vectors:
        for theta in thetas:
            roundtrip = to_body(to_inertial(v, theta), theta)
            assert np.allclose(roundtrip, v)

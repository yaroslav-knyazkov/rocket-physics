"""Sign-check / algebraic tests for sim/flow.py (architecture.md SS15;
main.tex SS"Relative wind and angle of attack"; roadmap.md Step 9).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np

from sim.flow import altitude_agl, altitude_msl, flow_state
from sim.params import Params
from sim.state import State

_P = Params(m=0.5, I=0.05, l1=0.3, l2=0.4)


def test_alpha_zero_when_moving_nose_first():
    """Nose-up (theta = pi/2), climbing straight up (vz < 0, z down-
    positive): the relative wind is purely along the body x-axis, so
    alpha = 0, u_hat = (1, 0), n_hat = (0, 1) -- the Phase 1 axes.
    """
    s = State(x=0.0, z=0.0, vx=0.0, vz=-100.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)

    flow = flow_state(0.0, y, _P)

    assert math.isclose(flow.V, 100.0, rel_tol=1e-12)
    assert math.isclose(flow.alpha, 0.0, abs_tol=1e-12)
    assert np.allclose(flow.u_hat, np.array([1.0, 0.0]))
    assert np.allclose(flow.n_hat, np.array([0.0, 1.0]))


def test_alpha_near_pi_on_tail_first_descent():
    """Same fixed nose-up attitude, but now falling (vz > 0): the relative
    wind now comes from ahead of the nose (flying "backwards" relative to
    the body), so alpha is close to +-pi, not 0 -- the case Step 9 makes
    physical for the first time (roadmap.md Step 9's descent-leg check).
    """
    s = State(x=0.0, z=0.0, vx=0.0, vz=80.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)

    flow = flow_state(0.0, y, _P)

    assert math.isclose(flow.V, 80.0, rel_tol=1e-12)
    assert math.isclose(abs(flow.alpha), math.pi, abs_tol=1e-12)
    assert np.allclose(flow.u_hat, np.array([-1.0, 0.0]), atol=1e-12)
    assert np.allclose(flow.n_hat, np.array([0.0, -1.0]), atol=1e-12)


def test_flow_state_is_internally_consistent_at_nonzero_alpha():
    """Round-trip / reasonableness check for a genuinely 2D relative wind:
    V, alpha reconstruct the original body-frame (u, w), and u_hat/n_hat are
    an orthonormal pair (main.tex: u = V cos alpha, w = V sin alpha).
    """
    theta = 0.4
    s = State(x=0.0, z=0.0, vx=30.0, vz=-10.0, theta=theta, omega=0.0)
    y = np.array(s)

    flow = flow_state(0.0, y, _P)

    # Reconstruct (u, w) from V, alpha and compare to a direct rotation.
    from sim.frames import to_body

    u, w = to_body(np.array([30.0, -10.0]), theta)
    assert math.isclose(flow.V, math.hypot(u, w), rel_tol=1e-12)
    assert math.isclose(flow.V * math.cos(flow.alpha), u, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(flow.V * math.sin(flow.alpha), w, rel_tol=1e-9, abs_tol=1e-9)

    # u_hat, n_hat: unit length, orthogonal, n_hat is +90 degrees from u_hat.
    assert math.isclose(np.linalg.norm(flow.u_hat), 1.0, rel_tol=1e-12)
    assert math.isclose(np.linalg.norm(flow.n_hat), 1.0, rel_tol=1e-12)
    assert math.isclose(np.dot(flow.u_hat, flow.n_hat), 0.0, abs_tol=1e-12)


def test_v_zero_on_the_pad_gives_alpha_zero_no_exception():
    """Degenerate V = 0 case (architecture.md SS15): atan2(0, 0) = 0 in
    Python, no exception, and V/alpha are both exactly zero.
    """
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)

    flow = flow_state(0.0, y, _P)

    assert flow.V == 0.0
    assert flow.alpha == 0.0


def test_altitude_agl_is_minus_z():
    s = State(x=0.0, z=-1650.7, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y = np.array(s)
    assert math.isclose(altitude_agl(y), 1650.7, rel_tol=1e-12)


def test_altitude_msl_falls_back_to_agl_when_h0_m_absent():
    """Params has no h0_m field yet (that's Step 11's site block), so
    altitude_msl must reduce exactly to altitude_agl until it exists
    (architecture.md SS15: 'p.h0_m defaults to 0.0, which makes the two
    identical').
    """
    s = State(x=0.0, z=-500.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y = np.array(s)
    assert altitude_msl(y, _P) == altitude_agl(y)

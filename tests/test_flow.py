"""Sign-check / algebraic tests for sim/flow.py (architecture.md SS15;
main.tex SS"Relative wind and angle of attack"; roadmap.md Step 9).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np

from sim.flow import flow_state
from sim.params import Params
from sim.state import State

# Parameters for existing tests (Step 9)
_P = Params.flat(m=0.5, I=0.05, l1=0.3, l2=0.4)

# Parameters for Step 13 tests (with non-zero reference values)
_P_step13 = Params.flat(
    m=0.5,
    I=0.05,
    l1=0.3,
    l2=0.4,
    l_ref=0.5,   # reference length [m]
    S=0.1,       # reference area [m^2]
    d_ref=0.3,   # reference diameter [m]
    C_A0=0.0,
    C_N_alpha=2.0,
    C_m_alpha=-0.5,
    aero_model="constant",  # we'll test the coefficients model separately
)


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


def test_flow_has_new_fields():
    """Flow object returned by flow_state should have the new fields:
    air, q, M, Re.
    """
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y = np.array(s)

    flow = flow_state(0.0, y, _P_step13)

    # Check that the new fields exist and have the correct types
    assert hasattr(flow, 'air')
    assert hasattr(flow, 'q')
    assert hasattr(flow, 'M')
    assert hasattr(flow, 'Re')

    # Check that air is an AirState (we can check by attribute)
    assert hasattr(flow.air, 'rho')
    assert hasattr(flow.air, 'a')
    assert hasattr(flow.air, 'mu')

    # At zero velocity, q should be zero, M should be zero, Re should be zero (since V=0)
    assert math.isclose(flow.q, 0.0, abs_tol=1e-12)
    assert math.isclose(flow.M, 0.0, abs_tol=1e-12)
    assert math.isclose(flow.Re, 0.0, abs_tol=1e-12)


def test_flow_q_M_Re_nonzero_velocity():
    """At nonzero velocity, q, M, Re should be nonzero and correctly computed."""
    # Choose a state with known velocity and altitude (sea level, ISA)
    s = State(x=0.0, z=0.0, vx=100.0, vz=0.0, theta=0.0, omega=0.0)
    y = np.array(s)

    flow = flow_state(0.0, y, _P_step13)

    # At sea level, ISA: rho ~ 1.225 kg/m^3, a ~ 340.3 m/s, mu ~ 1.789e-5 Pa*s
    # We'll compute expected values using the air state from the flow
    rho = flow.air.rho
    a = flow.air.a
    mu = flow.air.mu
    V = flow.V

    # Dynamic pressure: q = 0.5 * rho * V^2
    expected_q = 0.5 * rho * V**2
    # Mach number: M = V / a
    expected_M = V / a
    # Reynolds number: Re = rho * V * l_ref / mu
    expected_Re = rho * V * _P_step13.l_ref / mu

    assert math.isclose(flow.q, expected_q, rel_tol=1e-9)
    assert math.isclose(flow.M, expected_M, rel_tol=1e-9)
    assert math.isclose(flow.Re, expected_Re, rel_tol=1e-9)


def test_flow_state_with_altitude():
    """Test that air state changes with altitude (density decreases)."""
    # State at sea level
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y0 = np.array(s0)
    flow0 = flow_state(0.0, y0, _P_step13)

    # State at 1000 m altitude (z = -1000 because z is down-positive)
    s1 = State(x=0.0, z=-1000.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y1 = np.array(s1)
    flow1 = flow_state(0.0, y1, _P_step13)

    # Density should be lower at altitude
    assert flow1.air.rho < flow0.air.rho
    # Speed of sound should be lower at altitude (temperature decreases)
    assert flow1.air.a < flow0.air.a
    # Dynamic pressure at zero velocity is zero in both cases
    assert math.isclose(flow0.q, 0.0, abs_tol=1e-12)
    assert math.isclose(flow1.q, 0.0, abs_tol=1e-12)
"""Sign-check / algebraic tests for the pitching-moment terms in
sim/dynamics.py (architecture.md SS2, "Moments need no rotation at all";
roadmap.md Step 6).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np

from sim.dynamics import derivatives
from sim.params import Params
from sim.state import OMEGA, State


def test_thrust_moment_is_zero_on_axis():
    """aB x T is zero: on-axis thrust applied at an on-axis point (aB
    parallel to T = (T, 0)) produces no pitching moment. With A_x = A_z =
    A_m = 0, the only possible moment contribution is from thrust, so
    dydt[OMEGA] must be exactly 0.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, T=50.0, A_x=0.0, A_z=0.0, A_m=0.0)
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)

    dydt = derivatives(0.0, y, p)

    assert dydt[OMEGA] == 0.0


def test_moment_matches_closed_form_l1_Az_minus_Am():
    """architecture.md SS2's "one-line unit test": with the current
    geometry (on-axis thrust), M_y = l1*A_z - A_m exactly. Thrust is zero
    here (t past T_BURN) so it cannot contaminate the check; A_x and theta
    are irrelevant to M_y (A_x and A_m don't interact, and cross_y(aA,
    aero_force_body) only picks up the A_z component since aA has no
    z-component).
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, T=0.0, A_x=1.23, A_z=2.0, A_m=0.5)
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.7, omega=1.5)
    y = np.array(s)

    dydt = derivatives(10.0, y, p)  # t > T_BURN, thrust is zero

    expected_M_y = p.l1 * p.A_z - p.A_m
    assert math.isclose(dydt[OMEGA] * p.I, expected_M_y, rel_tol=1e-12, abs_tol=1e-12)

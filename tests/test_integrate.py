"""Tests for the burnout event added in sim/integrate.py (roadmap.md
Step 14). Physics/numerics sanity checks only, per the project's testing
philosophy -- no fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import math

from sim.integrate import run_sim
from sim.params import Params
from sim.state import State


# data/motors/placeholder.csv burns from t=0 (thrust=0) up through an
# ignition spike, a flat sustain, and a linear tail-off that reaches zero
# exactly at t=2.0 s -- see that file's header comment.
BURNOUT_EXPECTED = 2.0
BURNOUT_TOL = 0.05


def test_rk45_burnout_event_detected():
    """RK45's solve_ivp-based burnout event fires once, at the curve's
    tail-off-to-zero time, and not spuriously at t=0 (the curve starts at
    zero thrust and rises on ignition, which `direction=-1` excludes).
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv")
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(p, s0, method="RK45")

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    assert math.isclose(t_burnout, BURNOUT_EXPECTED, abs_tol=BURNOUT_TOL)


def test_rk4_burnout_event_detected():
    """Same check for the hand-written fixed-step RK4 path (`method="rk4"`),
    which locates the burnout crossing by linear interpolation within the
    one step that straddles it (same approach as apogee/ground there).
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv")
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(p, s0, method="rk4", dt=1e-3)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    assert math.isclose(t_burnout, BURNOUT_EXPECTED, abs_tol=BURNOUT_TOL)


def test_no_burnout_event_when_no_curve():
    """With no motor curve (`motor_curve=""`, thrust is zero throughout),
    thrust never goes from positive to negative, so the burnout event must
    never fire for either integrator.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="")
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    rk45 = run_sim(p, s0, method="RK45", t_max=5.0)
    rk4 = run_sim(p, s0, method="rk4", t_max=5.0, dt=1e-3)

    assert rk45.events["burnout"] is None
    assert rk4.events["burnout"] is None

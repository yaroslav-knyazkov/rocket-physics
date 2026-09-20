"""Test the thrust curve model."""

import math

import numpy as np

from sim.thrust_curve import _load_motor_curve, thrust
from sim.params import Params
from sim.state import State


def test_load_motor_curve():
    """Test loading the placeholder motor curve (ignition spike, settle,
    sustain, tail-off to zero -- see data/motors/placeholder.csv).
    """
    times, thrusts = _load_motor_curve("placeholder.csv")

    assert len(times) == 5
    assert len(thrusts) == 5

    assert np.allclose(times, [0.0, 0.05, 0.1, 1.6, 2.0])
    assert np.allclose(thrusts, [0.0, 150.0, 90.0, 90.0, 0.0])

    # Check that times are sorted
    assert np.all(np.diff(times) > 0)


def test_thrust_curve_shape():
    """Test thrust curve at key points: ignition spike, settle, sustain,
    tail-off, and clean cutoff at burnout.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv")
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

    # Before ignition (should return first point: zero thrust)
    assert thrust(-1.0, s, p) == 0.0

    # Ignition spike, settle, sustained flat burn
    assert thrust(0.0, s, p) == 0.0
    assert thrust(0.05, s, p) == 150.0
    assert thrust(0.1, s, p) == 90.0
    assert thrust(0.8, s, p) == 90.0
    assert thrust(1.6, s, p) == 90.0

    # Tail-off, linear interpolation down to zero at burnout (t=2.0)
    assert math.isclose(thrust(1.8, s, p), 45.0)
    assert thrust(2.0, s, p) == 0.0

    # After burnout (should return 0.0, clean cut)
    assert thrust(2.1, s, p) == 0.0
    assert thrust(10.0, s, p) == 0.0


def test_thrust_curve_total_impulse():
    """Roadmap Step 14 check: the trapezoidal integral of the curve equals
    the motor's stated total impulse (see the header comment in
    data/motors/placeholder.csv).
    """
    times, thrusts = _load_motor_curve("placeholder.csv")
    total_impulse = np.trapezoid(thrusts, times)

    assert math.isclose(total_impulse, 162.75, rel_tol=1e-9)


def test_thrust_zero_when_no_curve():
    """Test that thrust returns zero when no curve is specified."""
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="")  # Empty string
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

    assert thrust(0.0, s, p) == 0.0
    assert thrust(100.0, s, p) == 0.0


def test_thrust_interpolation():
    """Test interpolation with a custom curve."""
    # Create a test curve file
    import os
    test_curve_path = os.path.join(os.path.dirname(__file__), "..", "data", "motors", "test_curve.csv")
    with open(test_curve_path, "w") as f:
        f.write("# Test curve\n")
        f.write("0.0, 0.0\n")
        f.write("1.0, 100.0\n")
        f.write("2.0, 50.0\n")

    try:
        p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="test_curve.csv")
        s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

        # Before first point
        assert thrust(-1.0, s, p) == 0.0  # Returns first point (0.0)

        # Interpolation points
        assert thrust(0.0, s, p) == 0.0
        assert thrust(0.5, s, p) == 50.0  # Midway between 0,0 and 1,100
        assert thrust(1.0, s, p) == 100.0
        assert thrust(1.5, s, p) == 75.0  # Midway between 1,100 and 2,50
        assert thrust(2.0, s, p) == 50.0

        # After last point (should return 0.0)
        assert thrust(2.1, s, p) == 0.0
        assert thrust(3.0, s, p) == 0.0

    finally:
        # Clean up test file
        if os.path.exists(test_curve_path):
            os.remove(test_curve_path)


if __name__ == "__main__":
    test_load_motor_curve()
    test_thrust_curve_shape()
    test_thrust_curve_total_impulse()
    test_thrust_zero_when_no_curve()
    test_thrust_interpolation()
    print("All tests passed!")
"""Test the thrust curve model."""

import math

import numpy as np

from apps.sim.engine.thrust_curve import _load_motor_curve, thrust
from apps.sim.engine.params import Lengths, Params, Thrust, Weight
from apps.sim.engine.state import State
from tests.datadir import MOTORS_DIR


def test_load_motor_curve():
    """Test loading the placeholder motor curve (ignition spike, settle,
    sustain, tail-off to zero -- see examples/data/motors/placeholder.csv).
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
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
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


def test_synthetic_small_total_impulse():
    """Roadmap Step 61 check (architecture-29-motor-selection.md SS29.5):
    the trapezoidal integral of data/motors/synthetic_small.csv equals its
    stated total impulse, 39.75 N*s (Class E)."""
    times, thrusts = _load_motor_curve("synthetic_small.csv")
    assert math.isclose(np.trapezoid(thrusts, times), 39.75, rel_tol=1e-9)


def test_synthetic_medium_punchy_total_impulse():
    """Roadmap Step 61 check: data/motors/synthetic_medium_punchy.csv's
    stated total impulse, 169.2 N*s (Class H) -- the short-burn half of
    the equal-impulse pair."""
    times, thrusts = _load_motor_curve("synthetic_medium_punchy.csv")
    assert math.isclose(np.trapezoid(thrusts, times), 169.2, rel_tol=1e-9)


def test_synthetic_medium_long_total_impulse():
    """Roadmap Step 61 check: data/motors/synthetic_medium_long.csv's
    stated total impulse, 169.54 N*s (Class H) -- within 0.2% of
    synthetic_medium_punchy.csv's impulse, deliberately close but not
    bit-equal (see that fixture's header comment)."""
    times, thrusts = _load_motor_curve("synthetic_medium_long.csv")
    assert math.isclose(np.trapezoid(thrusts, times), 169.54, rel_tol=1e-9)


def test_synthetic_large_total_impulse():
    """Roadmap Step 61 check: data/motors/synthetic_large.csv's stated
    total impulse, 338.0 N*s (Class I)."""
    times, thrusts = _load_motor_curve("synthetic_large.csv")
    assert math.isclose(np.trapezoid(thrusts, times), 338.0, rel_tol=1e-9)


def test_thrust_zero_when_no_curve():
    """Test that thrust returns zero when no curve is specified."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve=""),
    )  # Empty string
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

    assert thrust(0.0, s, p) == 0.0
    assert thrust(100.0, s, p) == 0.0


def test_thrust_interpolation():
    """Test interpolation with a custom curve."""
    # Create a test curve file
    import os
    test_curve_path = os.path.join(MOTORS_DIR, "test_curve.csv")
    with open(test_curve_path, "w") as f:
        f.write("# Test curve\n")
        f.write("0.0, 0.0\n")
        f.write("1.0, 100.0\n")
        f.write("2.0, 50.0\n")

    try:
        p = Params(
            weight=Weight(m=0.5, I=0.05),
            lengths=Lengths(l1=0.3, l2=0.4),
            thrust=Thrust(motor_curve="test_curve.csv"),
        )
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


def test_pressure_correction_inert_at_default_A_e():
    """Roadmap Step 16 check: `A_e = 0.0` (the `Params` default) must
    reproduce Step 14's raw curve lookup bit-for-bit at several time
    points, including a pre-ignition point, several during-burn points
    and a post-burnout point.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

    for t, expected in [
        (-1.0, 0.0),
        (0.0, 0.0),
        (0.05, 150.0),
        (0.1, 90.0),
        (0.8, 90.0),
        (1.6, 90.0),
        (1.8, 45.0),
        (2.0, 0.0),
        (2.1, 0.0),
        (10.0, 0.0),
    ]:
        assert thrust(t, s, p) == expected


def test_pressure_correction_increases_thrust_with_lower_ambient_pressure():
    """Roadmap Step 16 check: with `A_e > 0` and `p_ref` above the ambient
    pressure at the state's altitude, thrust at a non-zero-thrust time
    point is measurably higher than the raw curve value, with the exact
    magnitude given by the formula `T(t,h) = T_ref(t) + A_e*(p_ref -
    p_amb)`. At sea level (z=0, default h0_m=0) the ISA model gives
    `p_amb = 101325.0` Pa exactly, so choosing `p_ref` above that gives a
    known, exact correction to check against -- confirming the sign, not
    just `!=`.
    """
    t = 0.8  # flat-sustain part of the curve: raw T_ref = 90.0 N
    A_e = 0.001  # m^2
    p_ref = 150000.0  # Pa, above the sea-level ambient the curve implies
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv", A_e=A_e, p_ref=p_ref),
    )
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

    raw_thrust = 90.0
    p_amb = 101325.0  # ISA sea-level pressure, exact per the ISA base layer
    expected = raw_thrust + A_e * (p_ref - p_amb)

    corrected = thrust(t, s, p)
    assert corrected > raw_thrust
    assert math.isclose(corrected, expected, rel_tol=1e-9)


def test_pressure_correction_still_zero_after_burnout():
    """Roadmap Step 16 check / SS19 guard: even with `A_e != 0`, thrust
    stays exactly zero after burnout (and before ignition) -- the
    pressure term must not manufacture nonzero thrust once the motor
    isn't actually flowing, since `integrate.py`'s `_burnout_event` and
    Step 14's own check both depend on a clean cut to zero.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv", A_e=0.001, p_ref=150000.0),
    )
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)

    assert thrust(-1.0, s, p) == 0.0
    assert thrust(0.0, s, p) == 0.0
    assert thrust(2.0, s, p) == 0.0
    assert thrust(2.1, s, p) == 0.0
    assert thrust(10.0, s, p) == 0.0


if __name__ == "__main__":
    test_load_motor_curve()
    test_thrust_curve_shape()
    test_thrust_curve_total_impulse()
    test_synthetic_small_total_impulse()
    test_synthetic_medium_punchy_total_impulse()
    test_synthetic_medium_long_total_impulse()
    test_synthetic_large_total_impulse()
    test_thrust_zero_when_no_curve()
    test_thrust_interpolation()
    test_pressure_correction_inert_at_default_A_e()
    test_pressure_correction_increases_thrust_with_lower_ambient_pressure()
    test_pressure_correction_still_zero_after_burnout()
    print("All tests passed!")
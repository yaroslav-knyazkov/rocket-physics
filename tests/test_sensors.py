"""Tests for sim/sensors.py -- the real baro-pressure sensing channel
(Step 108, architecture-35-paper-alignment.md SS35.4.4, D-115,
task-108-sensors-estimator.md SS108.6).

Same "no fixtures, no conftest.py, plain assert" style as
tests/test_atmosphere.py / tests/test_control.py.
"""

import math

import numpy as np
import pytest

from sim import atmosphere, control, gravity, sensors
from sim.params import Params, Sensors, Site, Solver, Weight, with_solver
from sim.state import State


def _y_at_h_msl(h_msl: float) -> np.ndarray:
    """State vector whose AGL == MSL altitude is `h_msl` (default `Site`,
    `h0_m == 0.0`), all other components zero -- only altitude matters to
    sim.sensors.measure."""
    return np.array(State(x=0.0, z=-h_msl, vx=0.0, vz=0.0, theta=0.0, omega=0.0))


def _base_params(**sensor_kw) -> Params:
    return Params(weight=Weight(m=0.5, I=0.05), sensors=Sensors(**sensor_kw))


# ----------------------------------------------------------------------
# Test 1 (§108.6): all-default Sensors(), "isa" tier -- exact inverse
# ----------------------------------------------------------------------


def test_all_default_sensor_reproduces_truth_altitude_exactly_at_first_tick():
    p = _base_params()
    y = _y_at_h_msl(250.0)
    meas, state = sensors.measure(0.0, y, p, None)
    assert meas.h_baro == pytest.approx(gravity.altitude_agl(y, p), abs=1e-9)
    assert state.t_prev == 0.0


def test_all_default_sensor_reproduces_truth_altitude_exactly_at_a_later_tick():
    p = _base_params()
    y1 = _y_at_h_msl(250.0)
    y2 = _y_at_h_msl(400.0)
    meas1, state1 = sensors.measure(0.0, y1, p, None)
    meas2, state2 = sensors.measure(1.0, y2, p, state1)
    assert meas2.h_baro == pytest.approx(gravity.altitude_agl(y2, p), abs=1e-9)


# ----------------------------------------------------------------------
# Test 2 (§108.6): isa_pressure_altitude is the algebraic inverse of
# _isa_air_state's own pressure column, within one layer AND crossing a
# layer boundary.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("h_msl", [0.0, 3000.0, 8000.0, 10900.0, 15000.0, 25000.0])
def test_isa_pressure_altitude_inverts_air_state_pressure(h_msl):
    p = Params(weight=Weight(m=0.5, I=0.05))
    air = atmosphere.air_state(0.0, _y_at_h_msl(h_msl), p)
    assert atmosphere.isa_pressure_altitude(air.p) == pytest.approx(h_msl, abs=1e-6)


# ----------------------------------------------------------------------
# Test 3 (§108.6): noise -- sample std + determinism
# ----------------------------------------------------------------------


def test_noise_sample_std_matches_sigma_and_is_deterministic():
    sigma = 2.0
    sample_rate_hz = 20.0
    n = 5000
    p = with_solver(_base_params(baro_sigma_m=sigma), sample_rate_hz=sample_rate_hz)
    y = _y_at_h_msl(300.0)

    draws = []
    for k in range(n):
        t = k / sample_rate_hz
        meas, _ = sensors.measure(t, y, p, None)
        draws.append(meas.h_baro)
    draws = np.array(draws)
    truth = gravity.altitude_agl(y, p)
    std = np.std(draws - truth)
    assert std == pytest.approx(sigma, rel=0.05)

    # Determinism: the SAME (seed, k) pair reproduces the identical draw.
    meas_a, _ = sensors.measure(3.0 / sample_rate_hz, y, p, None)
    meas_b, _ = sensors.measure(3.0 / sample_rate_hz, y, p, None)
    assert meas_a.h_baro == meas_b.h_baro


# ----------------------------------------------------------------------
# Test 4 (§108.6): first-order lag -- exact analytic step response
# ----------------------------------------------------------------------


def test_lag_step_response_matches_analytic_first_order_form():
    tau = 0.1
    h0, h_in = 100.0, 150.0
    dt = 0.01
    p = _base_params(baro_tau_s=tau)
    y_in = _y_at_h_msl(h_in)

    prev = sensors.SensorState(t_prev=0.0, h_lag_prev=h0)
    for n in range(1, 50):
        t = n * dt
        meas, prev = sensors.measure(t, y_in, p, prev)
        expected = h_in - (h_in - h0) * math.exp(-t / tau)
        assert meas.h_baro == pytest.approx(expected, rel=1e-9)


def test_lag_out_of_order_tick_holds_previous_estimate_instead_of_overflowing():
    """Found during this ticket's own code-review pass: a repeated/out-of-
    order tick (`dt <= 0.0`) must not feed a large positive argument into
    `math.exp` (OverflowError) -- same "hold the previous estimate
    unchanged" guard controllers/estimator.py's `_step_alpha_beta` already
    uses for the identical class of input."""
    p = _base_params(baro_tau_s=0.01)  # a small tau makes -dt/tau large for any dt < 0
    y = _y_at_h_msl(500.0)
    prev = sensors.SensorState(t_prev=10.0, h_lag_prev=123.0)
    meas, new_state = sensors.measure(0.0, y, p, prev)  # t < prev.t_prev: dt == -10.0
    assert meas.h_baro == pytest.approx(123.0, abs=1e-9)
    assert new_state.h_lag_prev == pytest.approx(123.0, abs=1e-9)


def test_lag_zero_tau_is_inert_regardless_of_prev():
    """baro_tau_s <= 0.0 (the default, 0.0) skips the lag branch entirely
    -- even with a `prev` carrying a stale `h_lag_prev`, the reading is
    the instantaneous truth."""
    p = _base_params(baro_tau_s=0.0)
    y = _y_at_h_msl(123.0)
    prev = sensors.SensorState(t_prev=0.0, h_lag_prev=999.0)
    meas, _ = sensors.measure(1.0, y, p, prev)
    assert meas.h_baro == pytest.approx(gravity.altitude_agl(y, p), abs=1e-9)


# ----------------------------------------------------------------------
# Test 5 (§108.6): quantisation
# ----------------------------------------------------------------------


def test_quantisation_rounds_to_an_exact_multiple_of_resolution():
    resolution = 0.5
    p = _base_params(baro_resolution_m=resolution)
    prev = None
    for h in (12.3, 45.678, 200.01, 999.9):
        y = _y_at_h_msl(h)
        meas, prev = sensors.measure(0.0, y, p, prev)
        ratio = meas.h_baro / resolution
        assert ratio == pytest.approx(round(ratio), abs=1e-9)


# ----------------------------------------------------------------------
# Test 6 (§108.6): all three effects composed -- smoke test only
# ----------------------------------------------------------------------


def test_all_three_effects_composed_smoke_test():
    sample_rate_hz = 10.0
    p = with_solver(
        _base_params(baro_sigma_m=1.5, baro_tau_s=0.2, baro_resolution_m=0.25),
        sample_rate_hz=sample_rate_hz,
    )
    y = _y_at_h_msl(500.0)
    truth = gravity.altitude_agl(y, p)
    prev = None
    for k in range(50):
        t = k / sample_rate_hz
        meas, prev = sensors.measure(t, y, p, prev)
        assert math.isfinite(meas.h_baro)
        assert abs(meas.h_baro - truth) < 20.0  # generous bound: a few sigma + lag transient


# ----------------------------------------------------------------------
# Test 7 (§108.6): _in_coast_window gating via sample_airbrake --
# sens_state frozen outside the coast window.
# ----------------------------------------------------------------------


def test_sample_airbrake_freezes_sens_state_outside_coast_window():
    from sim.params import Aero, Control, Lengths, Thrust

    assert "test_s108_dummy" not in control.known_sampled_laws()
    control.register_sampled_law("test_s108_dummy", lambda t_k, meas, p, state: (0.0, state))
    try:
        p = Params(
            weight=Weight(m=0.5, I=0.05), lengths=Lengths(l1=0.3, l2=0.4),
            aero=Aero(S=0.005, d_ref=0.08, C_x=0.5), thrust=Thrust(motor_curve="placeholder.csv"),
            control=Control(airbrake_model="test_s108_dummy"),
            solver=Solver(sample_rate_hz=10.0, method="rk4"),
        )
        y = np.array(State(x=0.0, z=0.0, vx=0.0, vz=-10.0, theta=math.pi / 2, omega=0.0))
        # Still under power: _in_coast_window is False.
        hold1 = control.sample_airbrake(0.1, y, p, None)
        assert isinstance(hold1, control.SampledLawHold)
        assert hold1.sens_state is None

        hold2 = control.sample_airbrake(0.2, y, p, hold1)
        assert hold2.sens_state is None  # still frozen (still under power)
    finally:
        del control._SAMPLED_LAWS["test_s108_dummy"]

"""Step 98 (Phase 2.17, architecture-35 SS35.4.2, D-112): stand thrust T_0,
mass flow from the stand curve, impulse/time scatter (`Thrust.k_J`,
`Thrust.k_t`) and `Motor.d_exit` -> `Thrust.A_e`.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from configs.schema import Airframe, LaunchSite, Motor, Rocket, Scenario, Weather
from apps.sim.engine import thrust_curve
from apps.sim.engine.dynamics import derivatives
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Aero, Lengths, Params, Thrust, Weight, with_solver
from apps.sim.engine.state import M, State

_CURVES = ["placeholder.csv", "Cesaroni_2060K570-17A.eng"]
_G0 = 9.80665


def _p(curve="placeholder.csv", **thrust_kw) -> Params:
    return Params(
        weight=Weight(m=1.0, I=0.05, m_d=0.5, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=200.0),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve=curve, **thrust_kw),
    )


def _grid(curve):
    times, _ = thrust_curve._load_motor_curve(curve)
    return np.linspace(0.0, 1.5 * times[-1], 300001), times[-1]


@pytest.mark.parametrize("curve", _CURVES)
def test_defaults_are_bit_identical_to_raw_curve_lookup(curve):
    p = _p(curve)
    times, thrusts = thrust_curve._load_motor_curve(curve)
    for t in np.linspace(0.0, times[-1] * 1.2, 57):
        raw = float(np.interp(t, times, thrusts, left=thrusts[0], right=0.0))
        assert thrust_curve.thrust(t, None, p) == raw
        assert thrust_curve.thrust_stand(t, p) == raw
        assert thrust_curve.mass_flow(t, p) == -raw / (p.weight.I_sp * p.g0)


@pytest.mark.parametrize("curve", _CURVES)
@pytest.mark.parametrize("k_J", [0.9, 1.0, 1.1])
@pytest.mark.parametrize("k_t", [0.9, 1.0, 1.1])
def test_impulse_burnout_time_and_burned_mass(curve, k_J, k_t):
    p = _p(curve, k_J=k_J, k_t=k_t)
    ts, t_b = _grid(curve)
    stand = np.array([thrust_curve.thrust_stand(t, p) for t in ts[::10]])
    flow = np.array([thrust_curve.mass_flow(t, p) for t in ts[::10]])
    _times, thrusts = thrust_curve._load_motor_curve(curve)
    J = float(np.trapezoid(thrusts, _times))
    tt = ts[::10]
    assert math.isclose(float(np.trapezoid(stand, tt)), k_J * J, rel_tol=1e-4)
    # burned mass is independent of k_J, scaled by nothing: m_prop = J/(I_sp g0)
    assert math.isclose(-float(np.trapezoid(flow, tt)), J / (200.0 * _G0), rel_tol=1e-4)
    # burnout at k_t * t_b
    assert thrust_curve.thrust_stand(0.99 * k_t * t_b, p) > 0.0
    assert thrust_curve.thrust_stand(1.01 * k_t * t_b, p) == 0.0


def test_stand_curve_amplitude_scales_with_k_J():
    p = _p(k_J=1.1)
    p0 = _p()
    assert math.isclose(thrust_curve.thrust_stand(1.0, p), 1.1 * thrust_curve.thrust_stand(1.0, p0), rel_tol=1e-12)
    p2 = _p(k_J=1.1, k_t=1.1)  # amplitude k_J/k_t = 1 at the time-scaled point
    assert math.isclose(thrust_curve.thrust_stand(1.1, p2), thrust_curve.thrust_stand(1.0, p0), rel_tol=1e-12)


def test_simulated_burn_reaches_dry_mass_for_scatter():
    m_d = 0.5
    J = 162.75
    m_prop = 0.3
    I_sp = J / (m_prop * _G0)
    for k_J, k_t in [(0.9, 1.1), (1.1, 0.9), (1.0, 1.0)]:
        p = with_solver(
            Params(
                weight=Weight(m=m_d + m_prop, I=0.0, m_d=m_d, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=I_sp),
                lengths=Lengths(l1=0.3, l2=0.4),
                thrust=Thrust(motor_curve="placeholder.csv", k_J=k_J, k_t=k_t),
                aero=Aero(S=0.005, d_ref=0.08, C_x=0.5),
            ),
            t_max=30.0,
        )
        s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=m_d + m_prop)
        r = run_sim(p, s0)
        ys = r.raw.sol(np.linspace(0.0, r.t[-1], 2001))
        assert math.isclose(ys[M][-1], m_d, abs_tol=1e-4)


def test_mass_flow_independent_of_altitude_and_A_e_while_thrust_changes():
    base = _p(A_e=0.0)
    nozzle = _p(A_e=0.002, p_ref=101325.0)
    t = 1.0
    lo = np.array(State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=0.9))
    hi = np.array(State(x=0.0, z=-8000.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=0.9))
    assert thrust_curve.mass_flow(t, base) == thrust_curve.mass_flow(t, nozzle)
    assert derivatives(t, lo, nozzle)[M] == derivatives(t, hi, nozzle)[M] == derivatives(t, lo, base)[M]
    assert thrust_curve.thrust(t, hi, nozzle) > thrust_curve.thrust(t, lo, nozzle) > thrust_curve.thrust(t, lo, base) - 1e-9


# ----------------------------------------------------------------------
# Motor.d_exit -> Thrust.A_e
# ----------------------------------------------------------------------


def _scenario(motor: Motor) -> Scenario:
    return Scenario(
        name="d_exit_test",
        rocket=Rocket(name="rocket", airframe=Airframe(m=1.0, I=0.01)),
        motor=motor,
        site=LaunchSite(name="site"),
        weather=Weather(name="weather"),
    )


def test_d_exit_maps_to_A_e():
    m = Motor(name="m", thrust=Thrust(motor_curve="placeholder.csv"), d_exit=0.05)
    assert math.isclose(_scenario(m).config.params.thrust.A_e, math.pi / 4 * 0.05**2, rel_tol=1e-15)


def test_d_exit_none_leaves_thrust_untouched():
    th = Thrust(motor_curve="placeholder.csv", A_e=0.001)
    m = Motor(name="m", thrust=th)
    assert m.d_exit is None
    assert _scenario(m).config.params.thrust == th


def test_d_exit_and_nonzero_A_e_conflict():
    m = Motor(name="m", thrust=Thrust(motor_curve="placeholder.csv", A_e=0.001), d_exit=0.05)
    with pytest.raises(ValueError):
        _scenario(m).config

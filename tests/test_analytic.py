"""Step 97 (Phase 2.17): analytic regression suite + B32 bug-fix tests.

Closed-form oracles (vacuum shot, drag-only coast, canopy terminal speed)
and the four B32 fixes: mass floor at `m_d` (G5), Coriolis under canopy
exactly once (G19), air-brake `after_apogee` 0.1 s pad guard (C1), and the
Reynolds-length fallback `l_ref == 0 -> d_ref` (C2, D-118 option c).

Sign convention: `z` points down, so a rising rocket has `vz < 0`.
"""

import math

import numpy as np

from apps.sim.engine import control, forces
from apps.sim.engine.atmosphere import air_state
from apps.sim.engine.dynamics import derivatives
from apps.sim.engine.flow import flow_state
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import (
    Aero, Control, Gravity, Lengths, Params, Recovery, Site, Thrust, Weight, with_solver,
)
from apps.sim.engine.rotation import coriolis_inplane
from apps.sim.engine.state import M, VX, VZ, State, Z

_LENGTHS = Lengths(l1=0.3, l2=0.4)


def _apogee_height(r) -> float:
    ts = np.linspace(0.0, r.t[-1], 20001)
    return float(-np.min(r.raw.sol(ts)[Z]))


# ----------------------------------------------------------------------
# Analytic oracles
# ----------------------------------------------------------------------


def test_vacuum_vertical_shot_apogee_is_v0_squared_over_2g():
    """No thrust, no drag (C_x = 0), constant gravity: h = v0^2/(2 g)."""
    v0 = 50.0
    p = with_solver(
        Params(weight=Weight(m=1.0, I=0.05), lengths=_LENGTHS, aero=Aero(C_x=0.0)),
        t_max=30.0,
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-v0, theta=math.pi / 2, omega=0.0)
    r = run_sim(p, s0)
    assert math.isclose(_apogee_height(r), v0**2 / (2.0 * p.g0), rel_tol=1e-6)


def test_drag_only_coast_matches_closed_form_within_one_percent():
    """Constant C_x, constant mass, no thrust: with F_d = k v^2,
    k = 0.5 rho S C_x, the apogee is h = (m/2k) ln(1 + k v0^2/(m g)).
    The closed form assumes constant rho; the rise is ~65 m, over which the
    ISA density drops by <1% (scale height ~8.4 km) and the apogee depends
    on rho only logarithmically, so the expected error is well below the
    1% tolerance (sea-level rho is used in the oracle).
    """
    m, v0, S, Cx = 1.0, 40.0, 0.005, 1.0
    p = with_solver(
        Params(
            weight=Weight(m=m, I=0.05), lengths=_LENGTHS,
            aero=Aero(S=S, d_ref=0.08, C_x=Cx, C_z=0.0, C_m=0.0),
        ),
        t_max=30.0,
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-v0, theta=math.pi / 2, omega=0.0)
    r = run_sim(p, s0)

    rho0 = air_state(0.0, np.array(s0), p).rho
    k = 0.5 * rho0 * S * Cx
    expected = (m / (2.0 * k)) * math.log(1.0 + k * v0**2 / (m * p.g0))
    assert math.isclose(_apogee_height(r), expected, rel_tol=0.01)


def test_canopy_terminal_speed_within_one_percent():
    m, Cd, v_t = 2.0, 0.8, 10.0
    S = 2.0 * m * 9.80665 / (1.225 * Cd * v_t**2)
    p = with_solver(
        Params(
            weight=Weight(m=m, I=0.05), lengths=_LENGTHS,
            recovery=Recovery(model="deploy", trigger="timer", deploy_time=0.0, Cd=Cd, S=S),
        ),
        t_max=20.0,
    )
    s0 = State(x=0.0, z=-400.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    r = run_sim(p, s0)
    t = 8.0  # ~8 time constants (v_t/g ~ 1 s)
    y = r.raw.sol(t)
    assert -y[Z] > 100.0
    rho = air_state(t, y, p).rho
    assert math.isclose(y[VZ], math.sqrt(2.0 * m * p.g0 / (rho * Cd * S)), rel_tol=0.01)


# ----------------------------------------------------------------------
# G5: mass floor
# ----------------------------------------------------------------------


def test_mass_never_below_dry_mass_for_too_low_isp():
    """I_sp = 20 s on the placeholder curve (162.75 N*s) would burn
    ~0.83 kg, but only 0.3 kg of propellant is loaded: y[M] must stop at
    m_d (no negative propellant mass, no NaN downstream)."""
    m_d, m_p = 0.5, 0.3
    p = with_solver(
        Params(
            weight=Weight(m=m_d + m_p, I=0.0, m_d=m_d, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=20.0),
            lengths=_LENGTHS,
            thrust=Thrust(motor_curve="placeholder.csv"),
            aero=Aero(S=0.005, d_ref=0.08, C_x=0.5),
        ),
        t_max=60.0,
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=m_d + m_p)
    r = run_sim(p, s0)
    ts = np.linspace(0.0, r.t[-1], 4001)
    ys = r.raw.sol(ts)
    assert np.all(np.isfinite(ys))
    # The branch `dm_dt = 0` at `y[M] <= m_d` is a kink: the adaptive step
    # that crosses it overshoots by a solver sliver (measured ~1.3e-7 kg,
    # vs ~0.5 kg of unfloored over-burn); 1e-5 kg bounds that sliver.
    assert ys[M].min() >= m_d - 1e-5
    assert math.isclose(ys[M][-1], m_d, abs_tol=1e-5)


# ----------------------------------------------------------------------
# G19: Coriolis under canopy exactly once
# ----------------------------------------------------------------------


def _chute_params(earth_rotation: bool) -> Params:
    return Params(
        weight=Weight(m=2.0, I=0.05), lengths=_LENGTHS,
        gravity=Gravity(earth_rotation=earth_rotation),
        site=Site(lat0_deg=50.0, azimuth_deg=90.0),
        recovery=Recovery(model="deploy", trigger="timer", deploy_time=0.0, Cd=0.8, S=0.5),
    )


def test_coriolis_included_once_under_canopy():
    s = np.array(State(x=0.0, z=-1000.0, vx=30.0, vz=10.0, theta=math.pi / 2, omega=0.0))
    p_off, p_on = _chute_params(False), _chute_params(True)
    assert forces.parachute_deployed(0.0, s, p_on)

    d_off = derivatives(0.0, s, p_off)
    d_on = derivatives(0.0, s, p_on)

    # flag off: bit-identical legacy expression (F_i + F_chute) / m
    F_chute = forces.parachute_drag_inertial(0.0, s, p_off, None)
    legacy = (forces.weight_inertial(0.0, s, p_off) + F_chute) / p_off.weight.m
    assert np.array_equal(np.array([d_off[VX], d_off[VZ]]), legacy)

    # flag on: legacy + exactly one Coriolis term
    cor = coriolis_inplane(0.0, s, p_on)
    assert np.any(cor != 0.0)
    assert np.allclose(np.array([d_on[VX], d_on[VZ]]), legacy + cor, rtol=1e-12, atol=1e-15)


# ----------------------------------------------------------------------
# C1: after_apogee pad guard
# ----------------------------------------------------------------------


def test_after_apogee_trigger_requires_t_at_least_0_1():
    p = Params(
        weight=Weight(m=1.0, I=0.05), lengths=_LENGTHS,
        control=Control(airbrake_trigger="after_apogee"),
    )
    y = np.zeros(7)
    y[VZ] = 1.0  # falling
    assert not control.airbrake_triggered(0.0, y, p)
    assert not control.airbrake_triggered(0.05, y, p)
    assert control.airbrake_triggered(0.1, y, p)
    assert control.airbrake_triggered(5.0, y, p)
    y[VZ] = -1.0  # still rising
    assert not control.airbrake_triggered(5.0, y, p)


# ----------------------------------------------------------------------
# C2: Reynolds length fallback (D-118 option c)
# ----------------------------------------------------------------------


def _re(l_ref: float) -> tuple[float, float, float, float]:
    p = Params(
        weight=Weight(m=0.5, I=0.05), lengths=_LENGTHS,
        aero=Aero(l_ref=l_ref, d_ref=0.3, S=0.1),
    )
    y = np.array(State(x=0.0, z=0.0, vx=100.0, vz=0.0, theta=0.0, omega=0.0))
    f = flow_state(0.0, y, p)
    return f.Re, f.air.rho, f.V, f.air.mu


def test_reynolds_falls_back_to_d_ref_when_l_ref_is_zero():
    Re, rho, V, mu = _re(0.0)
    assert math.isclose(Re, rho * V * 0.3 / mu, rel_tol=1e-12)


def test_reynolds_honours_nonzero_l_ref():
    Re, rho, V, mu = _re(0.5)
    assert math.isclose(Re, rho * V * 0.5 / mu, rel_tol=1e-12)

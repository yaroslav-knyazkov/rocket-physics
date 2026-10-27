"""Tests for Step 109 (task-109-roll-reaction-wheel.md): the decoupled 2D
roll degree of freedom and its reaction wheel.

Written test-first (`tdd` skill): every test below targets a public
contract stated in the ticket (sim.state.width/to_vector, sim.roll's eight
public functions, sim.dynamics.derivatives' roll block, sim.integrate.
run_sim's eager validation) rather than an implementation detail.
"""

import math

import numpy as np
import pytest

from sim import roll
from sim.dynamics import derivatives, on_rail
from sim.flow import flow_state
from sim.frames import to_inertial
from sim.integrate import run_sim
from sim.params import Aero, Lengths, Params, Roll, Site, Solver, Weight
from sim.state import (
    GAMMA,
    OMEGA_W,
    OMEGA_X,
    State,
    THETA,
    VX,
    VZ,
    X,
    Z,
    to_vector,
    width,
)


# ----------------------------------------------------------------------
# Shared builders
# ----------------------------------------------------------------------


def _base_params(roll_group=Roll(), **overrides) -> Params:
    """A minimal, valid `Params`: nonzero weight/lengths, zero aero force
    (S=0.0) unless a test overrides `aero`, so the translational dynamics
    reduce to plain gravity and never interfere with the roll channel
    (the whole point of the decoupling, task-109 SS109.1.4)."""
    aero = overrides.pop("aero", Aero(S=0.0, d_ref=0.075))
    return Params(
        weight=Weight(m=1.0, I=0.1),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=aero,
        roll=roll_group,
        **overrides,
    )


def _rest_state(**roll_kw) -> State:
    """At rest, nose up, well above the ground so no run in this file hits
    the ground-impact event before `t_max` (z is DOWN-positive)."""
    return State(x=0.0, z=-2000.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, **roll_kw)


def _e_rail(rail_angle_deg: float) -> np.ndarray:
    """Same construction as `dynamics._e_rail` (private) -- recomputed here
    from the public `to_inertial` rather than reaching into the module's
    private helper."""
    return to_inertial(np.array([1.0, 0.0]), math.radians(rail_angle_deg))


# ----------------------------------------------------------------------
# 1-3: the width gate
# ----------------------------------------------------------------------


def test_width_gate():
    p_off = _base_params(Roll(model="none"))
    p_free = _base_params(Roll(model="free", I_x=0.02))
    p_wheel = _base_params(Roll(model="wheel", I_x=0.02, I_w=2e-4))
    assert width(p_off) == 7
    assert width(p_free) == 10
    assert width(p_wheel) == 10


def test_to_vector_trims_roll_when_off():
    s = State(x=1.0, z=2.0, vx=3.0, vz=4.0, theta=5.0, omega=6.0, m=7.0,
              gamma=1.0, omega_x=2.0, omega_w=3.0)
    p_off = _base_params(Roll(model="none"))
    p_on = _base_params(Roll(model="wheel", I_x=0.02, I_w=2e-4))

    v_off = to_vector(s, p_off)
    assert v_off.shape == (7,)
    assert np.array_equal(v_off, np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]))

    v_on = to_vector(s, p_on)
    assert v_on.shape == (10,)
    assert np.array_equal(v_on, np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 1.0, 2.0, 3.0]))


def test_derivatives_width_follows_params():
    p_off = _base_params(Roll(model="none"))
    p_on = _base_params(Roll(model="wheel", I_x=0.02, I_w=2e-4, law="rate_null", kd=0.01))
    y_off = to_vector(_rest_state(), p_off)
    y_on = to_vector(_rest_state(omega_x=0.1), p_on)
    assert derivatives(0.0, y_off, p_off).shape == (7,)
    assert derivatives(0.0, y_on, p_on).shape == (10,)


# ----------------------------------------------------------------------
# 4: momentum exchange -- the primary physics check (SS109.10.1)
# ----------------------------------------------------------------------


def test_momentum_exchange_from_rest():
    """eq:roll_exchange: with C_l = C_l_p = 0 and the vehicle starting at
    rest, I_x*omega_x + h_w is conserved at its initial value (0) for the
    whole flight -- a property of the exact ODE, so the only error is the
    integrator's."""
    I_x, I_w = 0.02, 2e-4
    p = _base_params(Roll(
        model="wheel", I_x=I_x, I_w=I_w, law="angle_hold",
        kp=0.01, kd=0.002, gamma_cmd=0.5,
    ), solver=Solver(t_max=3.0))
    s0 = _rest_state()

    result = run_sim(p, s0)
    gamma = result.y[GAMMA]
    omega_x = result.y[OMEGA_X]
    omega_w = result.y[OMEGA_W]
    h_w = I_w * (omega_w - omega_x)
    total = I_x * omega_x + h_w

    assert np.max(np.abs(total)) <= 1e-9

    # Opposite signs once the wheel has spun up meaningfully (skip the
    # near-zero transient right at t=0).
    significant = np.abs(h_w) > 1e-6
    assert np.any(significant)
    assert np.all(np.sign(omega_x[significant]) == -np.sign(h_w[significant]))
    # gamma actually moved towards gamma_cmd (sanity: the law is doing something)
    assert gamma[-1] != 0.0


# ----------------------------------------------------------------------
# 5: law "none" + zero initial roll -> exactly zero throughout
# ----------------------------------------------------------------------


def test_no_law_no_roll():
    p = _base_params(Roll(model="wheel", I_x=0.02, I_w=2e-4, law="none"),
                      solver=Solver(t_max=2.0))
    s0 = _rest_state()
    result = run_sim(p, s0)
    assert np.all(result.y[GAMMA] == 0.0)
    assert np.all(result.y[OMEGA_X] == 0.0)
    assert np.all(result.y[OMEGA_W] == 0.0)


# ----------------------------------------------------------------------
# 6: decoupling, demonstrated under rk4 (SS109.10.4) -- the subtle one.
# RK45's error norm is an RMS over the state vector (SS109.2.1), so the
# 7-wide and 10-wide runs take DIFFERENT adaptive steps even though the
# underlying ODE for rows 0-6 is identical; only a FIXED-step integrator
# (rk4) makes the two runs bit-identical, because every RK4 stage computes
# rows 0-6 from rows 0-6 alone, never touching rows 7-9.
# ----------------------------------------------------------------------


def test_roll_does_not_perturb_the_other_seven():
    solver = Solver(method="rk4", dt=0.01, t_max=2.0)
    p_off = _base_params(Roll(model="none"), solver=solver)
    p_on = _base_params(
        Roll(model="wheel", I_x=0.02, I_w=2e-4, law="rate_null", kd=0.01),
        solver=solver,
    )
    s0 = State(x=0.0, z=-2000.0, vx=50.0, vz=-80.0, theta=math.pi / 2, omega=0.0,
               gamma=0.3, omega_x=0.5, omega_w=1.0)

    r_off = run_sim(p_off, s0)
    r_on = run_sim(p_on, s0)

    assert r_off.y.shape[0] == 7
    assert r_on.y.shape[0] == 10
    assert np.array_equal(r_off.y, r_on.y[:7])


# ----------------------------------------------------------------------
# 7-8: wheel speed saturation, one-sided
# ----------------------------------------------------------------------


def test_wheel_speed_saturation():
    omega_w_max = 5.0
    p = _base_params(Roll(
        model="wheel", I_x=0.02, I_w=2e-4, law="angle_hold",
        kp=1.0, kd=0.0, gamma_cmd=10.0, omega_w_max=omega_w_max,
    ), solver=Solver(t_max=3.0))
    s0 = _rest_state()
    result = run_sim(p, s0)

    omega_rel = result.y[OMEGA_W] - result.y[OMEGA_X]
    assert np.all(np.abs(omega_rel) <= omega_w_max + 1e-6)
    assert np.max(np.abs(omega_rel)) >= omega_w_max - 1e-3  # the limit IS reached

    # Once saturated, omega_x stops growing: find the first sample at the
    # limit and check it stays flat afterward.
    hit = np.argmax(np.abs(omega_rel) >= omega_w_max - 1e-3)
    omega_x_after = result.y[OMEGA_X][hit:]
    assert np.max(omega_x_after) - np.min(omega_x_after) < 1e-5


def test_wheel_speed_clamp_is_one_sided():
    omega_w_max = 5.0
    p = _base_params(Roll(
        model="wheel", I_x=0.02, I_w=2e-4, law="rate_null", kd=0.01,
        omega_w_max=omega_w_max,
    ))

    # A positive command (omega_x > 0, kd > 0) at the +limit must be zeroed.
    y_pos = np.zeros(10)
    y_pos[OMEGA_X] = 1.0
    y_pos[OMEGA_W] = y_pos[OMEGA_X] + omega_w_max
    assert roll.wheel_torque(0.0, y_pos, p) == 0.0

    # A negative command (omega_x < 0, kd > 0) at the SAME +limit must pass
    # through unclamped -- the wheel can always be braked back (SS109.1.3).
    y_neg = np.zeros(10)
    y_neg[OMEGA_X] = -1.0
    y_neg[OMEGA_W] = y_neg[OMEGA_X] + omega_w_max
    tau = roll.wheel_torque(0.0, y_neg, p)
    assert tau == p.roll.kd * y_neg[OMEGA_X]
    assert tau != 0.0


# ----------------------------------------------------------------------
# 9: torque clamp
# ----------------------------------------------------------------------


def test_torque_clamp():
    tau_max = 1e-4
    p = _base_params(Roll(
        model="wheel", I_x=0.02, I_w=2e-4, law="rate_null", kd=10.0, tau_max=tau_max,
    ))
    for omega_x in (-50.0, -1.0, 0.0, 1.0, 50.0):
        y = np.zeros(10)
        y[OMEGA_X] = omega_x
        tau = roll.wheel_torque(0.0, y, p)
        assert abs(tau) <= tau_max + 1e-15


# ----------------------------------------------------------------------
# 10: rate_null despins, conserving total momentum
# ----------------------------------------------------------------------


def test_rate_null_despins():
    I_x, I_w = 0.02, 2e-4
    p = _base_params(Roll(
        model="wheel", I_x=I_x, I_w=I_w, law="rate_null", kd=0.05,
    ), solver=Solver(t_max=3.0))
    s0 = _rest_state(omega_x=2.0)

    result = run_sim(p, s0)
    omega_x = result.y[OMEGA_X]
    omega_w = result.y[OMEGA_W]
    h_x = I_x * omega_x + I_w * (omega_w - omega_x)

    assert np.max(np.abs(h_x - h_x[0])) <= 1e-9
    abs_omega_x = np.abs(omega_x)
    # Monotonically decreasing (allow tiny numerical noise).
    assert np.all(np.diff(abs_omega_x) <= 1e-9)
    assert abs_omega_x[-1] < abs_omega_x[0]


# ----------------------------------------------------------------------
# 11: "free" model has no wheel
# ----------------------------------------------------------------------


def test_free_model_has_no_wheel_damping():
    p = _base_params(
        Roll(model="free", I_x=0.02),
        aero=Aero(S=0.005, d_ref=0.075, C_l=0.0, C_l_p=0.5),
    )
    y = np.zeros(10)
    y[VX] = 100.0
    y[Z] = -1000.0
    y[THETA] = math.pi / 2
    y[OMEGA_X] = 1.0

    assert roll.wheel_torque(0.0, y, p) == 0.0

    flow = flow_state(0.0, y, p)
    d_gamma, d_omega_x, d_omega_w = roll.derivatives_roll(0.0, y, p, flow)
    assert d_omega_w == 0.0
    assert d_omega_x < 0.0  # damps a positive roll rate towards zero


# ----------------------------------------------------------------------
# 12: division-free aero roll moment at zero airspeed
# ----------------------------------------------------------------------


def test_roll_damping_finite_at_zero_airspeed():
    p = _base_params(Roll(model="free", I_x=0.02),
                      aero=Aero(S=0.005, d_ref=0.075, C_l=0.0, C_l_p=0.5))
    y = np.zeros(10)
    y[Z] = -1000.0
    y[THETA] = math.pi / 2
    y[OMEGA_X] = 3.0
    flow = flow_state(0.0, y, p)
    assert flow.V == 0.0
    L_x = roll.aero_moment_x(0.0, y, p, flow)
    assert np.isfinite(L_x)
    assert L_x == 0.0  # q == 0 at V == 0, so the whole moment is exactly 0


# ----------------------------------------------------------------------
# 13: the rail freezes roll but not the wheel
# ----------------------------------------------------------------------


def test_rail_freezes_roll_but_not_the_wheel():
    p = _base_params(
        Roll(model="wheel", I_x=0.02, I_w=2e-4, law="rate_null", kd=0.05),
        site=Site(L_rail=5.0, rail_angle_deg=90.0),
    )

    y_on_rail = np.zeros(10)
    y_on_rail[THETA] = math.pi / 2
    y_on_rail[OMEGA_X] = 1.0
    assert on_rail(y_on_rail, p)
    dydt_on = derivatives(0.5, y_on_rail, p)
    assert dydt_on[GAMMA] == 0.0
    assert dydt_on[OMEGA_X] == 0.0
    assert dydt_on[OMEGA_W] != 0.0

    e_rail = _e_rail(90.0)
    pos = e_rail * (p.site.L_rail + 10.0)
    y_off_rail = np.zeros(10)
    y_off_rail[X], y_off_rail[Z] = pos
    y_off_rail[THETA] = math.pi / 2
    y_off_rail[OMEGA_X] = 1.0
    assert not on_rail(y_off_rail, p)
    dydt_off = derivatives(0.5, y_off_rail, p)
    assert dydt_off[GAMMA] != 0.0
    assert dydt_off[OMEGA_X] != 0.0
    assert dydt_off[OMEGA_W] != 0.0


# ----------------------------------------------------------------------
# 14: run_sim's eager validation
# ----------------------------------------------------------------------


def test_run_sim_rejects_bad_roll_config():
    s0 = _rest_state()

    p_bad_model = _base_params(Roll(model="bogus"))
    with pytest.raises(ValueError):
        run_sim(p_bad_model, s0)

    p_bad_law = _base_params(Roll(model="wheel", I_x=0.02, I_w=2e-4, law="bogus"))
    with pytest.raises(ValueError):
        run_sim(p_bad_law, s0)

    p_bad_inertia = _base_params(Roll(model="wheel", I_x=1e-4, I_w=2e-4))
    with pytest.raises(ValueError):
        run_sim(p_bad_inertia, s0)


# ----------------------------------------------------------------------
# 15: wheel_momentum / wheel_saturated agree with the state
# ----------------------------------------------------------------------


def test_wheel_momentum_and_saturated_helpers():
    p = _base_params(Roll(model="wheel", I_x=0.02, I_w=2e-4, omega_w_max=10.0))
    y = np.zeros(10)
    y[OMEGA_X] = 1.0
    y[OMEGA_W] = 1.0 + 10.0  # exactly at the limit

    assert roll.wheel_momentum(y, p) == p.roll.I_w * (y[OMEGA_W] - y[OMEGA_X])
    assert bool(roll.wheel_saturated(y, p)) is True

    y[OMEGA_W] = 1.0 + 1.0  # well under the limit
    assert bool(roll.wheel_saturated(y, p)) is False

"""Cross-check for sim/dynamics3d.py (roadmap.md Step 29): planar initial
conditions must reproduce the existing Phase 1 2D trajectory to solver
tolerance, with the out-of-plane components staying exactly zero.

Physics sanity check, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`/`math.isclose`.
"""

import math

import numpy as np
from scipy.integrate import solve_ivp

from sim.dynamics import derivatives
from sim.dynamics3d import derivatives_3d
from sim.integrate import run_sim
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.quaternion import from_euler
from sim.state import State
from sim.state3d import OMEGA, Q, R, V

# Same zero-net-moment scenario as
# test_dynamics.test_rk4_agrees_with_rk45_on_apogee_and_impact:
# `A_z=0.0`, `A_m=0.0`, on-axis thrust (`thrust_misalign_deg` default 0.0),
# no lateral CoG/thrust offset (`u_B`/`u_C` default 0.0) -- together these
# make `M_y` identically zero for the whole flight regardless of `l1`/
# `l2`, so `theta`/`omega` are *exact* constants in the 2D solution too
# (not merely held fixed by the 3D code) -- the two sides integrate the
# same physics, not an approximation of it.
_P = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
)
_THETA0 = math.radians(45.0)  # non-vertical, so both x and z actually move
_VX0, _VZ0 = 10.0, -5.0       # nonzero initial velocity, both components


def test_planar_3d_matches_phase1_2d_trajectory():
    """r[0]/r[2] (the 3D embedding's x/z) must match the 2D x/z to solver
    tolerance; r[1]/v[1] (out-of-plane) must stay exactly 0.0 throughout --
    the check that the embedding has no out-of-plane leakage, not just
    that it happens to agree in-plane."""
    s0_2d = State(x=0.0, z=0.0, vx=_VX0, vz=_VZ0, theta=_THETA0, omega=0.0)
    # Tighter-than-default solver tolerances on both sides (two independent
    # solve_ivp runs otherwise land on slightly different adaptive step
    # grids/dense-output polynomials, which is a numerical-integration
    # artifact, not a dynamics discrepancy -- the pointwise RHS cross-check
    # below confirms the two derivative functions agree to machine
    # precision at matching states).
    result_2d = run_sim(_P, s0_2d, method="RK45", rtol=1e-11, atol=1e-13)
    t_ground = result_2d.events["ground"]
    assert t_ground is not None

    q0 = from_euler(0.0, _THETA0, 0.0)
    y0_3d = np.concatenate([
        [0.0, 0.0, 0.0],      # r: x=0, y=0, z=0
        [_VX0, 0.0, _VZ0],    # v: vx, vy=0, vz
        q0,                   # q: pitch-only
        [0.0, 0.0, 0.0],      # omega: zero, held constant
    ])

    sol_3d = solve_ivp(
        derivatives_3d,
        (0.0, t_ground),
        y0_3d,
        method="RK45",
        args=(_P,),
        dense_output=True,
        rtol=1e-11,
        atol=1e-13,
    )
    assert sol_3d.success

    t_samples = np.linspace(0.0, t_ground, 25)
    y2d_samples = result_2d.raw.sol(t_samples)
    y3d_samples = sol_3d.sol(t_samples)

    x_2d, z_2d = y2d_samples[0], y2d_samples[1]
    r_3d = y3d_samples[R]
    v_3d = y3d_samples[V]

    assert np.allclose(r_3d[0], x_2d, rtol=1e-7, atol=1e-4)
    assert np.allclose(r_3d[2], z_2d, rtol=1e-7, atol=1e-4)

    # No out-of-plane leakage: y-position and y-velocity are exactly zero
    # at every sampled instant, not just approximately so.
    assert np.all(r_3d[1] == 0.0)
    assert np.all(v_3d[1] == 0.0)

    # Attitude/angular velocity are genuinely held constant (Step 29 scope).
    q_3d = y3d_samples[Q]
    omega_3d = y3d_samples[OMEGA]
    for i in range(len(t_samples)):
        assert np.allclose(q_3d[:, i], q0)
    assert np.all(omega_3d == 0.0)


def test_derivatives_3d_cross_checks_derivatives_2d_pointwise():
    """At a handful of mid-flight (t, state) pairs, `derivatives_3d`'s
    translational components must equal `sim.dynamics.derivatives`'s,
    independent of the dense-output integration above -- a direct,
    single-call-per-sample check of the RHS itself."""
    s0_2d = State(x=0.0, z=0.0, vx=_VX0, vz=_VZ0, theta=_THETA0, omega=0.0)
    result_2d = run_sim(_P, s0_2d, method="RK45")
    t_ground = result_2d.events["ground"]
    assert t_ground is not None

    q0 = from_euler(0.0, _THETA0, 0.0)

    for t in np.linspace(0.0, t_ground, 10):
        y2d = result_2d.raw.sol(t)
        dydt_2d = derivatives(t, y2d, _P)

        y3d = np.concatenate([
            [y2d[0], 0.0, y2d[1]],
            [y2d[2], 0.0, y2d[3]],
            q0,
            [0.0, 0.0, 0.0],
        ])
        dydt_3d = derivatives_3d(t, y3d, _P)

        assert math.isclose(dydt_3d[0], dydt_2d[0], rel_tol=1e-9, abs_tol=1e-9)  # dx/dt
        assert dydt_3d[1] == 0.0                                                 # dy/dt
        assert math.isclose(dydt_3d[2], dydt_2d[1], rel_tol=1e-9, abs_tol=1e-9)  # dz/dt
        assert math.isclose(dydt_3d[3], dydt_2d[2], rel_tol=1e-9, abs_tol=1e-9)  # dvx/dt
        assert dydt_3d[4] == 0.0                                                 # dvy/dt
        assert math.isclose(dydt_3d[5], dydt_2d[3], rel_tol=1e-9, abs_tol=1e-9)  # dvz/dt
        assert np.all(dydt_3d[6:13] == 0.0)                                      # dq/dt, domega/dt

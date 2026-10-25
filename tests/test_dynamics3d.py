"""Cross-check for sim/dynamics3d.py (roadmap.md Step 29): planar initial
conditions must reproduce the existing Phase 1 2D trajectory to solver
tolerance, with the out-of-plane components staying exactly zero.

Physics sanity check, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`/`math.isclose`.
"""

import functools
import math

import numpy as np
from scipy.integrate import solve_ivp

from sim import inertia
from sim.dynamics import derivatives
from sim.dynamics3d import derivatives_3d
from sim.forces3d import moment_body_3d
from sim.integrate import run_sim
from sim.params import Aero, Inertia, Lengths, Params, Thrust, Weight, with_solver
from sim.quaternion import from_euler, to_dcm, to_euler
from sim.state import OMEGA as OMEGA_2D
from sim.state import THETA as THETA_2D
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
    result_2d = run_sim(with_solver(_P, rtol=1e-11, atol=1e-13), s0_2d)
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

    # Attitude/angular velocity are genuinely held constant -- not because
    # the code forces it any more (Step 29 scope, retired), but because
    # `omega = 0` and `M = 0` make it so under Step 30's real dynamics
    # (task-30-3d-rotational-dynamics.md SS30.5.2): `q_dot(q, 0) == 0`
    # exactly, and `p.inertia.model == "none"` (the default, unset here)
    # leaves `domega/dt == 0.0`. A strictly stronger statement than before.
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
    result_2d = run_sim(_P, s0_2d)
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
        # dq/dt, domega/dt: `q_dot(q0, omega=0) == 0` exactly (IEEE-754
        # `-0.0 == 0.0`), and `_P`'s default `inertia.model == "none"`
        # leaves `domega/dt == 0.0` -- Step 30's real dynamics (task-30-
        # 3d-rotational-dynamics.md SS30.5.2), not the retired Step-29
        # hardwired zero.
        assert np.all(dydt_3d[6:13] == 0.0)


# ----------------------------------------------------------------------
# Step 30 (task-30-3d-rotational-dynamics.md): tests 15-20
# ----------------------------------------------------------------------


def _pitch_tensor_params(C_m: float, I_xy: float = 0.0) -> Params:
    """A diagonal (or near-diagonal) tensor with `I_yy = I_zz = p.weight.I`
    -- the SS30.10.3 preconditions for comparing the 3D path against the
    trusted 2D pitch history: mass model OFF (default `m_d=None`), no
    rail/parachute (the 3D path has neither)."""
    I_val = 0.05
    return Params(
        weight=Weight(m=0.5, I=I_val),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(S=0.00442, d_ref=0.075, C_x=0.5, C_z=0.0, C_m=C_m),
        inertia=Inertia(model="tensor", I_xx=1.0e-4, I_yy=I_val, I_zz=I_val, I_xy=I_xy),
    )


def test_prescribed_rate_kinematics_with_no_inertia_model():
    """task-30 SS30.5.2/SS30.9 #15: `model == "none"` (the default) is
    PRESCRIBED-RATE kinematics -- `omega` exactly constant throughout,
    and `theta(t)` recovered from `to_euler(q)[1]` matches
    `theta0 + omega_y*t` to solver tolerance."""
    omega0 = np.array([0.0, 0.1, 0.0])
    q0 = from_euler(0.0, _THETA0, 0.0)
    y0 = np.concatenate([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], q0, omega0])

    t_max = 5.0
    sol = solve_ivp(
        derivatives_3d, (0.0, t_max), y0, method="RK45",
        args=(_P,), dense_output=True, rtol=1e-11, atol=1e-13,
    )
    assert sol.success

    t_samples = np.linspace(0.0, t_max, 25)
    y_samples = sol.sol(t_samples)
    omega_samples = y_samples[OMEGA]
    q_samples = y_samples[Q]

    assert np.all(omega_samples[0] == 0.0)
    assert np.all(omega_samples[1] == 0.1)
    assert np.all(omega_samples[2] == 0.0)

    for i, t in enumerate(t_samples):
        theta = to_euler(q_samples[:, i])[1]
        assert math.isclose(theta, _THETA0 + 0.1 * t, rel_tol=1e-9, abs_tol=1e-9)


def test_planar_3d_reproduces_the_phase1_2d_pitch_history():
    """THE ROADMAP'S OWN STATED STEP-30 CHECK (task-30 SS30.9 #16,
    SS30.10.3) -- and the weakest of the three acceptance checks, because
    `omega_x = omega_z = 0` makes the gyroscopic term identically zero
    (so it cannot see a sign error there at all). See `_pitch_tensor_params`
    for the load-bearing preconditions.

    The "constant" aero model's `C_m` is a genuinely constant torque (not
    alpha-proportional), so it is undamped (`c_mq = 0.0` default) and
    `theta` grows without bound over a full flight -- not chaos, just
    accumulated rotation, but it makes a FULL-FLIGHT trajectory
    comparison meaningless once `|theta|` leaves `to_euler`'s `arcsin`
    range `(-pi/2, pi/2)` (2D's `theta` is unwrapped; the 3D `to_euler`
    recovery is not). So this test deliberately uses a SHORT span and a
    small `C_m` -- enough to move `theta` by a clearly non-trivial amount
    (order 10 deg over 2 s) while staying comfortably inside that range,
    which is what makes the comparison apples-to-apples rather than a
    choice that happens to hide a bug."""
    p = _pitch_tensor_params(C_m=0.003)
    t_span = 2.0
    s0_2d = State(x=0.0, z=0.0, vx=_VX0, vz=_VZ0, theta=_THETA0, omega=0.0)
    result_2d = run_sim(with_solver(p, rtol=1e-11, atol=1e-13, t_max=t_span), s0_2d)

    q0 = from_euler(0.0, _THETA0, 0.0)
    y0_3d = np.concatenate([
        [0.0, 0.0, 0.0],
        [_VX0, 0.0, _VZ0],
        q0,
        [0.0, 0.0, 0.0],
    ])
    sol_3d = solve_ivp(
        derivatives_3d, (0.0, t_span), y0_3d, method="RK45",
        args=(p,), dense_output=True, rtol=1e-11, atol=1e-13,
    )
    assert sol_3d.success

    t_samples = np.linspace(0.0, t_span, 25)
    y2d_samples = result_2d.raw.sol(t_samples)
    y3d_samples = sol_3d.sol(t_samples)

    theta_2d = y2d_samples[THETA_2D]
    omega_2d = y2d_samples[OMEGA_2D]
    r_3d = y3d_samples[R]
    v_3d = y3d_samples[V]
    q_3d = y3d_samples[Q]
    omega_3d = y3d_samples[OMEGA]

    theta_3d = np.array([to_euler(q_3d[:, i])[1] for i in range(len(t_samples))])
    # The rotational channel is actually exercised (not vacuously equal
    # because nothing moved): theta changes by several degrees over the span.
    assert abs(theta_2d[-1] - _THETA0) > math.radians(5.0)
    assert np.allclose(theta_3d, theta_2d, rtol=1e-6, atol=1e-6)
    assert np.allclose(omega_3d[1], omega_2d, rtol=1e-6, atol=1e-6)

    # Out-of-plane components stay EXACTLY 0.0 (task-30 SS30.1.6) -- a
    # diagonal tensor, so no spurious out-of-plane coupling.
    assert np.all(r_3d[1] == 0.0)
    assert np.all(v_3d[1] == 0.0)
    assert np.all(omega_3d[0] == 0.0)
    assert np.all(omega_3d[2] == 0.0)
    assert np.all(q_3d[1] == 0.0)
    assert np.all(q_3d[3] == 0.0)


def test_moment_body_3d_embeds_the_2d_pitching_moment():
    """task-30 SS30.4.2 note 1/SS30.9 #17: no sign conversion is needed --
    `moment_body_3d(t, y3d, p)[1]` must equal the 2D moment
    (`dynamics.derivatives(...)[OMEGA] * I`) at matching states to
    `rel_tol=1e-13`, and components 0 and 2 must be exactly `0.0`. Guards
    the SS30.4.2 `pitch_moment` extraction (D-30.7)."""
    p = _pitch_tensor_params(C_m=0.3)
    s0_2d = State(x=0.0, z=0.0, vx=_VX0, vz=_VZ0, theta=_THETA0, omega=0.2)
    result_2d = run_sim(p, s0_2d)
    t_ground = result_2d.events["ground"]
    assert t_ground is not None

    for t in np.linspace(0.0, t_ground, 10):
        y2d = result_2d.raw.sol(t)
        dydt_2d = derivatives(t, y2d, p)
        M_y_2d = dydt_2d[OMEGA_2D] * p.weight.I

        theta = y2d[THETA_2D]
        omega_y = y2d[OMEGA_2D]
        q = from_euler(0.0, theta, 0.0)
        y3d = np.concatenate([
            [y2d[0], 0.0, y2d[1]],
            [y2d[2], 0.0, y2d[3]],
            q,
            [0.0, omega_y, 0.0],
        ])
        M_3d = moment_body_3d(t, y3d, p)
        assert math.isclose(M_3d[1], M_y_2d, rel_tol=1e-13)
        assert M_3d[0] == 0.0
        assert M_3d[2] == 0.0


def test_off_diagonal_inertia_breaks_planarity():
    """task-30 SS30.1.6/SS30.9 #18 -- THE POSITIVE TEST FOR THE CHOSEN
    MODEL. Same setup as `test_planar_3d_reproduces_the_phase1_2d_pitch_
    history` but with a non-zero admissible `I_xy`: `omega_x`/`omega_z`
    become non-zero and `r[1]` leaves the launch plane. Without this, the
    full 6-value tensor could be inert and every other test would still
    pass -- and this is the guard that stops a later refactor from
    "fixing" the exact-zero test above by hard-zeroing out-of-plane
    terms."""
    p = _pitch_tensor_params(C_m=0.3, I_xy=1.0e-5)
    q0 = from_euler(0.0, _THETA0, 0.0)
    y0_3d = np.concatenate([
        [0.0, 0.0, 0.0],
        [_VX0, 0.0, _VZ0],
        q0,
        [0.0, 0.0, 0.0],
    ])
    sol = solve_ivp(
        derivatives_3d, (0.0, 2.0), y0_3d, method="RK45",
        args=(p,), dense_output=True, rtol=1e-11, atol=1e-13,
    )
    assert sol.success

    y_end = sol.y[:, -1]
    assert y_end[R][1] != 0.0
    assert y_end[OMEGA][0] != 0.0
    assert y_end[OMEGA][2] != 0.0


def _rk4_step_3d(p, t: float, y: np.ndarray, dt: float) -> np.ndarray:
    """Classical fixed-step RK4 on the full 13-component 3D state (same
    standard update as `sim.integrate._run_rk4`'s own docstring) --
    re-implemented here, generically, because no reusable rk4 stepper
    exists outside that 2D-state-specific function (task-30 SS30.0.2: the
    3D path is an island; SS30.10.2: version-stable, unlike scipy's
    adaptive RK45, D-77)."""
    k1 = derivatives_3d(t, y, p)
    k2 = derivatives_3d(t + dt / 2.0, y + dt / 2.0 * k1, p)
    k3 = derivatives_3d(t + dt / 2.0, y + dt / 2.0 * k2, p)
    k4 = derivatives_3d(t + dt, y + dt * k3, p)
    return y + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


@functools.lru_cache(maxsize=1)
def _torque_free_tumble_trajectory():
    """Shared fixed-step rk4 integration for tests 19-20 (task-30 SS30.9
    #19-20): zero moment -- default `Aero()` has `S=0.0` (every aero
    force/moment inert) and default `Thrust()` has `motor_curve=""` (zero
    thrust, `sim.thrust_curve.thrust`'s own early return), so `M ==
    (0,0,0)` identically regardless of attitude/velocity -- an asymmetric
    admissible tensor, non-zero 3-axis omega0. `lru_cache` so tests 19 and
    20 share one integration rather than paying for it twice."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        inertia=Inertia(
            model="tensor", I_xx=0.05, I_yy=0.06, I_zz=0.065,
            I_xy=0.002, I_xz=0.0015, I_yz=0.001,
        ),
    )
    omega0 = np.array([0.5, -0.3, 0.8])
    q0 = np.array([1.0, 0.0, 0.0, 0.0])
    y = np.concatenate([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], q0, omega0])

    dt = 1.0e-3
    t_max = 10.0
    n_steps = int(round(t_max / dt))
    sample_every = max(1, n_steps // 200)

    t_samples = []
    y_samples = []
    t = 0.0
    for i in range(n_steps + 1):
        if i % sample_every == 0:
            t_samples.append(t)
            y_samples.append(y.copy())
        if i == n_steps:
            break
        y = _rk4_step_3d(p, t, y, dt)
        t += dt

    return p, np.array(t_samples), np.array(y_samples)


def test_torque_free_tumble_conserves_inertial_angular_momentum():
    """THE STRONGEST END-TO-END CHECK (task-30 SS30.9 #19, SS30.10.2):
    zero moment, asymmetric tensor, 3-axis omega0; integrate the full
    13-state and assert `to_dcm(q) @ (I @ omega)` is constant IN THE
    INERTIAL FRAME. Strictly stronger than the body-frame check (test 13,
    sim/test_inertia.py): it also catches a `q`/`omega` frame mismatch, a
    transposed DCM, or a quaternion-order error, none of which a
    body-frame-only check can see."""
    p, _t_samples, y_samples = _torque_free_tumble_trajectory()
    I = inertia.tensor(p.inertia)

    H_inertial = np.array([
        to_dcm(y[Q]) @ (I @ y[OMEGA]) for y in y_samples
    ])

    H0_norm = np.linalg.norm(H_inertial[0])
    max_dev = np.max(np.linalg.norm(H_inertial - H_inertial[0], axis=1)) / H0_norm
    assert max_dev < 1e-9


def test_quaternion_norm_drift_is_bounded():
    """task-30 SS30.6/SS30.9 #20: over test 19's span, `|norm(q) - 1|`
    stays bounded at every sample -- a MEASURED quantity (no
    renormalisation in the RHS, D-30.11), not an assumed-small one."""
    _p, _t_samples, y_samples = _torque_free_tumble_trajectory()
    q_samples = y_samples[:, Q]
    norms = np.linalg.norm(q_samples, axis=1)
    assert np.max(np.abs(norms - 1.0)) < 1e-9

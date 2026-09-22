"""Sign-check / algebraic tests for the pitching-moment terms in
sim/dynamics.py (architecture.md SS2, "Moments need no rotation at all";
roadmap.md Step 6).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np
from scipy.integrate import solve_ivp

from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.forces import aero_force_body, aero_moment_y, thrust_body, weight_inertial
from sim.frames import to_inertial
from sim.integrate import run_sim
from sim.params import Params
from sim.state import OMEGA, THETA, VX, VZ, X, Z, State


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


def test_moment_matches_closed_form_minus_l1_Az_minus_Am():
    """architecture.md SS2's "one-line unit test": with the corrected
    geometry (main.tex SSGeometry, corrected 2026-09-20: `aA = -l1*x_hat_r`,
    CoP aft of the CoG for a positive, nose-tip-referenced `l1`),
    M_y = -l1*A_z - A_m exactly. Thrust is zero here (t past T_BURN) so it
    cannot contaminate the check; A_x and theta are irrelevant to M_y (A_x
    and A_m don't interact, and cross_y(aA, aero_force_body) only picks up
    the A_z component since aA has no z-component).

    Re-derived (not just asserted) from `_cross_y`, the same way the
    previous version of this test's docstring did for the old sign: with
    the rocket at rest (alpha = 0 regardless of theta, so u_hat = x_hat_r,
    n_hat = z_hat_r -- Phase 1 axes) `aero_force_body = (-A_x, -A_z)`, and
    `aA = (-l1, 0)` under the corrected geometry. `_cross_y(aA, aero_force)
    = -(a_x*b_z - a_z*b_x) = -((-l1)*(-A_z) - 0*(-A_x)) = -l1*A_z`. Adding
    `aero_moment_y = -A_m` (main.tex SSMoments) gives the expected total
    `M_y = -l1*A_z - A_m`.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, T=0.0, A_x=1.23, A_z=2.0, A_m=0.5)
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=0.7, omega=1.5)
    y = np.array(s)

    dydt = derivatives(10.0, y, p)  # t > T_BURN, thrust is zero

    expected_M_y = -p.l1 * p.A_z - p.A_m
    assert math.isclose(dydt[OMEGA] * p.I, expected_M_y, rel_tol=1e-12, abs_tol=1e-12)


def _cross_y(a: np.ndarray, b: np.ndarray) -> float:
    """Local copy of dynamics._cross_y, used below only inside
    `_buggy_derivatives` (a from-scratch reconstruction of the pre-fix
    sign, kept out of sim/dynamics.py on purpose -- see that function's
    docstring)."""
    a_x, a_z = a
    b_x, b_z = b
    return -(a_x * b_z - a_z * b_x)


def _buggy_derivatives(t: float, y: np.ndarray, p) -> np.ndarray:
    """The pre-fix geometry, reconstructed here (not imported from
    anywhere -- it no longer exists in sim/dynamics.py) purely to
    demonstrate, by direct numeric contrast, what this fix actually
    changes: `aA = +l1*x_hat_r`, `aB = (l1 - l2)*x_hat_r`, i.e. the sign
    main.tex had *before* its 2026-09-20 correction. Everything else is
    identical to `dynamics.derivatives`.
    """
    theta = y[THETA]
    thrust = thrust_body(t, y, p)
    aero_force = aero_force_body(t, y, p)
    body_forces = thrust + aero_force
    F_i = weight_inertial(t, y, p) + to_inertial(body_forces, theta)
    a_i = F_i / p.m

    aA = np.array([p.l1, 0.0])
    aB = np.array([p.l1 - p.l2, 0.0])

    M_thrust = _cross_y(aB, thrust)
    M_aero = _cross_y(aA, aero_force)
    M_moment = aero_moment_y(t, y, p)
    M_y = M_thrust + M_aero + M_moment

    dydt = np.zeros(6)
    dydt[X] = y[VX]
    dydt[Z] = y[VZ]
    dydt[VX] = a_i[0]
    dydt[VZ] = a_i[1]
    dydt[THETA] = y[OMEGA]
    dydt[OMEGA] = M_y / p.I
    return dydt


def test_offaxis_alpha_stays_bounded_with_corrected_sign_but_diverges_with_old_sign():
    """The actual physical point of the aA/aB sign fix (main.tex
    SSGeometry, corrected 2026-09-20), demonstrated by running the real
    dynamics rather than re-deriving algebra: a rocket launched with a
    small initial angle of attack (a wind-gust- or off-axis-launch-like
    perturbation: `theta0` offset from the velocity direction by 0.15 rad,
    ~8.6 deg) with `aero_model="coefficients"`, a positive `C_N_alpha`, and
    `l1 > 0` should show a *restoring* (weathercocking) pitching moment
    with the corrected sign, and a *destabilizing* one with the old sign.

    Physical caveat, confirmed numerically before writing this test (not
    assumed): this model has no pitch-rate damping term yet (`C_m_alpha`/
    `C_N_alpha` act on `alpha` only, not `omega` -- that arrives with
    Mach/alpha-dependent coefficients, roadmap.md Step 25). A pure
    position-proportional restoring torque with no damping is an
    *undamped* oscillator, not a decaying one -- so the honest, verified
    claim is "bounded, oscillatory" (stable) vs "unbounded, monotonically
    growing" (divergent/tumbling), not literal decay to zero. Sampled
    directly (`aA = (-0.3, 0)`, `V0 = 60 m/s`, `alpha0 = -0.15 rad`) over
    the powered/coasting ascent (t in [0, 5] s, safely before this
    scenario's ~6.1 s apogee -- kept clear of the unrelated, already-
    covered tail-first-descent flip near/after apogee,
    tests/test_flow.py's `test_alpha_near_pi_on_tail_first_descent`):
    `|alpha(t)|` stays within [0.05, 0.15] rad throughout, i.e. bounded by
    (in fact never exceeding) its initial magnitude -- restoring, not
    growing.

    Contrast, from `_buggy_derivatives` (the pre-fix sign, reconstructed
    from scratch above, not imported from anywhere -- sim/dynamics.py no
    longer contains it): the identical initial condition reaches
    `alpha(2.0 s) = -1.65 rad`, well past +-pi/2 -- clearly tumbling, not a
    numerical artifact.

    Re-verified numerically after Phase 2.5 Step 35 changed `C_N`'s
    fallback from `C_N_alpha*alpha` to `C_N_alpha*sin(alpha)` (aero.py's
    module docstring): since `sin` saturates at 1, the buggy sign no
    longer produces smooth, monotonically-accelerating runaway (the old
    `alpha(1.0 s) = -2.19 rad` this test used to pin) -- it produces a
    large, wildly oscillating tumble instead (`alpha` sampled at
    t=1..5 s: -0.38, -1.65, +2.11, +0.47, -0.11 rad). The qualitative
    contrast this test exists to demonstrate is unchanged (bounded,
    small-amplitude restoring oscillation vs. large-amplitude tumbling),
    it just needs a threshold that tolerates non-monotonic growth: sampled
    at t=2.0 s (comfortably past the first excursion above `pi/2`, still
    within this scenario's pre-apogee window), not at t=1.0 s.
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.0, C_N_alpha=2.0, C_m_alpha=0.0,
    )
    alpha0 = -0.15
    theta0 = math.pi / 2 + alpha0  # vz-only launch: alpha = theta - pi/2 exactly
    V0 = 60.0
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-V0, theta=theta0, omega=0.0)

    # --- Corrected sign: run the real dynamics via run_sim -----------
    r = run_sim(p, s0, t_max=5.0, method="RK45")
    assert r.events["apogee"] is None  # confirms t_max=5.0 stays pre-apogee

    sample_times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    alphas_fixed = []
    for t in sample_times:
        y = r.raw.sol(t)
        alphas_fixed.append(flow_state(t, y, p).alpha)

    assert math.isclose(alphas_fixed[0], alpha0, abs_tol=1e-9)
    for a in alphas_fixed:
        assert abs(a) <= 0.2, alphas_fixed  # bounded, comfortably >= observed max ~0.15
    # Not monotonically diverging away from the trim condition: the last
    # sample is not larger in magnitude than several multiples of alpha0.
    assert abs(alphas_fixed[-1]) <= 2.0 * abs(alpha0), alphas_fixed

    # --- Old (pre-fix) sign: reconstructed locally, same initial state -
    y0 = np.array(s0)
    sol = solve_ivp(
        _buggy_derivatives, (0.0, 2.0), y0, args=(p,),
        dense_output=True, max_step=0.01, rtol=1e-9, atol=1e-9,
    )
    assert sol.status == 0
    alpha_buggy_2s = flow_state(2.0, sol.sol(2.0), p).alpha

    # Comfortably past +-pi/2 (genuinely tumbling, nose no longer even
    # broadside to the relative wind) -- observed ~-1.65 rad.
    assert abs(alpha_buggy_2s) > math.pi / 2


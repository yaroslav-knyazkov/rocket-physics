"""Sign-check / algebraic tests for the pitching-moment terms in
sim/dynamics.py (architecture.md SS2, "Moments need no rotation at all";
roadmap.md Step 6).

Physics sanity checks only, per the project's testing philosophy -- no
fixtures, no conftest.py, plain `assert` + `numpy.allclose`.
"""

import math

import numpy as np
from scipy.integrate import solve_ivp

from sim import aero, thrust_curve
from sim.dynamics import derivatives
from sim.flow import flow_state
from sim.forces import aero_force_body, aero_moment_y, thrust_body, weight_inertial
from sim.frames import to_inertial
from sim.integrate import run_sim
from sim.params import Params
from sim.state import M, OMEGA, THETA, VX, VZ, X, Z, State


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

    # Step 36: state is now 7-long (`m` appended, sim/state.py) -- this
    # reconstruction predates that and never used mass beyond `p.m`
    # (`p.m_d` is never set in this test), so dydt[M] stays the implicit
    # 0.0 `np.zeros` already gives it; only the array length needs to
    # track the now-7-component state so `solve_ivp` sees matching shapes.
    dydt = np.zeros(7)
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


def test_gravity_direction_parallel_reproduces_derivatives_bit_for_bit():
    """`p.gravity_direction = "parallel"` (the default) -- the on/off gate
    for Step 38's non-parallel gravity -- must give bit-for-bit identical
    derivatives regardless of `R_e`/downrange position `x`, exactly the
    same "gated field is inert when off" property
    `test_earth_rotation_off_reproduces_derivatives_bit_for_bit`
    (tests/test_dynamics.py) exercises for Step 37's `p.earth_rotation`.
    `x` and `R_e` are the two quantities the "radial" direction variant
    reads (`phi = x/R_e`) and "parallel" must not -- so varying both here
    and still getting an identical result is the real check.
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, A_x=0.5, gravity_direction="parallel")
    p_a = Params(R_e=6371000.0, **common)
    p_b = Params(R_e=1000.0, **common)
    s = State(x=0.0, z=-500.0, vx=120.0, vz=-40.0, theta=math.pi / 2, omega=0.05)
    s2 = State(x=50_000.0, z=-500.0, vx=120.0, vz=-40.0, theta=math.pi / 2, omega=0.05)

    dydt_a = derivatives(5.0, np.array(s), p_a)
    dydt_b = derivatives(5.0, np.array(s), p_b)
    dydt_a2 = derivatives(5.0, np.array(s2), p_a)
    dydt_b2 = derivatives(5.0, np.array(s2), p_b)

    assert np.array_equal(dydt_a, dydt_b)
    assert np.array_equal(dydt_a2, dydt_b2)
    assert np.array_equal(dydt_a, dydt_a2)


def test_gravity_direction_radial_matches_closed_form_and_leaves_moment_exactly_zero():
    """`gravity_direction="radial"` vs `"parallel"` at the same state
    (main.tex eq:weight_rotated): the added translational acceleration is
    exactly `[-g*sin(phi), g*(cos(phi)-1)]`, `phi = x/R_e`, and the moment
    equation is untouched -- `domega/dt` is asserted *exactly* equal (not
    `np.isclose`), since weight passes through the CoG by construction and
    contributes no moment whatever direction it points (this is the
    load-bearing physical claim of this step, main.tex
    SSAnalysis_moment referenced from eq:weight_rotated).
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, A_x=0.5, R_e=6371000.0)
    p_par = Params(gravity_direction="parallel", **common)
    p_rad = Params(gravity_direction="radial", **common)
    s = State(x=50_000.0, z=-1000.0, vx=120.0, vz=-40.0, theta=math.pi / 2, omega=0.05)
    y = np.array(s)

    dydt_par = derivatives(5.0, y, p_par)
    dydt_rad = derivatives(5.0, y, p_rad)

    phi = s.x / common["R_e"]
    g0 = p_par.g  # gravity_model="constant" (the default) -- g is exactly p.g

    assert math.isclose(dydt_rad[VX] - dydt_par[VX], -g0 * math.sin(phi),
                         rel_tol=1e-9, abs_tol=1e-12)
    assert math.isclose(dydt_rad[VZ] - dydt_par[VZ], g0 * (math.cos(phi) - 1.0),
                         rel_tol=1e-9, abs_tol=1e-12)
    assert dydt_rad[OMEGA] == dydt_par[OMEGA]


def test_gravity_direction_radial_adds_retarding_downrange_acceleration():
    """At `theta=0` (nose horizontal) and `x > 0`, the radial-direction
    correction tilts `z_hat_g` backwards (away from the flight direction,
    main.tex's own reading of eq:zhat_g_rotated), so weight gains a
    *negative* (retarding) downrange component -- it must not accelerate
    further downrange travel.
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, R_e=6371000.0)
    p_par = Params(gravity_direction="parallel", **common)
    p_rad = Params(gravity_direction="radial", **common)
    s = State(x=50_000.0, z=-1000.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y = np.array(s)

    W_par = weight_inertial(0.0, y, p_par)
    W_rad = weight_inertial(0.0, y, p_rad)

    assert W_par[0] == 0.0
    assert W_rad[0] < 0.0


# ---------------------------------------------------------------------
# Step 41 (Phase 2.7): elliptical gravity direction (architecture.md
# SS24.1) at the derivatives() level -- the "radial" tests above already
# cover z_hat_g itself in isolation (tests/test_gravity.py has the rest of
# Step 41's own unit tests, e.g. R_chi's pinned values).
# ---------------------------------------------------------------------


def test_gravity_direction_elliptical_reproduces_parallel_and_radial_domega_unchanged():
    """`gravity_direction="elliptical"` must leave `domega/dt` *exactly*
    equal to the "parallel"/"radial" cases at the same state -- weight
    passes through the CoG regardless of which direction model is active,
    so it contributes no moment whatever direction it points (the same
    load-bearing claim `test_gravity_direction_radial_matches_closed_form_
    and_leaves_moment_exactly_zero` makes for "radial").
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, A_x=0.5, lat0_deg=50.0, azimuth_deg=90.0)
    p_par = Params(gravity_direction="parallel", **common)
    p_ell = Params(gravity_direction="elliptical", **common)
    s = State(x=10_000.0, z=-1000.0, vx=120.0, vz=-40.0, theta=math.pi / 2, omega=0.05)
    y = np.array(s)

    dydt_par = derivatives(5.0, y, p_par)
    dydt_ell = derivatives(5.0, y, p_ell)

    assert dydt_ell[OMEGA] == dydt_par[OMEGA]


def test_gravity_direction_elliptical_differs_from_radial_at_the_same_state():
    """"radial" and "elliptical" must give a genuinely different
    translational acceleration at the same non-equatorial, non-cardinal
    launch site (architecture.md SS24.1's pinned Delta_phi = 4.839e-6 rad
    at phi0=50, chi=90, x=10km) -- otherwise "elliptical" would be a dead
    code path.
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, R_e=6371000.0, lat0_deg=50.0, azimuth_deg=90.0)
    p_rad = Params(gravity_direction="radial", **common)
    p_ell = Params(gravity_direction="elliptical", **common)
    s = State(x=10_000.0, z=-1000.0, vx=0.0, vz=0.0, theta=0.0, omega=0.0)
    y = np.array(s)

    W_rad = weight_inertial(0.0, y, p_rad)
    W_ell = weight_inertial(0.0, y, p_ell)

    assert not math.isclose(W_rad[0], W_ell[0], rel_tol=1e-9)


# ---------------------------------------------------------------------
# Step 39: thrust-axis misalignment (architecture.md SS23.2; main.tex
# eq:thrust_vector, analysis.tex eq:moment_full/moment_misaligned).
# ---------------------------------------------------------------------


def test_thrust_body_default_misalign_is_onaxis_vector_bitforbit():
    """`thrust_misalign_deg = 0.0` (the default) -- the on/off gate for
    Step 39 -- must make `thrust_body` return exactly `(T, 0.0)`, with no
    rounding: `np.radians(0.0) == 0.0`, `np.cos(0.0) == 1.0`,
    `np.sin(0.0) == 0.0` are all exact in IEEE754, so this is a genuine
    bitwise check (`np.array_equal`), not an `isclose` one. Exercised at
    several times, including one after burnout (T == 0), since the claim
    is "bit-for-bit for every T", not just a nonzero one.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv")
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)

    for t in (0.0, 0.5, 1.0, 2.5, 10.0):
        T = thrust_curve.thrust(t, y, p)
        assert np.array_equal(thrust_body(t, y, p), np.array([T, 0.0]))


def test_thrust_body_misaligned_matches_closed_form_vector():
    """`thrust_misalign_deg = delta != 0` must return
    `(T*cos(delta), T*sin(delta))` exactly (main.tex eq:thrust_vector) --
    checked algebraically against an independently computed `T`, not just
    "the vector changed".
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
               thrust_misalign_deg=5.0)
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)
    t = 1.0

    T = thrust_curve.thrust(t, y, p)
    delta = math.radians(5.0)
    vec = thrust_body(t, y, p)

    assert math.isclose(vec[0], T * math.cos(delta), rel_tol=1e-12)
    assert math.isclose(vec[1], T * math.sin(delta), rel_tol=1e-12)


def test_moment_shift_matches_closed_form_l1_plus_l2_T_sin_delta():
    """`M_y` (isolated here as `dydt[OMEGA] * p.I`, since `p.m_d` is off so
    `I` is the fixed `p.I`) shifts by exactly `(p.l1 + p.l2) * T * sin(delta)`
    between a misaligned and an aligned case at the same state and thrust
    magnitude (analysis.tex eq:moment_misaligned's `M_delta`, with the
    code's `l1 + l2` standing in for `l_C - l_B`) -- checked against the
    closed form, not merely "M_y changed".
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
                  A_x=0.5, A_z=0.3, A_m=0.1)
    p_aligned = Params(thrust_misalign_deg=0.0, **common)
    p_misaligned = Params(thrust_misalign_deg=7.0, **common)
    s = State(x=0.0, z=-50.0, vx=20.0, vz=-15.0, theta=1.1, omega=0.05)
    y = np.array(s)
    t = 0.5  # mid-burn -- T > 0

    dydt_aligned = derivatives(t, y, p_aligned)
    dydt_misaligned = derivatives(t, y, p_misaligned)

    T = thrust_curve.thrust(t, y, p_aligned)
    assert T > 0.0  # otherwise this test would not exercise the new term at all
    delta = math.radians(7.0)
    expected_shift = (p_aligned.l1 + p_aligned.l2) * T * math.sin(delta)

    My_aligned = dydt_aligned[OMEGA] * p_aligned.I
    My_misaligned = dydt_misaligned[OMEGA] * p_misaligned.I

    assert math.isclose(My_misaligned - My_aligned, expected_shift, rel_tol=1e-12)


def test_moment_shift_is_exactly_zero_when_thrust_is_zero():
    """analysis.tex sec:analysis_moment's table: "no thrust" collapses the
    aligned and misaligned columns onto each other for *any* `delta`,
    since `T = 0` scales both `cos(delta)` and `sin(delta)` out --
    misalignment is physically inert without thrust. Checked past burnout
    (`t` beyond the placeholder curve's last point, so `T == 0` exactly).
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
                  A_x=0.5, A_z=0.3, A_m=0.1)
    p_aligned = Params(thrust_misalign_deg=0.0, **common)
    p_misaligned = Params(thrust_misalign_deg=7.0, **common)
    s = State(x=0.0, z=-50.0, vx=20.0, vz=-15.0, theta=1.1, omega=0.05)
    y = np.array(s)
    t = 10.0  # well past the placeholder curve's burnout

    T = thrust_curve.thrust(t, y, p_aligned)
    assert T == 0.0

    dydt_aligned = derivatives(t, y, p_aligned)
    dydt_misaligned = derivatives(t, y, p_misaligned)

    assert dydt_aligned[OMEGA] == dydt_misaligned[OMEGA]


def test_moment_shift_is_independent_of_angle_of_attack():
    """analysis.tex sec:analysis_misaligned, "it does not change the
    static-stability result": `delta` is a constant, so
    `d(M_delta)/d(alpha) == 0` -- the moment shift from a fixed `delta`
    must be *identical* at two states with different angles of attack
    (same thrust magnitude, `aero_model="coefficients"` so `alpha` really
    does drive a nonzero, alpha-dependent aero moment/force on top of it),
    not merely "nonzero at both".
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3,
    )
    p_aligned = Params(thrust_misalign_deg=0.0, **common)
    p_misaligned = Params(thrust_misalign_deg=3.0, **common)
    t = 1.0

    V0 = 60.0
    s_alpha0 = State(x=0.0, z=-200.0, vx=0.0, vz=-V0, theta=math.pi / 2, omega=0.0)
    alpha2 = 0.25
    s_alpha_nonzero = State(x=0.0, z=-200.0, vx=0.0, vz=-V0,
                             theta=math.pi / 2 + alpha2, omega=0.0)

    T = thrust_curve.thrust(t, np.array(s_alpha0), p_aligned)
    delta = math.radians(3.0)
    expected_shift = (p_aligned.l1 + p_aligned.l2) * T * math.sin(delta)

    # Sanity: the two states really do differ in alpha, otherwise the loop
    # below would not actually exercise "different angles of attack".
    alpha_a = flow_state(t, np.array(s_alpha0), p_aligned).alpha
    alpha_b = flow_state(t, np.array(s_alpha_nonzero), p_aligned).alpha
    assert not math.isclose(alpha_a, alpha_b, abs_tol=1e-6)

    for s in (s_alpha0, s_alpha_nonzero):
        y = np.array(s)
        dydt_aligned = derivatives(t, y, p_aligned)
        dydt_misaligned = derivatives(t, y, p_misaligned)
        shift = (dydt_misaligned[OMEGA] - dydt_aligned[OMEGA]) * p_aligned.I

        assert math.isclose(shift, expected_shift, rel_tol=1e-12)


# ---------------------------------------------------------------------
# Step 43: lateral offsets u_B, u_C (architecture.md SS24.3; rocket-2d.tex
# SSGeometry; analysis.tex eq:moment_full).
# ---------------------------------------------------------------------


def test_lateral_offsets_default_reproduce_derivatives_bit_for_bit():
    """`u_B = u_C = 0.0` (the default) -- the on/off gate for Step 43 --
    must give bit-for-bit identical `derivatives()` output to a Params
    without the fields set at all, at several states, with a table-driven
    CoP (`aero_table`) and with `thrust_misalign_deg != 0` both exercised
    (the two other lateral-geometry-adjacent seams), per architecture.md
    SS24.3's "Checks for the step".
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3,
    )
    states = [
        State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0),
        State(x=10.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.05),
    ]
    t = 0.5

    for extra in (
        {},
        {"aero_table": "example.csv"},
        {"thrust_misalign_deg": 3.0},
        {"aero_table": "example.csv", "thrust_misalign_deg": 3.0},
    ):
        p_implicit = Params(**common, **extra)
        p_explicit = Params(u_B=0.0, u_C=0.0, **common, **extra)
        for s in states:
            y = np.array(s)
            dydt_implicit = derivatives(t, y, p_implicit)
            dydt_explicit = derivatives(t, y, p_explicit)
            assert np.array_equal(dydt_implicit, dydt_explicit)


def test_lateral_offsets_shift_moment_by_closed_form():
    """`M_y` shifts by exactly `(u_B-u_C)*T*cos(delta) - u_B*A_x` relative
    to the zero-offset case at the same state (architecture.md SS24.3):
    evaluate both and difference them, do not re-derive `M_y`.
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.5, C_N_alpha=2.0, C_m_alpha=0.3,
        thrust_misalign_deg=0.2,
    )
    p_zero = Params(u_B=0.0, u_C=0.0, **common)
    p_offset = Params(u_B=0.001, u_C=-0.002, **common)
    s = State(x=0.0, z=-100.0, vx=50.0, vz=-10.0, theta=1.3, omega=0.02)
    y = np.array(s)
    t = 0.5

    T = thrust_curve.thrust(t, y, p_zero)
    assert T > 0.0  # otherwise the thrust term would not be exercised
    delta = math.radians(p_zero.thrust_misalign_deg)
    flow = flow_state(t, y, p_zero)
    A_x = flow.q * p_zero.S * aero.C_A(flow.alpha, flow.M, p_zero)

    expected_shift = (p_offset.u_B - p_offset.u_C) * T * math.cos(delta) - p_offset.u_B * A_x

    My_zero = derivatives(t, y, p_zero)[OMEGA] * p_zero.I
    My_offset = derivatives(t, y, p_offset)[OMEGA] * p_offset.I

    assert math.isclose(My_offset - My_zero, expected_shift, rel_tol=1e-9)


def test_lateral_offset_closed_form_matches_thrust_moment_exactly():
    """The two thrust terms combine into a single closed form,
    `T*sqrt((u_B-u_C)^2+(l_C-l_B)^2)*sin(delta + atan2(u_B-u_C, l_C-l_B))`
    (architecture.md SS24.3): reproduces `M_thrust` exactly (isolated here
    via `T=0` aero to leave only the thrust term in `M_y`).
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        A_x=0.0, A_z=0.0, A_m=0.0,  # "constant" aero regime, all zero -> isolates thrust term
        thrust_misalign_deg=0.2,
        u_B=0.001, u_C=-0.0005,
    )
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)
    t = 0.5

    T = thrust_curve.thrust(t, y, p)
    assert T > 0.0
    delta = math.radians(p.thrust_misalign_deg)
    l_C_minus_l_B = p.l1 + p.l2
    u_diff = p.u_B - p.u_C

    expected_M_thrust = T * math.sqrt(u_diff**2 + l_C_minus_l_B**2) * math.sin(
        delta + math.atan2(u_diff, l_C_minus_l_B)
    )

    M_y = derivatives(t, y, p)[OMEGA] * p.I
    assert math.isclose(M_y, expected_M_thrust, rel_tol=1e-12)


def test_lateral_offset_equal_ub_uc_zeroes_thrust_term_but_not_aero_term():
    """With `u_B == u_C != 0` the thrust term is exactly zero (only the
    *difference* matters for thrust) while the `-u_B*A_x` term is not --
    the sharpest available test that the two fields are not conflated
    (architecture.md SS24.3).
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        A_x=0.5, A_z=0.0, A_m=0.0,
    )
    p_zero_offset = Params(u_B=0.0, u_C=0.0, **common)
    p_equal_offset = Params(u_B=0.002, u_C=0.002, **common)
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)
    t = 0.5  # mid-burn -- T > 0

    T = thrust_curve.thrust(t, y, p_zero_offset)
    assert T > 0.0

    My_zero = derivatives(t, y, p_zero_offset)[OMEGA] * p_zero_offset.I
    My_equal = derivatives(t, y, p_equal_offset)[OMEGA] * p_equal_offset.I

    # Thrust term unaffected (u_B - u_C == 0): only the -u_B*A_x term shifts.
    expected_shift = -p_equal_offset.u_B * common["A_x"]
    assert math.isclose(My_equal - My_zero, expected_shift, rel_tol=1e-12)
    assert not math.isclose(expected_shift, 0.0, abs_tol=1e-15)


def test_lateral_offset_at_alpha_zero_no_thrust_moment_is_exactly_minus_uB_Ax():
    """At `alpha = 0`, `T = 0`: `M_y == -u_B*A_x` exactly, the only
    surviving term of eq:moment_full (architecture.md SS24.3).
    """
    p = Params(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        A_x=0.75, A_z=0.0, A_m=0.0,
        u_B=0.0015, u_C=0.003,
    )
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)
    t = 10.0  # past burnout -- T == 0

    T = thrust_curve.thrust(t, y, p)
    assert T == 0.0

    M_y = derivatives(t, y, p)[OMEGA] * p.I
    assert math.isclose(M_y, -p.u_B * p.A_x, rel_tol=1e-12, abs_tol=1e-15)


def test_lateral_offsets_do_not_affect_translation_only_rotation():
    """architecture.md SS24.3, "No effect on the translational equation":
    `u_B`/`u_C` are moment arms only -- `dvx/dt`, `dvz/dt`, `dm/dt` are
    identical with and without the offsets at the same state, only
    `dydt[OMEGA]` differs.
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv",
        A_x=0.5, A_z=0.3, A_m=0.1,
    )
    p_zero = Params(u_B=0.0, u_C=0.0, **common)
    p_offset = Params(u_B=0.002, u_C=-0.001, **common)
    s = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    y = np.array(s)
    t = 0.0

    dydt_zero = derivatives(t, y, p_zero)
    dydt_offset = derivatives(t, y, p_offset)

    assert dydt_zero[VX] == dydt_offset[VX]
    assert dydt_zero[VZ] == dydt_offset[VZ]
    assert dydt_zero[M] == dydt_offset[M]
    assert not math.isclose(dydt_zero[OMEGA], dydt_offset[OMEGA], rel_tol=1e-9)


# ---------------------------------------------------------------------
# Step 44: pitch-damping c_mq scaffold (architecture.md SS24.4;
# analysis.tex sec:analysis_dynamic). Division-free q_hat*c_mq term,
# added to A_m inside aero_moment_y's "coefficients" regime only.
# ---------------------------------------------------------------------


def test_pitch_damping_default_is_exactly_zero_shift():
    """`c_mq = 0.0` (the default) must add exactly `0.0` to `aero_moment_y`
    at a state with nonzero omega, V, rho -- the on/off gate for Step 44.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4,
               aero_model="coefficients", S=0.005, d_ref=0.08,
               C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3, c_mq=0.0)
    s = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.3)
    y = np.array(s)

    p_no_damping_field = Params(m=0.5, I=0.05, l1=0.3, l2=0.4,
                                 aero_model="coefficients", S=0.005, d_ref=0.08,
                                 C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3)

    assert aero_moment_y(0.5, y, p) == aero_moment_y(0.5, y, p_no_damping_field)
    assert np.array_equal(derivatives(0.5, y, p), derivatives(0.5, y, p_no_damping_field))


def test_pitch_damping_shifts_A_m_by_closed_form():
    """`A_m` shifts by exactly `0.25*rho*V*S*d_ref^2*omega*c_mq` relative to
    `c_mq = 0` at the same state (architecture.md SS24.4) -- differencing
    two `aero_moment_y` calls, not re-deriving `A_m` itself. `aero_moment_y`
    returns `-A_m` (main.tex SSMoments), so its own shift is the *negative*
    of the `A_m` shift above.
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4,
                  aero_model="coefficients", S=0.005, d_ref=0.08,
                  C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3)
    p_zero = Params(c_mq=0.0, **common)
    p_damped = Params(c_mq=56.25, **common)
    s = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.3)
    y = np.array(s)
    t = 0.5

    flow = flow_state(t, y, p_zero)
    expected_A_m_shift = 0.25 * flow.air.rho * flow.V * p_zero.S * p_zero.d_ref**2 * y[OMEGA] * p_damped.c_mq

    shift = aero_moment_y(t, y, p_damped) - aero_moment_y(t, y, p_zero)
    assert math.isclose(shift, -expected_A_m_shift, rel_tol=1e-12)


def test_pitch_damping_shift_is_exactly_zero_at_omega_zero_and_at_V_zero():
    """The damping shift is exactly `0.0` at `omega = 0.0` (rest, nonzero
    V) and at `V = 0.0` (on the pad, nonzero omega) -- both factors
    multiply the product to a hard zero (architecture.md SS24.4).
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4,
                  aero_model="coefficients", S=0.005, d_ref=0.08,
                  C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3)
    p_zero = Params(c_mq=0.0, **common)
    p_damped = Params(c_mq=56.25, **common)

    s_omega_zero = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.0)
    y_omega_zero = np.array(s_omega_zero)
    assert aero_moment_y(0.5, y_omega_zero, p_damped) == aero_moment_y(0.5, y_omega_zero, p_zero)

    s_V_zero = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.3)
    y_V_zero = np.array(s_V_zero)
    assert aero_moment_y(0.0, y_V_zero, p_damped) == aero_moment_y(0.0, y_V_zero, p_zero)


def test_pitch_damping_no_nan_at_denormal_V():
    """The specific failure the division-free form exists to prevent
    (architecture.md SS24.4): a literal `omega*d_ref/(2*V)` intermediate
    gives `0.0*inf = nan` at a denormal `V`; the actual, division-free
    implementation must stay finite there.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4,
               aero_model="coefficients", S=0.005, d_ref=0.08,
               C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3, c_mq=56.25)
    s = State(x=0.0, z=0.0, vx=1e-300, vz=0.0, theta=math.pi / 2, omega=0.3)
    y = np.array(s)

    assert flow_state(0.0, y, p).V > 0.0  # confirms V is denormal, not literally 0
    A_m = aero_moment_y(0.0, y, p)
    assert np.isfinite(A_m)

    dydt = derivatives(0.0, y, p)
    assert np.all(np.isfinite(dydt))


def test_pitch_damping_shift_is_linear_and_odd_in_omega():
    """The shift is linear and odd in `omega`: negating `omega` negates the
    shift exactly, at fixed `(V, rho, alpha)` (architecture.md SS24.4).
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4,
                  aero_model="coefficients", S=0.005, d_ref=0.08,
                  C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3)
    p_zero = Params(c_mq=0.0, **common)
    p_damped = Params(c_mq=56.25, **common)
    t = 0.5

    s_pos = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.3)
    s_neg = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=-0.3)
    y_pos = np.array(s_pos)
    y_neg = np.array(s_neg)

    shift_pos = aero_moment_y(t, y_pos, p_damped) - aero_moment_y(t, y_pos, p_zero)
    shift_neg = aero_moment_y(t, y_neg, p_damped) - aero_moment_y(t, y_neg, p_zero)

    assert math.isclose(shift_pos, -shift_neg, rel_tol=1e-12)


def test_pitch_damping_shift_is_independent_of_alpha():
    """The damping shift depends only on `(V, rho, omega, c_mq)`, not on
    `alpha` -- the `c_mq` analogue of Step 39's "`delta` does not touch
    `∂θ̈/∂α`" check. Two states differing only in `theta` (hence `alpha`,
    since velocity is fixed) at the same `(V, omega)` must give the same
    shift (architecture.md SS24.4).
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4,
                  aero_model="coefficients", S=0.005, d_ref=0.08,
                  C_A0=0.05, C_N_alpha=2.0, C_m_alpha=0.3)
    p_zero = Params(c_mq=0.0, **common)
    p_damped = Params(c_mq=56.25, **common)
    t = 0.5

    V0 = 80.0
    s_alpha0 = State(x=0.0, z=-500.0, vx=0.0, vz=-V0, theta=math.pi / 2, omega=0.3)
    s_alpha_nonzero = State(x=0.0, z=-500.0, vx=0.0, vz=-V0, theta=math.pi / 2 + 0.25, omega=0.3)

    alpha_a = flow_state(t, np.array(s_alpha0), p_zero).alpha
    alpha_b = flow_state(t, np.array(s_alpha_nonzero), p_zero).alpha
    assert not math.isclose(alpha_a, alpha_b, abs_tol=1e-6)  # sanity: alpha really differs

    for s in (s_alpha0, s_alpha_nonzero):
        y = np.array(s)
        shift = aero_moment_y(t, y, p_damped) - aero_moment_y(t, y, p_zero)
        expected_A_m_shift = 0.25 * flow_state(t, y, p_zero).air.rho * flow_state(t, y, p_zero).V \
            * p_zero.S * p_zero.d_ref**2 * y[OMEGA] * p_damped.c_mq
        assert math.isclose(shift, -expected_A_m_shift, rel_tol=1e-12)


def test_pitch_damping_constant_regime_untouched():
    """`aero_model="constant"` has no `q`/`V`/`rho` in it by definition
    (main.tex SSMoments Phase 1 form) -- `c_mq`/`C_mq` are not consulted
    there, so a nonzero `c_mq` changes nothing (architecture.md SS24.4).
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4,
                  aero_model="constant", A_x=0.5, A_z=0.3, A_m=0.1)
    p_zero = Params(c_mq=0.0, **common)
    p_damped = Params(c_mq=56.25, **common)
    s = State(x=0.0, z=-500.0, vx=50.0, vz=-20.0, theta=1.2, omega=0.3)
    y = np.array(s)

    assert aero_moment_y(0.5, y, p_zero) == aero_moment_y(0.5, y, p_damped)
    assert np.array_equal(derivatives(0.5, y, p_zero), derivatives(0.5, y, p_damped))


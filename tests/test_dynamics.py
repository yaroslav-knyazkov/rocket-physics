"""Cross-check that RK4 (sim/integrate.py's `method="rk4"`) and RK45
(`method="RK45"`, the default) agree on the flight of the same scenario
(roadmap.md Step 8).

This is the test that proves sim/dynamics.py is genuinely solver-agnostic:
both paths call `derivatives(t, y, p)` with no special-casing, and only
differ in how they step through time. It is a physics/numerics sanity
check, not a unit test of a single function -- per the project's testing
philosophy, no fixtures, no conftest.py, plain `assert` + `math.isclose`.

Step 36 (roadmap.md; main.tex SSModels > Mass and moment of inertia) adds
the variable-mass tests below: `state.m`/`params.m_d` on/off gate,
`dm/dt = -T_ref(t)/(I_sp*g0)` reaching the dry mass at burnout, and the
two-lumped-mass `l_B(t)`/`I(t)` model (parallel-axis theorem). See
sim/dynamics.py's module docstring for the one deliberate scope decision
made here: `p.l1`/`p.l2` (the CoP-to-CoG and CoP-to-thrust moment arms)
are *not* made functions of `l_B(t)` by this step -- main.tex's Mass and
moment of inertia section gives no formula for that, and architecture.md
SS19 flags it as a still-open question. `I(t)`'s own parallel-axis terms
already depend on `l_B(t)`, which is what the tests below exercise.
"""

import math

import numpy as np

from sim.dynamics import _cog_position, _moment_of_inertia, _propellant_mass, derivatives
from sim.flow import flow_state
from sim.integrate import run_sim
from sim.params import Params
from sim.rotation import OMEGA_EARTH, coriolis_inplane, coriolis_lateral_diagnostic, omega_components
from sim.state import M, THETA, VX, VZ, State, X, Z


def test_rk4_agrees_with_rk45_on_apogee_and_impact():
    """Same scenario as run.py's placeholder: the placeholder motor curve
    (Step 14) plus a constant axial drag, vertical launch from rest.

    Note (Step 14): this used to set `T=50.0` (Phase 1's constant-thrust
    magnitude). `motor_curve` now fully owns thrust (`forces.thrust_body`
    no longer reads `p.T` at all -- see sim/thrust_curve.py), so a `T=...`
    value alone would silently mean *zero* thrust for the whole flight,
    not "a different thrust profile". That degenerate scenario also makes
    this specific cross-check impractically slow: with nothing to
    overcome gravity, the flight runs the full default `t_max` and RK4's
    fixed dt=1e-4 grid turns into millions of steps in a pure-Python loop.
    Using the real placeholder curve keeps both the physics and the
    runtime representative of an actual flight.

    Tolerance rationale: RK4 here has no event location, only a fixed dt
    grid refined by linear interpolation across the one step that
    straddles each event (see `_run_rk4`'s docstring) -- so its event
    times and apogee altitude are grid-resolution-limited, not exact.
    Measured directly (this scenario, dt=1e-4 s): apogee time differs by
    ~3.2e-5 s, impact time by ~5.9e-5 s, apogee altitude by ~8.7e-3 m from
    RK45's values. The tolerances below (1e-3 s, 5e-2 m) sit comfortably
    above those measured differences while still being tight enough that
    an actual dynamics.py bug (a sign error, a missing term) -- which
    would show up as a difference many orders of magnitude larger, not a
    grid-resolution artifact -- would fail this test.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv", A_x=0.5, A_z=0.0, A_m=0.0)
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    rk45 = run_sim(p, s0, method="RK45")
    rk4 = run_sim(p, s0, method="rk4", dt=1e-4)

    apogee_rk45 = rk45.events["apogee"]
    apogee_rk4 = rk4.events["apogee"]
    impact_rk45 = rk45.events["ground"]
    impact_rk4 = rk4.events["ground"]

    assert apogee_rk45 is not None and apogee_rk4 is not None
    assert impact_rk45 is not None and impact_rk4 is not None

    alt_rk45 = -rk45.raw.sol(apogee_rk45)[Z]
    alt_rk4 = -rk4.raw.sol(apogee_rk4)[Z]

    assert math.isclose(apogee_rk4, apogee_rk45, abs_tol=1e-3)
    assert math.isclose(impact_rk4, impact_rk45, abs_tol=1e-3)
    assert math.isclose(alt_rk4, alt_rk45, abs_tol=5e-2)


# ---------------------------------------------------------------------
# Step 36: variable mass -- CoG and moment-of-inertia travel
# ---------------------------------------------------------------------

# data/motors/placeholder.csv's own header comment: "total impulse:
# 162.75 N*s" -- used below to pick an initial propellant mass that
# consumes itself exactly (to numerical-integration tolerance) over the
# curve's whole burn, so "final m == m_d" is a real check, not a fudge.
_PLACEHOLDER_IMPULSE_NS = 162.75
_ISP_S = 200.0          # s, placeholder specific impulse
_G0 = 9.80665            # m/s^2, matches Params.g's default (read as g0)
_M_D = 0.4               # kg, dry (burnout) mass
_M_P0 = _PLACEHOLDER_IMPULSE_NS / (_ISP_S * _G0)  # kg, initial propellant mass
_M0 = _M_D + _M_P0        # kg, initial (wet) mass


def test_mass_model_off_reproduces_fixed_mass_bit_for_bit():
    """`p.m_d = None` (the default) -- the on/off gate -- must reproduce
    the pre-Step-36 fixed-`p.m`/`p.I` physics exactly, regardless of what
    `state.m` (the now-added 7th component, unused on this path) happens
    to hold. Two states differing *only* in `m` (0.0, State's own default,
    vs. a deliberately wrong 999.0) must give bit-for-bit identical
    derivatives.
    """
    p = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv", A_x=0.5)
    s_default_m = State(x=0.0, z=0.0, vx=0.0, vz=-10.0, theta=math.pi / 2, omega=0.1)
    s_garbage_m = State(x=0.0, z=0.0, vx=0.0, vz=-10.0, theta=math.pi / 2, omega=0.1, m=999.0)

    dydt_default = derivatives(0.5, np.array(s_default_m), p)
    dydt_garbage = derivatives(0.5, np.array(s_garbage_m), p)

    assert np.array_equal(dydt_default, dydt_garbage)


def test_mass_reaches_dry_mass_at_burnout():
    """Check text, first clause: integrating `dm/dt = -T_ref(t)/(I_sp*g0)`
    over the placeholder curve's whole burn (total impulse 162.75 N*s,
    burnout at t=2.0 s) must bring `m` down to `m_d` -- `_M_P0` above is
    exactly the propellant mass that curve's impulse consumes.
    """
    p = Params(
        m=_M0, I=0.05, l1=0.3, l2=0.4,
        motor_curve="placeholder.csv",
        m_d=_M_D, l_d=0.3, l_p=0.3, I_d=0.05, I_sp=_ISP_S,
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=_M0)

    result = run_sim(p, s0, t_max=2.5)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    m_at_burnout = result.raw.sol(t_burnout)[M]
    m_at_end = result.raw.sol(2.5)[M]

    assert math.isclose(m_at_burnout, p.m_d, abs_tol=1e-3)
    # dm/dt == 0 once T_ref == 0 (thrust_curve.thrust returns 0 past the
    # curve's last point) -- mass must stay pinned at m_d, not drift.
    assert math.isclose(m_at_end, p.m_d, abs_tol=1e-3)


def test_cog_position_stays_at_l_d_when_l_p_equals_l_d():
    """models.tex's l_B(t) = (m_d*l_d + m_p*l_p)/(m_d+m_p): when l_p == l_d
    every term shares the same centroid, so l_B(t) == l_d identically for
    every m_p, and I(t)'s parallel-axis terms vanish -- "no CoG shift",
    the regression check's own phrase.
    """
    p = Params(m=_M0, I=0.05, l1=0.3, l2=0.4, m_d=_M_D, l_d=0.3, l_p=0.3, I_d=0.05, I_sp=_ISP_S)

    for m in (p.m, 0.6, 0.5, p.m_d + 0.01, p.m_d):
        m_p = _propellant_mass(m, p)
        l_B = _cog_position(m_p, p)
        assert math.isclose(l_B, p.l_d, rel_tol=1e-12, abs_tol=1e-12)

        I = _moment_of_inertia(m_p, l_B, p)
        expected_I = p.I_d + (p.I_d / p.m_d) * m_p  # I_p(t) only, zero parallel-axis term
        assert math.isclose(I, expected_I, rel_tol=1e-12)


def test_cog_shifts_and_inertia_grows_when_l_p_differs_from_l_d():
    """With a real offset (l_p != l_d) the CoG sits strictly between l_d
    and l_p (mass-weighted average) whenever propellant remains, and the
    parallel-axis terms make I(t) strictly larger than the "no CoG shift"
    case at the same mass -- isolating the effect of l_B(t) != l_d that
    the regression check asks for.
    """
    p = Params(m=_M0, I=0.05, l1=0.3, l2=0.4, m_d=_M_D, l_d=0.3, l_p=0.5, I_d=0.05, I_sp=_ISP_S)
    m_p_wet = p.m - p.m_d
    assert m_p_wet > 0.0

    l_B = _cog_position(m_p_wet, p)
    assert p.l_d < l_B < p.l_p

    I_shifted = _moment_of_inertia(m_p_wet, l_B, p)
    I_noshift = p.I_d + (p.I_d / p.m_d) * m_p_wet  # what Step 36 gives when l_p == l_d
    assert I_shifted > I_noshift


def test_real_cog_offset_changes_pitch_trajectory():
    """Trajectory-level version of the isolation check above: same burn,
    same constant aero pitching moment (A_m, so the moment equation's only
    time-dependence is `I(t)` itself), only `l_p` differs. `l_p == l_d`
    ("no CoG shift") must give a different `theta(t)` than a real offset
    `l_p != l_d`, since `I(t)` -- and therefore `domega/dt = M_y/I(t)` --
    differs between the two runs (main.tex SSModels > Mass and moment of
    inertia; `p.l1`/`p.l2` are unchanged in both runs -- see this file's
    module docstring).
    """
    common = dict(
        m=_M0, I=0.05, l1=0.3, l2=0.4,
        motor_curve="placeholder.csv",
        m_d=_M_D, I_d=0.05, I_sp=_ISP_S,
        A_m=0.05,  # constant pitching moment -- the only moment source here
    )
    p_noshift = Params(l_d=0.3, l_p=0.3, **common)
    p_shift = Params(l_d=0.3, l_p=0.5, **common)
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0, m=_M0)

    r_noshift = run_sim(p_noshift, s0, t_max=2.5)
    r_shift = run_sim(p_shift, s0, t_max=2.5)

    theta_noshift = r_noshift.raw.sol(2.0)[THETA]
    theta_shift = r_shift.raw.sol(2.0)[THETA]

    assert not math.isclose(theta_noshift, theta_shift, rel_tol=1e-6, abs_tol=1e-6)


# ---------------------------------------------------------------------
# Step 37: non-inertial (Coriolis) frame correction -- Option B (see
# sim/rotation.py's module docstring): in-plane Coriolis only, gated by
# `p.earth_rotation`, plus a labeled-but-unused lateral diagnostic. No
# residual centrifugal term (rejected scope).
# ---------------------------------------------------------------------


def test_omega_components_have_unit_norm():
    """models.tex eq:omega_components is a pure change of basis (ENU ->
    the flight-plane triad), so `Omega_x^2 + Omega_y^2 + Omega_z^2` must
    equal `Omega^2` for every `(phi0, chi)` -- a basis-independent
    invariant that catches a sign/axis-labeling error even before any
    force is computed.
    """
    for lat0_deg in (-90.0, -50.0, 0.0, 23.4, 50.0, 90.0):
        for azimuth_deg in (0.0, 45.0, 90.0, 135.0, 180.0, 270.0, 359.0):
            p = Params(m=1.0, I=1.0, l1=0.1, l2=0.1, lat0_deg=lat0_deg, azimuth_deg=azimuth_deg)
            omega_x, omega_y, omega_z = omega_components(p)
            norm_sq = omega_x**2 + omega_y**2 + omega_z**2
            assert math.isclose(norm_sq, OMEGA_EARTH**2, rel_tol=1e-9)


def test_earth_rotation_off_reproduces_derivatives_bit_for_bit():
    """`p.earth_rotation = False` (the default) -- the on/off gate -- must
    give bit-for-bit identical derivatives regardless of `lat0_deg`/
    `azimuth_deg`, exactly the same "gated field is inert when off"
    property `test_mass_model_off_reproduces_fixed_mass_bit_for_bit`
    exercises for Step 36's `p.m_d`. A nonzero velocity is required here
    (unlike that test) since `coriolis_inplane` is `[0, 0]` at `v=0`
    regardless of the gate -- a state at rest would not actually exercise
    the gate.
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, A_x=0.5)
    p_site_a = Params(lat0_deg=0.0, azimuth_deg=90.0, **common)
    p_site_b = Params(lat0_deg=50.0, azimuth_deg=30.0, **common)
    s = State(x=100.0, z=-500.0, vx=120.0, vz=-40.0, theta=math.pi / 2, omega=0.05)

    dydt_a = derivatives(5.0, np.array(s), p_site_a)
    dydt_b = derivatives(5.0, np.array(s), p_site_b)

    assert np.array_equal(dydt_a, dydt_b)


def test_earth_rotation_on_matches_closed_form_in_plane_acceleration():
    """`derivatives`'s added acceleration, with `p.earth_rotation = True`,
    must equal models.tex eq:coriolis_2d's closed form,

        a_x = +2*Omega*cos(phi0)*sin(chi)*vz
        a_z = -2*Omega*cos(phi0)*sin(chi)*vx

    computed independently here (not by calling `sim.rotation` itself) so
    this is a real check against the derivation, not a tautology. Also a
    magnitude sanity check: at `phi0=50`, `chi=90`, `V=300 m/s` (`vx=300`,
    `vz=0`) the architect's report and models.tex SS"Magnitudes" both give
    ~2.8e-2 m/s^2.
    """
    p_off = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, A_x=0.0,
                    lat0_deg=50.0, azimuth_deg=90.0, earth_rotation=False)
    p_on = Params(m=0.5, I=0.05, l1=0.3, l2=0.4, A_x=0.0,
                   lat0_deg=50.0, azimuth_deg=90.0, earth_rotation=True)
    s = State(x=0.0, z=-1000.0, vx=300.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    dydt_off = derivatives(0.0, np.array(s), p_off)
    dydt_on = derivatives(0.0, np.array(s), p_on)
    added = np.array([dydt_on[VX] - dydt_off[VX], dydt_on[VZ] - dydt_off[VZ]])

    phi0 = math.radians(50.0)
    chi = math.radians(90.0)
    k = 2.0 * OMEGA_EARTH * math.cos(phi0) * math.sin(chi)
    expected = np.array([k * s.vz, -k * s.vx])

    assert np.allclose(added, expected, rtol=1e-9, atol=1e-15)
    assert math.isclose(abs(expected[1]), 2.8e-2, rel_tol=0.05)


def test_earth_rotation_deflects_vertical_flight_by_order_ten_metres():
    """Trajectory-level sanity check (roadmap.md Step 37's "Check"):
    reuse the vertical-launch, few-km-apogee scenario from
    `test_rk4_agrees_with_rk45_on_apogee_and_impact` above (theta=pi/2,
    `A_z=0`, `A_m=0` -> zero pitching moment for the whole flight, so
    `theta` never leaves pi/2 and, with `earth_rotation=False`, downrange
    `x` stays *exactly* 0 the whole flight -- the body-frame thrust/aero
    forces only ever rotate into the inertial z-axis).

    With `earth_rotation=True` at `phi0=50`, `chi=90` (`p.azimuth_deg`'s
    default), the only source of downrange motion is the added Coriolis
    term, and models.tex SS"Magnitudes" gives an explicit worked number
    for this exact scenario: "order 10 m of displacement over a 30 s
    powered ascent" -- this flight's apogee is at t~=30 s.
    """
    common = dict(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve="placeholder.csv", A_x=0.5, A_z=0.0, A_m=0.0)
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    p_off = Params(lat0_deg=50.0, azimuth_deg=90.0, earth_rotation=False, **common)
    p_on = Params(lat0_deg=50.0, azimuth_deg=90.0, earth_rotation=True, **common)

    r_off = run_sim(p_off, s0)
    r_on = run_sim(p_on, s0)

    t_apogee_off = r_off.events["apogee"]
    t_apogee_on = r_on.events["apogee"]
    assert t_apogee_off is not None and t_apogee_on is not None

    x_apogee_off = r_off.raw.sol(t_apogee_off)[X]
    x_apogee_on = r_on.raw.sol(t_apogee_on)[X]

    assert math.isclose(x_apogee_off, 0.0, abs_tol=1e-9)
    # "Order 10 m" -- generously bracketed, this is an order-of-magnitude
    # check, not a precise regression value (main.tex/models.tex give the
    # estimate, not an exact number to reproduce bit-for-bit).
    assert 1.0 < abs(x_apogee_on) < 100.0


def test_coriolis_inplane_zero_for_due_north_south_launch():
    """models.tex: `Omega_y = -Omega*cos(phi0)*sin(chi)` vanishes for a
    launch due North or due South (`chi = 0`/`180` deg) at any latitude --
    the in-plane Coriolis term the 2D model actually applies is then
    exactly zero, the model's documented "blind spot".
    """
    s = State(x=10.0, z=-2000.0, vx=250.0, vz=-30.0, theta=math.pi / 2, omega=0.0)
    for lat0_deg in (-60.0, 0.0, 45.0, 89.0):
        for azimuth_deg in (0.0, 180.0):
            p = Params(m=1.0, I=1.0, l1=0.1, l2=0.1, lat0_deg=lat0_deg, azimuth_deg=azimuth_deg)
            a = coriolis_inplane(0.0, np.array(s), p)
            assert math.isclose(a[0], 0.0, abs_tol=1e-15)
            assert math.isclose(a[1], 0.0, abs_tol=1e-15)


def test_coriolis_lateral_diagnostic_nonzero_at_the_blind_spot():
    """The whole point of `coriolis_lateral_diagnostic` (sim/rotation.py's
    module docstring, point 2): exactly where the retained in-plane term
    is zero (`chi = 0`/`180` deg, per the test above), the *true* Coriolis
    effect is not zero -- it is maximal and entirely lateral. The
    diagnostic must report a nonzero value there, so the in-plane number
    alone is never misread as "no Coriolis effect on this launch".
    """
    s = State(x=10.0, z=-2000.0, vx=250.0, vz=-30.0, theta=math.pi / 2, omega=0.0)

    for lat0_deg in (-60.0, 30.0, 60.0):
        for azimuth_deg in (0.0, 180.0):
            p = Params(m=1.0, I=1.0, l1=0.1, l2=0.1, lat0_deg=lat0_deg, azimuth_deg=azimuth_deg)
            in_plane = coriolis_inplane(0.0, np.array(s), p)
            lateral = coriolis_lateral_diagnostic(0.0, np.array(s), p)

            assert math.isclose(in_plane[0], 0.0, abs_tol=1e-15)
            assert math.isclose(in_plane[1], 0.0, abs_tol=1e-15)
            assert abs(lateral) > 1e-6

    # And it is generically nonzero away from the blind spot too, for a
    # moving rocket (it is not a "only fires at chi=0/180" quantity).
    p_generic = Params(m=1.0, I=1.0, l1=0.1, l2=0.1, lat0_deg=50.0, azimuth_deg=90.0)
    assert abs(coriolis_lateral_diagnostic(0.0, np.array(s), p_generic)) > 1e-6


def test_coriolis_lateral_diagnostic_matches_closed_form():
    """`coriolis_lateral_diagnostic` must equal models.tex
    eq:coriolis_split's discarded bracket, `-2*(Omega_z*vx - Omega_x*vz)`,
    computed independently here from `omega_components` (not by re-calling
    `coriolis_lateral_diagnostic` itself)."""
    s = State(x=0.0, z=-1500.0, vx=180.0, vz=-25.0, theta=math.pi / 2, omega=0.0)
    p = Params(m=1.0, I=1.0, l1=0.1, l2=0.1, lat0_deg=35.0, azimuth_deg=60.0)

    omega_x, _omega_y, omega_z = omega_components(p)
    expected = -2.0 * (omega_z * s.vx - omega_x * s.vz)

    assert math.isclose(coriolis_lateral_diagnostic(0.0, np.array(s), p), expected, rel_tol=1e-12)


# ---------------------------------------------------------------------
# Step 39: thrust-axis misalignment -- trim angle of attack
# (architecture.md SS23.2; analysis.tex eq:alpha_trim).
# ---------------------------------------------------------------------


def test_misaligned_thrust_trims_stable_airframe_instead_of_diverging():
    """A statically stable airframe (the same aero_model="coefficients"
    fixture Steps 25/35 use, tests/test_forces.py's
    `test_offaxis_alpha_stays_bounded_with_corrected_sign...`: positive
    `C_N_alpha`, `l1 > 0`, i.e. CoP aft of CoG) launched dead vertical
    (`theta0 = pi/2`, `alpha0 = 0`) with `thrust_misalign_deg = 0.0` stays
    at `alpha = 0` for the whole burn -- the trivial "aligned" equilibrium
    of analysis.tex eq:moment_aligned, with nothing to disturb it.

    Introducing a small, realistic nozzle cant (`|delta| = 0.2 deg`, inside
    the spec's stated "0.1-1.0 deg" range) gives `M_delta != 0` from
    ignition (analysis.tex eq:moment_misaligned), so eq:alpha_trim predicts
    a nonzero equilibrium alpha whose sign matches `M_delta`'s: positive
    `delta` gives `l_C - l_B > 0` (`aB = -(l1+l2)*x_hat_r` puts the nozzle
    aft of the CoG, same convention as tests/test_forces.py's moment-shift
    tests), `sin(delta) > 0`, `T > 0` -> `M_delta > 0`; a stable airframe's
    `d(theta_ddot)/d(alpha) < 0` then makes `alpha_trim > 0` (eq:alpha_trim).

    Without a pitch-damping term (tests/test_forces.py's existing off-axis
    test already documents this model has none yet), the airframe does not
    asymptote to `alpha_trim` -- it is a forced, undamped oscillator that
    starts away from the *new* equilibrium, so it swings through a range
    including it rather than settling there. What is checked instead,
    early in the burn before the first oscillation reverses (verified
    numerically: sampled at t=0.1..0.4 s, well before the ~0.5 s first
    sign flip) is exactly the claim the check calls for: `alpha(t)` takes
    the sign of `M_delta` (i.e. of `delta`) throughout that window, stays
    small (bounded, not diverging towards +-pi/2 like the sign-bug
    regression test's tumble), and negating `delta` mirrors `alpha(t)`
    almost exactly (the configuration is otherwise perfectly symmetric).
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.0, C_N_alpha=2.0, C_m_alpha=0.0,
        motor_curve="placeholder.csv",
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    sample_times = [0.1, 0.2, 0.3, 0.4]

    # --- Baseline: delta = 0.0 -> the trivial aligned equilibrium -----
    p_baseline = Params(thrust_misalign_deg=0.0, **common)
    r_baseline = run_sim(p_baseline, s0, t_max=1.0, method="RK45")
    for t in sample_times:
        alpha = flow_state(t, r_baseline.raw.sol(t), p_baseline).alpha
        assert math.isclose(alpha, 0.0, abs_tol=1e-9)

    # --- Positive cant: alpha(t) > 0 throughout the sampled window ----
    p_pos = Params(thrust_misalign_deg=0.2, **common)
    r_pos = run_sim(p_pos, s0, t_max=1.0, method="RK45")
    alphas_pos = [flow_state(t, r_pos.raw.sol(t), p_pos).alpha for t in sample_times]
    for a in alphas_pos:
        assert a > 0.0
        assert abs(a) < 0.5  # bounded -- nowhere near the tumbling regime

    # --- Negative cant: mirrors the positive case almost exactly ------
    p_neg = Params(thrust_misalign_deg=-0.2, **common)
    r_neg = run_sim(p_neg, s0, t_max=1.0, method="RK45")
    alphas_neg = [flow_state(t, r_neg.raw.sol(t), p_neg).alpha for t in sample_times]
    for a in alphas_neg:
        assert a < 0.0

    for a_pos, a_neg in zip(alphas_pos, alphas_neg):
        assert math.isclose(a_pos, -a_neg, rel_tol=1e-6, abs_tol=1e-8)


# ---------------------------------------------------------------------
# Step 43: lateral offsets u_B, u_C (architecture.md SS24.3; rocket-2d.tex
# SSGeometry; analysis.tex eq:moment_full). A lateral offset acts exactly
# like a thrust-cant offset on the thrust moment (eq:alpha_trim with M_delta
# replaced by the combined term), so this test mirrors
# `test_misaligned_thrust_trims_stable_airframe_instead_of_diverging` above.
# ---------------------------------------------------------------------


def test_lateral_cog_offset_trims_stable_airframe_like_a_thrust_cant():
    """A statically stable airframe (same fixture as the Step 39 trim
    test) with `u_B != 0` (CoG offset from the body axis, `u_C = 0`) trims
    at a small nonzero `alpha` instead of diverging, exactly like a
    physical thrust cant did in Step 39 -- architecture.md SS24.3's closed
    form says `1mm` of offset over the `l2 = 0.4 m`-ish arm is equivalent
    to a `~0.1 deg`-scale cant. Negating the offset mirrors `alpha(t)`.
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.0, C_N_alpha=2.0, C_m_alpha=0.0,
        motor_curve="placeholder.csv",
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)
    sample_times = [0.1, 0.2, 0.3, 0.4]

    # --- Baseline: u_B = u_C = 0.0 -> the trivial aligned equilibrium ---
    p_baseline = Params(u_B=0.0, u_C=0.0, **common)
    r_baseline = run_sim(p_baseline, s0, t_max=1.0, method="RK45")
    for t in sample_times:
        alpha = flow_state(t, r_baseline.raw.sol(t), p_baseline).alpha
        assert math.isclose(alpha, 0.0, abs_tol=1e-9)

    # --- Positive u_B: alpha(t) takes a consistent, bounded sign --------
    p_pos = Params(u_B=0.001, u_C=0.0, **common)
    r_pos = run_sim(p_pos, s0, t_max=1.0, method="RK45")
    alphas_pos = [flow_state(t, r_pos.raw.sol(t), p_pos).alpha for t in sample_times]
    for a in alphas_pos:
        assert a != 0.0
        assert abs(a) < 0.5  # bounded -- nowhere near the tumbling regime

    # --- Negative u_B: mirrors the positive case almost exactly ---------
    p_neg = Params(u_B=-0.001, u_C=0.0, **common)
    r_neg = run_sim(p_neg, s0, t_max=1.0, method="RK45")
    alphas_neg = [flow_state(t, r_neg.raw.sol(t), p_neg).alpha for t in sample_times]

    for a_pos, a_neg in zip(alphas_pos, alphas_neg):
        assert math.isclose(a_pos, -a_neg, rel_tol=1e-6, abs_tol=1e-8)


# ---------------------------------------------------------------------
# Step 44: pitch-damping c_mq scaffold -- the sign/behaviour test that
# encodes architecture.md SS24.4's sign-convention resolution (positive
# c_mq is DAMPING here, opposite the textbook convention). Reuses the
# project's pinned pitch-oscillation fixture (m=0.5, I=0.05, l1=0.3,
# l2=0.4, S=0.005, d_ref=0.08, C_N_alpha=2.0, C_m_alpha=0.0, V~=100 m/s),
# whose strip-estimate c_mq = 2*C_N_alpha*(l1/d_ref)^2 = 56.25 gives a
# damping rate D = qS*d_ref^2*c_mq/(2VI) = 1.1025/s (architecture.md
# SS24.4's pinned numbers) -- amplitude falls to e^{-D*t/2} of its start.
# ---------------------------------------------------------------------


def _envelope_peaks(result, p, t_max: float, n: int = 2000) -> list:
    """`|alpha(t)|`'s local maxima (dense sampling, simple 3-point extremum
    test) -- occur twice per pitch period (once per sign of `alpha`), so
    consecutive entries are ~half a period apart. Used as the oscillation's
    amplitude envelope without assuming an exact, constant period (`V`
    itself slowly falls under gravity here, with no thrust)."""
    times = np.linspace(0.0, t_max, n)
    abs_alpha = np.array([abs(flow_state(t, result.raw.sol(t), p).alpha) for t in times])
    peaks = []
    for i in range(1, len(abs_alpha) - 1):
        if abs_alpha[i] >= abs_alpha[i - 1] and abs_alpha[i] >= abs_alpha[i + 1]:
            peaks.append(abs_alpha[i])
    return peaks


def test_pitch_damping_sign_convention_decays_undamped_grows():
    """The one real risk this step's spec calls out: getting the sign
    backwards. `c_mq > 0` (the strip value, 56.25) must make a statically
    stable airframe's pitch oscillation decay *faster* than the `c_mq = 0`
    baseline; `c_mq < 0` (the same magnitude, negated) must decay slower
    than that baseline, or grow -- so the three cases' envelope-decay
    ratios come out in the single order `damped < undamped < anti_damped`,
    exactly encoding architecture.md SS24.4's sign resolution (positive
    `c_mq` is DAMPING here, the opposite of the textbook convention).

    Not compared against a literal "no decay at all" baseline: verified
    numerically before writing this test (not assumed) that even `c_mq =
    0` shows *some* gradual envelope decay in the full coupled 2D
    dynamics at this fixture's V0=100 m/s (unlike the coarser, order-of-
    magnitude-only sampling tests/test_forces.py's off-axis test uses at
    V0=60 m/s) -- a real translational/rotational coupling effect (the
    velocity vector partially follows the restoring pitch motion), not an
    explicit damping *term*. That is exactly why the claim here is the
    *relative* ordering of decay rates, not "undamped is flat" -- the
    honest, checked claim, not the stronger one this model does not make.
    """
    common = dict(
        m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_model="coefficients", S=0.005, d_ref=0.08,
        C_A0=0.0, C_N_alpha=2.0, C_m_alpha=0.0,
    )
    alpha0 = -0.15
    theta0 = math.pi / 2 + alpha0
    V0 = 100.0
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=-V0, theta=theta0, omega=0.0)
    t_max = 1.65  # comfortably pre-apogee (V0/g ~= 10.2 s)

    ratios = {}
    for label, c_mq in (("damped", 56.25), ("undamped", 0.0), ("anti_damped", -56.25)):
        p = Params(c_mq=c_mq, **common)
        r = run_sim(p, s0, t_max=t_max, method="RK45")
        assert r.events["apogee"] is None  # confirms t_max stays pre-apogee

        peaks = _envelope_peaks(r, p, t_max)
        assert len(peaks) >= 6, (label, peaks)  # several oscillations captured
        # Mean of the first two / last two peaks -- smooths over the
        # half-period sampling noise a single first/last peak would carry.
        early = (peaks[0] + peaks[1]) / 2.0
        late = (peaks[-2] + peaks[-1]) / 2.0
        ratios[label] = late / early

    # The sharpest single check: getting the sign backwards would reverse
    # this ordering outright, not just shift it slightly.
    assert ratios["damped"] < ratios["undamped"] < ratios["anti_damped"], ratios

    # Damped decays outright (not merely "less than the others").
    assert ratios["damped"] < 0.7, ratios

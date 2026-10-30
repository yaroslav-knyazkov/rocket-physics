"""Tests for the Step 32 3D integration harness (Phase 3;
architecture-37-step32-3d-integration-harness.md). A new, separate file
from `tests/test_dynamics3d.py` (RHS-level 2D/3D cross-checks) and
`tests/test_integrate.py` (pure 2D harness pins, D-77) -- this file is the
*harness*-level 2D/3D regression SS37.6.1 calls for: `run_sim_3d` finding
its own events end to end, not a test calling `solve_ivp` directly.

Sub-step 32.1: the projection seam and event factory
(`_project_identity`/`_events_for`). Sub-step 32.2: `run_sim_3d`'s `RK45`
path + eager validation (SS37.6.1 tests 1, 2, 3, 8; SS37.9 risk 2's
verticality probe). Sub-step 32.3: the `rk4` path + the committed 3D
reference pin (SS37.6.1 tests 4, 7). Sub-step 32.4: the rail/parachute
attitude freeze, `apps.sim.engine.dynamics3d` (SS37.6.1 tests 5, 6).
"""

import math

import numpy as np
import pytest

from apps.sim.engine.integrate import (
    _apogee_event,
    _burnout_event,
    _events_for,
    _ground_event,
    _parachute_deploy_event,
    _project_identity,
    _rail_exit_event,
    run_sim,
    run_sim_3d,
)
from apps.sim.engine.params import (
    Actuator,
    Aero,
    Inertia,
    Lengths,
    Params,
    Recovery,
    Roll,
    Site,
    Thrust,
    Weight,
    with_solver,
)
from apps.sim.engine.quaternion import from_euler
from apps.sim.engine.state import State
from apps.sim.engine.state3d import OMEGA, Q, R, V, to_vector as to_vector_3d, State3D

_MODULE_LEVEL_EVENTS = (
    _ground_event,
    _apogee_event,
    _burnout_event,
    _rail_exit_event,
    _parachute_deploy_event,
)


def test_project_identity_is_a_true_noop():
    y = np.array([1.0, 2.0, 3.0, -4.0, 0.5, 0.1, 0.0])
    out = _project_identity(y)
    assert out is y


def test_events_for_identity_matches_module_level_events_byte_identically():
    """D-32.1/C's own self-test (SS37.7/32.1): `_events_for(_project_identity)`
    must behave EXACTLY like the five module-level event functions on a 2D
    state -- same return value at the same `(t, y, p)`, same `.terminal`/
    `.direction` attributes. This is the proof that the seam introduces no
    behaviour change on the 2D path before any 3D driver exists to use it."""
    wrapped = _events_for(_project_identity)
    assert len(wrapped) == 5

    # Attribute fidelity -- scipy's solve_ivp reads these off the callable
    # itself (module docstring of _events_for).
    for wrapped_fn, original_fn in zip(wrapped, _MODULE_LEVEL_EVENTS):
        assert wrapped_fn.terminal == original_fn.terminal
        assert wrapped_fn.direction == original_fn.direction

    # Behavioural fidelity -- a handful of representative (t, y) pairs,
    # including ones chosen to be near each event's own zero crossing so a
    # sign error in the wrapper (not just a missing attribute) would show.
    from apps.sim.engine.params import Params, Weight, with_solver

    p = with_solver(Params(weight=Weight(m=0.5, I=0.05)), t_max=10.0)

    sample_states = [
        np.array([0.0, 0.0, 10.0, -5.0, 0.0, 0.0, 0.0]),
        np.array([5.0, -100.0, 10.0, 5.0, 0.1, 0.0, 0.0]),
        np.array([5.0, 10.0, 10.0, 5.0, 0.1, 0.0, 0.0]),
    ]
    sample_ts = [0.2, 5.0, 10.0]

    for wrapped_fn, original_fn in zip(wrapped, _MODULE_LEVEL_EVENTS):
        for t in sample_ts:
            for y in sample_states:
                assert wrapped_fn(t, y, p) == original_fn(t, y, p)


def test_events_for_applies_the_given_projection():
    """A non-identity projection must actually be applied before the
    underlying predicate runs -- otherwise the wrapper would silently
    degrade to the identity case regardless of what `project` is."""

    def _project_shift(y):
        # Shifts VZ (index 3) by a fixed amount -- enough to flip the
        # apogee event's sign at a `y` chosen to sit right at the
        # boundary under the identity projection.
        y = np.array(y, dtype=float, copy=True)
        y[3] += 100.0
        return y

    from apps.sim.engine.params import Params, Weight, with_solver

    p = with_solver(Params(weight=Weight(m=0.5, I=0.05)), t_max=10.0)

    wrapped = _events_for(_project_shift)
    apogee_wrapped = wrapped[1]

    y = np.array([0.0, 0.0, 10.0, -1.0, 0.0, 0.0, 0.0])
    t = 1.0

    # Under the identity projection, VZ = -1.0 (rising) -> _apogee_event
    # returns -1.0 directly.
    assert _apogee_event(t, y, p) == -1.0
    # Under the shifted projection, VZ becomes +99.0 -> the SAME predicate
    # body now reports the shifted value, proving `project` was applied.
    assert apogee_wrapped(t, y, p) == 99.0


# ----------------------------------------------------------------------
# Sub-step 32.2: run_sim_3d, RK45 path, eager validation
# ----------------------------------------------------------------------

# Same zero-net-moment scenario as tests/test_dynamics3d.py's own `_P`:
# on-axis thrust, no lateral CoG/thrust offset, `C_z = C_m = 0.0` --
# together these make the pitching moment M_y identically zero for the
# WHOLE flight regardless of theta or l1/l2 (that module's own comment).
# Picked here for the same reason: it makes the 2D and 3D sides integrate
# the SAME physics exactly, not an approximation of it, at any theta0 --
# including right at and past the old arcsin singularity.
_P = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
)
_VX0, _VZ0 = 10.0, -5.0


def _make_2d_3d_states(theta0_rad: float, omega0: float = 0.0):
    """Matching 2D `State` and flat 3D state vector at the same
    (planar) initial condition -- `omega0` is the 2D pitch rate /
    `omega[1]` (3D), the x-z plane's only rotation axis."""
    s0_2d = State(x=0.0, z=0.0, vx=_VX0, vz=_VZ0, theta=theta0_rad, omega=omega0)
    q0 = from_euler(0.0, theta0_rad, 0.0)
    s0_3d = State3D(
        r=np.array([0.0, 0.0, 0.0]),
        v=np.array([_VX0, 0.0, _VZ0]),
        q=q0,
        omega=np.array([0.0, omega0, 0.0]),
    )
    return s0_2d, to_vector_3d(s0_3d)


def _assert_run_sim_3d_matches_run_sim(p, theta0_rad: float, omega0: float = 0.0):
    """SS37.6.1 test 1 (harness-level planar equivalence, RK45): all five
    `events[...]` entries agree and the x/z trajectory agrees to the
    existing `rtol=1e-7, atol=1e-4` tolerance (the same tolerance
    `tests/test_dynamics3d.py`'s own full-trajectory check uses). Returns
    both `Result`s so callers can layer further assertions (e.g. test 2's
    exact-zero checks) without re-running the integration."""
    s0_2d, y0_3d = _make_2d_3d_states(theta0_rad, omega0)
    tight_p = with_solver(p, rtol=1e-11, atol=1e-13)

    result_2d = run_sim(tight_p, s0_2d)
    result_3d = run_sim_3d(tight_p, y0_3d)

    for name in ("ground", "apogee", "burnout", "rail_exit", "parachute_deploy"):
        e2d = result_2d.events[name]
        e3d = result_3d.events[name]
        if e2d is None or e3d is None:
            assert e2d is None and e3d is None, (
                f"event {name!r}: 2D={e2d}, 3D={e3d} -- one fired, the other didn't"
            )
        else:
            assert math.isclose(e2d, e3d, rel_tol=1e-6), (
                f"event {name!r}: 2D={e2d}, 3D={e3d}"
            )

    t_ground = result_2d.events["ground"]
    assert t_ground is not None
    t_samples = np.linspace(0.0, t_ground, 25)
    y2d_samples = result_2d.raw.sol(t_samples)
    y3d_samples = result_3d.raw.sol(t_samples)

    x_2d, z_2d = y2d_samples[0], y2d_samples[1]
    r_3d = y3d_samples[R]
    assert np.allclose(r_3d[0], x_2d, rtol=1e-7, atol=1e-4)
    assert np.allclose(r_3d[2], z_2d, rtol=1e-7, atol=1e-4)

    return result_2d, result_3d


def test_run_sim_3d_matches_run_sim_planar_rk45():
    """SS37.6.1 test 1, the headline harness-level equivalence check --
    THE test that would have caught every bug the harness can have."""
    _assert_run_sim_3d_matches_run_sim(_P, math.radians(45.0))


@pytest.mark.parametrize("theta0_deg", [85.0, 89.0, 90.0])
def test_run_sim_3d_matches_run_sim_near_the_old_singularity(theta0_deg):
    """SS37.9 risk 2's own required probe: `_s2d`'s `atan2` recovery is
    well-conditioned near `theta = +-90 deg` (unlike the old `arcsin`
    form, which was only exact AT 90 deg, not past it) -- this is
    measured here, not assumed, at launch angles at and either side of
    the project's default `rail_angle_deg = 90.0`."""
    _assert_run_sim_3d_matches_run_sim(_P, math.radians(theta0_deg))


def test_run_sim_3d_matches_run_sim_through_a_descent_that_crosses_vertical():
    """SS37.9 risk 2's second required probe: a run whose attitude
    genuinely rotates (nonzero omega0) through `theta = +-90 deg` one or
    more times DURING the flight, not just at t=0 -- exactly the
    situation SS37.0.4 found broken under the old `arcsin` recovery.
    `omega0 = 0.1 rad/s` over this scenario's ~66 s flight carries theta
    through multiple multiples of 90 deg (ascent AND descent), so this
    would have failed hard before sub-step 32.0's fix. Compared via
    sin/cos of theta (SS37.6.2: 2D's theta is unwrapped, `atan2`'s is
    wrapped at +-180 deg, so raw-theta equality is not the right
    assertion once theta leaves one period)."""
    theta0 = math.radians(85.0)
    omega0 = 0.1
    result_2d, result_3d = _assert_run_sim_3d_matches_run_sim(_P, theta0, omega0)

    t_ground = result_2d.events["ground"]
    # The scenario is expected to pass through vertical during the flight
    # -- assert that expectation itself, so a future change to the
    # scenario that stops doing so fails loudly instead of silently
    # weakening this test.
    t_samples = np.linspace(0.0, t_ground, 50)
    theta_2d = result_2d.raw.sol(t_samples)[4]
    assert np.any(np.abs(np.cos(theta_2d)) < 1e-3), (
        "scenario no longer crosses vertical during the flight -- the "
        "whole point of this test"
    )

    y3d_samples = result_3d.raw.sol(t_samples)
    q_3d = y3d_samples[Q]
    from apps.sim.engine.quaternion import to_dcm

    theta_3d = np.array([
        math.atan2(-to_dcm(q_3d[:, i])[2, 0], to_dcm(q_3d[:, i])[0, 0])
        for i in range(len(t_samples))
    ])
    assert np.allclose(np.sin(theta_3d), np.sin(theta_2d), atol=1e-4)
    assert np.allclose(np.cos(theta_3d), np.cos(theta_2d), atol=1e-4)


def test_run_sim_3d_out_of_plane_components_stay_exactly_zero():
    """SS37.6.1 test 2: no out-of-plane leakage through the harness
    (events + crossing code), bit-exact, not `allclose`."""
    s0_2d, y0_3d = _make_2d_3d_states(math.radians(45.0))
    result_3d = run_sim_3d(_P, y0_3d)

    y = result_3d.y
    assert np.all(y[R][1] == 0.0)
    assert np.all(y[V][1] == 0.0)
    assert np.all(y[OMEGA][0] == 0.0)
    assert np.all(y[OMEGA][2] == 0.0)
    assert np.all(y[Q][1] == 0.0)
    assert np.all(y[Q][3] == 0.0)


def test_run_sim_3d_terminates_on_ground_impact_not_t_max():
    """SS37.6.1 test 3: the run stops at ground impact, well inside
    `p.solver.t_max`, not because the clock ran out."""
    s0_2d, y0_3d = _make_2d_3d_states(math.radians(45.0))
    p = with_solver(_P, t_max=300.0)
    result_3d = run_sim_3d(p, y0_3d)

    t_ground = result_3d.events["ground"]
    assert t_ground is not None
    assert t_ground < p.solver.t_max
    assert math.isclose(result_3d.t[-1], t_ground, rel_tol=1e-6)


# ----------------------------------------------------------------------
# SS37.6.1 test 8: the five eager-validation guards (D-32.6, D-32.2)
# ----------------------------------------------------------------------


def _y0_3d_default():
    _s0_2d, y0_3d = _make_2d_3d_states(math.radians(45.0))
    return y0_3d


def test_run_sim_3d_rejects_an_inadmissible_inertia_tensor():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        inertia=Inertia(model="tensor", I_xx=-1.0, I_yy=0.05, I_zz=0.05),
    )
    with pytest.raises(ValueError, match="positive definite"):
        run_sim_3d(p, _y0_3d_default())


def test_run_sim_3d_rejects_the_2d_roll_model():
    p = Params(weight=Weight(m=0.5, I=0.05), roll=Roll(model="free", I_x=1.0))
    with pytest.raises(ValueError, match="double-count roll"):
        run_sim_3d(p, _y0_3d_default())


def test_run_sim_3d_rejects_the_3d_variable_mass_model():
    p = Params(weight=Weight(m=0.5, I=0.05, m_d=0.3))
    with pytest.raises(ValueError, match="variable-mass model"):
        run_sim_3d(p, _y0_3d_default())


def test_run_sim_3d_rejects_sampled_data_and_segmented_rk45():
    p_sampled = with_solver(
        Params(weight=Weight(m=0.5, I=0.05)), sample_rate_hz=20.0
    )
    with pytest.raises(ValueError, match="sample_rate_hz"):
        run_sim_3d(p_sampled, _y0_3d_default())

    p_seg = with_solver(Params(weight=Weight(m=0.5, I=0.05)), method="rk45_seg")
    with pytest.raises(ValueError, match="rk45_seg"):
        run_sim_3d(p_seg, _y0_3d_default())


def test_run_sim_3d_rejects_an_unregistered_actuator_model():
    p = Params(weight=Weight(m=0.5, I=0.05), actuator=Actuator(model="bogus"))
    with pytest.raises(ValueError, match="actuator model"):
        run_sim_3d(p, _y0_3d_default())


# ----------------------------------------------------------------------
# Sub-step 32.3: run_sim_3d, rk4 path + the committed 3D reference pin
# ----------------------------------------------------------------------

# The note's Stage 2 deliverable, finally reachable through the harness
# (SS37.9 "done" item 6): a pure ballistic lob (no thrust, no aero, no
# rotation) so the pin is deterministic, cheap, and depends on nothing
# but gravity + the rk4 stepper + the quaternion machinery -- found by
# direct experimentation (dt=1e-2 keeps the step count small, ~0.15s
# wall time) rather than reusing a motor-curve scenario, which would cost
# an order of magnitude more wall time for no extra pin value (CLAUDE.md:
# only the in-house rk4 is version-stable enough to pin; this scenario
# commits to that path only).
_RK4_PIN_P = with_solver(
    Params(weight=Weight(m=0.5, I=0.05)),
    method="rk4", dt=1e-2, t_max=10.0,
)
_RK4_PIN_THETA0 = math.radians(45.0)
_RK4_PIN_VX0, _RK4_PIN_VZ0 = 10.0, -20.0

_RK4_PIN_Y_FINAL = [
    40.78862380139285, 0.0, 0.0,
    10.0, 0.0, 19.9999757601927,
    0.9238795325112867, 0.0, 0.3826834323650898, 0.0,
    0.0, 0.0, 0.0,
]
_RK4_PIN_T_FINAL = 4.078862380139212
_RK4_PIN_EVENTS = {
    "apogee": 2.039432425955853, "ground": 4.078862380139212,
    "burnout": None, "rail_exit": None, "parachute_deploy": None,
}


def _rk4_pin_y0():
    q0 = from_euler(0.0, _RK4_PIN_THETA0, 0.0)
    s0 = State3D(
        r=np.array([0.0, 0.0, 0.0]),
        v=np.array([_RK4_PIN_VX0, 0.0, _RK4_PIN_VZ0]),
        q=q0,
        omega=np.array([0.0, 0.0, 0.0]),
    )
    return to_vector_3d(s0)


def test_run_sim_3d_rk4_matches_committed_reference_trajectory():
    """SS37.6.1 test 4: the committed `rk4` 3D reference pin, run TWICE
    to confirm determinism (SS37.7/32.3's own gate: "green twice in a
    row"). Only the `rk4` path is pinned -- `RK45` is version-unstable
    (CLAUDE.md, D-77) and is never pinned, on the 3D path or the 2D one.
    """
    y0 = _rk4_pin_y0()

    for _ in range(2):
        r = run_sim_3d(_RK4_PIN_P, y0)
        assert np.array_equal(r.y[:, -1], np.array(_RK4_PIN_Y_FINAL))
        assert r.t[-1] == _RK4_PIN_T_FINAL
        for key, val in _RK4_PIN_EVENTS.items():
            assert r.events[key] == val


def test_run_sim_3d_rk4_quaternion_norm_is_exact_at_every_sample():
    """SS37.6.1 test 7, `rk4` half: D-32.4's per-accepted-step
    renormalisation keeps `norm(q)` exactly 1.0 (to 1e-15) at every
    recorded sample, not merely bounded."""
    y0 = _rk4_pin_y0()
    r = run_sim_3d(_RK4_PIN_P, y0)
    norms = np.linalg.norm(r.y[Q, :], axis=0)
    assert np.max(np.abs(norms - 1.0)) < 1e-15


def test_run_sim_3d_rk45_quaternion_norm_drift_is_bounded():
    """SS37.6.1 test 7, `RK45` half: no renormalisation on this path
    (D-32.4 -- scipy's adaptive solver has no accessible accepted-step
    hook), so `abs(norm(q) - 1)` is a MEASURED, bounded quantity, not an
    exact one -- a genuinely rotating scenario (nonzero omega0, a tensor
    inertia model) through ground impact, tight solver tolerance (same
    `rtol=1e-11, atol=1e-13` precedent as `tests/test_dynamics3d.py`'s
    own full-trajectory checks)."""
    I_val = 0.05
    p = Params(
        weight=Weight(m=0.5, I=I_val),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(S=0.00442, d_ref=0.075, C_x=0.5, C_z=0.0, C_m=0.003),
        inertia=Inertia(model="tensor", I_xx=1.0e-4, I_yy=I_val, I_zz=I_val),
    )
    p = with_solver(p, t_max=40.0, rtol=1e-11, atol=1e-13)
    q0 = from_euler(0.0, math.radians(45.0), 0.0)
    s0 = State3D(
        r=np.array([0.0, 0.0, 0.0]),
        v=np.array([10.0, 0.0, -5.0]),
        q=q0,
        omega=np.array([0.0, 0.1, 0.0]),
    )
    y0 = to_vector_3d(s0)

    r = run_sim_3d(p, y0)
    assert r.events["ground"] is not None  # the scenario is expected to reach the ground
    norms = np.linalg.norm(r.y[Q, :], axis=0)
    assert np.max(np.abs(norms - 1.0)) < 1e-9


# ----------------------------------------------------------------------
# Sub-step 32.4: the rail and parachute attitude freeze (D-32.5)
# ----------------------------------------------------------------------


def test_run_sim_3d_rail_freeze_holds_attitude_exactly_constant():
    """SS37.6.1 test 5: while `rail_distance < L_rail`, `q` and `omega`
    are exactly constant through the harness, DESPITE a genuine nonzero
    moment being available to act (nozzle misalignment + a tensor
    inertia model -- a negative control: without the freeze this
    scenario visibly rotates, found by direct experimentation). After
    rail exit they move, and the 2D `rail_exit` time matches."""
    I_val = 0.05
    p = Params(
        weight=Weight(m=0.5, I=I_val),
        lengths=Lengths(l1=0.3, l2=0.4, misalign_deg=5.0),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
        site=Site(L_rail=3.0, rail_angle_deg=90.0),
        inertia=Inertia(model="tensor", I_xx=1.0e-4, I_yy=I_val, I_zz=I_val),
    )
    theta0 = math.radians(90.0)
    q0 = from_euler(0.0, theta0, 0.0)
    s0_3d = State3D(r=np.zeros(3), v=np.zeros(3), q=q0, omega=np.zeros(3))
    y0 = to_vector_3d(s0_3d)

    p_rk4 = with_solver(p, method="rk4", dt=1e-3, t_max=5.0)
    r = run_sim_3d(p_rk4, y0)

    t_rail_exit = r.events["rail_exit"]
    assert t_rail_exit is not None
    idx_exit = int(np.searchsorted(r.t, t_rail_exit))

    q_hist = r.y[Q, :idx_exit]
    omega_hist = r.y[OMEGA, :idx_exit]
    assert np.all(q_hist == q_hist[:, 0:1])  # bit-exact, broadcasting against the first column
    assert np.all(omega_hist == 0.0)

    # Negative control: once off the rail, the misalignment moment is
    # free to act -- omega must have moved away from zero. Without this
    # assertion the test above would also pass if the moment were
    # (bugged into being) zero everywhere.
    assert not np.all(r.y[OMEGA, idx_exit + 50] == 0.0)

    s0_2d = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=theta0, omega=0.0)
    r_2d = run_sim(with_solver(p, method="rk4", dt=1e-3, t_max=5.0), s0_2d)
    assert math.isclose(t_rail_exit, r_2d.events["rail_exit"], rel_tol=1e-6)


def test_run_sim_3d_parachute_freeze_holds_attitude_exactly_constant():
    """SS37.6.1 test 6: once `parachute_deploy` fires, `q` is exactly
    constant for the rest of the flight -- DESPITE a nonzero prescribed
    `omega` that would otherwise keep rotating it (`p.inertia.model ==
    "none"`: `omega` is held constant throughout by that model regardless
    of the freeze, so the load-bearing assertion here is specifically
    that `q` stops following it once chuted). Descent rate matches the
    2D terminal velocity exactly (both sides integrate the identical
    canopy-drag formula through the same `_s2d` projection)."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        recovery=Recovery(model="deploy", trigger="apogee", Cd=0.8, S=0.05),
    )
    theta0 = math.radians(80.0)
    omega0 = 0.3
    q0 = from_euler(0.0, theta0, 0.0)
    s0_3d = State3D(
        r=np.zeros(3), v=np.array([5.0, 0.0, -20.0]), q=q0,
        omega=np.array([0.0, omega0, 0.0]),
    )
    y0 = to_vector_3d(s0_3d)

    p_rk4 = with_solver(p, method="rk4", dt=1e-3, t_max=20.0)
    r = run_sim_3d(p_rk4, y0)

    t_dep = r.events["parachute_deploy"]
    assert t_dep is not None
    idx_dep = int(np.searchsorted(r.t, t_dep))

    # Negative control first: q is ACTIVELY changing before deploy (the
    # prescribed omega is doing real work), so the post-deploy freeze
    # below is not vacuous.
    assert not np.allclose(r.y[Q, 0], r.y[Q, idx_dep])

    # The ONE rk4 step straddling the deploy crossing blends frozen and
    # unfrozen RHS evaluations across its four stages (dynamics3d.py's
    # own module docstring: `forces.parachute_deployed` is a smooth,
    # RHS-computable predicate, not a refined event -- same as 2D's
    # `chuted` branch), so it is bit-exact only from the step AFTER that
    # one; measured directly (`idx_dep`/`idx_dep+1` differ at the 1-ULP
    # level, `idx_dep+2` on is exactly 0.0).
    q_after = r.y[Q, idx_dep + 2:]
    assert np.all(q_after == q_after[:, 0:1])  # bit-exact

    s0_2d = State(x=0.0, z=0.0, vx=5.0, vz=-20.0, theta=theta0, omega=omega0)
    r_2d = run_sim(with_solver(p, method="rk4", dt=1e-3, t_max=20.0), s0_2d)
    assert math.isclose(t_dep, r_2d.events["parachute_deploy"], rel_tol=1e-6)
    assert math.isclose(r.y[5, -1], r_2d.y[3, -1], rel_tol=1e-9)  # terminal vz

"""Tests for the burnout event added in sim/integrate.py (roadmap.md
Step 14). Physics/numerics sanity checks only, per the project's testing
philosophy -- no fixtures, no conftest.py, plain `assert` + `math.isclose`.
"""

import math
from unittest.mock import MagicMock

import numpy as np
import pytest
from scipy.integrate import solve_ivp as _scipy_solve_ivp

from sim.integrate import (
    _apogee_event, _burnout_event, _ground_event, _parachute_deploy_event,
    _pending_events, _rail_exit_event, _SegmentedSol, run_sim,
)
from sim.params import (
    Aero, Atmosphere, Gravity, Lengths, Params, Recovery, Site, Soundings, Thrust, Weight, Wind,
    with_solver,
)
from sim.state import State, Z, to_vector


# data/motors/placeholder.csv burns from t=0 (thrust=0) up through an
# ignition spike, a flat sustain, and a linear tail-off that reaches zero
# exactly at t=2.0 s -- see that file's header comment.
BURNOUT_EXPECTED = 2.0
BURNOUT_TOL = 0.05


def test_rk45_burnout_event_detected():
    """RK45's solve_ivp-based burnout event fires once, at the curve's
    tail-off-to-zero time, and not spuriously at t=0 (the curve starts at
    zero thrust and rises on ignition, which `direction=-1` excludes).
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(p, s0)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    assert math.isclose(t_burnout, BURNOUT_EXPECTED, abs_tol=BURNOUT_TOL)


def test_rk4_burnout_event_detected():
    """Same check for the hand-written fixed-step RK4 path (`method="rk4"`),
    which locates the burnout crossing by linear interpolation within the
    one step that straddles it (same approach as apogee/ground there).
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(with_solver(p, method="rk4", dt=1e-3), s0)

    t_burnout = result.events["burnout"]
    assert t_burnout is not None
    assert math.isclose(t_burnout, BURNOUT_EXPECTED, abs_tol=BURNOUT_TOL)


def test_no_burnout_event_when_no_curve():
    """With no motor curve (`motor_curve=""`, thrust is zero throughout),
    thrust never goes from positive to negative, so the burnout event must
    never fire for either integrator.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve=""),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    rk45 = run_sim(with_solver(p, t_max=5.0), s0)
    rk4 = run_sim(with_solver(p, method="rk4", t_max=5.0, dt=1e-3), s0)

    assert rk45.events["burnout"] is None
    assert rk4.events["burnout"] is None


# ---------------------------------------------------------------------
# Step 45 (Phase 2.8; architecture.md SS25.5): Result.params, the untouched
# apogee event, and the bit-for-bit regression under the default
# "parallel" gravity_direction.
# ---------------------------------------------------------------------


def test_result_params_is_p_on_both_integrator_paths():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    p_rk4 = with_solver(p, method="rk4", dt=1e-3)
    r_rk45 = run_sim(p, s0)
    r_rk4 = run_sim(p_rk4, s0)

    assert r_rk45.params is p
    assert r_rk4.params is p_rk4


def test_apogee_event_attributes_unchanged():
    """architecture.md SS25.8's hard line: `_apogee_event` stays
    `direction=1`, `terminal=False` -- Step 45 does not touch the event
    trigger, only the reported altitude value."""
    assert _apogee_event.direction == 1
    assert _apogee_event.terminal is False


# Tilted, curvature-exercising scenario (gravity_model="wgs84",
# atmosphere_model="isa" (default), aero_model="linearized",
# wind_model="analytic") under the default gravity_direction="parallel" --
# pinned final-state/event values captured from the pre-Step-45 code (the
# unedited repository, before sim/gravity.py/sim/flow.py/sim/atmosphere.py/
# sim/wind.py/sim/integrate.py were touched), proving the post-Step-45
# physics is bit-for-bit identical under the flat default (architecture.md
# SS25.6). x != 0 throughout, so a mistake in the flat branch of the new
# altitude_agl/altitude_msl call sites would show up here -- the vertical
# run.py scenario (x == 0 always) could not catch it.
_TILT_PARAMS = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.5, C_N_alpha=2.0, C_m_alpha=-0.5),
    gravity=Gravity(model="wgs84"),
    atmosphere=Atmosphere(model="isa"),
    wind=Wind(model="analytic", ref_ms=5.0, ref_h_m=10.0, shear_exp=0.143, dir_deg=45.0),
    site=Site(lat0_deg=50.0, azimuth_deg=90.0),
)
_TILT_S0 = State(x=0.0, z=0.0, vx=50.0, vz=0.0, theta=math.radians(80.0), omega=0.0)

# RK45 pins re-recorded 2026-10-15 (D-77, user-approved): scipy 1.18.1 /
# numpy 2.5.4 move solve_ivp's RK45 result at round-off level (~1e-14
# relative); the project's own rk4 path below is unchanged bit-for-bit.
_TILT_PINNED = {
    "RK45": dict(
        y_final=[634.8103836834275, -5.4817261840867104e-15, 59.61236937554152,
                 19.52923203571373, -0.3106550930107851, -0.2986216972287503, 0.0],
        t_final=5.393359857760246,
        events={"apogee": 2.6382969670047016, "ground": 5.393359857760246,
                "burnout": 1.9999999999955556},
    ),
    "rk4": dict(
        y_final=[634.8102578513177, 0.0, 59.61236364096141, 19.529231848850742,
                 -0.3106546467112906, -0.29862245176650026, 0.0],
        t_final=5.39335961920151,
        events={"apogee": 2.6382986765214778, "ground": 5.39335961920151,
                "burnout": 2.0009999999998906},
    ),
}

# Same scenario's aero/motor setup, but atmosphere_model/wind_model
# switched to tier 2 ("sounding"), the committed `example` case (LKPR),
# h0_m matching its elevation -- covers the tier-2 code path too
# (architecture.md SS25.9).
_TILT_SOUNDING_PARAMS = Params(
    weight=Weight(m=0.5, I=0.05),
    lengths=Lengths(l1=0.3, l2=0.4),
    thrust=Thrust(motor_curve="placeholder.csv"),
    aero=Aero(model="linearized", S=0.005, d_ref=0.08, C_A0=0.5, C_N_alpha=2.0, C_m_alpha=-0.5),
    atmosphere=Atmosphere(model="sounding"),
    wind=Wind(model="sounding"),
    soundings=Soundings(case="example"),
    site=Site(h0_m=380.0),
)

# RK45 pins re-recorded 2026-10-15 (D-77, user-approved): scipy 1.18.1 /
# numpy 2.5.4 move solve_ivp's RK45 result at round-off level (~1e-14
# relative); the project's own rk4 path below is unchanged bit-for-bit.
_TILT_SOUNDING_PINNED = {
    "RK45": dict(
        y_final=[787.754688433039, 4.003741782554471e-15, 48.82342057638281,
                 27.408071824539135, -0.5404909185805109, -0.13152735823982897, 0.0],
        t_final=7.384917372272603,
        events={"apogee": 3.4708868647803905, "ground": 7.384917372272603,
                "burnout": 1.9999999999955556},
    ),
    "rk4": dict(
        y_final=[787.7545563968736, 0.0, 48.82342798836863, 27.408066606348907,
                 -0.5404908148143166, -0.13153004089547823, 0.0],
        t_final=7.384916047480754,
        events={"apogee": 3.4708865903771247, "ground": 7.384916047480754,
                "burnout": 2.0009999999998906},
    ),
}


def test_tilted_run_bit_for_bit_under_parallel_both_integrators():
    """architecture.md SS25.9's headline regression check: a tilted
    (x != 0 throughout), every-altitude-consumer-exercising scenario
    (gravity_model="wgs84", atmosphere_model="isa", aero_model=
    "coefficients", wind_model="analytic"), under the default
    gravity_direction="parallel", reproduces the pre-Step-45 events/t/y
    bit-for-bit (`np.array_equal`), on both integrator paths."""
    p = _TILT_PARAMS

    r_rk45 = run_sim(p, _TILT_S0)
    pin = _TILT_PINNED["RK45"]
    assert np.array_equal(r_rk45.y[:, -1], np.array(pin["y_final"]))
    assert r_rk45.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk45.events[key] == val

    r_rk4 = run_sim(with_solver(p, method="rk4", dt=1e-3), _TILT_S0)
    pin = _TILT_PINNED["rk4"]
    assert np.array_equal(r_rk4.y[:, -1], np.array(pin["y_final"]))
    assert r_rk4.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk4.events[key] == val


def test_tilted_sounding_run_bit_for_bit_under_parallel_both_integrators():
    """Same regression, tier-2 atmosphere/wind (the committed `example`
    sounding case), covering the sounding call sites (architecture.md
    SS25.9's "repeat once with atmosphere_model=sounding + wind_model=
    sounding on the committed example case")."""
    p = _TILT_SOUNDING_PARAMS

    r_rk45 = run_sim(p, _TILT_S0)
    pin = _TILT_SOUNDING_PINNED["RK45"]
    assert np.array_equal(r_rk45.y[:, -1], np.array(pin["y_final"]))
    assert r_rk45.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk45.events[key] == val

    r_rk4 = run_sim(with_solver(p, method="rk4", dt=1e-3), _TILT_S0)
    pin = _TILT_SOUNDING_PINNED["rk4"]
    assert np.array_equal(r_rk4.y[:, -1], np.array(pin["y_final"]))
    assert r_rk4.t[-1] == pin["t_final"]
    for key, val in pin["events"].items():
        assert r_rk4.events[key] == val


# ---------------------------------------------------------------------
# Step 59 (Phase 2.11 rewrite pass; architecture-28-rewrite.md SS28.8):
# the opt-in sampled-data/zero-order-hold mode's gate -- `run_sim`'s own
# `ValueError`/dispatch behaviour. The hold mechanism itself (sim/
# sampling.py) is tested in tests/test_sampling.py.
# ---------------------------------------------------------------------


def test_sample_rate_hz_zero_explicit_is_bit_for_bit_the_implicit_default():
    """`p.solver.sample_rate_hz = 0.0` is the implicit default on every
    `Solver()` already built throughout this suite -- this test exercises
    the gate variable explicitly (`with_solver(..., sample_rate_hz=0.0)`)
    on both integration paths and proves it is bit-for-bit identical to
    never having set it at all: the off switch is a genuine no-op at
    exactly zero, the same standard every other model-selection gate in
    this project meets (`m_d is None`, `L_rail == 0.0`, `wind_model ==
    "none"`)."""
    p = _TILT_PARAMS

    for method, dt in (("RK45", None), ("rk4", 1e-3)):
        kw = {"method": method}
        if dt is not None:
            kw["dt"] = dt
        p_implicit = with_solver(p, **kw)
        p_explicit = with_solver(p, sample_rate_hz=0.0, **kw)

        r_implicit = run_sim(p_implicit, _TILT_S0)
        r_explicit = run_sim(p_explicit, _TILT_S0)

        assert np.array_equal(r_implicit.y, r_explicit.y)
        assert np.array_equal(r_implicit.t, r_explicit.t)
        assert r_implicit.events == r_explicit.events


def test_rk45_with_nonzero_sample_rate_raises_immediately():
    """architecture-28-rewrite.md SS28.8.2 (decision D-11): an adaptive
    method (the default `"RK45"`, or any other scipy method name) combined
    with `p.solver.sample_rate_hz > 0.0` must raise `ValueError`
    immediately -- adaptive stepping cannot honour a zero-order-hold
    boundary. Checked before any integration is attempted (the default
    `method="RK45"` here would otherwise run to completion)."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    with pytest.raises(ValueError):
        run_sim(with_solver(p, sample_rate_hz=10.0), s0)


def test_non_rk4_other_method_with_nonzero_sample_rate_also_raises():
    """The gate checks `method != "rk4"`, not merely `method == "RK45"` --
    any other scipy method name combined with a nonzero sample rate must
    raise the same way."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    with pytest.raises(ValueError):
        run_sim(with_solver(p, method="RK23", sample_rate_hz=10.0), s0)


def test_non_integer_sample_ratio_raises_not_silently_rounds():
    """architecture-28-rewrite.md SS28.8.2, point 3: `T_s/dt` must be an
    exact integer multiple; a non-integer ratio must raise `ValueError`,
    not silently round to the nearest integer number of substeps (which
    would change the effective sample rate from the one configured
    without telling the caller).

    `dt=1e-3`, `sample_rate_hz=7.0` -> `T_s=1/7 s`, `T_s/dt ~= 142.857`,
    not an integer.
    """
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    with pytest.raises(ValueError):
        run_sim(with_solver(p, method="rk4", dt=1e-3, sample_rate_hz=7.0), s0)


def test_integer_sample_ratio_does_not_raise():
    """The converse of the test above: a `T_s/dt` that genuinely is an
    exact integer multiple (`dt=1e-3`, `sample_rate_hz=10.0` ->
    `T_s/dt=100.0`) must run to completion without raising."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk4", dt=1e-3, sample_rate_hz=10.0), s0)
    assert r.t[-1] > 0.0


# ---------------------------------------------------------------------
# Step 104 (Phase 2.17; D-116/D-128; task-104-segmented-rk45.md): a second,
# also opt-in sampled-data path -- `p.solver.method == "rk45_seg"`. Mirrors
# the Step 59 gate-test section above's own style; see task-104-segmented-
# rk45.md SS104.11 for the full test plan this section implements.
# ---------------------------------------------------------------------


def test_rk45_seg_without_sample_rate_raises():
    """`method="rk45_seg"` requires `sample_rate_hz > 0.0` (SS104.2's new
    symmetric gate) -- the sentinel method with the field default
    (`sample_rate_hz=0.0`) must raise immediately."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    with pytest.raises(ValueError):
        run_sim(with_solver(p, method="rk45_seg"), s0)


def test_rk45_seg_with_sample_rate_does_not_raise():
    """The converse: `method="rk45_seg"` with a positive `sample_rate_hz`
    runs to completion -- `dt` is irrelevant to this path (SS104.9) and
    must not trigger any `dt`-shaped error (unlike `rk4`'s own T_s/dt
    integer-multiple gate)."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=10.0), s0)
    assert r.t[-1] > 0.0


# -- _pending_events: pure function, no solve_ivp call (SS104.5) --------


def test_pending_events_includes_ground_and_all_four_when_nothing_found():
    found = {"apogee": None, "burnout": None, "rail_exit": None, "parachute_deploy": None}
    names, fns = _pending_events(found)
    assert names == ["ground", "apogee", "burnout", "rail_exit", "parachute_deploy"]
    assert fns == [_ground_event, _apogee_event, _burnout_event, _rail_exit_event, _parachute_deploy_event]


def test_pending_events_drops_an_already_found_event():
    found = {"apogee": None, "burnout": 1.23, "rail_exit": None, "parachute_deploy": None}
    names, fns = _pending_events(found)
    assert "burnout" not in names
    assert names == ["ground", "apogee", "rail_exit", "parachute_deploy"]
    assert fns == [_ground_event, _apogee_event, _rail_exit_event, _parachute_deploy_event]


def test_pending_events_returns_only_ground_when_all_four_found():
    found = {"apogee": 1.0, "burnout": 2.0, "rail_exit": 3.0, "parachute_deploy": 4.0}
    names, fns = _pending_events(found)
    assert names == ["ground"]
    assert fns == [_ground_event]


# -- _SegmentedSol: stitching, no run_sim call (SS104.6) -----------------
#
# A trivial dy/dt = 1 (6 components), each segment continuing the previous
# one's own end state, so the analytic value at any `t` is just `t`
# (broadcast across all 6 components) regardless of which segment answers.


def _trivial_dense_sol(t_start, t_end, y_start):
    sol = _scipy_solve_ivp(
        lambda t, y: np.ones(6), (t_start, t_end), y_start, dense_output=True,
    )
    return sol.sol


def _three_segments():
    """3 segments covering [0,1), [1,2), [2,3], each wrapped in a
    `MagicMock` spy (delegating to the real dense interpolant) so tests can
    pin WHICH segment answered a given query, not just the numeric value."""
    starts = [0.0, 1.0, 2.0]
    raw_sols = [
        _trivial_dense_sol(0.0, 1.0, np.zeros(6)),
        _trivial_dense_sol(1.0, 2.0, np.ones(6)),
        _trivial_dense_sol(2.0, 3.0, 2.0 * np.ones(6)),
    ]
    spies = [MagicMock(side_effect=raw) for raw in raw_sols]
    return starts, spies


def test_segmented_sol_scalar_t_matches_the_right_segment():
    for t, seg_idx in ((0.5, 0), (1.5, 1), (2.999, 2)):
        starts, spies = _three_segments()
        stitched = _SegmentedSol(starts, spies)
        out = stitched(t)
        assert out.shape == (6,)
        assert np.allclose(out, t)
        assert spies[seg_idx].call_count == 1
        for i, spy in enumerate(spies):
            if i != seg_idx:
                assert spy.call_count == 0


def test_segmented_sol_array_t_spanning_multiple_segments():
    starts, spies = _three_segments()
    stitched = _SegmentedSol(starts, spies)

    t_grid = np.array([0.1, 0.9, 1.2, 1.8, 2.1, 2.9])
    out = stitched(t_grid)
    assert out.shape == (6, t_grid.size)
    assert np.allclose(out, t_grid)  # broadcasts across the 6 rows

    # Cross-check against a per-element scalar call on a FRESH set of
    # segments (so call-count assertions above stay uncontaminated) --
    # proves the vectorised np.unique-grouped path agrees with the scalar
    # path, element by element.
    starts2, spies2 = _three_segments()
    scalar_stitched = _SegmentedSol(starts2, spies2)
    for i, t in enumerate(t_grid):
        assert np.allclose(out[:, i], scalar_stitched(float(t)))


def test_segmented_sol_boundary_t_pins_the_selected_segment():
    """`t` exactly on a shared boundary (`t=1.0`, shared between segment 0's
    own end and segment 1's own start) must agree numerically (both
    segments' dense interpolants reproduce the same continuous trajectory
    value there), but this test pins WHICH segment the implementation
    actually delegates to via the spy, so a future refactor that flips the
    tie-break is caught. `np.searchsorted(starts, t, side="right") - 1`
    (SS104.6's own formula) resolves `t == starts[k]` to segment `k` itself
    (the segment that OWNS that instant as its own first point) -- segment
    1 here, not segment 0 -- confirmed directly against the formula before
    writing this assertion (not assumed from the class docstring's looser
    "earlier segment" phrasing, which this test's own naming corrects)."""
    starts, spies = _three_segments()
    stitched = _SegmentedSol(starts, spies)

    out = stitched(1.0)
    assert np.allclose(out, 1.0)
    assert spies[1].call_count == 1
    assert spies[0].call_count == 0
    assert spies[2].call_count == 0


# -- Integration-level tests: real run_sim(method="rk45_seg") ------------


def test_rk45_seg_result_t_is_strictly_increasing_no_duplicate_boundaries():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=5.0), s0)
    assert np.all(np.diff(r.t) > 0)


def test_rk45_seg_degenerate_t_max_zero_does_not_crash_raw_sol():
    """Regression (found in code-review, not anticipated by
    task-104-segmented-rk45.md SS104.9's own "no new guard needed"
    reasoning): `t_max=0.0` makes `_run_segmented_rk45`'s own `while` loop
    never run, so `seg_sols` is empty -- `_SegmentedSol([], [])` would
    `IndexError` on the very first `raw.sol(t)` call. The sibling `rk4`
    and plain-RK45 paths both degrade gracefully (constant extrapolation
    of the single initial point) on the same input; `rk45_seg` must too."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=0.0), s0)
    assert r.t.shape == (1,)
    # Step 109 audit (task-109-roll-reaction-wheel.md SS109.9): `State` grew
    # three roll fields, so a bare `np.array(s0)` is now 10-wide while
    # `r.raw.sol(t)` stays 7-wide (`p.roll.model` defaults to "none" here) --
    # `state.to_vector(s0, p)` is the width-matched, bit-for-bit replacement.
    assert np.allclose(r.raw.sol(0.0), to_vector(s0, p))
    assert np.allclose(r.raw.sol(5.0), to_vector(s0, p))  # constant extrapolation, same as _run_rk4's


def test_rk45_seg_raw_sol_matches_result_y_at_every_stored_t():
    """The test most likely to catch a stitching/boundary bug (SS104.11
    test 11): the dense, stitched `raw.sol(t)` must self-consistently agree
    with the stored discrete grid `(r.t, r.y)` it was built from."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=5.0), s0)
    idxs = np.linspace(0, len(r.t) - 1, 25, dtype=int)
    for i in idxs:
        assert np.allclose(r.raw.sol(r.t[i]), r.y[:, i], atol=1e-6)


def test_rk45_seg_ground_event_terminates_the_whole_run():
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    # Ground impact for this scenario is at t~=65.5s (confirmed directly,
    # not assumed); t_max=70.0 comfortably reaches it without reaching the
    # t_max clip instead.
    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=70.0), s0)
    assert r.events["ground"] is not None
    assert r.t[-1] <= 70.0
    assert math.isclose(r.t[-1], r.events["ground"], rel_tol=1e-6, abs_tol=1e-6)


def test_rk45_seg_each_of_the_four_events_fires_at_most_once():
    """Type/shape regression (SS104.11 test 13): every one of the four
    first-occurrence events is `None` or a single `float`, never a list --
    a full-flight scenario exercising burnout, rail-exit, and a timer-
    triggered parachute deploy, all before ground impact."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(C_x=0.5, C_z=0.0, C_m=0.0),
        site=Site(L_rail=0.5),
        recovery=Recovery(model="deploy", trigger="timer", deploy_time=3.0, Cd=0.8, S=0.5),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=30.0), s0)
    for name in ("apogee", "burnout", "rail_exit", "parachute_deploy"):
        v = r.events[name]
        assert v is None or isinstance(v, float)
    # This scenario is built to exercise all four -- confirm none is
    # silently None (would mask a real regression to "never fires").
    assert r.events["burnout"] is not None
    assert r.events["rail_exit"] is not None
    assert r.events["parachute_deploy"] is not None
    assert r.events["apogee"] is not None


_SEG_RK45_TOL_S = 0.1  # loose cross-check tolerance between two DIFFERENT integrators
_SEG_RK45_TOL_M = 1.0


def test_rk45_seg_agrees_with_rk4_sampled_within_tolerance():
    """Cross-check in the spirit of tests/test_dynamics.py's existing
    `alt_rk45` vs `alt_rk4` comparison for the two un-sampled integrators
    (SS104.11 test 14) -- `rk45_seg` and `rk4`+ZOH are different
    integrators under the SAME sampled-data config and are not expected to
    be bit-identical, only to agree on apogee time/altitude within a loose,
    named tolerance."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    # Apogee for this scenario is at t~=33.2s (confirmed directly, not
    # assumed); t_max=40.0 comfortably reaches it.
    r_seg = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=40.0), s0)
    r_rk4 = run_sim(with_solver(p, method="rk4", dt=1e-4, sample_rate_hz=20.0, t_max=40.0), s0)

    assert r_seg.events["apogee"] is not None
    assert r_rk4.events["apogee"] is not None
    assert math.isclose(r_seg.events["apogee"], r_rk4.events["apogee"], abs_tol=_SEG_RK45_TOL_S)

    alt_seg = -r_seg.raw.sol(r_seg.events["apogee"])[Z]
    alt_rk4 = -r_rk4.raw.sol(r_rk4.events["apogee"])[Z]
    assert math.isclose(alt_seg, alt_rk4, abs_tol=_SEG_RK45_TOL_M)


def test_rk45_seg_with_default_airbrake_model_is_a_no_controller_passthrough():
    """Basic smoke test (SS104.11 test 15): the default
    `control.airbrake_model == "none"` requires no controller to exist --
    `rk45_seg` runs to completion through `sampling.sample`'s existing
    single `"airbrake"` channel exactly as `rk4`+ZOH already does."""
    p = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
    )
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    r = run_sim(with_solver(p, method="rk45_seg", sample_rate_hz=20.0, t_max=5.0), s0)
    assert r.t[-1] > 0.0

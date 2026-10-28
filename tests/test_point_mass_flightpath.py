"""tests/test_point_mass_flightpath.py -- Step 137 (Phase 2.17,
dev/docs/task-136-137-point-mass-flight-path-angle.md TBD-1/SS8.1):
acceptance tests for the point-mass flight-path-angle diagnostic
(`apps._shared.flight_stats.point_mass_flightpath`).

Pure post-processing over an already-simulated `Result` -- no
`apps/sim/engine/` file is touched by the module under test, so these
tests exercise only `apps/_shared/flight_stats.py`'s additive code.

Sign convention (ticket SS4.1, inherited from `rocket-2d.tex:9-12`): `z`
points DOWN, so a climbing rocket has `vz < 0` and `theta_v > 0`.
"""

import math

import numpy as np

from apps._shared.flight_stats import flight_path_angle, point_mass_flightpath
from apps.input.demo_scenario import DEMO_SCENARIO
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import Aero, Lengths, Params, Weight
from apps.sim.engine.state import State
from apps.sim.schema import assemble

# ----------------------------------------------------------------------
# 1. theta_v of a purely vertical ascent/descent is +-90 deg.
# ----------------------------------------------------------------------


def test_theta_v_vertical_ascent_is_plus_90_degrees():
    theta_v = flight_path_angle(vx=0.0, vz=-50.0)  # climbing: vz < 0
    assert math.isclose(theta_v, math.pi / 2, abs_tol=1e-12)


def test_theta_v_vertical_descent_is_minus_90_degrees():
    theta_v = flight_path_angle(vx=0.0, vz=50.0)  # descending: vz > 0
    assert math.isclose(theta_v, -math.pi / 2, abs_tol=1e-12)


def test_theta_v_is_vectorised_over_an_array():
    theta_v = flight_path_angle(vx=np.array([0.0, 0.0]), vz=np.array([-50.0, 50.0]))
    assert np.allclose(theta_v, [math.pi / 2, -math.pi / 2])


# ----------------------------------------------------------------------
# 2. Still-air residual theta - alpha - theta_v is an EXACT identity
#    (< 1e-9 rad), across a full DEMO_SCENARIO run -- the real test of
#    ticket SS4.7. Excludes the single on-pad instant V == 0, where the
#    identity is genuinely undefined (atan2(0, 0) degenerate case,
#    documented identically in flow_state's own docstring), not merely
#    imprecise.
# ----------------------------------------------------------------------


def test_still_air_residual_is_exact_zero_across_demo_run():
    cfg = assemble(DEMO_SCENARIO)
    result = run_sim(cfg.params, cfg.s0)

    diag = point_mass_flightpath(result, cfg.params)

    moving = diag.V > 1e-6
    assert moving.sum() > 0.9 * diag.V.size  # the V == 0 instant is a single grid point, not a window
    assert np.max(np.abs(diag.still_air_residual[moving])) < 1e-9


# ----------------------------------------------------------------------
# 3. Drag-free, aero-free, thrust-free ballistic coast: the point-mass
#    model is EXACT for theta_v_dot (A1-A5 all hold exactly, with no
#    drag/lift/thrust/rotation at all), so theta_v_dot_actual must match
#    theta_v_dot_pointmass to a true oracle tolerance, not a fudge.
# ----------------------------------------------------------------------


def test_ballistic_coast_matches_pointmass_rate_within_one_percent():
    v0 = 60.0
    angle = math.radians(50.0)
    p = Params(
        weight=Weight(m=1.0, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        aero=Aero(C_x=0.0, C_z=0.0, C_m=0.0),  # drag-free, aero-free
    )  # default Thrust() -- thrust-free, same precedent as test_analytic.py's vacuum shot
    s0 = State(
        x=0.0, z=0.0,
        vx=v0 * math.cos(angle), vz=-v0 * math.sin(angle),
        theta=math.pi / 2, omega=0.0,
    )
    result = run_sim(p, s0)

    diag = point_mass_flightpath(result, p)

    # vx is exactly constant (no drag, no thrust -> a_x == 0 always), so
    # V is never 0 anywhere in this fixture -- no masking needed.
    assert np.all(diag.V > 0.0)
    rel_err = np.abs(diag.theta_v_dot_actual - diag.theta_v_dot_pointmass) / np.abs(
        diag.theta_v_dot_pointmass
    )
    assert np.nanmax(rel_err) < 0.01


# ----------------------------------------------------------------------
# 4. lambda_ratio: "else None" on DEMO_SCENARIO itself (aero.model ==
#    "constant" has an identically-zero alpha-slope, so M_alpha == 0
#    everywhere -- a genuine finding, not a bug, see flight_stats.py's
#    point_mass_flightpath docstring), and a real, finite, >0.1-somewhere
#    Lambda on a derived fixture with an alpha-dependent ("linearized")
#    aero model -- confirming the >0.1 region is the low-speed one
#    section 5 predicts.
# ----------------------------------------------------------------------


def test_lambda_ratio_is_unavailable_on_demo_scenario_constant_aero_model():
    """DEMO_SCENARIO's aero.model == "constant" coefficients are literally
    alpha-independent (apps/sim/engine/aero.py's _constant_coeffs), so
    M_alpha is identically 0 and omega_n is not a real, positive number
    anywhere -- lambda_ratio must be NaN ("else None") everywhere, not a
    fabricated value."""
    cfg = assemble(DEMO_SCENARIO)
    result = run_sim(cfg.params, cfg.s0)

    diag = point_mass_flightpath(result, cfg.params)

    assert np.all(np.isnan(diag.lambda_ratio))


def test_lambda_ratio_exceeds_0_1_in_the_low_speed_region_on_a_stable_fixture():
    """A DEMO_SCENARIO-derived fixture with an alpha-dependent
    ("linearized") aero model has a real, finite M_alpha, and ticket
    section 5 predicts Lambda = (g/V)/omega_n grows large precisely where
    V is low (near the rail / early boost, and -- since M_alpha itself
    scales with dynamic pressure, i.e. with V too, within one flight --
    even more sharply there than section 5's illustrative fixed-omega_n
    numbers suggest)."""
    cfg = assemble(DEMO_SCENARIO)
    stable_cfg = cfg.derive(
        name="demo+linearized_stable",
        overrides={
            "aero.model": "linearized",
            "aero.C_N_alpha": 10.0,  # [1/rad], positive -- normal-force slope
            "aero.C_m_alpha": 0.0,   # keep the restoring moment from the CP location (Lengths.l1) alone
            "recovery.model": "none",  # ballistic fall after burnout -- keeps the run short
        },
    )
    result = run_sim(stable_cfg.params, stable_cfg.s0)

    diag = point_mass_flightpath(result, stable_cfg.params)

    available = ~np.isnan(diag.lambda_ratio)
    assert available.any(), "a linearized, alpha-dependent aero model must yield a real M_alpha somewhere"

    hi_lambda = available & (diag.lambda_ratio > 0.1)
    assert hi_lambda.any(), "expected at least one low-speed sample with Lambda > 0.1"

    median_v = float(np.median(diag.V[available]))
    print(
        f"\nLambda > 0.1 at t={diag.t[hi_lambda].min():.3f}..{diag.t[hi_lambda].max():.3f} s, "
        f"V range there = {diag.V[hi_lambda].min():.2f}..{diag.V[hi_lambda].max():.2f} m/s "
        f"(median V over the available samples = {median_v:.2f} m/s)"
    )
    # the Lambda > 0.1 region must be a low-speed one (section 5's prediction),
    # not scattered across the whole flight at arbitrary speed
    assert diag.V[hi_lambda].max() < median_v

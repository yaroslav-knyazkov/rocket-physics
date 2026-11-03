"""tests/test_fx27_port.py -- acceptance tests for the fx27 port
(dev/docs/architecture-38-fx27-port.md SS38.6.1/SS38.9, tickets FX27-1
through FX27-5).

Per the ticket boundary (FX27-5): this is the ONLY test file this port
touches. No numeric pin outside this file is added or changed.

AC-3 note: `estimate_cx(pro54_transition)` uses a WIDER, explicitly
documented tolerance than the other three oracle figures -- see that
test's own docstring and `dev/docs/fx27-port-progress-notes.md` ("STOP:
AC-3 measured failure") for the full diagnosis. This is a user-accepted
decision (2026-11), not a silently-loosened band: the other three cases
stay at the originally-specified 5%.
"""

import math

import matplotlib

matplotlib.use("Agg")  # headless -- must run before pyplot is imported
# anywhere else in the process, same precedent as tests/test_plotting.py.

import matplotlib.figure
import pytest

from apps.sim.engine.aero import C_A
from apps.sim.schema import assemble

from projects.fx27.campaigns.cspace.rockets_ideal import (
    PRO54_TRANSITION_IDEAL_DRAG_CX,
    PRO54_TRANSITION_IDEAL_MASS_KG,
    PRO75_IDEAL_DRAG_CX,
    PRO75_IDEAL_MASS_KG,
)
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS as CSPACE_SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.campaigns.euroc.motors import DEFERRED_MOTORS
from projects.fx27.campaigns.euroc.scenarios import CANDIDATES, generate_scenarios
from projects.fx27.point.airbrake import size_airbrake
from projects.fx27.point.comparison import evaluate_scenarios, run_many
from projects.fx27.point.estimate import estimate_airframe_mass, estimate_cx
from projects.fx27.point.metrics import row_from_flight
from projects.fx27.point.plots import plot_displacement_comparison, plot_kinematics_comparison

TARGET_APOGEE_M = 3000.0

# ----------------------------------------------------------------------
# AC-1: every cspace/euroc scenario assembles without raising (cheap, no
# integration) -- the real guard against the zero-geometry motor recipe
# (SS38.2.8) being typed in wrong.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CSPACE_SCENARIOS))
def test_cspace_scenario_assembles(name):
    cfg = assemble(CSPACE_SCENARIOS[name])
    assert cfg.params.weight.m > 0.0
    assert cfg.params.weight.m_d is not None  # mass model is ON (SS38.4.2)


_EUROC_SCENARIOS, _EUROC_DEFERRED = generate_scenarios()


@pytest.mark.parametrize("name", sorted(_EUROC_SCENARIOS))
def test_euroc_scenario_assembles(name):
    cfg = assemble(_EUROC_SCENARIOS[name])
    assert cfg.params.weight.m > 0.0
    assert cfg.params.weight.m_d is not None


def test_cspace_has_exactly_the_seven_comparison_rows():
    assert set(CSPACE_SCENARIOS) == {
        "pro54_transition", "pro54_equal", "pro75",
        "pro54_transition (ideal mass)", "pro54_transition (ideal drag)",
        "pro75 (ideal mass)", "pro75 (ideal drag)",
    }


def test_evaluate_scenarios_matches_the_run_many_plus_row_from_flight_reduction():
    """`comparison.evaluate_scenarios` has no caller in `runs/*` (those
    scripts need the raw `FlightRun`s too, for plotting/validity, so they
    hand-inline `run_many` + `row_from_flight` instead) -- pin here that
    it is nonetheless exactly that same reduction, so a future edit to
    either path cannot silently diverge from the other unnoticed."""
    subset = {"pro54_transition": CSPACE_SCENARIOS["pro54_transition"]}

    rows_via_evaluate = evaluate_scenarios(subset)
    rows_via_run_many = [row_from_flight(n, fr) for n, fr in run_many(subset).items()]

    assert rows_via_evaluate == rows_via_run_many


# ----------------------------------------------------------------------
# SS38.7.1/AC-6: DEFERRED_MOTORS is exactly the 3 -todo names, and
# generate_scenarios() excludes every combo that uses one of them.
# ----------------------------------------------------------------------


def test_deferred_motors_is_exactly_the_three_todo_names():
    assert DEFERRED_MOTORS == frozenset(
        {"pro75-2412K1085", "pro98-9876M1890", "pro98-14200N3180"}
    )


def test_generate_scenarios_excludes_every_deferred_combo():
    for name in _EUROC_SCENARIOS:
        config_name, _, motor_id = name.partition("/")
        assert motor_id not in DEFERRED_MOTORS

    for name in _EUROC_DEFERRED:
        config_name, _, motor_id = name.partition("/")
        assert motor_id in DEFERRED_MOTORS
        assert name not in _EUROC_SCENARIOS


def test_generate_scenarios_runnable_plus_deferred_covers_every_candidate():
    total_candidates = sum(len(motor_ids) for motor_ids in CANDIDATES.values())
    assert len(_EUROC_SCENARIOS) + len(_EUROC_DEFERRED) == total_candidates
    assert len(_EUROC_DEFERRED) == 3  # one combo per deferred motor in this data (SS38.7.1)


# ----------------------------------------------------------------------
# AC-3 (the hard gate, SS38.9): estimate_airframe_mass/estimate_cx
# reproduce fx27's four hardcoded solved figures. Slowest tests in this
# file (each runs a brentq search, ~15-20 flights).
#
# Per the user decision (2026-11, documented in dev/docs/fx27-port-
# progress-notes.md "STOP: AC-3 measured failure"): 3 of the 4 figures
# are asserted within the originally-specified 5%. The fourth,
# estimate_cx(pro54_transition), is asserted within a wider, explicitly
# documented 10% -- the measured error (+7.35%) is a genuine Option-C
# divergence (frozen body-axis force direction vs fx27's true point-mass
# velocity-aligned force), concentrated in the lightest, fastest-burning
# (peak Mach 1.36), highest-T/W vehicle in the cspace set -- exactly the
# vehicle the architecture doc's own SS38.3.1 sensitivity analysis flags
# as the most exposed to this port's one real physics difference from
# fx27. Not a bug: forward-simulating this project's model at fx27's own
# already-solved value for this case already lands 1.66% off-target
# before any solving happens (see the progress notes for the full
# cross-check). 10% gives headroom over the measured 7.35% without being
# padded further than needed.
# ----------------------------------------------------------------------

_AC3_TOLERANCE_DEFAULT = 0.05
_AC3_TOLERANCE_PRO54_TRANSITION_CX = 0.10  # see docstring above


def _pct_error(measured: float, reference: float) -> float:
    return abs(measured - reference) / abs(reference)


def test_ac3_estimate_airframe_mass_pro54_transition():
    res = estimate_airframe_mass(CSPACE_SCENARIOS["pro54_transition"], target_apogee_agl=TARGET_APOGEE_M)
    assert res.reachable
    assert _pct_error(res.required, PRO54_TRANSITION_IDEAL_MASS_KG) <= _AC3_TOLERANCE_DEFAULT


def test_ac3_estimate_airframe_mass_pro75():
    res = estimate_airframe_mass(CSPACE_SCENARIOS["pro75"], target_apogee_agl=TARGET_APOGEE_M)
    assert res.reachable
    assert _pct_error(res.required, PRO75_IDEAL_MASS_KG) <= _AC3_TOLERANCE_DEFAULT


def test_ac3_estimate_cx_pro75():
    res = estimate_cx(CSPACE_SCENARIOS["pro75"], target_apogee_agl=TARGET_APOGEE_M)
    assert res.reachable
    assert _pct_error(res.required, PRO75_IDEAL_DRAG_CX) <= _AC3_TOLERANCE_DEFAULT


def test_ac3_estimate_cx_pro54_transition_wider_tolerance():
    """Wider, explicitly documented tolerance -- see the module-level
    docstring block above and dev/docs/fx27-port-progress-notes.md
    ("STOP: AC-3 measured failure") for why this one case differs from
    the other three AC-3 assertions."""
    res = estimate_cx(CSPACE_SCENARIOS["pro54_transition"], target_apogee_agl=TARGET_APOGEE_M)
    assert res.reachable
    err = _pct_error(res.required, PRO54_TRANSITION_IDEAL_DRAG_CX)
    assert err <= _AC3_TOLERANCE_PRO54_TRANSITION_CX
    # Document, don't silently also tighten: still measurably above the
    # default 5% band, so a future reader sees this case is genuinely
    # different, not just "a bigger number happened to pass".
    assert err > _AC3_TOLERANCE_DEFAULT


# ----------------------------------------------------------------------
# AC-5: the air-brake solve converges for an ideal variant.
# ----------------------------------------------------------------------


def test_airbrake_solve_converges_for_one_ideal_variant():
    cfg = CSPACE_SCENARIOS["pro75 (ideal mass)"].config
    sizing = size_airbrake(cfg, target_apogee_m=2500.0)
    assert sizing.solution.reachable is True
    assert sizing.solution.converged is True
    assert sizing.area_min_m2 > 0.0
    assert math.isclose(sizing.area_design_m2, sizing.area_min_m2 * 2.0)
    assert math.isclose(sizing.area_per_panel_m2, sizing.area_design_m2 / 3.0)


# ----------------------------------------------------------------------
# Part B (dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.8):
# the Mach-dependent ("dm") cspace rockets/scenarios ported from fx27's
# own "DRAG MACH DEPENDENT" data. No fx27-solved oracle exists for these
# (unlike AC-3's dc figures) -- sanity-checked, not oracle-validated.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS_DM))
def test_cspace_dm_scenario_assembles(name):
    cfg = assemble(SCENARIOS_DM[name])
    assert cfg.params.weight.m > 0.0
    assert cfg.params.weight.m_d is not None


def test_cspace_dm_has_exactly_the_seven_comparison_rows():
    assert set(SCENARIOS_DM) == {
        "pro54_transition_dm", "pro54_equal_dm", "pro75_dm",
        "pro54_transition_dm (ideal mass)", "pro54_transition_dm (ideal drag)",
        "pro75_dm (ideal mass)", "pro75_dm (ideal drag)",
    }


# SS40.5's own quoted samples: for each of the 3 generated aero tables,
# (Mach, expected C_A) pairs read directly off fx27's source Mach,Cd curve
# (verified byte-for-byte against the sibling repo's own CSVs during this
# step's research) -- `axial_flow_factor(0.0) == 1.0` exactly (SS40.3.3),
# so no fudge factor is needed for alpha=0.0.
_DM_AERO_SAMPLES = {
    "pro54_transition_dm": [(0.0, 1.245), (3.0, 0.308)],
    "pro54_equal_dm": [(0.0, 1.472), (3.0, 0.372)],
    "pro75_dm": [(0.0, 1.466), (3.0, 0.374)],
}


@pytest.mark.parametrize("name", sorted(_DM_AERO_SAMPLES))
def test_dm_aero_table_matches_fx27_source_curve_at_sample_points(name):
    cfg = assemble(SCENARIOS_DM[name])
    for mach, expected_cd in _DM_AERO_SAMPLES[name]:
        measured = C_A(alpha=0.0, M=mach, p=cfg.params)
        assert measured == pytest.approx(expected_cd, abs=1e-9)


_DM_TO_DC_NAMESAKE = {
    "pro54_transition_dm": "pro54_transition",
    "pro54_equal_dm": "pro54_equal",
    "pro75_dm": "pro75",
}


@pytest.mark.parametrize("dm_name", sorted(_DM_TO_DC_NAMESAKE))
def test_dm_scenario_apogee_is_plausible_against_its_dc_namesake(dm_name):
    """Sanity check only, NOT a numeric pin (SS40.4.2/SS40.9: fx27 gives no
    fresh target-apogee-solved oracle for the dm rockets). A wildly
    different apogee from the dc namesake (same motor, same approximate
    mass/drag order of magnitude) would indicate a wiring bug in
    rockets_dm.py, not a credible physical result."""
    dc_name = _DM_TO_DC_NAMESAKE[dm_name]
    runs = run_many({dm_name: SCENARIOS_DM[dm_name], dc_name: CSPACE_SCENARIOS[dc_name]})
    dm_row = row_from_flight(dm_name, runs[dm_name])
    dc_row = row_from_flight(dc_name, runs[dc_name])

    assert dm_row.apogee_agl is not None
    assert math.isfinite(dm_row.apogee_agl)
    assert dm_row.apogee_agl > 0.0
    assert 500.0 <= dm_row.apogee_agl <= 10000.0
    # cross-check band around the dc namesake's own apogee, same order of magnitude
    assert 0.2 * dc_row.apogee_agl <= dm_row.apogee_agl <= 5.0 * dc_row.apogee_agl


# ----------------------------------------------------------------------
# Plot smoke tests -- assert the DATA SERIES, not the pixels
# (tests/test_plotting3d.py's precedent).
# ----------------------------------------------------------------------


def test_comparison_plots_have_the_expected_axes_and_series():
    names = ["pro54_transition", "pro75"]
    runs = run_many({n: CSPACE_SCENARIOS[n] for n in names})
    results = {n: fr.result for n, fr in runs.items()}

    fig_disp = plot_displacement_comparison(results)
    assert isinstance(fig_disp, matplotlib.figure.Figure)
    assert len(fig_disp.axes) == 4
    for ax in fig_disp.axes:
        assert len(ax.lines) == len(names)
        for line in ax.lines:
            assert len(line.get_xdata()) > 1  # a real series, not an empty placeholder

    fig_kin = plot_kinematics_comparison(results)
    assert isinstance(fig_kin, matplotlib.figure.Figure)
    assert len(fig_kin.axes) == 6
    for ax in fig_kin.axes:
        assert len(ax.lines) == len(names)

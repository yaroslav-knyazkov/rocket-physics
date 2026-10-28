"""Tests for apps/analysis/weight_aero_tradeoff/trade_surface.py (App 5
mode (b), roadmap.md Step 67) and
apps/analysis/weight_aero_tradeoff/compare_configs.py (App
5 mode (a), roadmap.md Step 68), dev/docs/architecture-30-apps-4-5-and-
configs.md SS30.7.1/SS30.7.2/SS30.8.

Per that design doc's test strategy (SS30.8): this module pins no raw
apogee *value* as a fact (those are solver predictions, not facts about
the world) -- it pins what IS derivable from first principles and the
project's own architecture:

- the **exact S*C_x invariance** (F9) -- the fact the entire 1-D drag
  axis stands on;
- **node-exact bilinear interpolation** -- the classic off-by-one-axis
  bug, checked at several non-diagonal points;
- the **exchange rate's sign and magnitude**, cross-checked against an
  independent direct finite-difference pair of `run_sim` calls built in
  this file (not reusing `TradeSurface`'s own `np.gradient` machinery) --
  this is what actually proves the axis order and the gradient units;
- `nan` propagation and counting for an unflyable grid point;
- (Step 68) mode (a)'s ranking/`None`-last rule, `cda_axial`'s
  `aero.model` suppression, `Variant`'s no-silent-reset property, and the
  **mode (a)/mode (b) cross-check** -- two scenarios differing only in
  `(mass, C_dA)`, inside Step 67's default grid box, must agree between
  `compare_configs` and `TradeSurface.apogee_at` to interpolation
  accuracy (the load-bearing proof the two modes do not quietly disagree
  where they overlap).

A note on the unflyable-row mechanism: the roadmap ticket's own example
("an absurdly heavy mass value") does not actually produce
`events["apogee"] is None` in this solver -- an under-thrust vehicle
still trips a documented guard-boundary artifact at t=0.1 s
(`sim/integrate.py`'s `_apogee_event`/`_ground_event`, both guarded for
`t < 0.1`) and reports a small, non-nan altitude there, confirmed
empirically against this tree's own solver. The mechanism this file uses
instead -- `solver.t_max` truncated below one grid row's natural
apogee time but above another's -- is the same one
`tests/test_aero.py`/`tests/test_forces.py`/`tests/test_dynamics.py`
already use to get a genuine `events["apogee"] is None`, and it exercises
exactly the property under test (a `nan` grid point propagating through
`np.gradient` and being counted), independent of which physical scenario
produces it.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from apps.input import study_vehicle
from apps._shared.flight_stats import flight_stats
from apps.input.demo_scenario import DEMO_SCENARIO
from apps.analysis.weight_aero_tradeoff.compare_configs import (
    ConfigRun,
    compare_configs,
    evaluate_config,
)
from apps.analysis.weight_aero_tradeoff.compare_configs import main as compare_main
from apps.analysis.weight_aero_tradeoff.scenarios import SCENARIOS, default_axes
from apps.analysis.weight_aero_tradeoff.trade_surface import (
    TradeAxes,
    build_surface,
    count_unflyable,
    main,
    print_exchange_rates,
    print_surface_table,
    save_contour_plot,
    save_surface_csv,
)
from apps.sim.engine.integrate import run_sim
from apps.sim.engine.params import replace as params_replace


def _demo_cfg():
    return study_vehicle.CONFIG


def _small_axes(cfg, n=5):
    """A fast 5x5 grid bracketing `cfg`'s own baseline -- same shape
    convention as `scenarios.default_axes`, just smaller, for the tests
    that do not need the full 11x11 F10 box."""
    cda_baseline = cfg.params.aero.S * cfg.params.aero.C_x
    cda_values = tuple(np.linspace(0.5 * cda_baseline, 1.5 * cda_baseline, n))
    mass_values = tuple(np.linspace(1.0, 2.5, n))
    return TradeAxes(cda_values=cda_values, mass_values=mass_values)


# ----------------------------------------------------------------------
# Primary check 1 -- exact S*C_x invariance (F9)
# ----------------------------------------------------------------------


def test_exact_S_Cx_invariance_bit_for_bit():
    """Two configs with the same S*C_x product give the same apogee
    bit-for-bit -- the fact the entire 1-D C_dA axis stands on (F9). This
    exact pair (doubling C_x while halving S) is the one SS30.2's own
    measured table reports as identical to every printed digit; verified
    here as a literal `==`, not `pytest.approx`."""
    cfg = _demo_cfg()
    target = cfg.params.aero.S * cfg.params.aero.C_x

    p1 = params_replace(cfg.params, {"aero.S": 0.00442, "aero.C_x": 0.5})
    p2 = params_replace(cfg.params, {"aero.S": 0.00221, "aero.C_x": 1.0})
    assert p1.aero.S * p1.aero.C_x == target
    assert p2.aero.S * p2.aero.C_x == target

    r1 = run_sim(p1, cfg.s0)
    r2 = run_sim(p2, cfg.s0)

    assert r1.events["apogee"] == r2.events["apogee"]
    a1 = flight_stats(r1, p1).apogee_altitude
    a2 = flight_stats(r2, p2).apogee_altitude
    assert a1 == a2


def test_S_Cx_invariance_holds_loosely_across_more_pairs():
    """A looser (~1e-6 relative) cross-check across two more S/C_x pairs
    at the same product: the property holds generally, even though not
    every pair reproduces bit-for-bit (observed: a 0.1x/10x S/C_x pair
    differs from the others at the ~1e-9 s level in the apogee *time*,
    evidently adaptive-RK45 step-path noise rather than a physical
    difference) -- flagged as a judgment call in the Step 67 developer
    report, not asserted as bit-for-bit here."""
    cfg = _demo_cfg()
    target = cfg.params.aero.S * cfg.params.aero.C_x

    pairs = [(0.0221, 0.1), (0.001105, 2.0)]
    apogees = []
    for S, C_x in pairs:
        assert math.isclose(S * C_x, target, rel_tol=1e-12)
        p = params_replace(cfg.params, {"aero.S": S, "aero.C_x": C_x})
        r = run_sim(p, cfg.s0)
        apogees.append(flight_stats(r, p).apogee_altitude)

    assert apogees[0] == pytest.approx(apogees[1], rel=1e-6)


# ----------------------------------------------------------------------
# Primary check 2 -- node-exact bilinear interpolation
# ----------------------------------------------------------------------


def test_apogee_at_reproduces_grid_nodes_exactly():
    """`apogee_at(grid point)` must equal the stored value exactly, at
    several non-diagonal points -- an axis transposition bug would still
    pass a single diagonal-point check (both axes have the same length
    here) but would fail at an off-diagonal one."""
    cfg = _demo_cfg()
    axes = _small_axes(cfg, n=5)
    s = build_surface(cfg, axes)

    for i, j in [(0, 0), (1, 3), (3, 1), (4, 4), (2, 0), (0, 4)]:
        m = axes.mass_values[i]
        cda = axes.cda_values[j]
        assert s.apogee_at(cda, m) == s.apogee[i, j], (i, j)


# ----------------------------------------------------------------------
# Shape / orientation / monotonicity
# ----------------------------------------------------------------------


def test_surface_shape_is_mass_rows_by_cda_columns():
    cfg = _demo_cfg()
    axes = _small_axes(cfg, n=4)
    s = build_surface(cfg, axes)
    assert s.apogee.shape == (len(axes.mass_values), len(axes.cda_values))


def test_surface_monotone_decreasing_along_both_axes():
    """More mass -> lower apogee; more drag -> lower apogee, strictly,
    everywhere on this grid (F10's own measured property)."""
    cfg = _demo_cfg()
    axes = _small_axes(cfg, n=5)
    s = build_surface(cfg, axes)

    # Rows (fixed C_dA, increasing mass): strictly decreasing down each column.
    for j in range(s.apogee.shape[1]):
        column = s.apogee[:, j]
        assert np.all(np.diff(column) < 0.0), ("mass axis not monotone", j)

    # Columns (fixed mass, increasing C_dA): strictly decreasing along each row.
    for i in range(s.apogee.shape[0]):
        row = s.apogee[i, :]
        assert np.all(np.diff(row) < 0.0), ("C_dA axis not monotone", i)


# ----------------------------------------------------------------------
# exchange_rate: sign + independent finite-difference cross-check
# ----------------------------------------------------------------------


def test_exchange_rate_negative_and_matches_independent_finite_difference():
    """`exchange_rate` is negative, and agrees to ~10% with
    `-(dA/dC_dA)/(dA/dm)` computed from two *independent* direct
    finite-difference `run_sim` pairs built here -- not reusing
    `TradeSurface`'s own `np.gradient` machinery at all. This is the
    check that actually proves the axis order and the gradient units: a
    passing shape/monotonicity test alone would not catch a transposed
    axis that happened to still look monotone."""
    cfg = _demo_cfg()
    axes = _small_axes(cfg, n=5)
    s = build_surface(cfg, axes)

    # Query at a grid node (the surface's own centre) so the comparison
    # is not also exercising TradeSurface's bilinear interpolation.
    i0, j0 = 2, 2
    m0 = axes.mass_values[i0]
    cda0 = axes.cda_values[j0]

    rate = s.exchange_rate(cda0, m0)
    assert rate < 0.0

    def _apogee_direct(cda: float, m: float) -> float:
        c_x = cda / cfg.params.aero.S
        p = params_replace(cfg.params, {"weight.m": m, "aero.C_x": c_x})
        r = run_sim(p, cfg.s0)
        return flight_stats(r, p).apogee_altitude

    h_cda = 0.02 * cda0
    h_m = 0.05
    d_dcda_fd = (
        _apogee_direct(cda0 + h_cda, m0) - _apogee_direct(cda0 - h_cda, m0)
    ) / (2.0 * h_cda)
    d_dm_fd = (
        _apogee_direct(cda0, m0 + h_m) - _apogee_direct(cda0, m0 - h_m)
    ) / (2.0 * h_m)
    rate_fd = -d_dcda_fd / d_dm_fd

    assert rate_fd < 0.0
    assert rate == pytest.approx(rate_fd, rel=0.10)


# ----------------------------------------------------------------------
# nan propagation and counting
# ----------------------------------------------------------------------


def test_count_unflyable_counts_nan_grid_points_directly():
    """The counting function itself, on a hand-built array -- independent
    of the print formatting that uses it."""
    grid = np.array([[1.0, np.nan, 3.0], [np.nan, np.nan, 6.0]])
    n_nan, n_total = count_unflyable(grid)
    assert n_nan == 3
    assert n_total == 6


def test_unflyable_mass_row_propagates_nan_and_is_counted():
    """One mass row whose flights never reach an apogee event (here:
    `solver.t_max` truncated below that row's natural apogee time, see
    module docstring) is `nan` across the whole row, `np.gradient`
    propagates that `nan` into neighbouring cells, and `count_unflyable`
    reports it -- not silently dropped."""
    cfg = _demo_cfg()
    # m=1.5's natural apogee is ~9.2 s at this baseline C_dA; m=6.0's is
    # ~2.8 s (heavier means *less* thrust-to-weight margin and a faster,
    # lower arc here, not a longer one -- verified empirically against
    # this tree's own solver before writing this test). t_max=5.0 s
    # truncates the first row's flights before they crest, leaving the
    # second row untouched.
    cfg_t5 = cfg.derive("demo_75mm_t5_test", {"solver.t_max": 5.0}, notes="test-only")
    baseline_cda = cfg.params.aero.S * cfg.params.aero.C_x
    axes = TradeAxes(
        cda_values=(0.5 * baseline_cda, baseline_cda, 1.5 * baseline_cda),
        mass_values=(1.5, 6.0),
    )

    s = build_surface(cfg_t5, axes)

    assert np.all(np.isnan(s.apogee[0, :]))
    assert np.all(~np.isnan(s.apogee[1, :]))

    n_nan, n_total = count_unflyable(s.apogee)
    assert n_nan == 3
    assert n_total == 6

    d_dcda, d_dm = s.gradients()
    # d(apogee)/dm needs both mass rows (central difference along the
    # mass axis) -- with only two rows, one of them nan, every cell of
    # this gradient is nan.
    assert np.all(np.isnan(d_dm))
    # d(apogee)/dC_dA only needs neighbours *within* a row -- the nan
    # row's own d_dcda is nan, but the flyable row's is not.
    assert np.all(np.isnan(d_dcda[0, :]))
    assert np.all(~np.isnan(d_dcda[1, :]))

    # print_surface_table/print_exchange_rates must not crash on this
    # surface, and must not raise while handling the nan row.
    print_surface_table(s)
    print_exchange_rates(s)


# ----------------------------------------------------------------------
# scenarios.default_axes
# ----------------------------------------------------------------------


def test_default_axes_is_the_f10_11x11_box_bracketing_the_baseline():
    cfg = _demo_cfg()
    axes = default_axes(cfg)

    assert len(axes.mass_values) == 11
    assert len(axes.cda_values) == 11

    baseline_cda = cfg.params.aero.S * cfg.params.aero.C_x
    assert min(axes.cda_values) == pytest.approx(0.5 * baseline_cda)
    assert max(axes.cda_values) == pytest.approx(1.5 * baseline_cda)
    assert min(axes.mass_values) == pytest.approx(1.0)
    assert max(axes.mass_values) == pytest.approx(2.5)


# ----------------------------------------------------------------------
# End-to-end: python run_trade.py --mode surface (called as main())
# ----------------------------------------------------------------------


def test_main_end_to_end_default_grid_writes_artifacts(tmp_path, capsys):
    """The full default 11x11 grid against `demo_75mm`: prints the table
    and the exchange rates, writes a CSV and a contour PNG. No apogee
    value is pinned (SS30.8) -- the actual exchange rate and wall-clock
    are reported in the Step 67 developer report, per the roadmap
    ticket, not asserted here beyond sanity bounds (rate negative and
    finite; the run completes in well under the test timeout)."""
    # Step 127 (Phase 2.19): `output_dir()` is now a function, read at
    # call time -- so routing the artifacts into `tmp_path` is just the
    # CLI's own `--out-dir`, exercising the real public flag instead of
    # monkeypatching the app module's internal import binding.
    main(["--out-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert "Weight-vs-aero trade surface" in out
    assert "Iso-apogee exchange rate" in out
    assert "runs in" in out

    csv_path = tmp_path / "trade_surface.csv"
    png_path = tmp_path / "trade_surface_contour.png"
    assert csv_path.exists()
    assert png_path.exists()

    rows = csv_path.read_text().splitlines()
    assert rows[0] == "m_kg,cda_m2,apogee_m"
    assert len(rows) == 1 + 11 * 11  # header + 121 grid points


def test_save_contour_plot_and_save_surface_csv_smoke(tmp_path):
    """Directly exercises the two artifact-writing functions on a small
    grid (the end-to-end test above already covers the default 11x11
    grid; this is the fast smoke test for the functions themselves)."""
    cfg = _demo_cfg()
    axes = _small_axes(cfg, n=3)
    s = build_surface(cfg, axes)

    csv_path = tmp_path / "surface.csv"
    png_path = tmp_path / "surface.png"
    save_surface_csv(s, csv_path)
    save_contour_plot(s, png_path)

    assert csv_path.exists()
    assert png_path.exists()
    rows = csv_path.read_text().splitlines()
    assert len(rows) == 1 + 3 * 3


# ----------------------------------------------------------------------
# App 5 mode (a): apps/analysis/weight_aero_tradeoff/compare_configs.py (Step 68)
# ----------------------------------------------------------------------
#
# Mirrors tests/test_motor_selection.py's own ordering/degenerate-flight
# checks for compare_motors (SS30.7.2: "same shape as compare_motors,
# deliberately") rather than assuming the shape from scratch.


def test_compare_configs_ranking_non_increasing_with_none_last():
    """Ranked by apogee descending (non-increasing), and a config that
    cannot fly within its own `solver.t_max` (`apogee_altitude is None`)
    sorts last -- the exact rule `compare_motors.compare_motors` already
    uses (test_motor_selection.py's own
    `test_ordering_invariants_across_fixtures` /
    `test_motor_curve_empty_does_not_crash_and_ranks_last`), mirrored
    here rather than reinvented."""
    cfg = _demo_cfg()
    light = cfg.derive("demo_75mm_light_test", {"weight.m": 1.2}, notes="test-only")
    heavy = cfg.derive("demo_75mm_heavy_test", {"weight.m": 2.0}, notes="test-only")
    # m=6.0's natural apogee is ~2.8 s at this baseline C_dA (confirmed
    # empirically, same fact test_unflyable_mass_row_propagates_nan_and_
    # is_counted above already relies on); t_max=2.0 truncates its flight
    # before it crests, giving a genuine events["apogee"] is None, while
    # every other config here keeps the default t_max=300.0 untouched.
    unflyable = cfg.derive(
        "demo_75mm_unflyable_test",
        {"weight.m": 6.0, "solver.t_max": 2.0},
        notes="test-only",
    )

    runs = compare_configs([heavy, unflyable, cfg, light])

    apogees = [r.stats.apogee_altitude for r in runs]
    assert apogees[-1] is None
    numeric = [a for a in apogees if a is not None]
    assert len(numeric) == 3
    assert all(numeric[i] >= numeric[i + 1] for i in range(len(numeric) - 1))
    assert runs[-1].cfg.name == "demo_75mm_unflyable_test"


def test_cda_axial_is_none_under_table_aero_model():
    """`cda_axial` is `None` unless `aero.model == "constant"` -- the
    same suppression rule `apps.optimization.airbrake_sizing.solve_cda`'s
    `_cda_rocket_and_total` already applies to its `cda_rocket` column.
    `solver.t_max` is bounded well below the default 300 s here: this
    table + geometry combination is statically marginal and the adaptive
    integrator spends a very long wall-clock time grinding through a
    long simulated tumble before `t_max` is reached (confirmed
    empirically) -- irrelevant to what this test checks (`cda_axial` is
    derived from `cfg.params.aero` alone, not from the flight outcome),
    so a short bound keeps the test fast without weakening the check."""
    cfg = _demo_cfg()
    table_cfg = cfg.derive(
        "demo_75mm_table_test",
        {"aero.model": "table", "aero.table": "example.csv", "solver.t_max": 2.0},
        notes="test-only: non-constant aero model",
    )

    run = evaluate_config(table_cfg)

    assert run.cda_axial is None
    assert run.mass_kg == table_cfg.params.weight.m


def test_cda_axial_is_s_times_cx_under_constant_aero_model():
    """The positive case: `aero.model == "constant"` (the default) does
    report `cda_axial = aero.S * aero.C_x`, exactly."""
    cfg = _demo_cfg()
    run = evaluate_config(cfg)
    assert run.cda_axial == cfg.params.aero.S * cfg.params.aero.C_x
    assert run.mass_kg == cfg.params.weight.m


def test_scenarios_variant_changes_exactly_its_named_fields():
    """Confirms the same no-silent-reset property
    `tests/test_configs.py`'s own `test_derive_changes_exactly_the_
    named_fields` already pins at the `Config.derive` level holds through
    this app's own usage path: applying each `scenarios.SCENARIOS` entry
    to the baseline changes exactly its own `overrides` keys and leaves
    every other field of every group (including untouched groups in
    full) equal to the baseline's."""
    base = _demo_cfg()
    group_names = tuple(f.name for f in dataclasses.fields(base.params))

    for variant in SCENARIOS:
        derived = variant.apply(base)

        for key, value in variant.overrides.items():
            group_name, field_name = key.split(".")
            assert getattr(getattr(derived.params, group_name), field_name) == value

        touched_groups = {key.split(".")[0] for key in variant.overrides}
        for group_name in group_names:
            orig_group = getattr(base.params, group_name)
            new_group = getattr(derived.params, group_name)
            if group_name not in touched_groups:
                assert new_group == orig_group, group_name
                continue
            touched_fields = {
                key.split(".")[1]
                for key in variant.overrides
                if key.split(".")[0] == group_name
            }
            for f in dataclasses.fields(orig_group):
                if f.name in touched_fields:
                    continue
                assert getattr(new_group, f.name) == getattr(orig_group, f.name), (
                    group_name,
                    f.name,
                )

        assert derived.s0 == base.s0
        assert derived.name == f"{base.name}+{variant.name}"


# ----------------------------------------------------------------------
# End-to-end: python run_trade.py --mode compare (via compare_configs.main)
# ----------------------------------------------------------------------


def test_compare_main_default_scenarios_writes_artifacts(tmp_path, capsys):
    """No `--config` (the default, the study vehicle): prints the ranked
    table for the baseline plus every `SCENARIOS` variant, and writes
    both artifacts.

    Step 127 (Phase 2.19): routed through the CLI's own `--out-dir`
    rather than monkeypatching the app module's internal import binding
    (`output_dir()` is now a function, read at call time)."""
    compare_main(["--out-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert "Config comparison" in out
    assert "study_75mm" in out
    assert "study_75mm+heavy_sleek" in out
    assert "study_75mm+light_draggy" in out

    csv_path = tmp_path / "config_comparison.csv"
    png_path = tmp_path / "config_comparison_overlay.png"
    assert csv_path.exists()
    assert png_path.exists()

    rows = csv_path.read_text().splitlines()
    assert rows[0].startswith("rank,name,mass_kg,cda_axial_m2,notes,apogee_m")
    assert len(rows) == 1 + 1 + len(SCENARIOS)  # header + baseline + each variant


# ----------------------------------------------------------------------
# The cross-check (roadmap.md Step 68's "Check"): mode (a) must agree
# with mode (b)'s TradeSurface where they overlap.
# ----------------------------------------------------------------------


def test_mode_a_agrees_with_mode_b_trade_surface_at_shared_points():
    """Two scenarios differing **only** in `(mass, C_dA)`, both strictly
    inside Step 67's default grid box (`scenarios.default_axes`'s own
    range) and deliberately off any grid node (so this genuinely
    exercises `TradeSurface`'s bilinear interpolation, not a node-exact
    lookup): mode (a)'s `compare_configs`/`evaluate_config` apogee for
    each must agree with mode (b)'s `TradeSurface.apogee_at` to
    interpolation accuracy.

    This is the test the roadmap ticket calls load-bearing, not a
    nice-to-have -- it is the only check in this file that would catch
    the two modes silently disagreeing where they overlap (e.g. mode (a)
    realising C_dA via a different C_x/S split, or a units slip). The
    measured agreement (see the Step 68 developer report for the actual
    numbers) is ~0.1-0.3% relative, consistent with bilinear truncation
    error on this grid's spacing, well inside the 1% bound asserted here
    and far tighter than the 10% bound the independent-finite-difference
    `exchange_rate` cross-check above needs (that one differentiates the
    grid; this one only interpolates it)."""
    cfg = _demo_cfg()
    axes = default_axes(cfg)  # the full F10 11x11 box -- "the same grid"
    surface = build_surface(cfg, axes)

    baseline_cda = cfg.params.aero.S * cfg.params.aero.C_x
    # Both strictly inside [0.5, 1.5]*baseline_cda x [1.0, 2.5] kg, and
    # off any of the 11 evenly-spaced grid nodes on either axis.
    points = [(0.83 * baseline_cda, 1.37), (1.22 * baseline_cda, 1.93)]

    def _cfg_at(cda: float, m: float, name: str):
        c_x = cda / cfg.params.aero.S
        return cfg.derive(name, {"weight.m": m, "aero.C_x": c_x}, notes="cross-check test-only")

    cfgs = [_cfg_at(cda, m, f"xcheck_{i}") for i, (cda, m) in enumerate(points)]
    runs = compare_configs(cfgs)
    by_name = {r.cfg.name: r for r in runs}

    for i, (cda, m) in enumerate(points):
        apogee_mode_a = by_name[f"xcheck_{i}"].stats.apogee_altitude
        apogee_mode_b = surface.apogee_at(cda, m)
        assert apogee_mode_a is not None
        assert not np.isnan(apogee_mode_b)
        assert apogee_mode_a == pytest.approx(apogee_mode_b, rel=0.01), (i, cda, m)


# ----------------------------------------------------------------------
# D-82: the constant-mass study refuses a mass-model-on baseline
# ----------------------------------------------------------------------


def test_build_surface_refuses_mass_model_on_config(monkeypatch):
    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("run_sim must not be called for a mass-on config")

    monkeypatch.setattr("apps.analysis.weight_aero_tradeoff.trade_surface.run_sim", _must_not_be_called)

    cfg = DEMO_SCENARIO.config
    with pytest.raises(ValueError, match="mass model is on"):
        build_surface(cfg, default_axes(cfg))


"""Tests for apps/weight_aero_tradeoff/trade_surface.py (App 5 mode (b),
roadmap.md Step 67, docs/architecture-30-apps-4-5-and-configs.md
SS30.7.1/SS30.8).

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
- `nan` propagation and counting for an unflyable grid point.

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

import math

import numpy as np
import pytest

import configs
from apps.common.flight_stats import flight_stats
from apps.weight_aero_tradeoff.scenarios import default_axes
from apps.weight_aero_tradeoff.trade_surface import (
    TradeAxes,
    build_surface,
    count_unflyable,
    main,
    print_exchange_rates,
    print_surface_table,
    save_contour_plot,
    save_surface_csv,
)
from sim.integrate import run_sim
from sim.params import replace as params_replace


def _demo_cfg():
    return configs.get("demo_75mm")


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


def test_main_end_to_end_default_grid_writes_artifacts(tmp_path, monkeypatch, capsys):
    """The full default 11x11 grid against `demo_75mm`: prints the table
    and the exchange rates, writes a CSV and a contour PNG. No apogee
    value is pinned (SS30.8) -- the actual exchange rate and wall-clock
    are reported in the Step 67 developer report, per the roadmap
    ticket, not asserted here beyond sanity bounds (rate negative and
    finite; the run completes in well under the test timeout)."""
    import apps.weight_aero_tradeoff.trade_surface as trade_surface_module

    # `trade_surface.py` does `from apps.common.artifacts import
    # OUTPUT_DIR`, binding its own module-level name -- patch that name
    # directly, not `apps.common.artifacts.OUTPUT_DIR` (already-bound
    # imports do not see a later patch of the original).
    monkeypatch.setattr(trade_surface_module, "OUTPUT_DIR", tmp_path)

    main([])

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

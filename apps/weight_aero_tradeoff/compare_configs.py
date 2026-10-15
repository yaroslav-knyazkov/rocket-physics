"""apps/weight_aero_tradeoff/compare_configs.py -- App 5 mode (a):
named-configuration side-by-side comparison (Step 68, roadmap.md;
dev/docs/architecture-30-apps-4-5-and-configs.md SS30.7.2).

**Why this mode exists at all, given mode (b)'s trade surface
(`trade_surface.py`, Step 67) already answers "what does a (delta-mass,
delta-C_dA) change cost me apogee-wise, anywhere in this box".** Two real
candidate configurations can differ in things the surface's two axes do
not span -- a different aero *model* or `data/aero/*.csv` table, a
different motor, a different `S`/`d_ref` geometry, a different launch
site. The moment a configuration difference is not expressible as
`(delta_m, delta_C_dA)`, the surface cannot answer it, and only a genuine
side-by-side run can -- the case this module exists for.

Same shape as `apps/motor_selection/compare_motors.py`'s
`compare_motors`, deliberately (SS30.7.2): ranked by apogee descending,
`None` apogee last, the ascent-window stats bundle per row, plain
fixed-width table, CSV, overlay PNG via `sim.plotting.plot_trajectory_
overlay` (F13 -- this mode genuinely produces one `Result` per row, so
reusing that module's `Result -> Figure` contract is the intended case,
unlike `trade_surface.py`'s surface, which is not a `Result` and
therefore does NOT reuse it).

The two columns that make this a *weight-vs-aero trade* table rather
than a generic comparison table are `mass_kg` (`params.weight.m`) and
`cda_axial` (`aero.S * aero.C_x`, `None` unless `aero.model ==
"constant"`) -- the same suppression rule
`apps/airbrake_sizing/solve_cda.py`'s own `_cda_rocket_and_total` already
applies to its `cda_rocket` column: under `"linearized"`/`"table"` the
airframe's own `C_dA` is Mach/alpha-dependent, so no single number is
honest to report there, even though the row's apogee is still a real,
comparable number.

**Inputs (SS30.7.2).** `--config NAME` (a single registry name, the
default) is a *baseline*: this mode compares it against every
`apps.weight_aero_tradeoff.scenarios.SCENARIOS` entry applied to it (via
`Variant.apply`/`Config.with_variant`, Step 63's machinery), plus the
baseline itself. `--config a,b,c` (two or more comma-separated names)
instead compares those registry configs *directly*, `SCENARIOS` not
consulted at all -- the case that justifies this mode existing in the
first place (two candidates differing by more than a weight/C_dA delta).
This dispatch is based purely on whether the comma splits the string into
one name or several; see `_resolve_configs`.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
from pathlib import Path
from typing import Optional

import configs
from apps.common import study_vehicle
from apps.common.artifacts import OUTPUT_DIR, ensure_dir
from apps.common.flight_stats import FlightStats, _assert_derivatives_reconstructible, flight_stats
from configs.schema import Config
from sim.integrate import Result, run_sim
from sim.plotting import plot_trajectory_overlay


@dataclasses.dataclass(frozen=True)
class ConfigRun:
    """Everything one row of the table knows: the config, its
    trajectory, its reduced stats, and the two trade-specific columns
    (module docstring)."""

    cfg: Config
    result: Result
    stats: FlightStats
    cda_axial: "float | None"   # aero.S * aero.C_x, or None if aero.model != "constant"
    mass_kg: float              # params.weight.m


def _cda_axial(cfg: Config) -> "float | None":
    """`aero.S * aero.C_x` if `aero.model == "constant"`, else `None` --
    exactly `apps.airbrake_sizing.solve_cda._cda_rocket_and_total`'s own
    rule for its `cda_rocket` column (module docstring)."""
    if cfg.params.aero.model != "constant":
        return None
    return cfg.params.aero.S * cfg.params.aero.C_x


def evaluate_config(cfg: Config) -> ConfigRun:
    """`run_sim` -> `flight_stats` -> `ConfigRun`. THE objective-function
    seam, same role as `compare_motors.evaluate_motor` and
    `apps.airbrake_sizing.solve_cda.apogee_for_cda`: one config in, one
    scored run out, no printing, no I/O, no global state.

    The `sample_rate_hz` guard (F8) is checked here, before `run_sim`
    runs the integration at all -- the same fail-fast reasoning
    `compare_configs`'s own pre-flight pass applies."""
    _assert_derivatives_reconstructible(cfg.params)
    result = run_sim(cfg.params, cfg.s0)
    stats = flight_stats(result, cfg.params)
    return ConfigRun(
        cfg=cfg,
        result=result,
        stats=stats,
        cda_axial=_cda_axial(cfg),
        mass_kg=cfg.params.weight.m,
    )


def compare_configs(cfgs: "list[Config]") -> "list[ConfigRun]":
    """Evaluate every config, ranked by apogee altitude descending
    (`None` apogee -- a config that cannot fly -- sorts last). The exact
    tie-breaking rule `apps.motor_selection.compare_motors.compare_motors`
    already uses, mirrored here rather than reinvented.

    Pre-flight validation pass: check the `sample_rate_hz` guard (F8) for
    every config before starting any integration, so a sampled-data
    config fails in the first millisecond instead of after several
    completed runs (same reasoning as `compare_motors`'s own pre-flight
    pass)."""
    for cfg in cfgs:
        _assert_derivatives_reconstructible(cfg.params)

    runs = [evaluate_config(cfg) for cfg in cfgs]

    runs.sort(
        key=lambda r: (
            r.stats.apogee_altitude is not None,
            r.stats.apogee_altitude if r.stats.apogee_altitude is not None else float("-inf"),
        ),
        reverse=True,
    )
    return runs


def _nan_if_none(x: "float | None") -> float:
    return x if x is not None else float("nan")


def print_comparison_table(runs: "list[ConfigRun]") -> None:
    """Plain fixed-width table (the house style, `compare_motors.
    print_motor_table`/`trade_surface.print_surface_table`), ranked by
    apogee descending -- this ranking *is* the answer to the question.
    `mass_kg` and `cda_axial` (printed in cm^2, design units) are the two
    columns that make this a weight-vs-aero trade table rather than a
    generic one."""
    header = (
        f"{'config':<30}{'mass[kg]':>10}{'cda_axial[cm2]':>16}{'apogee[m]':>12}"
        f"{'apogee_t[s]':>13}{'v_max[m/s]':>12}{'v_avg[m/s]':>12}{'a_max[g]':>10}"
        f"{'burnout_t[s]':>14}{'max_q[Pa]':>12}{'impact_t[s]':>13}{'downrange[m]':>14}"
    )
    print("\nConfig comparison (ranked by apogee; ascent-window extrema):")
    print(header)
    print("-" * len(header))
    for r in runs:
        s = r.stats
        cda_cm2 = r.cda_axial * 1e4 if r.cda_axial is not None else float("nan")
        print(
            f"{r.cfg.name:<30}{r.mass_kg:10.3f}{cda_cm2:16.3f}"
            f"{_nan_if_none(s.apogee_altitude):12.2f}{_nan_if_none(s.apogee_time):13.3f}"
            f"{_nan_if_none(s.max_velocity):12.2f}{_nan_if_none(s.avg_velocity):12.2f}"
            f"{_nan_if_none(s.max_accel_g):10.2f}{_nan_if_none(s.burnout_time):14.3f}"
            f"{_nan_if_none(s.max_q):12.1f}{_nan_if_none(s.impact_time):13.3f}"
            f"{_nan_if_none(s.downrange_impact):14.2f}"
        )
    print(
        "(cda_axial is nan unless aero.model == \"constant\" -- under "
        "\"linearized\"/\"table\" the airframe's own C_dA is Mach/alpha-"
        "dependent, so no single number is honest to report there; "
        "apps/airbrake_sizing/solve_cda.py's cda_rocket applies the same "
        "rule)"
    )
    print(
        "(extrema are ascent-window, launch -> apogee; a_max is inertial "
        "acceleration, gravity included)"
    )


def save_comparison_csv(runs: "list[ConfigRun]", path: Path) -> None:
    """One row per config in ranked order, all stats columns plus
    `mass_kg`, `cda_axial_m2` (raw SI, unlike the printed table's cm^2)
    and the config's own `notes` first line, so the CSV is
    self-describing on its own (F13, same reasoning as
    `compare_motors.save_motor_csv`'s `overrides` column)."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank", "name", "mass_kg", "cda_axial_m2", "notes", "apogee_m",
                "apogee_t_s", "v_max_ms", "v_avg_ms", "a_max_ms2", "a_max_g",
                "burnout_t_s", "max_q_Pa", "impact_t_s", "downrange_m",
            ]
        )
        for rank, r in enumerate(runs, start=1):
            s = r.stats
            notes_first_line = r.cfg.notes.splitlines()[0] if r.cfg.notes else ""
            writer.writerow(
                [
                    rank, r.cfg.name, r.mass_kg, r.cda_axial, notes_first_line,
                    s.apogee_altitude, s.apogee_time, s.max_velocity, s.avg_velocity,
                    s.max_accel, s.max_accel_g, s.burnout_time, s.max_q, s.impact_time,
                    s.downrange_impact,
                ]
            )


def save_overlay(runs: "list[ConfigRun]", path: Path) -> None:
    """Overlay plot via `sim.plotting.plot_trajectory_overlay`, keyed by
    config name. Unlike `trade_surface.py`'s surface (not a `Result`,
    F13 non-reuse), this mode genuinely produces one `Result` per row --
    reusing the module is the intended case here, exactly as
    `compare_motors.save_overlay` already does."""
    fig = plot_trajectory_overlay(
        {r.cfg.name: r.result for r in runs}, title="Config comparison"
    )
    fig.savefig(path)


def _parse_config_names(spec: str) -> "list[str]":
    """Split a `--config` value on commas, stripping whitespace. Raises
    `ValueError` if any entry is empty (a typo'd trailing comma), the
    same "fail fast on a plausible typo" reasoning the rest of this
    project's CLIs use."""
    names = [s.strip() for s in spec.split(",")]
    if any(not n for n in names):
        raise ValueError(
            f"--config {spec!r}: empty name in comma-separated list"
        )
    return names


def _resolve_configs(spec: "Optional[str]") -> "list[Config]":
    """A single name resolves to a *baseline*: compared against every
    `apps.weight_aero_tradeoff.scenarios.SCENARIOS` variant applied to it
    (plus the baseline itself) -- the default, SCENARIOS-driven use of
    this mode. Two or more comma-separated names instead resolve to those
    registry configs directly, `SCENARIOS` not consulted -- the case that
    justifies this mode existing at all (module docstring, SS30.7.2):
    candidates differing by more than a weight/C_dA delta against one
    baseline."""
    from apps.weight_aero_tradeoff.scenarios import SCENARIOS

    if spec is None:
        # no --config: the app's own constant-mass study vehicle (D-79)
        baseline = study_vehicle.CONFIG
        return [baseline] + [variant.apply(baseline) for variant in SCENARIOS]
    names = _parse_config_names(spec)
    if len(names) == 1:
        baseline = configs.get(names[0])

        return [baseline] + [variant.apply(baseline) for variant in SCENARIOS]
    return [configs.get(name) for name in names]


def main(argv: "Optional[list[str]]" = None) -> None:
    """Self-sufficient entry point: `python -m
    apps.weight_aero_tradeoff.compare_configs` or `run_trade.py --mode
    compare` (forwarding every other argument, same pattern `run_trade.py
    --mode surface` already uses for `trade_surface.main`)."""
    parser = argparse.ArgumentParser(
        description="App 5 mode (a): named-configuration side-by-side "
        "comparison"
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="NAME[,NAME,...]",
        help="omitted (default): the app's constant-mass study vehicle "
        "(apps/common/study_vehicle.py) as baseline. A single registry name is a "
        "baseline: compares it against every SCENARIOS variant "
        "(apps/weight_aero_tradeoff/scenarios.py) applied to it, plus "
        "the baseline itself. Two or more comma-separated registry "
        "names instead compares those configs directly, SCENARIOS "
        "ignored -- for candidates differing by more than a weight/C_dA "
        "delta (a different aero model/table, motor, geometry or site), "
        "the case that justifies this mode existing (SS30.7.2). See "
        "--list-configs for the registry.",
    )
    parser.add_argument(
        "--list-configs",
        action="store_true",
        help="print every registered config name with its notes' first "
        "line, then exit",
    )
    args = parser.parse_args(argv)

    if args.list_configs:
        for name in configs.names():
            notes = configs.get(name).notes
            first_line = notes.splitlines()[0] if notes else ""
            print(f"{name}: {first_line}" if first_line else name)
        raise SystemExit(0)

    cfgs = _resolve_configs(args.config)
    runs = compare_configs(cfgs)
    print_comparison_table(runs)

    out_dir = ensure_dir(OUTPUT_DIR)
    csv_path = out_dir / "config_comparison.csv"
    png_path = out_dir / "config_comparison_overlay.png"
    save_comparison_csv(runs, csv_path)
    save_overlay(runs, png_path)
    print(f"\nSaved {csv_path}")
    print(f"Saved {png_path}")


if __name__ == "__main__":
    main()

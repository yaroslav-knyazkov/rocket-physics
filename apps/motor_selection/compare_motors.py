"""App 3 -- motor selection sweep.

Answers the question the user asked for directly: "of these N motors, flown
on *this* airframe under *this* one environment, which gives the highest
apogee -- and what does each one cost me in peak velocity, peak
acceleration, peak dynamic pressure and flight time?"

This is a pure *consumer* of `sim/`, on the `apps/cfd_conditions/
select_conditions.py` ("App 2") precedent: it builds one `Params` per motor
via `sim.params.replace`, calls `sim.integrate.run_sim` once per motor,
post-processes each `Result`, and prints/saves a table ranked by apogee. It
adds no new physics and changes nothing under `sim/`. It is the third such
tool in the repo and the second under `apps/`.

Design: `dev/docs/architecture-29-motor-selection.md` SS29.2-SS29.6 for the
sweep mechanics (Step 61); SS29.7/SS29.8 for the per-motor configuration
schema below (Step 62).

### Scope -- what this first version deliberately does NOT do

- **One fixed condition set per sweep run.** The launch state, site,
  atmosphere, wind, recovery and solver settings are the baseline's,
  fixed, not swept -- only the motor varies across rows. A second sweep
  dimension (motor x wind, motor x launch angle) is a different tool.
- **No optimizer.** This is brute-force enumeration of a list the caller
  wrote, which is the degenerate case of an optimizer, deliberately: the
  user asked for optimizers to be separate things that *use* the
  simulation. `evaluate_motor` is the one pure objective-function seam a
  future optimizer app would import -- no search, no gradients, no
  continuous design variables here.
- **No motor database and no `.eng`/RASP import.** Motors are whatever CSV
  files exist under `data/motors/` in the format `sim/thrust_curve.py`
  already reads.
- **Constant mass.** The baseline keeps the Step-36 mass model off
  (`Weight.m_d is None`), the same simplification `run.py` and App 2
  already make.
- **Ascent-window extrema for every kinematic/aerodynamic quantity except
  impact time/downrange.** This is a scope call with physics behind it,
  not an implementation shortcut -- see `flight_stats`'s own docstring.
- **No uncertainty / Monte Carlo / dispersion.** One deterministic
  trajectory per motor.
- **No airbrake, recovery or rail work.** All three already exist in
  `sim/` and are reachable purely by configuring the baseline `Params`;
  none is touched, designed or re-specced here.

### Step 62 -- per-motor configuration (dry-rocket overrides)

`MotorEntry` carries a third field, `overrides: dict[str, Any]` -- an
**open** dict of dotted `sim.params.replace` paths (e.g. `{"weight.m":
0.9, "aero.S": 0.00114}`), applied on top of `baseline` for that motor
only (SS29.7). This needed **no change to `sim/params.py`**: `replace`
already accepts an arbitrary number of dotted keys spanning arbitrary
groups in a single call (F1), so `build_params` just merges
`{"thrust.motor_curve": entry.motor_curve}` with `entry.overrides` into
one `replace()` call. The motor-curve key is reserved: `build_params`
raises `ValueError` if `entry.overrides` also sets `"thrust.motor_curve"`
-- one selector, one place, the same "two uncoordinated selectors for one
thing" defect this repo has already been bitten by (`aero_model` vs
`aero_table`, Phase 2.11). `overrides` defaults to an empty dict (safe for
a frozen dataclass via `default_factory`, not a shared mutable default),
so every Step 61 entry/test/demo scenario that does not specify it is
bit-for-bit unchanged. The actual per-motor configuration data (which
motor gets which overrides) lives in `apps/motor_selection/motors.py`
(SS29.8, D-23: a Python literal, not CSV/JSON/YAML -- `None` is a
meaningful override value, the key set is open and per-entry sparse, and
every number here is commented with *why*).

Run with `python -m apps.motor_selection.compare_motors` from the repo
root -- `apps/` has no `__init__.py` anywhere (an implicit namespace
package), so running the file by path instead would put the script's own
directory on `sys.path` and break `import sim`.
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any, Optional

from apps.common import study_vehicle
from apps.common.artifacts import OUTPUT_DIR
from apps.common.flight_stats import (
    FlightStats,
    _assert_derivatives_reconstructible,
    flight_stats,
)
from sim.integrate import Result, run_sim
from sim.params import Params
from sim.params import replace as params_replace
from sim.plotting import plot_trajectory_overlay
from sim.state import State

# Step 64: MotorStats/flight_stats moved to apps/common/flight_stats.py
# (dev/docs/architecture-30-apps-4-5-and-configs.md SS30.5) -- Apps 4/5 want
# the same ascent-window reduction App 3 pioneered (SS30.2 F11). Re-exported
# under the original name so nothing downstream moves:
# tests/test_motor_selection.py imports `flight_stats` (never `MotorStats`)
# from this module, unedited.
MotorStats = FlightStats


@dataclasses.dataclass(frozen=True)
class MotorEntry:
    """One candidate motor, as configured by the caller.

    `overrides` (Step 62, SS29.7) is an open dict of dotted `Params` paths
    applied on top of the baseline for this motor only -- e.g. `{"weight.m":
    0.9, "aero.S": 0.00114}` for a smaller motor's smaller, lighter casing.
    Defaults to an empty dict via `default_factory` (not a shared mutable
    default, and safe on a `frozen=True` dataclass) so every entry that
    does not need one is unaffected. `"thrust.motor_curve"` is reserved --
    it is always set from `motor_curve` above, never from `overrides` (see
    `build_params`).
    """

    name: str          # label for the table / legend / CSV; free text
    motor_curve: str   # file under data/motors/, e.g. "synthetic_large.csv"
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class MotorRun:
    """Everything one row of the table knows: the input, the `Params` it
    produced, the trajectory, and the reduced stats."""

    entry: MotorEntry
    params: Params
    result: Result
    stats: MotorStats


def build_params(entry: MotorEntry, baseline: Params) -> Params:
    """One `Params` per motor: swap in `entry.motor_curve`, apply
    `entry.overrides` (Step 62, SS29.7) on top, everything else from
    `baseline` unchanged -- one `sim.params.replace` call, since `replace`
    already accepts an arbitrary number of dotted keys across arbitrary
    groups (F1).

    `"thrust.motor_curve"` is reserved for `entry.motor_curve`: if
    `entry.overrides` also sets it, that is two uncoordinated selectors for
    the same field, so this raises `ValueError` rather than silently
    letting one win.
    """
    if "thrust.motor_curve" in entry.overrides:
        raise ValueError(
            f"MotorEntry {entry.name!r}: 'thrust.motor_curve' must not "
            "appear in overrides -- it is already set from entry.motor_curve "
            f"({entry.motor_curve!r}); one selector, one place."
        )
    return params_replace(
        baseline, {"thrust.motor_curve": entry.motor_curve, **entry.overrides}
    )


def evaluate_motor(entry: MotorEntry, baseline: Params, s0: State) -> MotorRun:
    """`build_params` -> `run_sim` -> `flight_stats`. THE objective-function
    seam a future optimizer app imports: one entry in, one scored run out,
    no printing, no I/O, no global state.

    The `sample_rate_hz` guard (F8) is checked here, before `run_sim` runs
    the integration at all -- the same "fail fast" reasoning
    `compare_motors`'s pre-flight pass applies to a typo'd override."""
    p = build_params(entry, baseline)
    _assert_derivatives_reconstructible(p)
    result = run_sim(p, s0)
    stats = flight_stats(result, p)
    return MotorRun(entry=entry, params=p, result=result, stats=stats)


def compare_motors(entries: list[MotorEntry], baseline: Params, s0: State) -> list[MotorRun]:
    """Evaluate every entry, ranked by apogee altitude descending (`None`
    apogee -- a motor too small for this airframe -- sorts last).

    Pre-flight validation pass: build **every** entry's `Params` via
    `build_params` and check the `sample_rate_hz` guard (F8) for all of
    them before starting any integration, so a typo in entry #7 (an
    unknown dotted path, raising `AttributeError`/`TypeError` from
    `sim.params.replace`) or a sampled-data `Params` fails in the first
    millisecond instead of after six completed runs.

    Raises `ValueError` (D-82) if `baseline.weight.m_d is not None`: this
    is a constant-mass study, and with the mass model on the integrator
    reads mass from `y[M]`, so per-motor curve/weight overrides would be
    inert or inconsistent. Raised before any integration.
    """
    if baseline.weight.m_d is not None:
        raise ValueError(
            "compare_motors: baseline has the mass model on "
            f"(weight.m_d={baseline.weight.m_d!r}); App 3 is a constant-mass "
            "study -- the integrator reads mass from y[M], so per-motor "
            "curve/weight overrides are meaningless on such a baseline (F3)"
        )
    params_list = [build_params(entry, baseline) for entry in entries]
    for p in params_list:
        _assert_derivatives_reconstructible(p)

    runs = []
    for entry, p in zip(entries, params_list):
        result = run_sim(p, s0)
        stats = flight_stats(result, p)
        runs.append(MotorRun(entry=entry, params=p, result=result, stats=stats))

    runs.sort(
        key=lambda r: (
            r.stats.apogee_altitude is not None,
            r.stats.apogee_altitude if r.stats.apogee_altitude is not None else float("-inf"),
        ),
        reverse=True,
    )
    return runs


def _nan_if_none(x: Optional[float]) -> float:
    return x if x is not None else float("nan")


def print_motor_table(runs: list[MotorRun]) -> None:
    """Plain fixed-width table (the `sim.report.print_sweep_table` /
    `select_conditions.print_conditions_table` house style), ranked by
    apogee descending -- unlike App 2's time-ordered table, this ranking
    *is* the answer to the question."""
    header = (
        f"{'motor':<22}{'impulse[Ns]':>12}{'apogee[m]':>12}{'apogee_t[s]':>13}"
        f"{'v_max[m/s]':>12}{'v_avg[m/s]':>12}{'a_max[g]':>10}"
        f"{'burnout_t[s]':>14}{'max_q[Pa]':>12}{'impact_t[s]':>13}{'downrange[m]':>14}"
    )
    print("\nMotor comparison (ranked by apogee; ascent-window extrema):")
    print(header)
    print("-" * len(header))
    for r in runs:
        s = r.stats
        print(
            f"{r.entry.name:<22}{_nan_if_none(s.total_impulse):12.2f}"
            f"{_nan_if_none(s.apogee_altitude):12.2f}{_nan_if_none(s.apogee_time):13.3f}"
            f"{_nan_if_none(s.max_velocity):12.2f}{_nan_if_none(s.avg_velocity):12.2f}"
            f"{_nan_if_none(s.max_accel_g):10.2f}{_nan_if_none(s.burnout_time):14.3f}"
            f"{_nan_if_none(s.max_q):12.1f}{_nan_if_none(s.impact_time):13.3f}"
            f"{_nan_if_none(s.downrange_impact):14.2f}"
        )
    print(
        "(extrema are ascent-window, launch -> apogee; a_max is inertial "
        "acceleration, gravity included)"
    )


def _format_overrides(overrides: dict[str, Any]) -> str:
    """`;`-joined `path=value` string (Step 62), so the CSV records exactly
    what dry-rocket configuration each row flew with, traceably, without a
    second file (F13). Empty dict -> empty string."""
    return ";".join(f"{k}={v}" for k, v in overrides.items())


def save_motor_csv(runs: list[MotorRun], path: Path) -> None:
    """One row per motor in ranked order, all twelve stats columns
    (including `max_accel` in m/s^2, which the printed table omits in
    favour of g) plus the motor-curve filename and the `;`-joined
    per-motor override string (Step 62), so the CSV is self-describing on
    its own (F13)."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank", "name", "motor_curve", "overrides", "impulse_Ns", "apogee_m",
                "apogee_t_s", "v_max_ms", "v_avg_ms", "a_max_ms2", "a_max_g", "burnout_t_s",
                "max_q_Pa", "impact_t_s", "downrange_m",
            ]
        )
        for rank, r in enumerate(runs, start=1):
            s = r.stats
            writer.writerow(
                [
                    rank, r.entry.name, r.entry.motor_curve,
                    _format_overrides(r.entry.overrides), s.total_impulse, s.apogee_altitude,
                    s.apogee_time, s.max_velocity, s.avg_velocity, s.max_accel, s.max_accel_g,
                    s.burnout_time, s.max_q, s.impact_time, s.downrange_impact,
                ]
            )


def save_overlay(runs: list[MotorRun], path: Path) -> None:
    """Overlay plot via `sim.plotting.plot_trajectory_overlay`, keyed by
    motor name -- zero `sim/` change, reused exactly as App 2 would (F13).
    Deliberately not routed through `sim.report.save_sweep_artifacts`, which
    expects `sim.report.sweep`'s `{value: {"result": ...}}` dict shape;
    building that shape just to reuse a savefig would be contortion."""
    fig = plot_trajectory_overlay(
        {r.entry.name: r.result for r in runs}, title="Motor comparison"
    )
    fig.savefig(path)


# ----------------------------------------------------------------------
# Demo scenario (architecture-29-motor-selection.md SS29.5, D-26)
# ----------------------------------------------------------------------


def _demo_baseline() -> Params:
    """The architect's synthetic 1.5 kg / 75 mm vehicle (D-26) -- Step 86
    (dev/docs/architecture-33-configs-one-demo.md SS33.4.3, D-79): a
    one-line re-export of `apps.common.study_vehicle.CONFIG.params`, kept
    under this name only because `tests/test_motor_selection.py` imports it
    unedited (F11). The full provenance/rationale for these numbers lives
    once, in `apps/common/study_vehicle.py`'s own docstring.
    """
    return study_vehicle.CONFIG.params


def _demo_entries() -> list[MotorEntry]:
    return [
        MotorEntry(name="small_E", motor_curve="synthetic_small.csv"),
        MotorEntry(name="medium_punchy_H", motor_curve="synthetic_medium_punchy.csv"),
        MotorEntry(name="medium_long_H", motor_curve="synthetic_medium_long.csv"),
        MotorEntry(name="large_I", motor_curve="synthetic_large.csv"),
        MotorEntry(name="placeholder_H", motor_curve="placeholder.csv"),
    ]


def main() -> None:
    """Runs the configured `apps.motor_selection.motors.MOTORS` set (Step
    62) -- the per-motor dry-rocket overrides, not the override-free Step
    61 `_demo_entries()` above (which stays, unused by `main`, purely so
    the existing Step-61 tests that import it keep working bit-for-bit)."""
    from apps.motor_selection.motors import MOTORS

    # Step 86: baseline + s0 both sourced from apps/common/study_vehicle.py
    # (the same Config _demo_baseline() above re-exports .params from), so
    # the study vehicle's initial state is not a second, separately
    # maintained literal.
    cfg = study_vehicle.CONFIG
    baseline = cfg.params
    s0 = cfg.s0

    runs = compare_motors(MOTORS, baseline, s0)
    print_motor_table(runs)

    OUTPUT_DIR.mkdir(exist_ok=True)
    csv_path = OUTPUT_DIR / "motor_selection.csv"
    overlay_path = OUTPUT_DIR / "motor_selection_overlay.png"
    save_motor_csv(runs, csv_path)
    save_overlay(runs, overlay_path)
    print(f"\nSaved {csv_path}")
    print(f"Saved {overlay_path}")


if __name__ == "__main__":
    main()

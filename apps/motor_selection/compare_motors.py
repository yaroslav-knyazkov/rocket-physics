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

Design: `docs/architecture-29-motor-selection.md` SS29.2-SS29.6 for the
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
import math
from pathlib import Path
from typing import Any, Optional

import numpy as np

from sim import dynamics, thrust_curve
from sim.flow import flow_state
from sim.gravity import altitude_agl
from sim.integrate import Result, run_sim
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.params import replace as params_replace
from sim.plotting import plot_trajectory_overlay
from sim.state import State, VX, VZ, X

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

# The house dense-grid size (sim/report.py, apps/cfd_conditions/
# select_conditions.py both use 2000-4000-point grids over the window they
# reduce) -- SS29.4.2.
_ASCENT_GRID_N = 2000
_BURN_GRID_N = 2000


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
class MotorStats:
    """The per-motor stats bundle (architecture-29-motor-selection.md
    SS29.4). Every field is a float or None; None means "the flight never
    produced this event" (SS29.4.6 -- a motor too small to leave the pad is
    a legitimate study result, not an error)."""

    apogee_altitude: float | None    # m AGL, the ranking criterion
    apogee_time: float | None        # s
    max_velocity: float | None       # m/s, ascent window, inertial |v|
    avg_velocity: float | None       # m/s, time-average over the ascent window
    max_accel: float | None          # m/s^2, ascent window, inertial |dv/dt| incl. gravity
    max_accel_g: float | None        # max_accel / p.g0 [-]
    max_q: float | None              # Pa, ascent window
    total_impulse: float | None      # N*s, delivered, numerically integrated over the ascent
    burnout_time: float | None       # s, from result.events
    impact_time: float | None        # s, from result.events (full flight)
    downrange_impact: float | None   # m, at impact (full flight)


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


def _assert_derivatives_reconstructible(p: Params) -> None:
    """Shared guard (F8): a post-hoc `dynamics.derivatives` re-evaluation on
    this module's own sampling grid cannot reconstruct a sampled-data run's
    per-tick zero-order hold (`sim/sampling.py`, roadmap.md Step 59), so
    `max_accel` would silently not be the acceleration that actually flew.
    Called both before `run_sim` (`evaluate_motor`/`compare_motors`'
    pre-flight pass, so this fails in a millisecond rather than after a
    full integration) and again in `flight_stats` itself (which is a public
    pure function and may be called directly on a `Result`/`Params` pair
    this module did not itself produce).
    """
    if p.solver.sample_rate_hz != 0.0:
        raise ValueError(
            f"p.solver.sample_rate_hz={p.solver.sample_rate_hz} is not "
            "supported here: a post-hoc dynamics.derivatives re-evaluation "
            "cannot reconstruct a sampled-data run's per-tick zero-order "
            "hold (sim/sampling.py, roadmap.md Step 59), so max_accel would "
            "not be the acceleration that actually flew "
            "(architecture-29-motor-selection.md F8)."
        )


def flight_stats(result: Result, p: Params) -> MotorStats:
    """Reduce one `Result` to the stats bundle (SS29.4).

    Two measurement windows, per-quantity, not per-table (SS29.4.1):
    `apogee_altitude`/`apogee_time` at the apogee event instant;
    `max_velocity`/`avg_velocity`/`max_accel`/`max_q`/`total_impulse` over
    the **ascent only** (launch to apogee) -- because this project's own
    scenarios can put max speed *during descent* (frozen nose-up attitude,
    real axial drag accelerating a tail-first fall, roadmap.md Step 55), so
    a whole-flight extremum here would be reporting that descent artifact
    in the column that is supposed to answer "how fast does this motor make
    my rocket go"; `burnout_time` from the event; `impact_time`/
    `downrange_impact` over the **whole flight** (they are end-of-flight
    quantities by definition). A useful side effect: the ranking and every
    ascent column are unaffected by the recovery configuration.

    Raises `ValueError` if `p.solver.sample_rate_hz != 0.0`: a post-hoc
    `dynamics.derivatives` re-evaluation on this function's own sampling
    grid cannot reconstruct a sampled-data run's per-tick zero-order hold
    (`sim/sampling.py`, roadmap.md Step 59), so `max_accel` would silently
    not be the acceleration that actually flew. `p.solver.method == "rk4"`
    is allowed, but its dense interpolant is piecewise-linear
    (`sim/integrate.py`'s `_LinearInterpolant`), so grid-sampled extrema
    are then only as good as `p.solver.dt`.
    """
    _assert_derivatives_reconstructible(p)

    burnout_time = result.events["burnout"]
    impact_time = result.events["ground"]
    t_apogee = result.events["apogee"]

    t_end = impact_time if impact_time is not None else result.t[-1]
    t_full_grid = np.linspace(0.0, t_end, _ASCENT_GRID_N)
    y_full_grid = result.raw.sol(t_full_grid)
    downrange_impact = (
        float(result.raw.sol(impact_time)[X])
        if impact_time is not None
        else float(y_full_grid[X, -1])
    )

    if t_apogee is None:
        # Degenerate flight (SS29.4.6): the motor never produced an apogee
        # event (too small to leave the pad, or never comes back down
        # inside t_max). Every ascent-window field is unknowable; the
        # whole-flight fields are still reported.
        return MotorStats(
            apogee_altitude=None,
            apogee_time=None,
            max_velocity=None,
            avg_velocity=None,
            max_accel=None,
            max_accel_g=None,
            max_q=None,
            total_impulse=None,
            burnout_time=burnout_time,
            impact_time=impact_time,
            downrange_impact=downrange_impact,
        )

    apogee_altitude = float(altitude_agl(result.raw.sol(t_apogee), p))

    # The ascent grid: the house 2000-point grid over [0, t_apogee], unioned
    # with a second 2000-point grid over [0, t_burnout] -- a motor's
    # ignition spike (~50 ms) would otherwise be under-sampled by a uniform
    # grid over a multi-second ascent (SS29.4.2). np.union1d sorts and
    # de-duplicates, giving a single strictly increasing, non-uniform grid.
    t_grid = np.linspace(0.0, t_apogee, _ASCENT_GRID_N)
    if burnout_time is not None and 0.0 < burnout_time < t_apogee:
        t_grid = np.union1d(t_grid, np.linspace(0.0, burnout_time, _BURN_GRID_N))
    y_grid = result.raw.sol(t_grid)

    speed = np.hypot(y_grid[VX], y_grid[VZ])
    max_velocity = float(speed.max())
    # Time-average over a non-uniform grid must be a proper time integral,
    # not speed.mean() (which would be wrong by the ratio of the refined to
    # the coarse spacing) -- np.trapezoid, not np.trapz (removed in numpy
    # 2.x, architecture-29-motor-selection.md F11).
    avg_velocity = float(np.trapezoid(speed, t_grid) / (t_grid[-1] - t_grid[0]))

    # Exact inertial acceleration: re-evaluate the RHS the integrator
    # itself saw, rather than finite-differencing the velocity grid (F7) --
    # no differencing stencil, no smearing of the thrust curve's kinks.
    dydt = np.array([dynamics.derivatives(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
    accel = np.hypot(dydt[:, VX], dydt[:, VZ])
    max_accel = float(accel.max())
    max_accel_g = max_accel / p.g0

    q = np.array([flow_state(t, y_grid[:, i], p).q for i, t in enumerate(t_grid)])
    max_q = float(q.max())

    T = np.array([thrust_curve.thrust(t, y_grid[:, i], p) for i, t in enumerate(t_grid)])
    total_impulse = float(np.trapezoid(T, t_grid))

    return MotorStats(
        apogee_altitude=apogee_altitude,
        apogee_time=float(t_apogee),
        max_velocity=max_velocity,
        avg_velocity=avg_velocity,
        max_accel=max_accel,
        max_accel_g=max_accel_g,
        max_q=max_q,
        total_impulse=total_impulse,
        burnout_time=burnout_time,
        impact_time=impact_time,
        downrange_impact=downrange_impact,
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
    """
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
    """The architect's own synthetic 1.5 kg / 75 mm vehicle. Deliberately
    NOT run.py's 0.5 kg toy scenario: 338 N*s (the largest new fixture) on
    0.5 kg gives an ideal delta-v of ~676 m/s (~Mach 2), where a constant
    C_x = 0.5 is not a defensible aerodynamic model and the ISA
    extrapolation ceiling starts to matter. 1.5 kg keeps every fixture
    subsonic (largest motor: ideal delta-v ~225 m/s before gravity/drag
    losses, <~ Mach 0.7) while still leaving the smallest motor just barely
    flyable -- itself informative. `C_z = C_m = 0.0` makes this a vertical,
    attitude-frozen 1-D shot, the same simplification run.py and App 2
    already carry, appropriate for a motor comparison (one variable at a
    time) and, per SS29.4.1/F5, the reason the ascent window is mandatory.
    """
    return Params(
        weight=Weight(m=1.5, I=0.08),                 # launch mass, mass model OFF (m_d=None)
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),  # replaced per entry; never read as-is
        aero=Aero(
            S=0.00442, d_ref=0.075, l_ref=0.75,        # 75 mm body: S = pi*d^2/4 = 0.004418 m^2
            C_x=0.5, C_z=0.0, C_m=0.0,
        ),
    )


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

    baseline = _demo_baseline()
    s0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    runs = compare_motors(MOTORS, baseline, s0)
    print_motor_table(runs)

    _OUTPUT_DIR.mkdir(exist_ok=True)
    csv_path = _OUTPUT_DIR / "motor_selection.csv"
    overlay_path = _OUTPUT_DIR / "motor_selection_overlay.png"
    save_motor_csv(runs, csv_path)
    save_overlay(runs, overlay_path)
    print(f"\nSaved {csv_path}")
    print(f"Saved {overlay_path}")


if __name__ == "__main__":
    main()

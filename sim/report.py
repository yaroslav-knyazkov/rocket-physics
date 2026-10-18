"""Orchestration layer above `sim/plotting.py` (architecture-28-rewrite.md
SS28.9): build a figure, print a summary/table, save artifacts to disk.

Step 58 moves this whole layer out of `run.py`, which Step 57 left still
carrying the single-run summary printing, plot/CSV saving and both model-
comparison sweeps (gravity, atmosphere) verbatim from Step 27/Step 55.
`run.py` keeps only scenario *definition* -- which `Params`, which sweep
fields/values/titles -- everything that turns a `Result` into console text,
a saved PNG or a saved CSV lives here instead.

`sim/plotting.py` is unchanged by this move: it stays the pure figure-
builder layer (`Result` -> `Figure`, no I/O, no printing). This module is
the layer above it.
"""

import warnings
from pathlib import Path

import numpy as np

from sim import aero
from sim.flow import flow_state
from sim.gravity import altitude_agl
from sim.integrate import run_sim
from sim.params import Params
from sim.params import replace as params_replace
from sim.plotting import plot_time_histories, plot_trajectory, plot_trajectory_overlay
from sim.state import State, X, Z, VX, VZ, THETA, OMEGA

# Generated artifacts (plots, trajectory.csv) go under output/, kept out of
# the repo root -- created on demand, gitignored wholesale (.gitignore).
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"


def flight_summary(result, p) -> dict:
    """Apogee altitude/time, max dynamic pressure ("max-Q") over the whole
    recorded flight, and impact time -- the same quantities
    `print_run_summary` below prints, generalised so `sweep()` can compute
    them per variant.

    `q` is sampled via `sim.flow.flow_state` on the same dense, uniform
    time grid the single-run summary already uses for speed/downrange
    (`result.raw.sol(t_grid)`) -- `flow_state` needs a single state vector
    per call, so this loops over the grid columns.
    """
    apogee_time = result.events["apogee"]
    impact_time = result.events["ground"]
    apogee_altitude = (
        altitude_agl(result.raw.sol(apogee_time), p) if apogee_time is not None else None
    )

    t_end = impact_time if impact_time is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, 2000)
    y_grid = result.raw.sol(t_grid)

    q_values = np.array(
        [flow_state(t, y_grid[:, i], p).q for i, t in enumerate(t_grid)]
    )
    max_q = float(q_values.max())

    return dict(
        apogee_altitude=apogee_altitude,
        apogee_time=apogee_time,
        max_q=max_q,
        impact_time=impact_time,
    )


def static_margin_cal(result, p, t_grid=None):
    """Static margin series in calibres, `(t, margin)` with
    `margin(t) = l1(t) / d_ref` -- `l1` is the CoP-to-CoG arm the dynamics
    uses (`aero.coefficients(...).l1`), i.e. `(l_p - l_g(t)) / d_ref` for an
    `l_p`/`l_p_m` config (Step 99, architecture-35 SS35.4.3), evaluated on the
    flight's own `(alpha, M)`. Defaults to a 400-point grid over the flight.
    """
    if p.aero.d_ref <= 0.0:
        raise ValueError("static_margin_cal needs Aero.d_ref > 0")
    t, y = _flight_grid(result, t_grid)
    margin = np.empty(t.size)
    for i, ti in enumerate(t):
        flow = flow_state(ti, y[:, i], p)
        margin[i] = aero.coefficients(ti, y[:, i], p, flow).l1 / p.aero.d_ref
    return t, margin


def _flight_grid(result, t_grid):
    if t_grid is None:
        impact = result.events["ground"]
        t_end = impact if impact is not None else result.t[-1]
        t_grid = np.linspace(0.0, t_end, 400)
    t = np.asarray(t_grid, dtype=float)
    return t, result.raw.sol(t)


_CM_SLOPE_STEP = np.radians(0.5)


def cm_slope_series(result, p, t_grid=None):
    """`(t, dC_m/dalpha)` in the code's convention (positive slope =
    restoring), central difference about the flight's own `(alpha, M)`."""
    t, y = _flight_grid(result, t_grid)
    slope = np.empty(t.size)
    for i, ti in enumerate(t):
        flow = flow_state(ti, y[:, i], p)
        hi = aero.C_m(flow.alpha + _CM_SLOPE_STEP, flow.M, p)
        lo = aero.C_m(flow.alpha - _CM_SLOPE_STEP, flow.M, p)
        slope[i] = (hi - lo) / (2.0 * _CM_SLOPE_STEP)
    return t, slope


def stability_check(result, p, t_grid=None) -> dict:
    """Static-stability diagnostic (Step 99, D-111): warns (`UserWarning`) when
    the static margin goes negative (CoP ahead of the CoG) or when the pitching-
    moment slope has the destabilising sign in the code's convention (e.g. a
    table whose declared `# cm_convention:` is wrong). Returns
    `{min_margin_cal, min_cm_slope, stable}`; `stable` is False if either warned.
    """
    _, margin = static_margin_cal(result, p, t_grid)
    _, slope = cm_slope_series(result, p, t_grid)
    min_margin = float(margin.min())
    min_slope = float(slope.min())
    stable = True
    if min_margin < 0.0:
        stable = False
        warnings.warn(
            f"unstable: static margin reaches {min_margin:.3f} cal (CoP ahead of the CoG)",
            UserWarning, stacklevel=2,
        )
    if min_slope < -1e-9:  # tolerance: finite-difference rounding on flat segments
        stable = False
        warnings.warn(
            f"unstable: dC_m/dalpha = {min_slope:.4g} < 0 in the code convention "
            "(positive C_m is nose-down) -- check the table's `# cm_convention:`",
            UserWarning, stacklevel=2,
        )
    return dict(min_margin_cal=min_margin, min_cm_slope=min_slope, stable=stable)


def sweep(base_params: Params, path: str, values, s0: State) -> dict:
    """Model comparison sweep (architecture.md SS12, roadmap.md Step 27 --
    "the payoff for the selection pattern"): run `run_sim` once per `value`
    of `path`, varying only that one field on `base_params` via
    `sim.params.replace`'s dotted-path helper (architecture-28-rewrite.md
    SS28.4), exactly the idiom SS12 gives:

        for gm in ("constant", "radial", "wgs84"):
            run_sim(params_replace(p, {"gravity.model": gm}), s0)

    `path` is therefore a dotted group path (e.g. `"gravity.model"`), not a
    flat Params kwarg -- the printed table's column header is that same
    dotted string.

    Returns `{value: {"result": Result, "params": Params, **flight_summary}}`,
    keyed by the model-selection string so callers (the printed table,
    `plot_trajectory_overlay`) can label each variant directly.
    """
    out = {}
    for value in values:
        p = params_replace(base_params, {path: value})
        result = run_sim(p, s0)
        out[value] = dict(result=result, params=p, **flight_summary(result, p))
    return out


def print_sweep_table(title: str, path: str, results: dict) -> None:
    """Plain-text summary table (this project's existing "print a flight
    summary" style, no table library -- roadmap.md Step 27's check)."""
    print(f"\n{title} ({path} sweep):")
    header = f"{path:<14}{'apogee_alt[m]':>16}{'apogee_t[s]':>14}{'max_q[Pa]':>14}{'impact_t[s]':>14}"
    print(header)
    print("-" * len(header))
    for value, d in results.items():
        impact_t = d["impact_time"] if d["impact_time"] is not None else float("nan")
        print(
            f"{value:<14}{d['apogee_altitude']:16.4f}{d['apogee_time']:14.4f}"
            f"{d['max_q']:14.4f}{impact_t:14.4f}"
        )


def print_run_summary(result, p, s0: State) -> None:
    """The single-run printed flight summary (Step 7, extended by Step 14's
    burnout-time line) -- `p`/`s0` reprs, then burnout/apogee/max-speed/
    impact/downrange, printed straight to stdout, no return value.

    Takes `s0` (the initial `State`) on top of the `(result, p)` shape
    architecture-28-rewrite.md SS28.9's illustrative `run.py` snippet shows,
    so the pre-Step-58 `print(params); print(state0)` pair at the top of
    this summary stays bit-for-bit -- dropping `state0` from the signature
    would silently drop that printed line.
    """
    apogee_time = result.events["apogee"]
    impact_time = result.events["ground"]
    burnout_time = result.events["burnout"]
    # Evaluate the dense interpolant exactly at the apogee event time
    # rather than taking -min(z) over the adaptive-step samples: RK45's
    # accepted steps rarely land exactly on the apogee, so a raw min()
    # under-estimates it. dense_output=True gives us that interpolant.
    # altitude_agl (Step 45, architecture.md SS25.5) reads the curved
    # ground under gravity_direction != "parallel"; under the default
    # "parallel" it is bitwise -result.raw.sol(apogee_time)[Z], unchanged.
    apogee_altitude = altitude_agl(result.raw.sol(apogee_time), p)

    # Max speed and downrange-at-impact: sample the dense interpolant on a
    # fine uniform grid over the whole recorded flight (apogee is a
    # non-terminal event, so the interpolant is valid past it too) rather
    # than relying on the sparse adaptive-step points in result.t/result.y.
    t_end = impact_time if impact_time is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, 2000)
    y_grid = result.raw.sol(t_grid)
    speed = np.hypot(y_grid[VX], y_grid[VZ])
    max_speed = speed.max()

    if impact_time is not None:
        downrange_impact = result.raw.sol(impact_time)[X]
    else:
        downrange_impact = y_grid[X, -1]

    print(p)
    print(s0)
    print(f"Burnout time:        {burnout_time:.4f} s")
    print(f"Apogee altitude:     {apogee_altitude:.4f} m")
    print(f"Apogee time:         {apogee_time:.4f} s")
    print(f"Max speed:           {max_speed:.4f} m/s")
    print(f"Impact time:         {impact_time:.4f} s")
    print(f"Downrange at impact: {downrange_impact:.4f} m")


def save_run_artifacts(result, p, out_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Build the single-run plots, save them as PNGs, and dump the CSV
    trajectory sample -- the Step 7/Step 27 artifact set, unchanged."""
    out_dir.mkdir(exist_ok=True)

    fig_traj = plot_trajectory(result)
    fig_hist = plot_time_histories(result)
    # Always save to files -- this may run in a non-interactive/headless
    # context (e.g. no display), where plt.show() would either do nothing
    # or raise. Saving PNGs guarantees usable artifacts either way.
    fig_traj.savefig(out_dir / "trajectory.png")
    fig_hist.savefig(out_dir / "time_histories.png")
    print(f"Saved plots to {out_dir / 'trajectory.png'} and {out_dir / 'time_histories.png'}")

    # Optional one-line CSV dump (architecture.md SS7 "Persistence") for
    # diffing runs -- time, x, z, theta, omega on the same fine grid used
    # above for the summary stats.
    impact_time = result.events["ground"]
    t_end = impact_time if impact_time is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, 2000)
    y_grid = result.raw.sol(t_grid)
    np.savetxt(
        out_dir / "trajectory.csv",
        np.column_stack(
            [t_grid, y_grid[X], y_grid[Z], y_grid[THETA], y_grid[OMEGA]]
        ),
        delimiter=",",
        header="t,x,z,theta,omega",
        comments="",
    )
    print(f"Saved {out_dir / 'trajectory.csv'}")


def save_sweep_artifacts(
    name: str, sweep_results: dict, out_dir: Path = DEFAULT_OUTPUT_DIR, title: str = "Model comparison"
) -> None:
    """Overlay plot + savefig for one sweep's results -- `name` is the
    filename stem (e.g. `"gravity"` -> `gravity_sweep.png`), `title` is the
    human-readable string passed through to
    `sim.plotting.plot_trajectory_overlay`."""
    out_dir.mkdir(exist_ok=True)
    fig = plot_trajectory_overlay(
        {v: d["result"] for v, d in sweep_results.items()},
        title=title,
    )
    out_path = out_dir / f"{name}_sweep.png"
    fig.savefig(out_path)
    print(f"Saved {out_path}")


def run_sweep(
    base_params: Params,
    path: str,
    values,
    s0: State,
    title: str,
    plot_title: str = None,
    out_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict:
    """Convenience wrapper (architecture-28-rewrite.md SS28.9, D-13): sweep
    -> print table -> overlay plot -> savefig, in one call, so `run.py`'s
    two model-comparison sweeps (Step 27) each reduce to a single line. The
    filename stem is derived from `path`'s first dotted segment (e.g.
    `"gravity.model"` -> `gravity_sweep.png`, `"atmosphere.model"` ->
    `atmosphere_sweep.png`), matching the names the pre-Step-58 `run.py`
    already used.

    `plot_title` defaults to `title` but can be given separately -- the
    pre-Step-58 `run.py` used a slightly different string for the printed
    table ("Atmosphere model comparison (station LKPR)") than for the
    overlay figure's own title ("Atmosphere model comparison (LKPR)")
    for its atmosphere sweep; this keeps that distinction available
    instead of silently collapsing the two onto one string.

    Returns the same `{value: {...}}` dict `sweep()` does, in case a
    caller wants it (not used by `run.py`'s own `main()`)."""
    results = sweep(base_params, path, values, s0)
    print_sweep_table(title, path, results)
    name = path.split(".")[0]
    save_sweep_artifacts(name, results, out_dir, plot_title if plot_title is not None else title)
    return results

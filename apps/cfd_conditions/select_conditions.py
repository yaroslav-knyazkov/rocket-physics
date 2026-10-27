"""App 2 -- CFD condition selector.

Answers the question that has to be answered *before* CFD is run at all:
out of everything a flight passes through, which (V, AoA, M, Re) combinations
actually matter enough to spend a CFD run on? Per the multipoint/robust
aerodynamic-shape-optimization framing in the user's own Notion CFD-workflow
notes ("CFD Simulation Workflow -- Best Practices" SS4): characterize the
condition space as a weighted distribution, J = sum_i w_i * f(V_i, AoA_i),
rather than either guessing a handful of conditions or brute-forcing the
whole flight envelope in CFD.

This is a pure *consumer* of `sim/` -- it runs a trajectory with the existing,
already-verified simulator and post-processes its output. It adds no new
physics and changes nothing under `sim/`.

### What is being reduced, and why by dynamic pressure

`sim.flow.flow_state(t, y, p)` already computes `V`, `alpha` (AoA), `M`, `Re`
and `q` (dynamic pressure) at any instant of any trajectory -- `run.py`
already samples it on a fine time grid for the max-Q figure. This module
samples the same quantities over the whole flight and reduces thousands of
samples down to `n_points` representative weighted conditions.

The weight is **time-integrated dynamic pressure**, `w_i ~ q(t_i) * dt_i`,
normalized to sum to 1 (the user's own choice, over plain time-weighting or
a full sensitivity/adjoint measure): aerodynamic loads and drag's effect on
the trajectory both scale with `q`, so this concentrates CFD effort where
drag actually costs altitude, and naturally discounts the slow pad-exit.

### Ascent only (the user's own scope call)

CFD optimization here only cares about the **ascent phase** -- launch to
apogee, `result.events["apogee"]` -- not descent/recovery. This also
sidesteps a real wrinkle the full-flight version of this tool hit: with no
restoring aerodynamic moment, a vehicle's orientation does not track the
relative wind through apogee, so the body-frame angle of attack can jump by
180 degrees past that point -- a descent-phase artifact that is simply out
of scope now, not a case this module needs to handle well.

### The reduction: equal-weight-mass binning along time

The raw samples are a dense, continuous curve in time, not a discrete set of
conditions -- they need reducing to `n_points` representative ones. This
bins along the time axis so that **every bin carries the same share of the
total q-weight** (not the same time span): `n_points` cut points are placed
on the *cumulative* normalized weight at the `1/n_points, 2/n_points, ...`
marks. The practical effect is that bins are narrow (fine time resolution)
wherever `q` is large -- e.g. around max-Q -- and wide wherever it is small,
so the table's resolution automatically follows where dynamic pressure is
concentrated, without a separate adaptive-binning algorithm. Each bin's
representative point is the q-weighted mean of `(V, alpha, M, Re)` within it;
its weight is the actual (not assumed-equal) sum of normalized weight it
captured.

### Scope -- what this first version does NOT do

- **Ascent only** (launch to apogee), per the user's explicit instruction --
  descent/recovery conditions are out of scope for this tool entirely, not
  merely down-weighted.
- **Single nominal trajectory only**, no wind, no turbulence (the user's own
  choice, over an ensemble of wind/turbulence-seeded flights). On a vertical
  no-wind ascent AoA stays near zero throughout, so the condition table from
  this version is mostly a reduction along `(V, M, Re)` with limited AoA
  variation -- an ensemble run across wind directions/turbulence seeds
  (reusing Step 46's Dryden model) is the natural next version if AoA
  sensitivity is wanted; not built here.
- **No worst-case/constraint handling.** The user's Notion notes flag that a
  pure weighted mean can neglect rare-but-catastrophic conditions (stall,
  high-AoA separation) and suggests adding a worst-case constraint or a
  mean + k*(std dev) robust-design objective. Not implemented in this first
  version -- the table is the weighted-mean set only.
- **No DOE/range output.** Only the "weighted discrete points" format (the
  user's choice) -- suitable for the cheap 2D/XFoil loop the Notion notes
  describe (cheap enough to run every weighted point directly) and as a
  manual input list for a handful of 3D CFD runs. The range/DOE format for
  an expensive 3D Response-Surface sweep is a separate, not-yet-built output
  mode.
"""

from __future__ import annotations

import csv
import dataclasses
import math
from pathlib import Path

import numpy as np

from apps.common.artifacts import ensure_dir, output_dir
from examples.worked_scenario import DEMO_SCENARIO
from sim.flow import flow_state
from sim.integrate import Result, run_sim
from sim.params import Params


@dataclasses.dataclass(frozen=True)
class WeightedCondition:
    """One representative CFD operating point, and the share of the
    flight's total time-integrated dynamic pressure it stands in for.
    `weight` across a full table sums to 1 (up to floating-point roundoff).
    """

    V: float          # m/s, relative-wind speed
    alpha_deg: float  # degrees, angle of attack
    M: float           # Mach number [-]
    Re: float          # Reynolds number [-]
    weight: float      # fraction of total time-integrated q this point represents


def select_cfd_conditions(
    result: Result, p: Params, n_points: int = 10, t_grid_n: int = 4000
) -> list[WeightedCondition]:
    """Reduce one flight's **ascent-phase** `(V, alpha, M, Re, q)` history
    (launch to apogee -- the user's explicit scope call, module docstring)
    to `n_points` dynamic-pressure-weighted representative conditions.

    Samples `sim.flow.flow_state` on a fine uniform time grid from launch to
    the apogee event (falling back to the last recorded time if the flight
    never registers one -- same "fall back to the last recorded sample"
    convention `run.py`'s own summary uses for the ground event), bins by
    equal shares of cumulative `q*dt`, and returns one `WeightedCondition`
    per non-empty bin (a bin can come back empty only if `n_points` exceeds
    the number of samples carrying nonzero weight, which `t_grid_n`'s
    default makes practically unreachable).
    """
    apogee_t = result.events.get("apogee")
    t_end = apogee_t if apogee_t is not None else result.t[-1]
    t_grid = np.linspace(0.0, t_end, t_grid_n)
    y_grid = result.raw.sol(t_grid)

    V = np.empty(t_grid_n)
    alpha = np.empty(t_grid_n)
    M = np.empty(t_grid_n)
    Re = np.empty(t_grid_n)
    q = np.empty(t_grid_n)
    for i, t in enumerate(t_grid):
        flow = flow_state(t, y_grid[:, i], p)
        V[i], alpha[i], M[i], Re[i], q[i] = flow.V, flow.alpha, flow.M, flow.Re, flow.q

    dt = np.gradient(t_grid)
    raw_weight = q * dt
    total = raw_weight.sum()
    if total <= 0.0:
        return []
    norm_weight = raw_weight / total

    cum = np.cumsum(norm_weight)
    boundaries = np.searchsorted(cum, np.arange(1, n_points) / n_points)
    groups = np.split(np.arange(t_grid_n), boundaries)

    conditions = []
    for idx in groups:
        if idx.size == 0:
            continue
        w = norm_weight[idx]
        w_sum = float(w.sum())
        if w_sum <= 0.0:
            continue
        conditions.append(
            WeightedCondition(
                V=float(np.average(V[idx], weights=w)),
                alpha_deg=float(math.degrees(np.average(alpha[idx], weights=w))),
                M=float(np.average(M[idx], weights=w)),
                Re=float(np.average(Re[idx], weights=w)),
                weight=w_sum,
            )
        )
    return conditions


def print_conditions_table(conditions: list[WeightedCondition]) -> None:
    """Plain-text table, same style as `run.py`'s `_print_sweep_table`.

    Printed in the order `select_cfd_conditions` returns -- i.e. time order,
    not weight order. Equal-weight-mass binning makes every bin's weight
    close to `1/n_points` by construction, so sorting by weight is close to
    an arbitrary shuffle; time order is what actually shows the flight's
    story (the Mach ramp up, the peak, the ramp back down).
    """
    header = f"{'weight':>8}{'V [m/s]':>12}{'AoA [deg]':>12}{'M':>10}{'Re':>14}"
    print(header)
    print("-" * len(header))
    for c in conditions:
        print(f"{c.weight:8.4f}{c.V:12.4f}{c.alpha_deg:12.4f}{c.M:10.4f}{c.Re:14.3e}")
    print(f"{'sum':>8}{sum(c.weight for c in conditions):12.4f}")


def save_conditions_csv(conditions: list[WeightedCondition], path: Path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["weight", "V_ms", "alpha_deg", "M", "Re"])
        for c in conditions:
            writer.writerow([c.weight, c.V, c.alpha_deg, c.M, c.Re])


def main() -> None:
    # Step 123 (Phase 2.18, D-139/D-140): the one demo
    # (examples/worked_scenario.py), the same scenario run.py uses. Its
    # ascent reaches supersonic Mach (selected rows span ~0.5-1.7; peak
    # ~1.75), which is what a K-class demo honestly produces (D-83).
    cfg = DEMO_SCENARIO.config
    params = cfg.params
    state0 = cfg.s0
    result = run_sim(params, state0)

    conditions = select_cfd_conditions(result, params, n_points=10)
    print_conditions_table(conditions)

    out_dir = ensure_dir(output_dir())
    out_path = out_dir / "cfd_conditions.csv"
    save_conditions_csv(conditions, out_path)
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()

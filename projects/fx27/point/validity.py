"""projects/fx27/point/validity.py -- Option C's measured error bound
(dev/docs/architecture-38-fx27-port.md SS38.3.2/SS38.5.7): reduce
`apps._shared.flight_stats.point_mass_flightpath` to the three printable
numbers per scenario fx27 users actually need.

`(a)` + `(b)`: `point_mass_flightpath` is the existing public diagnostic
(Step 137); this module is the ~40-line reduction to `alpha_burnout_deg`,
`alpha_max_deg @ q>1%`, and `still_air_residual_max`. `lambda_ratio` is
deliberately NOT surfaced: it is `NaN` everywhere under `aero.model ==
"constant"` (SS38.2.3) -- printing a `NaN` column would read as a defect.

Costs an extra ~2000-point `dynamics.derivatives` pass per flight
(`point_mass_flightpath`'s own grid) plus one more dense pass here for
`q(t)` -- opt-in per run script (`--validity`), never run by default on a
24-scenario sweep.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from apps._shared.flight_stats import point_mass_flightpath
from apps.sim.engine.flow import flow_state
from apps.sim.engine.integrate import Result
from apps.sim.engine.params import Params

_RESIDUAL_OK_RAD = 1.0e-6  # "config self-check" threshold -- machine precision, not a physics tolerance


@dataclasses.dataclass(frozen=True)
class ValidityReport:
    alpha_burnout_deg: "float | None"
    alpha_max_deg_q_gt_1pct: "float | None"
    still_air_residual_max: float


def check_validity(result: Result, p: Params) -> ValidityReport:
    """Option C's three numbers (SS38.5.7):

    - `alpha_burnout_deg`: `|alpha|` at the burnout event (exact --
      `flow_state`'s own `alpha`, not a grid lookup).
    - `alpha_max_deg_q_gt_1pct`: `max|alpha|` restricted to samples where
      `q > 1% of its own peak` -- the only window where the frozen-axis
      error (force along the body axis, not along `v_hat`) can move a
      number (SS38.3.1).
    - `still_air_residual_max`: must be ~0 to machine precision -- a
      non-zero value means wind got turned on by accident, i.e. this is a
      CONFIG self-check, not a physics result (SS38.2.3).

    Two windowing details, both required to avoid reporting a spurious
    "divergence" that is really just a grid artefact, not physics:

    1. **Grid restricted to the ascent (launch -> apogee)**, D-19/
       SS38.2.9's own window -- fx27 runs `terminate_on_apogee=True`, so
       it never computes anything past apogee; a whole-flight grid would
       pull in the tail-first free-fall descent (no recovery model here),
       where `alpha` legitimately approaches 180 deg and is not part of
       what this port is validating.
    2. **`V <= 0` samples excluded** -- the on-pad instant (`t=0`,
       `V=0`) is the one place `still_air_residual`'s identity is
       genuinely undefined, not approximately 0 (`flow_state`'s own
       documented degenerate case, `theta_v = atan2(0,0) = 0`, `alpha =
       atan2(0,0) = 0`, leaving a spurious `residual = theta_rail`
       there) -- `flight_stats.py`'s own module docstring says callers
       checking this identity should exclude it, the same way
       `lambda_ratio` already excludes `V <= 0` from a real ratio.
    """
    t_apogee = result.events.get("apogee")
    # D-19 window: ascent only, matching fx27's own terminate_on_apogee=True
    # scope -- None (degenerate flight, no apogee) falls back to
    # point_mass_flightpath's own whole-flight default grid.
    t_grid = np.linspace(0.0, t_apogee, 2000) if t_apogee is not None else None
    pmf = point_mass_flightpath(result, p, t_grid=t_grid)
    valid = pmf.V > 0.0  # exclude the on-pad degenerate instant (see above)

    t_burnout = result.events.get("burnout")
    if t_burnout is None:
        alpha_burnout = None
    else:
        y_burnout = result.raw.sol(t_burnout)
        alpha_burnout = float(abs(math.degrees(flow_state(t_burnout, y_burnout, p).alpha)))

    y_grid = result.raw.sol(pmf.t)
    flows = [flow_state(ti, y_grid[:, i], p) for i, ti in enumerate(pmf.t)]
    q = np.array([f.q for f in flows])
    alpha_deg = np.degrees(np.array([f.alpha for f in flows]))

    q_max = float(q[valid].max()) if valid.any() else 0.0
    mask = valid & (q > 0.01 * q_max)
    alpha_max = float(np.abs(alpha_deg[mask]).max()) if mask.any() else None

    residual = pmf.still_air_residual[valid]
    residual_max = float(np.nanmax(np.abs(residual))) if valid.any() else 0.0

    return ValidityReport(
        alpha_burnout_deg=alpha_burnout,
        alpha_max_deg_q_gt_1pct=alpha_max,
        still_air_residual_max=residual_max,
    )


def print_validity(name: str, report: ValidityReport) -> None:
    def fmt(x: "float | None") -> str:
        return "n/a" if x is None else f"{x:.3f}"

    status = "OK" if report.still_air_residual_max < _RESIDUAL_OK_RAD else "WARN: nonzero residual, check wind config"
    print(
        f"  [validity] {name}: alpha_burnout={fmt(report.alpha_burnout_deg)} deg, "
        f"alpha_max@q>1%={fmt(report.alpha_max_deg_q_gt_1pct)} deg, "
        f"still_air_residual_max={report.still_air_residual_max:.3e} rad ({status})"
    )

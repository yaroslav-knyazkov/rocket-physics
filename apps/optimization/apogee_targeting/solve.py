"""apps/optimization/apogee_targeting/solve.py -- a 1-D root finder (scipy
brentq) against an arbitrary Scenario-derived parameter, searching for the
value that puts a flight's apogee at a target altitude AGL. Promoted
(dev/docs/architecture-39-promote-apogee-target-solver.md, backlog B41) from
projects/fx27/point/estimate.py, written during the fx27 port
(architecture-38-fx27-port.md SS38.5.4) as a one-off, fx27-local module.

Works correctly WITH the mass model on (`Params.weight.m_d is not None`) --
unlike `apps.optimization.motor_selection.compare_motors`/
`apps.analysis.weight_aero_tradeoff.trade_surface.build_surface`, which both
*refuse* a mass-model-on baseline (D-82): those two guard against
mass-model-on because their own methodology assumes a constant-mass
baseline. This module has no such guard and needs none -- its whole purpose
is to search over a Scenario-derived parameter (e.g. dry airframe mass) and
re-derive the flight from scratch each iteration, so a mass-model-on
baseline is the normal case, not a hazard. See the mass-varying note below.

**Every mass-varying search goes through `Scenario` -> `assemble`, NEVER
`apps.sim.engine.params.replace`** (architecture-38 SS38.4.2): `assemble`
derives `weight` from the pieces and seeds `s0.m` from `weight.m`; a
post-hoc `params.replace` on an already-assembled `Config` would leave
`s0.m` stale, so the mass model would fly the OLD launch mass. A parameter
that does not feed into `weight`/`s0` (e.g. constant `C_x`) may safely use
either route; `param_setter` callers below use `Scenario.overrides` for it
anyway, for one tidy seam rather than two (the same choice `solve_cda.py`'s
own `apogee_for_cda` makes for `control.airbrake_*`).

The apogee-evaluation seam (`_apogee_for_scenario`, below) inlines
`assemble -> run_sim -> flight_stats` directly rather than importing
`projects.fx27.point.flight.run` (which does exactly this, but `apps/` must
never import `projects/` -- see dev/docs/architecture-39-promote-apogee-
target-solver.md SS39.3 for why this module does not just call that
function).
"""

from __future__ import annotations

import dataclasses
from typing import Callable

from scipy.optimize import brentq

from apps._shared.flight_stats import flight_stats
from apps.sim.engine.integrate import run_sim
from apps.sim.schema import Scenario, assemble


@dataclasses.dataclass(frozen=True)
class ApogeeTargetResult:
    """`(baseline, required, delta)` plus the target/achieved apogee and a
    reachability flag (the `solve_cda._solve_scalar` robustness pattern:
    an unbracketed target is reported and clamped, never a bare `brentq`
    `ValueError`). Named `ApogeeTargetResult`, not fx27's original
    `EstimateResult` -- this type is now generic, the old name stays only
    as `projects/fx27/point/estimate.py`'s local import alias (SS39.5)."""

    baseline: float
    required: float
    delta: float
    target_apogee_m: float
    achieved_apogee_m: "float | None"
    reachable: bool


def _apogee_for_scenario(scenario: Scenario) -> "float | None":
    """`assemble -> run_sim -> flight_stats.apogee_altitude`, inlined
    rather than imported from `projects.fx27.point.flight.run` (SS39.3) --
    that function's own body, minus the `FlightRun.cfg`/`.result` fields
    this module never reads."""
    cfg = assemble(scenario)
    result = run_sim(cfg.params, cfg.s0)
    return flight_stats(result, cfg.params).apogee_altitude


def solve_for_target_apogee(
    scenario: Scenario,
    param_setter: "Callable[[Scenario, float], Scenario]",
    baseline_value: float,
    bracket: "tuple[float, float]",
    target_apogee_agl: float = 3000.0,
    xtol: float = 1.0e-4,
) -> ApogeeTargetResult:
    """The generic engine (B41, SS39.2.2 Option C). `param_setter(scenario,
    x) -> Scenario` builds the scenario to evaluate at search value `x`;
    `baseline_value` is `x`'s own current value on `scenario` (reported
    back as `.baseline`/used for `.delta`, never searched over).

    Verbatim port of `estimate.py`'s private `_solve` (architecture-38
    SS38.5.4): evaluate both bracket ends first; an unbracketed target
    clamps to the nearer bound and reports `reachable=False` rather than
    letting `brentq` raise; `_apogee_for_scenario` returning `None` inside
    the search is treated as "far short of target", not `None - float`.
    """
    lo, hi = bracket

    def apogee_at(x: float) -> "float | None":
        return _apogee_for_scenario(param_setter(scenario, x))

    apogee_lo = apogee_at(lo)
    apogee_hi = apogee_at(hi)
    if apogee_lo is None or apogee_hi is None:
        raise ValueError(
            f"solve_for_target_apogee: one bound of bracket {bracket!r} never "
            "leaves the pad (no apogee event) -- nothing to solve."
        )

    lo_bound_apogee, hi_bound_apogee = apogee_lo, apogee_hi
    reachable = min(lo_bound_apogee, hi_bound_apogee) <= target_apogee_agl <= max(
        lo_bound_apogee, hi_bound_apogee
    )

    if not reachable:
        if target_apogee_agl > max(lo_bound_apogee, hi_bound_apogee):
            required, achieved = (hi, hi_bound_apogee) if hi_bound_apogee > lo_bound_apogee else (lo, lo_bound_apogee)
        else:
            required, achieved = (lo, lo_bound_apogee) if lo_bound_apogee < hi_bound_apogee else (hi, hi_bound_apogee)
        return ApogeeTargetResult(
            baseline=baseline_value,
            required=required,
            delta=required - baseline_value,
            target_apogee_m=target_apogee_agl,
            achieved_apogee_m=achieved,
            reachable=False,
        )

    def f(x: float) -> float:
        a = apogee_at(x)
        return (-abs(target_apogee_agl) - 1.0) if a is None else a - target_apogee_agl

    required = brentq(f, lo, hi, xtol=xtol)
    achieved = apogee_at(required)
    return ApogeeTargetResult(
        baseline=baseline_value,
        required=required,
        delta=required - baseline_value,
        target_apogee_m=target_apogee_agl,
        achieved_apogee_m=achieved,
        reachable=True,
    )


def estimate_airframe_mass(
    scenario: Scenario,
    target_apogee_agl: float = 3000.0,
    mass_bracket: "tuple[float, float]" = (2.0, 12.0),
    xtol: float = 1.0e-4,
) -> ApogeeTargetResult:
    """Unchanged name/signature/defaults from `estimate.py` (zero behavior
    change) -- the `Airframe.m` that puts this scenario's apogee at
    `target_apogee_agl`. Now a one-line caller into the generic engine."""

    def with_mass(s: Scenario, m: float) -> Scenario:
        return dataclasses.replace(
            s, rocket=dataclasses.replace(s.rocket, airframe=dataclasses.replace(s.rocket.airframe, m=m))
        )

    return solve_for_target_apogee(
        scenario, with_mass, scenario.rocket.airframe.m, mass_bracket, target_apogee_agl, xtol
    )


def estimate_cx(
    scenario: Scenario,
    target_apogee_agl: float = 3000.0,
    cx_bracket: "tuple[float, float]" = (0.0, 2.0),
    xtol: float = 1.0e-6,
) -> ApogeeTargetResult:
    """Unchanged name/signature/defaults from `estimate.py` -- the constant
    `Aero.C_x` that puts this scenario's apogee at `target_apogee_agl`,
    via `Scenario.overrides` (still `Scenario` -> `assemble`, never a
    post-hoc `params.replace` -- module docstring)."""

    def with_cx(s: Scenario, cx: float) -> Scenario:
        return dataclasses.replace(s, overrides={**s.overrides, "aero.C_x": cx})

    return solve_for_target_apogee(scenario, with_cx, scenario.rocket.aero.C_x, cx_bracket, target_apogee_agl, xtol)

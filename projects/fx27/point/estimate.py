"""projects/fx27/point/estimate.py -- 1-D solves against a target apogee:
dry-mass (fx27 `mass_estimation.estimate_mass`) and constant `C_x` (fx27
`drag_estimation.estimate_drag`), dev/docs/architecture-38-fx27-port.md
SS38.5.4.

No existing `apps/` function does a 1-D root find to a target apogee
(SS38.2.7): `apps.analysis.weight_aero_tradeoff.trade_surface.
build_surface` is a 2-D grid sweep that also refuses a mass-model-on
baseline, and `apps.optimization.airbrake_sizing.solve_cda._solve_scalar`
is private and coupled to `AirbrakeSpec` -- AC-10 forbids importing it.

**Every mass-varying objective below goes through `Scenario` ->
`assemble`, NEVER `apps.sim.engine.params.replace`** (SS38.4.2):
`assemble` derives `weight` from the pieces and seeds `s0.m` from
`weight.m`; a post-hoc `params.replace` on an already-assembled `Config`
would leave `s0.m` stale, so the mass model would fly the OLD launch
mass. `estimate_cx` could safely use either route (`C_x` is not derived
and does not feed `s0`) but uses `Scenario.overrides` for the same
reason `solve_cda`'s own `apogee_for_cda` does: one tidy seam, not two.

These two functions are the acceptance oracle for this whole port's
Option C decision (AC-3, SS38.9): they must reproduce fx27's own four
hardcoded solved figures (`cspace/rockets_ideal.py`) within 5%.
"""

from __future__ import annotations

import dataclasses

from scipy.optimize import brentq

from apps.sim.schema import Scenario

from .flight import run as run_flight


@dataclasses.dataclass(frozen=True)
class EstimateResult:
    """fx27's own `(baseline, required, delta)` return shape, plus the
    target/achieved apogee and a reachability flag (the `solve_cda.
    _solve_scalar` robustness pattern, SS38.5.4 note 1/2: an unbracketed
    target is reported and clamped, never a bare `brentq` `ValueError`)."""

    baseline: float
    required: float
    delta: float
    target_apogee_m: float
    achieved_apogee_m: "float | None"
    reachable: bool


def _solve(
    objective_scenario,
    baseline_value: float,
    bracket: "tuple[float, float]",
    target_apogee_agl: float,
    xtol: float,
) -> EstimateResult:
    lo, hi = bracket

    def apogee_at(x: float) -> "float | None":
        return run_flight(objective_scenario(x)).stats.apogee_altitude

    apogee_lo = apogee_at(lo)
    apogee_hi = apogee_at(hi)
    if apogee_lo is None or apogee_hi is None:
        raise ValueError(
            f"estimate: one bound of bracket {bracket!r} never leaves the pad "
            "(no apogee event) -- nothing to solve."
        )

    lo_bound_apogee, hi_bound_apogee = apogee_lo, apogee_hi
    reachable = min(lo_bound_apogee, hi_bound_apogee) <= target_apogee_agl <= max(
        lo_bound_apogee, hi_bound_apogee
    )

    if not reachable:
        # SS38.5.4 note 1: clamp to the nearer bound and report loudly,
        # rather than letting brentq raise on an unbracketed target.
        # `achieved` reuses the already-computed apogee_lo/apogee_hi --
        # `required` is always exactly `lo` or `hi`, so re-running the
        # flight here would just recompute a number already in hand.
        if target_apogee_agl > max(lo_bound_apogee, hi_bound_apogee):
            required, achieved = (hi, hi_bound_apogee) if hi_bound_apogee > lo_bound_apogee else (lo, lo_bound_apogee)
        else:
            required, achieved = (lo, lo_bound_apogee) if lo_bound_apogee < hi_bound_apogee else (hi, hi_bound_apogee)
        return EstimateResult(
            baseline=baseline_value,
            required=required,
            delta=required - baseline_value,
            target_apogee_m=target_apogee_agl,
            achieved_apogee_m=achieved,
            reachable=False,
        )

    def f(x: float) -> float:
        # SS38.5.4 note 2: `apogee_at` returning None (motor too small/
        # draggy at this x) must not raise inside brentq's own bracketing
        # -- treat it as "far short of target" instead of `None - float`.
        a = apogee_at(x)
        return (-abs(target_apogee_agl) - 1.0) if a is None else a - target_apogee_agl

    required = brentq(f, lo, hi, xtol=xtol)
    achieved = apogee_at(required)
    return EstimateResult(
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
) -> EstimateResult:
    """fx27's `mass_estimation.estimate_mass`: the `Airframe.m` that
    puts this scenario's apogee at `target_apogee_agl`. `Scenario` ->
    `assemble`, never `params.replace` (module docstring, SS38.4.2)."""

    def with_mass(m: float) -> Scenario:
        return dataclasses.replace(
            scenario,
            rocket=dataclasses.replace(
                scenario.rocket,
                airframe=dataclasses.replace(scenario.rocket.airframe, m=m),
            ),
        )

    return _solve(with_mass, scenario.rocket.airframe.m, mass_bracket, target_apogee_agl, xtol)


def estimate_cx(
    scenario: Scenario,
    target_apogee_agl: float = 3000.0,
    cx_bracket: "tuple[float, float]" = (0.0, 2.0),
    xtol: float = 1.0e-6,
) -> EstimateResult:
    """fx27's `drag_estimation.estimate_drag`: the constant `Aero.C_x`
    that puts this scenario's apogee at `target_apogee_agl`. Routed
    through `Scenario.overrides` (still `Scenario` -> `assemble`, never a
    post-hoc `params.replace` on an already-built `Config` -- module
    docstring)."""

    def with_cx(cx: float) -> Scenario:
        return dataclasses.replace(scenario, overrides={**scenario.overrides, "aero.C_x": cx})

    return _solve(with_cx, scenario.rocket.aero.C_x, cx_bracket, target_apogee_agl, xtol)

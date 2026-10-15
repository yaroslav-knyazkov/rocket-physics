"""App 4 -- airbrake C_dA determination against the real solver.

Answers the user's own framing of their `temp/AB_01.m` + `AB_01_sim.m` pair:
"smn like this but this time I have proper solver." The MATLAB precedent
fixed `m`, `g`, `rho`; took a mid-flight state from a separate simulation;
hand-rolled an explicit-Euler ballistic integrator with a constant total
`C_dA` and no thrust; and called `fminbnd` over the brake's own
`CdAa in [0, 10]` to minimize `(apogee - targetApogee)**2`.

This app keeps the precedent's *interface* -- one scalar brake `C_dA`,
user-supplied bounds, a target apogee, a reported convergence flag, a
printed altitude/velocity history -- and replaces its *engine* with the
project's real simulator: adaptive `solve_ivp`, the real thrust curve,
ISA/sounding atmosphere, q-scaled variable aero, the real additive brake
term (`sim/forces.py`'s `A_brake = flow.q * Cd * S_max * deploy_fraction`),
launched from the pad rather than from an injected mid-flight state (D-37).

Design: `dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.6 (in full,
including SS30.6.1) and SS30.2's F1-F8/F15-F19.

### Scope -- what this app deliberately does NOT do

- **Does not solve for `airbrake_Cd` and `S_max` separately.** `sim/forces.py`
  only ever uses the product `airbrake_Cd * airbrake_S_max` (F1), so solving
  for both is ill-posed (D-34). This app solves for one scalar,
  `C_dA_airbrake = Cd * S_max` [m^2], treats the mechanism's own `Cd` as a
  fixed design input, and *reports* the implied `S_max = C_dA / Cd`.
- **No deployment schedule, retraction, or rate limit.** Each of the three
  triggers (`sim/control.py`'s `_AIRBRAKE_TRIGGERS`, Step 65) is a pure
  *onset* latch -- backlog B19.
- **No descent-braking study.** `"after_apogee"` cannot be an apogee-sizing
  trigger (F19: the objective is flat by construction, the trigger fires
  only strictly after apogee). Descent physics is sound since the
  axial-drag sign fix (Step 93, D-91; B17 closed), but a descent objective
  is not built yet (roadmap B23). `evaluate_airbrake`
  is the report-only path for that trigger; `solve_airbrake` refuses it
  outright, loudly, without running a search.

### The three triggers -- which can be solved against an apogee target

(`sim/control.py`'s `p.control.airbrake_trigger`, Step 65, SS30.6.1):

| Trigger          | Apogee sensitive to `C_dA`? | This app's behaviour                         |
|------------------|------------------------------|-----------------------------------------------|
| `after_burnout`  | yes, strongly, monotonically  | full root-find for `C_dA` at a target apogee  |
| `after_time`     | yes, monotone at fixed `t_deploy`, decaying to zero as `t_deploy -> t_apogee` (F18) | root-find for `C_dA`; **and** the mirror solve, root-find for `t_deploy` at fixed `C_dA` (`solve_for="deploy_time"`) -- apogee is monotone **increasing** in `t_deploy` (F18), the opposite direction from `C_dA` |
| `after_apogee`   | no -- flat to ~2.4e-3 m of solver noise across the whole bound range (F19) | refuses to solve; `evaluate_airbrake` only |

### Method (D-35, SS30.6's five steps), implemented once in `_solve_scalar`

```
0. refuse up front if spec.trigger == "after_apogee" (F19)
1. p_lo = bounds[0], p_hi = bounds[1]
2. run both -> apogee_lo, apogee_hi               (2 sim runs, free diagnostics)
3. if apogee_lo == apogee_hi (to tolerance): the objective is FLAT -- name
   the cause and stop; if target is not bracketed: reachable = False,
   clamp to the nearer bound, report loudly, stop
4. scipy.optimize.brentq(lambda x: apogee(x) - target, *bounds, xtol=...)
5. one final run at the root -> Result + FlightStats + artifacts
```

A root-find, not the precedent's squared-residual minimization: F6/F18
measured strict monotonicity (decreasing in `C_dA`, increasing in
`t_deploy`), so the root is unique and bracketing is a *proof* of
reachability, not a hope -- and an unreachable target gets a diagnostic
that names the cause instead of a `fminbnd` call that returns a
plausible-looking bound with a "converged" flag.

Run with `python run_airbrake.py` (root wrapper, D-29) or
`python -m apps.airbrake_sizing.solve_cda` from the repo root.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
from pathlib import Path
from typing import Any

from scipy.optimize import brentq

from apps.common.artifacts import OUTPUT_DIR, ensure_dir
from apps.common.cli import add_config_arg, resolve_config
from apps.common.flight_stats import FlightStats, _assert_derivatives_reconstructible, flight_stats
from configs.schema import Config
from sim.gravity import altitude_agl
from sim.integrate import Result, run_sim
from sim.params import Control, Params
from sim.params import replace as params_replace
from sim.plotting import plot_trajectory_overlay

# F19: measured spread across the full [0, 10] m^2 bound range under
# "after_apogee" is 2.4e-3 m -- pure solver (adaptive-step) jitter, against
# hundreds of metres of real signal under "after_burnout"/"after_time"
# (F6/F18). This threshold sits comfortably above that noise floor and
# comfortably below the smallest genuine "after_time"-near-apogee signal
# F18 measured (8.85 m at t_deploy=10s, 996.75m brake-closed apogee), so it
# tells the two cases apart without false-positiving on a real, if small,
# gradient.
_FLAT_OBJECTIVE_ATOL_M = 0.1

# F7: brentq achieved a 1.4e-4 m residual on its target. 1e-2 m gives two
# orders of margin while still being "the achieved apogee is the target" in
# any unit this app prints (cm, not even mm).
_APOGEE_CONVERGED_ATOL_M = 1.0e-2

_AFTER_APOGEE_REFUSAL = (
    'trigger "after_apogee" cannot size a brake against an apogee target -- '
    "the trigger condition (v_z > 0) is true only strictly after apogee, so "
    "the apogee is independent of C_dA_airbrake by construction (measured "
    "flat to 2.4e-3 m across C_dA in [0, 10] m^2, i.e. solver noise; "
    "architecture-30-apps-4-5-and-configs.md F19). Call evaluate_airbrake "
    "for a report-only flight instead; a descent-rate objective for a "
    "post-apogee brake is not built yet (roadmap B23)."
)


@dataclasses.dataclass(frozen=True)
class AirbrakeSpec:
    """One airbrake-sizing study input (SS30.6.1/SS30.6's "API consequences").

    A target apogee is a *mission requirement*, not a vehicle property --
    `AirbrakeSpec` instances live in `apps/airbrake_sizing/targets.py`
    (D-23 style), never in `configs/`.
    """

    target_apogee_m: float
    trigger: str = "after_burnout"      # after_burnout | after_time | after_apogee
    deploy_time_s: float = 0.0          # s, read when trigger == "after_time"
    solve_for: str = "cda"              # "cda" | "deploy_time" | "none"
    cd_brake: float = 1.0
    # The precedent's own default bound, carried as a user input (D-34),
    # never a hardcoded constant. Under solve_for == "deploy_time" this
    # must be a *degenerate* pair (lo == hi): the single fixed C_dA of the
    # already-built brake the mirror solve searches a deploy time for.
    cda_bounds: tuple[float, float] = (0.0, 10.0)
    deploy_time_bounds: tuple[float, float] = (0.0, 60.0)   # s, solve_for == "deploy_time"
    xtol_m2: float = 1.0e-7   # brentq's xtol -- m^2 for solve_for="cda", s for "deploy_time"


@dataclasses.dataclass(frozen=True)
class AirbrakeSolution:
    """Everything one solve (or one report-only evaluation) produced."""

    cda_airbrake: float          # m^2, the answer (a bound if reachable is False)
    s_max_m2: float               # = cda_airbrake / spec.cd_brake, the mechanism-design output
    cda_rocket: float | None     # p.aero.S * p.aero.C_x, or None if aero.model != "constant"
    cda_total: float | None      # cda_rocket + cda_airbrake, or None
    trigger: str                 # which of the three laws flew (SS30.6.1)
    deploy_time_s: float | None  # the trigger instant that actually flew
    apogee_m: float               # achieved
    target_apogee_m: float
    apogee_error_m: float         # achieved - target
    reachable: bool                # was the target bracketed by the bounds?
    converged: bool | None        # None under evaluate_airbrake -- not applicable, no search ran
    n_sim_runs: int
    apogee_closed_m: float        # upper envelope (brake stowed / earliest-acting-equivalent bound)
    apogee_open_m: float          # lower envelope (brake fully open / latest-acting-equivalent bound)
    params: Params                 # the solved Params (brake overrides applied)
    result: Result                 # the solved trajectory
    stats: FlightStats             # the full ascent-window bundle at the solution
    result_closed: Result          # kept for the overlay plot
    result_open: Result


def brake_overrides(cda: float, spec: AirbrakeSpec) -> dict[str, Any]:
    """The **single** place the `control.airbrake_*` override dict is built
    (SS30.6: "a future combined-C_dA refactor only touches one function").
    Under Step 65's trigger dispatch this is the plain `"full"` law plus
    the trigger/time/Cd/S_max it needs -- no gain, no `kp = 1e9` to explain
    (F5/F17's saturated-gain trick is no longer needed).

    `cda / spec.cd_brake` is exact, not a reconstruction: the model only
    ever uses the product `Cd * S_max` (F1), so any `(Cd, S_max)` pair with
    this ratio reproduces the same `C_dA_airbrake` and the same apogee.
    """
    return {
        "control.airbrake_model": "full",
        "control.airbrake_trigger": spec.trigger,
        "control.airbrake_deploy_time": spec.deploy_time_s,
        "control.airbrake_Cd": spec.cd_brake,
        "control.airbrake_S_max": cda / spec.cd_brake,
    }


def apogee_for_cda(
    cda: float, cfg: Config, spec: AirbrakeSpec
) -> "tuple[float | None, Result, Params]":
    """This app's objective-function seam, the role `evaluate_motor` plays
    in App 3 (`apps/motor_selection/compare_motors.py`): one scalar in, one
    apogee *altitude* out (not the apogee *time* `Result.events["apogee"]`
    carries), no printing, no I/O, no global state.

    Returns `(None, result, p)` if the flight never produces an apogee
    event (too small/draggy to leave the pad in a useful sense, or does
    not come back down inside `p.solver.t_max`) -- the one signal
    `solve_airbrake`'s pre-flight check reads to fail loudly rather than
    silently root-finding against a `None`.
    """
    p = params_replace(cfg.params, brake_overrides(cda, spec))
    result = run_sim(p, cfg.s0)
    t_apogee = result.events["apogee"]
    apogee_m = float(altitude_agl(result.raw.sol(t_apogee), p)) if t_apogee is not None else None
    return apogee_m, result, p


def apogee_for_deploy_time(
    t_d: float, cda: float, cfg: Config, spec: AirbrakeSpec
) -> "tuple[float | None, Result, Params]":
    """The mirror objective-function seam (F18): `C_dA` held fixed, the
    trigger's own deploy time free. Reuses `brake_overrides` for every key
    except `control.airbrake_deploy_time`, which this function patches on
    top for its own search variable -- the same "one reserved key, one
    override on top" pattern `compare_motors.build_params` uses for
    `thrust.motor_curve`, so `brake_overrides` stays the single place the
    base dict is built.
    """
    overrides = {**brake_overrides(cda, spec), "control.airbrake_deploy_time": t_d}
    p = params_replace(cfg.params, overrides)
    result = run_sim(p, cfg.s0)
    t_apogee = result.events["apogee"]
    apogee_m = float(altitude_agl(result.raw.sol(t_apogee), p)) if t_apogee is not None else None
    return apogee_m, result, p


@dataclasses.dataclass(frozen=True)
class _SolveOutcome:
    """Internal: everything `_solve_scalar` produces, before the two thin
    callers (`solve_for="cda"` / `"deploy_time"`) assemble it into the
    public `AirbrakeSolution`."""

    reachable: bool
    converged: bool
    n_sim_runs: int
    root: float
    root_apogee: float
    root_result: Result
    root_params: Params
    apogee_closed_m: float
    apogee_open_m: float
    result_closed: Result
    result_open: Result


def _solve_scalar(
    objective, bounds: "tuple[float, float]", target: float, xtol: float, *, increasing: bool, spec: AirbrakeSpec, cfg: Config
) -> _SolveOutcome:
    """SS30.6's five-step method, implemented once. `objective(x) ->
    (apogee_m | None, Result, Params)` is one of the two seams above;
    `increasing` says which direction the objective moves in `x` (F6:
    `apogee_for_cda` is strictly decreasing; F18: `apogee_for_deploy_time`
    is strictly increasing) -- the root-find and the reachability clamp
    are symmetric in this one flag, not two copies of the method.

    "Closed"/"open" is this function's own upper/lower-envelope language,
    reused from the `C_dA` case for the deploy-time mirror solve too: the
    bound that behaves like "less brake effect" (brake stowed, or deployed
    so late it barely acts) always gives the *higher* apogee, regardless
    of which scalar is being searched -- `apogee_closed_m >= apogee_open_m`
    always holds given a correctly-measured monotone direction.
    """
    lo, hi = bounds
    apogee_lo, result_lo, params_lo = objective(lo)
    apogee_hi, result_hi, params_hi = objective(hi)
    n_runs = 2

    if apogee_lo is None or apogee_hi is None:
        raise ValueError(
            f"config {cfg.name!r} never leaves the pad (no apogee event at "
            f"one or both bounds {bounds!r}) -- nothing to solve."
        )

    if not increasing:
        apogee_closed, apogee_open = apogee_lo, apogee_hi
        result_closed, result_open = result_lo, result_hi
        params_closed, params_open = params_lo, params_hi
        closed_bound, open_bound = lo, hi
    else:
        apogee_closed, apogee_open = apogee_hi, apogee_lo
        result_closed, result_open = result_hi, result_lo
        params_closed, params_open = params_hi, params_lo
        closed_bound, open_bound = hi, lo

    if abs(apogee_closed - apogee_open) < _FLAT_OBJECTIVE_ATOL_M:
        if spec.trigger == "after_time":
            cause = (
                f'trigger "after_time" with deploy_time={spec.deploy_time_s:.3f} s is '
                "later than the brake-closed apogee, so the brake never acts "
                "before apogee. Lower deploy_time."
            )
        else:
            cause = f"trigger {spec.trigger!r} produces no sensitivity of apogee to this search variable."
        raise ValueError(
            "the objective is flat -- apogee with the brake fully open "
            f"({apogee_open:.3f} m) equals apogee with it stowed "
            f"({apogee_closed:.3f} m) to within solver tolerance. Cause: {cause}"
        )

    reachable = apogee_open <= target <= apogee_closed
    if not reachable:
        if target > apogee_closed:
            root, root_apogee = closed_bound, apogee_closed
            root_result, root_params = result_closed, params_closed
        else:
            root, root_apogee = open_bound, apogee_open
            root_result, root_params = result_open, params_open
        return _SolveOutcome(
            reachable=False,
            converged=False,
            n_sim_runs=n_runs,
            root=root,
            root_apogee=root_apogee,
            root_result=root_result,
            root_params=root_params,
            apogee_closed_m=apogee_closed,
            apogee_open_m=apogee_open,
            result_closed=result_closed,
            result_open=result_open,
        )

    def f(x: float) -> float:
        nonlocal n_runs
        n_runs += 1
        apogee_x, _, _ = objective(x)
        return apogee_x - target

    root = brentq(f, lo, hi, xtol=xtol)
    root_apogee, root_result, root_params = objective(root)
    n_runs += 1   # step 5's final confirmation run, kept separate from brentq's own internal evaluations
    converged = abs(root_apogee - target) <= _APOGEE_CONVERGED_ATOL_M

    return _SolveOutcome(
        reachable=True,
        converged=converged,
        n_sim_runs=n_runs,
        root=root,
        root_apogee=root_apogee,
        root_result=root_result,
        root_params=root_params,
        apogee_closed_m=apogee_closed,
        apogee_open_m=apogee_open,
        result_closed=result_closed,
        result_open=result_open,
    )


def _warn_if_airbrake_already_set(cfg: Config) -> None:
    """The app owns `control.airbrake_*` entirely (SS30.6): whatever the
    incoming `Config` set there is overwritten by `brake_overrides`. A
    config carrying a *previous* solution is a perfectly reasonable thing
    to re-solve, so this prints a warning rather than raising -- but it
    must say so, not silently clobber it.
    """
    default = Control()
    c = cfg.params.control
    if (c.airbrake_model, c.airbrake_trigger, c.airbrake_deploy_time, c.airbrake_Cd, c.airbrake_S_max) != (
        default.airbrake_model,
        default.airbrake_trigger,
        default.airbrake_deploy_time,
        default.airbrake_Cd,
        default.airbrake_S_max,
    ):
        print(
            f"NOTE: config {cfg.name!r} already set control.airbrake_* "
            f"(model={c.airbrake_model!r}, trigger={c.airbrake_trigger!r}, "
            f"deploy_time={c.airbrake_deploy_time}, Cd={c.airbrake_Cd}, "
            f"S_max={c.airbrake_S_max}) -- apps.airbrake_sizing owns this "
            "group entirely and has overridden it with its own solution."
        )


def _cda_rocket_and_total(params: Params, cda_airbrake: float) -> "tuple[float | None, float | None]":
    """`cda_rocket` is `None` unless `aero.model == "constant"`: under
    `"linearized"`/`"table"` the airframe's own `C_dA` is Mach/alpha-
    dependent, so no single number is honest to report (SS30.6). The
    brake's own `C_dA` stays exactly constant either way (F1), so the
    solve itself is unaffected -- only this *reported* total is withheld.
    """
    if params.aero.model != "constant":
        return None, None
    cda_rocket = params.aero.S * params.aero.C_x
    return cda_rocket, cda_rocket + cda_airbrake


def _deploy_time_for_report(trigger: str, spec_deploy_time_s: float, result: Result) -> "float | None":
    """The trigger instant actually read back for the printed/CSV report:
    the spec's own fixed value under `"after_time"`, else the burnout/
    apogee event time `result.events` recorded -- never a re-derivation.
    """
    if trigger == "after_time":
        return spec_deploy_time_s
    if trigger == "after_burnout":
        return result.events["burnout"]
    return result.events["apogee"]   # after_apogee, evaluate_airbrake only


def solve_airbrake(cfg: Config, spec: AirbrakeSpec) -> AirbrakeSolution:
    """Dispatches on `spec.solve_for`. `"cda"` root-finds `C_dA_airbrake` at
    a target apogee (the main case); `"deploy_time"` reuses the same
    `_solve_scalar` helper over `spec.deploy_time_bounds` at a fixed
    `C_dA` (F18's mirror solve, "my brake is this big, when do I pop it?").
    `"none"` is not a thing this function handles -- see `evaluate_airbrake`.

    Refuses `spec.trigger == "after_apogee"` up front (F19), before running
    a single simulation: the objective is flat by construction, there is
    nothing to solve. Checks the `sample_rate_hz` guard (F8) before that,
    so a sampled-data config fails in the first millisecond.
    """
    _assert_derivatives_reconstructible(cfg.params)
    _warn_if_airbrake_already_set(cfg)

    if spec.trigger == "after_apogee":
        raise ValueError(_AFTER_APOGEE_REFUSAL)

    if spec.solve_for == "cda":
        outcome = _solve_scalar(
            lambda cda: apogee_for_cda(cda, cfg, spec),
            spec.cda_bounds,
            spec.target_apogee_m,
            spec.xtol_m2,
            increasing=False,
            spec=spec,
            cfg=cfg,
        )
        cda_airbrake = outcome.root
    elif spec.solve_for == "deploy_time":
        if spec.cda_bounds[0] != spec.cda_bounds[1]:
            raise ValueError(
                "spec.solve_for == 'deploy_time' needs a single fixed C_dA "
                "(the brake that is already built), carried as a degenerate "
                f"cda_bounds pair (lo == hi); got {spec.cda_bounds!r}."
            )
        cda_airbrake = spec.cda_bounds[0]
        outcome = _solve_scalar(
            lambda t_d: apogee_for_deploy_time(t_d, cda_airbrake, cfg, spec),
            spec.deploy_time_bounds,
            spec.target_apogee_m,
            spec.xtol_m2,
            increasing=True,
            spec=spec,
            cfg=cfg,
        )
    elif spec.solve_for == "none":
        raise ValueError(
            "solve_airbrake does not handle spec.solve_for == 'none' -- "
            "call evaluate_airbrake directly for the report-only path."
        )
    else:
        raise ValueError(f"unknown spec.solve_for={spec.solve_for!r}")

    deploy_time_s = (
        outcome.root
        if spec.solve_for == "deploy_time"
        else _deploy_time_for_report(spec.trigger, spec.deploy_time_s, outcome.root_result)
    )
    cda_rocket, cda_total = _cda_rocket_and_total(outcome.root_params, cda_airbrake)
    stats = flight_stats(outcome.root_result, outcome.root_params)

    return AirbrakeSolution(
        cda_airbrake=cda_airbrake,
        s_max_m2=cda_airbrake / spec.cd_brake,
        cda_rocket=cda_rocket,
        cda_total=cda_total,
        trigger=spec.trigger,
        deploy_time_s=deploy_time_s,
        apogee_m=outcome.root_apogee,
        target_apogee_m=spec.target_apogee_m,
        apogee_error_m=outcome.root_apogee - spec.target_apogee_m,
        reachable=outcome.reachable,
        converged=outcome.converged,
        n_sim_runs=outcome.n_sim_runs,
        apogee_closed_m=outcome.apogee_closed_m,
        apogee_open_m=outcome.apogee_open_m,
        params=outcome.root_params,
        result=outcome.root_result,
        stats=stats,
        result_closed=outcome.result_closed,
        result_open=outcome.result_open,
    )


def evaluate_airbrake(cda: float, cfg: Config, spec: AirbrakeSpec) -> AirbrakeSolution:
    """No search at all: runs the spec's trigger/time/Cd at the given
    `cda` and reports flight stats. The report-only path `solve_for="none"`
    and the `"after_apogee"` demonstration both go through (SS30.6).

    `converged` is `None` -- not applicable, no search ran. `apogee_closed_m`
    /`apogee_open_m`/`result_closed`/`result_open` are all set from this one
    run (not two separate envelope runs, hence `n_sim_runs=1`): under
    `"after_apogee"` this is exact by construction (F19 -- the trajectory up
    to and including apogee is independent of `C_dA`, so "stowed" and "fully
    open" are the same trajectory up to apogee), and is this function's
    deliberate simplification for any other trigger a future `solve_for=
    "none"` caller might use it with (flagged in the Step 66 developer
    report).
    """
    _assert_derivatives_reconstructible(cfg.params)
    _warn_if_airbrake_already_set(cfg)

    apogee_m, result, params = apogee_for_cda(cda, cfg, spec)
    cda_rocket, cda_total = _cda_rocket_and_total(params, cda)
    deploy_time_s = _deploy_time_for_report(spec.trigger, spec.deploy_time_s, result)
    stats = flight_stats(result, params)

    reported_apogee = apogee_m if apogee_m is not None else float("nan")
    reported_error = (apogee_m - spec.target_apogee_m) if apogee_m is not None else float("nan")

    return AirbrakeSolution(
        cda_airbrake=cda,
        s_max_m2=cda / spec.cd_brake,
        cda_rocket=cda_rocket,
        cda_total=cda_total,
        trigger=spec.trigger,
        deploy_time_s=deploy_time_s,
        apogee_m=reported_apogee,
        target_apogee_m=spec.target_apogee_m,
        apogee_error_m=reported_error,
        reachable=True,
        converged=None,
        n_sim_runs=1,
        apogee_closed_m=reported_apogee,
        apogee_open_m=reported_apogee,
        params=params,
        result=result,
        stats=stats,
        result_closed=result,
        result_open=result,
    )


def _fmt(x: "float | None", spec: str) -> str:
    return "n/a" if x is None else format(x, spec)


def print_solution(sol: AirbrakeSolution, config_name: str | None = None) -> None:
    """The SS30.6 "Output" printed block. `config_name` is an optional
    convenience (not part of `AirbrakeSolution` -- `Params`/`Config` are
    disjoint, `Config.name` is not carried through `sim.params.replace`),
    defaulting to an empty label so the single-argument call the design
    doc's public-API listing shows still works.
    """
    name = config_name or "<unnamed config>"
    cd_brake = sol.cda_airbrake / sol.s_max_m2 if sol.s_max_m2 != 0.0 else 1.0

    print(f'Airbrake C_dA determination -- config "{name}", brake Cd = {cd_brake:.2f}')
    deploy_time_str = _fmt(sol.deploy_time_s, ".3f")
    if sol.trigger == "after_time":
        trigger_detail = f"(fully deployed from t = {deploy_time_str} s onward, no retraction)"
    elif sol.trigger == "after_burnout":
        trigger_detail = f"(fully deployed from burnout, t = {deploy_time_str} s onward, no retraction)"
    else:
        trigger_detail = f"(fully deployed from apogee, t = {deploy_time_str} s onward -- report-only)"
    print(f"  trigger                  {sol.trigger:<15} {trigger_detail}")
    print(f"  target apogee            {sol.target_apogee_m:.2f} m")
    print(f"  apogee, brake stowed     {sol.apogee_closed_m:.2f} m        <- upper envelope")
    print(f"  apogee, brake fully open {sol.apogee_open_m:.2f} m        <- lower envelope")

    if not sol.reachable:
        print(
            f"  REFUSED: target {sol.target_apogee_m:.2f} m is outside the "
            f"reachable range [{sol.apogee_open_m:.2f}, {sol.apogee_closed_m:.2f}] m "
            f"-- clamped to the nearer bound, C_dA_airbrake = {sol.cda_airbrake:.6f} m^2 "
            f"(apogee {sol.apogee_m:.2f} m). No brake setting on this airframe/motor "
            "reaches the target; the airframe or the motor has to change."
        )
    else:
        print(f"  --> C_dA_airbrake        {sol.cda_airbrake:.6f} m^2    (= {sol.cda_airbrake * 1.0e4:.2f} cm^2)")
        print(f"      implied S_max        {sol.s_max_m2:.6f} m^2    (at Cd = {cd_brake:.2f})")
        if sol.cda_rocket is not None:
            print(f"      C_dA_rocket          {sol.cda_rocket:.6f} m^2    (aero.model = \"constant\": S*C_x)")
            print(f"      C_dA_total           {sol.cda_total:.6f} m^2")
        else:
            print('      C_dA_rocket          n/a    (aero.model != "constant": no single honest number)')
        print(f"  achieved apogee          {sol.apogee_m:.2f} m        (error {sol.apogee_error_m:+.2e} m)")
        converged_str = "n/a (report-only, no search ran)" if sol.converged is None else ("yes" if sol.converged else "no")
        print(f"  converged                {converged_str}             ({sol.n_sim_runs} simulator runs)")

    s = sol.stats
    print("Flight at the solution (ascent-window extrema):")
    print(
        f"  burnout {_fmt(s.burnout_time, '.3f')} s | apogee {_fmt(s.apogee_time, '.2f')} s | "
        f"v_max {_fmt(s.max_velocity, '.1f')} m/s | v_avg {_fmt(s.avg_velocity, '.1f')} m/s | "
        f"a_max {_fmt(s.max_accel_g, '.1f')} g | max_q {_fmt(s.max_q / 1000.0 if s.max_q is not None else None, '.1f')} kPa"
    )


def save_solution_csv(sol: AirbrakeSolution, path: Path) -> None:
    """One row, every `AirbrakeSolution` scalar field plus the `FlightStats`
    fields -- self-describing, the same convention as App 3's CSV
    (`compare_motors.save_motor_csv`)."""
    s = sol.stats
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "trigger", "solve_for_deploy_time_s", "cda_airbrake_m2", "s_max_m2", "cda_rocket_m2",
                "cda_total_m2", "target_apogee_m", "apogee_m", "apogee_error_m", "reachable", "converged",
                "n_sim_runs", "apogee_closed_m", "apogee_open_m",
                "apogee_altitude", "apogee_time", "max_velocity", "avg_velocity", "max_accel", "max_accel_g",
                "max_q", "total_impulse", "burnout_time", "impact_time", "downrange_impact",
            ]
        )
        writer.writerow(
            [
                sol.trigger, sol.deploy_time_s, sol.cda_airbrake, sol.s_max_m2, sol.cda_rocket,
                sol.cda_total, sol.target_apogee_m, sol.apogee_m, sol.apogee_error_m, sol.reachable,
                sol.converged, sol.n_sim_runs, sol.apogee_closed_m, sol.apogee_open_m,
                s.apogee_altitude, s.apogee_time, s.max_velocity, s.avg_velocity, s.max_accel,
                s.max_accel_g, s.max_q, s.total_impulse, s.burnout_time, s.impact_time, s.downrange_impact,
            ]
        )


def save_overlay(sol: AirbrakeSolution, path: Path) -> None:
    """`sim.plotting.plot_trajectory_overlay`, three series -- the MATLAB
    precedent's altitude/velocity plot plus both envelopes, zero `sim/`
    change (F13)."""
    fig = plot_trajectory_overlay(
        {"brake stowed": sol.result_closed, "solved C_dA": sol.result, "brake fully open": sol.result_open},
        title="Airbrake C_dA sizing",
    )
    fig.savefig(path)


def main(argv: "list[str] | None" = None) -> None:
    """`python run_airbrake.py` / `python -m apps.airbrake_sizing.solve_cda`.
    Runs one named spec from `targets.SPECS` (`--spec`, default the main
    burnout solve) against `--config` (default `demo`),
    prints the SS30.6 report, writes `output/airbrake_sizing.csv` and
    `output/airbrake_sizing_overlay.png`. `--list-configs` lists every
    registered vehicle; running every named spec in one go is the test
    suite's job (`tests/test_airbrake_sizing.py`), not this CLI's."""
    from apps.airbrake_sizing.targets import SPECS

    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser, default="demo")
    parser.add_argument(
        "--spec",
        default=next(iter(SPECS)),
        metavar="NAME",
        choices=sorted(SPECS),
        help="named spec from apps/airbrake_sizing/targets.py",
    )
    args = parser.parse_args(argv)
    cfg = resolve_config(args)
    spec = SPECS[args.spec]

    if spec.solve_for == "none":
        cda = spec.cda_bounds[1]
        sol = evaluate_airbrake(cda, cfg, spec)
    else:
        sol = solve_airbrake(cfg, spec)
    print_solution(sol, config_name=cfg.name)

    ensure_dir(OUTPUT_DIR)
    csv_path = OUTPUT_DIR / "airbrake_sizing.csv"
    overlay_path = OUTPUT_DIR / "airbrake_sizing_overlay.png"
    save_solution_csv(sol, csv_path)
    save_overlay(sol, overlay_path)
    print(f"\nSaved {csv_path}")
    print(f"Saved {overlay_path}")


if __name__ == "__main__":
    main()

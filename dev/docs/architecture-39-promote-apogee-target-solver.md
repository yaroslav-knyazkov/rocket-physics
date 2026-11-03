## Кратко (RU)

- Документ описывает Phase 2.21, Step 144: перенос общего солвера "параметр -> целевой апогей"
  (сейчас `projects/fx27/point/estimate.py`, написан как одноразовый модуль во время fx27-порта,
  architecture-38 SS38.5.4) в постоянную библиотеку `apps/optimization/apogee_targeting/`
  (backlog **B41**).
- Переносится только логика `estimate.py` (`estimate_airframe_mass`/`estimate_cx` + их общий
  `_solve`). `projects/fx27/point/airbrake.py` не трогается (там уже тонкая обёртка над
  `apps/optimization/airbrake_sizing/solve_cda.py`, ничего переносить). `comparison.py`/`plots.py`
  (backlog B40) и сам `solve_cda.py`'s движок (`_solve_scalar`) — вне скоупа этого тикета.
- Ядро обобщено в один параметризованный движок `solve_for_target_apogee(scenario, param_setter,
  baseline_value, bracket, target_apogee_agl, xtol)`; `estimate_airframe_mass`/`estimate_cx`
  остаются именованными тонкими обёртками с теми же сигнатурами/дефолтами — ноль изменений
  поведения для существующих вызывающих мест.
- **Важная находка при переносе**: старый `estimate.py` считал апогей через
  `projects/fx27/point/flight.run` — тривиальную обёртку `assemble -> run_sim -> flight_stats`,
  без единой fx27-специфичной строчки. Если бы новый модуль в `apps/` импортировал
  `projects.fx27.point.flight`, это было бы нарушением направления зависимостей (`apps/` никогда
  не зависит от `projects/`) — архитектура этот риск явно обходит: три вызова инлайнятся прямо в
  новом модуле, `flight.py` не импортируется.
- `projects/fx27/point/estimate.py` становится тонкой обёрткой (по образцу `airbrake.py`),
  переэкспортирует те же два имени — `tests/test_fx27_port.py` не меняется ни на строку, импорт
  остаётся тем же.
- Новый файл тестов `tests/test_apogee_targeting.py` добавляет generic-тесты движка (недостижимая
  цель с обеих сторон, `ValueError` на границе без апогея, устойчивость к `None` апогею внутри
  скобки, round-trip по синтетической и по реальной `DEMO_SCENARIO`) — используется
  `monkeypatch`, этот приём уже принят в проекте (14 файлов). AC-3 оракульные тесты (4 шт.,
  числа fx27) остаются в `test_fx27_port.py` без изменений.
- Решений, требующих нового одобрения пользователя, не нашлось — название подпакета и форма API
  выбраны по существующей конвенции `apps/optimization/`. Один пункт на подтверждение
  оркестратору (не пользователю): что сам перенос — чисто additive, риска сдвига числовых пинов
  нет (ни один существующий тест не редактируется, только добавляются новые).

## Table of contents

- [SS39.1 Scope](#ss391-scope)
- [SS39.2 Subpackage name and API shape](#ss392-subpackage-name-and-api-shape)
- [SS39.3 The layering hazard found during promotion](#ss393-the-layering-hazard-found-during-promotion)
- [SS39.4 Public API — code skeleton](#ss394-public-api--code-skeleton)
- [SS39.5 `projects/fx27/point/estimate.py` becomes a thin wrapper](#ss395-projectsfx27pointestimatepy-becomes-a-thin-wrapper)
- [SS39.6 Test plan](#ss396-test-plan)
- [SS39.7 Directory structure diff](#ss397-directory-structure-diff)
- [SS39.8 Risk register / zero-behavior-change checklist](#ss398-risk-register--zero-behavior-change-checklist)
- [SS39.9 Rejected options](#ss399-rejected-options)
- [SS39.10 Tickets](#ss3910-tickets)
- [SS39.11 Open decisions for the user gate](#ss3911-open-decisions-for-the-user-gate)

## SS39.1 Scope

Phase 2.21, Step 144. Promotes **only** the root-finder logic of
`projects/fx27/point/estimate.py` (`estimate_airframe_mass`, `estimate_cx`, their shared `_solve`
helper) into `apps/optimization/`, closing backlog **B41** (`dev/status.json ->
backlog_ideas`). This generalizes architecture-38's own `SS38.5.4` deferred alternative
("B-NN-1"), narrowed per the user's 2026-11 decision: generalize `estimate.py`'s own engine, do
**not** attempt to unify it with `apps/optimization/airbrake_sizing/solve_cda.py`'s separate,
more elaborate engine (`_solve_scalar` — monotonicity-direction flag, flat-objective detection,
adaptive `xtol` refinement). `solve_cda.py` is untouched; see SS39.9.

Out of scope (confirmed by the orchestrator before this ticket was opened, re-confirmed here by
reading each file):

- `projects/fx27/point/comparison.py` / `plots.py` — backlog **B40**, the two matplotlib
  comparison plots. Explicitly deferred; not in this ticket.
- `projects/fx27/point/airbrake.py` — already a thin wrapper over
  `apps/optimization/airbrake_sizing/solve_cda.solve_airbrake`. Read in full: nothing left to
  promote. Untouched.
- `projects/fx27/point/flight.py` / `metrics.py` / `validity.py` — fx27-specific glue (`flight.py`
  is in fact fx27-*location*-specific only by address, not by content — see SS39.3 — but it stays
  where it is; this ticket does not move or delete it, only avoids creating a new dependency on
  it from `apps/`).
- `projects/fx27/cspace/`, `projects/fx27/euroc/`, `projects/fx27/data/` — real instance data,
  never moves to `apps/`.
- The gated, reserved **Step 143** ("standalone point-mass estimator, Option A") — a different,
  cruder, never-implemented closed-form estimator. Unrelated; this ticket does not consume or
  reference Step 143's reservation.

**Zero-behavior-change constraint**: this is additive-only. No existing `apps/` test, pin, or
public signature changes. See SS39.8 for the explicit checklist that confirms this.

## SS39.2 Subpackage name and API shape

### SS39.2.1 Location and naming — resolved by existing convention, not a user-facing fork

`apps/optimization/` already has two subpackages, named as gerund/noun phrases describing the
*activity* performed, not the mechanism:

| Existing subpackage                      | Activity named                              |
|-------------------------------------------|----------------------------------------------|
| `apps/optimization/airbrake_sizing/`      | sizing an airbrake                           |
| `apps/optimization/motor_selection/`      | selecting a motor                            |

Following this, the new subpackage is **`apps/optimization/apogee_targeting/`** (the activity:
targeting an apogee against an arbitrary scenario parameter) — not `apogee_target` (noun phrase,
breaks the gerund pattern) and not `target_apogee` (verb-first, also breaks it).

Module name inside it: **`solve.py`** (the one file; unlike `airbrake_sizing`, which splits
`solve_cda.py` (engine) from `targets.py` (named study-input literals), there is no equivalent
named-literal-set here — callers pass `target_apogee_agl`/`bracket` directly, there is no fixed
roster of named `ApogeeTargetSpec` instances the way `airbrake_sizing.targets.SPECS` is a fixed
roster of `AirbrakeSpec`s sized against `apps.input.demo_scenario.DEMO_SCENARIO`. If a future
caller wants a named-spec roster, add a `targets.py` then — not preemptively now, per this
project's "no speculative generality" norm).

Public import path: `from apps.optimization.apogee_targeting.solve import (...)` — same shape as
`from apps.optimization.airbrake_sizing.solve_cda import (...)`.

This is a naming-convention application, not an architectural fork: there is no second
reasonable option once the existing `airbrake_sizing`/`motor_selection` precedent is read. Not
raised as a `decision_required` table.

### SS39.2.2 Public API shape — generalize the core, keep the two named wrappers

Three options were weighed for the public shape:

| Option | Shape | Pros | Cons |
|--------|-------|------|------|
| **A. Verbatim move** | Move `_solve`, `estimate_airframe_mass`, `estimate_cx`, `EstimateResult` unchanged, just a new address. | Zero risk, zero design work. | Does not satisfy B41's own wording ("generalizing the per-parameter root-finders... against an arbitrary Scenario-derived parameter") — leaves the engine still only reachable through two hardcoded field-setters; a third future caller (e.g. a `Scenario`-level, not `Config`-level, airbrake-C_dA search) would have to copy-paste `_solve` again. |
| **B. One fully generic function only** | Drop `estimate_airframe_mass`/`estimate_cx` entirely; every caller builds its own `param_setter`/`baseline_value`/`bracket` inline. | Maximally general, least code. | Breaks the existing call sites (`projects/fx27/runs/cspace_ideal_mass.py`, `cspace_ideal_drag.py`, `tests/test_fx27_port.py` import `estimate_airframe_mass`/`estimate_cx` by name) — would force editing files this ticket's own "zero-behavior-change" constraint says not to touch, or force a wrapper anyway (reduces to Option C with extra churn). |
| **C. Generic core + two named convenience wrappers (chosen)** | `solve_for_target_apogee(scenario, param_setter, baseline_value, bracket, target_apogee_agl, xtol)` is the new public generic engine (what B41 actually asks for); `estimate_airframe_mass`/`estimate_cx` keep their exact original names, signatures, and defaults, now implemented as two one-line callers into the generic core. | Satisfies B41's "arbitrary Scenario-derived parameter" framing *and* preserves every existing call site and test import byte-for-byte (`projects/fx27/point/estimate.py`'s thin wrapper re-exports the same two names — see SS39.5). | None material — the only "cost" is one extra public name (`solve_for_target_apogee`) in the module, which is the entire point. |

**Chosen: C.** Not raised as a `decision_required` table needing the user's approval — B41's own
backlog wording already specifies this shape ("generalizing the per-parameter root-finders...
against an arbitrary Scenario-derived parameter"), and Option C is the only one of the three that
is simultaneously faithful to that wording and additive-only.

## SS39.3 The layering hazard found during promotion

Reading `projects/fx27/point/flight.py` in full (required by this ticket's own instructions)
surfaced a design fact not visible from `estimate.py` alone:

```python
def run(scenario: Scenario) -> FlightRun:
    """`assemble(scenario) -> run_sim -> flight_stats`, fx27's
    `build_flight` + `flight_metrics` in three calls (SS38.5.1)."""
    cfg = assemble(scenario)
    result = run_sim(cfg.params, cfg.s0)
    stats = flight_stats(result, cfg.params)
    return FlightRun(cfg=cfg, result=result, stats=stats)
```

`flight.run` is **itself** generic — three calls, all rooted at `apps.sim.schema`/
`apps.sim.engine.integrate`/`apps._shared.flight_stats`, zero fx27-specific content. It is
fx27-specific only *by address* (it happens to live under `projects/fx27/point/`), not by
content. `estimate.py`'s original `_solve` imported it (`from .flight import run as
run_flight`) and called `run_flight(objective_scenario(x)).stats.apogee_altitude`.

**This import must not be carried into `apps/optimization/apogee_targeting/solve.py`.** `apps/`
must never import from `projects/` — this is the project's established layering direction
(`architecture.md`'s "the engine never imports the application layer" rule, and the converse
holds just as hard: the library layer, `apps/`, never imports a specific application built on
top of it, `projects/*`). `tests/test_layering.py`'s G1 guard currently only scans
`apps/sim/engine` for this direction (engine -> application-layer bans); it does not scan
`apps/optimization/` for an `apps/` -> `projects/` violation, so nothing would have caught this
mechanically if it were introduced. The fix is architectural, not a test: **inline the same three
calls directly in the new module** (`assemble`, `run_sim`, `flight_stats` — exactly `flight.run`'s
own body, minus the parts `estimate.py` never used (`FlightRun`'s `cfg`/`result` fields — only
`.stats.apogee_altitude` was ever read)). See SS39.4 for the resulting private helper.

This is flagged here as a finding, not a `decision_required` fork — there is no second
reasonable option (importing `projects/` from `apps/` is not a live alternative to weigh against
inlining three lines; it is simply wrong for this codebase's layering). Noted as a candidate
backlog item in SS39.9 (extending G1-style scanning to all of `apps/`, not acted on in this
ticket).

## SS39.4 Public API — code skeleton

`apps/optimization/apogee_targeting/__init__.py` — one-line docstring, same convention as
`airbrake_sizing/__init__.py` / `motor_selection/__init__.py`:

```python
"""apps/optimization/apogee_targeting/ -- apogee-target root finder for an
arbitrary Scenario-derived parameter (dry mass, constant C_x, ... -- B41)."""
```

`apps/optimization/apogee_targeting/solve.py` — moved verbatim from `projects/fx27/point/
estimate.py` (SS38.5.4), with exactly two substantive changes: (1) the module docstring is
rewritten to describe the generic module, not fx27's acceptance oracle; (2) `_solve`'s
`objective_scenario: Callable[[float], Scenario]` closure parameter is replaced by the public
`param_setter: Callable[[Scenario, float], Scenario]` + `scenario` pair, and the function is
renamed and made public (`solve_for_target_apogee`), per SS39.2.2 Option C. The brentq
mechanics, the unreachable-target clamp, and the `None`-apogee guard inside `f()` are copied
**verbatim** — these are exactly the two "robustness notes" architecture-38's SS38.5.4 already
called out as lifted from `solve_cda._solve_scalar`'s hard-won behaviour, and this ticket does
not revisit them.

```python
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
```

## SS39.5 `projects/fx27/point/estimate.py` becomes a thin wrapper

Confirmed: this mirrors `projects/fx27/point/airbrake.py`'s existing wrapper of
`apps/optimization/airbrake_sizing/solve_cda.py` exactly. Replaces the ~140-line original with:

```python
"""projects/fx27/point/estimate.py -- thin fx27-local wrapper around
apps.optimization.apogee_targeting.solve (promoted dev/docs/architecture-39-
promote-apogee-target-solver.md, backlog B41), mirroring projects/fx27/
point/airbrake.py's wrapper of apps.optimization.airbrake_sizing.solve_cda.

Re-exports the two names fx27's own runs/ scripts
(runs/cspace_ideal_mass.py, runs/cspace_ideal_drag.py) and
tests/test_fx27_port.py import. `EstimateResult` is kept here as the
fx27-local alias of the promoted `ApogeeTargetResult` -- same shape, same
fields, SS38.5.4's original name -- not a separate type: nothing in this
project imports `EstimateResult` by name today (checked: only attribute
access on its instances, e.g. `res.required`/`res.reachable`), so the
alias exists purely so a future direct `from .estimate import
EstimateResult` import, if anyone ever writes one, keeps working under the
name this module always had.

These two functions remain the acceptance oracle for the fx27 port's
Option C decision (AC-3, architecture-38 SS38.9): `tests/test_fx27_port.py`
imports them through this same module path, unchanged.
"""

from apps.optimization.apogee_targeting.solve import ApogeeTargetResult as EstimateResult
from apps.optimization.apogee_targeting.solve import estimate_airframe_mass, estimate_cx

__all__ = ["EstimateResult", "estimate_airframe_mass", "estimate_cx"]
```

**No other file under `projects/fx27/` changes.** `tests/test_fx27_port.py`'s own import line
(`from projects.fx27.point.estimate import estimate_airframe_mass, estimate_cx`) is untouched —
same module path, same two names, same behavior. `projects/fx27/runs/cspace_ideal_mass.py` /
`cspace_ideal_drag.py` (`from projects.fx27.point.estimate import estimate_airframe_mass` /
`estimate_cx`) likewise need no edit. `projects/fx27/point/__init__.py` and
`projects/fx27/cspace/rockets_ideal.py` reference `estimate.estimate_airframe_mass`/`estimate_cx`
only in prose docstrings (checked via grep) — accurate before and after, no edit needed.

## SS39.6 Test plan

### SS39.6.1 `tests/test_fx27_port.py` — zero edits

Read in full (~221 lines, module docstring through `test_comparison_plots_have_the_expected_axes_
and_series`). Of its test functions, exactly four exercise `estimate_airframe_mass`/`estimate_cx`
(`test_ac3_estimate_airframe_mass_pro54_transition`, `test_ac3_estimate_airframe_mass_pro75`,
`test_ac3_estimate_cx_pro75`, `test_ac3_estimate_cx_pro54_transition_wider_tolerance`) — **all
four are fx27-data-specific numeric-oracle checks** against `PRO54_TRANSITION_IDEAL_MASS_KG`/
`PRO75_IDEAL_MASS_KG`/`PRO75_IDEAL_DRAG_CX`/`PRO54_TRANSITION_IDEAL_DRAG_CX` from fx27's own
`cspace/rockets_ideal.py`, including the explicitly-documented
`_AC3_TOLERANCE_PRO54_TRANSITION_CX` guard. None of this file's existing tests exercise *generic*
engine behavior (unreachable-target clamping, the pad-bound `ValueError`, the mid-search `None`
guard) at all — those code paths were only ever reached indirectly, through AC-3's four
always-reachable cases.

**Conclusion: nothing moves.** There is no generic-behavior test currently sitting in
`test_fx27_port.py` to relocate. All four AC-3 tests stay exactly as written, calling through the
now-thin wrapper — this file is not edited by this ticket at all. This is the cleanest possible
confirmation of the zero-behavior-change constraint (SS39.8).

### SS39.6.2 `tests/test_apogee_targeting.py` — new, generic engine tests

New file, named to match the subpackage (`test_airbrake_sizing.py` <-> `airbrake_sizing/`,
`test_motor_selection.py` <-> `motor_selection/` precedent). House testing style per
`test_airbrake_sizing.py`'s own docstring: "no fixtures, no conftest.py, plain `assert` +
`math.isclose`"; `monkeypatch` is already idiomatic in this suite (14 existing files use it,
including `test_airbrake_sizing.py`'s sibling files). Two tiers:

**Tier 1 — pure-logic tests via `monkeypatch`.** `monkeypatch.setattr(solve, "_apogee_for_
scenario", <fake>)` replaces the one physics-touching seam with a deterministic function,
letting `scenario`/`param_setter` be trivial placeholders (`param_setter=lambda s, x: x`,
`scenario=None`) — these tests run in milliseconds and exercise logic branches that are
difficult or impossible to hit with a real flight (monotonic real objectives never produce a
`None` apogee strictly *inside* an otherwise-valid bracket):

1. `test_unreachable_target_above_max_clamps_to_hi_bound` — fake apogee = identity; target above
   both bounds; assert `reachable is False`, `required == hi`, `achieved_apogee_m == hi`.
2. `test_unreachable_target_below_min_clamps_to_lo_bound` — mirror, target below both bounds.
3. `test_bound_with_no_apogee_event_raises_valueerror` — fake apogee returns `None` at one bound;
   assert `pytest.raises(ValueError, match="never leaves the pad")`.
4. `test_none_apogee_strictly_inside_bracket_does_not_crash` — fake apogee is `None` everywhere
   except exactly at the two bracket bounds (deliberately non-physical, to force `brentq` to
   probe an interior `None`); assert no exception propagates and `reachable is True` (the
   bound-only reachability check already passes).
5. `test_converges_to_the_analytic_root_within_xtol` — fake apogee `= 1000.0 - 2.0 * x` (a known
   affine function); solve for a target inside `[1000 - 2*hi, 1000 - 2*lo]`; assert `required`
   matches the closed-form root within `xtol`, and `baseline`/`delta` are plumbed through
   correctly from the `baseline_value` argument (the one field name that changed meaning-adjacent
   wording from `estimate.py`'s original docstring, pinned here explicitly).

**Tier 2 — one real-physics regression test, no fx27 data.** Uses
`apps.input.demo_scenario.DEMO_SCENARIO` (mass model ON, `mass_model="endpoints"` —
`apps/optimization/` tests should not need `projects/fx27` fixtures, and should not be the first
place a real-physics check for this module runs):

6. `test_estimate_airframe_mass_on_demo_scenario_is_reachable_and_converges` — pick a
   `target_apogee_agl` and `mass_bracket` around `DEMO_SCENARIO`'s own (unmodified) apogee (no
   fx27 numbers involved); assert `reachable is True` and `abs(achieved_apogee_m -
   target_apogee_agl)` is small. This is the regression guard against a future reintroduction of
   the `params.replace`-on-assembled-`Config` staleness bug SS38.4.2/this module's own docstring
   warns against: if a future edit swapped `Scenario -> assemble` for a post-hoc `params.replace`,
   `s0.m` would go stale and the search would no longer actually respond to the swept mass, so
   this test would stop converging (or converge to a physically wrong value) rather than silently
   passing.
7. `test_estimate_cx_on_demo_scenario_is_reachable_and_converges` — same shape, for `estimate_cx`.

Both tier-2 tests run a handful of real flights each (same order of cost as
`test_airbrake_sizing.py`'s own round-trip test) — not "slowest in the suite" territory the way
the four real AC-3 tests are (those run against heavier fx27 vehicles with tighter tolerances).

## SS39.7 Directory structure diff

```
apps/optimization/
  airbrake_sizing/        (unchanged)
  motor_selection/         (unchanged)
  apogee_targeting/        NEW
    __init__.py             NEW -- one-line docstring (SS39.4)
    solve.py                NEW -- ApogeeTargetResult, solve_for_target_apogee,
                             estimate_airframe_mass, estimate_cx (SS39.4)

projects/fx27/point/
  estimate.py              REWRITTEN -- thin wrapper, ~20 lines (was ~153) (SS39.5)
  airbrake.py              unchanged (confirmed nothing to promote)
  flight.py                unchanged (stays put, SS39.1/SS39.3)
  comparison.py, plots.py  unchanged (backlog B40, out of scope)
  metrics.py, validity.py  unchanged

tests/
  test_apogee_targeting.py NEW -- 7 tests, generic engine behavior (SS39.6.2)
  test_fx27_port.py        unchanged (SS39.6.1)
```

## SS39.8 Risk register / zero-behavior-change checklist

This ticket is additive-only; the explicit checklist confirming no existing pin or test can
shift:

| Check | Status |
|-------|--------|
| `tests/test_fx27_port.py` source — edited? | No (SS39.6.1) |
| `estimate_airframe_mass`/`estimate_cx` public signatures (names, params, defaults, return type shape) | Identical (SS39.4) |
| `EstimateResult`/`ApogeeTargetResult` field names/order | Identical (`baseline`, `required`, `delta`, `target_apogee_m`, `achieved_apogee_m`, `reachable`) |
| `_solve`'s brentq call, bracket-reachability clamp, `None`-apogee guard in `f()` | Copied verbatim into `solve_for_target_apogee` (SS39.4) — no logic change, only the closure-vs-callback parameter shape |
| Any `apps/` module edited? | No — only one new subpackage added |
| Any existing `apps/` test file edited? | No |
| `tests/test_layering.py` G1/G2/G3/G5/G6 guards | Unaffected: `apogee_targeting/` is importable (G2), imports nothing banned (G1 does not even scan it since it is outside `ENGINE_DIR`; G3's banned-network-import scan does cover `apps/` broadly and the new module imports none), no network import (G3), no retired path touched (G6) |
| `projects/fx27/point/estimate.py` call sites (`runs/cspace_ideal_mass.py`, `runs/cspace_ideal_drag.py`) | Unedited, same import path, same behavior (SS39.5) |
| New `apps/` -> `projects/` import introduced? | No — the one real hazard found (SS39.3), resolved by inlining, not importing |

**Residual risk, named explicitly**: none identified. The one place a subtle regression could in
principle hide is if `solve_for_target_apogee`'s generalized `param_setter(scenario, x)` callback
shape somehow evaluated `scenario`/`x` in a different order or with different rounding than the
original closure-based `objective_scenario(x)` did — checked by inspection (SS39.4's skeleton):
the body is copied verbatim, only the two one-line `with_mass`/`with_cx` closures gained an
explicit `s` parameter (previously captured `scenario` by closure) — behaviorally identical.
`tests/test_apogee_targeting.py`'s tier-2 tests (SS39.6.2 #6/#7) are the regression guard a
developer runs to confirm this empirically, not just by inspection.

## SS39.9 Rejected options

- **Unify with `solve_cda.py`'s own engine (`_solve_scalar`)** — architecture-38 SS38.5.4's
  original "B-NN-1" framing (superseded by B41) suggested one shared engine for all three
  parameters (mass, `C_x`, airbrake `C_dA`). Rejected again here, for the same reason plus one
  new one: `_solve_scalar` has materially diverged features this module's two parameters do not
  need (an `increasing` monotonicity-direction flag, flat-objective detection with a named
  tolerance, adaptive-`xtol` refinement via measured local slope) — forcing `estimate_
  airframe_mass`/`estimate_cx` through that richer, airbrake-tuned engine would be a bigger,
  riskier change for a benefit (one shared engine instead of two small ones) that is not asked
  for by B41 and was explicitly placed out of scope for this ticket (orchestrator's framing:
  "already a thin wrapper... nothing left to promote there... do not touch it").
- **Option A (verbatim move, SS39.2.2)** — rejected: does not satisfy B41's "arbitrary
  Scenario-derived parameter" wording, leaves a third future caller no better off than before.
- **Option B (drop the named wrappers, SS39.2.2)** — rejected: breaks existing call-site imports,
  violating this ticket's own additive-only constraint.
- **A `targets.py`-style named-spec roster for `apogee_targeting/`** (mirroring `airbrake_sizing.
  targets.SPECS`) — rejected for now, SS39.2.1: no current caller needs a fixed named roster of
  targets; add it when one does, not speculatively.
- **Extending `tests/test_layering.py`'s G1 guard to scan all of `apps/` for `apps/` -> `projects/`
  imports** (not just the engine for `apps/` -> application-layer imports) — a reasonable
  hardening noticed while writing SS39.3, but it is a change to an existing, unrelated test file
  and a broader-scope guard addition than this ticket's own boundary; logged as a candidate
  backlog item for the orchestrator to consider separately, not actioned here.

## SS39.10 Tickets

### [AT-1] New subpackage: `apps/optimization/apogee_targeting/`
- **Module/boundaries:** `apps/optimization/apogee_targeting/__init__.py` (new),
  `apps/optimization/apogee_targeting/solve.py` (new). No existing file under `apps/` is edited.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true
Spec: this doc, SS39.4 (full code skeleton) + SS39.2 (naming/API rationale) + SS39.3 (the
layering constraint — `solve.py` must not import `projects.*`, must inline `_apogee_for_
scenario` instead). Write `ApogeeTargetResult`, `_apogee_for_scenario`,
`solve_for_target_apogee`, `estimate_airframe_mass`, `estimate_cx` exactly as specced (the
brentq/clamp/`None`-guard body is a verbatim port — do not "improve" it as part of this ticket).
Follow the `tdd` skill: write `tests/test_apogee_targeting.py` (ticket AT-3) before/alongside
this module, not after.

### [AT-2] `projects/fx27/point/estimate.py` -> thin wrapper
- **Module/boundaries:** `projects/fx27/point/estimate.py` only (rewrite in place). No other file
  under `projects/fx27/` is touched.
- **Assignee:** developer
- **depends_on:** [AT-1]
- **parallel_safe:** false (needs AT-1's module to exist first; touches a file AT-1 does not, so
  would be parallel_safe on file boundaries alone, but the dependency ordering makes it
  sequential)
Spec: this doc, SS39.5 (full wrapper code) + SS39.1 (confirm no other `projects/fx27/` file needs
touching — `runs/cspace_ideal_mass.py`/`cspace_ideal_drag.py`/`point/__init__.py`/`cspace/
rockets_ideal.py` all already reference `estimate.py` by the same module path and the same two
function names; verify this still holds against the actual tree before closing the ticket, in
case something drifted since this doc was written).

### [AT-3] New tests: `tests/test_apogee_targeting.py`
- **Module/boundaries:** `tests/test_apogee_targeting.py` (new file only).
- **Assignee:** developer
- **depends_on:** [AT-1] (imports `apps.optimization.apogee_targeting.solve`)
- **parallel_safe:** false (depends_on AT-1; could run in parallel with AT-2 since file
  boundaries do not overlap, but keep sequential unless the orchestrator confirms AT-1 is fully
  merged first)
Spec: this doc, SS39.6.2 (all 7 tests specified: 5 tier-1 `monkeypatch`-based pure-logic tests, 2
tier-2 real-physics regression tests against `apps.input.demo_scenario.DEMO_SCENARIO`). Follow
`test_airbrake_sizing.py`'s house style (no fixtures, no conftest.py, plain `assert`).

### [AT-4] Verification: confirm zero behavior change
- **Module/boundaries:** none (verification only — runs the existing suite, does not edit files).
- **Assignee:** developer (as the step's own closing gate) or qa
- **depends_on:** [AT-1, AT-2, AT-3]
- **parallel_safe:** false
Spec: this doc, SS39.8's checklist. Run `tests/test_fx27_port.py` and confirm its 4 AC-3 tests
still pass with the exact same pass/fail outcome and the same measured `_pct_error` values as
before this ticket (the wrapper must be behaviorally transparent) — re-run and diff against the
pre-ticket baseline if in doubt, do not just check "still green". Run the full suite per this
project's chunking convention (`CLAUDE.md` "Профиль проекта" ловушки) and confirm no numeric pin
outside the two new/changed files moved.

## SS39.11 Open decisions for the user gate

None found that need a user "yes" before implementation starts. This is an incremental,
additive-only architecture step on an already-approved stack (no new dependency, no new
external service, no stack pivot) — per this role's own "incremental architecture of an already
existing stage" rule, it goes through the standard flow (comparison tables above) without a
`grilling` round. The one item worth the orchestrator's attention (not the user's) is SS39.9's
closing note: extending `test_layering.py`'s G1 guard to scan `apps/` -> `projects/` broadly is a
reasonable follow-up, logged as a candidate backlog item, not a blocking decision for this
ticket.


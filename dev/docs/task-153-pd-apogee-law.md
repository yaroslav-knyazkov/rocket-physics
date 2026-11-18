# Task 153 -- `pd_apogee`: a third Tier-1 predictive sampled law (PD)

## Кратко (RU)

- Третий закон управления аэротормозом в `apps/control/flight_software/laws.py`, рядом с `proportional_drag` и `pi_apogee` -- те же предиктор `drag_aware_predicted_apogee` и каркас (сигнатура, `NamedTuple`-состояние, регистрация в `control.py`).
- Добавляется PD: `cmd = clip(kp*error + kd*d_error, 0, 1)`, где `d_error` -- обратная разность по последовательным значениям `error` с тем же `dt`, что уже считает `pi_apogee`.
- Новое поле `Control.airbrake_kd: float = 0.0` (инертно по умолчанию, та же договорённость, что у `airbrake_ki`).
- Два архитектурных развилки отданы на решение пользователю (`decision_required` в чат-ответе): (1) что делать с `d_error` на первом тике (0.0 vs пропуск D-члена), (2) клэмпить ли D-член отдельно перед суммированием с P (derivative kick на входе в окно коаста).
- Полный TDD-бриф для разработчика: 4 юнит-теста по образцу существующих + решение по closed-loop кейсу в `test_harness.py` (рекомендация: не нужен для первого прохода, Tier-1 закрытый цикл уже покрыт через `proportional_drag`/`pi_apogee`).
- Это НЕ фиксация архитектуры/стека -- тот же уже одобренный паттерн sampled-law реестра (Step 107/108), применённый третий раз. Полный прогон тестов и числовые пины обязательны (TDD-биндинг жёсткий, carve-out D-181 не применяется).

---

## Table of contents

- [SS153.1 Scope](#ss1531-scope)
- [SS153.2 Derivative term definition](#ss1532-derivative-term-definition)
- [SS153.3 New state class: `PdApogeeState`](#ss1533-new-state-class-pdapogeestate)
- [SS153.4 New `Control` field: `airbrake_kd`](#ss1534-new-control-field-airbrake_kd)
- [SS153.5 Registration](#ss1535-registration)
- [SS153.6 Sign/saturation behavior](#ss1536-signsaturation-behavior)
- [SS153.7 TDD brief for developer](#ss1537-tdd-brief-for-developer)
- [SS153.8 Out of scope](#ss1538-out-of-scope)

---

## SS153.1 Scope

Add a third registered sampled law, `pd_apogee`, to `apps/control/flight_software/laws.py`. It reuses, unchanged:

- `drag_aware_predicted_apogee(h, v, g, m, k)` (laws.py:16-45) -- the closed-form predictor, bit-for-bit.
- `_k(c, f_b_prev)` (laws.py:48-55) -- the onboard-model drag coefficient helper.
- `estimator.step(...)` (`apps/control/flight_software/estimator.py`) -- same `prev.est` threading every existing law uses, no changes to that module.
- The `fn(t_k, meas, p, state) -> (cmd, state)` signature and registration mechanism `pi_apogee`/`proportional_drag` already use (laws.py:70-104, `apps/sim/engine/control.py:456-477`).

This is additive only: no existing law, state class, or `Control` field changes shape. `proportional_drag` and `pi_apogee` are both regression-pinned elsewhere (`tests/test_controllers.py`) and must keep passing unchanged.

## SS153.2 Derivative term definition

`error_k = h_a_k - target` is already computed every tick by every existing law (laws.py:76/96). The D term is a **backward difference** over consecutive `error` values, using the exact same `dt` computation `pi_apogee` already uses:

```
dt = 0.0 if prev.est is None or prev.est.t_prev is None else t_k - prev.est.t_prev
d_error = 0.0 if dt <= 0.0 else (error - prev.error_prev) / dt
```

Note the `dt <= 0.0` guard (not just `prev.est is None`) -- mirrors `estimator.py`'s own `_step_alpha_beta` dt-guard (estimator.py:55), covering a repeated/out-of-order tick the same way, not just the very first call.

**`decision_required` -- first-tick edge case.** On the very first call `prev.error_prev` does not exist yet (state is fresh/default). Two options:

| Option | Behavior | Pros | Cons |
|---|---|---|---|
| **A -- `d_error = 0.0` on first tick** (recommended) | Same convention `pi_apogee` already uses for `integral` at the first tick (dt=0.0 there too, laws.py:92/103) -- reduces to pure P for exactly one tick, then PD from tick 2 onward | Consistent with the existing law's own first-tick convention; trivial to implement (`dt <= 0.0` guard already forces `d_error=0.0`); no special-cased branch needed | One tick of "P-only" behavior before D kicks in -- negligible at typical sample rates (10s-100s of Hz relative to coast duration of several seconds) |
| **B -- skip D term entirely on first tick (treat as `None`, not `0.0`)** | Functionally identical output to A here (since `kd * 0.0 == 0.0` regardless of why), but requires an explicit `Optional[float]` sentinel distinguishing "no previous error" from "previous error was exactly 0.0" | None over A -- same numeric result for this law's purposes, since the vacuum-limit/drag-coast predictor never yields exactly `error_prev == 0.0` in a way that matters | Extra state complexity (sentinel/Optional threading) for zero behavioral difference -- `dt <= 0.0` already disambiguates "no valid previous sample" from "previous error was zero" without needing a separate flag |

Recommendation: **Option A**. It is strictly simpler, matches the `dt<=0.0` guard pattern already in this file and in `estimator.py`, and produces the identical numeric output to Option B for every real scenario (the only case they'd differ is a contrived `prev.error_prev` sentinel check that never changes `d_error`'s computed value). Flagging as `decision_required` only because it is a genuine, user-visible control-law design choice (what the controller does on its very first active tick), not because the two options differ numerically.

## SS153.3 New state class: `PdApogeeState`

Mirrors `ProportionalDragState`/`PiApogeeState`'s shape (laws.py:58-67, 81-86) exactly -- same `est` field/docstring convention, `f_b_prev` for the `_k()` one-tick-delayed self-consistency, plus `error_prev` for the new D term:

```python
class PdApogeeState(NamedTuple):
    # See ProportionalDragState.est's own comment above -- same honest
    # either-model type hint, same reason.
    est: "Optional[estimator.EstimatorState | estimator.AlphaBetaState]" = None
    error_prev: float = 0.0
    f_b_prev: float = 0.0
```

Default `error_prev=0.0` is inert here because the first-tick `dt<=0.0` guard (SS153.2) already zeroes `d_error` regardless of `error_prev`'s default value -- the default is never actually read on a real first tick, only present so the `NamedTuple` has a defined value before the first `pd_apogee` call.

## SS153.4 New `Control` field: `airbrake_kd`

One new field in `apps/sim/engine/params.py`'s `Control` dataclass, placed immediately after `airbrake_ki` (params.py:222), following that file's exact documentation convention (unit, default, inert-when-zero framing, which law reads it):

```python
airbrake_ki: float = 0.0          # pi_apogee's integral gain [1/(m*s)]; 0.0 = inert
airbrake_kd: float = 0.0          # pd_apogee's derivative gain [s]; 0.0 = inert
```

Units check: `error` is in meters, `d_error = d(error)/dt` is in m/s, and `kd * d_error` must be dimensionless (same as `kp * error`) to sit in the same `clip(..., 0, 1)` sum -- so `kd` has units of seconds (`[cmd]/[m/s] = s`), matching `airbrake_kp`'s implicit `[1/m]` and `airbrake_ki`'s documented `[1/(m*s)]`.

No other `Control` field is needed. `airbrake_kp`/`airbrake_target_apogee_m` are reused by name exactly as `proportional_drag`/`pi_apogee` already reuse them (params.py:219-221 comment block) -- extend that comment's reused-field list to mention `pd_apogee` alongside the other two when editing it (one-line addition, not a rewrite).

## SS153.5 Registration

`pd_apogee` is registered in `apps/sim/engine/control.py` exactly like the other two sampled laws -- find the existing `register_sampled_law("proportional_drag", ...)`/`register_sampled_law("pi_apogee", ...)` call site (same module that owns `_SAMPLED_LAWS`/`register_sampled_law`/`known_sampled_laws()`, control.py:456-484) and add a third call:

```python
register_sampled_law("pd_apogee", laws.pd_apogee)
```

`known_sampled_laws()` then returns `("proportional_drag", "pi_apogee", "pd_apogee")` (order per whatever the existing registration call order is) with no other change needed -- `sim.integrate.run_sim`'s eager-validation guard and `p.control.airbrake_model` dispatch both already go through this registry generically.

## SS153.6 Sign/saturation behavior

**`decision_required` -- clamp D separately, or let it flow through the combined clip?**

| Option | Behavior | Pros | Cons |
|---|---|---|---|
| **A -- combined clip only** (recommended for this first cut) | `unsat = kp*error + kd*d_error; cmd = clip(unsat, 0.0, 1.0)` -- same single-clip shape `pi_apogee` already uses for `kp*error + ki*integral` (laws.py:97-98) | Matches the existing two laws' structure exactly (one clip, no new knobs); simplest; a raw derivative-kick spike only matters if it is large enough AND sustained enough to visibly perturb `cmd` for more than one tick -- and `cmd` is recomputed fresh every tick from the CURRENT `error`/`d_error`, so a one-tick kick self-corrects by the next sample with no memory of it (unlike the integral term, which would carry a kick forward) | A sudden `error` jump right at the first active tick (entering `_in_coast_window`) produces one anomalously large/saturated `cmd` tick before settling -- cosmetic only given SS153.2 Option A already forces `d_error=0.0` on that exact first tick (`dt<=0.0`), so the classical "kick on window-entry" case is already zero by construction, not by a separate guard |
| **B -- separate pre-clip on the D term** (e.g. `d_term = clip(kd*d_error, -d_max, d_max)` before summing with P) | Bounds the D contribution independently of saturation headroom | Classic anti-kick technique in real PID implementations | Needs a new tunable (`d_max` or similar) with no obvious default and no existing convention in this codebase to borrow from; adds a knob nobody asked for yet; premature for a "first cut" per the task's own framing |

Recommendation: **Option A**. Reasoning given in the task itself already points this way: the window-gating (`_in_coast_window`, `apps/sim/engine/control.py`, referenced from `tests/test_controllers.py:81`/`174`) means `pd_apogee` is never called outside `[burnout, apogee]`, and SS153.2's first-tick `dt<=0.0` guard already zeroes `d_error` on the one tick where a step-change in `error` could otherwise appear (window entry). A real derivative-kick risk would need a second mechanism entirely (e.g. a discontinuous `target` change mid-coast), which this project has no such mechanism for today. Revisit only if a future ticket introduces mid-flight target changes.

## SS153.7 TDD brief for developer

New tests go in `tests/test_controllers.py`, matching the existing per-law test naming/shape (`test_proportional_drag_*`, `test_pi_apogee_*` at lines 218-296) -- add `test_pd_apogee_*` alongside them. At minimum:

1. **`test_pd_apogee_zero_kd_matches_proportional_drag`** -- with `airbrake_kd=0.0` and identical `kp`/target/measurement sequence, `pd_apogee`'s `cmd` output must equal `proportional_drag`'s own `cmd` output tick-for-tick (regression/consistency check -- same spirit as `test_proportional_drag_matches_proportional_structure_at_zero_k`, laws.py:232-246).
2. **`test_pd_apogee_derivative_term_changes_command_on_a_two_tick_sequence`** -- a two/three-tick sequence where `error` changes between ticks 1 and 2 (non-constant `h_baro`, so `d_error != 0.0` on tick 2); assert `cmd` at tick 2 differs from what `kp*error` alone (i.e. `kd=0.0`) would give, by `kd * d_error` (hand-computed, same style as the existing zero-k test's `expected` computation).
3. **`test_pd_apogee_first_tick_has_zero_derivative_contribution`** -- first call (`state=None`): `cmd == clip(kp*error, 0, 1)` exactly (no D contribution), confirming the SS153.2 Option A first-tick convention; also assert `state.error_prev` afterward equals the first tick's `error` (threaded forward correctly for tick 2).
4. **`test_pd_apogee_saturates_combined_pd_signal`** -- large `kp`/`kd` and/or large error/d_error driving `unsat` past `1.0` (or below `0.0`): assert `cmd` clips to `1.0`/`0.0` exactly (mirrors `test_pi_apogee_anti_windup_freezes_integral_while_saturated_in_the_same_direction`'s saturation setup, laws.py:273-296, minus the anti-windup part -- `pd_apogee` has no integral/anti-windup state to freeze, just confirm the clip itself fires).

**Closed-loop (`tests/test_harness.py`-level) case: not warranted for this first cut.** The existing Rung-1 oracle cross-check already exercises the registered-sampled-law dispatch path generically (`proportional_drag`/`pi_apogee` both go through it); `pd_apogee` reuses that exact dispatch/registration mechanism unchanged (SS153.5), so the closed-loop plumbing is not new risk here -- only the law's own arithmetic is new, which the four unit tests above cover directly and more cheaply. Add a harness-level case later only if/when `pd_apogee` becomes a user-facing default (not part of this ticket).

Full-suite regression (`python -m pytest -q`, backgrounded per this project's own ~220-400s full-run convention) is mandatory before closing the step -- confirm `proportional_drag`/`pi_apogee`'s existing pins are untouched and the new `pd_apogee` tests are green, per this project's hard `tdd` binding (no D-181 carve-out here, per the task's own framing -- this is `apps/` core, not fx27 consumption).

## SS153.8 Out of scope

- No changes to `estimator.py`, `_in_coast_window`, the actuator model, or any existing law's behavior.
- No new default `airbrake_model` value anywhere -- `pd_apogee` is opt-in exactly like `proportional_drag`/`pi_apogee` are today (nothing selects it unless a scenario's `Control.airbrake_model` is explicitly set to `"pd_apogee"`).
- No tuning/gain-selection guidance for real flight data -- `airbrake_kd`'s default `0.0` keeps it inert everywhere until a user opts in, same standing as `airbrake_ki`.
- No fx27-side consumption work (that would be a separate ticket under the D-181 carve-out, not this one).

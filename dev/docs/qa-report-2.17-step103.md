# QA report Phase 2.17 Step 103 (actuator model: rate/range/command-delay)

## Кратко (RU)

- Вердикт: PASS с замечаниями (pass-with-findings). Блокеров и major нет. 3 minor находки (ниже), все — пробелы в покрытии/документации, не баги поведения.
- Все 6 критериев приёмки тикета (аналитическая рампа на RK4-стадиях, клип f_min/f_max, delay_ticks=2, ideal-путь даёт голый float и не меняет legacy, неизвестная модель падает на входе в `run_sim`, длина вектора состояния =7) реально протестированы в `tests/test_actuator.py` и дополнении к `tests/test_sampling.py` — не просто заявлены, а код трассирован вручную и совпадает с ожидаемым поведением аналитически.
- Независимо перезапущены точечные тесты (91/91 passed) и полный прогон (668 passed, 0 failed, 47 warnings — все предсуществующие aero/Mach-предупреждения, не связаны с Step 103). Оба числа подтверждают отчёт разработчика.
- `sim/control.py`: диспетчер `_ACTUATOR_MODELS["ideal"]` = `_actuator_ideal`, возвращает `cmd` как есть — байт-в-байт эквивалентно поведению до Step 103; `configs/schema.py`/`_TEMPLATE_rocket.py`: `Rocket.actuator` корректно заведён в `assemble()`'s `Params(...)`, шаблон следует стилю секции `Control`.
- Minor-находки: (1) нет теста на `rate_close` (закрывающее направление рампы) — проверяется только значение по умолчанию, не поведение; (2) нет валидации отрицательного `delay_ticks`/`rate_*` (тихо принимается как 0/не ограничено) — не требуется тикетом, но стоит иметь в виду при проде; (3) `_TEMPLATE_rocket.py`'s `Control` section documents `airbrake_model` as `none | proportional` but the code (pre-existing, not part of Step 103) also registers `"full"` — doc gap outside this step's boundary, flagging for awareness only.

## Scope and method

Branch `feature/sim-paper-alignment` (not a worktree, worktree mode off for this project). Ticket: `dev/docs/architecture-35-paper-alignment.md` §35.6 (Step 103 entry) / §35.4.4 (sampled-data chain) / D-114 (actuator fidelity decision). Boundaries under review: `sim/control.py`, `sim/sampling.py`, `sim/params.py` (`Actuator` group), `sim/integrate.py` (guard only), plus the approved follow-up into `configs/schema.py` and `configs/rockets/_TEMPLATE_rocket.py`. Verifying independently against developer's claim of 91 targeted tests + 668/0 full suite — not trusting the report, re-derived each result below.

## 1. Test coverage against acceptance criteria

Read `tests/test_actuator.py` (new, 262 lines) and the diff to `tests/test_sampling.py` (+37 lines). Mapped each of the ticket's "Tests first" items:

| Acceptance criterion | Test | Verdict |
|---|---|---|
| Ramp `f_b(t) = rate_open*(t - t_0)` until saturation, evaluated at RK4 stage times | `test_full_actuator_ramps_linearly_at_rate_open_evaluated_at_rk4_stage_times` — 12 ticks, 4 fractional stage times each (0, 0.25, 0.5, 0.75 of `T_s`), compared against `min(2.0*t, 1.0)` | Covered. Traced the closed form by hand across ticks 0-2 (f_k accumulates correctly tick to tick via `_ramp(prev.f_k, prev.cmd_eff, dt, ...)`) — matches the test's expected values exactly. |
| `f_min`/`f_max` clip | `test_full_actuator_clips_to_f_min_f_max_even_though_the_raw_law_saturates_at_0_1` — `rate_open=inf`, `f_min=0.1`, `f_max=0.6`, checked at `t=t_k` (dt=0) and `t=t_k+0.01` | Covered, including the `dt=0` edge case (the `inf*0.0` NaN trap `_ramp`'s own docstring calls out). |
| `delay_ticks=2` delays the command by `2*T_s` | `test_full_actuator_delays_the_command_by_delay_ticks_sample_periods` — drives `sampling.sample` directly for 5 ticks, step command from `t=0`, asserts `cmd_effs == [0.0, 0.0, 1.0, 1.0, 1.0]` | Covered for the step-input case. Traced the FIFO logic (`_actuator_full`'s `queue`) by hand for a general (non-constant) command sequence too — confirms it is a genuine depth-`delay_ticks` delay, not an artifact of the constant-1.0 test input. |
| `actuator.model="ideal"` returns the float, `hold.values["airbrake"]` stays a float | `test_ideal_actuator_model_keeps_the_held_value_a_plain_float` — `type(v) is float`, legacy branch unaffected | Covered. |
| Unknown model raises at `run_sim` entry | `test_unknown_actuator_model_raises_valueerror_at_run_sim_entry` — `actuator_kw=dict(model="nope")`, `pytest.raises(ValueError)` around `run_sim` | Covered; also independently confirmed the guard's placement in `sim/integrate.py` (see §3 below) — it fires before any integration path is chosen, not deep in the RHS. |
| State vector length unchanged (7) | `test_state_vector_length_is_unchanged_by_the_actuator` — `len(State._fields) == 7` and `len(np.array(_launch_state())) == 7` | Covered. |
| Acceptance: `full`-law flight with `rate_open=inf` == legacy sampled flight bit-for-bit | `test_full_actuator_with_infinite_rates_reproduces_the_legacy_sampled_flight` — runs the same `proportional` airbrake scenario once under `actuator.model="ideal"` and once under `"full"` (rates left at the `inf` default), asserts `np.array_equal(r_ideal.y, r_full.y)` and `r_ideal.events == r_full.events` | Covered, and this is a real end-to-end `run_sim` comparison (not just a `_ramp` unit check), which is the right level for a "bit-for-bit" acceptance claim. |
| Channel contract: `prev` genuinely threads a non-scalar `AirbrakeHold` through the real airbrake channel (not just the pre-existing synthetic test double in `test_sampling.py`) | `test_channel_value_can_be_a_non_scalar_threaded_through_prev_the_airbrake_channel` (new, in `test_sampling.py`) | Covered. Confirms `sim/sampling.py` needed **zero** code changes — the channel contract was already generic (`f(t, y, p, prev) -> Any`), so Step 103 only had to prove the real channel exercises the existing contract. Verified by reading `sim/sampling.py`: no diff on that file at all, consistent with the "contract extended, float still valid" note in §35.4.6. |

No criterion from the ticket's "Tests first" list is assumed-but-untested. All are exercised at the right level (unit-level closed-form math for the ramp/clip/delay, and a real `run_sim` end-to-end comparison for the bit-identity acceptance claim).

### Coverage gaps found (not blocking, not in the ticket's explicit list)

- **No test exercises the closing direction (`rate_close`).** Every ramp test in `test_actuator.py` only drives an opening command (`0 -> 1`); `rate_close` is checked solely for its *default value* (`test_actuator_defaults_are_ideal_with_unbounded_rates_and_unit_range`, `math.isinf(a.rate_close)`), never for its *effect* on a closing ramp (command stepping down, e.g. `1 -> 0` with a finite `rate_close`). `_ramp`'s `lower = -rate_close * dt` branch is therefore never hit with a finite, non-default `rate_close` by any test in the suite. Minor — the closing-direction code path is structurally symmetric to the already-tested opening path, but it is untested as written.
- **No validation test for negative `delay_ticks`, negative `rate_open`/`rate_close`, or `f_min > f_max`.** `_actuator_full`'s delay logic treats any `delay_ticks <= 0` as "no delay" (silently accepts negative values as zero, not an error); `_ramp` would silently produce `upper < 0`/`lower > 0` for a negative rate, which combined with `np.clip(delta, lower, upper)` could raise `ValueError` from numpy if `lower > upper` (f_min/f_max swapped has the same risk, no test covers it). This is consistent with the project's SS7 "no input validation" convention (same gap pattern flagged for other config fields in the M1 QA report), so not a Step-103-specific regression — flagging for completeness, not as a new defect.

## 2. `sim/control.py` dispatch — ideal path cannot diverge from legacy

Read the full diff to `sim/control.py`. Confirmed:
- `sample_airbrake` now computes `cmd = _AIRBRAKE_CONTROLLERS[...](t, y, p)` (unchanged law call) then `return _ACTUATOR_MODELS[p.actuator.model](t, cmd, p, prev)`.
- `_ACTUATOR_MODELS = {"ideal": _actuator_ideal, "full": _actuator_full}`; `_actuator_ideal(t, cmd, p, prev) -> float` is a one-line `return cmd` — a bare float, with `t`/`p`/`prev` unused. Since `Actuator.model` defaults to `"ideal"`, every pre-existing scenario (`Params` built without ever mentioning `actuator=`) takes this branch and gets exactly the same float `sample_airbrake` returned pre-Step-103. No wrapping, no `AirbrakeHold`, no behavior change possible on the default path.
- `airbrake_deploy_fraction`'s legacy branch (`isinstance(v, AirbrakeHold)` false) still does `return v` unchanged for the ideal/float case — confirmed in the diff.
- Follow-up code-review fix verified present: `known_actuator_models()` (public accessor, `sim/control.py:376`) replaces what the report describes as a prior cross-module private-dict reach; `sim/integrate.py` calls this accessor, not `control._ACTUATOR_MODELS` directly (confirmed by grep — no `_ACTUATOR_MODELS` reference outside `control.py`).
- Follow-up comment fix verified present: `_actuator_full`'s docstring explicitly calls out `f_k = 0.0` as "the spec's own literal initial condition... deliberately NOT `a.f_min`" — present and matches D-114/§35.4.4's `f_0 = 0` note.

Traced `_ramp`'s `inf`-handling by hand: `upper = np.inf if math.isinf(rate_open) else rate_open * dt` avoids the `inf * 0.0 == nan` trap at a tick's first RK4 stage (`dt == 0`) — this is exactly what makes the `rate_open=rate_close=inf` default (even under `model="full"`) produce a true zero-order-hold discontinuity bit-identical to the `"ideal"` path, which is what the acceptance test (`test_full_actuator_with_infinite_rates_reproduces_the_legacy_sampled_flight`) exercises end-to-end. Confirmed consistent.

## 3. `sim/integrate.py` guard — fails fast at `run_sim` entry, not in the RHS

Read the diff and the surrounding function. The guard:

```python
if p.actuator.model not in control.known_actuator_models():
    raise ValueError(
        f"p.actuator.model={p.actuator.model!r} is not a registered "
        f"actuator model (known: {sorted(control.known_actuator_models())}) "
        "(architecture-35-paper-alignment.md SS35.6)."
    )
```

sits immediately after `run_sim` unpacks `p.solver.*` locals and before the `sample_rate_hz`/`method` compatibility check, well before `_run_rk4`/`solve_ivp` is ever called. Confirmed this fires unconditionally (even when `sample_rate_hz == 0.0`, i.e. the non-sampled path, where the actuator model is otherwise irrelevant) — a deliberately conservative fail-fast that is consistent with the ticket's "unknown law name raises at run_sim entry" wording (not scoped to "only in sampled mode" in the ticket text). The error message names the offending value and the known set, with a pointer to the spec section. No divergence between claim and implementation.

## 4. `configs/schema.py` + `_TEMPLATE_rocket.py` follow-up

- `Rocket.actuator: Actuator = dataclasses.field(default_factory=Actuator)` added alongside `control`, same bucket, confirmed by reading the dataclass.
- `assemble()`'s `Params(...)` call threads `actuator=sc.rocket.actuator` — confirmed inside the actual `Params(` constructor call (grepped the surrounding block to rule out a stray assignment outside it).
- The structural one-owner-invariant test (`tests/test_config_pieces.py`, SS31.8 #1, "two ways") needed **no changes** and passed — it is a generic structural check against `{f.name for f in dataclasses.fields(Params)}`, so the new `actuator` group is automatically covered. Verified by re-running it explicitly (see §5).
- Template doc section `### Actuator` added, following the `### Control` section's exact table format (`field | REQ/OPT | unit/choices | default | what it does`), with every field annotated `OPT` and an inline comment in the `ROCKET = Rocket(...)` literal noting "full model only" for the rate/range/delay fields and that the whole group is normally left at defaults. Matches style precedent.
- Minor, out-of-scope observation: the `### Control` section's `airbrake_model` row still only documents `none | proportional`, but `sim/control.py` has registered a third `"full"` airbrake law for some time already (unrelated to Step 103's diff — `_AIRBRAKE_CONTROLLERS["full"]` predates this change, confirmed no diff touches that dict). Not a Step 103 regression; flagging since it was visible while reading the same table.

## 5. Independent test execution

- Targeted re-run (exact files from the dev report): `python -m pytest -q tests/test_actuator.py tests/test_control.py tests/test_sampling.py tests/test_config_pieces.py tests/test_template_docs.py tests/test_config_registries.py` → **91 passed** in 19.48s. Matches the developer's claim exactly.
- Full suite re-run (`python -m pytest -q`, backgrounded, polled under the 240s-per-call cap): **668 passed, 0 failed, 47 warnings** in 550.96s (~9m11s). Matches the developer's claim exactly. All 47 warnings are pre-existing `AeroRangeWarning`/`MachRangeWarning` diagnostics from unrelated aero/scenario-sweep tests (table out-of-range alpha, Mach-independent aero model above Mach 0.8) — none reference the actuator, sampling, control, or config-schema modules touched by this step.
- No numeric pins touched by this diff: `sim/sampling.py` has zero line changes, and the "ideal" default path through `sim/control.py` is provably unchanged (see §2) — consistent with the ticket's "pin impact: none" claim, and the full-suite green run is the direct evidence.

## Overall verdict

**Pass-with-findings.** No blocker, no major. Three minor findings, all either coverage gaps (rate_close untested; no negative-input validation tests) or a pre-existing, out-of-scope documentation gap (Control's airbrake_model table). None affect the acceptance criteria, which are all met and independently verified against the code (not just the test assertions) by hand-tracing the closed-form math and the FIFO delay logic.

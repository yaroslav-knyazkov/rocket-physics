# Airbrake controller — fidelity-ladder reconciliation against existing code (2026-11-04)

## Кратко (RU)

- Документ сверяет план контроллера аэротормоза (`airbrake-controller-plan.md`, ступени 0-8)
  с уже существующим кодом Phase 2.17 (`apps/control/flight_software/`), который был
  построен раньше и независимо от этого планирования.
- Вывод: ступень 1 (Tier 1, P/PI на предсказанном апогее) — сделана и покрыта тестами;
  ступень 2 (ограничение скорости актуатора) — код есть, но не подтверждено его включение
  в рабочий сценарий с законами управления; ступень 3 (оценщик по шуму) — частично: есть
  alpha-beta фильтр по одному датчику (баро), но его коэффициент `estimator_beta` помечен
  как непроверенная заглушка, и фьюжн акселерометра отсутствует.
  Ступень 4 (Mach-зависимый `k`) не начата.
- Рекомендуемый следующий шаг — НЕ полный Kalman-фильтр и не Rung 4 Mach-таблица, а узкая,
  тестируемая задача: написать скрипт прогона замкнутого контура (laws.py + estimator.py +
  rate limiter, уже существующие части) на существующем сценарии, который до сих пор нигде
  не инстанцирован вместе, и через него (а) подтвердить/протестировать wiring ступени 2,
  (б) дать практическую основу для тюнинга `estimator_beta` через локальную линеаризацию +
  Monte Carlo по `apps/analysis/ensemble`, без "chirp".
- Полноценный многодатчиковый Kalman-фильтр (ступень 3+) и Mach-зависимый `k` (ступень 4) —
  это следующие шаги ПОСЛЕ, не сейчас: сначала нужно знать, достаточно ли текущего
  alpha-beta фильтра эмпирически, а это можно узнать только через прогон на сценарии.

---

## Table of contents

- [S1. Scope and method](#s1-scope-and-method)
- [S2. Per-rung status](#s2-per-rung-status)
- [S3. Next concrete coding step](#s3-next-concrete-coding-step)
- [S4. Step breakdown](#s4-step-breakdown)
- [S5. Rejected alternatives for the next step](#s5-rejected-alternatives)

## S1. Scope and method

This note reconciles `projects/fx27/docs/airbrake-controller-plan.md` (rungs 0-8, Tier
1/2/3 taxonomy) against code that already exists under this project's own main
Phase 2.17 ("paper-alignment") stage, built for reasons unrelated to this week's
controller-planning conversation. It does **not** re-litigate the Tier 1/2/3 taxonomy
and does **not** propose starting Rung 1/2 from scratch — both are explicitly out of
scope per the brief.

Sources read in full: `airbrake-controller-plan.md`,
`vehicle-dynamics-roadmap.md` (both `projects/fx27/docs/`),
`dev/docs/architecture-35-paper-alignment.md` SS35.4.4 (L237-323) and its Step
107/108 tickets (L433-446) and D-114/D-115 decisions (L536-537), the tracker's
own closed-step log for Step 107/108/109 (`dev/status-archive.json`,
`stage_subkeys.2.17.steps_done[29..37]`), `apps/control/flight_software/laws.py`,
`apps/control/flight_software/estimator.py`, the `Control`/`Sensors`/`Actuator`
dataclasses in `apps/sim/engine/params.py` (L201-279), and `tests/test_controllers.py`
(test names + two bodies read in full: `test_full_traceability_comparison_table`
L395-435, `test_proportional_drag_and_pi_apogee_run_with_alpha_beta_estimator`
L185-208).

One naming trap worth flagging up front: the tracker's **Step 109** is *not* the
architecture-35 ticket that was originally numbered 109 ("closed-loop harness and
metrics", `apps/airbrake_control/{harness.py,metrics.py}`). That harness ticket was
never built under any name — grep confirms no `airbrake_control`, `harness.py`, or
`metrics.py` exists anywhere in `apps/` or `projects/`. The step number 109 was later
reused by an unrelated roll/reaction-wheel ticket (`task-109-roll-reaction-wheel.md`,
D-131). Separately, "Step 143 (standalone estimator, Option A)" that shows up in the
tracker is **also unrelated** — per D-169/D-171/D-173 it is a different, cruder
closed-form point-mass flight-path-angle diagnostic estimator (`apps/analysis/
point_mass/`, still gated/not started), not the Kalman/alpha-beta state estimator this
note is about. Neither of these two "Step 109"/"Step 143" tracker hits should be
mistaken for closed-loop-controller work.

## S2. Per-rung status

### Rung 0 (static sizing) — status per the plan doc itself, not re-verified here
Out of scope for this note (plan doc already says done for cspace, pending for euroc).

### Rung 1 (Tier 1 predictive P/PD on apogee-prediction error) — **DONE**

- `apps/control/flight_software/laws.py::drag_aware_predicted_apogee(h, v, g, m, k)` is
  exactly the closed-form drag-only ballistic-coast predictor Rung 1 specifies, with
  `k = 0.5*rho_hat*(onboard_CdA0 + onboard_CdA_brake*f_b)` linear in `f_b` — matches the
  plan's plant assumption exactly (confirmed by direct read of the docstring and body,
  laws.py L16-55).
- Two registered sampled laws consume it: `proportional_drag` (P) and `pi_apogee` (PI
  with conditional-clamping anti-windup), laws.py L70-104.
- Tested by 19 cases in `tests/test_controllers.py` including an oracle
  (`test_drag_aware_predictor_matches_numerically_integrated_constant_k_coast`), a
  vacuum-limit continuity check, and an end-to-end comparison on the actual demo flight
  (`test_full_traceability_comparison_table`, L395-435): apogee `none`=666.5 m (no
  brake) > `full`=303.5 m (legacy memoryless) > `proportional_drag`=513.2 m >
  `pi_apogee`=490.9 m (vs. target 500 m — PI's integral action measurably cuts the P
  law's steady-state error, 9.1 m vs 13.2 m).
- Built under Phase 2.17 Step 107 (commit `74cab7e`), QA Step 107 (commit `d099cf8`):
  PASS, no defects, independently re-verified against a clean 743-test collection
  count.
- **Nothing left to build at Rung 1.** The plan's own §1.4 correction already says
  this; this note confirms it by direct code/test read, not by trusting the plan doc.

### Rung 2 (rate-limited + position-feedback actuator) — **PARTIALLY DONE: wiring gap**

- The actuator model exists and is real: `apps/sim/engine/params.py`'s `Actuator`
  dataclass (L256-278) — `model: "ideal"|"full"`, `rate_open`/`rate_close`
  (fraction/s), `f_min`/`f_max`, `delay_ticks` — with `sim/control.py`'s
  `AirbrakeHold`/`_ramp` implementing the closed-form rate-limited ramp-toward-command
  (Step 103, commit `6390c1d`, QA-passed `f17a88a`).
- **Gap, concretely:** no test or script anywhere exercises `Actuator(model="full",
  rate_open=..., rate_close=...)` *together with* `proportional_drag`/`pi_apogee`. Grep
  of `tests/test_controllers.py` confirms `test_full_traceability_comparison_table`'s
  `proportional_drag`/`pi_apogee` rows use the default `Actuator()` (`model="ideal"`,
  i.e. zero-order hold, no rate limit) — the row literally labelled `"full"` in that
  test is the *legacy memoryless `airbrake_model="full"`* controller, an unrelated
  reuse of the word "full" (it means "full-brake-always-open" airbrake law, not
  "Actuator.model='full'"). Actuator rate-limiting itself is tested only in isolation
  (`tests/test_actuator.py`, against the legacy `none`/`proportional` laws, not
  against the Tier-1 sampled laws).
- **This is Rung 2's actual remaining gap**, not new actuator physics: the two pieces
  exist, nobody has run them together.

### Rung 3 (noisy sensors + baro-inertial estimator) — **PARTIALLY DONE: two gaps**

- `apps/sim/engine/params.py`'s `Sensors` dataclass (L240-252): baro pressure-altitude
  channel with Gaussian noise (`baro_sigma_m`), first-order lag (`baro_tau_s`), and
  quantisation (`baro_resolution_m`), all inert at defaults (Step 108, commit
  `79887dd`, QA-passed `dc1a6bf`).
- `apps/control/flight_software/estimator.py::_step_alpha_beta` — a real
  constant-velocity alpha-beta (Kalata g-h) filter: predict `h_pred = h_hat +
  v_hat*dt`, correct both states from the residual, with a documented `dt<=0` guard
  (estimator.py L41-61). Both `proportional_drag` and `pi_apogee` already thread
  `estimator.step(...)`'s output through regardless of which model is selected
  (laws.py L73, L93) — the estimator-swap seam the plan's §2.5 calls for already
  exists structurally.
- **Gap 1 (named by the code itself, not a new finding):**
  `apps/sim/engine/params.py` L236: `estimator_beta: float = 0.1667  # ... UNVERIFIED
  placeholder, see §108.8.3` — the filter's own velocity gain has never been tuned or
  validated against anything, just picked as a plausible number.
- **Gap 2 (single-sensor only):** the estimator fuses baro altitude alone. No
  accelerometer/IMU channel exists in `Sensors`, and `estimator.step`'s signature
  (`t, h_baro, prev, *, model, p`) has no second measurement input — this is not "a
  Kalman filter with one sensor disabled", it is structurally single-input (two states,
  one measurement equation). A real multi-sensor fusion (baro + accelerometer) is not
  a parameter change, it is new code (new `Measurement` field, new estimator model,
  likely a proper 2-state KF with a measurement model per sensor rather than the
  hand-tuned alpha-beta recursion).
- **Gap 3 (integration-level, same root cause as Rung 2's gap):** the only test that
  runs a sampled law under `estimator_model="alpha_beta"`
  (`test_proportional_drag_and_pi_apogee_run_with_alpha_beta_estimator`, L185-208)
  calls `laws.proportional_drag`/`laws.pi_apogee` directly with three hand-fed
  `(t, h_baro)` pairs — it is a unit smoke test of the law/estimator wiring, not a
  `run_sim` flight with the `Sensors` noise/lag pipeline actually turned on. No test
  anywhere runs a full flight with noisy `Sensors` **and** `estimator_model=
  "alpha_beta"` **and** a Tier-1 law **and** `Actuator(model="full")` all active at
  once — i.e. Rung 2's and Rung 3's wiring gaps are really the same gap, reachable
  from one next step.
- **Net: Rung 3 is "most of the way there" for the plant/estimator-architecture
  choice (alpha-beta, not yet multi-sensor), but not closed** — both because the one
  live gain is unverified and because the pieces have never been run together end to
  end.

### Rung 4 (`Cd(extension, Mach)`) — **NOT STARTED**

- `laws.py::_k` (L48-55) computes `k = 0.5*onboard_rho0*(onboard_CdA0 +
  onboard_CdA_brake*f_b)` — `onboard_CdA_brake` is a flat scalar, no Mach dependence
  anywhere in `Control`'s onboard-model fields (params.py L223-226) or in `_k`'s body.
  `onboard_rho0` is also a flat nominal constant (`1.225`, ISA sea level), not even
  `rho`-at-`h_hat` yet, let alone Mach-at-`h_hat`/`v_hat`.
- Extending to Mach-dependent `k` is a small, bounded change *to this module alone*
  (replace the scalar `onboard_CdA_brake` lookup with a `Cd(M)` curve/table sampled at
  an onboard Mach estimate derived from `v_hat` and `rho_hat`/ISA-at-`h_hat`) — it does
  **not** require new simulator machinery, since the plant side (`apps/sim/engine/
  aero.py`'s "table" model) is already Mach-aware; this is purely an onboard-model
  change in `apps/control/flight_software/laws.py`+`estimator.py`, same shape as the
  existing scalar `_k`.
- Not started; reasonably deferred until Rung 2/3's wiring gap closes, since there is
  currently no harness to even observe Rung 4's effect in.

**Stopping here per the brief** (rungs 5+ depend on attitude dynamics / CFD data not
yet relevant to this reconciliation, and are already covered by the plan doc's own
§0 cross-reference to `apps/sim/engine`'s existing rigid-body dynamics).

## S3. Next concrete coding step

**Recommendation: build the missing closed-loop integration harness/demo scenario
first — not a Kalman filter, not Rung 4's Mach table.**

Point-by-point against the brief's four sub-questions:

**(a) Tuning `estimator_beta` now — not yet, and not directly.** Tuning a gain against
nothing is circular: there is currently no scripted scenario that runs the alpha-beta
estimator against a *noisy* flight (every existing test either feeds it three
hand-picked numbers or runs it under `Sensors()` defaults, i.e. noiseless). The plan's
own §2.5 "no chirp" answer (local linearization at trim points + Monte Carlo sim-sweep
via `apps/analysis/ensemble`) is the right method, but both techniques need a scripted
closed-loop run to sweep *over* — that harness does not exist yet. Building the
harness is therefore the actual prerequisite for the tuning work the user already
discussed, not a parallel task.

**(b) Multi-sensor KF vs. the existing single-sensor alpha-beta filter — defer the
decision, it is premature.** Nothing in the codebase today exercises the alpha-beta
filter under real sensor noise end-to-end, so there is no empirical basis yet to say
whether it is "good enough" for Rung 3 or not. Per the plan's own §2.5 methodology
(step 6: down-select empirically, not by table lookup), that empirical answer is
exactly what the harness from (a)/(c) produces as a side effect (apogee-error RMS and
bias under the alpha-beta filter, at a range of noise levels) — building a multi-sensor
KF before that evidence exists would be speculative work against an unmeasured gap.

**(c) The actuator rate-limit wiring is itself the gap — confirmed, not assumed.**
Per S2's Rung 2 analysis, no code path combines `Actuator(model="full")` with
`proportional_drag`/`pi_apogee`. This is the same wiring gap as Rung 3's estimator
integration gap (S2, Gap 3) — one scenario closes both.

**(d) Rung 4 is a small extension once the harness exists, not before.** Per S2's
Rung 4 analysis, it is bounded to `laws.py`/`estimator.py` — but there is no reason to
build it before there is a way to run and observe it.

**Conclusion:** the single most useful next step is a scripted closed-loop
demo/scenario (a new, committed runnable script + its own test, in the project's usual
TDD style) that, for the first time, runs one flight with **all four** existing pieces
active simultaneously: a Tier-1 law (`proportional_drag` or `pi_apogee`), the
alpha-beta estimator (`estimator_model="alpha_beta"`), noisy/lagged `Sensors`
(`baro_sigma_m`/`baro_tau_s`/`baro_resolution_m` nonzero), and the rate-limited
actuator (`Actuator(model="full")`). This single step directly closes Rung 2's and
Rung 3's wiring gaps, and is the load-bearing prerequisite both (a)'s tuning
methodology and (b)'s KF-vs-alpha-beta empirical question need before either can be
answered with evidence instead of guesswork.

## S4. Step breakdown

Per `python .claude/scripts/status_query.py current`/`roadmap`: the project's step
numbering is sequential across phases regardless of which phase a step is filed under
(e.g. Steps 136/137 are Phase 2.17 while Steps 144/145 are Phase 2.21/2.22, interleaved
by calendar order, not by phase). The highest step number issued so far is **145**
(Phase 2.22, closed 2026-11-03). The next free number is **146**. This work is a
continuation of Phase 2.17's own Milestone M3 (laws/estimator/actuator, Steps
103/107/108) — recommend filing it there as **Step 146 (Phase 2.17)**, not opening a
new phase, since it adds no new stack/architecture decision, only an integration
harness over already-approved pieces.

### Step 146 (Phase 2.17) — closed-loop airbrake controller demo/harness

- **Goal:** close Rung 2/3's wiring gap (S2/S3 above); produce the first scripted,
  committed, repeatable flight that exercises `proportional_drag`/`pi_apogee` +
  `estimator_model="alpha_beta"` + noisy `Sensors` + `Actuator(model="full")` together.
- **Boundaries:** one new module (suggested: `projects/fx27/point/airbrake_control.py`
  or an `apps/`-level `apps/control/flight_software/harness.py` if the team wants it
  reusable beyond fx27 — **architect note, not yet decided: file under `projects/
  fx27/` if fx27-specific framing stays, or under `apps/` if intended as a
  library-level reusable harness; flag this choice to the user/architect at ticket
  time, do not assume**), a thin runnable script, and its test file. No changes to
  `apps/sim/engine/`, `apps/control/flight_software/laws.py`, or `estimator.py` — this
  step is pure integration, not new physics.
- **Tests first (TDD):** (1) a scripted flight with all four pieces active completes
  without error and produces a finite apogee; (2) with `Sensors()` all-zero (noiseless)
  the result is close to the existing `test_full_traceability_comparison_table`
  numbers for the same law (sanity cross-check against Step 107's own oracle); (3) with
  `Actuator(model="full", rate_open=..., rate_close=...)` set to a deliberately tight
  rate, the brake visibly lags the commanded fraction (a real saturation/rate-limit
  regression test, not just "it runs"); (4) metrics captured per run: apogee error vs.
  `airbrake_target_apogee_m`, time-at-saturation fraction, actuator travel — reusing
  the metric shapes architecture-35 §35.4.4/Step 109(orig)/Step 105's `EnsembleResult`
  already establish, not inventing a new metrics vocabulary.
- **Acceptance:** one documented, reproducible comparison table (gain, noise level,
  actuator rate -> apogee error, saturation fraction) on the existing demo flight,
  committed as a test fixture or a small `output/`-style artifact; this is the
  dataset Step 147 (tuning `estimator_beta` via `apps/analysis/ensemble`, per S3(a))
  and the later Tier-2 promotion decision both read from.
- **depends_on:** none (all consumed pieces — laws, estimator, sensors, actuator — are
  already landed and tested). **parallel_safe:** true as a standalone ticket, but note
  it is the sole input to the (not-yet-ticketed) Step 147 tuning step, so sequence
  147 after it, not in parallel.
- **Explicitly NOT in this step's scope:** tuning `estimator_beta`'s actual value (that
  is Step 147, consumes this step's harness); building a multi-sensor KF (S3(b), no
  evidence yet that it's needed); Rung 4's Mach-dependent `k` (S2, small but premature
  before this harness exists).

## S5. Rejected alternatives for the next step

- **Start with a multi-sensor Kalman filter.** Rejected per S3(b): no measured gap yet
  that the existing single-sensor alpha-beta filter fails to close; would be
  speculative work against an unmeasured deficiency, and a strictly bigger lift
  (new sensor model, new measurement-model machinery) than the harness.
- **Tune `estimator_beta` directly by hand/guess.** Rejected: contradicts the plan
  doc's own §2.5 methodology (no chirp available for this loop) and there is currently
  nothing to tune it *against* (no scripted noisy-flight scenario exists).
- **Build Rung 4 (Mach-dependent `k`) next, since it's "small".** Rejected: per S2,
  it is indeed a small change, but there is no harness yet to observe its effect in,
  so building it now would not be verifiable beyond unit-level numeric checks — low
  value until Step 146 exists.
- **Re-implement architecture-35's originally-numbered Step 109 (`apps/
  airbrake_control/{harness.py,metrics.py}`) verbatim.** Considered and substantially
  adopted in spirit (S4's Step 146 is functionally that ticket), but not resurrected
  under its old number/old paths verbatim, since the project's directory layout has
  moved twice since that ticket was written (`sim/`→`apps/sim/engine/`, `controllers/`
  →`apps/control/flight_software/`, Phase 2.19) and the fx27-vs-library-level
  filing question (S4's boundaries note) did not exist when architecture-35 was
  written.

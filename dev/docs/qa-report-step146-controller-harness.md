# QA Report — Step 146 (Phase 2.17): Controller integration harness

## Кратко (RU)

Вердикт: **PASS**, без дефектов (полное резюме — в секции «Кратко (RU)» внизу документа).

## Scope

- Reviewed diff: only `apps/control/flight_software/harness.py` (new) and `tests/test_harness.py` (new, 7 tests) are untracked/changed per `git status --porcelain`.
- Confirmed no modifications to any tracked file.

## Boundaries check (diff-level, not just developer's claim)

- `git status --porcelain` shows exactly two untracked entries (`apps/control/flight_software/harness.py`, `tests/test_harness.py`); no `M` (modified) entries anywhere. Confirms no edits to `apps/sim/engine/`, `laws.py`, or `estimator.py`.
- `apps/sim/engine/params.py` line 236: `estimator_beta: float = 0.1667  # alpha_beta only: ... UNVERIFIED placeholder` — unchanged, untouched by this step, as required.
- No dead-code markers (`TODO`/`FIXME`/`NotImplementedError`) left in `harness.py`.

**Verdict: PASS.** Boundary holds exactly as specified.

## Code-review fixes — independently verified present in current file state

1. **Saturation-metric window restricted to `[burnout, apogee]`.** Confirmed: `_active_window` (harness.py:171-181) reads `result.events["burnout"]`/`["apogee"]`; `_metrics` (harness.py:184-206) filters `actuator_f` to that window before computing `saturation_fraction`/`travel`, returning `nan` when no window exists. Matches `apps/sim/engine/control.py::_in_coast_window` semantics (thrust==0 and vz<0, i.e. unpowered pre-apogee) that gates when a registered sampled law is actually called (control.py:514-532) — so the metric's window choice is consistent with when the actuator is ever actively commanded.
2. **`"ideal"` actuator docstring correction.** Confirmed: `HarnessResult` docstring (harness.py:88-93) states the `actuator_saturation_fraction` metric under `model == "ideal"` reflects the registered law's own `np.clip(..., 0.0, 1.0)` output sitting at a rail, not a real actuator limit. Independently verified against `apps/control/flight_software/laws.py:77,98` (`cmd = float(np.clip(..., 0.0, 1.0))` in both `proportional_drag`/`pi_apogee`) and `apps/sim/engine/control.py::_actuator_ideal` (returns `cmd` unmodified, no further clip) — docstring claim is accurate.
3. **Curved-gravity fix via `gravity.altitude_agl`.** Confirmed: `_metrics` (harness.py:186-188) calls `gravity.altitude_agl(result.raw.sol(apogee_t), p)`, not a raw `-sol()[Z]` lookup. Cross-checked `apps/sim/engine/gravity.py:269-281`: `altitude_agl` is documented as `-ground_depth(...)`, correct under every `p.gravity.direction`, and reduces to `-y[Z]` only under the default `"parallel"` — so the fix is real (matters once/if a non-parallel gravity direction scenario is run through this harness) and correctly wired.
4. **Off-by-one tick edge case at `t_max`.** Confirmed present: `_replay_actuator_trajectory` (harness.py:142-159) has the explicit guard decrementing `n_ticks` when the flight ran exactly to `p.solver.t_max` and that is an exact multiple of `T_s`. Honestly self-documented as "not reachable by any scenario in this ticket's own tests" — correct per inspection of `test_harness.py`: every scenario terminates via a ground/apogee event, never by hitting the solver's `t_max` wall exactly on a tick boundary. No test exercises this guard directly, but the logic is sound by inspection and the gap is honestly disclosed, not hidden.
5. **Dead/unreachable guards removed.** No stale markers or obviously-dead branches found by inspection of the current file.

**Verdict: PASS.** All five claimed fixes are present and independently verified correct.

## Test coverage vs. S4 tests-first list (4 required scenarios)

Ran `tests/test_harness.py` standalone (`python -m pytest tests/test_harness.py -v`): **7 passed, 0 failed, 148.45s**.

1. **All-four-pieces-active, completes, finite apogee** — `test_closed_loop_with_all_four_pieces_active_completes_and_reports_finite_apogee` (parametrized over both registered laws = 2 of the 7 tests). Uses non-zero `baro_sigma_m/baro_tau_s/baro_resolution_m` AND a finite `rate_open/rate_close` AND `estimator_model="alpha_beta"` simultaneously — genuinely exercises all four pieces together, not a subset. PASS.
2. **Noiseless cross-check against Step 107's oracle** — `test_closed_loop_matches_step107_oracle_under_noiseless_sensors` (parametrized, 2 of 7). Independently re-ran `tests/test_controllers.py::test_full_traceability_comparison_table -s` myself and confirmed the printed oracle values the test's own comment cites are exact: `proportional_drag -> 513.165`, `pi_apogee -> 490.870` (abs tolerance in the harness test is 15.0 m, loose enough to tolerate the estimator-model swap `stub`->`alpha_beta` the test's own docstring explains is the one deliberate variable, tight enough to catch a real wiring bug). PASS, and the oracle numbers are not fabricated.
3. **Tight actuator rate produces visible lag** — `test_tight_actuator_rate_lags_behind_a_fast_actuator_on_the_same_flight`. Uses an engineered always-saturating command (`kp=1.0, target=0.0`) to force a clean step input, then asserts (a) the fast actuator reaches `f_max=1.0`, the tight one does not, (b) pointwise up to the earlier of the two runs' apogee times the fast trajectory is never behind the tight one and is strictly ahead somewhere. This is a real, deterministic rate-limit regression check, not a smoke test — the assertions would fail if the rate limiting were wired incorrectly or not applied at all. PASS.
4. **Metrics dict shape** — `test_metrics_dict_has_the_four_documented_keys_in_the_ensemble_evaluate_shape`. Confirms exact key set, `float`-typed values, and internal consistency (`apogee_error_m == apogee_m - target`). Cross-checked `apps/analysis/ensemble/ensemble.py` — `evaluate(config) -> dict[str, float]` is indeed the established convention there (`_safe_evaluate`'s own type signature, ensemble.py:271/291). PASS.

Plus one acceptance-table test (`test_comparison_table_across_gain_noise_and_actuator_rate_is_reproducible`) covering S4's acceptance bullet directly: gain x noise x actuator-rate -> apogee error/saturation/travel, printed in the same style as the existing `test_full_traceability_comparison_table` precedent, plus a bit-for-bit reproducibility check on a fixed-seed noisy run. PASS.

**Verdict: PASS.** All 4 required scenarios genuinely present and testing what they claim; test count (7) matches developer's report exactly.

## Risk assessment — developer-flagged caveats

**Risk 1 — `actuator_saturation_fraction` under `model="ideal"` reflects the law's own clip, not a real actuator rail.**
Docstring (harness.py:88-93) states this explicitly, naming both the mechanism (`np.clip(..., 0.0, 1.0)` in the registered law) and the consequence (not a real rate/range limit, which "ideal" has none of). Verified accurate against `laws.py`/`control.py` (see fix #2 above). The sentence is dense but unambiguous on a careful read. **Assessment: acceptable as a documented caveat, no defect.** Minor suggestion (non-blocking): a one-line summary sentence at the very top of that bullet (e.g. "Caveat: under `model=\"ideal\"` this metric does NOT measure actuator saturation.") would make the caveat skimmable for a reader who doesn't read the full paragraph — cosmetic, not required for acceptance.

**Risk 2 — `_replay_actuator_trajectory` reconstructs actuator position post-hoc by replaying `sampling.sample` deterministically off the dense trajectory, rather than capturing hold-history live during `run_sim`.**
This is architecturally sound today (verified the RNG keying claim: `apps/sim/engine/sensors.py`'s `measure` uses `np.random.default_rng([seed, k])` seeded only by `(baro_seed, tick index)` — no wall-clock/call-order dependence), and is explicitly, honestly documented as fragile to a FUTURE change in `apps/sim/engine/`'s determinism contract. Given:
- this step is explicitly scoped (S4 boundaries) to touch nothing under `apps/sim/engine/`, so building a stronger guard (e.g. actually threading hold-history out of `run_sim`) would itself require an engine-level change, which is out of scope here and would re-open the "pure integration" boundary this step is specifically trying to keep closed;
- the reproducibility test (`test_comparison_table_across_gain_noise_and_actuator_rate_is_reproducible`'s bit-for-bit check) already provides a regression tripwire for the common failure mode (RNG determinism breaking) — if a future engine change broke the determinism contract, bit-for-bit reproducibility would fail loudly in this exact test, even though it wouldn't catch every conceivable form of drift between the replay and the original run.

**Assessment: acceptable as a documented caveat for this step.** It is not a defect against Step 146's own scope. Recommendation (not a blocker, for the orchestrator/backlog, not a QA defect against this step): file a backlog item to track that any future change to `apps/sim/engine/`'s sampling/RNG determinism contract must re-verify this module's replay fidelity — a cross-module coupling that is currently undetected by any test *outside* `test_harness.py` itself.

## Full suite re-run

Ran `python -m pytest -q` independently (background, full repo, not trusting developer's number).

**Result: 885 passed, 0 failed, 101 warnings, 995.67s (0:16:35).**

- Matches developer's reported count exactly (885 passed / 0 failed).
- Warnings are all pre-existing, expected `MachRangeWarning`/`AeroRangeWarning` instances from unrelated tests exercising out-of-table Mach/alpha ranges on purpose (house convention per other test files) — none originate from `harness.py` or `test_harness.py`.
- Runtime (995.67s) is on the high end of this project's previously observed range (~220-800s typical, one outlier at 765s per `CLAUDE.md`'s own ledger) — noting as an observation, not a regression tied to this step: `tests/test_harness.py` itself only accounts for ~148s of the total, and the suite otherwise completed cleanly. No action needed, but worth a line in the project's environment-trap ledger if this recurs (runtime creeping upward run over run).
- Also independently re-ran `tests/test_harness.py` standalone first (per task instructions): 7/7 passed in 148.45s, see above.

## Overall verdict

**PASS.** All required test coverage (4 S4 tests-first scenarios + 1 acceptance table) is genuinely present and correctly exercises the four integrated pieces; both code-review-claimed fixes and the developer's reported test/suite counts are independently verified, not just trusted; the `apps/sim/engine/`/`laws.py`/`estimator.py`/`estimator_beta` boundary holds exactly; both developer-flagged risks are acceptable, adequately documented caveats for this step's explicit scope, not defects.

No defects filed. One non-blocking recommendation for the orchestrator/backlog: track that a future change to `apps/sim/engine/`'s sampling/RNG determinism contract should trigger a re-check of `harness.py::_replay_actuator_trajectory`'s fidelity (currently only guarded indirectly, via `test_harness.py`'s own bit-for-bit reproducibility assertion, not a direct contract test). Cosmetic-only suggestion on the `"ideal"`-mode docstring caveat (lead with a one-line summary) — not required for acceptance.

## Кратко (RU)

Вердикт: **PASS**, без дефектов. Проверены оба новых файла (`apps/control/flight_software/harness.py`, `tests/test_harness.py`, 7 тестов) — все 4 обязательных сценария из S4 tests-first реально тестируют то, что заявлено (совместная работа закона управления, alpha-beta фильтра, шумного/квантованного баро и ограниченного по скорости актуатора), а не являются smoke-тестами. Независимо перепроверены все 5 заявленных code-review фиксов (окно насыщения `[burnout, apogee]`, докстринг про `"ideal"`, `gravity.altitude_agl` вместо `-sol()[Z]`, off-by-one на `t_max`, чистка мёртвого кода) — присутствуют и корректны. Границы шага (`apps/sim/engine/`, `laws.py`, `estimator.py`, `estimator_beta`) не тронуты — подтверждено по `git status`, не только со слов разработчика. Полный прогон тестов независимо повторён: **885 passed, 0 failed** — совпадает с отчётом разработчика. Оба риска, которые разработчик сам обозначил (метрика насыщения под `"ideal"`; пост-хок реплей актуатора вместо захвата истории в реальном времени), признаны приемлемыми документированными допущениями для этого шага, не дефектами — с одной некритичной рекомендацией в backlog на будущее.

## Status: COMPLETE

# QA Report — Phase 2.17, Step 107 (sampled laws registry + drag-aware predictor law)

## Кратко (RU)

- Проверка Step 107 (commit `74cab7e`, ветка `feature/sim-paper-alignment`) — все проверки прошли, вердикт **PASS**.
- Реальный полный прогон тестов (дождались настоящего кода возврата, не wrapper-плейсхолдера): **743 passed, 0 failed**, 729.69 с.
- Расхождение "742 заявлено разработчиком vs 743 факт" — это **необъявленная ошибка off-by-one в самоотчёте разработчика**, не регрессия. Обе гипотезы из брифа неверны: сборка тестов (`--collect-only`) уже даёт 743, а "тест 22 как скрипт, не pytest-функция" опровергается прямым чтением кода — `test_full_traceability_comparison_table` реально существует как `def test_...`. Арифметика 721 (базa) + 9 (test_control.py, 8 по плану + 1 доп. регрессионный тест на ValueError-фикс) + 13 (test_controllers.py, все 13 пунктов плана включая опциональный 22-й) = 743 — сходится и со сборкой, и с реальным прогоном. Та же дисциплина трекинга, что поймала 720-vs-721 в Step 104 QA — здесь фиксируется для записи, блокером не является.
- Все 5 grep-проверок §107.9 перепрогнаны с нуля — чисто, коллизий нет; diff `sim/control.py` (4 хунка) подтверждает: легаси-функции (`_proportional_airbrake`/`_full_airbrake`/`_no_airbrake`/`AirbrakeHold`/`_ramp`/`_actuator_ideal`/`_actuator_full`) буквально не задеты ни одним хунком.
- ValueError-фикс в `airbrake_deploy_fraction` — аддитивен по построению (доказуемо никогда не срабатывает для существующих вызовов), регрессионный тест реально его дёргает.
- Два незафикшенных review-finding (`p.g0` вместо `gravity.g(t,y,p)`, повторный расчёт `dt` в `pi_apogee`) — подтверждено побайтово: это буквальный код из самого тикета (§107.5), не отклонение разработчика.
- Сравнительная таблица (`none/full/proportional/proportional_drag/pi_apogee`) и свойство "интегральное действие снижает статическую ошибку" воспроизведены живым прогоном, не пересчётом по заявленным числам — совпадают точно.

## Verdict: **PASS**

No defects filed. One minor process note (developer self-report slip, non-blocking, documented below for tracking discipline).

## Scope

Commit under test: `74cab7e` "Step 107 (Phase 2.17): sampled laws registry + drag-aware predictor law", branch `feature/sim-paper-alignment`.
Ticket: `dev/docs/task-107-sampled-laws-registry.md` (focus: §107.9 pin-safety greps, §107.10 test plan, §107.13 Definition of Done).

## Full suite — real background run, waited to a genuine process exit

Ran `python -m pytest -q > log 2>&1 ; echo "REAL_EXIT_CODE:$?"` via `run_in_background`, polled until the summary line and the echoed exit code both appeared (not inferred from the Bash tool's own "[exited with code 0]" wrapper message, which this project has twice mistaken for real completion — Steps 117/118). A first attempt here using `nohup ... &` inside a foreground Bash call reproduced exactly that trap: the tool reported "[exited with code 0]" in under a second while pytest kept running underneath for several more minutes (confirmed by watching the log file continue to grow). Caught and discarded before trusting it; re-run cleanly without `nohup`.

**Result: `743 passed, 0 failed, 56 warnings in 729.69s (0:12:09)`, `REAL_EXIT_CODE:0`** — echoed explicitly inside the backgrounded shell, confirmed by direct `Read` of the task's own `.output` file, not inferred from the harness's completion notification alone.

This resolves the 742-vs-743 question directly: the real full-suite count is **743 passed, 0 failed** — not 742 as the developer reported. See §1 below for the full reconciliation.

## Point-in-time run (DoD-mandated subset)

`python -m pytest tests/test_control.py tests/test_controllers.py tests/test_template_docs.py tests/test_integrate.py -q` → **78 passed, 0 failed**, real process exit code 0 (confirmed in the raw background-task output, not a wrapper placeholder). Only Mach-range sanity warnings in the output (pre-existing, unrelated to Step 107), no failures/errors.

## 1. Full-suite count reconciliation (742 vs 743 vs 721+22)

Independently re-derived via `git checkout <commit> && python -m pytest --collect-only -q` (no reliance on the developer's self-report):

- Parent commit `414bf8b` (QA report for Step 104, immediately before `74cab7e`): **721 tests collected**. Confirms the ticket's stated baseline.
- `74cab7e` (Step 107 HEAD): **743 tests collected**.
- `git show 74cab7e^:tests/test_control.py | grep -c "^def test_"` = 14; `git show 74cab7e:tests/test_control.py | grep -c "^def test_"` = 23 → **+9 new** test functions in `test_control.py`.
- `git show 74cab7e:tests/test_controllers.py | grep -c "^def test_"` = **13 new** test functions (new file).
- 9 + 13 = 22 new test *functions*; 721 + 22 = 743, which matches the collected count exactly, and matches the real full-suite pass count (743 passed, 0 failed/skipped).
- Read `tests/test_controllers.py` directly: `test_full_traceability_comparison_table` (§107.10 test 22, marked OPTIONAL in the ticket) **was implemented as a real pytest test function** (lines 296-343), not a plain script/print. It asserts an ordering (`none`'s apogee is the max of the five) and is one of the 13 counted above.
- `test_control.py`'s +9 (not the ticket's listed 8) is explained by one EXTRA regression test the developer added beyond the ticket's numbered test plan: `test_airbrake_deploy_fraction_without_a_hold_raises_for_a_registered_sampled_law` (covering the ValueError fix found during code review, not in §107.10's items 1-8).

**Verdict: the developer's self-reported "742 passed" does NOT reconcile with either hypothesis offered in the QA brief, and is simply wrong.** Collection is 743 (confirmed via `--collect-only`), the actual full-suite run passed all 743 with zero failures/skips, and the "test 22 implemented as a script, giving 721+21=742" theory is actively contradicted by the source: `test_full_traceability_comparison_table` IS a real `def test_...` function, already counted in both the grep-based function count and the pytest collection count — there is no missing-22nd-test to find. 721 + 9 + 13 = 743 exactly, matching both collection and the real run. **This is an undocumented off-by-one self-report slip by the developer (742 reported vs. 743 actual), the same standing issue Step 104's QA flagged (720-vs-721) — not a real regression, but worth recording per this phase's tracking discipline.**

## 2. Pin safety — §107.9's five grep commands, re-run from scratch

All five re-run independently (not copied from the developer's report):

1. `rg -n '"proportional_drag"|"pi_apogee"' sim/ tests/ controllers/ configs/ apps/` → matches ONLY in new/touched files (`controllers/__init__.py`, `tests/test_controllers.py`). No pre-existing collision.
2. `rg -n "register_sampled_law|known_sampled_laws|SampledLawHold|class Measurement" sim/ controllers/ tests/` (excluding the new/touched files) → matches only in `sim/integrate.py`'s new guard and `sim/params.py`'s new comment — both new code, both expected. No pre-existing collision.
3. `rg -n "AirbrakeHold\(" sim/ tests/` → `sim/control.py:408` (the pre-existing `_actuator_full` factory, keyword args, untouched), and `tests/test_control.py:616` (the NEW test `test_airbrake_deploy_fraction_unwraps_sampled_law_hold_full_actuator`, keyword args). No positional construction anywhere.
4. `rg -n 'airbrake_model\s*=\s*"[^"]+"' tests/ configs/ apps/` deduplicated → existing test/config values are exclusively `none`/`proportional`/`full`; the only `proportional_drag`/`pi_apogee` values are in the new test files; one new test-only dummy name (`test_s107_powered`). No existing call site reaches the new sampled-law path.
5. `rg -n "Control\(" tests/ configs/ apps/ sim/ | rg -v "Control\([a-zA-Z_]+="` → only `Control()` (no-arg) or `Control(**kw)` (unpacking) forms. No positional construction exists anywhere in the codebase.

**Verdict: all five grep checks confirmed clean, independently.**

### Diff-level confirmation on `sim/control.py`

`git diff 414bf8b..74cab7e -- sim/control.py` has exactly 4 hunks. Read directly (not just hunk headers):
- Hunk 1: module docstring addition only.
- Hunk 2: `airbrake_deploy_fraction`'s docstring + a new `SampledLawHold` unwrap + a new `ValueError` branch inserted BEFORE the existing `return _AIRBRAKE_CONTROLLERS[...]` line — the existing dispatch line itself is unmodified below the insertion.
- Hunk 3: `sample_airbrake`'s docstring + a new `if name in _SAMPLED_LAWS:` branch inserted BEFORE the existing two-line dispatch body, which is otherwise unmodified.
- Hunk 4: purely new code appended after `known_actuator_models()` (registry, `Measurement`, `SampledLawHold`, `_ideal_measurement`, `_in_coast_window`, etc.) — append-only, no hunk touches `_proportional_airbrake`/`_full_airbrake`/`_no_airbrake`/`AirbrakeHold`/`_ramp`/`_actuator_ideal`/`_actuator_full` bodies anywhere.

Also confirmed: `git diff 414bf8b..74cab7e -- sim/params.py sim/integrate.py configs/rockets/_TEMPLATE_rocket.py` — the five new `Control` fields are appended at the END of the dataclass (no positional shift risk even if positional construction existed, which it doesn't per grep 5), the new eager-validation guard in `run_sim` matches the ticket's §107.7 design, and the template doc table/example rows are consistent additions.

Confirms the DoD's "zero diff" claim for the seven legacy names directly from the diff, not from the developer's self-report.

## 3. The `airbrake_deploy_fraction` `ValueError` fix — additivity and regression test

Diff (hunk 2 above): the new code is `name = p.control.airbrake_model; if name in _SAMPLED_LAWS: raise ValueError(...)` inserted immediately before the pre-existing `return _AIRBRAKE_CONTROLLERS[name](t, y, p)`. Because `register_sampled_law` (same commit) explicitly raises `ValueError` if a caller tries to register a name colliding with a built-in (`none`/`proportional`/`full`), `_SAMPLED_LAWS` can never contain one of those three names — so `name in _SAMPLED_LAWS` is **provably always `False`** for every existing call site (which only ever uses `none`/`proportional`/`full`), regardless of whether `controllers/` has been imported. Confirmed additive-only: cannot change behavior for any existing non-sampled-law call site.

Regression test `test_airbrake_deploy_fraction_without_a_hold_raises_for_a_registered_sampled_law` (`tests/test_control.py:630-646`) genuinely exercises the new path: it registers a real (if trivial) dummy law under a test-only name, builds a `Params` using that name, calls `airbrake_deploy_fraction` WITHOUT a `hold` argument, and asserts `pytest.raises(ValueError)` — not a no-op/trivial assertion. Cleans up via `finally: del control._SAMPLED_LAWS[...]`. **Confirmed genuine.**

## 4. The two unfixed review findings — traced to the ticket's own literal content

Both read directly against the ticket text (§107.5, lines 537-591) and the shipped `controllers/laws.py`:

- **`p.g0` instead of `gravity.g(t,y,p)`**: the ticket's own code sketch at line 564/582 (`drag_aware_predicted_apogee(h_hat, v_hat, p.g0, c.onboard_mass, k)`) uses `p.g0` verbatim. `controllers/laws.py` lines 68/86 match this byte-for-byte. **Confirmed: ticket's own literal content, not a developer deviation.**
- **`pi_apogee` recomputing `dt` that `estimator.step` also computes internally**: the ticket's own sketch at line 579 (`dt = 0.0 if prev.est is None or prev.est.t_prev is None else t_k - prev.est.t_prev`) duplicates the same subtraction `estimator.step` performs internally at line 515 (`dt = t - prev.t_prev`). `controllers/laws.py` line 83 matches the ticket's sketch verbatim. **Confirmed: ticket's own literal content, not a developer deviation.**

Neither finding is a developer-introduced regression; both are the architect's own ticket code, correctly left as literal per §107.12's explicit hand-off to Step 108. Not a QA defect against the developer — if anything, a (very minor, non-blocking) observation that the ticket's own code sketch carries forward two known inefficiencies already flagged in review.

## 5. §107.10 test-plan spot checks (3-5, 9, 17-18, 19) — read, not just run

- **Test 3** (`test_sample_airbrake_dispatches_to_a_registered_law_once_per_tick`): calls `sample_airbrake` directly in a loop over 6 synthetic ticks (not through `run_sim`, avoiding the RK4-substep trap), asserts the counting dummy's call count equals exactly `n_ticks`. Genuine.
- **Test 4** (`..._threads_prev_ctrl_state_across_ticks`): a recording dummy returns `len(seen_states)` as its new state; test asserts `seen_states[k] == k` for `k>0`, i.e., tick `k`'s `state` argument is exactly tick `k-1`'s returned state. Genuine, direct proof of state threading.
- **Test 5** (`..._outside_the_coast_window_does_not_call_the_law`): builds a genuinely-under-thrust scenario, asserts `thrust_curve.thrust(...) > 0.0` as an explicit sanity check (not assumed), then asserts the dummy law's call count stays 0 and `hold.actuator_hold == 0.0`. Genuine, includes the sanity assertion the brief asked to look for.
- **Test 9** is structural (full pre-existing suite re-run) rather than a single function — confirmed via the point-in-time DoD run above (78 passed) plus the full-suite run above (743 passed, 0 failed); `_proportional_airbrake` itself is untouched per the diff-level check in §2.
- **Tests 17-18** (`pi_apogee` integral accumulation / anti-windup, `tests/test_controllers.py:150-197`): test 17 isolates the integral term by holding `h_baro` constant (so `v_hat==0`, `h_a` constant) and asserts `integral[0]==0.0`, `integral[1]==error*1.0`, `integral[2]==integral[1]+error*1.0` — genuine isolation of the accumulation formula. Test 18 drives a large sustained positive error to saturate `cmd==1.0`, asserts two consecutive post-saturation `integral` values are EQUAL (frozen), then flips the target to force a sign change on `error` and asserts `integral` moves again (desaturation) — genuinely exercises both halves of the anti-windup logic, not just existence.
- **Test 19** (`test_sampled_law_state_resets_between_independent_run_sim_calls`, `tests/test_controllers.py:205-226`): runs the identical `pi_apogee` scenario twice via two independent `run_sim` calls with freshly-constructed `Params` each time, asserts the two resulting apogee altitudes are bit-identical (`==`, not `approx`). Genuine proof against module-level mutable-default leakage.

All seven spot-checked tests genuinely test what they claim.

## 6. Comparison-table live reproduction

Re-ran `tests/test_controllers.py::test_full_traceability_comparison_table` and `::test_pi_apogee_open_loop_sanity_reduces_steady_state_error_vs_proportional_drag` live (`-s` to capture the printed table), not recomputed from the developer's reported numbers:

```
Step 107 comparison table (nominal demo flight, apogee in m):
  none                 666.506
  full                 303.522
  proportional         490.269
  proportional_drag    513.165
  pi_apogee            490.870
2 passed in 21.75s
```

Matches the developer's reported numbers exactly on live re-run. `|490.870 - 500| = 9.130` (pi_apogee) < `|513.165 - 500| = 13.165` (proportional_drag) — the "integral action reduces P-only steady-state error" acceptance claim is confirmed live, and both the comparison-table test and the dedicated steady-state-error comparison test pass. **Confirmed via a live re-run, not arithmetic on reported numbers.**

## Definition of Done (§107.13) — checklist cross-reference

- [x] `sim/control.py` registry/dispatch wiring, zero diff on legacy functions — confirmed §2.
- [x] `controllers/` package implemented per §107.5 — read directly, matches ticket sketch (§4).
- [x] `sim/params.py` five new fields + comment fix — confirmed §2 diff.
- [x] `sim/integrate.py` eager-validation guard — confirmed §2 diff.
- [x] `configs/rockets/_TEMPLATE_rocket.py` table/example rows — confirmed §2 diff; `tests/test_template_docs.py` green in the point-in-time run.
- [x] `tests/test_control.py` new tests (9, not ~9 as "approximately 8") all passing — confirmed §1/§5.
- [x] `tests/test_controllers.py` new tests (13) all passing — confirmed §1/§5/§6.
- [x] §107.9 grep re-run, zero surprising matches — confirmed §2.
- [x] Point-in-time subset green — confirmed (78 passed).
- [x] Full suite green in background, real exit code — confirmed (743 passed, 0 failed).
- [x] §107.10 test 22 comparison table measured and reported — confirmed §6, live reproduction matches.
- [x] code-review skill run before QA — evidenced by the commit message itself ("Also fixes a gap code-review surfaced").

## Defects

None. Zero blocker/major/minor defects found in this pass.

## Process note (non-blocking)

Developer's PR/ticket-closing self-report said "742 passed" against an actual 743. Not a regression, not affecting the PASS verdict, but recorded per this phase's own tracking discipline (same standing as Step 104's 720-vs-721 catch) — worth a one-line correction in the step's closing note if the orchestrator wants the record exact.

# QA Report — Phase 2.17 Step 108 (baro sensing channel + alpha-beta estimator)

## Кратко (RU)

- Вердикт: **PASS**. Все 8 пунктов независимой проверки подтверждены: список изменённых файлов
  совпадает с заявленным; пинованная `_isa_air_state` байт-в-байт не тронута; циклический импорт
  `sim/sensors.py` <-> `sim/control.py` реально разрешён ленивым импортом (тот же паттерн, что и в
  `sim/aero.py`), проверено в обоих направлениях импорта; alpha-beta-оценщик аддитивен и включается
  только явно, путь по умолчанию (`estimator_model="stub"`) функционально не изменился; оба
  заявленных фикса после код-ревью (guard от `OverflowError` на `dt<=0`, расширенные тайп-хинты
  `est`) реально есть в диффе; 4 из 5 pin-safety grep'ов из §108.5 совпали точно; полный прогон —
  765/765 (точное совпадение с заявленным числом), 11м19с — целевой прогон и точечный (58 тестов).
- Найдено 3 минорных замечания (не блокеры): (D1) нет отдельного регрессионного теста на
  `_step_alpha_beta`'s `dt<=0` guard в estimator.py (есть только для sensors.py); (D2) саммари
  разработчика переврал число новых тестов (+8/16 заявлено, фактически +6/15) — итоговая сумма
  (765) верна, расхождение только в разбивке по файлам; (D3) один grep из §108.5 нашёл одно
  совпадение в докстринге вместо заявленных "zero hits" — не дефект, формулировка тикета неточна.
- Отдельно зафлагано (не дефект Step 108): в рабочем дереве одновременно лежат несcommitted
  правки latex-секций (`dev/docs/latex/sections-ai/*.tex`) и новые research-доки — это параллельная
  работа архитектора по Step 109 (маховик/roll), не связанная с сенсорами/оценщиком. При коммите
  Step 108 нужно стейджить файлы поимённо, а не `git add -A`, чтобы не затащить чужую работу.
- Рекомендация: принять Step 108 как есть; D1-D3 — опциональные доработки, не блокируют коммит.

## Scope

Branch `feature/sim-paper-alignment`, uncommitted working tree. Verifying developer's Step 108
self-report against `dev/docs/task-108-sensors-estimator.md` (876 lines, architect spec) and the
8 verification items given by the orchestrator. Independent, no trust in the self-report.

## 1. Diff footprint vs claimed file list

`git diff --stat` (uncommitted, vs last commit `d099cf8`):

```
configs/rockets/_TEMPLATE_rocket.py           |  28 ++-
configs/schema.py                             |   7 ++
controllers/estimator.py                      |  89 +++++++---
controllers/laws.py                           |  17 +-
dev/docs/latex/sections-ai/appendix.tex       |   7 ++
dev/docs/latex/sections-ai/assumptions.tex    |  11 +-
dev/docs/latex/sections-ai/backlog.tex        |  15 +-
dev/docs/latex/sections-ai/models.tex         |   5 +-
dev/docs/latex/sections-ai/other-dynamics.tex | 145 +++++++
sim/atmosphere.py                             |  70 +++
sim/control.py                                |  46 +-
sim/params.py                                 |  27 +++
tests/test_control.py                         |  26 +++
tests/test_controllers.py                     |  98 +++
14 files changed, 520 insertions(+), 71 deletions(-)
```

Untracked: `sim/sensors.py`, `tests/test_sensors.py` (claimed, new), plus
`dev/docs/task-108-sensors-estimator.md`, `dev/docs/task-109-roll-reaction-wheel.md`,
`dev/docs/latex/research/*.md`, `docs/` — all documentation/spec artifacts, not code.

**Finding (not a defect):** the five `dev/docs/latex/sections-ai/*.tex` files ARE modified in the
working tree, which looks at first glance like a violation of acceptance item 8 ("confirm zero
edits anywhere under dev/docs/latex/"). Inspected the content of the diffs (`other-dynamics.tex`,
`backlog.tex`): they add a whole new `\subsection{Roll and the reaction wheel}` section plus
`\restodo`/`\simtodo` markers and backlog rewording — this is **architect's design content for the
next step, Step 109 (roll reaction wheel)**, matching the new untracked
`dev/docs/task-109-roll-reaction-wheel.md`. It has nothing to do with sensors/estimator and is not
part of developer's Step 108 diff (developer's own file list never mentions latex). This is
pre-existing/parallel uncommitted work sitting in the same working tree, not a Step 108 scope leak.
Confirmed clean for Step 108 purposes; flagging so the orchestrator knows the tree is not currently
"only Step 108" — anyone diffing by `git status` alone would need this context before committing.

Claimed file list vs actual: **all 14 tracked + 2 new files match exactly**, no extra code file
changed, no claimed file missing a change. PASS.

## 2. `_isa_air_state` zero-diff check

`git diff -U1 sim/atmosphere.py` shows **only added lines** for the `_isa_air_state` region (no
`-` lines except the diff header itself). Independently extracted the function body via regex from
`git show d099cf8:sim/atmosphere.py` (pre-Step-108) vs the working tree and compared: **byte-identical
(`True`)**. `isa_pressure_altitude`/`_isa_pressure_core` are fully additive, inserted after the
existing function, duplicating the tiny forward-pressure core rather than refactoring the pinned
path — matches the claimed "duplicate, don't refactor a pinned path" precedent (task-104/107).
PASS, zero pin risk from this file.

## 3. Circular-import fix — independently verified

`sim/control.py` now imports `from sim import gravity, sensors, thrust_curve` at module top-level
(line 88). `sim/sensors.py` does **not** import `sim.control` at module top; it does
`from sim.control import Measurement` lazily, inside `measure()` (line 58), guarded by
`TYPE_CHECKING` for the type-hint-only top-level reference. This is structurally identical to the
cited precedent in `sim/aero.py` (line 847, `from sim import control` deferred inside
`aero_coeff_delta`'s helper, same "circular-import avoidance" comment style, same precedent chain
citing `sim/flow.py`/`sim/forces.py`).

Fresh-process verification, both import orders, no `ImportError`:
```
python -c "import sim.sensors; import sim.control"   -> OK
python -c "import sim.control; import sim.sensors"   -> OK
```
PASS.

## 4. Alpha-beta estimator additivity / stub default path

- `Control.estimator_model: str = "stub"` (new field, `sim/params.py` diff) — confirmed default.
- `controllers/estimator.py`: `_step_stub` docstring claims "Step 107's own body, UNCHANGED"; `step()`
  dispatches `model=="stub"` (default) -> `_step_stub(t, h_baro, prev)`, ignoring `p` entirely —
  confirmed by reading the dispatcher.
- `controllers/laws.py` call sites (`proportional_drag`, `pi_apogee`): both changed from
  `estimator.step(t_k, meas.h_baro, prev.est)` (3 positional args) to
  `estimator.step(t_k, meas.h_baro, prev.est, model=c.estimator_model, p=p)`. With
  `c.estimator_model` defaulting to `"stub"`, this call is functionally identical to the
  pre-Step-108 3-arg call (the dispatcher ignores `p` on the stub branch). A dedicated regression
  test (`test_estimator_step_three_positional_args_is_bit_identical_to_pre_ticket_stub`, new,
  `tests/test_controllers.py`) asserts bit-identity between the bare 3-arg call and the explicit
  `model="stub", p=None` call. PASS — genuinely additive and opt-in only.

## 5. Spot-check the two code-review fixes

**(a) OverflowError guard on negative/out-of-order `dt`:**
- `sim/sensors.py::measure`, lag branch (lines 67-80): `dt = t - prev.t_prev`; `if dt <= 0.0:
  h_lag = prev.h_lag_prev` (holds previous value) **before** reaching the `math.exp(-dt/tau)` line
  that would otherwise overflow for a strongly negative `dt`. Confirmed present in the diff, and a
  dedicated regression test exists and passes:
  `test_lag_out_of_order_tick_holds_previous_estimate_instead_of_overflowing` (`tests/test_sensors.py`).
- `controllers/estimator.py::_step_alpha_beta` (lines 54-56): same `if dt <= 0.0: return prev.h_hat,
  prev.v_hat, AlphaBetaState(...)` guard, same "hold previous" convention. **Gap found:** no
  dedicated unit test in `tests/test_controllers.py` exercises this specific branch directly (only
  `tests/test_sensors.py`'s docstring references it by name in a comment). Manually verified by hand
  that the guard works correctly (no crash, holds previous estimate: fed `t=10.0` then `t=0.0`,
  got `h_hat=123.0` held, `state.t_prev` updated to `0.0` as expected) — the code is correct, but
  test coverage of this exact branch is indirect only. **Minor defect: missing direct regression
  test for `_step_alpha_beta`'s own `dt<=0.0` guard** (ticket claims "a regression test" singular
  for this fix-class; only the sensors.py side has one).

**(b) Widened `est` type hints:**
- `controllers/laws.py`: `ProportionalDragState.est` and `PiApogeeState.est` changed from
  `Optional[estimator.EstimatorState]` to `Optional[estimator.EstimatorState | estimator.AlphaBetaState]`,
  with a comment attributing the find to code review. Confirmed present in the diff at both sites.
  PASS — real, not just claimed.

## 6. §108.5 pin-safety grep re-run (independent)

Ran all five greps myself (verbatim commands from the ticket):

1. `grep -rn "_ideal_measurement" sim/ controllers/ tests/` — ticket expects **zero hits**. Actual:
   **one hit**, `sim/sensors.py:4`, inside the new module's own docstring referencing the
   historical name for context ("replacing Step 107's own `sim.control._ideal_measurement` stub").
   Not a live code reference — `_ideal_measurement` itself is fully deleted from `sim/control.py`
   (confirmed by reading the diff: function body removed, not just renamed). **Minor
   discrepancy from the ticket's literal "zero hits" wording** — functionally harmless (a doc
   comment, not dead code), but technically not what the acceptance grep promised; worth a
   one-line decision on whether the architect's own wording should have said "zero hits outside
   this ticket's own new docstrings."
2. `grep -rn "estimator\.step(" controllers/ tests/` — matches ticket's expectation exactly: 2
   `laws.py` sites (now with `model=`/`p=`) + direct stub/alpha_beta calls in
   `tests/test_controllers.py` (3-positional-arg stub calls unchanged). PASS.
3. `grep -n "_isa_air_state" sim/atmosphere.py` — all 9 hits are either the untouched function
   definition or new/unrelated code's comments referencing it by name; none is inside a modified
   line of the function body itself (cross-checked against item 2's byte-identical diff). PASS.
4. `grep -rn "sens_state" sim/control.py` — matches: `SampledLawHold.sens_state` field declaration
   (unchanged shape) + the two new read/write sites in `sample_airbrake`. PASS.
5. `grep -rn "Params(" configs/schema.py` — exactly one call site (line 371), now with
   `sensors=sc.rocket.sensors` added (line 379). PASS.

Net: 4/5 exact match, 1/5 (`_ideal_measurement`) technically has a stray docstring hit not
anticipated by the ticket's own "zero hits" wording — logged as minor, not a functional defect.

## 7. Full test suite — independent re-run

Targeted first (`tests/test_sensors.py tests/test_controllers.py tests/test_control.py`): **58
passed**, 36.15s. No failures.

Full suite collection count (`pytest --collect-only -q`): **765 tests** — matches the self-report's
claimed pass count exactly.

**Test-count discrepancy found in the self-report** (does not affect pass/fail, only the stated
breakdown): self-report claims `tests/test_sensors.py` (new) has "16 tests" and
`tests/test_controllers.py` gained "+8". Independently counted via `pytest --collect-only`:
`test_sensors.py` collects **15** tests (not 16); `test_controllers.py` went from 13 -> 19 tests,
i.e. **+6** (not +8), confirmed against both the pre-ticket file (`git show d099cf8:...`) and a
`git diff | grep '^+def test_'` count (6 new function defs: `test_alpha_beta_first_call_...`,
`test_alpha_beta_converges_...`, `test_alpha_beta_attenuates_noise_...`,
`test_estimator_step_three_positional_args_...`, `test_estimator_step_unknown_model_...`,
`test_proportional_drag_and_pi_apogee_run_with_alpha_beta_estimator`).
`tests/test_control.py`'s claimed "+1" is exact (23 -> 24). Net effect: self-report overcounts new
tests by 3 (claimed 16+8+1=25 new; actual 15+6+1=22 new) — but the **total current suite count
(765) matches the claimed pass count exactly**, so this is a bookkeeping inaccuracy in the
self-report's per-file breakdown, not a sign of missing/hidden test files or an inflated pass
count. Logged as minor (self-report hygiene), not a functional defect.

Full background re-run (`python -m pytest -q`, this session, `run_in_background`) completed:

```
765 passed, 56 warnings in 679.38s (0:11:19)
```

Exact pass count match (765 == 765 collected == self-report's claimed 765), 0 failed, runtime
11m19s — consistent with the developer's own observation of ~11 min tonight (slower than the
~220-390s historical baseline, but the self-report flagged this in advance; no flaky crash
observed on this independent run either). The 56 warnings are pre-existing `AeroRangeWarning`/
`MachRangeWarning` noise from unrelated test modules (`test_scenario_sweep.py`,
`test_weight_aero_tradeoff.py`), not new from this ticket's own files. PASS.

**Process note (not a defect):** attempted `git stash` / `git stash pop` to get a clean pre-ticket
baseline collection count for cross-reference; this was **denied by the Claude Code auto-mode
permission classifier** ("Blocked by classifier"). Correct outcome per this role's own git-safety
contract (no destructive/working-tree-touching git beyond read-only inspection) — did not retry or
work around it; abandoned that line of inquiry since the collected-count match (765) already gives
sufficient confidence without it.

## 8. Edits outside the claimed scope — `dev/docs/latex/`, `configs/`, `data/`

`git status --porcelain -- configs/ data/ dev/docs/latex/`:

```
 M configs/rockets/_TEMPLATE_rocket.py
 M configs/schema.py
 M dev/docs/latex/sections-ai/appendix.tex
 M dev/docs/latex/sections-ai/assumptions.tex
 M dev/docs/latex/sections-ai/backlog.tex
 M dev/docs/latex/sections-ai/models.tex
 M dev/docs/latex/sections-ai/other-dynamics.tex
?? dev/docs/latex/research/3d-readiness-proposal.md
?? dev/docs/latex/research/model-development-candidates.md
```

- `configs/`: only the two claimed files (`schema.py`, `_TEMPLATE_rocket.py`) touched. `data/`:
  zero changes (nothing listed at all). PASS for both.
- `dev/docs/latex/`: five `.tex` files modified + two new untracked research `.md` files. As
  established in §1, read the full diffs of `appendix.tex`, `assumptions.tex`, `backlog.tex`,
  `models.tex`, `other-dynamics.tex` — every single one is about the roll/reaction-wheel topic
  (`\subsection{Roll and the reaction wheel}`, roll sign conventions, roll-torque backlog item),
  matching the new `dev/docs/task-109-roll-reaction-wheel.md`. **None references sensors, the baro
  channel, or the estimator** — this is the architect's own parallel design work for the *next*
  step (Step 109), already sitting uncommitted in this shared working tree, not something the
  Step 108 developer touched. Developer's own file list in the self-report never mentions any
  latex file, consistent with this conclusion.
  **Verdict for Step 108 specifically: PASS** (zero latex edits attributable to this ticket).
  **Operational flag for the orchestrator (not a Step 108 defect):** the working tree currently
  mixes Step 108's code changes with Step 109's uncommitted design/latex changes. Whoever commits
  Step 108 needs to stage file-by-file (not `git add -A`) to avoid bundling Step 109's unrelated
  latex/doc work into the Step 108 commit.

## Summary / Verdict

**Overall: PASS.** All 8 independent verification items check out: file footprint matches the
claimed list exactly (modulo the pre-existing Step-109 latex/doc noise in the shared tree, which
is not Step 108's own scope and does not touch sensors/estimator content); the pinned
`_isa_air_state` core is byte-identical; the circular-import fix is real and structurally matches
the cited precedent, verified in both import orders; the alpha-beta estimator is genuinely
additive/opt-in with the stub default path functionally unchanged; both claimed code-review fixes
are real in the diff; 4 of 5 pin-safety greps match exactly, one has an inconsequential stray
docstring hit; the full suite passes 765/765 (exact match to the claim) in both a targeted (58
tests, 36s) and full (765 tests, 11m19s) independent re-run.

### Defects / findings log

| # | Severity | Area | Description |
|---|----------|------|-------------|
| D1 | Minor | Test coverage | `controllers/estimator.py::_step_alpha_beta`'s own `dt<=0.0` guard (code-review fix (a), estimator side) has no direct regression test — only `sim/sensors.py`'s lag-branch sibling fix is covered by `test_lag_out_of_order_tick_holds_previous_estimate_instead_of_overflowing`. Manually verified the guard behaves correctly; recommend adding one direct test in `tests/test_controllers.py` (e.g. `estimator.step(t=10.0, h, None, model="alpha_beta", p=p)` then `estimator.step(t=0.0, h2, state, model="alpha_beta", p=p)`, assert previous estimate held, no exception). |
| D2 | Minor | Self-report accuracy | Self-report overcounts new tests: claims `test_sensors.py` has 16 tests (actual 15) and `test_controllers.py` gained +8 (actual +6). Total suite count (765) is correct regardless — no missing test files, just an inaccurate per-file breakdown in the hand-off narrative. |
| D3 | Minor / informational | Pin-safety grep wording | §108.5 grep #1 (`_ideal_measurement`) finds one hit (a docstring reference to the deleted name in `sim/sensors.py`'s own module docstring), not the "zero hits" the ticket's own text promises. Functionally harmless; either accept the docstring reference or reword the ticket's acceptance text to "zero *live* references." |
| — | Not a defect (flagged for orchestrator) | Git hygiene | `dev/docs/latex/sections-ai/*.tex` (5 files) + 2 new `dev/docs/latex/research/*.md` files are modified/added in the shared working tree from what appears to be the architect's parallel Step 109 (roll reaction wheel) design work, unrelated to Step 108. Needs file-by-file staging when Step 108 is committed so the two steps' work doesn't get bundled into one commit. |

No blocker or major defects found. Recommend accepting Step 108 as-is; D1-D3 are cheap/optional
follow-ups and do not block the commit.

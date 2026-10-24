# QA Report — Step 117 (D-126): C_m/C_mq internal rename

## Кратко (RU)

- **Вердикт: PASS.** Переименование `C_m`/`C_mq` → `C_m_code`/`C_mq_code` (только внутренние,
  всегда-code-convention поля `AeroCoeffs`/`_AeroTable` и обёртки `aero.C_m()`/`aero.C_mq()`)
  проверено независимо и полностью — все 13 изменённых файлов, все diff-хунки побайтово совпадают
  с тикетом, ни одно числовое значение/формула не задеты.
- Все 4 acceptance-проверки §117.10 (`rg`) перепрогнаны самостоятельно — классификация совпадает с
  тикетом, пропущенных переименований нет, граница ввода-вывода (`configs/`, `apps/`, `data/`,
  CSV-заголовки) не тронута.
- `dev/docs/latex/` — ноль правок (подтверждено `git diff --stat`). `sim/params.py` — ровно одна
  строка докстринга `l_p` (§117.8), больше ничего.
- Полный прогон тестов: **705/705 passed, 0 failed, 0 error** (637 с) — совпадает с заявленным
  бейзлайном. Первая попытка полного прогона в этой сессии упала с нативным
  `Windows fatal exception: access violation` внутри `scipy.integrate.solve_ivp` на
  `tests/test_plotting.py` на 71% прогона — не воспроизводится при повторном прогоне того же файла
  изолированно (10/10 passed) и не повторилась во втором полном прогоне (705/705 passed) → классифицирую
  как нестабильный (flaky) нативный краш окружения Windows/scipy, **не связанный со Step 117**
  (файл `test_plotting.py` и `sim/dynamics.py` не входят в дифф этого шага). Стоит зафиксировать в
  CLAUDE.md как известную ловушку окружения.

## Scope

Independent verification of Step 117 (D-126): rename internal always-code-sign `C_m`/`C_mq` fields and wrapper functions to `C_m_code`/`C_mq_code`. Claimed: zero numeric pin movement, zero LaTeX edits, 13 files changed, 705/705 tests passing.

Reference: `dev/docs/task-117-cm-rename.md` (910 lines).

## 1. File list check (`git diff --stat`)

`git diff --stat` (uncommitted working tree) shows exactly 13 files, matching the ticket's §117.9 table + §117.6/§117.7/§117.8 production files 1:1, no more, no less:

```
sim/aero.py                        | 89 ++++++++++++++++++++------------------
sim/control.py                     |  4 +-
sim/forces.py                      | 14 +++---
sim/params.py                      |  3 +-
sim/report.py                      | 18 ++++----
tests/test_aero.py                 | 30 ++++++-------
tests/test_aero_fb.py              |  2 +-
tests/test_aero_oob.py             |  8 ++--
tests/test_aero_v2.py              | 18 ++++----
tests/test_control.py              |  6 +--
tests/test_qa_phase217_m1.py       |  6 +--
tests/test_report.py               |  2 +-
tests/test_step114_review_fixes.py |  6 +--
```

`git status --porcelain` confirms no additional modified/staged files. Untracked: `dev/docs/qa-report-2.17-step117.md` (this report), `dev/docs/task-117-cm-rename.md` (the ticket itself), and a pre-existing empty `docs/latex/` directory dated 2026-10-20/22 (predates this step, unrelated — confirmed not part of this diff, harmless stray artifact, not flagging as a Step 117 defect).

**Verdict: PASS.** File list matches exactly.

## 2. Diff hunk spot-check (byte-for-byte RHS preservation)

Read full diffs for `sim/aero.py`, `sim/forces.py`, `sim/control.py`, `sim/params.py`, `sim/report.py`, and test files `tests/test_aero.py`, `tests/test_control.py`, `tests/test_aero_v2.py`, `tests/test_aero_oob.py`, `tests/test_aero_fb.py`, `tests/test_qa_phase217_m1.py`, `tests/test_report.py`, `tests/test_step114_review_fixes.py` (i.e. all 13 changed files, not just the minimum sample asked for) and compared every hunk against the ticket's §117.6-§117.9 "replace X with Y" blocks.

- Every hunk matches the ticket's specified replacement byte-for-byte on the right-hand side: numeric literals (`== -0.1396`, `== 12.5`, `== 7.0`, `== 50.0`, `== -0.2`, `== -5.0`, `== 0.2`, `== 8.0`, etc.) are untouched in every test file; arithmetic expressions in production code (`_cm_to_code(p.aero.C_m, p)`, `_table_lookup(table, alpha, M, table.C_m_code)`, `(1.0 - w) * clamped.C_m_code + w * Cm_J`, `flow.q * p.aero.S * p.aero.d_ref * c.C_m_code`, `0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * s[OMEGA] * c.C_mq_code`) are reproduced exactly, only the identifier/kwarg name changed on the left of `=` or after the dot.
- `p.aero.C_m`, `p.aero.C_m_alpha`, `p.aero.c_mq` (config-field reads, right-hand side of `_cm_to_code(...)` calls) are untouched everywhere, as required.
- `_cm_to_code`'s own body/parameter (`sim/aero.py` lines 413-420) verified untouched/STAYS as the ticket specifies.
- One finding (not a defect, informational): `sim/forces.py`'s diff includes three prose-only docstring renames at module-docstring lines ~36, 46, 48 (`` `C_A`/`C_N`/`C_m` `` → `` `C_A`/`C_N`/`C_m_code` ``, etc.) that are **not explicitly enumerated** in the ticket's §117.7 (which only names "docstring line 257, body lines 291-292" for this file). These are legitimate renames of the same always-code-sign `AeroCoeffs` field being described, consistent with §117.2's dividing line, and are required to satisfy §117.10 acceptance check 1 (`rg "\bC_m\b" sim/forces.py` would otherwise still show unrenamed hits not on the STAYS list) — so this is the ticket's own §117.7 enumeration being incomplete, not a developer scope violation. No arithmetic/numeric impact either way.

**Verdict: PASS.** No RHS/formula/literal drift found in any sampled or full-read hunk.

## 3. §117.10 acceptance checks (independently run and classified)

**Check 1** (`rg -n "\bC_m\b" sim/aero.py sim/forces.py sim/control.py sim/report.py`): 15 hits. All classified STAYS per ticket's explicit list (CSV format doc line 49, `cm_convention` prose lines 68/75/116/244, `_load_table` local `C_m_col`/CSV key lines 259/281, `_cm_to_code` verbatim body/param lines 413/415/418/420, `p.aero.C_m` RHS read line 575, `sim/report.py` line 152 generic-prose STAYS, and two lines (837-838) that are part of the ticket's own new `C_m_code` docstring text intentionally quoting the textbook formula name `C_m`/models.tex `A_m = qSd_ref*C_m`). Zero unclassified/missed-rename hits.

**Check 2** (`rg -n "\bC_mq\b" sim/aero.py sim/forces.py sim/control.py sim/report.py`): 2 hits, both STAYS per ticket (line 280's `_load_table` STAYS block, line 641's generic textbook-`C_mq`-vs-`C_m_alpha` prose). Zero unclassified hits.

**Check 3** (`rg -n "\.C_m\b|\.C_mq\b|AeroCoeffs\(.*C_m=|AeroCoeffs\(.*C_mq=|_AeroTable\(.*C_m=|_AeroTable\(.*C_mq=" tests/`): 3 hits, none a missed rename — all three (`tests/test_configs.py:138`, `tests/test_forces.py:94`, `tests/test_motor_selection.py:342`) are `*.aero.C_m` config-field reads (`derived.params.aero.C_m`, `p.aero.C_m`, `baseline.aero.C_m`), in files the ticket's §117.9 explicitly lists as needing **zero** changes. Note for the record: the ticket's own check 3 command says "should return zero hits" but the `\.C_m\b` pattern cannot syntactically distinguish `AeroCoeffs.C_m`-style field access from `params.aero.C_m`-style config access — this is an imprecision in the ticket's own acceptance-check regex, not a developer defect; I independently confirmed by context that all 3 surviving hits are config-field reads, not a missed `AeroCoeffs`/`_AeroTable` rename.

**Check 4** (`rg -n "\bC_m\b|\bC_mq\b" data/aero/ configs/ apps/ run.py`): 25 hits. Per the earlier `git diff --stat -- configs/ apps/ data/` (empty — see §4 below), this count is provably unchanged from pre-Step-117 baseline, since zero diff hunks touch any file under these paths.

**Verdict: PASS.** All four checks independently run and classified; zero missed renames, zero accidental I/O-boundary renames.

## 4. LaTeX / configs / apps / data scope isolation

- `git diff --stat -- dev/docs/latex/` → empty output. **Zero LaTeX edits confirmed.**
- `git diff --stat -- configs/ apps/ data/` → empty output. **Zero edits in configs/apps/data confirmed**, matching the I/O-boundary-untouched claim.

**Verdict: PASS.**

## 5. `sim/params.py` bundled fix (§117.8)

Full diff of `sim/params.py`:

```
@@ -102,7 +102,8 @@ class Aero:
-    # Step 99 (D-111): CP station from the nose [m] for the constant/linearized models
+    # Step 99 (D-111): moment reference station from the nose [m] (x_ref) for the
+    # constant/linearized models
     # (arm = l_p - CoG(t)); 0.0 = off, Lengths.l1 is the arm. A table carries its own l_p_m column.
     l_p: float = 0.0
```

Exactly the one `l_p` comment reword specified in §117.8 (one logical line split across two physical lines due to length — content matches the ticket's replacement text verbatim). Nothing else in the file touched; `Aero.C_m`/`C_m_alpha`/`c_mq`/`cm_convention` fields confirmed untouched (not present in diff at all).

**Verdict: PASS.**

## 6. Full test suite (independently rerun from scratch, two attempts)

**This QA attempt is a retry** of a prior QA session that was lost mid-run (per the task prompt). I re-verified sections 1-5 from scratch myself (not trusting the partial report's prior content beyond spot-re-confirming it), then ran the full suite independently, twice:

**Attempt 1** (`python -m pytest -q`, backgrounded, polled in ~210s-capped loops): reached 71% (all dots, zero `F`/`E` up to that point), then the background process terminated with a native crash, not a pytest-level failure:

```
Windows fatal exception: access violation

Current thread 0x00002e00 (most recent call first):
  File "D:\Projects - Ongoing\rocket-physics\sim\dynamics.py", line 131 in _cross_y
  File "D:\Projects - Ongoing\rocket-physics\sim\dynamics.py", line 332 in derivatives
  File ".../scipy/integrate/_ivp/ivp.py", line 598 in fun
  ...
  File ".../scipy/integrate/_ivp/rk.py", line 64 in rk_step
  ...
  File "D:\Projects - Ongoing\rocket-physics\sim\integrate.py", line 488 in run_sim
  File "D:\Projects - Ongoing\rocket-trajectory\tests\test_plotting.py", line 243 in test_flight_summary_apogee_altitude_equals_helper_directly
```

Noteworthy but not actionable for this ticket: the crashing frame's own path says `D:\Projects - Ongoing\rocket-trajectory\tests\test_plotting.py` — a stale absolute path baked into a cached/compiled artifact from before this repo was renamed from `rocket-trajectory` to `rocket-physics` (confirmed: no `rocket-trajectory` directory exists on this machine today; `rocket-physics` is the only one). This is an environment artifact, not a code defect.

**Triage before re-running the full suite:** reran `python -m pytest tests/test_plotting.py -q` alone — **10/10 passed, 0 crash**, no access violation, in 10.53s. The crash did not reproduce in isolation.

**Attempt 2** (full suite, backgrounded, polled in ~210s-capped loops across 4 turns): completed cleanly, no crash, no failures:

```
705 passed, 48 warnings in 637.49s (0:10:37)
```

`grep -c "FAILED|ERROR"` on the full log: 0. `grep -oE "[0-9]+ (passed|failed|error)"`: `705 passed` (no `failed`/`error` token present at all).

**Classification:** the attempt-1 access violation is a **flaky, non-deterministic native crash in this Windows/scipy environment** (`scipy.integrate._ivp`'s compiled RK path, triggered somewhere inside `sim/dynamics.py::_cross_y`/`derivatives` during `solve_ivp`), **not a Step 117 defect**: neither `sim/dynamics.py` nor `tests/test_plotting.py` appears anywhere in this step's 13-file diff (confirmed in §1 above), the crash did not reproduce when the same test file was run in isolation, and it did not recur on a second full-suite run. Recommend the orchestrator add this to CLAUDE.md's environment-pitfalls list (Windows native access-violation crash possible but rare/flaky in `scipy.integrate.solve_ivp` under the full suite; retry the full run if it recurs) — not a finding against this developer's diff.

**Verdict: PASS.** 705/705, matching the claimed baseline exactly, confirmed on a clean, uninterrupted run.

## 7. Overall verdict

All seven independent-verification points from the task are satisfied:

1. File list (13 files) — exact match, confirmed by `git diff --stat` run myself.
2. Diff hunks (all 13 files read in full, not just the minimum sample) — every RHS/arithmetic expression/numeric literal byte-for-byte identical to the ticket's "replace X with Y" blocks; zero drift.
3. §117.10's four `rg` acceptance checks — independently run and classified; all hits match the ticket's STAYS list; zero missed renames; zero accidental I/O-boundary renames.
4. `dev/docs/latex/` — zero edits, confirmed.
5. `configs/`, `apps/`, `data/` — zero edits, confirmed.
6. Full suite — 705/705 passed, 0 failed, 0 error, confirmed on a clean run (after triaging an unrelated, non-reproducible native-crash flake on the first attempt).
7. `sim/params.py` — exactly the one `l_p` docstring line from §117.8, nothing else touched.

**No defects found.** Step 117 (D-126) is accepted as implemented: a pure identifier/docstring/comment rename, zero numeric pin movement, zero LaTeX edits, I/O boundary (`Params.aero.C_m`/`C_m_alpha`/`c_mq`/`cm_convention`, CSV headers) correctly left untouched.



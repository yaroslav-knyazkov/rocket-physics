# QA Report — Step 119 (Phase 2.17) — B36 fix: `_table_coeffs` scalar `c_mq` fallback cm_convention

## Кратко (RU)

См. раздел "Кратко (RU)" в конце документа (блок "Overall verdict") для полного резюме.

---

## Test area 1: diff scope (`git diff --stat`)

```
sim/aero.py           | 21 +++++++++++++++++++++
tests/test_aero_v2.py | 29 +++++++++++++++++++++++++++++
2 files changed, 50 insertions(+)
```

Confirmed: exactly 2 tracked files changed, matching the developer's self-report. No other tracked
file (`sim/forces.py`, `sim/params.py`, `dev/docs/latex/**`, any config) shows a diff
(`git diff --stat -- sim/forces.py sim/params.py dev/docs/latex` returns empty). The untracked
top-level `docs/` dir and `dev/docs/task-119-b36-fix.md`/`task-117-cm-rename.md` predate this
diff (visible in the pre-existing `git status` at session start) and are not part of this change.

**PASS.**

---

## Test area 2: diff content vs ticket §119.5/§119.6

Read both diffs in full (`git diff -- sim/aero.py`, `git diff -- tests/test_aero_v2.py`) and the
surrounding code (`_AeroTable`, `_load_table`/`_plane`, `_at_fb`, `_table_coeffs`).

- `_AeroTable.cm_convention: str = "code"` new trailing field — matches ticket §119.5 verbatim
  (field placement, default, comment).
- `_load_table`'s `_plane()` closure now passes `cm_convention=cm_convention` (the already-parsed
  enclosing local variable, line ~246) into every `_AeroTable(...)` construction — matches ticket
  exactly, no new parsing introduced.
- `_table_coeffs`'s fallback branch: `elif table.cm_convention == "standard": C_mq_code = -p.aero.c_mq`
  else unflipped — matches ticket's exact code (§119.5), comment included, inserted as the ticket
  specifies (between the "column present" branch and the final unconditional `else`). The existing
  `if table.C_mq_code is not None:` branch (table *has* a c_mq column) is untouched — fallback-only
  change, as intended.
- `_table_coeffs`'s docstring: new paragraph appended (Step 119/D-128/B36), the Step-44 paragraph
  preserved verbatim above it — matches ticket (append, not replace).
- New test `test_table_cm_convention_flips_scalar_c_mq_fallback` — the ticket's own §119.6 flagged
  the literal call-shape snippet (`_mass_params(n_std, aero=Aero(...))`) as needing adjustment
  ("verify against the live helper at implementation time, do not copy-paste blind"). The developer's
  deviation is sound, not a shortcut: `_mass_params(table, **kw)` (tests/test_aero_v2.py:51-57)
  already hardcodes `aero=Aero(model="table", ...)` positionally inside its own body and forwards
  `**kw` straight into `Params(**kw)` — passing `aero=Aero(...)` through `**kw` on top of that would
  be a duplicate-keyword `TypeError`, not merely redundant. The developer's local `_params(table)`
  helper instead builds `Params(...)` directly, mirroring `_short_flight_alpha`'s own established
  shape in this same file (`Weight(m=2.0, I=0.1)`, `Lengths(l2=0.4, l_g=0.9)`, no mass-model fields —
  consistent with every other `aero.coefficients`-only test here, e.g. `_short_flight_alpha`). The
  test itself exercises exactly the three cases the ticket specifies: `"standard"` header → flipped
  (`-5.0`), `"code"` header → unflipped (`5.0`), no header → default `"code"` → unflipped (`5.0`).
  Ran standalone (see below) and passes. Confirmed this is a faithful, correct exercise of the fix,
  not a weakened one.

**PASS** — implementation matches ticket intent; the one deviation from the literal snippet is
exactly the kind of necessary adjustment the ticket itself anticipated and flagged, and the
replacement is at least as rigorous as the original would have been.

---

## Test area 3: independent recomputation of `test_example_v2_flies_stable`

Ran `python -m pytest tests/test_aero_v2.py -q` — all 18 tests in the file pass (includes the new
test and the existing `test_example_v2_flies_stable`).

Independently recomputed (own standalone script, not copy-pasted from the ticket's repro, built
fresh from `_short_flight_alpha`'s real current body in the test file):

```
a_stable  = 0.008758245042802728   (exact match to developer's self-reported value)
a_flipped = 0.013205733070822344   (matches ticket's predicted baseline 0.013206 bit-for-bit in
                                     the first 6 significant digits -- i.e. UNCHANGED from the
                                     pre-fix number, confirming the "code"-labelled copy's own
                                     fallback is correctly NOT flipped by this fix)
ratio     = 0.6632153622848699     (matches ticket's §119.3 predicted "0.6632" exactly)
threshold (0.8 * a_flipped) = 0.010564586456657876
assert a_stable < 0.8*a_flipped -> True, comfortable margin (0.00876 vs 0.01056, ~17% headroom)
```

Also directly inspected the loaded table: `aero._load_table('example_v2.csv').cm_convention ==
"standard"` and `.C_mq_code is None` (no column) — confirms this call genuinely exercises the new
fallback branch, not the column-present branch.

This confirms the asymmetry the fix is supposed to introduce: the `"standard"`-declaring table's
scalar fallback is flipped (`a_stable` moved from the pre-fix 0.008803 to 0.008758, per ticket
§119.3's table), while the `"code"`-declaring flipped copy's fallback is untouched (`a_flipped`
identical to its pre-fix value). The margin against the test's `0.8` threshold stayed comfortable
(0.6632 vs 0.8), consistent with the ticket's computed, not estimated, pin-impact claim.

**PASS.**

---

## Test area 4: independent repo-wide grep — any other live `c_mq` + `"table"` + missing-column case?

Re-grepped `c_mq` across `tests/`, `configs/`, `apps/` independently (not trusting the ticket's
table at face value):

| Call site | model | table has `c_mq` column? | table's declared convention | Fallback exercised? | Sign-sensitive (nonzero `c_mq` AND flip changes the value)? |
|---|---|---|---|---|---|
| `test_dynamics.py` (`aero_common`, model="linearized") | linearized | n/a | n/a | No (not table model) | No |
| `test_control.py:256` | constant | n/a | n/a | No | No |
| `test_aero.py:363` (`test_C_mq_no_table_returns_constant...`) | default (not "table") | n/a | n/a | No | No |
| `test_aero.py:380` (`test_C_mq_table_without_column_falls_back...`, `example.csv`, `c_mq=7.0`) | table | No (fallback exercised) | none declared -> default `"code"` (confirmed: `example.csv` header has no `cm_convention` line) | Yes | No (c_mq nonzero but `"code"` -> unflipped either way) |
| `test_aero.py:414` (`test_c_mq_table.csv`, `c_mq=-999.0`) | table | **Yes** (fixture declares a `c_mq` column) | n/a | No (column branch, not fallback) | No |
| `test_aero_v2.py:_legacy_params` (`example.csv`, `c_mq=0.5`) | table | No | default `"code"` | Yes | No |
| `test_aero_v2.py:_short_flight_alpha`/`test_example_v2_flies_stable` (`example_v2.csv`, `c_mq=0.5`) | table | No | `"standard"` | Yes | **YES — the one live case** |
| `test_aero_v2.py:_v2_example_params` | table | No | `"standard"` | — | dead helper, zero call sites (confirmed by grep) |
| `test_report.py` (3 sites, `example_v2.csv`, `c_mq` not set -> `0.0`) | table | No | `"standard"` | Yes | No (`c_mq=0.0`, `-0.0==0.0`) |
| `test_aero_oob.py`, `test_scenario_sweep.py` (`example_v2.csv`, `c_mq` not set) | table | No | `"standard"` | Yes | No (`c_mq=0.0`) |
| `test_step114_review_fixes.py` (table has its own `c_mq` column, line 41 header) | table | **Yes** | n/a | No (column branch) | No |
| `test_forces.py` (`aero_common`, model="linearized" throughout) | linearized | n/a | n/a | No | No |
| `configs/rockets/_TEMPLATE_rocket.py` | template comment/doc row only, no live Params construction | — | — | No | No |
| `apps/motor_selection/motors.py:24` | docstring parameter list only | — | — | No | No |

Independently confirmed: `data/aero/` contains exactly two `.csv` files (`example.csv`,
`example_v2.csv`); `example.csv` has no `# cm_convention:` header line (checked directly). The only
call site combining a nonzero `c_mq`, a `"table"` model, a table lacking a `c_mq` column, AND a
table-declared convention other than the default `"code"` is `test_example_v2_flies_stable`
(via `_short_flight_alpha`). Matches the ticket's §119.4 claim exactly — independently reproduced,
not just trusted.

**PASS.**

---

## Test area 5: `_at_fb`'s blend/`_replace()` and the new field

Read `_at_fb` (sim/aero.py:386-413) directly. Its `_mix()` helper and the `lo._replace(...)` call at
the end list `C_A`, `C_N`, `C_m_code`, `l1`, `C_mq_code`, `l_p` explicitly — `cm_convention` is
**not** in that list, so `_replace()` leaves it at `lo`'s (the lower bracketing plane's) value.
Confirmed this is correct and not an oversight: every plane returned by `_load_table`'s `_plane()`
closure is built from the *same* enclosing `cm_convention` local variable (parsed once per file,
before the `fb_grid`/`planes` loop even starts) — so `lo.cm_convention == hi.cm_convention` always,
for any two planes of the same loaded table. There is no way for a blended/`fb`-interpolated
plane's `cm_convention` to differ from either bracketing plane's. Verified by reading `_load_table`
top-to-bottom: `cm_convention` is a single local, assigned once (default `"code"`, possibly
overwritten once by the header parse, line ~231-253), consumed by every `_plane()` call it closes
over, including the `tuple(_plane(fb_col == f) for f in fb_grid)` comprehension that builds every
`f_b` plane from the same file.

**PASS.**

---

## Test area 6: no out-of-scope edits

`git diff --stat -- sim/forces.py sim/params.py dev/docs/latex` returns empty (no changes).
Read the diff of `sim/aero.py` in full (Test area 2): no change to `_constant_coeffs`,
`_linearized_coeffs`, `_load_table`'s existing `C_m_col`/`C_mq_col` flip logic (lines ~285-307,
unchanged), `Aero.C_x180` (not referenced anywhere in the diff), `_cm_to_code`, or any other
function. The only functions touched are `_AeroTable` (new field), `_load_table`'s `_plane()`
closure (one new kwarg), and `_table_coeffs` (fallback branch + docstring).

**PASS.**

---

## Test area 7: full suite

Launched `python -m pytest -q` redirected to `qa_full_suite_step119.log`, via plain
`run_in_background: true` (no manual `&`), per the backgrounding-hazard warning in this task.
Polled across three turns (capped ~235s waits each, checking the real Windows PID 11732 via
`tasklist`, not just the first launch notification) until the process actually exited.

Final log tail:
```
[32m706 passed[0m, [33m48 warnings[0m in 579.23s (0:09:39)
```
Exit code 0. Grepped the full log for `passed|failed|error` — exactly one summary line, `706
passed`, no `failed`/`error` anywhere. Matches the developer's self-report exactly: baseline 705 +
1 new test (`test_table_cm_convention_flips_scalar_c_mq_fallback`) = 706/706, 0 failed, 0 errors.
All 48 warnings are pre-existing `MachRangeWarning`/`AeroRangeWarning` instances unrelated to this
change (Mach-independent "constant" model above its credible range, table alpha-range-exceeded
warnings in `test_report.py`/`test_scenario_sweep.py`) — not new.

**PASS.**

---

## Overall verdict

All seven independent verification items confirmed:

1. Diff scope: exactly 2 tracked files (`sim/aero.py`, `tests/test_aero_v2.py`), +50/-0 lines. PASS.
2. Diff content matches ticket §119.5 (`_AeroTable.cm_convention` field, `_plane()` threading,
   `_table_coeffs` fallback + docstring) verbatim; the test's one deviation from the ticket's
   literal snippet (`_params(table)` local helper instead of `_mass_params(n_std, aero=...)`) is a
   necessary, correctly-reasoned fix for a duplicate-keyword collision the ticket itself flagged as
   needing adjustment — not a shortcut. The three required cases (standard->flipped,
   code->unflipped, no-header-default->unflipped) are all faithfully exercised. PASS.
3. Independently recomputed `a_stable = 0.008758245042802728` (exact match to developer's reported
   value), `a_flipped = 0.013205733070822344` (unchanged from pre-fix, confirming the "code"-labelled
   copy is correctly NOT flipped), ratio `0.6632` against threshold `0.8` — comfortable margin,
   `test_example_v2_flies_stable` passes. PASS.
4. Independently re-grepped the whole repo for `c_mq` + `"table"` model + missing column + nonzero
   `c_mq` + non-default declared convention: `test_example_v2_flies_stable` is confirmed the only
   live, sign-sensitive case. Every other call site is either not a `"table"` model, has its own
   `c_mq` column (fallback not exercised), has `c_mq=0.0` (flip is a no-op), or uses a table that
   declares no convention (defaults to `"code"`, unflipped either way). PASS.
5. `_at_fb`'s `_mix`/`_replace()` does not list `cm_convention`, so it is left at the lower
   bracketing plane's value — correct and safe because every plane of a multi-`f_b` table is built
   from the same single per-file `cm_convention` local variable in `_load_table`, confirmed by
   reading the code directly (no claim taken on trust). PASS.
6. No edits outside the intended scope: `git diff --stat` for `sim/forces.py`, `sim/params.py`,
   `dev/docs/latex/**` all empty; `_constant_coeffs`, `_linearized_coeffs`, the existing
   `C_m_col`/`C_mq_col` load-time flip logic, and `Aero.C_x180` are untouched in the diff. PASS.
7. Full suite re-run from scratch (background, polled to genuine completion, not a false-positive
   notification): **706 passed, 0 failed, 0 errors**, exit code 0 — exactly baseline (705) + 1 new
   test. PASS.

**No defects found.** The implementation is a faithful, correctly-reasoned realization of the
ticket's recommended Option B, independently verified rather than trusted from the developer's
self-report at every one of the seven checkpoints the task specified.

## Кратко (RU)

Независимая проверка Step 119 (D-128/B36): фикс `_table_coeffs`'s скалярного `c_mq` fallback для
table-модели, разворачиваемого по конвенции, заявленной самой таблицей (`_AeroTable.cm_convention`),
а не `Params.aero.cm_convention`. Диф строго в границах: 2 файла (`sim/aero.py`,
`tests/test_aero_v2.py`), +50/-0 строк, ничего больше не тронуто (`forces.py`, `params.py`, LaTeX —
пусто). Код соответствует тикету §119.5 построчно; отклонение нового теста от буквального сниппета
тикета (свой хелпер `_params(table)` вместо `_mass_params(..., aero=...)`) — обоснованное и
корректное (избегает `TypeError` на дублирующемся kwarg), не ослабляет тест, покрывает все три
случая (standard/code/default). Самостоятельно пересчитан `a_stable = 0.008758245042802728` —
точное совпадение с заявленным разработчиком числом; `a_flipped` не изменился, запас по порогу
`0.8` комфортный (0.6632). Самостоятельный grep по всему репозиторию подтвердил: это
действительно единственный живой знако-чувствительный кейс. `_at_fb`'s blend-логика корректно не
трогает новое поле (все планы одного файла делят одно значение). Полный прогон тестов с нуля,
дождались реального завершения процесса (не первого уведомления) — **706 passed, 0 failed**,
ровно базовая линия (705) + 1 новый тест. Дефектов не найдено.

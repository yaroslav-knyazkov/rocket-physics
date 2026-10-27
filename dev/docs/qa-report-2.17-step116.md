# QA Report — Step 116 (D-125, l_p relabel)

## Кратко (RU)

**Вердикт: PASS.** Независимо проверено Step 116 (D-125, релейбл `l_p`/`l_p_m` как станции приведения
момента, Option A). Ключевые проверки: `sim/dynamics.py` — нулевой дифф (подтверждено `git diff`);
единственный одобренный сдвиг пина (`test_static_margin_series_matches_cg_travel`) заменён
перекрёстной проверкой через `aero.C_m`/`aero.C_N`, не руками вписанным числом; исправленный §116.4
(знак `combined_slope <= 0` = устойчиво, `.max()` вместо `.min()`) независимо пересчитан с нуля (свой
скрипт, свой шаг дифференцирования, свой грид) для всех трёх тестов устойчивости — все три числа
совпали с заявленными в тикете по физическим причинам, не по совпадению фикстуры. Гейтинг на
`aero.uses_l_p(p)` и guard `_CZ_SLOPE_EPS` подтверждены и структурно, и эмпирически (drag-only таблица
даёт correction=0, формула совпадает со старой бит-в-бит). LaTeX-правки — ровно два одобренных места
в двух файлах, больше нигде в `dev/docs/latex/` изменений нет, обе `\autoref` метки существуют.
Полный прогон: **705 passed, 0 failed** (558.55s). Блокеров не найдено.

## Scope

Independent verification of Step 116 (D-125, l_p relabel) per `dev/docs/task-116-lp-relabel.md`, branch `feature/sim-paper-alignment`. Checklist per orchestrator task (items 1-7).

Changes are uncommitted on top of HEAD (`fac0a05`), working tree diffed directly against `HEAD` (`git diff HEAD -- <path>`), confirmed via `git diff --stat --cached` (empty) + `git status`.

---

## 1. `sim/dynamics.py` — zero diff

`git diff HEAD -- sim/dynamics.py` → empty (0 lines), `git status sim/dynamics.py` → "nothing to commit, working tree clean". **PASS.**

---

## 2. `sim/aero.py` / `sim/report.py` diffs — read in full

Read the full `git diff HEAD` for both files.

- `sim/aero.py`: exactly the §116.2 (`C_N` gains `fb=0.0`, now calls `_dispatch` instead of bypassing it) and §116.5/§116.9 wording-only edits (9 docstring/comment spots + `uses_l_p` limitation note). No arithmetic changed anywhere else in the file (`_resolve_arm`, `_cm_to_code`, `validate` bodies untouched, only prose). **PASS.**
- `sim/report.py`: exactly the §116.3 (`static_margin_cal` rewrite, gated on `aero.uses_l_p(p)`, `_CZ_SLOPE_EPS = 1e-9` guard) and §116.4 (new `combined_stability_slope_series` helper, `stability_check` rewritten to use `.max()` not `.min()`, sign `combined_slope <= 0` = stable, return key renamed `max_stability_slope`). Matches the corrected (post-bug-fix) ticket text verbatim, not the original buggy draft. **PASS.**

---

## 3. Pin replacement — `test_static_margin_series_matches_cg_travel`

`git diff HEAD -- tests/test_report.py`: the old hard literal `(1.18 - l_g0) / 0.1` is **not deleted** — it is kept as the base term, with a cross-check correction term (`dcm/dcz`) computed via `aero.C_m`/`aero.C_N` called at `flow0.alpha ± _CM_SLOPE_STEP` (imported from `sim.report`, same constant production code uses) subtracted from it. This is exactly the §116.7 patch (not a hand-typed new float). Confirmed `_CM_SLOPE_STEP` is imported at the top of the test file (`from sim.report import _CM_SLOPE_STEP, stability_check, static_margin_cal`) rather than the ticket's fallback `__import__` one-liner — ticket explicitly said either is fine. **PASS.**

---

## 4. Independent numeric recomputation of the three stability tests (item 3 of orchestrator checklist)

Wrote a standalone script (`verify_step116.py`, scratchpad) that does **not** import
`combined_stability_slope_series`/`stability_check` from `sim/report.py` — it re-derives the combined
criterion from scratch using only `sim.aero.C_m`/`C_N`/`coefficients` + `sim.flow.flow_state`, with its
own independent finite-difference step (`1e-4`, not the production `_CM_SLOPE_STEP`), and its own
400-point grid built from `result.t`/`result.events["ground"]` (not `sim.report._flight_grid`).

Results (independently computed, compared against the ticket's numeric claims in §116.4/§116.7a):

| Scenario | My combined.max() | Ticket's claim | Match |
|---|---|---|---|
| `test_stable_table_reports_no_warning` (`_params` default geometry, `l_d=0.8,l_p=1.3`) | -0.815021 | -0.815 | yes |
| `test_flipping_...`, NEW thinned fixture (`l_d=1.05,l_p=1.55`), `cm_convention: code` (wrong) | +0.035019 | ~+0.035 | yes |
| same thinned fixture, `cm_convention: standard` (correct) | -0.065019 | ~-0.065 | yes |
| OLD geometry (`l_d=0.8,l_p=1.3`) + `code` (wrong) — why the old fixture would now fail | -0.714983 | constant ~-0.715 | yes |
| `test_negative_geometric_margin_warns` (forward-CP, `l_d=1.6,l_p=1.7`) | +1.284984 early, exactly 0.0 at `t=2.0` (table-edge clamp) | +1.285 early / relaxes to 0.0 | yes |

For the forward-CP case also independently confirmed `combined.min() == 0.0` (the table-edge-clamp
artifact) vs `combined.max() == 1.284984` (the real destabilizing excursion) — i.e. independently
reproduced *why* `.min()` would have silently reported "stable" here while `.max()` correctly flags
instability. This is not re-trusting developer's numbers — every value above was recomputed from the
raw physics helpers with an independent script, independent step size, and independent grid.

Also independently recomputed `cm_slope.min()` for the two `code`/`standard` cases (+0.500/-0.500,
sign flips as expected from `_flipped_copy`'s header rewrite) confirming the existing
`assert out["min_cm_slope"] < 0.0` / `> 0.0` assertions are driven by genuinely different physical
quantities, not coincidence.

**Conclusion: the sign convention (`combined_slope <= 0` = stable) and the `.max()` extremum choice
produce the correct `stable`/`unstable` outcome for all three tests, for physically correct reasons —
not a coincidence of the specific test fixtures. PASS.**

---

## 5. Gating on `aero.uses_l_p(p)` + `_CZ_SLOPE_EPS` guard (item 4 of checklist)

- Code inspection (`sim/report.py` diff, §2 above): `use_derived_cp = aero.uses_l_p(p)`; the
  `dcm`/`dcz`/correction block is only entered `if use_derived_cp`; for `not uses_l_p(p)` (legacy
  `Lengths.l1` configs), `correction` stays `0.0` unconditionally, so `margin[i] = arm / p.aero.d_ref`
  — bit-for-bit the pre-Step-116 formula. No legacy-arm config in the current suite exercises
  `static_margin_cal` directly (noted in the ticket too), but the gating is structurally unconditional
  on the `if` — not a borderline case needing a numeric check.
- `tests/test_aero_fb.py::test_static_margin_shifts_with_fb_and_diagnostic_shows_it` uses a drag-only
  synthetic table (`_flight_rows`: `C_N = C_m = 0.0` identically at every grid node, confirmed by
  reading the fixture source) with an `l_p_m` column (`uses_l_p(p) is True`). Central-difference `dcz`
  off a table with `C_N ≡ 0` is exactly `0.0` (not an epsilon-adjacent value) at every `(alpha, M)`, so
  `_CZ_SLOPE_EPS`'s `abs(dcz) > 1e-9` test is `False`, `correction` stays `0.0`, and the formula reduces
  to the old `arm/d_ref` bit-for-bit. Confirmed **empirically** too: ran this exact test (targeted run
  below) and it passed, i.e. `drop == pytest.approx(0.2/_D_REF, rel=0.05)` held — the "Farha effect"
  drop is exactly the raw-arm drop, no spurious correction term appeared. **PASS.**

---

## 6. LaTeX diffs — exactly the two approved spots

- `git diff HEAD -- dev/docs/latex/sections-ai/rocket-2d.tex`: single hunk, lines 56-60 area, exactly
  the §116.8 Edit 1 text (verbatim match, including the `\emph{moment reference}` wording and the
  `\autoref{sec:analysis_stability}` reference).
- `git diff HEAD -- dev/docs/latex/sections-ai/analysis.tex`: single hunk, lines 129-138 area, exactly
  the §116.8 Edit 2 text (verbatim match, both equations, the `\autoref{sec:geometry}` reference, the
  degenerate-case closing sentence).
- `git status --porcelain dev/docs/latex/` → only these two files modified; `git diff HEAD --stat --
  dev/docs/latex/` → only these two files, no other hunks within them.
- Verified both referenced labels actually exist (not dangling `\autoref`s introduced by the edit):
  `sec:analysis_stability` defined at `analysis.tex:106` (`\subsection{Static stability}`), `sec:geometry`
  defined at `rocket-2d.tex:53` (`\subsection{Geometry}`) — both pre-existing, confirmed also present in
  the already-compiled `dev/docs/latex/main.aux` (`\newlabel{sec:geometry}{...}`,
  `\newlabel{sec:analysis_stability}{...}`).

**PASS — hard requirement satisfied: nothing else in either file, nothing else anywhere under
`dev/docs/latex/`, changed.**

---

## 7. `configs/rockets/_TEMPLATE_rocket.py` / `data/aero/example_v2.csv` doc changes

- `_TEMPLATE_rocket.py` lines 96/211 (table row + inline comment): "CoP station from the nose" →
  "moment reference station from the nose (x_ref)", wording matches §116.6 exactly in both spots.
- Line 62 (`Lengths.l1` doc row, "CoP to CoG distance (static-margin lever arm)") confirmed **untouched**
  — read it directly post-edit, unchanged, as required (legacy-arm wording out of scope).
- `data/aero/example_v2.csv` header comment: "the CoP is given as a station..." → "the moment reference
  station is given from the nose tip... (x_ref; C_m is taken about this station, the CP is a derived
  quantity)" — matches §116.6; the rest of the comment block (arm formula, `l1_m + 0.9 m` note) is
  unchanged. No mention of "CP"/"CoP" as an *input* remains in either file's changed lines; wording reads
  correctly and does not contradict the new derived-CP code in `sim/report.py`.

**PASS.**

---

## Targeted test run

`python -m pytest tests/test_report.py tests/test_aero_fb.py tests/test_aero_v2.py tests/test_scenario_sweep.py -q`
→ **49 passed**, 6 warnings (all pre-existing `AeroRangeWarning`/`MachRangeWarning` advisories, not new).

---

## Full suite (independent run, background, `run_in_background`)

`python -m pytest -q` → **705 passed, 0 failed, 0 errors**, 48 warnings (all pre-existing
`AeroRangeWarning`/`MachRangeWarning` advisories from other modules, none new or related to Step 116),
`558.55s (0:09:18)`, exit code 0. Confirms independently of developer's claimed count — no regression
anywhere in the suite, including all trajectory/integration pins outside `sim/report.py`'s own
diagnostics (consistent with item 1's zero-diff finding on `sim/dynamics.py`).

---

## Items not independently re-verified in full depth (low risk, noted for completeness)

- `sim/aero.py:819-822` → `_dispatch` arity handling for `C_N`'s new `fb` param: confirmed by code
  reading (ticket §116.2, `_dispatch` already handles the constant/linearized vs table arity mismatch
  for `C_m`) and by the full suite passing (`tests/test_aero.py`'s existing 3-arg `C_N` call sites all
  green) — not separately unit-tested in isolation beyond that, but the full-suite pass covers it.
- `tests/test_scenario_sweep.py::test_works_with_v2_table_and_margin_series` and
  `apps/motor_selection/scenario_sweep.py::_margins`: confirmed via the targeted run (passed, no code
  change needed per ticket) and full-suite pass; did not separately hand-verify a numeric margin value
  from this path (relational/`isfinite` assertions only, per ticket §116.7, nothing to hand-check).

## Overall verdict: PASS

No defects found. All 7 checklist items independently confirmed. Zero pin movement outside the one
approved pin (`test_static_margin_series_matches_cg_travel`, replaced with a cross-check, not a
hand-typed literal, per D-129). Recommend proceeding with Step 116 commit/merge.

---

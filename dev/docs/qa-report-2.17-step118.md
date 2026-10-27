# QA Report — Step 118 (D-127): axial cos²-shaped hybrid outside the 85° plateau

See "## Кратко (RU)" and "## Overall verdict" near the end of this document for the summary.

---

## Scope

Independent verification of Step 118 (D-127): `sim/aero.py::axial_flow_factor` reshaped from
linear-in-cos(alpha) ramp to `clip(r*|r|, -1, 1)` outside the `|alpha|<=85°` plateau, with the
single test tolerance bump `3e-3 -> 6e-3` in `tests/test_aero.py`. Ground truth:
`dev/docs/task-118-axial-cos2-hybrid.md` (426 lines, read in full).

## 1. git diff --stat — files changed

`git diff --stat` (and `git status --porcelain`) confirm **exactly 2 tracked files changed**:
`sim/aero.py` (25 insertions, 7 deletions) and `tests/test_aero.py` (11 insertions, 3 deletions).
No LaTeX, no other test file, no config file touched. One pre-existing untracked directory
(`docs/`) and the two doc files I/the architect produced (`dev/docs/task-118-*.md`,
`dev/docs/qa-report-2.17-step118.md`) appear as `??` — unrelated noise, not part of this diff
(untracked, nothing to diff against HEAD). **PASS.**

Note: the conversation's opening `gitStatus` snapshot listed many more modified files
(`sim/control.py`, `sim/forces.py`, `sim/params.py`, `sim/report.py`, several `tests/test_*.py`)
— those are stale (predate this session's actual state, likely from Step 116/117 before they were
committed as `3577266`/`62733b1`). Current `git status` only shows the 2 files above as modified.

## 2. Byte-for-byte diff comparison against ticket §118.6 / §118.8

Read full unified diffs for both files and compared line-by-line against the ticket's exact
before/after code blocks.

- `sim/aero.py`: the `_COS_ALPHA0` comment insertion (4 new comment lines) matches §118.6's
  "after" block verbatim. The `axial_flow_factor` docstring + body replacement matches §118.6's
  "after" block verbatim, including the exact wording of the new docstring paragraph and the
  `r = float(np.cos(alpha)) / _COS_ALPHA0; return min(1.0, max(-1.0, r * abs(r)))` body. No other
  line in the file changed (diff shows only these two hunks, 25+/7-).
- `tests/test_aero.py`: the section-header comment reword matches §118.8 verbatim. The
  `test_axial_flow_factor_is_continuous_across_the_ramp` docstring insertion and the
  `3e-3 -> 6e-3` / `11.5/rad` -> `23/rad` comment change match §118.8 verbatim. The other two
  boundary tests (`test_axial_flow_factor_is_one_inside_85_deg_exactly`,
  `test_axial_flow_factor_zero_at_90_and_minus_one_beyond_95`) are untouched in the diff, as
  claimed.

**PASS** — both diffs are byte-for-byte identical to the ticket's claimed before/after blocks.

## 3. Independent recomputation of anchor points, slope, and tolerance

Ran an independent Python script (`numpy`/`math`, not trusting the ticket's numbers) reproducing
both the old and new `axial_flow_factor` formulas from first principles.

- **Plateau anchors** `{0,10,-30,80,85,-85}` deg: `new_f(alpha) == 1.0` exactly for all six — confirmed.
- **90 deg anchor:** `f(90deg) = 4.9359e-31`, `f(-90deg)` same — `abs(f) < 1e-12` holds by ~19 orders
  of magnitude of margin — confirmed.
- **Beyond-95 anchors** `{95,-95,120,180,-180}` deg: `new_f(alpha) == -1.0` exactly for all five —
  confirmed.
- **Slope doubling at the 85 deg edge:** a naive centered finite difference straddling the kink
  underestimates (averages the flat plateau side with the ramp side, ~5.72/rad for old) — redid it
  one-sided, just past the edge: old formula slope `-11.4301`/rad, new formula slope `-22.8597`/rad,
  ratio `1.99997`. Closed-form check: `dr/dalpha` at `alpha=85deg` is `-sin(85deg)/cos(85deg) =
  -11.43005`/rad exactly (= old formula's slope there, since `f=r` unclipped on that side); new
  formula's `d(r^2)/dalpha = 2r·dr/dalpha` with `r=1` at the edge gives exactly `2×` that,
  `-22.86010`/rad. **Ticket's "exactly double" claim confirmed analytically and numerically.**
- **Tolerance adequacy for 6e-3:** reran the test's own sampling loop (84°-96°, 1201 points, 0.01°
  step) against both formulas. Old formula's empirical max consecutive-sample delta: `0.0020025`
  (old test tolerance `3e-3` → margin `1.498×`). New formula's empirical max delta: `0.0039859`
  (matches the ticket's reported figure exactly) with new tolerance `6e-3` → margin `1.505×` —
  essentially the same safety margin as the original test had, neither accidentally loosened nor
  tightened. Theoretical per-step bounds (`slope × 0.01deg-in-rad`) are `0.0019949` (old) and
  `0.0039898` (new, exactly 2× old) — both close to the empirical sampled maxima, confirming the
  test samples near the true worst case. **PASS** — `6e-3` is an appropriately, not accidentally,
  scaled tolerance.

## 4. Independent grep for degree/alpha literals in the open interval (85°, 95°)

Ran my own regex (`\b8[6-9](\.\d+)?\b|\b9[1-4](\.\d+)?\b`, catching integer/decimal literals
86-89 and 91-94, i.e. the open interval minus the 85/90/95 anchors already covered) across
`tests/`, then read every hit:

- Step numbers in comments/docstrings (88, 91, 93, 94) — unrelated to alpha.
- `Re_n = 88,000` (`test_aero_oob.py`) — Reynolds number, unrelated.
- `sat_vapor_pressure(273.15) == 610.94` (`test_atmosphere.py`) — Pa, unrelated.
- `lat0_deg in (-60.0, 0.0, 45.0, 89.0)` (`test_dynamics.py:383`) — site latitude, not AoA.
- CSV sounding fixture columns (`94, 91, 89` humidity-like values, `test_fetch_sounding.py`) —
  unrelated data columns.
- `baseline_cda` multipliers `0.83`/`1.22` with results `1.37`/`1.93` (`test_weight_aero_tradeoff.py`)
  — unrelated magnitude numbers, not degrees.
- `Step 91 (D-78)` motor demo comment — unrelated.

None is an `alpha`/AoA literal. Also checked for radian-literal `alpha =` assignments
(`alpha\s*=\s*(math\.radians\(|np\.radians\(|1\.[4-6]\d*)`) across `tests/` — only three hits, all
in `test_aero.py`, all `math.radians(5.0)`/`math.radians(10.0)` (inside the plateau, unrelated to
this ticket's anchors). **PASS** — independent grep confirms the ticket's claim: no pinned literal
alpha value lands strictly inside `(85°, 95°)` outside this ticket's own three
`axial_flow_factor` tests.

## 5. `_jorgensen_extend` untouched

`git diff -- sim/aero.py` hunk headers are `@@ -121,7 +121,10 @@` and `@@ -158,13 +161,28 @@` —
both entirely within the `_COS_ALPHA0` comment / `axial_flow_factor` region (lines ~121-188). The
only occurrence of the word "Jorgensen" touched by either hunk is inside the *new docstring prose*
referencing Jorgensen's literal form for context (line ~179, informational text, not code); the
pre-existing `# Step 112 (D-120): large-alpha extension of the table model (Jorgensen).` comment
line is unchanged context. `_jorgensen_extend` itself (lines ~702-732, including the
`Cx_J = x0*c2 / -x180*c2` lines) is nowhere near either diff hunk. **PASS** — confirmed untouched.

## 6. `axial_flow_factor` remains a pure function of `alpha` alone; `C_x180` not threaded in

Current signature: `def axial_flow_factor(alpha: float) -> float:` (line 163) — single parameter,
unchanged. All call sites use the same one-argument call shape as before:
`sim/forces.py:243` (`A_brake *= aero.axial_flow_factor(flow.alpha)`), `sim/aero.py:193, 591, 641`
(constant/linearized coefficient helpers), `tests/test_forces.py:979`, and all of
`tests/test_aero.py`'s calls — none pass a second argument, none pass `C_x180`. Grepped
`C_x180` across `sim/aero.py`: it appears at line 179 only inside the new docstring's explanatory
prose (mentioning *why* it is deliberately not threaded in); its only code usages remain the
pre-existing, untouched validation check (line 564) and `_jorgensen_extend` (line 732), both
outside either diff hunk. **PASS** — `axial_flow_factor` stays a pure function of `alpha`; `C_x180`
was not newly introduced into it, per the ticket's §118.5 restriction.

## 7. Full suite re-run from scratch

Ran `python -m pytest tests/test_aero.py tests/test_forces.py -q` first (point-in-time, matches
the ticket's own scope): **48 passed**, matching the developer's self-report.

Then ran the full suite (`python -m pytest -q`) from scratch, backgrounded. Note on process
hygiene: the first launch used `cmd & echo "started pid $!"` inside a tool call already marked
`run_in_background: true` — this double-backgrounds the work: the tool's own background tracking
only followed the launcher shell (which exits almost immediately after starting `python ... &`),
not the detached `pytest` child. The "task completed, exit code 0" notification received shortly
after was for the launcher only, **not** for the actual test run — confirmed by checking the
`python` PID directly (`Get-Process -Id 23484`): still alive, climbing CPU time, log file only
~2.6 KB of progress dots, no final summary line yet. Re-polled correctly by checking the actual
`python` PID's liveness in a capped-230s loop (not by trusting the launcher's notification) until
the process genuinely exited.

**Result: `705 passed, 48 warnings in 568.84s (0:09:28)`.** Zero failures, zero errors. Matches
the ticket's claimed 705/705 post-Step-117 baseline exactly — no test outside
`tests/test_aero.py` was affected, no undiscovered pin moved. The 48 warnings are pre-existing,
unrelated `AeroRangeWarning`/`MachRangeWarning` instances from other scenarios (table-OOB range
warnings, Mach-independent-model warnings) — not new, not related to this change. **PASS.**

## Overall verdict

All seven verification items PASS:

1. Exactly 2 tracked files changed (`sim/aero.py`, `tests/test_aero.py`) — confirmed via
   `git diff --stat`/`git status`.
2. Both diffs byte-for-byte match the ticket's §118.6/§118.8 exact before/after blocks.
3. All anchor-point claims (`1.0` plateau, `~0` at 90°, `-1.0` beyond 95°) reproduced exactly by
   independent computation; slope-doubling at the 85° edge confirmed analytically
   (`-11.4301`/rad → `-22.8597`/rad, ratio `1.99997`) and the `6e-3` tolerance confirmed
   appropriately scaled (same ~1.5× margin as the original `3e-3`/old-formula pair).
4. Independent grep of `tests/` for degree/alpha literals in `(85°, 95°)` found none outside this
   ticket's own three tests.
5. `_jorgensen_extend` (lines ~702-732) confirmed untouched — neither diff hunk is anywhere near it.
6. `axial_flow_factor` confirmed to remain a pure function of `alpha` alone; `C_x180` not threaded
   into its signature or body, only mentioned in explanatory docstring prose.
7. Full suite re-run from scratch: **705 passed, 0 failed**, matching the claimed baseline exactly.

**STATUS: PASS.** No defects found. Step 118 (D-127) is accepted as implemented — ready for
developer/orchestrator to proceed to commit.

## Кратко (RU)

Независимая проверка Step 118 (D-127, hybrid cos²-форма `axial_flow_factor` за пределами плато
`|alpha|<=85°`) пройдена полностью, без замечаний. Изменено ровно 2 файла (`sim/aero.py`,
`tests/test_aero.py`), оба диффа побайтово совпадают с тикетом §118.6/§118.8. Все заявленные
якорные точки (1.0 на плато, ~0 на 90°, -1.0 за 95°) пересчитаны самостоятельно и подтверждены
точно; удвоение наклона на границе 85° подтверждено аналитически (ratio 1.99997); допуск теста
`6e-3` — обоснованно смасштабирован, не случайно ослаблен/зажат. Собственный grep по `tests/` не
нашёл пинов альфа в открытом интервале (85°,95°) вне трёх тестов этого тикета. `_jorgensen_extend`
не тронут. `axial_flow_factor` остаётся чистой функцией от `alpha`, `C_x180` не протащен в сигнатуру.
Полный прогон с нуля (не доверяя уведомлению фона — оно пришло для скрипта-лаунчера, а не для
самого pytest; дождался реального завершения процесса) дал **705 passed, 0 failed** — совпадает с
заявленным базлайном. Вердикт: **PASS**, дефектов не найдено, степ принимается.

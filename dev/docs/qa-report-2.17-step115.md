# QA report Phase 2.17 Step 115 (conventions-audit safe fixes)

## Кратко (RU)

- Вердикт: **PASS**, без замечаний. Блокеров, major и minor дефектов нет.
- Все 5 пунктов Step 115 (B42->B35 коммент; пин `_ETA_LAM`/`_ETA_VAL` против research-заметки, закрывает QA-9; флип скаляра `c_mq` под `cm_convention="standard"`; устойчивость RASP-парсера мотора — многословный manufacturer + `ValueError` вместо `IndexError`; doc-only уточнения в `flow.py`/`gravity.py`/`motor_file.py`) проверены вручную против кода и против таблицы §14 аудита — каждый пункт действительно "no pin movement, no LaTeX, no user-decision fork", как и заявлено.
- Независимо перепроверена заявка "bit-for-bit safe" для пункта 3 (скаляр `c_mq`): собственный grep по `configs/`/`data/`/`tests/` подтверждает, что ни один существующий тест/конфиг не комбинирует `cm_convention="standard"` с ненулевым `c_mq` на пути `model="constant"/"linearized"` (единственная похожая комбинация — `example_v2.csv`, но она идёт через отдельный, нетронутый путь table-модели). Зафиксирована как примечание, не дефект: формулировка разработчика "no existing config combining..." чуть неточна (есть использование через table-модель), но не влияет на безопасность именно этого диффа.
- Тест `test_eta_table_matches_research_note` проверен на нецикличность: его литералы сверены вручную с `jorgensen-params-findings.md` (строки 16/18) — это реальная независимая перепроверка кода, а не эхо кода самого в себя. Docstring честно заявляет 10-из-12 точек покрытия.
- Независимый перезапуск: точечные тесты 249/249 passed; полный прогон 673 passed, 0 failed, 47 pre-existing warnings (538.59 с) — совпадает с заявкой разработчика, пины нигде не сдвинулись.

## Scope and method

Step 115 implements 5 independent "safe fix" items from the read-only conventions-industry-standard audit (`dev/docs/conventions-industry-standard-analysis.md` §14 table), each explicitly flagged by that audit as requiring no numeric-pin movement, no LaTeX edits, and no user-decision fork. Diff touches 9 files, 157 insertions / 9 deletions:

```
configs/rockets/_TEMPLATE_rocket.py |  2 +-
sim/aero.py                         |  6 ++---
sim/flow.py                         | 10 ++++++-
sim/gravity.py                      |  9 +++++++
sim/motor_file.py                   | 24 +++++++++++++++--
sim/params.py                       |  6 +++--
tests/test_aero_oob.py              | 26 ++++++++++++++++++
tests/test_aero_v2.py               | 29 ++++++++++++++++++++
tests/test_motor_file.py            | 54 +++++++++++++++++++++++++++++++++++++
9 files changed, 157 insertions(+), 9 deletions(-)
```

Method: read the full diff, cross-check each of the 5 items against the audit's §14 claims, independently re-derive the "bit-for-bit safe" claim for item 3 (grep configs/tests/data myself), re-run targeted test files, then the full suite in background, and diff pinned numeric values before/after where applicable.

## Item 1 (§12.6) -- `sim/aero.py` comment B42 -> B35

PASS. `git diff -- sim/aero.py` shows only one hunk for this item: a single comment-line text change, `grep -n "B42" sim/aero.py` returns nothing (exit code 1, no matches). No code line touched in this hunk. No behavior change possible.

## Item 2 (§9.1(b)) -- `tests/test_aero_oob.py::test_eta_table_matches_research_note`

PASS. Verified non-circularity directly: the test's local literals `lam_note_subset`/`eta_note_subset` were cross-checked by hand against `dev/docs/latex/research/jorgensen-params-findings.md` line 16/18 (the full 12-point table: `L/d = [2,4,6,8,10,12,15,20,25,30,35,40]`, `eta = [0.577,0.607,0.643,0.668,0.685,0.701,0.724,0.753,0.775,0.795,0.805,0.815]`). The code's actual `sim/aero.py::_ETA_LAM`/`_ETA_VAL` (lines 136-137) omit exactly the L/d=25 (0.775) and L/d=35 (0.805) points -- matching what the test's docstring claims ("10-of-12-point subset"), and matching the test's own literals. So the test is a real independent re-transcription compared against the code, not the code's arrays echoed back at themselves -- it would catch an accidental edit to `_ETA_LAM`/`_ETA_VAL`.

The Fig. 6 cross-check (`eta_10 ~= 0.68`, `eta_12 ~= 0.70`, `abs=0.01`) matches the research note's own line 22 verbatim ("about 0.68 and 0.70 ... matches the table (0.685/0.701)").

Docstring honesty: confirmed accurate -- it explicitly states the 10-of-12 subset, names both omitted points and their values, and does not claim full coverage of the research note's transcription.

## Item 3 (§1.3) -- scalar `c_mq` now flipped by `cm_convention="standard"` in `_constant_coeffs`/`_linearized_coeffs`

PASS, with one nuance flagged (not a defect, a precision note on the developer's claim).

Code: confirmed both `_constant_coeffs` (line ~568) and `_linearized_coeffs` (line ~619) now wrap the scalar in `_cm_to_code(p.aero.c_mq, p)`, matching the existing `C_m=_cm_to_code(p.aero.C_m, p)` pattern already used for the static moment. New test `tests/test_aero_v2.py::test_constant_model_cm_convention_flips_scalar_c_mq` exercises both `cm_convention="code"` (c_mq passes through unflipped) and `="standard"` (flipped) against the same `c_mq=-5.0` input, on the `model="constant"` path -- a real before/after discriminator, not a tautology.

Independent re-derivation of the "bit-for-bit safe" claim (own grep, not trusted from the report):
- `grep -rn "cm_convention" configs/ data/` -> only `configs/rockets/_TEMPLATE_rocket.py` (doc-comment text) and `data/aero/example_v2.csv` (`# cm_convention: standard`, a **table** model file, not constant/linearized).
- `grep -rn "c_mq" configs/ data/ tests/` -> every existing (pre-Step-115) use of `cm_convention="standard"` together with a nonzero `c_mq` is confined to the **table model** path (`example_v2.csv` + `tests/test_aero_v2.py::_v2_example_params`/`_short_flight_alpha` set `c_mq=0.5`, consumed via `_table_coeffs`'s scalar-fallback line `C_mq = p.aero.c_mq` at `sim/aero.py` ~line 662 -- a *different*, untouched function). No pre-existing config/test combines `cm_convention="standard"` with a nonzero `c_mq` on the `model="constant"`/`"linearized"` path that this diff actually modifies.
- Precision note: the developer's claim as stated in the handoff ("no existing config combining cm_convention=standard with a nonzero scalar c_mq") is not quite exact -- `example_v2.csv` + `c_mq=0.5` *is* such a combination, it's just routed through the table model's own (separate, unmodified) fallback, so it is unaffected by this diff. Confirmed the full-suite run below shows zero pin movement for `test_example_v2_flies_stable` and the other `example_v2`-table tests, consistent with that function being untouched. Flagging only so a future reader of the audit doesn't over-read "no existing config" as "no existing use of the combination anywhere in the codebase" -- it should read "...on the constant/linearized path touched here."

Doc comments: `sim/params.py::Aero.c_mq` comment rewritten to state the scalar IS now flipped (matches new behavior); `configs/rockets/_TEMPLATE_rocket.py` table row for `c_mq` updated the same way (`NOT flipped` -> `flipped ... same as C_m`). Both confirmed updated, no longer contradicting the code.

## Item 4 (§6) -- `sim/motor_file.py::_read_rasp` robustness

PASS, all three sub-behaviors independently exercised, not just "doesn't crash":
- (a) multi-word manufacturer: `test_multi_word_manufacturer_parses_in_full` feeds a header ending in `Cesaroni Technology Incorporated` (3 tokens past field 6) and asserts `rec.manufacturer == "Cesaroni Technology Incorporated"` -- the full joined string, not a truncated token. Code change confirmed: `tokens[6]` -> `" ".join(tokens[6:])`.
- (b) short header -> `ValueError`: `test_short_header_raises_value_error_not_index_error` feeds a 6-token header (`TestD 29.0 100.0 4-7-10 0.05 0.10`, no manufacturer field) and asserts the raised type is `ValueError` (not `IndexError`) and that both the filename and `"TestD"` (the offending content) appear in the message. Read the actual f-string (`sim/motor_file.py` ~line 204-209): message is `f"motor file '{filename}': header row {stripped!r} needs 7 tokens (...), got {len(tokens)}"` -- genuinely names the file and quotes the exact offending line, not a generic message.
- (c) short data row -> `ValueError`: `test_short_data_row_raises_value_error_not_index_error` feeds a 1-token data row (`0.0`) and asserts both filename and `"0.0"` appear in the message. Message f-string confirmed analogous and informative (`data row {stripped!r} needs at least 2 tokens...`).
- Confirmed `filename` in the error message is the bare filename argument passed to `_read_rasp`/`records` (not a resolved absolute path via `_motors_path`), so the `assert name in message` checks in both new tests are correctly testing what they claim, not passing by accident on a path substring.

## Item 5 -- doc-only clarifications (`sim/flow.py`, `sim/gravity.py`, `sim/motor_file.py` kg/g comment)

PASS. `git diff -- sim/flow.py sim/gravity.py` shows only docstring/comment line additions in both files for this item -- no executable line touched (confirmed by reading the actual diff hunks, not just file-level stat). The `sim/motor_file.py` kg-vs-grams comment (item 5's third file) is part of the same diff hunk already reviewed in item 4's section (the `MotorRecord` dataclass comment block above `diameter`/`length`/`delays`) -- comment-only there too, no code line changed in that hunk.

## Targeted test re-run

Independently re-ran (not trusting the developer's claimed numbers) the full module list named in the handoff plus `test_control.py`/`test_dynamics.py`/`test_forces.py` (consumers of `c_mq`/`C_mq`, to catch any collateral pin movement from item 3):

```
python -m pytest -q tests/test_aero.py tests/test_aero_fb.py tests/test_aero_oob.py tests/test_aero_v2.py \
  tests/test_motor_file.py tests/test_flow.py tests/test_gravity.py tests/test_step114_review_fixes.py \
  tests/test_control.py tests/test_dynamics.py tests/test_forces.py
```

Result: **249 passed, 11 warnings in 169.17s**. All 11 warnings are pre-existing `MachRangeWarning` (peak Mach > 0.8 with a Mach-independent `"constant"` aero model) from `test_dynamics.py` -- unrelated to Step 115, present on `develop` before this branch too (not introduced by this diff). Zero failures, zero errors.

## Full-suite re-run

`python -m pytest -q` (backgrounded, polled under the 240s-per-call cap): **673 passed, 0 failed, 47 warnings in 538.59s (0:08:58)**. Matches the developer's claimed 673/0 exactly.

All 47 warnings are pre-existing `MachRangeWarning` (Mach-independent `"constant"` aero model used above its credible Mach-0.8 range -- a long-standing diagnostic in `test_integrate.py`, `test_motor_selection.py`, `test_plotting.py`, `test_scenario_sweep.py`, `test_weight_aero_tradeoff.py`) and `AeroRangeWarning` (table `alpha` range exceeded, `test_report.py`/`test_scenario_sweep.py`, referencing the known `dev/docs/diagnosis-rk45-v2-table.md` issue). None reference `sim/aero.py`'s `_cm_to_code`/`c_mq` change, `sim/motor_file.py`'s new `ValueError` paths, or the new `_ETA_LAM`/`_ETA_VAL` pin test -- confirmed by reading every warning line in the captured output, not just the summary count.

Pin-movement check across the whole suite (not just the touched files): **zero failures across 673 tests is itself the proof** -- every pin-sensitive test (`np.array_equal`/`pytest.approx` against a hardcoded expected value) in the suite still passes against its pre-existing expected value; a moved pin would show up as a failure unless the test's own expected value was also edited, and `git diff --stat` confirms the only test-file edits in this diff are pure insertions (new test functions) in `tests/test_aero_oob.py`, `tests/test_aero_v2.py`, `tests/test_motor_file.py` -- independently confirmed by comparing function counts against `git show HEAD:<file>` (test_aero_oob.py 20->21, test_aero_v2.py 16->17, test_motor_file.py 13->16 -- exactly +1/+1/+3, nothing removed or renamed). No existing assertion in any test file was touched.

## Additional independent cross-checks (beyond the per-item checklist)

- **Item 1 B42->B35 cross-reference nuance**: `dev/docs/architecture-35-paper-alignment.md` line 664 (an older Phase-2.17 planning snapshot, still tracked in this branch) lists a *draft* backlog numbering plan where "B35" was provisionally pencilled in for "first-order actuator/servo model" -- a different topic than the transonic-C_dn item `sim/aero.py` now cites as B35. This is explained by the task framing already given to QA (tracker stays on `develop`; this branch's docs are a stale planning snapshot, not the final registration order) -- not treated as a defect, flagging only for the record in case a future reader of this branch's docs is confused by the same mismatch.
- **Item 3 whole-repo grep for `cm_convention`+`c_mq` combinations**: re-checked every file where `cm_convention` appears (16 files via repo-wide grep) beyond the ones already discussed -- `tests/test_qa_phase217_m1.py`, `tests/test_report.py`, `tests/test_scenario_sweep.py` all exercise the **table** model's header-declared `cm_convention` (flipping a table's `C_m`/`c_mq` *column*), never the `Aero.c_mq` scalar on `model="constant"`/`"linearized"`. No additional combination found beyond the one already noted (`example_v2.csv`, table model, out of this diff's scope).
- **Item 4 caching safety**: `sim.motor_file.records`/`load` are both `functools.lru_cache`-wrapped; confirmed this does not mask or stale-cache the new `ValueError` paths (`lru_cache` does not cache a raised exception, so a fixed-up retry re-executes cleanly) and does not leak state between the three new tests (each uses a distinct filename).
- **New tests run standalone**: `pytest -q tests/test_aero_oob.py::test_eta_table_matches_research_note tests/test_aero_v2.py::test_constant_model_cm_convention_flips_scalar_c_mq tests/test_motor_file.py::test_multi_word_manufacturer_parses_in_full tests/test_motor_file.py::test_short_header_raises_value_error_not_index_error tests/test_motor_file.py::test_short_data_row_raises_value_error_not_index_error` -> **5 passed in 0.76s**, confirming no interdependency on fixture/execution order within the broader test files.
- **Item 2 provenance cross-check**: confirmed the test docstring's "Re_n = 88,000", "HPR Sim crate `hpr_aero::crossflow`", and "+-0.005" claims verbatim against `dev/docs/latex/research/jorgensen-params-findings.md` line 14 -- not invented, not paraphrased loosely.
- **§14 audit-table cross-reference**: read `dev/docs/conventions-industry-standard-analysis.md` §14 rows 1-4 and row 10 directly (not just trusting the handoff's paraphrase) -- confirmed each of the 5 implemented items is listed there with "Pins move? no / LaTeX? no", matching the "no pin movement, no LaTeX, no user-decision fork" framing given for this step.

## Overall verdict

**PASS.** All 5 items match their audit-table classification (no pins move, no LaTeX touched, no user-decision fork needed) and are correctly, narrowly scoped to exactly what the audit specified -- no scope creep, no under-delivery. No blocker, no major, no minor defects found. One precision note (not a defect) on item 3's "no existing config combines..." claim, recorded above for the record. Targeted re-run: 249 passed (+ 5 new tests individually re-verified standalone). Full suite: 673 passed, 0 failed, 47 pre-existing warnings, matching the developer's claim exactly -- no numeric pins moved anywhere in the suite.



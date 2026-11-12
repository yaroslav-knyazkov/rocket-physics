## Кратко (RU)

- Рабочие заметки разработчика по Step 151 (Phase 2.26, D-180): консолидация
  fx27 idealized-данных в один файл `rockets_ideal.py` (Section A + Section B)
  по architecture-42. Полная спека уже одобрена пользователем — здесь только
  доказательства по тикетам FX27C-1..FX27C-7.
- Главный риск: Section A (58 строк rockets_ideal.py) — оракул AC-3, должен
  остаться байт-в-байт без изменений. Подтверждение — git diff ниже.
- По ходу работы нашёл и исправил одну реальную ловушку: первая версия нового
  теста для `estimate_cx_scale` случайно подобрала нестабильную комбинацию
  (демо-ракета + таблица с ненулевым моментом) и зависла на 20+ минут вместо
  падения/прохождения — не дал этому превратиться в ложный пройденный тест,
  продиагностировал и переписал тест на синтетическую drag-only таблицу.
- `code-review` нашёл ещё один реальный баг (нестабильный тест из-за гонки
  при удалении временного файла в синхронизируемой папке) и 2 устаревших
  докстринга (scenarios.py/scenarios_dm.py) — все три исправлены и
  переверифицированы; 3 находки про чужой незакоммиченный дифф (motors.zip,
  airbrake-controller-plan.md) и собственный маркер статуса — не мои правки,
  отмечены для оркестратора отдельно.
- Итог: полный прогон 899/899 (базовая линия 898 + 1 новый тест), AC-3
  границы не тронуты, Section A байт-в-байт не изменена.

---

## Pre-edit verification (read all source files before editing, per the task's instruction)

All files read and compared against the architecture-42 quoted excerpts before editing. No drift found:
- `projects/fx27/campaigns/cspace/rockets_ideal.py` — 58 lines (57 content + trailing newline), matches SS42.2 Section A description exactly.
- `projects/fx27/campaigns/cspace/rockets_ideal_own.py` — 112 lines, matches SS42.2's described B1 source (lines 45-111 body).
- `projects/fx27/campaigns/cspace/rockets_dm.py` — 111 lines, tail block (lines 73-110) matches SS42.3's described B2 source.
- `projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py` — matches SS42.4's described current shape.
- `apps/optimization/apogee_targeting/solve.py` — `estimate_cx` at lines 162-176, matches SS42.5's "placed directly after" instruction.
- `projects/fx27/point/estimate.py` — matches SS42.5's described current 2-name re-export.
- `projects/fx27/campaigns/cspace/scenarios.py` / `scenarios_dm.py` — match SS42.6's described current import/attribute shape.
- `tests/test_rockets_ideal_own.py` — matches SS42.7's described current shape.
- `tests/test_fx27_port.py` — only import of `rockets_ideal` module is the 4-name Section-A import listed in SS42.7; no reference to `rockets_ideal_own`/`generate_rockets_ideal_own`/dm-ideal constants beyond the already-known docstring mention.
- `tests/test_apogee_targeting.py` — exists, covers `estimate_cx`/`estimate_airframe_mass` with Tier 1 (monkeypatch) + Tier 2 (DEMO_SCENARIO regression) tests, no fixtures/conftest, plain `assert`/`math.isclose` — this is the house style FX27C-1's new test should match.
- `projects/fx27/runs/cspace/ideal_mass.py`, `ideal_drag.py`, `airbrake.py` — all match SS42.8's described current shape.

No `needs_input`/`blocked` triggered — proceeding with implementation in ticket order.

---

## FX27C-1 -- estimate_cx_scale + re-export (TDD)

- Red: added `test_estimate_cx_scale_on_table_scenario_is_reachable_and_converges` to
  `tests/test_apogee_targeting.py` (Tier 2 style, mirrors
  `test_estimate_cx_on_demo_scenario_is_reachable_and_converges`), using a locally-built
  `model="table"` variant of `DEMO_SCENARIO`'s rocket (`table="example.csv"`, the same
  fixture `tests/test_aero.py` already uses) -- no fx27 fixture needed, confirming the
  house-style note in `tests/test_apogee_targeting.py`'s own docstring ("apps/optimization/
  tests should not need projects/fx27 fixtures"). Confirmed import error before implementing
  (`ImportError: cannot import name 'estimate_cx_scale'`).
- Green: added `estimate_cx_scale` to `apps/optimization/apogee_targeting/solve.py`
  immediately after `estimate_cx`, body verbatim per architecture-42 SS42.5. Extended
  `projects/fx27/point/estimate.py`'s import/`__all__`/docstring to the third name.
- **Course correction, worth recording in full.** My first version of this test reused `DEMO_SCENARIO`'s
  own rocket with `model="table", table="example.csv"` (fx27's bundled test fixture, nonzero `C_N`/`C_m`).
  That combination turned out to destabilize `DEMO_SCENARIO`'s airframe almost immediately after rail exit
  (`AeroRangeWarning`, alpha left the table's covered range within ~5 s of a 1200 s flight) -- `DEMO_SCENARIO`'s
  own aero was deliberately built with `C_z=C_m=0` ("keeps flight vertical/1-D", that module's docstring),
  so pairing it with a table carrying real pitch-moment data reintroduced a genuine, unrelated instability
  (a documented RK45-stall regime, `dev/docs/diagnosis-rk45-v2-table.md`), not something that exercises
  `estimate_cx_scale` itself. First attempt's background run was left running >20 min with growing memory
  before I diagnosed this via a direct single-call timing probe and killed it -- it never produced a false
  pass, I caught it before trusting any output. Fix: built a small synthetic DRAG-ONLY table inline
  (`C_N=C_m=0` at every grid point, same Option C invariant `rockets_dm.py` itself relies on, same
  `_temp_table`/`aero._load_table.cache_clear()` pattern `tests/test_scenario_sweep.py` already uses for its
  own synthetic tables) so the flight stays exactly vertical and the known stall regime is never entered.
  Single-call timing with the fix: ~1.2-1.5 s/flight (cx_scale in {0.0, 1.0, 2.0}), vs. the first version's
  >60 s for a single call and no completion observed after 20+ min for a full brentq search.
  Also had to move the target from 3000 m (the other two Tier-2 tests' value, copied by rote) to 4000 m --
  measured that this table's C_A=0.5 only reaches apogees in ~[3654 m, 5947 m] over the default
  `cx_scale_bracket=(0.0, 2.0)`, so 3000 m was never reachable and the first corrected run still failed
  (`res.reachable is False`, `res.required == cx_scale_bracket[1] == 2.0`) until I picked a target inside
  the actually-achievable range. One leftover artifact from the killed run's incomplete cleanup (taskkill
  /F bypasses Python `finally` blocks): a stray `test_apogee_targeting_drag_only.csv` left in
  `projects/examples/data/aero/` from a manual debugging script -- found and removed (untracked, confirmed
  via `git status` before deleting).
- **Final result:** `python -m pytest tests/test_apogee_targeting.py -q` -> `8 passed, 10 warnings in
  34.99s` (the 10 warnings are expected -- `MachRangeWarning` on the 2 pre-existing constant-model Tier-2
  tests exceeding Mach 0.8, `AeroRangeWarning` once on the new table-model test; none are failures). No
  regression in the file's 7 pre-existing tests.

---

## FX27C-2 -- `rockets_ideal.py` Section B migration + `rockets_dm.py` trim

- Pre-edit: re-read `rockets_ideal.py` (58 lines) and `rockets_dm.py` (111 lines) fresh immediately before
  editing -- matched SS42.2/SS42.3 exactly, no drift.
- Inserted the one new import line directly below Section A's existing import, then appended Section B
  (B1 + B2) strictly after Section A's last line, verbatim per SS42.2's quoted final file shape.
- **Diff verification (SS42.2's own instruction, not skipped):**
  `git diff -- projects/fx27/campaigns/cspace/rockets_ideal.py` -- `grep -c '^-'` returns 1, and that one
  line is the `--- a/...` diff header itself, not a real removed content line (`grep '^-'` output confirms:
  only `--- a/projects/fx27/campaigns/cspace/rockets_ideal.py`). Zero actual `-` content lines. Two hunks,
  both additions only (the new import line + the appended Section B block). Section A is byte-for-bit
  unchanged -- confirmed by diff, not by eyeball.
- Trimmed `rockets_dm.py` per SS42.3: deleted lines 73-110 (B2's source block, now live in
  `rockets_ideal.py`), replaced the docstring's "4 ideal dm variants..." paragraph with the one-sentence
  pointer SS42.3 specifies. Final file is 69 lines: docstring + imports + 3 `_TABLE_*` constants + `_dm_aero`
  + 3 `*_DM` blocks, exactly SS42.3's described final shape. `PRO54_EQUAL_DM` untouched.
- Import sanity check (`python -c "from projects.fx27.campaigns.cspace import rockets_ideal, rockets_dm"`)
  -- both modules import cleanly, `rockets_ideal.PRO54_TRANSITION_IDEAL_OWN_MASS_KG == 4.3840` and
  `rockets_ideal.PRO54_TRANSITION_DM_IDEAL_MASS_KG == 4.9083` both present and correct (values carried
  verbatim from the migration sources).

---

## FX27C-3 -- `regenerate_ideal_own.py` (rename + retarget)

- Wrote the new file at `projects/fx27/campaigns/cspace/regenerate_ideal_own.py` per SS42.4: `_TARGET`
  repointed at `rockets_ideal.py`; removed `_with_cx_scale`/`_CX_SCALE_BRACKET`/the `solve_for_target_apogee`
  direct import/the `dataclasses` import (no longer needed, confirmed nothing else in the file used
  `dataclasses` before deleting the import); added `estimate_cx_scale` import; `_solved_values()`'s 2
  dm-drag entries now call `estimate_cx_scale(dm_t/dm_75, target_apogee_agl=TARGET_APOGEE_M).required`.
  Docstring updated per SS42.4's guardrail wording (every `rockets_ideal_own.py` mention replaced with
  `rockets_ideal.py`, every `generate_rockets_ideal_own` mention replaced with `regenerate_ideal_own` except
  the one deliberate historical-prose mention of the old script name explaining what it replaces, matching
  the architecture doc's own phrasing convention for such cross-references).
- Did NOT delete the old `generate_rockets_ideal_own.py` as part of this ticket, despite the ticket's own
  prose ("delete the old-named script... in the same commit") -- resolved the apparent tension with SS42.9's
  explicit delete list (which says "delete only after tickets 1-5 have all landed") and ticket FX27C-7's own
  explicit remit ("Delete the two files in SS42.9") by following the more specific, later-stated instruction:
  both files are deleted together in FX27C-7 after full verification, not piecemeal. Import sanity check
  (`from projects.fx27.campaigns.cspace.regenerate_ideal_own import _solved_values, _rewrite_file,
  _substitute_constant`) passes cleanly.
- Real-run verification (SS42.11 item 4, "run it for real, confirm no-op against the already-committed
  Section B1") deferred to the FX27C-7 verification pass below, run once, after every other ticket has
  landed -- running it twice (once here, once in FX27C-7) would be redundant and this script writes to the
  real committed file each time it runs.

---

## FX27C-4 -- `scenarios.py`/`scenarios_dm.py` import retarget

- Both files: `rockets_ideal_own` import swapped for `rockets_ideal`; all 8 attribute references (4 per
  file) repointed `rockets_ideal_own.X` -> `rockets_ideal.X`; both `_IDEAL_OWN_NOTE` regenerate-command
  strings updated to `regenerate_ideal_own`. Verified zero remaining `rockets_ideal_own.PRO*` attribute
  references in `projects/fx27/campaigns/cspace/` (grep, zero hits). The 2 remaining `rockets_ideal_own`
  substring hits per file are historical docstring/comment prose (SS42.6 explicitly scopes this ticket to
  "import + one attribute-prefix + one command-string edit only" -- surrounding prose is unchanged by
  design). Dict keys/motor/site/weather wiring untouched, confirmed by re-running the import sanity check
  above (`sorted(scenarios.SCENARIOS)`/`sorted(scenarios_dm.SCENARIOS_DM)` both still the same 7 keys each).

---

## FX27C-5 -- test rename/retarget: `tests/test_rockets_ideal_own.py` -> `tests/test_regenerate_ideal_own.py`

- `git mv` to the new name, then retargeted per SS42.7: module docstring (path + both architecture doc
  cross-references + "regenerate_ideal_own.py"/"rockets_ideal.py" naming throughout), imports
  (`rockets_ideal_own` -> `rockets_ideal`, `generate_rockets_ideal_own` -> `regenerate_ideal_own`), all 8
  `_VARIANTS` dict attribute accesses. Section 2 (write-mechanism, tmp_path-only) and section 3
  (plausibility) left unchanged beyond that swap, per the ticket's own scope note -- the tmp_path synthetic
  filename `rockets_ideal_own_fake.py` is untouched by design (an arbitrary fixture name, not a real import).
  Grep confirms zero remaining `generate_rockets_ideal_own` references in this file; the 2 remaining
  `rockets_ideal_own` substring hits are the tmp_path fixture filename and one section-4 comment's prose
  (both out of this ticket's stated scope).
- Isolated run (the ticket's own instruction, "before moving on"):
  `python -m pytest tests/test_regenerate_ideal_own.py -q` -> `22 passed, 7 warnings in 6.82s`. Fast and
  clean -- fx27's own `pro54-transition-drag.csv`/`pro75-drag.csv` tables cover alpha in [-89, 89] deg (wide
  enough for a real tail-first descent, unlike the ±10 deg generic fixture tables), confirming the FX27C-1
  test's earlier instability was specific to pairing a narrow-alpha table with a nonzero-moment curve, not a
  general problem with table-model flights in this project.

---

## FX27C-6 -- `ideal_mass.py`/`ideal_drag.py`/`airbrake.py` dm extensions

- `ideal_mass.py`: added `_OWN_AND_FX27_DM` dict + second `main()` loop per SS42.8's exact print format
  (own-regen/drift framing + "[NOT an oracle -- SS40.8...]" for the fx27 measured-delta figure). Docstring
  updated to describe the new rows.
- `ideal_drag.py`: same shape via `estimate_cx_scale`/`SCENARIOS_DM`, `_CAVEAT` dict left untouched (dc-only,
  keys never collide with the new `*_dm` names).
- `airbrake.py`: `IDEAL_VARIANTS` renamed `IDEAL_VARIANTS_DC`, added `IDEAL_VARIANTS_DM` + second loop; no
  "NOT an oracle" framing added (correct per SS42.8 -- this report never compared against an fx27 reference
  value). Grep confirmed zero other files reference the bare `IDEAL_VARIANTS` name before the rename.
- Import + dict-wiring sanity check (no heavy solving) confirms: `ideal_mass._OWN_AND_FX27_DM ==
  {'pro54_transition_dm': (4.9985, 4.9083), 'pro75_dm': (7.9238, 7.8663)}`, `ideal_drag._OWN_AND_FX27_DM ==
  {'pro54_transition_dm': (0.6263, 0.5843), 'pro75_dm': (1.5123, 1.4954)}` -- all 4 values match
  `rockets_ideal.py`'s Section B1/B2 constants exactly. `airbrake.IDEAL_VARIANTS_DC`/`IDEAL_VARIANTS_DM` both
  4-tuples, correct names.
- Manual `python -m` runs (captured, per the ticket's own instruction):

  `python -m projects.fx27.runs.cspace.ideal_mass`:
  ```
  pro54_transition: baseline=5.8350 kg, required=4.3840 kg (fx27 solved=4.2864 kg, error +2.28%), achieved apogee=3000.0 m, reachable=True
  pro75: baseline=6.2250 kg, required=8.1205 kg (fx27 solved=8.0654 kg, error +0.68%), achieved apogee=3000.0 m, reachable=True
  pro54_transition_dm: baseline=5.8350 kg, required=4.9985 kg (this project's own last regen=4.9985 kg, drift -0.00%), fx27 measured-delta figure=4.9083 kg [NOT an oracle -- SS40.8: no target-apogee solve backs this number, provenance only], achieved apogee=3000.0 m, reachable=True
  pro75_dm: baseline=6.2250 kg, required=7.9238 kg (this project's own last regen=7.9238 kg, drift +0.00%), fx27 measured-delta figure=7.8663 kg [NOT an oracle -- SS40.8: no target-apogee solve backs this number, provenance only], achieved apogee=3000.0 m, reachable=True
  ```

  `python -m projects.fx27.runs.cspace.ideal_drag`:
  ```
  pro54_transition: baseline=0.5000, required=0.2524 (fx27 solved=0.2351, error +7.35%), achieved apogee=3000.0 m, reachable=True
      NOTE: measured error for this vehicle exceeds the 5% band (accepted, user decision 2026-11) -- see dev/docs/fx27-port-progress-notes.md.
  pro75: baseline=0.5000, required=0.8400 (fx27 solved=0.8304, error +1.16%), achieved apogee=3000.0 m, reachable=True
  pro54_transition_dm: baseline=1.0000, required=0.6263 (this project's own last regen=0.6263, drift -0.00%), fx27 measured-delta figure=0.5843 [NOT an oracle -- SS40.8: no target-apogee solve backs this number, provenance only], achieved apogee=3000.0 m, reachable=True
  pro75_dm: baseline=1.0000, required=1.5123 (this project's own last regen=1.5123, drift -0.00%), fx27 measured-delta figure=1.4954 [NOT an oracle -- SS40.8: no target-apogee solve backs this number, provenance only], achieved apogee=3000.0 m, reachable=True
  ```

  `python -m projects.fx27.runs.cspace.airbrake` -- all 8 rows (4 dc + 4 dm) converged (16-23 simulator runs
  each), achieved apogee within ~3e-4 m of the 2500 m target on every row, no "NOT an oracle" labeling
  anywhere (correct per SS42.8 -- this report never compared against an fx27 reference value in the first
  place). The 4 dm rows' `C_dA_rocket` line correctly prints `n/a (aero.model != "constant": no single
  honest number)` instead of a number -- pre-existing behavior in `point/airbrake.py`, unaffected by this
  step, confirms the dm rows wired to real `model="table"` rockets, not silently falling back to dc.
  Full output captured in this run's terminal history; abbreviated here for length -- not pasted in full
  since the per-row shape is identical across all 8 and the key facts (converged=yes, achieved=target,
  no mislabeling) are already called out above.

- Verified `regenerate_ideal_own.py` real no-op run (SS42.11 item 4): `python -m
  projects.fx27.campaigns.cspace.regenerate_ideal_own` printed the same 8 values already committed in
  `rockets_ideal.py` Section B1 (`PRO54_TRANSITION_IDEAL_OWN_MASS_KG = 4.3840`, etc. -- all 8 match
  byte-for-bit), and `git diff --stat -- projects/fx27/campaigns/cspace/rockets_ideal.py` shows the same
  139-insertion/0-deletion diff as before the run (identical string substitution of identical values ->
  no new diff). Confirms this project's own base figures (rockets.py/rockets_dm.py) have not drifted since
  the last regen, and the script correctly reproduces its own prior output against the new file/target.

---

## FX27C-7 -- delete retired files + full verification (SS42.11)

- Deleted `projects/fx27/campaigns/cspace/rockets_ideal_own.py` and
  `projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py` (`git rm`, per SS42.9's delete list).
- **Grep check 1** (`grep -rln "rockets_ideal_own" --include="*.py" .`): hits only in
  `apps/optimization/apogee_targeting/solve.py`, `projects/fx27/campaigns/cspace/regenerate_ideal_own.py`,
  `rockets_ideal.py`, `scenarios.py`, `scenarios_dm.py`, `tests/test_regenerate_ideal_own.py` -- all 6
  already inspected per-ticket above, all are historical docstring/comment prose, zero are imports/live
  code references (confirmed by a second, stricter grep: `grep -rn "^from.*rockets_ideal_own\|^import.*
  rockets_ideal_own"` across all `.py` files returns zero matches).
- **Grep check 2** (`generate_rockets_ideal_own`): hits only in `solve.py` and `regenerate_ideal_own.py`,
  both historical-prose cross-references to the old script name (same "^from/^import" stricter check:
  zero matches).
- **SS42.11 verification sequence:**
  1. `python -m pytest tests/test_fx27_port.py -q` -> `61 passed, 19 warnings in 35.24s`. Zero changes in
     pass/fail status vs. before this consolidation (this file was not edited at all, per SS42.7's own
     reasoning -- confirmed: `git diff --stat -- tests/test_fx27_port.py` shows no output, i.e. truly
     zero-byte diff).
  2. `python -m pytest tests/test_regenerate_ideal_own.py -q` -> `22 passed, 7 warnings in 6.82s` (already
     recorded under FX27C-5 above).
  3. `git diff -- projects/fx27/campaigns/cspace/rockets_ideal.py`: 2 hunks, both pure additions (the one
     inserted import line + the appended Section B block), zero `-` content lines (only the `---
     a/...` diff header itself) -- Section A byte-for-bit untouched. Recorded in full under FX27C-2 above.
  4. `python -m projects.fx27.campaigns.cspace.regenerate_ideal_own` run for real: printed values identical
     to the already-committed Section B1, confirmed no-op via `git diff --stat` showing the same diff as
     before the run (recorded under FX27C-6 above).
  5. All 3 extended scripts (`ideal_mass`, `ideal_drag`, `airbrake`) run manually, printed output captured
     and visually confirmed against SS42.8's wording -- "NOT an oracle" framing present on both dm rows of
     `ideal_mass.py`/`ideal_drag.py`, absent (correctly) from all of `airbrake.py`'s 8 rows (recorded under
     FX27C-6 above).
---

## Code review (skill, medium effort) and fixes

Ran `code-review` on the working-tree diff vs HEAD per role contract (before handoff). 6 findings; 3 are
real bugs in my own diff, fixed below; 3 are pre-existing/unrelated drift in the working tree that I did
not touch and should not silently "fix" on someone else's behalf:

**Fixed (real bugs, my diff):**
1. **Flaky test** -- `tests/test_apogee_targeting.py`'s new `_temp_table` helper's `finally: os.remove(path)`
   intermittently raised `FileNotFoundError` when this test ran alongside other table-model tests in the
   same pytest session (code-review reproduced it 2/5 times via `python -m pytest tests/ -k "fx27 or cspace
   or scenario" -q`; my own earlier full-suite run of 899 happened not to hit the window). Root cause not
   fully pinned down -- no pytest-xdist/randomization plugin is configured (checked `requirements.txt`/
   `pyproject.toml`), so this is not a collection-order bug; most likely explanation given this repo's data/
   tree lives under a cloud-synced folder (CLAUDE.md's existing Yandex.Disk note, previously only flagged
   for `.git` internals) is a create-then-remove race with the sync client, but this was not independently
   proven, only inferred from elimination. Fix: wrapped `os.remove(path)` in `try/except FileNotFoundError:
   pass` -- the actual goal (no stray file left behind) is satisfied either way a missing file at cleanup
   time is found. Re-ran the exact reproducing command 3/3 clean after the fix (`92 passed, 807 deselected`
   each time) plus the file in isolation once more (`8 passed`). Flagging for the orchestrator: `tests/
   test_scenario_sweep.py`'s own `_temp_table` helper has the textually identical unguarded `os.remove`
   pattern and shares the same latent exposure -- out of this ticket's file boundary, not fixed here, but
   worth a follow-up note in CLAUDE.md's environment-hazards list if it's ever seen to flake for real.
2. **Stale docstring, `scenarios.py`** -- said the project's own solve lives in `rockets_ideal_own.py`
   (deleted by FX27C-7) and fx27's solved figures live in `rockets_ideal.py` without noting the file now
   holds both (Section A/B1). SS42.6 only mandated the import/attribute/command-string edits, not this
   paragraph, but code-review correctly flagged it as now actively wrong, not merely stale -- fixed to name
   both sections and the shared file.
3. **Stale docstring, `scenarios_dm.py`** -- same shape: said fx27's dm figures live in `rockets_dm.py`,
   which is false after SS42.3's trim moved them into `rockets_ideal.py` Section B2 -- fixed the same way,
   also tightened the wording to note B2 is NOT an oracle either (SS40.8), matching the rest of this step's
   own "NOT an oracle" framing discipline.

**Not fixed (pre-existing, outside this diff's authorship, flagged for the orchestrator instead):**
4. `projects/fx27/docs/airbrake-controller-plan.md` (484-line rewrite) and
   `projects/fx27/campaigns/cspace/data/motors.zip` (untracked, 463 bytes) both showed up in `git status`/
   `git diff --stat` from the start of this session, before I touched anything -- confirmed via `git log`
   that `airbrake-controller-plan.md` is tracked and was last committed at `03a1f77` (an unrelated step),
   and its current working-tree modification predates this session (the orchestrator's own initial
   `gitStatus` block already showed drift in that directory). I did not author either change and have no
   basis to judge what the correct resolution is -- noted here so the orchestrator excludes both from any
   Step 151 commit (`git add` by explicit path, not `-A`), rather than silently bundling someone else's
   in-flight work into this step's commit.
5. The deliverable file (this one) starts `<!-- STATUS: in-progress -->` while its body already documents a
   completed verification pass -- code-review correctly flagged the contradiction. Removed below, on this
   turn, now that the review round (including its own 3 fixes above) is actually done.

**Post-fix re-verification** (targeted, not a second full 997 s run -- the 3 fixes are docstring text plus
one exception-handling addition on an already-passing path, not a behavior change to anything the full run
exercised numerically): `python -c "from projects.fx27.campaigns.cspace import scenarios, scenarios_dm"`
imports cleanly, same 7+7 keys as before; `python -m pytest tests/test_apogee_targeting.py -q` -> `8 passed`
(unchanged); `python -m pytest tests/ -k "fx27 or cspace or scenario" -q` -> `92 passed, 807 deselected`
**3/3 clean runs in a row** (the exact command that reproduced the flake before the fix); `python -m pytest
tests/test_fx27_port.py tests/test_regenerate_ideal_own.py -q` -> `83 passed` (61 + 22, both files'
sub-counts unchanged from their own isolated runs recorded above).

---

- **Full suite:** `python -m pytest -q` -> `899 passed, 112 warnings in 997.41s (0:16:37)`. Baseline (Step
  150, orchestrator-verified) was 898 passed; `899 - 898 = +1`, exactly the one new test this step added
  (FX27C-1's `test_estimate_cx_scale_on_table_scenario_is_reachable_and_converges`) -- zero other count
  drift, zero failures, zero skips. Runtime (997 s) is well above this project's usual ~220 s baseline but
  within the documented outlier envelope (CLAUDE.md records a ~765 s one-off on 2026-10-27 of unexplained
  cause) -- checked via repeated `UserModeTime` polling throughout that this was active CPU work, not a
  hang, at every slow stretch. All 112 warnings are expected `MachRangeWarning`/`AeroRangeWarning`/
  `RuntimeWarning` (pre-existing precedent in this suite, not new), confirmed by reading the full warnings
  summary -- no new warning category introduced by this step's changes.
  **AC-3 boundary, explicitly checked in this run's output:** `tests/test_fx27_port.py::test_ac3_estimate_
  airframe_mass_pro54_transition`, `::test_ac3_estimate_airframe_mass_pro75`, `::test_ac3_estimate_cx_pro75`,
  `::test_ac3_estimate_cx_pro54_transition_wider_tolerance` all appear in the warnings summary (each
  triggers at least one `MachRangeWarning`, confirming they ran) and the run reports 0 failed -- all 4
  passed. `test_cspace_has_exactly_the_seven_comparison_rows`/`test_cspace_scenario_assembles` are part of
  `test_fx27_port.py`'s 61-passed/0-failed result (independently confirmed in isolation earlier in this
  file, SS42.11 item 1).

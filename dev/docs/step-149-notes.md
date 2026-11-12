# Step 149 (Phase 2.24) notes -- re-point ideal rows to own solver values

## Кратко (RU)

- Задача: 4 "ideal" строки в cspace-сценариях (dc и dm) должны лететь по собственным (этого проекта)
  значениям солвера апогея, а не по оракульным значениям fx27 (`rockets_ideal.py`/`rockets_dm.py`,
  которые трогать запрещено -- это AC-3 оракул для `tests/test_fx27_port.py`).
- Правим только `scenarios.py` и `scenarios_dm.py` (поле `rocket=` + `notes=` + докстринг),
  плюс докстринг `rockets_ideal_own.py` при необходимости, плюс архитектурную заметку SS41.7.
- Ключи словарей `SCENARIOS`/`SCENARIOS_DM` остаются неизменными (7 штук каждый) -- просто
  перенаправляем существующие строки на другую константу.
- Тест по TDD: добавлен параметризованный тест в `tests/test_rockets_ideal_own.py`, летит все 8
  "ideal own" строк через `flight.py::run` и проверяет апогей против 3000 м с допуском -- см. раздел
  "dm measurements" ниже для фактического допуска.

## Plan

1. Read `projects/fx27/campaigns/cspace/scenarios.py`, `scenarios_dm.py`, `rockets_ideal_own.py`,
   `rockets_ideal.py` (read-only), `rockets_dm.py` (read-only), `tests/test_rockets_ideal_own.py`,
   `projects/fx27/point/flight.py::run` signature.
2. Measure dm ideal-own values via `flight.py::run` (dc values already measured by orchestrator, given
   in the task).
3. Write test first (TDD), run it red against current wiring (still pointing at oracle -- expect FAIL
   if oracle numbers differ from target, or need to check behavior before rewiring).
4. Re-point `scenarios.py` and `scenarios_dm.py`.
5. Fix docstrings/notes.
6. Update `dev/docs/architecture-41-fx27-idealized-regenerate.md` SS41.7.
7. Run targeted tests, then full suite.
8. code-review skill.

## Measurements

### dc ideal rows (given by orchestrator, flown by them before handoff)

| case | apogee | err vs 3000 m |
|---|---|---|
| pro54_transition, m=4.3840 kg | 3000.01 m | +0.011 |
| pro54_transition, C_x=0.2524 | 2999.93 m | -0.069 |
| pro75, m=8.1205 kg | 3000.00 m | +0.003 |
| pro75, C_x=0.8400 | 3000.08 m | +0.078 |

### dm ideal rows (measured by me, `cx_scale` variants)

```
pro54_transition_dm_ideal_own_mass            apogee=2999.9970 err=-0.0030
pro54_transition_dm_ideal_own_drag            apogee=2999.9804 err=-0.0196
pro75_dm_ideal_own_mass                       apogee=2999.9857 err=-0.0143
pro75_dm_ideal_own_drag                       apogee=2999.9894 err=-0.0106
```

Max |error| across all 8 rows: 0.078 m (pro75 dc ideal drag). Chose tolerance
`abs(apogee - 3000.0) <= 1.0` m per task instructions (well inside the measured band for all 8
rows, no row needed to be excluded/flagged).

## TDD sequence

1. Appended section 4 to `tests/test_rockets_ideal_own.py`: `test_ideal_dc_row_reaches_apogee_
   target` / `test_ideal_dm_row_reaches_apogee_target`, parametrized over the 4 dc + 4 dm row
   names, importing `SCENARIOS`/`SCENARIOS_DM` and flying each row through `projects/fx27/point/
   flight.py::run` (aliased `fly` to avoid colliding with pytest's own `run` name confusion).
2. Ran red BEFORE touching `scenarios.py`/`scenarios_dm.py`: all 8 new tests failed (dicts still
   pointed at the fx27 oracle, which overshoots) -- e.g. `pro54_transition_dm (ideal mass)`:
   `apogee=3014.67 m`, `abs(err)=14.67 > 1.0`. Confirms the test actually exercises the wiring,
   not a tautology.
3. Re-pointed `scenarios.py`'s 4 ideal rows' `rocket=` to `rockets_ideal_own.PRO54_TRANSITION_
   IDEAL_OWN_MASS/_DRAG`, `PRO75_IDEAL_OWN_MASS/_DRAG`; swapped the `rockets_ideal` import for
   `rockets_ideal_own` (no other row in that file used `rockets_ideal`, so the old import was
   removed cleanly, no orphaned import).
4. Re-pointed `scenarios_dm.py`'s 4 ideal-dm rows the same way to `rockets_ideal_own.PRO54_
   TRANSITION_DM_IDEAL_OWN_MASS/_DRAG`, `PRO75_DM_IDEAL_OWN_MASS/_DRAG`; kept the `rockets_dm`
   import (still used by the 3 base dm rows) and added `rockets_ideal_own` alongside it.
5. Rewrote each touched row's `notes=` (previously claimed "fx27 data/cspace/rockets_ideal.py
   ... -- the AC-3 mass/drag oracle", now false) to point at this project's own solver and the
   regenerate script, and fixed both files' module docstrings (added a paragraph explaining the
   re-point and why the oracle files stay untouched/reserved).
6. Re-ran: all 22 tests in `tests/test_rockets_ideal_own.py` passed (green).

## Checked: stale-claim items from the task

- **(c) `rockets_ideal_own.py` docstring** -- read in full (112 lines). It never claims it is "not
  wired into the scenario sets" (that claim lives in the OLD comment inside
  `tests/test_rockets_ideal_own.py`, item below, not in this module). Its contrast with
  `rockets_ideal.py`/`rockets_dm.py` ("the AC-3 acceptance ORACLE ... MUST NEVER be touched") is
  still fully accurate after this step -- the oracle files are untouched. No edit made to this
  file (constraint: its 8 generated constant lines are off-limits, and no other line needed
  changing).
- Found and fixed one MORE stale claim not explicitly listed in the task: the comment block above
  section 1 in `tests/test_rockets_ideal_own.py` said "SS41.7: the 8 new Rocket variants are NOT
  wired into SCENARIOS/SCENARIOS_DM" -- now false for 4 dc + 4 dm of the 8. Reworded to clarify
  SS41.7's key-count reasoning still holds, while noting the new section 4 below covers the now-
  wired subset.
- `projects/fx27/runs/cspace/ideal_mass.py` / `ideal_drag.py` (task item e): read both in full.
  Confirmed unaffected -- they key `SCENARIOS["pro54_transition"]`/`SCENARIOS["pro75"]` (the BASE
  rows, untouched by this step) and import `rockets_ideal.PRO54_TRANSITION_IDEAL_MASS_KG`/etc.
  directly as their own comparison figure, never going through the ideal *rows* of `SCENARIOS`.
  Left completely alone, as instructed.

## Architecture doc (`dev/docs/architecture-41-fx27-idealized-regenerate.md`)

Added one addendum paragraph directly under SS41.7's existing text (before the SS41.8 heading),
recording the Step 149 re-point, explicitly stating the key-count pins are unaffected and SS41.7's
own "not extended" reasoning still stands. Added 2 lines to the top `## Кратко (RU)` block.

Left alone: the SS41.1 scope table (`| scenarios.py, scenarios_dm.py | No -- see SS41.7 |`) is a
historical record of Step 148's own zero-edit scope and is still accurate as a statement about
THAT step; it is not re-litigated here since the task asked for exactly one note, under SS41.7,
not a rewrite of SS41.1's table. Flagging this for the orchestrator/user in case they'd prefer a
parenthetical there too -- I judged it out of scope for "one short note."

## Code review (mattpocock-skills:code-review, Standards + Spec, medium effort)

3 findings, addressed:

1. **Doc completeness gap** -- the SS41.7 addendum didn't mention that `tests/test_fx27_port.py::
   test_airbrake_solve_converges_for_one_ideal_variant` (AC-5) and `runs/cspace/airbrake.py` also
   consume the 4 re-pointed dc ideal rows. Verified both still pass/converge (ran `python -m
   projects.fx27.runs.cspace.airbrake` manually -- converges for all 4 dc ideal rows; AC-5 test is
   part of the 56-passed `test_fx27_port.py` run). Added a paragraph to the addendum naming both as
   affected-input/unaffected-outcome consumers.
2. **Duplicated `notes=` string** -- same 4-line literal repeated verbatim across scenarios.py's 4
   ideal rows (and a near-identical copy across scenarios_dm.py's 4). Hoisted to a module-level
   `_IDEAL_OWN_NOTE` constant in each file, matching `rockets_ideal_own.py`'s own `_NOTE` pattern.
3. **Test overlap** (`pro75_ideal_own_mass`/`pro75_dm_ideal_own_drag` flown twice, once in section
   3's plausibility check and once in section 4's on-target check) -- left as-is: harmless, both
   checks have a distinct purpose (broad plausibility band vs. tight 3000 m target), and removing
   either would reduce what each section independently documents. Noted here for visibility, not
   acted on.

Re-ran `tests/test_rockets_ideal_own.py` + `tests/test_fx27_port.py` after the hoist refactor: 78
passed, confirming the notes-constant change is behavior-neutral.

## Full suite result (step gate)

`python -m pytest -q` (run_in_background, before the code-review's notes-constant refactor --
that refactor only touches string literals/docstrings, not `rocket=`/dict keys, so it does not
change any test behavior; confirmed by re-running the two directly-relevant test files above after
the refactor):

```
893 passed, 107 warnings in 993.78s (0:16:33)
```

0 failed. No `Windows fatal exception: access violation` this run. Runtime (~994s) is on the high
end of this machine's observed range (~220-800s typical, one prior ~765s outlier) but not flagged
as a regression -- no numeric pin test shows a different count or failure, and the known-flaky
crash did not occur.

Confirmed untouched (`git diff --stat`, empty output):
- `projects/fx27/campaigns/cspace/rockets_ideal.py`
- `projects/fx27/campaigns/cspace/rockets_dm.py`
- `tests/test_fx27_port.py`

`rockets_ideal_own.py` (task item c): read in full, no stale claim found needing edit (see
"Checked: stale-claim items" above) -- left untouched.

## Wall-clock cost of the added tests

8 new parametrized flights (4 dc + 4 dm) in `tests/test_rockets_ideal_own.py` section 4. The whole
file (22 tests, including these 8 plus the pre-existing 14) runs in ~7s locally -- negligible
addition to the suite's total ~994s.



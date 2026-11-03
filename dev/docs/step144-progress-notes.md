# Step 144 progress notes (developer)

Scope: promote `projects/fx27/point/estimate.py` apogee-target solver into
`apps/optimization/apogee_targeting/`. Per architecture-39, SS39.10 tickets
AT-1..AT-4.

## Кратко (RU)

Рабочие заметки по Step 144 (Phase 2.21): перенос генерик apogee-target
root-finder из `projects/fx27/point/estimate.py` в постоянную библиотеку
`apps/optimization/apogee_targeting/`. План по тикетам AT-1..AT-4 из
architecture-39 SS39.10. Обновляется по ходу работы.

## Baseline AC-3 `_pct_error` values (measured BEFORE any edit)

Captured via a throwaway script calling `estimate_airframe_mass`/`estimate_cx`
directly (same call shape as `tests/test_fx27_port.py`'s 4 AC-3 tests),
against the original (pre-refactor) `projects/fx27/point/estimate.py`:

| Case | `required` | `_pct_error` |
|------|-----------|---------------|
| `estimate_airframe_mass(pro54_transition)` | 4.38402204781832 | 0.02277483385085839 |
| `estimate_airframe_mass(pro75)` | 8.120517330130442 | 0.006833799951700013 |
| `estimate_cx(pro75)` | 0.8400492016157266 | 0.011619944142252621 |
| `estimate_cx(pro54_transition)` | 0.2523764135837346 | 0.07348538317198886 |

All 4 `reachable=True`. These will be re-measured in AT-4 after the wrapper
is in place and must match exactly (same floats, same algorithm, only the
call path changes).

## AT-1 checkpoint

Created `apps/optimization/apogee_targeting/__init__.py` and `solve.py` per
SS39.4's skeleton verbatim (ApogeeTargetResult, `_apogee_for_scenario`,
`solve_for_target_apogee`, `estimate_airframe_mass`, `estimate_cx`). No
`projects.*` import -- `_apogee_for_scenario` inlines `assemble -> run_sim
-> flight_stats` directly (SS39.3 constraint honored). No existing `apps/`
file edited.

## AT-2 checkpoint

Drift-check against the actual tree (grep across `projects/fx27/`) before
rewriting: `runs/cspace_ideal_mass.py` and `runs/cspace_ideal_drag.py` both
still import `from projects.fx27.point.estimate import
estimate_airframe_mass` / `estimate_cx` by the same module path and
names. `point/__init__.py` and `cspace/rockets_ideal.py` reference
`estimate.estimate_airframe_mass`/`estimate_cx` only in prose docstrings.
`tests/test_fx27_port.py` imports the same two names from the same path.
No drift found -- doc's assumption holds against the current tree.
`projects/fx27/README.md`'s own measured AC-3 figures (4.3840, 0.2524,
8.1205, 0.8400) match this session's baseline measurement exactly, as a
cross-check.

Rewrote `projects/fx27/point/estimate.py` in place as a 23-line thin
wrapper re-exporting `EstimateResult` (alias of `ApogeeTargetResult`),
`estimate_airframe_mass`, `estimate_cx` from
`apps.optimization.apogee_targeting.solve`, per SS39.5 verbatim. No other
file under `projects/fx27/` touched.

## AT-3 checkpoint

`tests/test_apogee_targeting.py` written alongside AT-1 (tdd skill), 7
tests per SS39.6.2 (5 tier-1 monkeypatch pure-logic, 2 tier-2 real-physics
against `DEMO_SCENARIO`). All 7 pass standalone (`python -m pytest
tests/test_apogee_targeting.py -q` -> `7 passed`). No fixtures/conftest,
plain assert + math.isclose, matching `test_airbrake_sizing.py` house
style.

## AT-4 checkpoint

`tests/test_fx27_port.py` standalone: `42 passed` (same count as before
this ticket's edits, same test names, no change). AC-3 `_pct_error`
re-measured via the same throwaway script calling
`estimate_airframe_mass`/`estimate_cx` the way the 4 AC-3 tests do, now
through the rewritten wrapper -- bit-for-bit identical to the pre-edit
baseline above (same `required` floats, same `_pct_error` floats, all
`reachable=True`). Wrapper is behaviorally transparent as required.

Full suite (`python -m pytest -q`) ran in background to completion:
`850 passed, 96 warnings in 836.63s (0:13:56)`, exit code 0. Includes the
7 new `tests/test_apogee_targeting.py` tests plus all 42
`tests/test_fx27_port.py` tests, counted in the 850. No failures, no
errors. `test_layering.py`'s G1/G2/G3/G5/G6 guards passed (confirms
SS39.8's row: no `apps/` -> `projects/` import introduced, no banned
network import in the new module). No numeric pin outside
`tests/test_apogee_targeting.py` (new) and the AC-3 values in
`tests/test_fx27_port.py` (unchanged, verified bit-for-bit above) moved --
the previous full-suite baseline for this project (per `CLAUDE.md`'s
project-profile notes) was in the ~220-390s range before this step; 836s
is on the high end of the observed range but not outside documented
precedent (a once-observed 765s outlier is noted in `CLAUDE.md` already),
and 850 collected tests all green is consistent with no regression
anywhere else in the suite.

## Result

AT-1/AT-2/AT-3/AT-4 all complete. Zero-behavior-change confirmed
bit-for-bit for the AC-3 oracle values. Full suite green at 850/850.

## Code review (self, no Task/subagent tool available in this session)

`mattpocock-skills:code-review` invoked; this environment has no generic
Agent/Task tool to spawn the skill's two parallel sub-agents, so the
two-axis review (Standards/Spec) was performed directly against the diff
instead of via sub-agents. Findings:

- **Standards**: matches `apps/optimization/airbrake_sizing/` precedent
  (one-line `__init__.py` docstring, module docstring shape, quoted
  `"float | None"`/`"tuple[float, float]"` annotations -- pre-existing
  style carried verbatim from the original `estimate.py`, not introduced
  here). Test file matches `test_airbrake_sizing.py`'s house style: no
  fixtures/conftest, `monkeypatch.setattr(solve, "_apogee_for_scenario",
  ...)` mirrors that file's `monkeypatch.setattr(solve_cda, "run_sim",
  ...)` pattern. No smells found (no duplication introduced -- the
  verbatim-port constraint from SS39.4 explicitly forbids "improving" the
  body; no speculative generality added).
- **Spec**: `solve.py` skeleton matches SS39.4 verbatim (checked line by
  line while writing). `estimate.py` wrapper matches SS39.5 verbatim.
  Layering constraint (SS39.3) honored: `solve.py` imports only
  `apps._shared.flight_stats`, `apps.sim.engine.integrate`,
  `apps.sim.schema`, `scipy.optimize`, `dataclasses`, `typing` -- no
  `projects.*` import anywhere. All 7 SS39.6.2 tests present with the
  exact assertions the spec lists. No scope creep (no file outside the 3
  ticket boundaries touched).

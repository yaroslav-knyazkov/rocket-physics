# Steps 138-142 (Phase 2.20) — progress notes

Scratch notes for the orchestrator, per-step. Implementing
`dev/docs/architecture-36-projects-pivot.md` in full, F1 resolved as (b) retire
`examples/worked_scenario.py`.

## Step 138 — `data/` -> `projects/data/` — DONE

- `git mv data/README.md projects/data/README.md`; updated its own prose
  (title, directory-tree example, resolver bare-name/relative-path examples,
  `Motor(...)` config example) from bare `data/`/`examples/data/` to
  `projects/data/`/`projects/examples/data/`.
- Plain filesystem move (not git mv, untracked): `data/motors/` ->
  `projects/data/motors/` (this machine's personal motor-curve scratch:
  `cspace/`, `euroc-sweep/` subfolders). Removed the now-empty `data/` dir.
- `.gitignore`: `/data/*` -> `/projects/data/*`, `!/data/README.md` ->
  `!/projects/data/README.md`, updated the explanatory comment above.
- `tests/test_layering.py`: `RETIRED_PATHS` gained `"data"` (+ comment).
- Confirmed by grep: nothing else hardcodes the old `data/` path.
  `apps/input/sounding_fetch/fetch_sounding.py:364` builds
  `os.path.join(os.getcwd(), "data", "soundings")` — already cwd-relative,
  no change needed (ticket's own note).
- Gate (targeted, per ticket): `pytest tests/test_layering.py
  tests/test_schema.py -q` -> 19 passed.

## Step 139 — resolve F1: retire `examples/worked_scenario.py` — DONE

- `git rm examples/worked_scenario.py` (deleted outright, not moved).
- `tests/test_worked_scenario_example.py` rewritten: dropped `subprocess`/
  `sys`/`Path`; now calls `assemble(DEMO_SCENARIO)` -> `run_sim` ->
  `report.print_run_summary` in-process, asserts on
  `capsys.readouterr().out` instead of a subprocess's stdout. Same two
  assertions (`"Apogee altitude:"`, `"Burnout time:"`).
- `apps/input/demo_scenario.py`'s docstring: rewrote the final paragraph
  (was: "`examples/worked_scenario.py` is the thin, directly-runnable
  copy... run `python -m examples.worked_scenario`") to say there's no
  pre-built runnable copy any more and point at writing a short script
  under `projects/` instead. Left the earlier historical paragraph
  ("Step 123 wired `run.py` and friends...") untouched — pure history,
  no functional dependency, matches the project's established
  carve-out practice.
- Left untouched (historical prose, no functional dependency, confirmed
  by reading each): `tests/test_schema.py` (2 mentions),
  `tests/test_demo_physics.py` (3 mentions),
  `apps/optimization/motor_selection/scenario_sweep.py` (comment) — all
  just narrate "moved from `examples.worked_scenario` at Step 130"
  history or name the still-existing test file by filename.
- Gate (per ticket — rewritten test must pass): `pytest
  tests/test_worked_scenario_example.py tests/test_layering.py
  tests/test_schema.py -q` -> 20 passed, 1 warning (pre-existing
  MachRangeWarning from the demo scenario's own Mach profile, unrelated
  to this change, same as before the rewrite via subprocess).

## Step 140 — `examples/data/` -> `projects/examples/data/` + library anchor update — DONE

- `git mv examples/data projects/examples/data` (aero/, motors/,
  soundings/ subtrees, 14 tracked files). Removed leftover gitignored
  `examples/__pycache__/` and the now-empty `examples/` directory.
- `projects/examples/data/motors/README.md`: title ->
  `projects/examples/data/motors/`, "gitignored root `data/`... see
  `data/README.md`" -> `projects/data/`/`projects/data/README.md`,
  dropped the now-stale "runnable via `python -m
  examples.worked_scenario`" mention in the Cesaroni table row (F1
  fallout).
- `projects/examples/data/soundings/README.md`: title ->
  `projects/examples/data/soundings/`, same `data/`/`data/README.md` ->
  `projects/data/`/`projects/data/README.md` prose update. Left its
  `run.py` "who reads it" mention alone (Step 141's job, not this
  step's).
- `apps/sim/engine/datafiles.py`: `_BUNDLED`'s join suffix `"examples",
  "data"` -> `"projects", "examples", "data"` (the four `dirname()`
  calls unchanged, per ticket's SS3). Updated docstring mentions (rule
  3, the Step 129/138/140 history paragraph) and the
  `BundledDataMissingError` message text to match.
- `tests/datadir.py`: `DATA = os.path.join(_REPO_ROOT, "projects",
  "examples", "data")`; updated its docstring mention.
- `tests/test_layering.py`: G5 docstring + its test's docstring/assertion
  updated to `projects/examples/data`; `NETWORK_SCAN_ROOTS` dropped the
  `"examples"` entry entirely (recommendation b — nothing left to scan,
  `projects/examples/` is pure data); `RETIRED_PATHS` gained `"examples"`;
  updated the module docstring's G3 scope note to explain the removal.
- Left untouched (established carve-out, confirmed no functional
  dependency): dozens of historical bare `data/motors/`,
  `data/soundings/`, `examples/data/...` prose mentions across
  `apps/sim/engine/{params,soundings,thrust_curve,motor_file,
  compare_motors,...}` and most of `tests/*.py`; `BANNED_ENGINE_IMPORT_
  ROOTS`'s `"examples"` entry (G1, vacuous now but harmless, not listed
  for change in the ticket).
- Gate (per ticket — full suite, this is the step that moves every
  bundled fixture the whole suite reads): orchestrator independently ran
  the full suite (chunked across 9 background calls on their end) and
  confirmed **774 passed, 0 failed, across all 48 test files, zero
  errors**.

## Step 141 — delete the 5 root `run_*.py` scripts — DONE

- `git rm run.py run_motor_sweep.py run_airbrake.py run_cfd_conditions.py
  run_trade.py` — all 5 deleted outright, no replacement.
- `tests/test_schema.py`: deleted `_RUN_PY = (_PROJECT_ROOT /
  "run.py").read_text()` and
  `test_run_py_sources_its_scenario_from_configs_get_demo` (the only test
  reading `run.py`'s own source text). `_SELECT_CONDITIONS_PY`/
  `_COMPARE_MOTORS_PY` and their tests untouched (those files aren't
  moving).
- `tests/test_layering.py`: `NETWORK_SCAN_ROOT_FILES` -> `()` (+
  comment); `RETIRED_PATHS` gained the 5 filenames (+ comment).
- Confirmed by grep: no code anywhere imports or subprocess-invokes any
  of the 5 deleted files. Left untouched (established carve-out, matches
  the ticket's own list exactly): historical "run.py's placeholder
  scenario" prose in `tests/test_control.py`, `tests/test_dynamics.py`,
  `tests/test_integrate.py`, `tests/test_plotting.py`,
  `tests/config_variants.py`, `tests/test_weight_aero_tradeoff.py`, and
  dozens of similar historical mentions across `apps/*.py` docstrings —
  none have a functional dependency on the deleted files.
- Gate (per ticket — full suite): orchestrator independently ran the
  full suite (9 background calls on their end) and confirmed **773
  passed, 0 failed, across all 48 test files** (774 minus the 1 test
  correctly deleted from `test_schema.py` — exact expected delta).

## Step 142 — delete `output/` — DONE

- `rm -rf output/` — 16 stale generated files from past manual runs
  (gitignored, never tracked) deleted wholesale, not relocated.
- `.gitignore`'s `output/` entry comment rewritten: was "regenerated by
  running run.py" (no longer accurate, `run.py` is gone as of Step 141);
  now explains the actual mechanism (`output_dir()`/
  `default_output_dir()` resolve `Path.cwd() / "output"`, recreated
  wherever an app's cwd happens to be on next invocation).
- No code change — confirmed cwd-anchored everywhere per the ticket's
  SS2.5/SS5.4 (`apps/_shared/artifacts.py::output_dir()`,
  `apps/sim/engine/report.py::default_output_dir()`).
- Gate (targeted, per ticket): `pytest tests/test_layering.py
  tests/test_schema.py -q` -> 18 passed (no output-path assertions
  exist in either file, confirmed by the ticket's own grep).

## All 5 steps done

Steps 138-142 (Phase 2.20) are complete. `git status`/`git diff --stat`
checked against the ticket's full SS5 file list (SS5.1-SS5.4) — matches
exactly, nothing stray outside what the ticket specifies.


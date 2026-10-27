# examples/data/motors/

Thrust-curve files, selected through `thrust.motor_curve` (a bare filename
resolves here via `sim/datafiles.py` rule 3, optionally
`"<file>#<designation>"`). Loaded by `sim/motor_file.py`. Nothing here is a
throwaway example: every file is read by code or tests. This is the bundled
fixture corpus (Phase 2.19, Step 129) -- your own personal motor data goes
in the gitignored root `data/` instead, see `data/README.md`.

| file | what it is | who reads it |
|---|---|---|
| `Cesaroni_2060K570-17A.eng` | Real vendor RASP data (Cesaroni K570). | `apps/input/demo_scenario.py` (`DEMO_SCENARIO`, runnable via `python -m examples.worked_scenario`), `tests/test_motor_file.py`, `tests/test_motor_pieces.py`, `apps/motor_selection/scenario_sweep.py` (CLI example in its docstring). Only file exercising the RASP reader, header-derived masses and the `"endpoints"` mass model. |
| `placeholder.csv` | Default demo motor (162.75 N*s). | `apps/common/study_vehicle.py`, `apps/motor_selection/compare_motors.py` (comparison set + `_demo_baseline()`), many `tests/test_*.py` (pins the `_demo_baseline()` equality). |
| `synthetic_small.csv` | Small (E-class) member of the comparison set. | `apps/motor_selection/{motors,compare_motors}.py`, `tests/test_motor_selection.py`, `tests/test_thrust_curve.py` (impulse pin). |
| `synthetic_medium_punchy.csv` | H motor, 169.2 N*s, short high-thrust burn. | Same as above. |
| `synthetic_medium_long.csv` | H motor, 169.5 N*s, long low-thrust burn. | Same as above. |
| `synthetic_large.csv` | Large (I-class) member of the comparison set. | `apps/motor_selection/{motors,compare_motors}.py`, `tests/test_motor_selection.py`, `tests/test_thrust_curve.py` (impulse pin). |

## The four `synthetic_*.csv` are one set

They are ONE deliberate four-motor comparison set (the motor-selection app
ranks them), not four examples of one category. `synthetic_medium_punchy` and
`synthetic_medium_long` are an **equal-impulse pair** (169.2 vs 169.5 N*s) that
isolates burn-profile effects, so removing either destroys the comparison.
Do not trim the set without re-pointing the app and re-pinning
`tests/test_motor_selection.py`.

## Format rules for a new file

- `.csv`: one record, two columns `time_s,thrust_N`, with a `#` comment/header
  line first. Extra columns are ignored; rows are sorted by time and
  de-duplicated. The designation is the filename stem; no metadata.
- `.eng` / `.rasp` (anything not `.csv`): RASP format, one or many records per
  file. Header line: `designation diameter_mm length_mm delays m_prop_kg
  m_total_kg manufacturer`; then `time thrust` rows. `;` comment lines and blank
  lines are ignored. If the first data row has `t > 0`, `(0.0, 0.0)` is
  prepended on load (RASP only).
- In a multi-record library file, `#designation` selects a record, e.g.
  `"Cesaroni_2060K570-17A.eng#K570"`. Without a fragment the file must hold
  exactly one record. An unknown designation raises `KeyError` listing the
  available ones.

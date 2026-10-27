# QA Report - Phase 2.18, Step 122

## Кратко (RU)

Вердикт: **PASS**. Независимо сверил вручную все 5 исходных файлов
(`configs/rockets/demo.py`, `configs/motors/cti_k570.py`, `configs/sites/origin_msl.py`,
`configs/weather/isa_dry_calm.py`, `configs/scenarios/demo.py`) против их построчных
транскрипций в `examples/worked_scenario.py` — расхождений не нашёл, включая значения,
которые в исходниках заданы через "пустой" конструктор (`Site()`, `Weather(...)`) и
сверены против дефолтов `sim/params.py`. Тест `_walk_equal` в
`tests/test_bridge_demo_scenario_equivalence.py` реально рекурсивно обходит все
вложенные группы `Params` и `State` (не только верхний уровень), использует
`np.array_equal` для массивов и называет точный dotted-путь при расхождении — проверил
это намеренной порчей двух независимых полей в копии (вне рабочего дерева, файл не
трогал) — тест поймал оба случая с точным путём (`params.recovery.S`, `params.aero.l_ref`).
`tests/test_worked_scenario_example.py` реально вызывает `python -m
examples.worked_scenario` сабпроцессом (не мок), строки `"Apogee altitude:"`/`"Burnout
time:"` подтверждены по реальному коду `sim/report.py::print_run_summary`. Полный прогон:
**823 passed, 0 failed** (818 база + 5 новых), без известного flaky-креша. Дефектов нет.

## Scope

Independent verification of Step 122 (`3087c28`): `examples/worked_scenario.py` +
`DEMO_SCENARIO` + bridge test proving equivalence to the `configs/` registry path.
Branch `feature/configs-pivot`, repo `D:\Projects - Ongoing\rocket-physics`.

## 1. Hand-diff of the 5 transcribed files vs examples/worked_scenario.py

Read all 5 source files in full and compared every literal field, by hand, against
`examples/worked_scenario.py`.

**rocket (`configs/rockets/demo.py` -> `rocket`)**: `Airframe(m=1.5, I=0.15, l=0.55)` match.
`Lengths(l1=0.3, l2=0.4)` match. `Aero(S=0.00229, d_ref=0.054, l_ref=1.10, C_x=0.5, C_z=0.0,
C_m=0.0)` match. `Sections(L_total=1.10, l_nose=0.25, l_fin_root_fwd=0.92, l_fin_root_aft=1.02,
l_motor_aft=1.10)` match. `Recovery(model="deploy", trigger="apogee", Cd=0.8, S=1.23)` match.
`name="demo"` match.

**motor (`configs/motors/cti_k570.py` -> `motor`)**: `name="cti_k570"`,
`thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng")`, `mass_model="endpoints"` all match.
`notes` text reproduced verbatim character-for-character (checked the full paragraph, including
the numeric figures 212.41 s / 2062.22 N*s / 0.990 kg / 1.685 kg) -- matches.

**site (`configs/sites/origin_msl.py` -> `site`)**: source uses a bare `Site()` (no args) and
bare `LaunchSite(name="origin_msl", site=Site())`. `worked_scenario.py` spells out
`lat0_deg=0.0, lon0_deg=0.0, h0_m=0.0, azimuth_deg=90.0, L_rail=0.0, rail_angle_deg=90.0`.
Cross-checked every one of these 6 values against `sim/params.py`'s own `Site` dataclass
defaults (lines 148-155): all 6 match the library defaults exactly. `name="origin_msl"` matches.

**weather (`configs/weather/isa_dry_calm.py` -> `weather`)**: source uses bare
`Weather(name="isa_dry_calm")`. `worked_scenario.py` spells out `Atmosphere(model="isa",
humid_air=False, dT_K=0.0)`, `Soundings(case="", horizontal_interp="idw", grid_top_m=30000.0,
grid_step_m=100.0, idw_epsilon_m=500.0)`, `Wind(model="none", ref_ms=0.0, dir_deg=0.0,
ref_h_m=10.0, shear_exp=0.143, turbulence_model="none", turbulence_sigma_high_ms=0.0,
turbulence_ref_speed_ms=100.0, turbulence_seed=0)`. Cross-checked all 3+9+2=... (3 Atmosphere +
5 Soundings + 9 Wind = 17) field values against `sim/params.py`'s own dataclass defaults
(lines 158-189): all 17 match exactly. `name="isa_dry_calm"` matches.

**DEMO_SCENARIO (`configs/scenarios/demo.py` -> `DEMO_SCENARIO`)**: `name="demo"`,
`rocket=rocket`, `motor=motor`, `site=site`, `weather=weather`,
`solver=Solver(t_max=1200.0)` all match. `notes` text reproduced verbatim -- matches.

**Verdict on this section: no transcription defects found.** Every literal field in all 5
source files is reproduced correctly (either verbatim where the source spells the value out,
or correctly cross-checked against the library default where the source relies on a bare
constructor).

## 2. `tests/test_bridge_demo_scenario_equivalence.py` -- `_walk_equal` review

Read the file in full. `_walk_equal(a, b, path)`:
- recurses into frozen dataclasses via `dataclasses.fields(a)`, iterating every field by
  name and recursing into its value with an extended dotted path -- confirmed by inspecting
  `sim/params.py`'s `Params` dataclass (16 fields: `weight, g0, lengths, thrust, aero,
  gravity, site, atmosphere, soundings, wind, recovery, control, actuator, roll, inertia,
  sensors, solver`), every group field itself a nested frozen dataclass of scalars (no
  arrays anywhere in `sim/params.py`, confirmed by reading `Weight`/`Thrust`/`Lengths`/
  `Aero`/`Gravity`/`Site`/`Atmosphere`/`Soundings`/`Wind`/`Recovery`/`Solver` in full) --
  so the recursion genuinely walks every nested group, not just the 16 top-level fields.
- recurses into `NamedTuple`s via `_fields` -- `sim/state.py`'s `State` has 9 scalar fields
  (`x, z, vx, vz, theta, omega, m, gamma, omega_x, omega_w` per the live repr captured in
  section 4 below), all walked.
- compares arrays with `np.array_equal` (dead code path for this specific scenario since
  there are no arrays in `Params`/`State`, but present and correct in principle; it does not
  rely on `==` for arrays anywhere, so an ambiguous `__eq__` cannot short-circuit).
- reports the exact dotted path on an `AssertionError`.

Both `registry_config = configs.get("demo")` and `worked_example_config =
assemble(DEMO_SCENARIO)` are genuine calls (not mocked/stubbed).

Ran the file directly, fresh (not relying on any stale/cached result):

```
tests/test_bridge_demo_scenario_equivalence.py::test_params_field_by_field_equivalence PASSED
tests/test_bridge_demo_scenario_equivalence.py::test_s0_field_by_field_equivalence PASSED
tests/test_bridge_demo_scenario_equivalence.py::test_scenario_config_property_matches_assemble PASSED
tests/test_bridge_demo_scenario_equivalence.py::test_demo_scenario_notes_and_name_match_the_registry PASSED
4 passed in 0.84s
```

Note: this file contains **4** test functions, not 5 as the review brief's item 2 implied --
the 5th new test (818 -> 823 baseline delta) lives in
`tests/test_worked_scenario_example.py` (1 test), covered in section 4 below. Not a defect,
just a correction to the review brief's framing; the total new-test count (5) is correct.

## 3. Deliberate-break check (scratch script, not committed)

Wrote a throwaway script (not left in the repo, not a committed test) that takes the REAL
`worked_example_config = assemble(DEMO_SCENARIO)` and `registry_config = configs.get("demo")`,
then builds a `dataclasses.replace`d **copy** of `worked_example_config.params` with one
nested literal deliberately wrong, and feeds that copy through the exact same `_walk_equal`
logic from the test file. No file in the real repo was edited.

Two independent corruptions tried, both two levels deep (group -> field):

```
params.recovery.S: 1.99 != 1.23      <- Recovery.S corrupted from 1.23 to 1.99
params.aero.l_ref: 2.0 != 1.1        <- Aero.l_ref corrupted from 1.10 to 2.0
```

Both caught immediately, both with the exact dotted path named. The bridge test's teeth are
real, not just structurally plausible: it would have caught the exact class of
hand-transcription slip this step is most worried about.

## 4. `tests/test_worked_scenario_example.py`

Read in full. `test_worked_scenario_runs_to_completion_and_prints_a_flight_summary`
genuinely subprocess-invokes `python -m examples.worked_scenario` via `subprocess.run`
(`sys.executable`, real process, `capture_output=True`, `timeout=120`) -- not mocked.
Asserts `returncode == 0`, `"Apogee altitude:"` and `"Burnout time:"` in `stdout`.

Cross-checked both literal strings against `sim/report.py::print_run_summary` (lines
287-290): `print(p); print(s0); print(f"Burnout time: ... s"); print(f"Apogee altitude:
... m")` -- strings match exactly, confirmed by reading the function's real source rather
than trusting the test's assumption.

Ran the test file directly, fresh:
```
tests/test_worked_scenario_example.py::test_worked_scenario_runs_to_completion_and_prints_a_flight_summary PASSED
1 passed in 2.36s
```

Also ran `python -m examples.worked_scenario` directly (not via pytest) to eyeball the real
stdout -- confirms a genuine end-to-end run, a `MachRangeWarning` (expected per the module's
own docstring, Mach 1.75 peak vs the 0.8 credibility limit of the "constant" aero model),
and the summary block:
```
Burnout time:        3.5900 s
Apogee altitude:     5947.0107 m
Apogee time:         29.6144 s
Max speed:           587.5037 m/s
Impact time:         890.8672 s
Downrange at impact: 0.0000 m
```
Both required substrings present; `returncode` implicitly 0 (no exception raised).

## 5. `Scenario.config` property vs `assemble()` direct call

`configs/schema.py` line 360-361: `Scenario.config` is a one-line `@property` that returns
`assemble(self)` -- literally the same function `test_scenario_config_property_matches_assemble`
calls directly as `assemble(DEMO_SCENARIO)`. Confirmed both access paths are exercised and
walked with `_walk_equal` plus a bare `==`. This test is close to tautological given the
property's trivial one-line implementation (there is no logic divergence possible today), but
it is legitimate regression insurance if `.config` is ever changed to do anything other than
delegate straight to `assemble` -- no defect, low marginal value, correctly scoped.

## 6. Full suite

Own clean run, backgrounded (`python -m pytest -q`), actively polled (capped waits,
no passive wait-for-notification) until completion:

```
823 passed, 56 warnings in 803.36s (0:13:23)
```

Matches the expected 818 baseline + 5 new = 823, 0 failed. No occurrence of the known
flaky Windows/scipy `access violation` crash this run; no retry needed. All warnings are
expected `MachRangeWarning`/`AeroRangeWarning` instances from scenarios that intentionally
exceed their aero model's credible range (including the K570 demo's own documented Mach
1.75 peak) -- not new, not related to this diff.

Runtime (803 s) is well above the ~220-390 s baseline noted in `CLAUDE.md`'s environment
pitfalls list for this machine class; did not investigate further since the suite passed
cleanly and this review's scope is correctness, not performance -- flagging only as a
data point in case the orchestrator is tracking suite-speed drift separately.

## Overall verdict: PASS

No defects found. The hand-transcription risk this step was adversarially reviewed for
(a wrong literal silently corrupting downstream physics) did not materialize: every field
in all 5 source files is reproduced correctly in `examples/worked_scenario.py`, and the
bridge test that is supposed to catch exactly this class of slip was confirmed, by a live
deliberate-break exercise, to actually do so with an exact dotted failure path. The
subprocess smoke test and the `Scenario.config`/`assemble` equivalence test are both
genuine (not mocked) and check what they claim to check. Full suite: 823 passed, 0 failed.

No defects to file. No blocker/major/minor issues identified in this step's diff.


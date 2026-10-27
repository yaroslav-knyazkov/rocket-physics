# QA Report — Phase 2.18, Step 124 (CLI-1 pivot, commit 09d9e73)

## Кратко (RU)

Вердикт: **PASS**. Проверены все 9 пунктов задачи (инлайн-константы study_vehicle.py,
DEMO_SCENARIO.config в solve_cda.py, study_vehicle.CONFIG в trade_surface.py, инлайн main() в
compare_configs.py, безопасное удаление apps/common/cli.py, resolve_motor/main в scenario_sweep.py,
диспатч-логика run_motor_sweep.py — реально прогнана оба пути, изменения тестов). Все утверждения
диффа подтверждены самостоятельно (чтением реальных файлов конфигов, grep по всему репо, запуском
кода). Блокеров и дефектов не найдено. Полный прогон: **821 passed, 0 failed, 800.42s** — ровно
823 - 2 удалённых теста, числовые пины не сдвинулись.

## Verdict: PASS

No defects found (blocker or minor). All 9 verification points in the task confirmed independently.

## Scope

Independent verification of Step 124 (commit `09d9e73`, branch `feature/configs-pivot`), implementing D-139/"CLI-1": drop `--config`/`--list-configs`/`--scenario` registry resolution from every app in favor of hardcoded vehicle/scenario constants. Steps 120-123 already QA-PASSed, not re-reviewed. `configs/*` registry itself untouched (Step 125 archives it).

`git show 09d9e73 --stat` confirms the 10 touched files match the task's inventory exactly:
`apps/airbrake_sizing/solve_cda.py`, `apps/common/cli.py` (deleted), `apps/common/study_vehicle.py`,
`apps/motor_selection/scenario_sweep.py`, `apps/weight_aero_tradeoff/compare_configs.py`,
`apps/weight_aero_tradeoff/trade_surface.py`, `run_motor_sweep.py`, `run_trade.py`,
`tests/test_scenario_sweep.py`, `tests/test_weight_aero_tradeoff.py`.

## 1. apps/common/study_vehicle.py — inlined constants

Read both real registry files (`configs/sites/origin_msl.py`, `configs/weather/isa_dry_calm.py`) and
compared field-for-field against the new inlined constants:

- `_ORIGIN_MSL_SITE = LaunchSite(name="origin_msl", site=Site())` — exact match to
  `origin_msl.SITE = LaunchSite(name="origin_msl", site=Site())`.
- `_ISA_DRY_CALM_WEATHER = Weather(name="isa_dry_calm")` — exact match to
  `isa_dry_calm.WEATHER = Weather(name="isa_dry_calm")`.

Both argument-free constructions, matching the comment's claim. **PASS.**

## 2. apps/airbrake_sizing/solve_cda.py — DEMO_SCENARIO.config

`add_config_arg`/`resolve_config` removed; `cfg = DEMO_SCENARIO.config` replaces
`cfg = resolve_config(args)` with `add_config_arg(parser, default="demo")`. Traced
`resolve_config`'s old no-`--list-configs`, default-`"demo"` path: `configs.get("demo")`, which resolves
through `configs/scenarios/demo.py`'s registered `SCENARIO`/`CONFIG`. `examples/worked_scenario.py`
states `DEMO_SCENARIO` is "configs/scenarios/demo.py's SCENARIO, field-for-field" (Step 122's own
bridge-test claim, not re-derived here per task scope) — `.config` is `Scenario`'s own computed
property, used correctly as a drop-in. **PASS.**

## 3. apps/weight_aero_tradeoff/trade_surface.py — study_vehicle.CONFIG

Old: `add_config_arg(parser, default=None)` + `resolve_config(args, fallback=study_vehicle.CONFIG)`.
Reading `resolve_config`'s body (`apps/common/cli.py`, pre-deletion, read via
`git show feature/sim-paper-alignment:apps/common/cli.py`): with `args.config is None` (the only path
this app's own tests exercise, no `--config` flag ever passed in `tests/test_weight_aero_tradeoff.py`'s
surface tests) it returns `fallback` unconditionally. New code: `cfg = study_vehicle.CONFIG` — exact
match. **PASS.**

## 4. apps/weight_aero_tradeoff/compare_configs.py — inline main()

`_resolve_configs`/`_parse_config_names` deleted entirely along with the `--config`/`--list-configs`
CLI arguments. New `main()`:
```
baseline = study_vehicle.CONFIG
cfgs = [baseline] + [variant.apply(baseline) for variant in SCENARIOS]
```
This is byte-for-byte the `spec is None` branch of the old `_resolve_configs` (the only branch this
app's surviving test, `test_compare_main_default_scenarios_writes_artifacts`, exercises — confirmed by
running it, see §8 below). `grep -n "configs\."` over the file post-diff shows only
`from configs.schema import Config` remains (a type import, not registry access) — `import configs` is
genuinely gone and nothing else in the file needed it. **PASS.**

## 5. apps/common/cli.py deletion — repo-wide reference check

`Grep` for `add_config_arg|resolve_config|apps\.common\.cli` across the whole repo (code + tests, no
glob restriction): only 4 hits, all in `dev/docs/*.md` (historical architecture docs referencing the
feature's own history, e.g. `architecture-30-apps-4-5-and-configs.md`). Zero remaining references in
any `.py` file. Deletion is safe. **PASS.**

## 6. apps/motor_selection/scenario_sweep.py — resolve_motor + main()

`resolve_motor`'s registry branch (`if spec in motor_registry.MOTORS: return motor_registry.get(spec)`,
plus the `from configs import motors as motor_registry` import) is fully removed. Read the current full
function body: the RASP-fallback branch (`filename = spec.partition("#")[0]`; `ext = os.path.splitext...`;
`if ext != ".csv" and os.path.exists(...): return Motor(...)`) is byte-identical to the pre-diff version
— only the registry branch above it and the final `KeyError` message text changed. `main()` no longer
references `args.scenario` anywhere; `scenario = DEMO_SCENARIO` is now a plain constant, and the csv/png
filenames switched from `f"motor_sweep_{args.scenario}..."` to `f"motor_sweep_{DEMO_SCENARIO.name}..."`.
**PASS.**

## 7. run_motor_sweep.py — dispatch discriminator

Confirmed `apps/motor_selection/compare_motors.py::main()` is `def main() -> None:` — zero CLI
arguments, never touches `sys.argv`, so a `--motors` check anywhere on the command line cannot
collide with legacy App 3's own argument space (it has none). Actually ran both dispatch paths:

- `python run_motor_sweep.py` (no args) → legacy App 3's `compare_motors` ranked table, wrote
  `output/motor_selection.csv`/`_overlay.png`. Correct target reached.
- `python run_motor_sweep.py --motors Cesaroni_2060K570-17A.eng --target 5000` → scenario-sweep v2,
  wrote `output/motor_sweep_demo.csv`/`_overlay.png` (uses `DEMO_SCENARIO.name` = "demo" as predicted).
  Correct target reached.

Additional empirical sanity check for item 2's `DEMO_SCENARIO.config` equivalence (beyond reading Step
122's own claim): `DEMO_SCENARIO.config == configs.scenarios.demo.SCENARIO.config` evaluates `True` at
runtime.

**PASS.**

## 8. Test changes

- `tests/test_weight_aero_tradeoff.py`: read both deleted tests in full diff context.
  `test_compare_main_comma_separated_registry_names_bypasses_scenarios` exercised `--config demo,toy_05kg`
  (the comma-separated-names registry-bypass feature) exclusively. `test_compare_single_name_baseline_
  refuses_mass_model_on_config` exercised `--config demo` (single registered name as baseline) exclusively.
  Neither touched anything else; the surviving `test_compare_main_default_scenarios_writes_artifacts`
  (no `--config`, i.e. the only path `main()` keeps) is unchanged in the diff.
- `tests/test_scenario_sweep.py`: `--scenario demo` dropped from the CLI test; `--motors cti_k570`
  (registered name) → `--motors Cesaroni_2060K570-17A.eng` (the real RASP file, same motor);
  `test_cli_unknown_motor_lists_available`'s `KeyError` match updated from `"cti_k570"` (old
  "registered:" list text) to `"unknown motor 'nope'"` (new message), consistent with the registry
  branch's removal.
- Ran both files directly: `python -m pytest tests/test_scenario_sweep.py tests/test_weight_aero_tradeoff.py -q`
  → **32 passed, 0 failed, 5 warnings (151.32s)**, warnings are pre-existing `AeroRangeWarning`/
  `MachRangeWarning` unrelated to this diff.

**PASS.**

## 9. Full suite — clean run

Own clean run, backgrounded, polled in capped waits (no passive blocking longer than ~230s per poll):

```
python -m pytest -q
...
821 passed, 55 warnings in 800.42s (0:13:20)
[exited with code 0]
```

**821 passed, 0 failed** — exactly matches the expected 823 baseline − 2 deleted tests. All 55 warnings
are pre-existing `AeroRangeWarning`/`MachRangeWarning` instrumentation unrelated to this diff (same
warnings seen in the targeted run in §8). No numeric-pin movement observed (no assertion failures of
any kind). Runtime (800s) is within the documented slow-environment range (~780-800s), not a regression
signal per CLAUDE.md's own note on this project's suite speed.

**PASS.**


# QA Report — Phase 2.18, Step 123

## Кратко (RU)

- Вердикт: **PASS**. Шаг 123 (коммит 5503669) переключает 12 файлов с `configs.get("demo")` /
  `configs.scenarios.demo.SCENARIO` на `examples.worked_scenario.DEMO_SCENARIO`.
- Проверен полный дифф (374feff -> 5503669) построчно: ровно 12 файлов, все изменения — механическая замена
  источника импорта, без изменений логики и без ослабления ассертов сверх двух ожидаемых строковых правок в
  `tests/test_configs.py`.
- Инлайненные `_ORIGIN_MSL_SITE`/`_ISA_DRY_CALM_WEATHER` в `tests/config_variants.py` побайтово совпадают с
  живыми `configs/sites/origin_msl.py`/`configs/weather/isa_dry_calm.py`.
- 4 файла, которые разработчик ранее ошибочно считал несуществующими (`test_aero_oob.py`, `test_aero_fb.py`,
  `test_qa_phase217_m1.py`, `test_step114_review_fixes.py`), независимо подтверждены: присутствуют в git,
  корректно переключены, без остаточных ссылок на старый источник.
- Полный прогон тестов: **823 passed, 0 failed**, 785.11s — совпадает с ожидаемым числом из Step 122, ни один
  числовой пин не сдвинулся. Дефектов не найдено.

## Scope

Independent verification of Step 123 (commit 5503669, branch feature/configs-pivot): repointing 12 files
from `configs.get("demo")` / `configs.scenarios.demo.SCENARIO` onto `examples.worked_scenario.DEMO_SCENARIO`.
Steps 120-122 already QA-PASSed and are out of scope.

## 1. Diff content review (commit 374feff -> 5503669)

`git diff 374feff 5503669 --stat` shows exactly the 12 files listed in the task, no more, no fewer:
`apps/cfd_conditions/select_conditions.py`, `run.py`, `tests/config_variants.py`, `tests/test_aero_fb.py`,
`tests/test_aero_oob.py`, `tests/test_airbrake_sizing.py`, `tests/test_configs.py`, `tests/test_dynamics.py`,
`tests/test_mach_warning.py`, `tests/test_motor_selection.py`, `tests/test_qa_phase217_m1.py`,
`tests/test_step114_review_fixes.py`. 12 files changed, 47 insertions(+), 35 deletions(-).

Read every hunk in full. All are one of the two expected mechanical patterns:
- `import configs` / `cfg = configs.get("demo")` -> `from examples.worked_scenario import DEMO_SCENARIO` /
  `cfg = DEMO_SCENARIO.config` (run.py, select_conditions.py, test_mach_warning.py, test_motor_selection.py,
  test_dynamics.py (x2), test_airbrake_sizing.py (import + 2 call sites)).
- `from configs.scenarios.demo import SCENARIO as DEMO` -> `from examples.worked_scenario import
  DEMO_SCENARIO as DEMO` (test_aero_fb.py, test_aero_oob.py, test_qa_phase217_m1.py,
  test_step114_review_fixes.py).

`tests/test_configs.py`: exactly the two expected assertion updates --
`assert 'configs.get("demo")' in _RUN_PY` -> `assert "DEMO_SCENARIO" in _RUN_PY` and the matching
`_SELECT_CONDITIONS_PY` assertion. The `Weight(` / `math.pi / 2` guard lines directly below both are
byte-identical, untouched. No assertion weakening beyond the sanctioned string swap.

`tests/config_variants.py`: the only substantive change, it inlines `_ORIGIN_MSL_SITE` /
`_ISA_DRY_CALM_WEATHER` instead of importing `configs.sites.origin_msl` / `configs.weather.isa_dry_calm`
(see section 2). Docstring and inline comment both correctly explain the change and cite Step 123/D-139/D-140.

No logic changes, no renamed test functions, no changed assertions beyond what's listed above, no touched
numeric literals in any of the 12 files. Comments updated to cite Step 123/D-139/D-140 are appropriately
scoped (old Step 90 references replaced with accurate new ones where the code they describe changed).

**Verdict: clean mechanical swap, as advertised.**

## 2. Inlined site/weather vs. live registry originals

Read both live registry files:
- `configs/sites/origin_msl.py`: `SITE = LaunchSite(name="origin_msl", site=Site())` -- argument-free `Site()`,
  by deliberate design per its docstring (tracks `sim/params.py` defaults, doesn't freeze them).
- `configs/weather/isa_dry_calm.py`: `WEATHER = Weather(name="isa_dry_calm")` -- same deliberate
  argument-free pattern.

`tests/config_variants.py` inlines:
```
_ORIGIN_MSL_SITE = LaunchSite(name="origin_msl", site=Site())
_ISA_DRY_CALM_WEATHER = Weather(name="isa_dry_calm")
```
Byte-for-byte identical constructor calls (`LaunchSite`/`Weather`/`Site` all imported from the same
`configs.schema`/`sim.params` sources both files use). **Confirmed genuinely identical** -- no silent
divergence introduced. The inline comment in `config_variants.py` correctly explains the no-arguments
convention is "a literal copy of that choice, not a new one."

## 3. Blast radius check

`git diff 374feff 5503669 --stat` (section 1) confirms the diff touches only the 12 named files -- no
changes to `apps/common/cli.py`, `apps/common/study_vehicle.py`,
`apps/weight_aero_tradeoff/compare_configs.py`, `tests/test_weight_aero_tradeoff.py`,
`apps/motor_selection/scenario_sweep.py`, `tests/test_scenario_sweep.py`, `tests/test_motor_pieces.py`,
`tests/test_config_registries.py`, `tests/test_config_migration.py`, or anything under `configs/`.
Residual `configs.scenarios.demo`/`configs.get("demo")` references remain (by design, out of scope) in
`tests/test_configs.py` (registry-still-works check at L220, comment at L248), `tests/test_scenario_sweep.py`,
`tests/test_bridge_demo_scenario_equivalence.py`, `examples/worked_scenario.py` (builds DEMO_SCENARIO from
the registry, that's the point), `tests/test_weight_aero_tradeoff.py`, `tests/test_config_migration.py` --
all expected, none are among the 12 files this step was supposed to touch.

## 4. Four previously-disputed files

`git ls-files` confirms all 4 are tracked: `tests/test_aero_fb.py`, `tests/test_aero_oob.py`,
`tests/test_qa_phase217_m1.py`, `tests/test_step114_review_fixes.py`. Diff content (section 1) confirms
all 4 are correctly repointed to `from examples.worked_scenario import DEMO_SCENARIO as DEMO`, and
`Grep` confirms zero residual `configs.scenarios.demo`/`configs.get("demo")` references in any of the 4.
**The correction stuck.**

## 5. Full suite — independent clean run

Backgrounded `python -m pytest -q`, polled in capped waits (not a single blocking call). Result:

```
823 passed, 56 warnings in 785.11s (0:13:05)
```

Exit code 0, zero failures, zero errors. Matches Step 122's expected 823 exactly (this step repoints
imports only, adds/removes no tests). The 56 warnings are all pre-existing, expected runtime warnings
(`MachRangeWarning`, `AeroRangeWarning`) unrelated to this diff, consistent with the project's known pattern.
Duration (785.11s) falls within the "unusually slow today" range the developer flagged -- not read as a
defect signal per the task's own framing.

No numeric-pin regressions observed (suite would have failed loudly on any `assert ... ==` pin mismatch;
none occurred).

## Overall verdict

**PASS.** All 5 verification points independently confirmed. No defects found (blocker, major, or minor).
Step 123 is a clean, correctly-scoped mechanical import-source swap across exactly the 12 named files, with
the two previously-flagged risk areas (inlined site/weather fidelity, the 4 disputed files) explicitly
re-checked and confirmed sound.

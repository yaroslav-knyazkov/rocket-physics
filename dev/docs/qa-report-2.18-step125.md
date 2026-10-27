# QA Report — Phase 2.18, Step 125 (final pivot step: registry removal)

## Кратко (RU)

- Вердикт: **PASS**. Шаг 125 (финальный шаг пивота Phase 2.18) корректно убирает реестр `configs/{rockets,sites,weather,motors,scenarios}/` из живого пути импорта, перенеся его в архив, и триажит связанные тесты.
- Самостоятельно (не на веру) перепроверено: 15 файлов архивированы как переименования (не delete+add), `configs/` теперь только `__init__.py` + `schema.py`; `schema.py` байт-в-байт не менялся за весь пивот; все 20 re-export имён в шиме реально резолвятся и указывают на правильные исходные модули (проверено импортом, не чтением кода).
- Триаж тестов перепроверен по каждому файлу: пины физики (`I_sp=212.41`, составные массы, скорость приземления ~5.97 м/с) перезапущены лично и совпадают; удалённые тесты — реально чисто механика реестра либо явно временный "bridge"-тест, либо документационная конвенция, которая не переносится (честно помечено как backlog, не скрыто).
- Два "хвоста" из шагов 123/124 (`configs.get("demo")`, `from configs.scenarios.demo import ...`) подтверждённо исчезли; grep по всему репо вне `dev/archive/` — ноль живых обращений к реестру.
- Все 5 продуктовых точек входа запущены лично, завершаются с кодом 0, числа согласуются друг с другом (apogee 5947.01 м везде).
- Полный прогон тестов — **761 passed, 0 failed**, точно совпадает с ожиданием.
- Найдено 2 некритичных пункта (не блокеры): (1) косметически устаревшие имена двух тестов в `tests/test_configs.py` (сами проверки корректны); (2) честно раскрытый пробел покрытия — нет замены для `test_template_docs.py`'s REQ/OPT-проверки под новый формат `examples/worked_scenario.py` (уже в backlog).
- Вся фаза 2.18 готова для решения пользователя о мерже.

## Scope

Step 125 physically removes `configs/{rockets,sites,weather,motors,scenarios}/` from the live import
path (archived to `dev/archive/configs-registry-2026-10/`), and triages registry-coupled tests. This
report independently re-verifies the developer's and orchestrator's claims per the QA prompt's 7
checklist items. Steps 120-124 are out of scope (already QA-PASSed).

Commit under review: `c858381` (branch `feature/configs-pivot`). Parent/pre-pivot tag:
`pre-pivot-configs-registry` at `9c3f203`.

## 1. The archive

Confirmed with `git diff-tree --no-commit-id --name-status -r c858381 -M100`: exactly 15 `R100`
renames into `dev/archive/configs-registry-2026-10/configs/...`, relative path preserved
(`motors/`, `rockets/`, `scenarios/`, `sites/`, `weather/`, 3 files each: `__init__.py`, one real
instance, one `_TEMPLATE_*.py`). Not delete+add — git detected these as 100% identical renames, so
blame/history survives.

`ls configs/` -> only `__init__.py`, `schema.py`, `__pycache__/` (gitignored). No leftover
subpackage dirs, no stray files. `pre-pivot-configs-registry` tag confirmed present and resolves to
`9c3f203`.

Archive README judged: genuinely useful, not padding. Explains what the convention was (file +
registry per piece kind), the 15 files by name, which decisions built it (D-45..D-78, with doc
pointers), which decisions replaced it (D-137..D-142), what replaced it (`examples/worked_scenario.py`,
the Cfg-1 shim), and two concrete resurrection paths (read in place, or `git show
pre-pivot-configs-registry:configs/motors/cti_k570.py`). Also honestly documents a known staleness
caveat (archived modules' `from configs.schema import ...` will rot if `schema.py` ever moves) instead
of pretending the archive stays evergreen. No defects found here.

## 2. configs/__init__.py shim

Read the file; then independently verified by import, not by reading source: `configs.__all__` lists
20 names, all 20 resolve with no `AttributeError`. Followed up with an identity check
(`getattr(configs, n) is getattr(configs.schema, n)` for the 10 schema names, `is getattr(sim.params, n)`
for the 10 params names) — all 20 pass, so every claimed re-export genuinely is the object from the
module claimed, not a shadowing redefinition.

`git diff feature/sim-paper-alignment feature/configs-pivot -- configs/schema.py` -> empty. `schema.py`
is byte-identical across the whole pivot branch, confirming the commit message's claim that it was
never registry-coupled and untouched by Step 125.

No defects found in section 2.

## 3. Test suite triage

### tests/test_demo_physics.py (renamed from test_config_migration.py)

Read the whole file (217 lines). Ran it standalone: `14 passed` (0.75-3.35s, 3 MachRangeWarning
suppressions/expected). Independently re-ran, not just read, the following pinned values, all unchanged:
- `test_demo_isp_eff_matches_f5`: `DEMO_SCENARIO.config.params.weight.I_sp == pytest.approx(212.41, abs=0.01)` — passed. Independently cross-checked against `python -m examples.worked_scenario`'s own printed `Params(...)` dump: `I_sp=212.41234625009926` — matches.
- `test_demo_composed_masses`: `weight.m`/`weight.m_d` composed-mass pins against `airframe.m + 1.685`/`airframe.m + 0.695` — passed.
- `test_demo_lands_under_its_main_canopy`: canopy landing speed `5.5 <= v_impact <= 6.5` (comment cites "measured 5.97 m/s at t ~ 890.9 s") — passed; cross-checked `run.py`'s own output: `Impact time: 890.8672 s` — matches the cited ~890.9 s.
- `test_demo_burnout_mass_lands_on_m_f` (the D-59 burnout pin) and `test_demo_isp_and_endpoints_motors_agree_on_apogee` (the D-59 apogee-equivalence pin) — both passed.

Confirmed `apps/common/study_vehicle.py` and `tests/config_variants.py` (both read in full) import only
`configs.schema` and `sim.params` — zero references to the archived registry subpackages. The
untouched tests (`test_demo_75mm_rocket_groups_equal_demo_baseline`, `test_toy_05kg_rocket_groups_equal_toy_05kg_literal`,
`test_every_test_variant_flies`, the three `highland` tests) read exclusively from `study_vehicle`/
`config_variants`, confirmed never registry-coupled — correctly left untouched.

### tests/test_motor_pieces.py

`git diff 9c3f203 c858381` reviewed in full. The lifted D-59 test
(`test_cti_k570_and_cti_k570_isp_compositions_agree_d59_equivalence`) now imports
`examples.worked_scenario.motor` and `tests.config_variants.CTI_K570_ISP`, composes both via
`_weight_from_pieces` against a synthetic `Airframe`/`Sections`, asserts `m`/`m_d`/`l_d`/`I_d`/`I_sp`
agree to 1e-3 rel. Ran the file standalone: `17 passed in 0.75s`, including this test.

The 2 deleted tests read at the parent commit:
- `test_import_configs_reads_motor_files_only_under_a_mass_model` (D-70a): monkeypatches
  `sim.motor_file.load`/`records`, force-reimports the whole `configs` tree from scratch, asserts only
  `cti_k570`'s own file is read. Pure registry-mechanism (walks `configs.names()`); with no registry
  left this assertion is vacuously true for nothing, confirmed safe to drop — no physics content.
- `test_configs_names_after_step_91`: `assert set(configs.names()) == {"demo"}` — pure registry
  cardinality check, confirmed safe to drop.

### tests/test_configs.py

`git diff 9c3f203 c858381` reviewed in full. 5 deleted tests confirmed registry-only:
`test_registry_keys_equal_module_basenames`, `test_registry_has_no_duplicate_names`,
`test_names_lists_every_registered_config`, `test_get_unknown_name_raises_keyerror_listing_every_name`,
`test_every_registered_config_flies` — all walk `configs._MODULES`/`configs.CONFIGS`/`configs.names()`/
`configs.get()`, none asserts anything about physical values. Confirmed safe.

The 2 adapted fresh-interpreter tests: read `_run_fresh_interpreter` (`subprocess.run([sys.executable,
"-c", code], ...); assert result.returncode == 0`). Independently stress-tested this mechanism myself
(outside the repo's test files) by feeding it code that raises `ImportError` after `import configs` —
confirmed `returncode != 0`, i.e. the assertion genuinely fails on a real circular-import regression, not
a vacuous pass. `test_import_worked_scenario_first_has_no_circular_import` now runs
`import examples.worked_scenario; print(examples.worked_scenario.DEMO_SCENARIO.name)` (first import is
`examples.worked_scenario`, not `configs`); `test_import_configs_package_first_has_no_circular_import`
now runs `import configs; print(configs.Scenario)` (first import is `configs`, checked attribute swapped
from the now-gone `configs.names()` to `configs.Scenario`, which exists both before and after the Step-125
shim swap). Ran the file standalone: `14 passed in 1.89s`.

### tests/test_config_registries.py, tests/test_template_docs.py, tests/test_bridge_demo_scenario_equivalence.py (all deleted)

Diffed against parent `9c3f203` and read each file's assertions:
- `tests/test_config_registries.py` (229 lines, ~13 tests): the great majority (registry-keys-equal-
  basenames, no-duplicate-names, names()-lists-every-piece, get()-KeyError-message, 5x no-circular-import,
  template-absent-from-registry) are pure registry mechanism parametrised over
  rockets/sites/weather/motors/scenarios — vacuous (c) once there's no registry. Two content-bearing
  tests found: `test_origin_msl_site_equals_bare_site_default` and
  `test_isa_dry_calm_weather_equals_bare_defaults`, asserting the registry's `origin_msl`/`isa_dry_calm`
  pieces equal bare `Site()`/`Atmosphere()`/`Soundings()`/`Wind()` defaults. Checked `apps/common/
  study_vehicle.py`/`tests/config_variants.py`'s replacements: both now construct
  `LaunchSite(name="origin_msl", site=Site())` / `Weather(name="isa_dry_calm")` with zero overrides — the
  equivalence is now a tautology by construction, not something that can silently drift, so losing the
  explicit check is (b) genuinely vacuous, not a coverage loss. The D-59 equivalence test in this file was
  the one lifted into `test_motor_pieces.py` (confirmed above) — correctly not double-deleted.
- `tests/test_template_docs.py`: Step-82 doc-table-vs-dataclass-fields cross-check specific to the
  `### TypeName` markdown-table convention inside the now-archived `_TEMPLATE_*.py` docstrings. Confirmed
  category (c) — a documentation-convention check that cannot transfer to `examples/worked_scenario.py`'s
  inline-comment convention (`# REQ|OPT, ...`) without being rewritten from scratch. The commit message
  flags this honestly as a backlog candidate rather than silently dropping it — **noted as a minor,
  disclosed gap** (see Defects below), not a blocker: no automated check currently verifies every REQ
  field in `examples/worked_scenario.py` is actually documented.
- `tests/test_bridge_demo_scenario_equivalence.py`: read in full; its own docstring says verbatim
  "TEMPORARY bridge test -- DELETE at Step 125" and explains it exists only to catch a hand-transcription
  slip during Step 122's registry->examples copy, with nothing left to bridge once `configs.get("demo")`
  stops existing. Category (a)/(b) — explicitly temporary by design, and its equivalence claim was already
  proven at Step 122 (this is corroborated independently by `test_demo_physics.py`'s own pins reproducing
  the same numbers post-pivot, confirmed above). Correctly deleted.

## 4. Stray Step-123/124 fixes + repo-wide grep

`git diff 9c3f203 c858381 -- tests/test_weight_aero_tradeoff.py tests/test_scenario_sweep.py` confirms
both stray references fixed: `configs.get("demo")` -> `DEMO_SCENARIO.config` in
`test_weight_aero_tradeoff.py`; `from configs.scenarios.demo import SCENARIO as DEMO` -> `from
examples.worked_scenario import DEMO_SCENARIO as DEMO` in `test_scenario_sweep.py`. Ran both files plus
`test_packaging_boundary.py` together: **34 passed in 154.07s**, 0 failed.

Repo-wide grep (excluding `dev/archive/`) for `configs.scenarios.demo`, `configs.get(`, `configs.rockets`,
`configs.motors`, `configs.sites`, `configs.weather`: every hit outside `dev/archive/` is either (a)
historical doc/commit-message/journal text (`dev/docs/architecture-31...md`, `qa-report-2.18-step123/124.md`,
`roadmap.md`), or (b) a comment/docstring explaining history inside `configs/__init__.py`,
`configs/schema.py`, `tests/test_demo_physics.py`, `tests/test_configs.py`, `examples/worked_scenario.py`.
Zero live code hits (no actual `import`/attribute-access statements) anywhere outside `dev/archive/`.
**One cosmetic defect found**: `tests/test_configs.py`'s `test_run_py_sources_its_scenario_from_configs_get_demo`
and `test_select_conditions_py_sources_its_scenario_from_configs_get_demo` are stale test *names* left over
from before Step 123/124 repointed `run.py`/`select_conditions.py` off the registry — the test bodies
correctly check for `"DEMO_SCENARIO" in <file text>`, not `configs.get`, so there is no functional bug,
just a misleading name (minor, cosmetic, pre-existed Step 125's own scope — not introduced by this step).

## 5. Production entry points

All 5 run clean, exit 0, independently executed (not trusted from the commit message):
- `python run.py` -> apogee 5947.0107 m, impact time 890.8672 s (matches the `test_demo_lands_under_its_main_canopy` comment's "~890.9 s" and `I_sp`/mass pins cross-checked above).
- `python -m examples.worked_scenario` -> printed `Params(...)` dump shows `I_sp=212.41234625009926` and the same apogee/impact numbers as `run.py` (5947.0107 m / 890.8672 s) -- confirms `run.py` and the worked example are genuinely sourcing the same scenario.
- `python run_motor_sweep.py --motors Cesaroni_2060K570-17A.eng --target 5000` -> one-row sweep table, `status=ok`, apogee 5947.0 m, saved CSV + overlay PNG.
- `python run_trade.py` -> 121-point trade surface grid ("0 of 121 grid points did not fly"), saved CSV + contour PNG, ~48s runtime.
- `python -m apps.airbrake_sizing.solve_cda` -> converged in 25 simulator runs, achieved apogee 3850.00 m (error -1.00e-07 m), saved CSV + overlay PNG.

No defects beyond the one cosmetic item noted in section 4.

## 6. Full suite

Own clean run, backgrounded (`run_in_background`), polled in capped loops (no passive wait). Result:

```
761 passed, 53 warnings in 821.17s (0:13:41)
```

**Matches the expected 761 passed, 0 failed exactly.** (A separate 34-test targeted run of
`test_weight_aero_tradeoff.py`+`test_scenario_sweep.py`+`test_packaging_boundary.py` was in flight
concurrently during the first part of this run, which is why wall-clock is ~821s rather than the
~220-390s baseline noted in CLAUDE.md -- CPU contention, not a regression; no test failures, no flaky
native crash observed this run.) One warning line surfaced the repo's already-known stale-bytecode
artifact (`D:\Projects - Ongoing\rocket-trajectory\tests\test_plotting.py:297` -- old pre-rename path
baked into a cached warning stack, documented in CLAUDE.md's project profile as a known, harmless
oddity) -- not a new finding, not investigated further per existing guidance.

## 7. Package boundary sanity

`pyproject.toml`'s `[tool.setuptools] packages = ["sim", "configs"]` (line 15, comment: "CORE only --
apps/, tests/, tools/ deliberately absent") still makes sense post-pivot -- `configs/` now has even less
surface area (shim + schema.py only) than before. `tests/test_packaging_boundary.py` ran as part of the
34-test targeted batch in section 4: passed (bundled into "34 passed in 154.07s", 0 failed).

## Overall verdict

**PASS.** No blocker or major defects found. One pre-existing minor/cosmetic defect (stale test names
in `tests/test_configs.py`, not introduced by Step 125, not a functional bug) and one disclosed,
backlog-flagged coverage gap (`tests/test_template_docs.py`'s REQ/OPT-completeness check has no
replacement yet for `examples/worked_scenario.py`'s format -- already called out honestly in the
Step-125 commit message as a backlog candidate, not hidden).

This is the final step of the Phase 2.18 pivot. Combined with Steps 120-124 already QA-PASSed, and this
step's own independent re-verification of the archive, the shim, every test-triage disposition, the two
carried-over stray fixes, all 5 production entry points, the full suite (761/0), and the packaging
boundary -- **the whole phase is ready for the orchestrator to bring to the user for the merge
decision.**


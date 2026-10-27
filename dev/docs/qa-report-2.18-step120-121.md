# QA Report — Phase 2.18, Steps 120-121 (configs pivot: datafiles.py + packaging)

## Кратко (RU)

- Вердикт: **PASS**, блокеров/major/minor дефектов не найдено.
- Step 120 (`sim/datafiles.py` + 3 рикейбла загрузчиков): правила резолва точно соответствуют докстрингу; все 4 `cache_clear`-атрибута сохранены и реально чистят нужный кэш; `_motors_path` — рабочий бэккомпат-шим, оба внешних вызывающих файла подтверждены grep'ом; порядок `spec.partition("#")` до резолва сохранён (важно для RASP-фрагментов); claim "нулевое изменение поведения" для bare-имён независимо перепроверен вручную (точное совпадение путей старой/новой формулы по 3 видам данных).
- Новый `tests/test_datafiles.py` (16 тестов) — реальные, не тавтологичные проверки всех 3 правил + regression-тест на POSIX-абсолютный путь + end-to-end с `#designation`-фрагментом через внешний абсолютный путь. Прогнан изолированно — 18/18 passed.
- Step 121 (`pyproject.toml`): `packages = ["sim", "configs"]` точно как заявлено (без apps/tests/tools); зависимости не потеряны при переносе из `requirements.txt`; `tests/test_packaging_boundary.py` реально парсит боевой `pyproject.toml` через `tomllib`, не фикстуру. `python run.py` и точечные тесты работают без изменений с `pyproject.toml` в корне.
- Полный прогон (мой собственный, из чистого состояния): **818 passed, 0 failed**, 56 warnings, 801.76s — точное совпадение с ожидаемым числом (800 baseline + 18 new). Известный flaky access-violation не встретился.
- Единственное замечание не-дефект: ошибка-сообщения в `_load_table`/`_read_csv`/`_read_rasp` теперь содержат резолвленный путь вместо голого имени файла — проверено, что это не ломает существующие `assert name in message` тесты Step 115 (резолвленный путь оканчивается точно на исходное имя, substring-проверка проходит).

## Scope

Independent verification of:
- Step 120 (`25f626d`): `sim/datafiles.py` + rewires in `sim/motor_file.py`, `sim/aero.py`, `sim/soundings.py`, new `tests/test_datafiles.py`.
- Step 121 (`3bc407e`): `pyproject.toml`, `requirements.txt`, new `tests/test_packaging_boundary.py`.
- `ecbb016` (docs-only, spot-check).

Branch: `feature/configs-pivot`, 3 commits ahead of `feature/sim-paper-alignment`.

## ecbb016 (docs-only)

Confirmed via `git show --stat ecbb016`: 2 files changed, both under `dev/docs/` (`configs-layout-analysis.md`, `pivot-configs-and-packaging-analysis.md`), +1172/-0, no code files touched. Docs-only as claimed.

## Step 120 -- `sim/datafiles.py`

Read the full file (56 lines). `resolve(given, kind)`:
```python
if os.path.isabs(given):
    return given
if os.sep in given or "/" in given:
    return os.path.abspath(given)
return os.path.join(_BUNDLED, kind, given)
```
Matches the docstring's 3 rules exactly, in the stated priority order. `_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")` -- from `sim/datafiles.py`'s own location (`<repo>/sim/datafiles.py`), one `dirname` up is `<repo>/sim`, two is `<repo>`, `+"data"` = `<repo>/data`. Correct, matches the pre-existing convention used by the 3 loaders before this step.

### Call-site rewires (`git diff feature/sim-paper-alignment feature/configs-pivot -- sim/motor_file.py sim/aero.py sim/soundings.py`)

- **`sim/aero.py`**: `_load_table` split into `_load_table_impl(path)` (uncached body) + `_load_table_cached = functools.lru_cache(...)(_load_table_impl)`, with a thin `_load_table(name)` wrapper that calls `datafiles.resolve(name, "aero")` first, then the cached impl on the resolved path. `_load_table.cache_clear = _load_table_cached.cache_clear` preserves the attribute existing tests call. Error messages inside the impl now reference the resolved `path` instead of the raw `name` -- confirmed harmless (see below).
- **`sim/soundings.py`**: same split pattern (`_load_case_impl(case, case_dir)` / `_load_case_cached` / `load_case(case)` wrapper). Cache is keyed on `(case, case_dir)` where `case_dir` is the *resolved* absolute directory -- satisfies the "keyed on resolved path, not raw string" requirement (the raw `case` string rides along only for the `FileNotFoundError` message). `load_case.cache_clear` preserved.
- **`sim/motor_file.py`**: same pattern for both `records()` (-> `_records_impl(abspath)` / `_records_cached`) and `load()` (-> `_load_impl(abspath, fragment)` / `_load_cached`). Confirmed `load()`'s `spec.partition("#")` still happens **before** `datafiles.resolve(filename, "motors")` -- fragment is split off the raw spec first, only the filename part goes through resolution, exactly as documented and load-bearing for multi-record RASP files. `_motors_path(filename)` kept, now a 1-line shim: `return datafiles.resolve(filename, "motors")`. All three of `records.cache_clear`, `load.cache_clear`, `_load_table.cache_clear`, `load_case.cache_clear` confirmed present and wired to the correct underlying `lru_cache`.

**`_motors_path` back-compat claim**: `grep -n "_motors_path"` confirms direct calls from both named external callers: `apps/motor_selection/scenario_sweep.py:129` and `:417`, and `tests/test_scenario_sweep.py:205`. Shim is behaviourally identical to a direct `datafiles.resolve(filename, "motors")` call (it *is* that call, verbatim).

**Error-message regression check**: `sim/aero.py`'s `_load_table_impl` and `sim/motor_file.py`'s `_read_csv`/`_read_rasp` now embed the *resolved* path/`csv_path`/`rasp_path` in `ValueError` messages instead of the raw bare filename. Flagged this as a possible regression risk against a prior QA note (`qa-report-2.17-step115.md`, Step 115) that explicitly asserted error messages contain the *bare* filename. Checked: for a bare-name input, `datafiles.resolve` returns `<bundled>/<kind>/<given>` -- the resolved path's trailing component is still the exact bare filename string, so `assert bare_name in message` still holds (substring match). Confirmed by running `tests/test_motor_file.py` directly below -- all pass, no regression.

### Targeted re-run (cache_clear call sites + error-message assertions)

```
python -m pytest -q tests/test_motor_file.py tests/test_aero.py tests/test_aero_v2.py tests/test_aero_fb.py \
  tests/test_aero_oob.py tests/test_soundings.py tests/test_atmosphere.py tests/test_wind.py tests/test_scenario_sweep.py
```
Result: **210 passed, 5 warnings** (all 5 warnings pre-existing `AeroRangeWarning`/`MachRangeWarning`, unrelated to this diff -- same warnings present before this branch). Zero failures.

### `tests/test_datafiles.py` (16 tests, run in isolation)

Read in full. Judged as real assertions, not tautologies:
- `test_bare_name_resolves_to_bundled_data_dir` (3 params: motors/aero/soundings) -- asserts exact path equality against an independently-constructed expected path (`os.path.join(_DATA, kind, name)`), not calling `resolve` twice.
- `test_windows_absolute_path_returned_unchanged` (3 params) -- uses `tmp_path` (genuinely Windows-absolute on this machine) and asserts identity passthrough.
- `test_posix_style_absolute_path_is_not_grafted_onto_repo_drive` (3 params) -- the regression test for the exact bug this step fixes: feeds `"/some/abs/path"` (absolute per `os.path.isabs` even without a drive letter on Windows), asserts the result is unchanged AND asserts the repo root string does not appear anywhere in the result (catches a reintroduced `os.path.join`/`os.path.abspath` re-wrap).
- `test_cwd_relative_path_resolves_against_getcwd_not_repo_data` (2x3 params) -- `monkeypatch.chdir(tmp_path)`, feeds `"sub/myfile.csv"` / `"./myfile.csv"`, asserts resolution lands under the new cwd and explicitly NOT under the repo's bundled data dir.
- `test_designation_fragment_survives_absolute_path_end_to_end` -- copies a real motor file to an external `tmp_path` dir, loads via `f"{abspath}#K570"` through the real `motor_file.load()` (not a mock), asserts `designation`/`m_prop`/`m_total`/`manufacturer` all match the known Cesaroni K570 values. Genuine end-to-end check, not circular.

Ran in isolation: `python -m pytest -q tests/test_datafiles.py tests/test_packaging_boundary.py -v` -> **18 passed in 0.13s**, every one a real `assert`, confirmed visually test-by-test (no skips, no xfail).

### Zero-behaviour-change independent re-derivation

Ran this manually (not trusting the commit message), reproducing the exact pre-Step-120 formula (`os.path.dirname(os.path.dirname(<sim file path>))` + `os.path.join(..., "data", kind, name)`) and comparing byte-for-byte against `datafiles.resolve()`'s output for 3 bare names across all 3 kinds:
```
motors Cesaroni_2060K570-17A.eng -> True (identical)
aero   example.csv               -> True (identical)
soundings example                -> True (identical)
```
All identical. Confirms the "zero behaviour change for bare filenames" claim independently.

## Step 121 -- `pyproject.toml` / packaging

- `pyproject.toml` read in full: `[tool.setuptools] packages = ["sim", "configs"]` -- exactly that list, no `apps`/`tests`/`tools`. Confirmed.
- `[project.dependencies] = ["numpy==2.5.4", "scipy>=1.18,<2", "matplotlib>=3.11,<4"]` -- matches CLAUDE.md's documented pin (`numpy==2.5.4 / scipy 1.18.1`) and nothing silently dropped from the pre-Step-121 `requirements.txt`.
- `requirements.txt` reduced to `pytest>=8` + a comment pointing at `pyproject.toml`. Confirmed.
- `tests/test_packaging_boundary.py` (2 tests): both use real `tomllib.load` against the actual repo-root `pyproject.toml` path (`os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")`), not a fixture copy. `test_core_packages_are_exactly_sim_and_configs` asserts exact list equality (meaningful -- would fail if `apps` were added or order/content changed). `test_apps_tests_tools_are_not_packaged` asserts non-membership individually for all three names (meaningful). Neither is vacuous.
- Manual confirmation (not trusting the commit message): `python run.py` run fresh from repo root with `pyproject.toml` present -- completed successfully (trajectory/gravity-sweep/atmosphere-sweep outputs all generated, exit 0). Targeted pytest module run (`test_motor_file.py` etc., see above) also unaffected by `pyproject.toml`'s presence -- pytest picks it up only as `rootdir`/`configfile` marker (no `[tool.pytest.ini_options]` section added), no behaviour change.
- Noted but not a defect: `configs/` has subdirectories (`motors/`, `rockets/`, `scenarios/`, `sites/`, `weather/`) alongside `schema.py` and `__init__.py`. Did not verify whether `packages = ["sim", "configs"]` (without `find_packages` / explicit subpackage listing) would actually include those subdirectories in a real `pip install` -- out of scope per the task ("you do NOT need to re-run the architect's packaging experiment"), flagging only as something to keep in mind if the next step in this sequence deals with subpackage declarations.

## Full-suite re-run (own invocation, clean state, `run_in_background`)

```
python -m pytest -q
```
Polled in capped ~200s turns over the full run. Result:

```
818 passed, 56 warnings in 801.76s (0:13:21)
```

Exactly matches the expected number (800 baseline on `feature/sim-paper-alignment` + 18 new: 16 `test_datafiles.py` + 2 `test_packaging_boundary.py`). 0 failed. All 56 warnings are pre-existing `AeroRangeWarning`/`MachRangeWarning` (Mach-independent "constant" aero model exceeding its valid range, or an aero table's alpha range being exceeded) -- same warning classes already seen in the targeted re-run above, not introduced by this diff. Did not hit the known flaky Windows/scipy native access-violation crash documented in `CLAUDE.md`'s environment-pitfalls list; no retry needed.

## Verdict

**PASS.** Both Step 120 and Step 121 independently verified against their stated acceptance criteria, no deviation found. No blocker/major/minor defects. One non-defect observation flagged above (error messages now carry the resolved path rather than the bare filename -- confirmed harmless against existing test assertions) and one scope note (configs/ subpackage listing not simulated against a real install, per task instructions).

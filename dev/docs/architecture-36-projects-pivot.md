# Pivot 3: a `projects/` workspace, `examples/`→`projects/examples/`, `data/`→`projects/data/`, retiring the root `run_*.py` scripts

## Кратко (RU)

- Фаза 2.20, Шаги 138-142 (следующие свободные номера после Step 137). Пивот — чисто механический
  (move/delete/замена path-строк), **никаких численных пинов не трогает**, та же категория риска, что
  Phase 2.16/2.18/2.19.
- Четыре решения пользователя уже приняты (не пересматриваются): `temp/` — сделано оркестратором;
  `tests/` — не трогаем; новая папка `projects/` забирает `examples/` → `projects/examples/`,
  `data/` → `projects/data/`; `output/` удаляется целиком (не переносится); все 5 корневых
  `run_*.py` удаляются без замены — `apps/` остаётся библиотекой/тулкитом (`python -m apps.<тип>.<имя>.<модуль>`),
  пользователь сам пишет входные скрипты в своей `projects/`.
- **Единственная настоящая развилка (F1):** судьба `examples/worked_scenario.py` — тонкого
  runnable-обёртки вокруг `apps/input/demo_scenario.py` (которая уже держит сам литерал сценария,
  это случилось на Step 130, Phase 2.19 — предыдущий пивот уже развернул зависимость правильно).
  Вариант (a) — перенести `examples/worked_scenario.py` → `projects/examples/worked_scenario.py`,
  запускать как `python -m projects.examples.worked_scenario`. Вариант (b, **рекомендуется**) — удалить
  файл целиком, переписать его smoke-тест на прямой in-process вызов `assemble()`/`run_sim()` без
  subprocess. (b) — та же категория вещи, что пользователь уже решил выпилить для `run_*.py`
  (пред-собранный entry-скрипт), и после неё `projects/examples/` остаётся чистыми данными без
  вопроса об импортируемости вообще.
- Важная поправка к заметке оркестратора: **`pyproject.toml` не нужно трогать** — механизм
  `packages = [...]` был полностью упразднён на Step 128 (Phase 2.19); файл сегодня — только
  комментарий, без секций `[project]`/`[tool.setuptools]`. Вторая поправка: якорь `_BUNDLED` в
  `apps/sim/engine/datafiles.py` **не нуждается в дополнительном уровне `os.path.dirname`** — уже
  стоящие 4 вызова `dirname` корректно поднимаются до корня репозитория независимо от глубины цели;
  меняется только хвост `os.path.join(...)` (`"examples","data"` → `"projects","examples","data"`).
- Библиотечная сторона переноса `examples/data/` — одна строка (`_BUNDLED`) + её тестовый зеркальный
  якорь `tests/datadir.py` — ровно по той же причине, что в прошлом пивоте: резолвер `datafiles.resolve()`
  решает по форме строки (абсолютная/с разделителем/голое имя), никогда по расположению bundled-дерева;
  каждое имя данных в проекте — голое имя, так что побайтовое поведение не меняется.
- Найдена живая зависимость от удаляемого `run.py`: `tests/test_schema.py` читает его текст
  (`_RUN_PY = (...).read_text()`) на уровне модуля для регрессии Step 69/123 — без правки тест-файл
  не соберётся вообще. Аналогично `tests/test_layering.py::NETWORK_SCAN_ROOT_FILES` перечисляет все
  5 `run_*.py` по имени для G3-гварда — тоже ломается без правки. Обе правки — часть шага удаления
  скриптов, не отдельная развилка.
- Сотни **исторических** упоминаний голого `data/motors/`/`examples/data/...` в докстрингах/комментариях
  по всему `apps/`/`tests/` **не правятся** — это установленная практика проекта: такие упоминания не
  синхронизировались и после прошлого переноса (Step 129), это читается как застывшая история, не живая
  документация. Правятся только живые якоря (`datafiles.py`, `tests/datadir.py`,
  `tests/test_layering.py`'s G5/G6/G3-константы) и пара файлов, которые физически переезжают внутри
  `examples/data/` (2 README.md там).
- Blast radius вне этого тикета (не моя правка, для оркестратора/documentation): `README.md` (строки
  34,39,45,48,50,52,100-104 — команды `run_*.py` и дерево каталогов), `CLAUDE.md` «Профиль проекта»
  (строка «Запуск приложения» и абзац «Построить свою ракету»), и одно предложение в
  `dev/docs/latex/sections-ai/introduction.tex:12` («soundings under `data/`») — станет неточным
  (должно быть `projects/data/`), но LaTeX не редактируется мной по правилу проекта.

---

## Table of contents

- [SS1. Scope recap — what's already decided vs. what's open](#ss1)
- [SS2. Current-state inventory (verified this session)](#ss2)
- [SS3. Corrections to the orchestrator's priming notes](#ss3)
- [SS4. The one decision fork — F1: fate of `examples/worked_scenario.py`](#ss4)
- [SS5. File-by-file move/delete list](#ss5)
- [SS6. Step breakdown (Steps 138-142)](#ss6)
- [SS7. Zero-pin-risk argument](#ss7)
- [SS8. Out of scope / blast radius for the orchestrator](#ss8)

---

<a id="ss1"></a>
## SS1. Scope recap — what's already decided vs. what's open

Four decisions, already made by the user via `AskUserQuestion`, not reopened here:

| # | Decision | Status |
|---|---|---|
| 1 | `temp/` vs `temporary/` | **Done** by the orchestrator already (3 files merged, `temp/` deleted, `.gitignore` line removed). No action in this ticket. |
| 2 | `tests/` structure | Stays exactly as one tree. No action. |
| 3 | New top-level `projects/`: `examples/` → `projects/examples/`, `data/` → `projects/data/`, `output/` removed entirely (not relocated) | **The real work of this ticket.** |
| 4 | Root `run_*.py` (5 files) deleted outright, no replacement | **The other real work of this ticket.** `apps/*` stays a usable library/toolkit (`python -m apps.<type>.<name>.<module>`); the user writes their own entry scripts inside `projects/` going forward. |

One genuine open design question, scoped as a fork in [SS4](#ss4): what happens to
`examples/worked_scenario.py` and its subprocess-based smoke test once `examples/` moves.

<a id="ss2"></a>
## SS2. Current-state inventory (verified this session)

### SS2.1 What's actually under `examples/` and `data/` today

```
examples/
  __pycache__/              (gitignored, bytecode cache — dies with the move)
  data/                      14 tracked files: aero/ (2 csv), motors/ (6: .eng + 5 .csv + README.md),
                             soundings/ (5: 3 case csv's + 2 README.md's)
  worked_scenario.py         thin __main__ wrapper: assemble(DEMO_SCENARIO) -> run_sim -> print_run_summary

data/
  README.md                  the ONLY tracked file (`.gitignore`'s `/data/*` + `!/data/README.md`)
  motors/                    untracked, this machine's local personal-data scratch (not in git at all)
```

Confirmed via `git ls-files`: `data/` has exactly one tracked file (`data/README.md`); `examples/` has
15 tracked files (14 under `data/` + `worked_scenario.py`).

### SS2.2 The `examples.worked_scenario` dependency graph, as it actually stands today (not as of the prior pivot doc)

The prior pivot document (`dev/docs/pivot-apps-restructure-analysis.md`, its F3) recommended moving the
demo-scenario literal out of `examples/worked_scenario.py` into the package, leaving `examples/
worked_scenario.py` as "a thin runner". **That recommendation was already implemented**, at Step 130
(Phase 2.19) — confirmed by reading the current files:

- `apps/input/demo_scenario.py` holds `DEMO_SCENARIO` (and `rocket`/`motor`/`site`/`weather`) as the
  real literal. Nothing under `apps/` imports `examples.*` any more — grepped exhaustively, zero hits
  for a real `from examples import` / `import examples` statement anywhere under `apps/`.
- `examples/worked_scenario.py` today is exactly 29 lines: a docstring plus
  `from apps.input.demo_scenario import DEMO_SCENARIO`, `assemble`, `run_sim`, `report.print_run_summary`,
  called only inside `if __name__ == "__main__":`.
- The **only** thing in the whole repo that still invokes it is its own smoke test,
  `tests/test_worked_scenario_example.py`, via `subprocess.run([sys.executable, "-m",
  "examples.worked_scenario"], ...)`.

So the backwards-dependency bug the prior pivot worried about (`apps/` reaching into `examples/`) is
already fixed and stays fixed regardless of which way [SS4](#ss4) is resolved — this pivot is choosing
between two ways to finish retiring the *runnable-script* convention, not re-litigating the import
direction.

### SS2.3 The bundled-data anchor (library side) — confirmed current code

```python
# apps/sim/engine/datafiles.py:69
_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "examples", "data")
```

`__file__` is `apps/sim/engine/datafiles.py`; the four nested `dirname` calls strip `engine`, `sim`,
`apps` in turn, landing on the repo root. `os.path.join(repo_root, "examples", "data")` is the result.
Confirmed call sites unchanged since the prior pivot: `apps/sim/engine/aero.py:371`,
`apps/sim/engine/motor_file.py` (`_motors_path` wraps `datafiles.resolve`), `apps/sim/engine/soundings.py`.

The test-side mirror is `tests/datadir.py:21`: `DATA = os.path.join(_REPO_ROOT, "examples", "data")`,
with `_REPO_ROOT = os.path.dirname(os.path.dirname(__file__))` (two `dirname` calls from `tests/
datadir.py` to the repo root). `tests/test_layering.py::test_g5_bundled_data_anchor_matches_sim_datafiles`
is the regression test keeping these two independent constants from drifting apart — it asserts both
the resolved path's identity *and* that it sits under `(REPO_ROOT / "examples" / "data")`
(`tests/test_layering.py:321`).

### SS2.4 `pyproject.toml` — confirmed empty of packaging config

Read in full this session:

```toml
# Step 128 (Phase 2.19, ...): the packaging mechanism ([build-system],
# [project], [tool.setuptools]) is retired -- the project is not
# `pip install`-ed in the working interpreter and everything already
# works without it, so the install mechanism goes away before any files
# move... requirements.txt is now the single dependency declaration.
# This file survives only as a home for tool configuration that isn't
# packaging -- there is none yet.
```

No `packages = [...]` list exists. Nothing in it references `examples`, `data`, or `apps`. **Zero
change needed to this file for this pivot.**

### SS2.5 Output-writing is already cwd-anchored everywhere, confirmed exhaustively

Grepped every `output_dir`/`OUTPUT_DIR`/`default_output_dir` call site across `apps/`:
`apps/analysis/cfd_conditions/select_conditions.py`, `apps/analysis/weight_aero_tradeoff/
{compare_configs,trade_surface}.py`, `apps/optimization/airbrake_sizing/solve_cda.py`,
`apps/optimization/motor_selection/{compare_motors,scenario_sweep}.py`, `apps/sim/engine/report.py`. All
of them go through `apps/_shared/artifacts.py::output_dir()` (`Path.cwd() / "output"`, read fresh on
every call) or `apps/sim/engine/report.py::default_output_dir()` (same contract). Confirmed by
`tests/test_layering.py::test_g4_output_helpers_resolve_under_cwd_not_repo`, which `monkeypatch.chdir`s
to a `tmp_path` far from the repo and asserts both resolve under it. **Deleting the repo-root `output/`
directory requires zero code change** — it is gitignored, currently holds only stale generated
artifacts from past manual runs, and will be recreated wherever an app's cwd happens to be the next
time one is invoked.

<a id="ss3"></a>
## SS3. Corrections to the orchestrator's priming notes

Two of the orchestrator's "facts I already verified" notes don't hold up against the current file
contents, worth flagging explicitly since the ticket depends on getting these two edits right:

1. **"`pyproject.toml` has a `packages = [...]` list (Phase 2.18, Step 121)"** — this was true at Step
   121, but Step 128 (Phase 2.19) retired the entire packaging mechanism, including that list. The file
   today is comment-only (see [SS2.4](#ss2.4)). **No change needed**, not "check whether it needs
   touching" — it doesn't.
2. **"`_BUNDLED`... becomes `<repo_root>/projects/examples/data` — one more `os.path.dirname` level"** —
   not quite. The number of `dirname` calls needed to reach `repo_root` from `apps/sim/engine/
   datafiles.py` depends only on *that file's own depth* in the tree (3 directories: `apps/sim/engine`),
   which hasn't changed. It is the target's *join suffix* that grows by one component
   (`"examples","data"` → `"projects","examples","data"`), not the walk-up-to-root prefix. Same for
   `tests/datadir.py`'s `_REPO_ROOT` (unaffected — `tests/` itself hasn't moved).

<a id="ss4"></a>
## SS4. The one decision fork — F1: fate of `examples/worked_scenario.py`

**Purpose.** `examples/` is about to move. Its one Python file is a 29-line runnable wrapper whose sole
remaining consumer is its own subprocess-based smoke test ([SS2.2](#ss2.2)). Two ways to carry it
across the move.

| | (a) move verbatim: `projects/examples/worked_scenario.py`, `python -m projects.examples.worked_scenario` | (b) retire it — delete the file, fold its smoke test into an in-process pytest (recommended) |
|---|---|---|
| Mechanics | `git mv examples/worked_scenario.py projects/examples/worked_scenario.py`; update its docstring's invocation line; update `tests/test_worked_scenario_example.py`'s subprocess argv from `"examples.worked_scenario"` to `"projects.examples.worked_scenario"`. No `__init__.py` needed either way — `examples/` already runs as an implicit PEP 420 namespace package today (its own docstring says so), and `projects/examples/` would work the same way from the repo root. | Delete `examples/worked_scenario.py` outright. Rewrite `tests/test_worked_scenario_example.py` to call `assemble(DEMO_SCENARIO)` → `run_sim` → `report.print_run_summary` directly (no `subprocess`, no `sys.executable`), asserting on `capsys.readouterr().out` instead of `result.stdout`. Update `apps/input/demo_scenario.py`'s docstring (the paragraph naming `examples/worked_scenario.py` as "the thin, directly-runnable copy... run `python -m examples.worked_scenario`") to drop that pointer. |
| What's left under `projects/examples/` | one `.py` file + the bundled `data/` corpus | **pure data** — `projects/examples/` is nothing but the bundled fixture corpus, no code, no importability question at all |
| Consistency with decision 4 (root `run_*.py` deletion) | **in tension with it.** The user's own stated rationale for deleting `run_*.py` ("apps are pre-built apps that can be used but user can always make them... no need to have [entry scripts] pre-done") describes `examples/worked_scenario.py` just as precisely — it is a pre-built, directly-runnable `__main__` wrapper around `assemble()`/`run_sim()`, the exact same shape as `run.py` one folder deeper. Keeping it under a new name reintroduces the pattern the user just asked to remove. | **matches it exactly.** Removes the last pre-built runnable entry script from the repo; `apps/input/demo_scenario.py` (the actually load-bearing REQ/OPT crib-sheet) is untouched and still fully importable/copyable, unaffected either way. |
| Test-guarantee preserved | the subprocess smoke test keeps proving `python -m <path>` resolution itself works (import-time namespace-package wiring), not just that the pipeline runs | that specific guarantee is lost, but it's already redundant: `tests/test_layering.py`'s G2 importability guard walks every module under `apps/` by dotted name, and `tests/test_schema.py`'s fresh-interpreter check already proves `apps.input.demo_scenario` imports cleanly as the first import in a fresh process. What's kept: the pipeline still actually runs end-to-end in the test (`assemble` → `run_sim` → real printed summary), same assertions (`"Apogee altitude:"`, `"Burnout time:"`), just in-process. |
| `tests/test_layering.py` impact | `NETWORK_SCAN_ROOTS`'s `"examples"` entry becomes `"projects/examples"` (still something to scan, one file) | `"examples"`/`"projects/examples"` entry can be dropped from `NETWORK_SCAN_ROOTS` entirely — nothing left to scan there |
| Cost | ~15 min (1 move, 2 one-line edits, re-run the suite) | ~30 min (1 delete, 1 test rewrite, 1 docstring edit, re-run the suite) |

**Recommendation: (b).** The tension row is decisive — this pivot's whole point, in the user's own
words, is that the repo stops shipping pre-built entry scripts and the user writes their own inside
`projects/`. Keeping `examples/worked_scenario.py` alive under a new address is the same thing by a
different name; retiring it is the only option that leaves `projects/examples/` meaning exactly what
decision 3 says it should ("bundled read-only fixtures"), with zero code left to maintain there. The
lost test guarantee is redundant with two other existing guards, not actually a coverage gap.

If the user picks (a) instead: everything in [SS5](#ss5)/[SS6](#ss6) below still applies except Step 139
becomes a straight `git mv` + two find-and-replace edits rather than a delete-and-rewrite, and the
`NETWORK_SCAN_ROOTS` edit in Step 140 becomes a rename instead of a removal.

<a id="ss5"></a>
## SS5. File-by-file move/delete list

Assumes [SS4](#ss4)'s recommendation (b). Where (a) would differ, noted inline.

### SS5.1 `data/` → `projects/data/`

| File | Action |
|---|---|
| `data/README.md` | `git mv` → `projects/data/README.md`; update its own prose (title, and its 6 mentions of `examples/data/` → `projects/examples/data/`, consistent with SS5.2 landing there in the same pivot) |
| `data/motors/` (untracked, local to this machine) | plain filesystem move alongside the `git mv` — it is not in git, so git has no opinion, but leaving it behind would silently orphan the user's own local test data |
| `.gitignore` | `/data/*` → `/projects/data/*`; `!/data/README.md` → `!/projects/data/README.md`; update the comment above it (currently explains the `/data/*` + negation idiom — just needs its path examples updated) |
| `tests/test_layering.py` | `RETIRED_PATHS` gains `"data"` |

Nothing else references the top-level `data/` path by hardcoded string — confirmed by grep: the only
code with a `"data"` string building a *default* path is `apps/input/sounding_fetch/
fetch_sounding.py:364` (`os.path.join(os.getcwd(), "data", "soundings")`), which is already cwd-relative
and keeps working unchanged (it will write to `<wherever the user runs it from>/data/soundings/`, which
for a user working inside `projects/` becomes `projects/data/soundings/` automatically — no edit
needed).

### SS5.2 `examples/` → `projects/examples/` (recommendation b: `worked_scenario.py` retired, not moved)

| File | Action |
|---|---|
| `examples/worked_scenario.py` | **deleted** (not moved) |
| `examples/data/aero/{example.csv,example_v2.csv}` | `git mv` → `projects/examples/data/aero/` |
| `examples/data/motors/{*.eng,*.csv}` (6 files) | `git mv` → `projects/examples/data/motors/` |
| `examples/data/motors/README.md` | `git mv` → same, same path suffix; update its prose: `examples/data/` → `projects/examples/data/` (2 mentions), `data/README.md` → `projects/data/README.md` (1 mention), drop the `python -m examples.worked_scenario` mention in its `Cesaroni_2060K570-17A.eng` table row (ties to F1) |
| `examples/data/soundings/{README.md, example/*.csv, example_live/*.csv, field_example/*.csv}` | `git mv` → `projects/examples/data/soundings/...`; update `soundings/README.md`'s 2 mentions of `examples/data/`/`data/` the same way as the motors README |
| `examples/__pycache__/` | gitignored, deleted along with the directory, no action needed |
| `apps/sim/engine/datafiles.py:69` | `_BUNDLED`'s join suffix: `"examples", "data"` → `"projects", "examples", "data"` (no change to the four `dirname` calls — see [SS3](#ss3)); docstring mentions at lines 32, 50-54, 73-76 updated to match |
| `tests/datadir.py:21` | `DATA = os.path.join(_REPO_ROOT, "projects", "examples", "data")`; docstring mention at line ~9 updated |
| `tests/test_layering.py` | G5: `test_g5_bundled_data_anchor_matches_sim_datafiles`'s assertion `(REPO_ROOT / "examples" / "data")` → `(REPO_ROOT / "projects" / "examples" / "data")`, and its docstring/module-docstring mentions (lines ~45-46, ~312); `NETWORK_SCAN_ROOTS` drops the `"examples"` entry entirely (nothing left to scan there under recommendation b); `RETIRED_PATHS` gains `"examples"` |
| `apps/input/demo_scenario.py` | docstring paragraph (lines ~46-56) naming `examples/worked_scenario.py` as "the thin, directly-runnable copy" and its `python -m examples.worked_scenario` invocation instruction — rewritten to say there is no pre-built runnable copy any more; to actually fly the demo scenario, write a short script in your own `projects/` (`from apps.input.demo_scenario import DEMO_SCENARIO`, `assemble`, `run_sim`) |
| `tests/test_worked_scenario_example.py` | rewritten per [SS4](#ss4)(b): drop `subprocess`/`sys` imports, call the pipeline in-process, assert on `capsys` |

**Not touched** (established-practice carve-out, see [SS6](#ss6)'s Кратко bullet and [SS8](#ss8)):
dozens of historical prose mentions of bare `data/motors/`/`data/soundings/`/`examples/data/...` inside
docstrings and comments across `apps/sim/engine/{params,soundings,thrust_curve,motor_file,compare_motors
etc.}` and most of `tests/*.py` — these already predate the Step 129 split and were never retroactively
fixed; this pivot doesn't start a new precedent of fixing them either.

### SS5.3 Root `run_*.py` deletion

| File | Action |
|---|---|
| `run.py`, `run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py` | **deleted**, no replacement |
| `tests/test_schema.py` | delete `_RUN_PY = (_PROJECT_ROOT / "run.py").read_text()` (line 201) and `test_run_py_sources_its_scenario_from_configs_get_demo` (lines 210-217) — the only test reading `run.py`'s own source text; `_SELECT_CONDITIONS_PY`/`_COMPARE_MOTORS_PY` and their tests are untouched (those files aren't moving) |
| `tests/test_layering.py` | `NETWORK_SCAN_ROOT_FILES` (line 124) → `()`; `RETIRED_PATHS` gains the 5 filenames |

**Not touched**: historical "run.py's placeholder scenario" prose comments in `tests/test_control.py`,
`tests/test_dynamics.py`, `tests/test_integrate.py`, `tests/test_plotting.py`,
`tests/config_variants.py`, `tests/test_weight_aero_tradeoff.py` — none of these have a functional
dependency on `run.py` existing (confirmed: none of them import or subprocess-invoke it; they describe a
historical scenario literal that still lives, reconstructed independently, in those test files
themselves). Same established-practice carve-out as SS5.2.

### SS5.4 `output/` deletion

| File | Action |
|---|---|
| `output/` (gitignored, 16 generated files currently present from past manual runs) | deleted wholesale |
| `.gitignore`'s `output/` entry | comment updated (currently says "regenerated by running run.py" — no longer accurate once `run.py` is gone) |

No code change — confirmed cwd-anchored everywhere, [SS2.5](#ss2.5).

<a id="ss6"></a>
## SS6. Step breakdown (Steps 138-142)

Five steps, sequential, each leaves the full suite green and is independently committable — mirroring
how Phase 2.18's Steps 120-125 and Phase 2.19's Steps 126-135 were broken up.

**Step 138 — `data/` → `projects/data/`.** SS5.1 in full. Zero ambiguity, zero dependency on the F1
fork. Full-suite gate: unchanged (nothing hardcodes the old path).

**Step 139 — resolve F1: retire `examples/worked_scenario.py`.** Delete the file; rewrite
`tests/test_worked_scenario_example.py` to run the pipeline in-process; update
`apps/input/demo_scenario.py`'s docstring. Done *before* the `examples/data/` move (Step 140) so the
directory's code-vs-data question is settled independently of the data-file relocation. Full-suite
gate: the rewritten test must still pass (same two assertions on real printed output).

**Step 140 — `examples/data/` → `projects/examples/data/` + library anchor update.** SS5.2's data-file
moves, `apps/sim/engine/datafiles.py::_BUNDLED`, `tests/datadir.py::DATA`, the two nested README.md's,
and `tests/test_layering.py`'s G5 assertion + `NETWORK_SCAN_ROOTS`/`RETIRED_PATHS` entries for
`examples`. Full-suite gate: full run — this is the step that actually moves every bundled motor/aero/
sounding fixture the whole suite reads, so it is the highest-value point to run the complete suite
(chunked per the project's background-test convention) rather than a targeted subset.

**Step 141 — delete the 5 root `run_*.py` scripts.** SS5.3: the 5 deletions, `tests/test_schema.py`'s
`_RUN_PY`-dependent test removal, `tests/test_layering.py`'s `NETWORK_SCAN_ROOT_FILES` →
`()`/`RETIRED_PATHS` additions. Full-suite gate: full run (this step removes a test, not just moves
paths — worth the full gate to confirm nothing else silently depended on these files existing, beyond
what SS2 already found by grep).

**Step 142 — delete `output/`.** SS5.4. Trivial; bundle the `.gitignore` comment wording fix here.
Full-suite gate: targeted (`test_layering.py`, `test_schema.py` if any output-path assertions exist —
grepped, none do) is sufficient; this step touches nothing executable.

Each step is one commit, per the project's step discipline (`Step NN (Phase 2.20): …`).

<a id="ss7"></a>
## SS7. Zero-pin-risk argument

Identical reasoning to the prior pivot's SS4.1, re-verified this session against the current (post-
Phase-2.19) code rather than assumed: `datafiles.resolve()`'s three rules key off the *shape* of the
given string (absolute / contains a separator / bare name), never off `_BUNDLED`'s own value. Every
data-file string anywhere in this repo — exhaustively the same set the prior pivot enumerated, unchanged
since — is a bare name, so every lookup takes rule 3, whose only effect of this pivot is a different
constant *prefix* on the returned path. The bytes read off disk, the parsed records, and therefore every
numeric result downstream are untouched. `output_dir()`/`default_output_dir()` were already proven
cwd-anchored (not touched by this pivot at all, just the directory they happen to point at today is
deleted). `examples.worked_scenario`'s retirement touches zero `sim`/`apps` physics code — it is a
wrapper script and its own test, nothing else imports it. The `run_*.py` deletions remove 5 files with
zero unique logic (each is a 5-40 line forwarder per the prior pivot's own SS1.2 inventory,
re-confirmed this session for `run_trade.py`). Nothing in this ticket touches `apps/sim/engine/` physics
modules, `apps/sim/schema.py`, or any numeric literal.

<a id="ss8"></a>
## SS8. Out of scope / blast radius for the orchestrator

Not edited by this ticket (per the ticket's own brief — documentation/orchestrator's job after
approval), but will be stale once this pivot lands:

- **`README.md`** — lines 34, 39 (`python run.py`, output mention), 45/48/50/52 (the other 4
  `run_*.py` invocation bullets), 100-104 (directory-tree block: `examples/data/`, `data/`, `output/`
  lines all need their `projects/` prefix or removal).
- **`CLAUDE.md`**'s "Профиль проекта" table — the "Запуск приложения" row currently lists all 5
  `run_*.py` commands as the way to run the simulation; needs to say there is none, pointing at
  `python -m apps.<type>.<name>.<module>` only. The "Построить свою ракету" paragraph's directory
  description (`examples/data/`, gitignored `data/`) needs the `projects/` prefix.
- **`dev/docs/latex/sections-ai/introduction.tex:12`** — "soundings under `\texttt{data/}`" becomes
  inaccurate (`projects/data/`); per the project's explicit-request-only LaTeX rule, not edited here —
  flagged for the orchestrator to decide whether/when to ask the user.
- **`dev/docs/architecture.md`/`roadmap.md`** — explicitly out of scope per the orchestrator's own
  brief; not touched, not re-flagged beyond this line.

Historical prose path mentions left untouched (established practice, not a new gap introduced by this
ticket) are listed inline in [SS5.2](#ss5.2)/[SS5.3](#ss5.3) rather than repeated here.

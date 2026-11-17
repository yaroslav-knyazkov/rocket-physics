# Architecture 44 — fx27 `campaigns/` reorg (rockets merge, tool relocation, `campaigns/` -> `data/` rename, airbrake naming)

## Кратко (RU)

- Это чисто организационный документ (Phase 2.28, incremental, без архитектурных развилок) поверх уже одобренного стека: никакого нового кода, только перенос/переименование файлов и путей импорта внутри `projects/fx27/`.
- Четыре изменения: (1) слить `campaigns/cspace/rockets.py` + `rockets_dm.py` в один файл `rockets.py`; (2) перенести одноразовый скрипт `regenerate_ideal_own.py` из `campaigns/cspace/` в `runs/point/` (campaigns/ — только данные); (3) переименовать `projects/fx27/campaigns/` -> `projects/fx27/data/`, заодно убрать лишнюю вложенность `cspace/data/aero` -> `cspace/aero` (и аналогично `motors/`, `airbrake/`, euroc `motors/` — для единообразия); (4) переименовать `solvers/point/airbrake.py` + `runs/point/airbrake.py` -> `ideal_open_airbrake.py` (оба), освобождая имя `airbrake` для будущего реального closed-loop скрипта параллельной сессии.
- **Коллизия с параллельной сессией подтверждена и живая**: вторая оркестрирующая сессия уже создала (без коммита) `campaigns/cspace/airbrake_data.py`, `campaigns/cspace/data/airbrake/*.csv`, `_paths.py::cspace_airbrake`/`AIRBRAKE_CSPACE`, и `solvers/point/controller.py` + `runs/point/controller.py` (последние импортируют `airbrake_data`, НЕ старый `solvers/point/airbrake.py` — значит переименование (4) ничего не ломает). По указанию пользователя эти файлы включены как полноправные участники переименования (3): они тоже переедут под `data/cspace/...` и их пути в `_paths.py`/импортах обновляются вместе со всем остальным.
- Контент `rockets_ideal.py` (Section A, 4-константный AC-3 oracle) не трогается ни байтом — только его import-строки (путь к `rockets`/`rockets_dm`) и один комментарий, указывающий старый путь `regenerate_ideal_own.py`.
- Тесты: только обновление путей импорта (политика D-181/это же правило из Phase 2.27) — новых тестов не добавляется. Ожидаемый итог: 899 passed, 0 failed, без изменений.
- Пункт 5 (реальный closed-loop airbrake-скрипт) явно НЕ входит в этот тикет — только оставлена сноска, где будущая `data/airbrake/` окажется после переименования (3).
- Разбивка на тикеты FX27E-1..6, строго последовательно (`parallel_safe: false` везде) — слишком много пересекающихся файлов (`rockets_ideal.py`, `scenarios_dm.py`, `_paths.py`) для безопасного параллельного запуска.

## Table of contents

- [S44.1 Scope, collision note, and what this ticket does NOT do](#s441-scope-collision-note-and-what-this-ticket-does-not-do)
- [S44.2 Target file tree](#s442-target-file-tree)
- [S44.3 Per-file disposition](#s443-per-file-disposition)
- [S44.4 Nesting-conflict resolution: `data/aero`, `data/airbrake`, `data/motors`](#s444-nesting-conflict-resolution-dataaero-dataairbrake-datamotors)
- [S44.5 Full import-path / docstring update list](#s445-full-import-path--docstring-update-list)
- [S44.6 `rockets.py` + `rockets_dm.py` merge design](#s446-rocketspy--rockets_dmpy-merge-design)
- [S44.7 Acceptance criteria](#s447-acceptance-criteria)
- [S44.8 Rejected options](#s448-rejected-options)
- [S44.9 Tickets FX27E-1..6](#s449-tickets-fx27e-1-6)

## S44.1 Scope, collision note, and what this ticket does NOT do

This is an **incremental organizational reorg** on an already-approved stack (Python 3.12, no new libraries, no new runtime behavior). No architectural fork; no `decision_required` beyond the one nesting-flattening judgment call resolved in S44.4 (reasoned, not escalated — see that section for why it does not rise to a user decision).

**Live cross-session collision (confirmed, not hypothetical).** At investigation time, a second orchestrator session had already written (uncommitted, working tree only) all four of the paths this ticket's brief warned about:

- `projects/fx27/campaigns/cspace/data/airbrake/{pro54-transition-airbrake.csv, pro75-airbrake.csv}` (new, untracked)
- `projects/fx27/campaigns/cspace/airbrake_data.py` (new, untracked — appeared mid-investigation)
- `projects/fx27/_paths.py` modified (unstaged) adding `AIRBRAKE_CSPACE` + `cspace_airbrake()`
- `projects/fx27/solvers/point/controller.py` and `projects/fx27/runs/point/controller.py` (new, untracked)

Checked what `controller.py` imports: **`from projects.fx27.campaigns.cspace.airbrake_data import AirbrakeHardware`** (solvers) and **`from projects.fx27.campaigns.cspace import airbrake_data`** (runs) — neither imports `solvers.point.airbrake` / `runs.point.airbrake` by name. So item 4 (the `airbrake.py` -> `ideal_open_airbrake.py` rename) has **no known caller to break** and proceeds exactly as scoped.

Per the coordinator's updated instructions, the other session's new files are folded into this reorg as first-class citizens (not reverted, not worked around): `airbrake_data.py` and `data/airbrake/*.csv` get the same `campaigns/` -> `data/` + flattening treatment as every other cspace module/data folder (S44.2-S44.5), and `_paths.py`'s `cspace_airbrake()`/`AIRBRAKE_CSPACE` get updated to the new path alongside `cspace_aero()`/`cspace_motor()`.

**Residual risk for the developer executing the tickets:** these four paths may still be under active edit (content, not just location) by the other session. Before editing `_paths.py`, `airbrake_data.py`, `solvers/point/controller.py`, or `runs/point/controller.py`, re-run `git status --short` / `git diff --stat` on exactly those four paths. If their *content* has changed since this doc was written, that is expected and fine — apply the same mechanical path substitution to whatever is there. If an **entirely new path** outside this list (not `controller.py`, not `airbrake_data.py`, not `data/airbrake/*`, not `_paths.py`) appears mid-ticket, stop that ticket and report back via `needs_input` rather than silently absorbing it (same rule the architect was given).

**Explicitly out of scope (item 5, per user instruction):** no real (non-ideal) closed-loop airbrake run-script, no new loader beyond what the other session already wrote, no new CSV data files. S44.4 notes where that future script's data will live once this rename lands, for the next ticket's benefit only.

**Also noticed, not actioned:** `projects/fx27/README.md`'s "Layout" section (lines ~113-131) is *already* stale — it still shows the pre-Phase-2.27 `point/` top-level dir and `runs/cspace/`/`runs/euroc/` entry points, predating even the `solvers/point/`+`runs/point/` restructure, let alone this ticket's rename. Patching only the `campaigns/` mentions in an already-broken README would leave it partially wrong in a new way. Left untouched here; flagged as a pre-existing staleness for a dedicated `readme-keeper` audit pass (not blocking this ticket, not caused by it).

## S44.2 Target file tree

Before (current, `projects/fx27/campaigns/`):

```
projects/fx27/campaigns/
  __init__.py
  cspace/
    __init__.py
    motors.py, rockets.py, rockets_dm.py, rockets_ideal.py, site.py, weather.py,
    scenarios.py, scenarios_dm.py, regenerate_ideal_own.py
    airbrake_data.py                      <- other session, in-flight
    data/
      motors/*.csv                        (2 files)
      aero/generate_dm_tables.py + *.csv  (3 csv)
      airbrake/*.csv                      (2 files, other session, in-flight)
  euroc/
    __init__.py
    motors.py, rockets.py, site.py, weather.py, scenarios.py
    data/
      motors/*.csv                        (27 files incl. 3 `-todo` stubs)
```

After (target, `projects/fx27/data/`):

```
projects/fx27/data/
  __init__.py
  cspace/
    __init__.py
    motors.py, rockets.py (merged, dc+dm), rockets_ideal.py (content untouched), site.py,
    weather.py, scenarios.py, scenarios_dm.py
    airbrake_data.py                      <- other session's file, path-updated only
    aero/        generate_dm_tables.py + *.csv   (3 csv)   -- flattened, was data/aero/
    motors/      *.csv                            (2 files) -- flattened, was data/motors/
    airbrake/    *.csv                            (2 files) -- flattened, was data/airbrake/
  euroc/
    __init__.py
    motors.py, rockets.py, site.py, weather.py, scenarios.py
    motors/      *.csv                            (27 files) -- flattened, was data/motors/

projects/fx27/solvers/point/
  ideal_open_airbrake.py   (renamed from airbrake.py; size_airbrake/print_brake_report unchanged)
  controller.py            (other session, in-flight; import path updated: campaigns -> data)
  [comparison.py, estimate.py, flight.py, metrics.py, plots.py, validity.py unchanged]

projects/fx27/runs/point/
  ideal_open_airbrake.py       (renamed from airbrake.py)
  regenerate_ideal_own.py      (moved here from data/cspace/, was campaigns/cspace/)
  controller.py                 (other session, in-flight; import path updated: campaigns -> data)
  [airbrake.py REMOVED (renamed), ideal_drag.py, ideal_mass.py, point.py, sweep.py,
   comparison.py unchanged except import paths]
```

`rockets_dm.py` ceases to exist (merged into `rockets.py`, S44.6). `campaigns/__init__.py`, `campaigns/cspace/__init__.py`, `campaigns/euroc/__init__.py` move (as directories move) and get their self-referencing docstring paths updated.

## S44.3 Per-file disposition

| Current path | Disposition | New path |
|---|---|---|
| `campaigns/__init__.py` | move + docstring path update | `data/__init__.py` |
| `campaigns/cspace/__init__.py` | move + docstring path update | `data/cspace/__init__.py` |
| `campaigns/cspace/rockets.py` | **merge** with `rockets_dm.py` (S44.6) | `data/cspace/rockets.py` |
| `campaigns/cspace/rockets_dm.py` | **deleted** (content merged into `rockets.py`) | — |
| `campaigns/cspace/rockets_ideal.py` | move only; content untouched (Section A byte-for-byte); update 2 import lines + 1 comment (old `regenerate_ideal_own` path) | `data/cspace/rockets_ideal.py` |
| `campaigns/cspace/regenerate_ideal_own.py` | **move** out of data tree into `runs/point/`; update its own docstring (path comment, `Run:` line) and the "`rockets_dm.py`" mention (now `rockets.py`) | `runs/point/regenerate_ideal_own.py` |
| `campaigns/cspace/motors.py` | move + docstring path update | `data/cspace/motors.py` |
| `campaigns/cspace/site.py`, `weather.py` | move + docstring path update | `data/cspace/{site,weather}.py` |
| `campaigns/cspace/scenarios.py` | move + import path update (`campaigns.cspace` -> `data.cspace`) | `data/cspace/scenarios.py` |
| `campaigns/cspace/scenarios_dm.py` | move + import path update; `rockets_dm` import/usages -> `rockets` (merge fallout, S44.6) | `data/cspace/scenarios_dm.py` |
| `campaigns/cspace/airbrake_data.py` | move + import path update (other session's file — path-only change, re-check content hasn't drifted before editing) | `data/cspace/airbrake_data.py` |
| `campaigns/cspace/data/motors/*.csv` (2) | move, flattened (S44.4) | `data/cspace/motors/*.csv` |
| `campaigns/cspace/data/aero/generate_dm_tables.py` | move, flattened; update its own 2 self-referencing path comments | `data/cspace/aero/generate_dm_tables.py` |
| `campaigns/cspace/data/aero/*.csv` (3) | move, flattened | `data/cspace/aero/*.csv` |
| `campaigns/cspace/data/airbrake/*.csv` (2) | move, flattened (other session's data) | `data/cspace/airbrake/*.csv` |
| `campaigns/euroc/__init__.py`, `motors.py`, `rockets.py`, `site.py`, `weather.py`, `scenarios.py` | move + docstring/import path update | `data/euroc/{same name}.py` |
| `campaigns/euroc/data/motors/*.csv` (27) | move, flattened (S44.4) | `data/euroc/motors/*.csv` |
| `_paths.py` | content edit (not moved): `MOTORS_CSPACE`/`MOTORS_EUROC`/`AERO_CSPACE`/`AIRBRAKE_CSPACE` all repointed from `campaigns/...` to `data/...`, and flattened (drop the inner `/data` segment) | `_paths.py` (unchanged location) |
| `solvers/point/airbrake.py` | **rename**; function names (`size_airbrake`, `print_brake_report`) unchanged | `solvers/point/ideal_open_airbrake.py` |
| `runs/point/airbrake.py` | **rename**; update its own import of the solvers module + `Run:` docstring line | `runs/point/ideal_open_airbrake.py` |
| `solvers/point/controller.py` | content edit only (other session's file): `campaigns.cspace` -> `data.cspace` in its import | unchanged location |
| `runs/point/controller.py` | content edit only (other session's file): `campaigns.cspace` -> `data.cspace` in its 2 imports | unchanged location |
| `runs/point/ideal_drag.py`, `ideal_mass.py`, `point.py`, `sweep.py`, `comparison.py` | content edit only: import paths `campaigns.cspace`/`campaigns.euroc` -> `data.cspace`/`data.euroc` | unchanged location |
| `tests/test_fx27_port.py` | content edit: 5 import-path lines (`campaigns.cspace.*` x3, `campaigns.euroc.*` x2) + 1 (`solvers.point.airbrake` -> `solvers.point.ideal_open_airbrake`) | unchanged location |
| `tests/test_regenerate_ideal_own.py` | content edit: 6 import-path lines, incl. `campaigns.cspace.regenerate_ideal_own` -> `runs.point.regenerate_ideal_own` | unchanged location |
| `tests/test_apogee_targeting.py` | content edit (cosmetic, not an import): 3 prose comments naming `rockets_dm.py` -> `rockets.py` (the file they describe no longer exists under that name) | unchanged location |

Everything not listed above (`apps/`, `projects/examples/`, `projects/data/`, other `tests/*.py`) has no reference to `projects.fx27.campaigns`/`rockets_dm`/`regenerate_ideal_own`/`solvers.point.airbrake`/`runs.point.airbrake` (verified by repo-wide grep) and needs no change.

## S44.4 Nesting-conflict resolution: `data/aero`, `data/airbrake`, `data/motors`

The brief's literal ask (item 3) is `campaigns/` -> `data/`. Doing only that produces `projects/fx27/data/cspace/data/aero/*.csv` (and `.../data/motors/`, `.../data/airbrake/`) — the inner `data/` segment, which existed only to disambiguate CSV data from the `.py` config modules sitting at the same `campaigns/cspace/` level, becomes redundant once the outer folder is itself named `data/`.

**Recommendation: flatten the inner `data/` away.** Result: `data/cspace/aero/*.csv`, `data/cspace/motors/*.csv`, `data/cspace/airbrake/*.csv`, sitting as siblings of `rockets.py`/`scenarios.py`/etc. at the same `data/cspace/` level. Reasoning:

1. The outer rename already does the job the inner `data/` segment used to do (signal "this is config, that is data") — the directory is now named `data/` at the point where ambiguity would otherwise exist, so a second nested `data/` says nothing a reader doesn't already know from the path.
2. `projects/fx27/data/cspace/data/...` reads as a typo/mistake to anyone unfamiliar with the history, not an intentional structure — it fails a fresh-eyes readability check.
3. Doing nothing (leaving `data/cspace/data/aero/`) saves zero work today but leaves a permanent, confusing artifact that the next person has to understand the history of this ticket to explain.

**Applied consistently, including `data/airbrake/` (the other session's folder) and `euroc/data/motors/`** (flattened to `euroc/motors/`), even though the user's literal question was only about the `aero`/outer-rename interaction and euroc's `motors/` folder was never called out as a conflict. Reasoning for extending the same treatment to euroc, stated plainly since this goes beyond the literal ask: leaving `data/cspace/{aero,motors,airbrake}/` flattened while `data/euroc/data/motors/` keeps its inner `data/` would be an asymmetric, undocumented inconsistency between the two campaigns for no reason tied to any actual ambiguity (euroc has no config/data name collision risk different from cspace's) — purely a matter of not leaving a structural inconsistency as a side effect of fixing one.

**`generate_dm_tables.py` stays where it lands (`data/cspace/aero/`), NOT moved to `runs/`.** It is also a one-off executable tool (like `regenerate_ideal_own.py`), which could suggest the same "campaigns/ should be only data" argument applies. It is left alone because: (a) the user's verbatim instruction (item 2) named only `regenerate_ideal_own.py` for the move, not this file; (b) unlike `regenerate_ideal_own.py` (which sat at the top `campaigns/cspace/` level, directly alongside the `.py` config modules the user called "should be only data"), `generate_dm_tables.py` already lives one level down, inside the CSV data subfolder it generates — it reads as "the tool that produces this specific dataset," co-located with its own output, which is a defensible and common pattern, not the thing the user's complaint was about. This is a judgment call, not a user decision point: low stakes (a one-off, non-runtime, already-isolated script), reversible later at zero cost, and consistent with the user's stated reasoning rather than contradicting it.

**Where item 5's future home lands:** once the other session's real (non-ideal) airbrake run-script work continues, its data will already live at `projects/fx27/data/cspace/airbrake/` (this ticket's flattened location) rather than `campaigns/cspace/data/airbrake/`. No action needed now — noted for whoever picks up that follow-on ticket.

## S44.5 Full import-path / docstring update list

All of the following are mechanical (grep-and-replace `projects.fx27.campaigns` -> `projects.fx27.data`, plus the flattening path segment drop in `_paths.py`, plus the `rockets_dm` merge fallout, plus the two `airbrake.py` renames). No logic changes anywhere in this list.

**Import statements (code):**

| File | Old | New |
|---|---|---|
| `data/cspace/rockets_ideal.py` | `from projects.fx27.campaigns.cspace.rockets import PRO54_TRANSITION, PRO75` + `from projects.fx27.campaigns.cspace.rockets_dm import PRO54_TRANSITION_DM, PRO75_DM` | `from projects.fx27.data.cspace.rockets import (PRO54_TRANSITION, PRO75, PRO54_TRANSITION_DM, PRO75_DM)` (one merged import, since both now live in one module) |
| `data/cspace/scenarios.py` | `from projects.fx27.campaigns.cspace import motors, rockets, rockets_ideal` + `from projects.fx27.campaigns.cspace.{site,weather} import ...` | `from projects.fx27.data.cspace import motors, rockets, rockets_ideal` + `from projects.fx27.data.cspace.{site,weather} import ...` |
| `data/cspace/scenarios_dm.py` | `from projects.fx27.campaigns.cspace import motors, rockets_dm, rockets_ideal` + site/weather | `from projects.fx27.data.cspace import motors, rockets, rockets_ideal` + site/weather; **and** every `rockets_dm.PRO54_TRANSITION_DM`/`PRO54_EQUAL_DM`/`PRO75_DM` usage (3 call sites) -> `rockets.PRO54_TRANSITION_DM`/etc. |
| `data/cspace/airbrake_data.py` | `from projects.fx27._paths import cspace_airbrake` | unchanged (import target, `_paths.py`, doesn't move — only its internal constant changes, S44.3) |
| `runs/point/regenerate_ideal_own.py` (moved) | `from projects.fx27.campaigns.cspace.scenarios import SCENARIOS` + `...scenarios_dm import SCENARIOS_DM` | `from projects.fx27.data.cspace.scenarios import SCENARIOS` + `...scenarios_dm import SCENARIOS_DM`; `_TARGET` path computation (`Path(__file__).resolve().parent / "rockets_ideal.py"`) must change since the script no longer lives next to `rockets_ideal.py` — becomes `Path(__file__).resolve().parent.parent.parent / "data" / "cspace" / "rockets_ideal.py"` or equivalent explicit anchor (developer's call on the cleanest spelling; must still point at the real file) |
| `solvers/point/ideal_open_airbrake.py` (renamed) | (no `campaigns` import — only `apps.*`) | no import changes beyond the file rename itself |
| `runs/point/ideal_open_airbrake.py` (renamed) | `from projects.fx27.campaigns.cspace.scenarios import SCENARIOS` + `...scenarios_dm import SCENARIOS_DM` + `from projects.fx27.solvers.point.airbrake import print_brake_report, size_airbrake` | `from projects.fx27.data.cspace.scenarios import SCENARIOS` + `...scenarios_dm import SCENARIOS_DM` + `from projects.fx27.solvers.point.ideal_open_airbrake import print_brake_report, size_airbrake` |
| `runs/point/ideal_drag.py`, `ideal_mass.py` | `from projects.fx27.campaigns.cspace.rockets_ideal import (...)` + scenarios/scenarios_dm | `from projects.fx27.data.cspace.rockets_ideal import (...)` + scenarios/scenarios_dm |
| `runs/point/point.py`, `comparison.py`, `sweep.py` | `from projects.fx27.campaigns.{cspace,euroc}.*` | `from projects.fx27.data.{cspace,euroc}.*` |
| `solvers/point/controller.py` (other session) | `from projects.fx27.campaigns.cspace.airbrake_data import AirbrakeHardware` | `from projects.fx27.data.cspace.airbrake_data import AirbrakeHardware` |
| `runs/point/controller.py` (other session) | `from projects.fx27.campaigns.cspace import airbrake_data` + `from projects.fx27.campaigns.cspace.scenarios import SCENARIOS` | `from projects.fx27.data.cspace import airbrake_data` + `from projects.fx27.data.cspace.scenarios import SCENARIOS` |
| `data/cspace/rockets.py` (merged, S44.6) | `from projects.fx27.campaigns.cspace import rockets` (inside old `rockets_dm.py`) | removed entirely — same-module references after merge |
| `data/euroc/scenarios.py` | `from projects.fx27.campaigns.euroc.{motors,rockets,site,weather} import ...` | `from projects.fx27.data.euroc.{motors,rockets,site,weather} import ...` |
| `tests/test_fx27_port.py` | 5 lines: `campaigns.cspace.rockets_ideal`, `campaigns.cspace.scenarios`, `campaigns.cspace.scenarios_dm`, `campaigns.euroc.motors`, `campaigns.euroc.scenarios`; + `from projects.fx27.solvers.point.airbrake import size_airbrake` | `data.cspace.*` / `data.euroc.*` equivalents; + `from projects.fx27.solvers.point.ideal_open_airbrake import size_airbrake` |
| `tests/test_regenerate_ideal_own.py` | 6 lines incl. `from projects.fx27.campaigns.cspace import motors, rockets_ideal` + `from projects.fx27.campaigns.cspace.regenerate_ideal_own import (...)` | `from projects.fx27.data.cspace import motors, rockets_ideal` + `from projects.fx27.runs.point.regenerate_ideal_own import (...)` (module moved, not just renamed namespace) + remaining 4 lines `campaigns.cspace.*` -> `data.cspace.*` |

**Self-referencing docstring path headers** (convention in this codebase: module's own first-line docstring states its own path, e.g. `"""projects/fx27/campaigns/cspace/rockets.py -- ..."""`) — every moved file's own header line updates to its new path: `campaigns/__init__.py`, `campaigns/cspace/__init__.py`, `campaigns/euroc/__init__.py`, `cspace/{motors,site,weather,scenarios,scenarios_dm,airbrake_data}.py`, `euroc/{motors,rockets,site,weather,scenarios}.py`, `data/aero/generate_dm_tables.py` (2 self-path mentions, line 2 and the `Run:`-equivalent line 22), `rockets_ideal.py`, `solvers/point/ideal_open_airbrake.py`, `runs/point/ideal_open_airbrake.py`, `runs/point/regenerate_ideal_own.py` (moved).

**Non-import prose mentions needing updates (docstrings, not architecture docs):**

- `regenerate_ideal_own.py`'s own docstring: "Run manually whenever `rockets.py`/`rockets_dm.py`'s base dry mass..." -> after merge there is only `rockets.py`; and "...which still lives in `rockets_dm.py` after SS42.3's trim (now the *only* thing left in that file)..." -> rewrite to reflect the merge (that content now lives in `rockets.py`'s dm section, `rockets_dm.py` no longer exists); and its own `Run:` line -> `python -m projects.fx27.runs.point.regenerate_ideal_own`.
- `rockets_ideal.py`'s Section B1 comment telling a future reader to re-run via `python -m projects.fx27.campaigns.cspace.regenerate_ideal_own` -> `python -m projects.fx27.runs.point.regenerate_ideal_own`.
- `runs/point/ideal_open_airbrake.py`'s own `Run:` line: `python -m projects.fx27.runs.point.airbrake` -> `python -m projects.fx27.runs.point.ideal_open_airbrake`.
- `tests/test_apogee_targeting.py`: 3 prose comments naming `rockets_dm.py` -> `rockets.py` (cosmetic accuracy fix, not an import; low priority but cheap and avoids pointing at a deleted filename).
- `_paths.py`'s own module docstring references "`campaigns/cspace/data/...`"-style paths in its prose (`cspace_motor`/`cspace_aero`/`cspace_airbrake` docstrings, 4 mentions) -> update to the flattened `data/cspace/...` form.

**Out of scope for text updates (explicitly, per brief):** `dev/docs/architecture-38/40/41/42/43-*.md`, `dev/docs/step-*-notes.md`, `dev/docs/task-152-*.md` — none of these are edited by this ticket. `projects/fx27/README.md` — pre-existing staleness, left for `readme-keeper` (S44.1).

## S44.6 `rockets.py` + `rockets_dm.py` merge design

Target: one file, `data/cspace/rockets.py`, keeping the `rockets.py` name (the obvious default per the brief — `rockets_dm` has no independent reason to be the surviving name, and every external caller of the dc variants already says `rockets.PRO54_TRANSITION` etc., so keeping that name is the smaller total edit).

Structure (developer's exact prose/wording discretion, but the shape is fixed):

1. One merged module docstring combining both files' rationale (radius/Aero/Option-C invariant from the current `rockets.py` header, plus the dm-table/`dataclasses.replace` rationale from `rockets_dm.py`'s header, plus a note that the 4 "ideal" dm variants live in `rockets_ideal.py` Section B2, not here — carried over from `rockets_dm.py`'s own docstring, last paragraph).
2. `import dataclasses` added once at the top (needed for the dm section; the dc section doesn't need it).
3. `from projects.fx27.data._paths import cspace_aero` (renamed from `.campaigns` location) for the dm table paths — only needed in the dm half.
4. Existing dc section (`_RADIUS_M`, `_AERO`, `_LENGTHS`, `_SECTIONS`, `_airframe()`, `PRO54_TRANSITION`, `PRO54_EQUAL`, `PRO75`) unchanged content.
5. dm section appended below: `_TABLE_PRO54_TRANSITION`/`_TABLE_PRO54_EQUAL`/`_TABLE_PRO75` (the `cspace_aero(...)` calls), `_dm_aero()` helper, `PRO54_TRANSITION_DM`/`PRO54_EQUAL_DM`/`PRO75_DM` — **every `rockets.PRO54_TRANSITION` reference in the old `rockets_dm.py` becomes a bare `PRO54_TRANSITION`** (same-module reference, no more `from ... import rockets` self-import needed).

**Callers to update (exhaustive, confirmed by repo-wide grep, S44.5 has the per-file detail):**
- `rockets_ideal.py` (2 import lines -> 1 merged import line)
- `scenarios_dm.py` (1 import line's module list changes `rockets_dm` -> `rockets`; 3 usage sites `rockets_dm.X` -> `rockets.X`)
- `regenerate_ideal_own.py`'s own docstring prose (2 mentions, not an import — it never imports `rockets`/`rockets_dm` directly, only reads them transitively via `scenarios`/`scenarios_dm`)
- `tests/test_apogee_targeting.py`'s 3 prose comments (cosmetic, S44.5)

**Confirmed NOT a caller:** `scenarios.py` imports `rockets` (not `rockets_dm`) already — no change beyond the `campaigns`->`data` path rename it needs anyway.

## S44.7 Acceptance criteria

1. Full suite: `python -m pytest -q` -> **899 passed, 0 failed** (same count as the Step 151/152 baseline — not fewer, not more; a changed count after a pure reorg means something was missed or double-collected, not progress).
2. `data/cspace/rockets_ideal.py`'s Section A (the 4-constant AC-3 oracle block) is **byte-for-byte identical** to the current `campaigns/cspace/rockets_ideal.py`'s Section A — verify with `git diff --no-index` (or equivalent) restricted to that section's line range before/after, not just "tests still pass" (a byte change that happens to not move any pin would still violate this).
3. No file at any of: `projects/fx27/campaigns/` (the whole old directory, including `__init__.py`, must be gone — not left as a dangling empty shell or a re-export shim), `projects/fx27/data/cspace/rockets_dm.py`, `projects/fx27/solvers/point/airbrake.py`, `projects/fx27/runs/point/airbrake.py`, `projects/fx27/data/cspace/regenerate_ideal_own.py`, `projects/fx27/data/cspace/data/` (the inner, now-redundant `data/` segment must not survive under any of the three cspace categories, nor under euroc).
4. `projects/fx27/data/cspace/airbrake/` (or wherever item 5's future home lands) is **not created or populated with any NEW content by this ticket** beyond moving what the other session already wrote (`pro54-transition-airbrake.csv`, `pro75-airbrake.csv`, `airbrake_data.py`) to their new flattened path — no new loader, no new CSV, no new consuming script (item 5 stays out of scope).
5. `rg -n "projects\.fx27\.campaigns"` (or equivalent) over `projects/` + `tests/` returns **zero matches** on completion (confirms no import path was missed).
6. `rg -n "campaigns/cspace|campaigns/euroc"` over `projects/fx27/**/*.py` docstrings returns zero matches (self-referencing path headers all updated) — `dev/docs/*` is exempt (out of scope, S44.1/S44.5).
7. `git status --short` immediately before declaring the ticket set done shows no unexpected new path outside what this doc already accounts for (S44.1's residual-risk check, repeated by the developer at the end of the last ticket, not just by the architect at the start).

## S44.8 Rejected options

- **Leave `campaigns/cspace/data/aero/` nested under the renamed `data/cspace/data/aero/`** (i.e., do only the literal outer rename, no flattening) — rejected per S44.4: produces a redundant, confusing double-`data` path for zero benefit; the ticket explicitly asked for this judgment call to be made and justified, not deferred.
- **Rename the merged rockets file to something other than `rockets.py`** (e.g. `rockets_all.py`, `airframes.py`) — rejected: every external caller already spells the dc names as `rockets.PRO54_TRANSITION`, so keeping the name `rockets.py` is strictly the smaller, more mechanical edit, with no naming-clarity loss (the file's own docstring already explains it now covers both dc and dm).
- **Move `generate_dm_tables.py` to `runs/point/` alongside `regenerate_ideal_own.py`** (treating both as "one-off tools that don't belong under data") — rejected per S44.4: not requested, and it is already co-located with the specific dataset it produces one level into the data tree, not sitting at the same level as the `.py` config modules the user's complaint was about.
- **Keep a `rockets_dm` re-export shim** (`rockets_dm.py` that just does `from .rockets import *`) to avoid touching `scenarios_dm.py`/`rockets_ideal.py`'s imports — rejected: the user asked for ONE file, a shim leaves two files on disk; the actual caller-update cost is 2 files (S44.6), trivial enough that the shim buys nothing.

## S44.9 Tickets FX27E-1..6

All tickets are **sequential** (`parallel_safe: false`, chained `depends_on`) — the import graph in S44.5 has enough overlap (`rockets_ideal.py`, `scenarios_dm.py`, `_paths.py` each touched by more than one logical change) that parallel execution risks two agents racing on the same file. Given the live cross-session collision already in play (S44.1), minimizing moving parts further is worth more here than parallelism would save.

### [FX27E-1] Directory rename `campaigns/` -> `data/` + flatten inner `data/` subfolders + repoint `_paths.py`
- **Module/boundaries:** `projects/fx27/campaigns/**` (entire tree, moves to `projects/fx27/data/**`, flattening `cspace/data/{aero,motors,airbrake}/` -> `cspace/{aero,motors,airbrake}/` and `euroc/data/motors/` -> `euroc/motors/`); `projects/fx27/_paths.py`; `projects/fx27/solvers/point/controller.py`, `projects/fx27/runs/point/controller.py` (import-path lines only, per S44.1's residual-risk check — re-verify their content hasn't drifted before editing); every file listed in S44.5's import-statement table (path substitution only, content logic untouched)
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false

Move the whole `campaigns/` tree to `data/`, flattening the inner `data/` subfolder under each of `cspace/{aero,motors,airbrake}` and `euroc/motors` (S44.4 — do NOT preserve the inner `data/` segment anywhere). Update `_paths.py`'s `MOTORS_CSPACE`/`MOTORS_EUROC`/`AERO_CSPACE`/`AIRBRAKE_CSPACE` constants and the 4 docstring path mentions in its function docstrings (`cspace_motor`/`euroc_motor`/`cspace_aero`/`cspace_airbrake`) to the new flattened paths. Update every `from projects.fx27.campaigns...` import across `projects/fx27/**` and `tests/**` to `from projects.fx27.data...` (full list: S44.5's import-statement table — every row except the ones specific to the rockets merge/regenerate move/airbrake rename, which are FX27E-2/3/4's job). Update every self-referencing docstring path header in every moved file (S44.5's list). Before touching `_paths.py`, `solvers/point/controller.py`, `runs/point/controller.py`: re-check `git status --short`/`git diff` on exactly those 3 paths — if content has changed since this doc was written, apply the same mechanical substitution to whatever is there; if a path outside this doc's accounted-for set appears, stop and report `needs_input` instead of reworking the plan. Do not yet merge `rockets.py`/`rockets_dm.py`, move `regenerate_ideal_own.py`, or rename `airbrake.py` — those are FX27E-2/3/4, done inside the now-renamed `data/` tree.

### [FX27E-2] Merge `rockets.py` + `rockets_dm.py`
- **Module/boundaries:** `projects/fx27/data/cspace/rockets.py`, `projects/fx27/data/cspace/rockets_dm.py` (deleted), `projects/fx27/data/cspace/rockets_ideal.py` (2 import lines only), `projects/fx27/data/cspace/scenarios_dm.py` (1 import line + 3 usage sites)
- **Assignee:** developer
- **depends_on:** [FX27E-1]
- **parallel_safe:** false

Merge per S44.6's structure into one `rockets.py`. Delete `rockets_dm.py`. Update `rockets_ideal.py`'s 2 import lines into 1 merged import (S44.5). Update `scenarios_dm.py`'s import (`rockets_dm` -> `rockets`) and its 3 `rockets_dm.X` usage sites -> `rockets.X`. Confirm `scenarios.py` needs no further change beyond FX27E-1's path rename (it already imports `rockets`, not `rockets_dm`). Run `tests/test_apogee_targeting.py` and `tests/test_fx27_port.py` after this ticket (point-tests, not full suite yet) to catch any missed usage site early.

### [FX27E-3] Move `regenerate_ideal_own.py` to `runs/point/`
- **Module/boundaries:** `projects/fx27/data/cspace/regenerate_ideal_own.py` -> `projects/fx27/runs/point/regenerate_ideal_own.py`; `projects/fx27/data/cspace/rockets_ideal.py` (1 comment line, Section B1's "re-run" pointer); `tests/test_regenerate_ideal_own.py` (import path)
- **Assignee:** developer
- **depends_on:** [FX27E-2]
- **parallel_safe:** false

Move the file. Update its own docstring: path header, the "`rockets.py`/`rockets_dm.py`" mention (now just `rockets.py`, post-merge), the "rockets_dm.py... now the only thing left in that file" sentence (rewrite — that file no longer exists), and its `Run:` line to `python -m projects.fx27.runs.point.regenerate_ideal_own`. Fix `_TARGET`'s path computation (S44.5 — it no longer sits next to `rockets_ideal.py`, needs an explicit anchor to `data/cspace/rockets_ideal.py`). Update `rockets_ideal.py`'s own Section B1 comment pointing at the old invocation path. Update `tests/test_regenerate_ideal_own.py`'s import of `regenerate_ideal_own` from `projects.fx27.data.cspace.regenerate_ideal_own` to `projects.fx27.runs.point.regenerate_ideal_own` (module moved, not just the `campaigns`->`data` substitution FX27E-1 already did for its other 5 import lines). Run `tests/test_regenerate_ideal_own.py` point-test after this ticket.

### [FX27E-4] Rename `airbrake.py` -> `ideal_open_airbrake.py` (both solvers and runs)
- **Module/boundaries:** `projects/fx27/solvers/point/airbrake.py` -> `ideal_open_airbrake.py`; `projects/fx27/runs/point/airbrake.py` -> `ideal_open_airbrake.py`; `tests/test_fx27_port.py` (1 import line)
- **Assignee:** developer
- **depends_on:** [FX27E-1]
- **parallel_safe:** false (shares `tests/test_fx27_port.py` with FX27E-1/5's edits; keep sequential)

Pure rename, both files. Function names (`size_airbrake`, `print_brake_report`, `BrakeSizing`) unchanged — do not touch them (S44's brief: keep mechanical, no reason to rename functions, and the cross-session risk means a smaller diff is safer). Update `runs/point/ideal_open_airbrake.py`'s own import of the solvers module (`from projects.fx27.solvers.point.airbrake import ...` -> `...ideal_open_airbrake import ...`) and its own `Run:` docstring line. Update `tests/test_fx27_port.py`'s `from projects.fx27.solvers.point.airbrake import size_airbrake` -> `...ideal_open_airbrake import size_airbrake`. Re-confirm before starting: `git status`/`grep` for any NEW reference to `solvers.point.airbrake`/`runs.point.airbrake` that might have appeared from the other session's controller work since this doc was written (S44.1 confirmed none existed at investigation time) — if found, stop and report `needs_input`.

### [FX27E-5] Test import-path sweep + stale-comment cleanup
- **Module/boundaries:** `tests/test_fx27_port.py`, `tests/test_regenerate_ideal_own.py`, `tests/test_apogee_targeting.py` (verification/cleanup pass after FX27E-1..4; mostly already done by those tickets' own scope, this ticket is the "did we actually get all of them" check)
- **Assignee:** developer
- **depends_on:** [FX27E-1, FX27E-2, FX27E-3, FX27E-4]
- **parallel_safe:** false

Run `rg -n "projects\.fx27\.campaigns"` and `rg -n "rockets_dm"` and `rg -n "solvers\.point\.airbrake|runs\.point\.airbrake"` over `tests/` — must return zero matches except `tests/test_apogee_targeting.py`'s 3 prose comments, which this ticket fixes (S44.5: `rockets_dm.py` -> `rockets.py` in those 3 comments, cosmetic only, no test logic change). This is a safety-net ticket, not new test coverage (D-181 policy: no new tests for this move).

### [FX27E-6] Full suite verification + acceptance-criteria check
- **Module/boundaries:** none (verification only, no file edits unless a gap from FX27E-1..5 surfaces, in which case loop back to the relevant prior ticket rather than patching ad hoc here)
- **Assignee:** developer
- **depends_on:** [FX27E-1, FX27E-2, FX27E-3, FX27E-4, FX27E-5]
- **parallel_safe:** false

Run the full suite (`python -m pytest -q`, backgrounded per this project's test-runtime convention) and confirm **899 passed, 0 failed**. Verify `rockets_ideal.py` Section A is byte-for-byte unchanged (diff the current file's Section A line range against a pre-reorg copy or `git show` of the pre-move blob). Walk S44.7's acceptance-criteria list item by item, including the two `rg` sweeps (criteria 5-6) and the final `git status --short` collision re-check (criterion 7) — report any surviving `campaigns` reference, any leftover `data/cspace/data/` nesting, or any new unaccounted-for path from the other session as a finding, not a silent fix.

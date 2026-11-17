# Architecture 43 — fx27 `point/` + `runs/` restructuring (Phase 2.27)

## Кратко (RU)

- Это чисто организационная перестройка `projects/fx27/` по просьбе пользователя — без новой физики и без архитектурной развилки стека (стек уже утверждён).
- Переезд 1: `projects/fx27/point/` (общая библиотека — решатель одного полёта, метрики, валидность, графики, оценщики) переезжает в `projects/fx27/solvers/point/`. Новый верхний пакет называется `solvers`, сам под-модуль сохраняет имя `point`.
- Переезд 2: в `projects/fx27/runs/` исчезают папки `cspace/` и `euroc/`; вместо них — одна папка `runs/point/` (имя совпадает с именем выше, но полный путь другой — `solvers.point` vs `runs.point`, конфликта нет). В неё переезжают все скрипты-точки входа, по одному файлу на *тип* анализа (`comparison.py`, `sweep.py`, `ideal_mass.py`, `ideal_drag.py`, `airbrake.py`, `point.py`), а не по соревнованию.
- Только один файл требует реального слияния логики, а не просто переноса: `runs/point/comparison.py` объединяет три существующих скрипта (`cspace/comparison.py` 7 строк, `cspace/comparison_dc_dm.py` 14 строк dc/dm, `euroc/comparison.py` 24 комбо) — выбор случая через новый флаг `--case {cspace,cspace_dc_dm,euroc}` (default `cspace`, сохраняет старое поведение "без флагов"). Остальные 5 типов (`sweep`, `ideal_mass`, `ideal_drag`, `airbrake`, `point`) сегодня существуют только для одного из двух соревнований — переезд для них чисто механический (только путь импорта), содержимое не меняется.
- **Развилка для пользователя** (не решаю молча): как выбирать случай в объединённом `comparison.py` — CLI-флаг `--case` (рекомендую), комментирование блока в коде (буквальная формулировка пользователя), или гибрид обоих. См. раздел "Decision required" ниже.
- `campaigns/` (включая `rockets_ideal.py` с защищённой AC-3 границей) вне скоупа — не трогается вообще, только о нём не забыть при импортах.
- Тестовая политика (D-181): только обновление путей импорта в `tests/test_fx27_port.py` и `tests/test_regenerate_ideal_own.py`, никаких новых тестов. Полный прогон должен остаться 899/0.
- 6 тикетов FX27D-1..6, строго последовательные (не параллельные — слишком плотное пересечение файлов для раздельных воркеров).

## Table of contents

- [SS43.1 Scope and non-goals](#ss431-scope-and-non-goals)
- [SS43.2 Current state (verified)](#ss432-current-state-verified)
- [SS43.3 Target file tree](#ss433-target-file-tree)
- [SS43.4 Per-file disposition](#ss434-per-file-disposition)
- [SS43.5 The `comparison.py` merge — design](#ss435-the-comparisonpy-merge--design)
- [SS43.6 Decision required — case-selector mechanism](#ss436-decision-required--case-selector-mechanism)
- [SS43.7 Import-path update list](#ss437-import-path-update-list)
- [SS43.8 Acceptance criteria](#ss438-acceptance-criteria)
- [SS43.9 Ticket list (FX27D-1..6)](#ss439-ticket-list-fx27d-1-6)
- [SS43.10 Rejected options](#ss4310-rejected-options)

## SS43.1 Scope and non-goals

This is Phase 2.27, additive/organisational restructuring on top of the already-approved stack (Python 3.12, numpy/scipy/matplotlib, pytest) — not a stack pivot, not a greenfield decision. No `grilling` gate is needed; this doc goes through the standard decision-table flow.

**In scope:**
- `projects/fx27/point/` → `projects/fx27/solvers/point/` (pure rename/move of a package).
- `projects/fx27/runs/{cspace,euroc}/` → `projects/fx27/runs/point/`, re-keyed from "one folder per competition" to "one file per analysis type", merging `comparison.py`/`comparison_dc_dm.py`/euroc's `comparison.py` into a single file.
- Updating every import path this move breaks (`projects/fx27/**` and `tests/**`).

**Explicitly out of scope — do not touch:**
- `projects/fx27/campaigns/**` (incl. `campaigns/cspace/rockets_ideal.py`, whose Section A 4 constants are a byte-for-byte AC-3 oracle boundary guarded by `tests/test_fx27_port.py` — nothing in this phase changes its content, and its import path is untouched since `campaigns/` itself does not move).
- `apps/**` (the engine/toolkit layer) — nothing here changes.
- The package-everywhere (`__init__.py` on every directory) convention — required by this project's `python -m projects.fx27....` execution convention and relative-import style (orchestrator already answered the user on this directly); this restructuring must keep every new directory a proper package, not remove `__init__.py` files.
- `tests/test_layering.py`'s G1-G6 guards — they scan `sim/apps/configs` roots only, never `projects/fx27/`, so this move does not interact with them at all (verified by reading the guard's `IMPORTABILITY_ROOTS`/`NETWORK_SCAN_ROOTS`/`RETIRED_PATHS` constants — none mention `projects`).

## SS43.2 Current state (verified)

Verified via `Glob`/`Read`/`Grep` across `projects/fx27/**/*.py` and `tests/**/*.py` (not from memory):

```
projects/fx27/point/__init__.py
projects/fx27/point/airbrake.py       -- library: size_airbrake(), print_brake_report()
projects/fx27/point/comparison.py     -- library: run_many(), evaluate_scenarios(), print_table(), save_csv()
projects/fx27/point/estimate.py       -- library: thin re-export of apps.optimization.apogee_targeting.solve
projects/fx27/point/flight.py         -- library: FlightRun, run() -- assemble+run_sim+flight_stats
projects/fx27/point/metrics.py        -- library: Row, row_from_flight()
projects/fx27/point/plots.py          -- library: plot_displacement_comparison(), plot_kinematics_comparison(), show_if_requested()
projects/fx27/point/validity.py       -- library: ValidityReport, check_validity(), print_validity()

projects/fx27/runs/__init__.py
projects/fx27/runs/cspace/__init__.py
projects/fx27/runs/cspace/airbrake.py         -- script, cspace-only, no euroc equivalent
projects/fx27/runs/cspace/comparison.py       -- script, cspace dc case (7 rows + 2 plots + CSV)
projects/fx27/runs/cspace/comparison_dc_dm.py -- script, cspace dc+dm case (14 rows + 2 plots + CSV)
projects/fx27/runs/cspace/ideal_drag.py       -- script, cspace-only, no euroc equivalent
projects/fx27/runs/cspace/ideal_mass.py       -- script, cspace-only, no euroc equivalent
projects/fx27/runs/cspace/point.py            -- script, cspace-only, no euroc equivalent (single flight)
projects/fx27/runs/euroc/__init__.py
projects/fx27/runs/euroc/comparison.py        -- script, euroc case (24 runnable combos, CSV only, no plots)
projects/fx27/runs/euroc/sweep.py             -- script, euroc-only, no cspace equivalent
```

**Key finding driving the merge design:** of the 6 "analysis types" implied by the file names, only `comparison` exists for *both* competitions today (`cspace/comparison.py` + `cspace/comparison_dc_dm.py` + `euroc/comparison.py` — 3 files, 1 type). The other 5 types (`airbrake`, `ideal_drag`, `ideal_mass`, `point`, `sweep`) each exist for exactly one competition today — `sweep` is euroc-only, the other four are cspace-only. So "one file per type, comment out/select the unwanted campaign" only requires *real* multi-case logic for `comparison.py`; the other 5 are pure moves (path-only changes), because there is nothing to merge — each already has exactly one case.

**All of `point/*.py` is pure library code** — no `argparse`, no `if __name__ == "__main__"`, no network, no file-path literals outside `estimate.py`'s re-export. Confirmed by reading every file in full. This settles the "library vs run-script" question the orchestrator flagged as a possible fork: there is no ambiguity, the whole package is library, `solvers/point/` is a clean 1:1 move.

**Import graph** (from `Grep -rn 'from projects\.fx27|import projects\.fx27'`):
- `runs/cspace/*.py` and `runs/euroc/*.py` import from `projects.fx27.campaigns.<own-competition>.*` (data) and `projects.fx27.point.*` (library). Neither `runs/` subfolder imports the other, and neither imports anything from `runs/` itself.
- `campaigns/cspace/*.py` and `campaigns/euroc/*.py` import only within their own competition's `campaigns/` subtree (plus `projects.fx27._paths`) — confirms `campaigns/` has zero dependency on `point/` or `runs/`, so it is fully decoupled from this move (as expected, it is out of scope).
- `tests/test_fx27_port.py` imports from `projects.fx27.campaigns.{cspace,euroc}.*`, `projects.fx27.point.*` (4 names: `airbrake`, `comparison`, `estimate`, `metrics`, `plots`), and `projects.fx27.runs.cspace.point` (as `point_cli`, in 2 tests).
- `tests/test_regenerate_ideal_own.py` imports from `projects.fx27.campaigns.cspace.*` and `projects.fx27.point.{comparison,flight,metrics}`.
- No test imports `runs.cspace.{comparison,comparison_dc_dm,airbrake,ideal_drag,ideal_mass}` or `runs.euroc.{comparison,sweep}` directly — those 7 run scripts are exercised by hand (`python -m ...`), never by pytest. This matters for SS43.8's acceptance criteria: the 899/0 count is unaffected by changes to any of these 7 files' *content*, only by the 2 test files' import paths.

## SS43.3 Target file tree

```
projects/fx27/solvers/__init__.py              NEW -- package marker + 1-paragraph docstring
                                                     ("launch-config-agnostic shared solver code;
                                                      today only point/, name reserved for any
                                                      future solver family alongside point mass")
projects/fx27/solvers/point/__init__.py        MOVED verbatim from projects/fx27/point/__init__.py
projects/fx27/solvers/point/airbrake.py        MOVED verbatim (pure library, no import changes needed)
projects/fx27/solvers/point/comparison.py      MOVED verbatim (pure library, no import changes needed)
projects/fx27/solvers/point/estimate.py        MOVED verbatim (pure library, no import changes needed)
projects/fx27/solvers/point/flight.py          MOVED verbatim (pure library, no import changes needed)
projects/fx27/solvers/point/metrics.py         MOVED verbatim (pure library, no import changes needed)
projects/fx27/solvers/point/plots.py           MOVED verbatim (pure library, no import changes needed)
projects/fx27/solvers/point/validity.py        MOVED verbatim (pure library, no import changes needed)

projects/fx27/runs/__init__.py                 UPDATED docstring only (no longer "one folder per
                                                     competition" -- now "one file per analysis type")
projects/fx27/runs/point/__init__.py           NEW -- package marker + short docstring
projects/fx27/runs/point/airbrake.py           MOVED from runs/cspace/airbrake.py, import-path fix only
projects/fx27/runs/point/comparison.py         MERGED from runs/cspace/comparison.py +
                                                     runs/cspace/comparison_dc_dm.py +
                                                     runs/euroc/comparison.py -- see SS43.5
projects/fx27/runs/point/ideal_drag.py         MOVED from runs/cspace/ideal_drag.py, import-path fix only
projects/fx27/runs/point/ideal_mass.py         MOVED from runs/cspace/ideal_mass.py, import-path fix only
projects/fx27/runs/point/point.py              MOVED from runs/cspace/point.py, import-path fix only
projects/fx27/runs/point/sweep.py              MOVED from runs/euroc/sweep.py, import-path fix only

-- DELETED entirely --
projects/fx27/runs/cspace/   (incl. __init__.py and all 6 files above)
projects/fx27/runs/euroc/    (incl. __init__.py and both files above)

-- UNCHANGED, out of scope --
projects/fx27/campaigns/**   (cspace/, euroc/, incl. rockets_ideal.py)
projects/fx27/_paths.py
projects/fx27/__init__.py
```

**Name-collision note (flagged per the orchestrator's instruction):** `projects/fx27/solvers/point/` and `projects/fx27/runs/point/` share the leaf name `point`, and inside the latter there is also a file literally named `point.py` (single-flight script) — so the full dotted path `projects.fx27.runs.point.point` has "point" three times at different levels. This is legal and unambiguous (`runs.point` is a package, `runs.point.point` is a module inside it, distinct from `solvers.point` which is a different package entirely) but reads awkwardly; ticket FX27D-2 (SS43.9) must keep every docstring/comment inside these files explicit about which "point" is meant, and this doc's table above spells out the disambiguation once so neither the developer nor a later reader has to re-derive it.

## SS43.4 Per-file disposition

| Old path | New path | Disposition | Content change? |
|---|---|---|---|
| `point/__init__.py` | `solvers/point/__init__.py` | move | none (docstring's own path self-reference line updated, SS43.1) |
| `point/airbrake.py` | `solvers/point/airbrake.py` | move | none (imports only `apps.*`, already absolute, untouched) |
| `point/comparison.py` | `solvers/point/comparison.py` | move | none (relative imports `.flight`/`.metrics` stay valid unchanged) |
| `point/estimate.py` | `solvers/point/estimate.py` | move | none (imports only `apps.*`) |
| `point/flight.py` | `solvers/point/flight.py` | move | none (imports only `apps.*`) |
| `point/metrics.py` | `solvers/point/metrics.py` | move | none (relative import `.flight` stays valid) |
| `point/plots.py` | `solvers/point/plots.py` | move | none (imports only `apps.*`) |
| `point/validity.py` | `solvers/point/validity.py` | move | none (imports only `apps.*`) |
| — | `solvers/__init__.py` | **new file** | new short docstring (SS43.3) |
| `runs/__init__.py` | `runs/__init__.py` | stays, edited | docstring only (SS43.3) |
| `runs/cspace/__init__.py` | — | **deleted** | n/a |
| `runs/euroc/__init__.py` | — | **deleted** | n/a |
| — | `runs/point/__init__.py` | **new file** | new short docstring |
| `runs/cspace/airbrake.py` | `runs/point/airbrake.py` | move | imports `projects.fx27.point.*` → `projects.fx27.solvers.point.*`; `projects.fx27.campaigns.cspace.*` untouched |
| `runs/cspace/ideal_drag.py` | `runs/point/ideal_drag.py` | move | same import-path fix only |
| `runs/cspace/ideal_mass.py` | `runs/point/ideal_mass.py` | move | same import-path fix only |
| `runs/cspace/point.py` | `runs/point/point.py` | move | same import-path fix only |
| `runs/euroc/sweep.py` | `runs/point/sweep.py` | move | same import-path fix only (`projects.fx27.campaigns.euroc.*` untouched) |
| `runs/cspace/comparison.py` | `runs/point/comparison.py` | **merge** (1 of 3 sources) | becomes the `--case cspace` branch, see SS43.5 |
| `runs/cspace/comparison_dc_dm.py` | `runs/point/comparison.py` | **merge** (1 of 3 sources) | becomes the `--case cspace_dc_dm` branch, see SS43.5 |
| `runs/euroc/comparison.py` | `runs/point/comparison.py` | **merge** (1 of 3 sources) | becomes the `--case euroc` branch, see SS43.5 |

Every "import-path fix only" row above touches exactly one line group: the `from projects.fx27.point.X import ...` lines become `from projects.fx27.solvers.point.X import ...`. Nothing else in these 5 files changes — same `main()` body, same output filenames, same CLI flags (`--scenario`, `--validity`, `--show` where present), same printed text. This is intentionally the least risky kind of change: a developer running `git diff` on any of these 5 files post-move should see only import lines different, nothing in the function bodies.

## SS43.5 The `comparison.py` merge — design

The three source files were read in full (SS43.2); their `main()` bodies differ only in: (a) which scenario dict(s) they fly, (b) the printed table title and the Mach-warning note text, (c) whether they also render the 2 comparison figures (`cspace`/`cspace_dc_dm` do; `euroc` does not — it only ever wrote a CSV), (d) `euroc`'s extra "deferred combinations" print, and (e) `euroc` never had a `--show` flag (there is nothing to show). Everything else — the imports, the `--validity` handling via `check_validity`/`print_validity`, the `MachRangeWarning` capture idiom, `save_csv`, `output_dir()` — is identical boilerplate shared by all three today (literally copy-pasted across the 3 files per the Grep in SS43.2).

Merge shape: one file, one shared `main()` that parses a `--case` argument (mechanism pending SS43.6's decision) and dispatches to one of three case functions, each case function being close to a byte-for-byte lift of the corresponding old `main()` body (renamed, with its own `--validity`/`--show` args passed in via the shared `argparse.Namespace`, not re-parsed):

```python
"""projects/fx27/runs/point/comparison.py -- point-mass comparison run
script for both competitions (Phase 2.27 reorg, architecture-43 SS43.5).
Replaces 3 scripts:
  - runs/cspace/comparison.py        -> --case cspace       (default)
  - runs/cspace/comparison_dc_dm.py  -> --case cspace_dc_dm
  - runs/euroc/comparison.py         -> --case euroc

Run: python -m projects.fx27.runs.point.comparison [--case {cspace,cspace_dc_dm,euroc}] [--validity] [--show]
"""
from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning, peak_mach

from projects.fx27.campaigns.cspace.scenarios import SCENARIOS as _CSPACE_SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM as _CSPACE_SCENARIOS_DM
from projects.fx27.campaigns.euroc.scenarios import generate_scenarios as _euroc_generate_scenarios
from projects.fx27.solvers.point.comparison import print_table, run_many, save_csv
from projects.fx27.solvers.point.metrics import row_from_flight
from projects.fx27.solvers.point.plots import (
    plot_displacement_comparison, plot_kinematics_comparison, show_if_requested,
)
from projects.fx27.solvers.point.validity import check_validity, print_validity


def _run_cspace(args: argparse.Namespace) -> None:
    """Body = old runs/cspace/comparison.py main(), unchanged (7 rows, 2 figures, 1 CSV)."""
    ...  # exact old body, SCENARIOS -> _CSPACE_SCENARIOS, output filenames unchanged ("fx27_cspace_*")


def _run_cspace_dc_dm(args: argparse.Namespace) -> None:
    """Body = old runs/cspace/comparison_dc_dm.py main(), unchanged (14 rows, 2 figures, 1 CSV,
    2 warning notes: dc caveat + dm informational)."""
    ...  # exact old body, output filenames unchanged ("fx27_cspace_dc_dm_*")


def _run_euroc(args: argparse.Namespace) -> None:
    """Body = old runs/euroc/comparison.py main(), unchanged (<=24 rows, CSV only, no figures,
    deferred-combinations line). args.show is accepted but unused here -- there is nothing to
    show, same as the old script never offering --show at all."""
    ...  # exact old body, output filename unchanged ("fx27_euroc_comparison.csv")


_CASES = {"cspace": _run_cspace, "cspace_dc_dm": _run_cspace_dc_dm, "euroc": _run_euroc}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="cspace", choices=sorted(_CASES))
    ap.add_argument("--validity", action="store_true", help="... (SS38.5.7)")
    ap.add_argument("--show", action="store_true", help="... (ignored for --case euroc)")
    args = ap.parse_args(argv)
    _CASES[args.case](args)


if __name__ == "__main__":
    main()
```

Design properties worth calling out explicitly:
- **Default invocation is behaviour-preserving.** `python -m projects.fx27.runs.point.comparison` with zero flags runs exactly the old `python -m projects.fx27.runs.cspace.comparison` zero-flag behaviour (`--case` defaults to `"cspace"`) — same 7 rows, same output filenames, same table title. Nobody who only ever ran the plain cspace comparison needs to learn a new flag.
- **Output filenames are unchanged per case** (`fx27_cspace_comparison.csv`/`fx27_cspace_dc_dm_comparison.csv`/`fx27_euroc_comparison.csv` and their `_displacement.png`/`_kinematics.png` siblings) — no downstream script or human workflow that greps `output/` for these names breaks.
- **No case function calls another** — each is a self-contained lift of one old file's `main()` body, so the risk profile of the merge is "did the extraction introduce a typo", not "did combining the logic change behaviour".
- `_run_euroc` accepting (but ignoring) `--show` is a 1-line behavioural widening (the flag is now parseable where it previously errored with "unrecognized arguments"); this is a strict superset of old behaviour (old: error; new: silently accepted no-op) and is called out here rather than silently introduced.

## SS43.6 Decision required — case-selector mechanism

**Question:** how should `runs/point/comparison.py` let the caller pick which of the 3 absorbed cases to run?

**Purpose:** this is the one place in the whole restructuring where user-visible CLI behaviour changes (new flag or new required code edit), so it is not architect's call to make silently (per the task brief's explicit instruction).

| Option | Pros | Cons | Cost impact |
|---|---|---|---|
| **A. `--case {cspace,cspace_dc_dm,euroc}` CLI flag**, default `cspace` | Fully scriptable/CI-friendly; discoverable via `--help`; zero source edits needed to switch case; consistent with this project's existing house style (`point.py`'s own `--scenario` flag already does exactly this kind of "pick one of several named things" selection); default preserves old zero-flag cspace behaviour exactly | Adds one new flag name the user did not explicitly request (though did not rule out — see brief's "your call") | none (code-only) |
| **B. Comment-out block selection** — a module-level `ACTIVE_CASES = ("cspace",)` tuple the user edits/uncomments by hand; `main()` iterates whatever is active | Literal match to the user's own stated wording ("whichever campaign's case isn't currently wanted commented out") | Every case switch requires editing + saving the source file — not CI/one-off-friendly; silently running 2-3 cases if more than one line is left uncommented is an easy mistake (each case is a non-trivial compute: up to 24 flights + 2 plots); no `--help` discoverability | none (code-only) |
| **C. Hybrid** — keep a comment-out-style `ACTIVE_CASES` default (B's literal wording) but let `--case` on argv override it for one-off runs without touching the file | Satisfies the literal "comment out" mental model as the resting state, while still allowing a scripted/CI override | Two selection mechanisms in one file to document and keep in sync; more code than A or B alone for a 3-case script | none (code-only) |

**Recommendation: A.** The comparison script is run by hand far more often than it is edited, `--case` is the smallest and most consistent-with-house-style option, and the default value already reproduces the literal zero-edit "just run it" case the user cares most about (`cspace`). B/C are available if the user specifically wants the comment-out feel for occasional one-off case toggling — this is genuinely a one-line judgment call the user should make, not an objectively correct answer.

**This choice only affects `runs/point/comparison.py`'s internals (SS43.5's `main()`/`_CASES` shape) — it does not change SS43.3's file tree, SS43.4's disposition table, or any of the other 5 moved scripts**, so ticket FX27D-3 (SS43.9) can proceed with option A's shape below pending confirmation, and the diff to switch to B/C if the user prefers is contained to that one ticket.

## SS43.7 Import-path update list

Every line below is a `from projects.fx27.point.X import ...` (or `import projects.fx27.runs.cspace.point`) that must become the new path. No other import in the repo references `projects.fx27.point.*` or `projects.fx27.runs.{cspace,euroc}.*` (verified exhaustively via `Grep -n 'from projects\.fx27|import projects\.fx27'` across the whole repo, SS43.2).

**Inside `projects/fx27/` (the 5 pure-move run scripts + the 3 merge sources):**
- `runs/cspace/airbrake.py` → `runs/point/airbrake.py`: `from projects.fx27.point.airbrake import ...` → `from projects.fx27.solvers.point.airbrake import ...`
- `runs/cspace/ideal_drag.py` → `runs/point/ideal_drag.py`: `from projects.fx27.point.estimate import ...` → `from projects.fx27.solvers.point.estimate import ...`
- `runs/cspace/ideal_mass.py` → `runs/point/ideal_mass.py`: same `point.estimate` → `solvers.point.estimate` fix
- `runs/cspace/point.py` → `runs/point/point.py`: `from projects.fx27.point.flight import ...` and `from projects.fx27.point.plots import ...` and `from projects.fx27.point.validity import ...` → `solvers.point.*`
- `runs/euroc/sweep.py` → `runs/point/sweep.py`: no `projects.fx27.point.*` import at all (only `campaigns.euroc.*` + `apps.*`) — pure path move, zero import-line changes inside the file itself
- The 3 `comparison*.py` sources: all `from projects.fx27.point.{comparison,metrics,plots,validity} import ...` lines → `solvers.point.*`, folded into SS43.5's single merged file

**Inside `tests/`:**
- `tests/test_fx27_port.py`:
  - `from projects.fx27.point.airbrake import size_airbrake` → `from projects.fx27.solvers.point.airbrake import size_airbrake`
  - `from projects.fx27.point.comparison import evaluate_scenarios, run_many` → `solvers.point.comparison`
  - `from projects.fx27.point.estimate import estimate_airframe_mass, estimate_cx` → `solvers.point.estimate`
  - `from projects.fx27.point.metrics import row_from_flight` → `solvers.point.metrics`
  - `from projects.fx27.point.plots import (...)` → `solvers.point.plots`
  - `import projects.fx27.runs.cspace.point as point_cli` (2 occurrences, lines ~360/~374) → `import projects.fx27.runs.point.point as point_cli`
  - `from projects.fx27.campaigns.cspace.rockets_ideal import (...)` and the `campaigns.cspace.scenarios`/`campaigns.cspace.scenarios_dm`/`campaigns.euroc.motors`/`campaigns.euroc.scenarios` imports: **unchanged** (`campaigns/` is out of scope, SS43.1)
- `tests/test_regenerate_ideal_own.py`:
  - `from projects.fx27.point.comparison import run_many` → `solvers.point.comparison`
  - `from projects.fx27.point.flight import run as fly` → `solvers.point.flight`
  - `from projects.fx27.point.metrics import row_from_flight` → `solvers.point.metrics`
  - the `campaigns.cspace.*` imports in this file: **unchanged**

No other test file references `projects.fx27.point.*` or `projects.fx27.runs.{cspace,euroc}.*` (confirmed by the SS43.2 Grep's full result set — only these 2 test files matched).

## SS43.8 Acceptance criteria

1. **File tree matches SS43.3 exactly** — `projects/fx27/solvers/point/` contains the 7 moved library files + `__init__.py`; `projects/fx27/solvers/__init__.py` exists; `projects/fx27/runs/point/` contains exactly 6 files (`airbrake.py`, `comparison.py`, `ideal_drag.py`, `ideal_mass.py`, `point.py`, `sweep.py`) + `__init__.py`; `projects/fx27/runs/cspace/` and `projects/fx27/runs/euroc/` no longer exist at all (directories gone, not just emptied).
2. **`projects/fx27/campaigns/**` is byte-identical to its pre-restructuring state**, including `campaigns/cspace/rockets_ideal.py`'s AC-3 Section A (`git diff --stat projects/fx27/campaigns` shows no changes at all).
3. **Every moved/merged script is still runnable via `python -m`** from the repo root: `projects.fx27.runs.point.{airbrake,comparison,ideal_drag,ideal_mass,point,sweep}`, including all 3 `--case` values of `comparison.py` (pending SS43.6's resolution) and the pre-existing `--scenario`/`--validity`/`--show` flags on the scripts that had them before.
4. **Full test suite remains 899 passed, 0 failed** (same baseline as commit 1a3588d / Phase 2.26 Step 151) — same test count, only import paths updated in `tests/test_fx27_port.py` and `tests/test_regenerate_ideal_own.py` per SS43.7. **No new test file or new test function is added for this move** (D-181) — the move is verified by the existing suite continuing to pass with corrected imports, not by new coverage.
5. **No other file outside `projects/fx27/` and the 2 named test files changes.** In particular `apps/**`, `tests/test_layering.py`, and every other test file are untouched (SS43.1/SS43.2 confirm no other reference exists).
6. **Numeric pins are untouched** — this move changes zero lines of physics/numeric code (confirmed: the only "content change" anywhere is the comparison.py merge's `argparse` plumbing, SS43.5, and that is itself behaviour-preserving for the default case).

## SS43.9 Ticket list (FX27D-1..6)

All 6 tickets are **strictly sequential** (`parallel_safe: false` throughout) — the move touches a tightly interlinked import graph (every `runs/` file imports `point/`, both `runs/point/__init__.py`-creating tickets land in the same new directory) and this project's worktree mode is off for this stage, so there is no isolation benefit to attempting parallel execution here; sequencing also matches this project's "one step, one commit, full suite green at the end" convention (CLAUDE.md) — these 6 tickets are the breakdown for review granularity, intended to land as a single Phase 2.27 step/commit once all 6 are done, not as 6 separate commits each left in a broken intermediate state.

### [FX27D-1] Move `point/` library to `solvers/point/`
- **Module/boundaries:** `projects/fx27/point/**` → `projects/fx27/solvers/point/**` (git mv, all 8 files); new `projects/fx27/solvers/__init__.py`
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false

Move the whole `point/` package verbatim to `projects/fx27/solvers/point/` (directory rename, no internal import changes needed — see SS43.4, every internal reference is either relative (`.flight`, `.metrics`, stays valid) or absolute into `apps.*` (unaffected)). Create `projects/fx27/solvers/__init__.py` with a short docstring (SS43.3's suggested wording). Update each moved file's own top-of-docstring path self-reference line (e.g. `"""projects/fx27/point/flight.py -- ..."""` → `"""projects/fx27/solvers/point/flight.py -- ..."""`) — this is the only docstring content this ticket touches; do not rewrite the surrounding rationale prose. Do NOT yet update any importer outside this directory (`runs/`, `tests/`) — that is FX27D-2/3/5's job; this ticket's own tree will not be fully importable by the rest of the repo until later tickets land, which is expected for an intermediate ticket in a single-step sequence.

### [FX27D-2] Move the 5 single-campaign run scripts into `runs/point/`
- **Module/boundaries:** `projects/fx27/runs/cspace/{airbrake,ideal_drag,ideal_mass,point}.py` → `projects/fx27/runs/point/{airbrake,ideal_drag,ideal_mass,point}.py`; `projects/fx27/runs/euroc/sweep.py` → `projects/fx27/runs/point/sweep.py`; new `projects/fx27/runs/point/__init__.py`
- **Assignee:** developer
- **depends_on:** [FX27D-1]
- **parallel_safe:** false

Create `projects/fx27/runs/point/__init__.py` (short docstring, SS43.3). Move the 5 named files per SS43.4's table — each needs exactly its `projects.fx27.point.X` import lines rewritten to `projects.fx27.solvers.point.X` (SS43.7 spells out every line); `sweep.py` has no such import at all, so it is a pure `git mv` with zero content change. No other line in any of these 5 files changes — same `main()` body, same CLI flags, same output filenames (SS43.4). Leave `runs/cspace/` and `runs/euroc/` directories in place for now (still holding the 3 comparison-merge sources + their `__init__.py`s) — FX27D-4 deletes them once FX27D-3 has consumed the comparison sources.

### [FX27D-3] Build the merged `runs/point/comparison.py`
- **Module/boundaries:** new `projects/fx27/runs/point/comparison.py`, built from `projects/fx27/runs/cspace/comparison.py` + `projects/fx27/runs/cspace/comparison_dc_dm.py` + `projects/fx27/runs/euroc/comparison.py` (read-only sources for this ticket, not deleted yet)
- **Assignee:** developer
- **depends_on:** [FX27D-1, FX27D-2]
- **parallel_safe:** false

Implement SS43.5's design using the case-selector mechanism the orchestrator confirms from SS43.6's decision table (this ticket's shape above assumes option A, `--case` flag with `default="cspace"` — adjust to B/C only if the user picks one of those instead; the rest of this ticket is unaffected either way). Each of the 3 case functions (`_run_cspace`, `_run_cspace_dc_dm`, `_run_euroc`) must be line-for-line equivalent to its source file's old `main()` body, with only (a) `projects.fx27.point.*` imports rewritten to `projects.fx27.solvers.point.*`, (b) the function renamed and taking `args: argparse.Namespace` instead of parsing its own argv, (c) `SCENARIOS`/`SCENARIOS_DM` import aliases disambiguated (`_CSPACE_SCENARIOS` etc., SS43.5) since all 3 campaigns' scenario dicts now live in one module's namespace. Output filenames, table titles, and printed warning text must be byte-identical to today's (SS43.4/SS43.5). Verify the default zero-flag invocation (`python -m projects.fx27.runs.point.comparison`) produces the same 7-row table and same 2 PNG + 1 CSV filenames as today's `python -m projects.fx27.runs.cspace.comparison`.

### [FX27D-4] Delete the old `runs/cspace/` and `runs/euroc/` directories
- **Module/boundaries:** delete `projects/fx27/runs/cspace/**` and `projects/fx27/runs/euroc/**` entirely; edit `projects/fx27/runs/__init__.py` docstring
- **Assignee:** developer
- **depends_on:** [FX27D-2, FX27D-3]
- **parallel_safe:** false

`git rm -r` both directories (all files, including their `__init__.py`s) now that FX27D-2 and FX27D-3 have consumed every file under them. Update `projects/fx27/runs/__init__.py`'s docstring to describe the new "one file per analysis type under `runs/point/`" shape instead of the old "one folder per competition" shape (SS43.3).

### [FX27D-5] Update test import paths
- **Module/boundaries:** `tests/test_fx27_port.py`, `tests/test_regenerate_ideal_own.py` (import lines only, per SS43.7's exact list)
- **Assignee:** developer
- **depends_on:** [FX27D-1, FX27D-2, FX27D-3, FX27D-4]
- **parallel_safe:** false

Apply exactly the line-level changes listed in SS43.7 — every `projects.fx27.point.*` import becomes `projects.fx27.solvers.point.*`, and the 2 `import projects.fx27.runs.cspace.point as point_cli` occurrences become `import projects.fx27.runs.point.point as point_cli`. **Do not add any new test, new assertion, or new fixture for this move** (D-181 test policy) — this ticket is a pure find-and-replace on import statements; the test bodies (assertions, monkeypatch targets, fixture usage) stay exactly as they are today. `projects.fx27.campaigns.*` imports in both files are untouched (out of scope, SS43.1).

### [FX27D-6] Full-suite verification and manual smoke run
- **Module/boundaries:** none (verification only, no file changes expected)
- **Assignee:** developer
- **depends_on:** [FX27D-1, FX27D-2, FX27D-3, FX27D-4, FX27D-5]
- **parallel_safe:** false

Run the full suite in the background per this project's own test-running convention (CLAUDE.md: `run_in_background`, chunked if needed) and confirm **899 passed, 0 failed** — same count as the pre-restructuring baseline (commit 1a3588d). Manually smoke-run each of the 6 scripts under `runs/point/` via `python -m projects.fx27.runs.point.<name>` (including all 3 `--case` values of `comparison.py`) from the repo root to confirm `-m`-runnability survived the move (there is no automated guard for this — `tests/test_layering.py`'s G2 importability guard does not scan `projects/fx27/`, SS43.1 — so this step is the only check). Confirm via `git status`/`git diff --stat` that `projects/fx27/campaigns/**` shows zero changes and that `projects/fx27/runs/{cspace,euroc}/` no longer exist in the working tree.

## SS43.10 Rejected options

- **Keeping `cspace/`/`euroc/` subfolders inside `runs/point/`** (e.g. `runs/point/cspace/comparison.py` alongside a thin `runs/point/euroc/comparison.py`) — rejected because it reproduces exactly the per-competition split the user asked to remove; the whole point of the request is one file per analysis type, not per competition, so nesting competition folders back in under the new name would satisfy the rename literally while missing the actual ask.
- **Splitting `comparison.py` into 3 separate case-specific functions in 3 separate files but re-exported from one `__init__.py`-level `main()`** — rejected as unnecessary indirection: the brief explicitly asks for "all analysis cases... kept in one file", and 3 files behind one dispatcher is not one file in any meaningful sense a future reader would recognise.
- **Making `--case` required with no default** — rejected because it breaks the single most common invocation (`python -m projects.fx27.runs.point.comparison` with no flags, today's cspace default) for no benefit; a sensible default costs nothing and preserves backward-compatible muscle memory.
- **Moving `campaigns/` under `solvers/` or `runs/` too, "while we're at it"** — explicitly out of scope per the orchestrator's brief (SS43.1); `campaigns/` holds plain-data config literals under this project's established "config modules are plain data" convention (CLAUDE.md) and is a separate architectural concern from the solver/run-script split this ticket addresses. Not touched, not even its import path (it does not move).


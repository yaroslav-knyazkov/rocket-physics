# Architecture — `apps/` becomes the product root: the engine moves to `apps/sim/`, `configs/` retires, `data/` splits

> **Supersedes** `dev/docs/pivot-apps-restructure-analysis.md` (F1-F17). That document stays in the tree
> as a **facts reference** — its SS1 inventory, SS1.3 coupling facts, SS7 file-by-file breakdown and SS9
> measurements are still valid and are re-used here. Its *premises* (an installable package with an
> external consumer, `sim/` staying top-level, `configs/` kept as a public API surface) are **obsolete**:
> the user has since made larger decisions. Where this document and that one disagree, **this one wins**.

## Кратко (RU)

- Документ — проект реструктуризации репозитория: `sim/` переезжает в `apps/sim/engine/`, `configs/`
  как формальный пакет/API исчезает (датаклассы и `assemble()` переезжают в `apps/sim/schema.py`),
  `apps/` раскладывается по таксономии пользователя (input / sim / analysis / optimization / control),
  `data/` расщепляется на гитигнорный `/data` (реальные данные пользователя) и `/examples/data`
  (синтетика, демо, тестовые фикстуры), корневой `docs/` удаляется.
- **Рекомендация по упаковке: отказаться от `pip install -e .`** — внешнего потребителя больше нет,
  установка теперь только мешает (список `packages` пришлось бы переписывать на каждом шаге переезда).
  `pyproject.toml` остаётся как дом для конфигурации инструментов, зависимости — `requirements.txt`.
- **Самая опасная находка:** пять путей, вычисляемых от `__file__` (`sim/datafiles.py:45`,
  `sim/report.py:32`, `apps/common/artifacts.py:21`, `apps/cfd_conditions/select_conditions.py:94`,
  `tools/fetch_sounding.py:351`), после переезда начнут указывать **не туда и молча** — без исключения,
  без падения теста. Поэтому их чинят **первым шагом, до любого `git mv`**.
- **Проверенный факт против посылки задания:** папок `data/motors/cspace/` и `data/motors/euroc-sweep/`
  в этом репозитории **нет** (14 отслеживаемых файлов в `data/` — все до одного демо/синтетика/фикстуры).
  Значит «разделение» на практике = *всё* содержимое `data/` уезжает в `/examples/data/`, а `/data`
  создаётся заново пустым и гитигнорным, с одним отслеживаемым `README.md`.
- Масштаб: 336 строк импорта `sim.*` в 82 файлах, 22 строки импорта `configs.*`, 49 тестовых файлов.
  Разбито на 10 шагов (Step 126 … Step 135), каждый — один коммит + полный прогон тестов.
- Открытых развилок для пользователя — 5 (SS6): механизм упаковки, глубина `apps/sim/engine/`, дом
  `schema.py`, судьба `tools/fetch_sounding.py`, нужно ли продвигать тело `run.py` в приложение сейчас.
- Предлагаемый id стадии — **Phase 2.19**, slug `apps-root-restructure`.

---

## Table of contents

- [SS0. Scope and settled ground](#ss0)
- [SS1. Verified facts — this session](#ss1)
- [SS2. Target tree](#ss2)
- [SS3. Per-file disposition](#ss3)
- [SS4. Layering rules, import surface, guard tests](#ss4)
- [SS5. Ordered step sequence (Step 126 … Step 135)](#ss5)
- [SS6. Open forks — `decision_required`](#ss6)
- [SS7. Implications for `CLAUDE.md` «Профиль проекта»](#ss7)
- [SS8. Proposed stage id and slug](#ss8)
- [SS9. Rejected options](#ss9)

---

<a id="ss0"></a>
## SS0. Scope and settled ground

### SS0.1 Settled by the user before this document — not reopened here

| # | Decision | Consequence this document must honour |
|---|---|---|
| 1 | **No installable package, no external consumer.** `fx27/simulation` stops existing as a separate consumer; all real work lives in this repo. | The whole CORE/REFERENCE boundary idea from Phase 2.18 is dead. The `pip install -e .` mechanism is now optional — see **FK1**. |
| 2 | **`sim/` physically relocates under `apps/`.** | 336 import lines in 82 files; the single largest mechanical change in the project's history. "It breaks fx27's import" is no longer a cost. |
| 3 | **`configs/` retires as a formal package / API surface.** The dataclasses and `assemble()` survive, relocated. | `configs/__init__.py` (the 28-line re-export shim) is **deleted**, not moved. `configs/schema.py` relocates — see **FK3**. |
| 4 | **`apps/<type>/<name>/` taxonomy**, user's categories input / simulation / optimization / control, with the previously-proposed `analysis/` kept. | See SS2; the `sim` vs `simulation` name collision is resolved by making `apps/sim/` itself the simulation slot. |
| 5 | **`data/` splits**: user's real candidates stay in a gitignored top-level `/data`; synthetic / demo / test fixtures move to `/examples`. | SS3.1 — the full 14-file sort. |
| 6 | **Root `docs/` deleted outright** (untracked LaTeX build output). `dev/docs/latex/` is untouched, read-only. | Step 128. |
| 7 | **`dev/` stays exactly where it is.** | Nothing in this document moves a tracker file. |
| 8 | **Migration is in-place** (`git mv` + import fixes), one step = one commit + full suite. | SS5. |

### SS0.2 Standing project invariants this restructure must not break

1. **Numeric pins are bit-for-bit.** Nothing in this phase may change a computed number. Every step that
   could is given a bridge/equality net in SS5.
2. **The engine is offline and deterministic.** Restated in its new location (SS4.2) and, for the first
   time, enforced by a test rather than a docstring.
3. **One-way decoupling.** Controller code may import the engine; the engine never imports controllers,
   apps or examples. Survives the move verbatim (SS4.1).
4. **`dev/docs/latex/` is read-only.** Its prose cites `configs/` and `data/` paths; those citations
   **will drift** after this phase. That is accepted, flagged to the user, and not fixed here.

### SS0.3 Stack — unchanged, stated for completeness

Python 3.12, `numpy==2.5.4`, `scipy>=1.18,<2`, `matplotlib>=3.11,<4`, `pytest>=8`. **No technology
choice is being made in this phase** — it is pure structure. Verified exhaustively in the superseded
document's SS1.4 and unchanged since: the apps layer introduces no third-party dependency beyond those
three.

---

<a id="ss1"></a>
## SS1. Verified facts — this session

Measured, not recalled. The implementing developer should not re-derive these.

### SS1.1 Blast radius

| Quantity | Value | How measured |
|---|---|---|
| Files importing `sim.*` (excl. `dev/archive`) | **82** — 23 inside `sim/` itself, 45 in `tests/`, 8 in `apps/`, 2 in `configs/`, 1 each in `controllers/`, `examples/`, `run.py`, `tools/` | `git grep -l -E "(from\|import) sim\b" -- '*.py' ':!dev/archive'` |
| **Import lines** mentioning `sim` | **336** | `git grep -c` over the same set, summed |
| Files importing `configs.*` (excl. `dev/archive`, excl. `configs/` itself) | **22** (7 in `apps/`, 14 in `tests/`, 1 in `examples/`) | same method |
| Import lines mentioning `configs` | **22** | — |
| Files referencing `worked_scenario` / `DEMO_SCENARIO` | **20** | `git grep -ln worked_scenario` |
| `tests/` tracked files | **49** | `git ls-files tests` |
| `data/` tracked files | **14** (not 13 — the superseded doc undercounted; the two `README.md` were omitted) | `git ls-files data` |
| `sim/` modules | **30** `.py` files (26 substantive + `__init__.py` + the 3D trio) | `ls sim/*.py` |

### SS1.2 The five silently-breaking `__file__` anchors — the highest-stakes finding

These are the only places where the restructure can produce a **wrong result with no exception**:
a path that still resolves, to the wrong directory.

| Location | Today's expression | Today's value | After the move, unfixed |
|---|---|---|---|
| `sim/datafiles.py:45` | `dirname(dirname(__file__)) + "/data"` | `<repo>/data` | `apps/sim/data` — **does not exist**; every bare-name lookup fails (loud, but only at run time, and after `/data` is gitignored it may *exist and be wrong*) |
| `sim/report.py:32` | `Path(__file__).parent.parent / "output"` | `<repo>/output` | `<repo>/apps/sim/output` — **silently writes artifacts into the source tree** |
| `apps/common/artifacts.py:21` | `Path(__file__).parents[2] / "output"` | `<repo>/output` | depends on new depth; at `apps/_shared/artifacts.py` it is still `<repo>/output` by accident — **the worst kind of pass** |
| `apps/cfd_conditions/select_conditions.py:94` | `Path(__file__).parent.parent.parent / "output"` | `<repo>/output` | at `apps/analysis/cfd_conditions/` → `<repo>/apps/output` — **silently wrong** |
| `tools/fetch_sounding.py:351` | `dirname(dirname(abspath(__file__)))` | `<repo>` | at `apps/input/sounding_fetch/` → `<repo>/apps` — **silently wrong** |

**Therefore the first production step of this phase removes this entire class before any file moves**
(Step 127). `apps/common/artifacts.py` is the instructive one: it would keep working after the move by
coincidence of depth, which is exactly how this bug survives review.

### SS1.3 The `data/` premise correction

The task brief states that `data/` mixes the user's real candidate motor curves (`data/motors/cspace/`,
`data/motors/euroc-sweep/`) with fixtures. **Those two directories do not exist in this repository.**
`git ls-files data` returns 14 files, and `git status --porcelain data` returns nothing (no untracked
content either). Every one of the 14 is a demo / synthetic / fixture file (full sort in SS3.1).

Consequence: the "split" is not a 50/50 sort. It is **14 of 14 → `/examples/data/`**, plus the creation
of a fresh, empty, gitignored `/data` as the *destination* for the user's real candidates when they
arrive. This is a better outcome than the brief assumed — there is no risk of mis-sorting live data —
but the orchestrator should confirm with the user that the real candidate curves are expected to be
*copied in* rather than *already here*.

### SS1.4 Other facts measured this session

| Fact | Evidence |
|---|---|
| `sim/` imports **nothing** from `configs`, `apps`, `examples`, `controllers` | `git grep -n -E "(from\|import) (configs\|apps\|examples\|controllers)\b" -- 'sim/*.py'` → empty |
| `sim/__init__.py` is a **bare docstring** (73 B) — no eager re-exports | `cat sim/__init__.py` |
| `configs/__init__.py` re-exports 10 schema names **plus 10 `sim.params` groups** (`Aero, Atmosphere, Control, Lengths, Recovery, Site, Solver, Soundings, Thrust, Wind`) | `cat configs/__init__.py` |
| `configs/schema.py` depends on `sim.*` (`assemble()` → `_weight_from_pieces` → `motor_file.load`); **`sim` does not depend on `schema`** → the layering `schema → engine` is strict and one-way | import graph |
| `pyproject.toml` is **16 lines**; `packages = ["sim", "configs"]` | `cat pyproject.toml` |
| `tests/test_configs.py:209-214` reads **three source files by path**: `run.py`, `apps/cfd_conditions/select_conditions.py`, `apps/motor_selection/compare_motors.py` | `git grep -n _PROJECT_ROOT -- tests/` |
| `tests/test_worked_scenario_example.py:21-27` runs `python -m examples.worked_scenario` in a subprocess with `cwd=<repo>` | same |
| **Every module's docstring line 1 names its own path** (`"""apps/common/artifacts.py -- …"""`). ~45 moved files therefore each need a 1-line docstring edit — cheap, but easy to forget, and it is the project's own navigation convention | `git grep -n -E '"""(sim\|apps\|configs\|examples)/'` |
| `data/motors/README.md` is **already stale**: it cites `configs/motors/cti_k570.py`, `configs/rockets/demo.py`, `configs/scenarios/_TEMPLATE_scenario.py`, `tests/test_config_registries.py` — all archived/removed in Phase 2.18 | `cat data/motors/README.md` |
| Stale `__pycache__` compiled by **CPython 3.14** still present under `apps/` (`solve_cda`, `targets`, `artifacts`, `flight_stats`, `study_vehicle`, and a `cli.cpython-31{2,4}.pyc` for a **module that no longer exists**) | `ls -R apps` |
| `examples/` contains exactly one source file (`worked_scenario.py`, 13.4 K) + a stale `.pyc` | `ls examples` |
| Highest step number in the tracker: **Step 125** (Phase 2.18). Highest decision: **D-142**. | `status_query.py search "Step 125"`, `decisions` |

---

<a id="ss2"></a>
## SS2. Target tree

### SS2.1 The organising idea, in one paragraph

`apps/` stops meaning "the study scripts" and starts meaning **the product's code root**. Everything
the user builds rockets with lives under it, classified by *what you do with the model*. The physics
engine is not an app, so it does not get a type bucket of its own — it lives inside the **simulation**
slot, fenced in its own `engine/` directory, because "simulating" is exactly the activity it serves.
That resolves the `sim` / `simulation` name collision that would otherwise follow from the user's own
category list: there is one slot, it is called `apps/sim/`, and the engine is its deepest component.

Outside `apps/` only four kinds of thing remain at the top level: **inputs the user owns** (`data/`,
gitignored), **the worked example and its fixture corpus** (`examples/`), **the test suite** (`tests/`),
and **the process files** (`dev/`, `run*.py`, `CLAUDE.md`, `requirements.txt`, `.gitignore`).

### SS2.2 The tree

```
rocket-physics/
├── apps/                          # THE PRODUCT ROOT — everything that is rocket-physics as a tool
│   ├── __init__.py
│   ├── sim/                       # [simulation] the model: what it is, how it is integrated
│   │   ├── __init__.py            #   bare docstring only — no re-exports (SS4.3)
│   │   ├── schema.py              #   <- configs/schema.py   Rocket/Motor/LaunchSite/Weather/
│   │   │                          #      Scenario/Airframe/Sections/Variant/Config + assemble()
│   │   └── engine/                #   <- sim/   THE PINNED CORE. 30 modules, bit-for-bit.
│   │       ├── __init__.py
│   │       ├── integrate.py  dynamics.py  dynamics3d.py  forces.py  forces3d.py
│   │       ├── aero.py  atmosphere.py  wind.py  soundings.py  gravity.py  flow.py
│   │       ├── mass.py  inertia.py  motor_file.py  thrust_curve.py  roll.py
│   │       ├── state.py  state3d.py  quaternion.py  rotation.py  frames.py  sampling.py
│   │       ├── params.py  control.py  sensors.py  datafiles.py  mach_warning.py
│   │       └── report.py  plotting.py
│   ├── input/                     # [input] describe the design / acquire external data
│   │   ├── __init__.py
│   │   ├── demo_scenario.py       #   <- examples/worked_scenario.py's literal (DEMO_SCENARIO,
│   │   │                          #      rocket, motor, site, weather) with REQ|OPT comments intact
│   │   ├── study_vehicle.py       #   <- apps/common/study_vehicle.py
│   │   └── sounding_fetch/        #   <- tools/fetch_sounding.py   (FK4 — the only networked code)
│   │       ├── __init__.py
│   │       └── fetch_sounding.py
│   ├── analysis/                  # [analysis] characterize behaviour; no objective is optimised
│   │   ├── __init__.py
│   │   ├── cfd_conditions/        #   <- apps/cfd_conditions/
│   │   ├── weight_aero_tradeoff/  #   <- apps/weight_aero_tradeoff/
│   │   └── ensemble/              #   <- apps/common/ensemble.py  (Monte-Carlo driver)
│   ├── optimization/              # [optimization] search a design space against a target
│   │   ├── __init__.py
│   │   ├── motor_selection/       #   <- apps/motor_selection/   (discrete search)
│   │   └── airbrake_sizing/       #   <- apps/airbrake_sizing/   (brentq, continuous)
│   ├── control/                   # [control] flight software designed inside the simulation
│   │   ├── __init__.py
│   │   └── flight_software/       #   <- controllers/  (laws.py, estimator.py, __init__.py)
│   └── _shared/                   # apps-layer infrastructure — NOT an app type (leading underscore)
│       ├── __init__.py
│       ├── artifacts.py           #   <- apps/common/artifacts.py  (cwd-anchored after Step 127)
│       └── flight_stats.py        #   <- apps/common/flight_stats.py
│
├── data/                          # THE USER'S OWN DATA — gitignored, never shipped, never committed
│   └── README.md                  #   the one tracked file (`!/data/README.md`): what goes here,
│                                  #   how to point a Scenario at it (explicit relative path)
│
├── examples/                      # the worked example + the demo/fixture corpus
│   ├── worked_scenario.py         #   thin annotated runner: imports apps.input.demo_scenario,
│   │                              #   assembles, runs, prints; "copy demo_scenario.py to start"
│   └── data/                      #   <- data/   all 14 files (SS3.1). The bundled-name root.
│       ├── motors/                #     Cesaroni_2060K570-17A.eng, placeholder.csv,
│       │                          #     synthetic_{small,medium_punchy,medium_long,large}.csv, README.md
│       ├── aero/                  #     example.csv, example_v2.csv
│       └── soundings/             #     example/, example_live/, field_example/, README.md
│
├── tests/                         # unchanged location; 49 files + the new guards (SS4.4)
│   ├── __init__.py                #   mandatory (the `eventkit` top-level-`tests` collision)
│   ├── datadir.py                 #   NEW: the single source of the fixture-tree paths (SS5 Step 129)
│   ├── test_layering.py           #   NEW: the guard suite (SS4.4)
│   └── test_*.py
│
├── dev/                           # tracker + docs — untouched by this phase
├── output/                        # gitignored; written cwd-relative after Step 127
├── run.py  run_motor_sweep.py  run_airbrake.py  run_cfd_conditions.py  run_trade.py
├── pyproject.toml                 # demoted to tool config only (FK1); no packaging tables
├── requirements.txt               # the dependency list
├── CLAUDE.md  .gitignore
└── (deleted: docs/, configs/, sim/, controllers/, tools/, apps/common/)
```

### SS2.3 What each top-level directory is, in one line each

| Dir | Meaning after the restructure | Tracked? |
|---|---|---|
| `apps/` | the product: the engine, the input vocabulary, and every tool that answers an engineering question | yes |
| `data/` | **the user's own rocket/motor/sounding data** — personal, gitignored, referenced by explicit path | only `data/README.md` |
| `examples/` | one runnable worked example + the demo/synthetic/fixture corpus the tests and demos resolve by bare name | yes |
| `tests/` | the suite, including every numeric pin and the new structural guards | yes |
| `dev/` | tracker, docs, LaTeX source, archives — orchestrator-owned | yes |
| `output/` | generated artifacts; created under the **cwd**, so running from the repo root keeps today's behaviour | no |
| `run*.py` | the five documented front doors; thin forwarders, bodies unchanged | yes |

### SS2.4 Why `apps/sim/engine/` and not `apps/sim/` flat

Three reasons, in order of weight:

1. **The bucket must stay able to hold apps.** `apps/sim/` is the *simulation slot* of the user's own
   taxonomy. If the 30 engine modules sit directly in it, the first simulation app (vision's "give me a
   summary of my rocket", a run manager, a replayer) has nowhere unambiguous to go — it would be a
   subdirectory among 30 loose physics modules.
2. **The pinned core becomes a named, fenced thing.** "Did a numeric pin move?" is answerable by
   diffing one directory, and the layering guard becomes a single crisp sentence: *nothing under
   `apps/sim/engine/` imports anything outside `apps.sim.engine`* (SS4.1). With a flat layout the rule
   has to carve out exceptions as soon as sibling app directories appear.
3. **The mechanical cost is identical.** Both layouts are one `git mv` and the same 336 rewritten import
   lines; `engine` costs seven characters per line and buys the two properties above.

Cost acknowledged: `from apps.sim.engine.integrate import run_sim` is a four-component path. This is
offered as **FK2** because it is the user's ergonomics, not mine, and the blast radius makes it
expensive to change later.

---

<a id="ss3"></a>
## SS3. Per-file disposition

### SS3.1 `data/` — the sort, all 14 tracked files

Classification rule applied: **is this file read by code or tests of this repository (→ fixture corpus,
`/examples/data/`), or is it a candidate the user is evaluating for a real vehicle (→ `/data/`)?**
Provenance ("it is genuine vendor data") is *not* the criterion — role is. Two files are genuinely real
data by provenance and still land in `examples/` because their role here is to be the thing that
exercises a reader; they are called out explicitly below.

| # | File | Size | What it is | Who reads it | **Destination** |
|---|---|---|---|---|---|
| 1 | `data/aero/example.csv` | 1.4 K | synthetic v1 aero table (rectangular grid fixture) | `sim/aero.py` tests, demo scenario | `examples/data/aero/example.csv` |
| 2 | `data/aero/example_v2.csv` | 1.4 K | synthetic v2-schema aero table | `tests/test_aero_v2.py` | `examples/data/aero/example_v2.csv` |
| 3 | `data/motors/Cesaroni_2060K570-17A.eng` | 257 B | **real vendor RASP data** (Cesaroni K570) — but the *only* file exercising the RASP reader, header-derived masses and the `"endpoints"` mass model; pinned by `test_motor_file.py`, `test_motor_pieces.py` and `DEMO_SCENARIO` | engine + 3 test files + the demo scenario | `examples/data/motors/…` — **fixture by role** |
| 4 | `data/motors/placeholder.csv` | 223 B | the default demo motor (162.75 N·s); pins `_demo_baseline()` across many tests | `study_vehicle.py`, `compare_motors.py`, `targets.py`, many tests | `examples/data/motors/placeholder.csv` |
| 5 | `data/motors/synthetic_small.csv` | 470 B | E-class member of the 4-motor comparison set | `motor_selection`, `test_motor_selection.py`, `test_thrust_curve.py` | `examples/data/motors/…` |
| 6 | `data/motors/synthetic_medium_punchy.csv` | 704 B | H, 169.2 N·s, short high-thrust — **equal-impulse pair partner of #7** | same | `examples/data/motors/…` |
| 7 | `data/motors/synthetic_medium_long.csv` | 747 B | H, 169.5 N·s, long low-thrust — pair partner of #6 | same | `examples/data/motors/…` |
| 8 | `data/motors/synthetic_large.csv` | 394 B | I-class member of the set | same | `examples/data/motors/…` |
| 9 | `data/motors/README.md` | 2.7 K | describes the four-motor set and the file-format rules | humans | `examples/data/motors/README.md` — **and must be rewritten**: it cites `configs/motors/cti_k570.py`, `configs/rockets/demo.py`, `configs/scenarios/_TEMPLATE_scenario.py`, `tests/test_config_registries.py`, none of which exist since Phase 2.18 |
| 10 | `data/soundings/example/LKPR_202605011200.csv` | 778 B | single-station tier-2 sounding case; pinned by `test_integrate.py`, `test_plotting.py`, used by `run.py` | engine + 4 test files | `examples/data/soundings/example/…` |
| 11 | `data/soundings/field_example/FLDA_202601011200.csv` | 931 B | synthetic station A of a 2-station field ~37 km apart; exercises tier-3 IDW/RBF | `test_atmosphere.py` | `examples/data/soundings/field_example/…` |
| 12 | `data/soundings/field_example/FLDB_202601011200.csv` | 1.1 K | synthetic station B — **moves as a pair with #11** | same | `examples/data/soundings/field_example/…` |
| 13 | `data/soundings/example_live/72672_202401151200.csv` | 4.6 K | **real fetched radiosonde** (station 72672, 2024-01-15 12 Z) — genuine `fetch_sounding.py` output, kept as the sample of real-world format. No test loads it by name | documented sample output of the fetcher | `examples/data/soundings/example_live/…` — **sample of real output, not a candidate** |
| 14 | `data/soundings/README.md` | 1.2 K | describes the three sounding categories; currently accurate | humans | `examples/data/soundings/README.md` — path wording only |

**Result: 14 of 14 → `examples/data/`. `/data` is then re-created empty.**

New `/data` contract (written in Step 129):

- `.gitignore` gains `/data/` **and** `!/data/README.md`, so a fresh clone has the directory and its
  purpose, and nothing inside it is ever committed.
- `data/README.md` (tracked, ~20 lines, Russian per the user-facing language rule) states: this is
  *your* data; drop candidate curves under `data/motors/<campaign>/`; reference them from a `Scenario`
  by **explicit relative path** (`motor_curve="data/motors/cspace/foo.eng"`), which `datafiles.resolve`
  rule 2 anchors on the cwd — *not* by bare name, because bare names resolve into the fixture corpus.
- That last sentence is the only user-visible semantic consequence of the split and it must be in the
  README, because the alternative (making `/data` a second bundled root) is explicitly rejected in SS9.

### SS3.2 `configs/` — two files, two different fates

| File | Fate | Detail |
|---|---|---|
| `configs/schema.py` (28.6 K) | **moves** → `apps/sim/schema.py` | Contents unchanged except the line-1 docstring path and its own `sim.*` imports → `apps.sim.engine.*`. Exports `Config`, `Variant`, `Airframe`, `Sections`, `Motor`, `Rocket`, `LaunchSite`, `Weather`, `Scenario`, `assemble()`, `_pad_state()`, `_weight_from_pieces()` — **the names and signatures do not change** (this is the pinned API shape agreed in Phase 2.18, D-141/D-142). |
| `configs/__init__.py` (28 lines) | **deleted** | It re-exported 10 schema names + 10 `sim.params` groups. Under decision 3 there is no API surface to keep stable. Each of the 22 call sites imports directly from the two real homes: `from apps.sim.schema import Motor, Rocket, …` and `from apps.sim.engine.params import Thrust, Aero, …`. Expect ~6 of the 22 sites to become *two* import lines instead of one. |

Everything under `dev/archive/configs-registry-2026-10/` is **left exactly as it is** — it is a frozen
archive, its `from configs…` lines are historical text, and `tests/` does not import it.

### SS3.3 `sim/` — 30 files, one functional change, 30 docstring lines

| Group | Files | Change |
|---|---|---|
| The 29 physics modules | `aero, atmosphere, control, dynamics, dynamics3d, flow, forces, forces3d, frames, gravity, inertia, integrate, mach_warning, mass, motor_file, params, plotting, quaternion, roll, rotation, sampling, sensors, soundings, state, state3d, thrust_curve, wind` + `report`, `datafiles` | `git mv` to `apps/sim/engine/`; internal `from sim.X import` → `from apps.sim.engine.X import`; **docstring line 1 path**. No logic edits. |
| `sim/datafiles.py:45` | `_BUNDLED` | **functional** — retargeted to `<repo>/examples/data` at Step 129, depth-corrected at Step 133, with a loud import-time existence check (SS5 Step 127). |
| `sim/report.py:32` | `DEFAULT_OUTPUT_DIR` | **functional** — cwd-anchored at Step 127 (before the move). |
| `sim/__init__.py` | bare docstring | becomes `apps/sim/engine/__init__.py`; stays a bare docstring. A new `apps/sim/__init__.py` and `apps/__init__.py` are created, also bare. |
| Docstring references to `controllers/` | `control.py:78,440,442`, `params.py:231`, `roll.py:13`, `sensors.py:2,16,18,74` | → `apps/control/flight_software/` (prose only) |
| Docstring references to `data/<kind>/` | `datafiles.py` (4), `aero.py:41,70,363,669`, `motor_file.py:248,252,257,297,301`, `soundings.py:19,204,209`, `thrust_curve.py:8`, `params.py:64,98,172` | → `examples/data/<kind>/` (prose only) |

### SS3.4 `apps/common/` — split by what each file actually is

Carried over unchanged from the superseded document's F10(c), which remains correct:

| File | Lines | Destination | Reason |
|---|---|---|---|
| `artifacts.py` | 30 | `apps/_shared/artifacts.py` | genuinely shared apps-layer infrastructure; also the file that gets the cwd-anchored `output_dir()` at Step 127 |
| `flight_stats.py` | 229 | `apps/_shared/flight_stats.py` | shared ascent-window reduction used by 3 apps. **Not** promoted into the engine: it is an apps-layer reduction over a `Result`, and the engine stays pinned and minimal |
| `ensemble.py` | 393 | `apps/analysis/ensemble/ensemble.py` (+ `__init__.py`) | it is a *driver*, not a helper — nothing but `tests/test_ensemble.py` imports it, and Monte-Carlo characterisation is analysis. Keep its `ProcessPoolExecutor` picklability docstring and re-verify it after the move (Windows `spawn` must be able to import the module defining the callable) |
| `study_vehicle.py` | 83 | `apps/input/study_vehicle.py` | an input literal of exactly the same kind as `motors.py` / `targets.py` / `scenarios.py` |

After the split `apps/common/` **is deleted**, not left empty.

### SS3.5 Everything else at the top level

| Item | Disposition | Note |
|---|---|---|
| `controllers/` (3 files) | → `apps/control/flight_software/` | Import direction unchanged (`apps → engine`, never the reverse). Registration into `sim.control` is a *runtime* side effect of import, so it is location-independent and cannot move a pin. The new docstring must restate the nuance: **control is the one app type whose code runs inside the integrator's loop** |
| `tools/fetch_sounding.py` | → `apps/input/sounding_fetch/fetch_sounding.py` (**FK4**) | The project's only networked code. Invariant restated as: *no module under `apps/sim/engine/` imports it, and no app imports it at module level* — and, for the first time, enforced by a test (SS4.4 G3). `tools/` is then deleted |
| `examples/worked_scenario.py` | stays, shrinks to a thin runner (~25 lines) | the literal (with every `REQ|OPT` comment verbatim) moves to `apps/input/demo_scenario.py`. `tests/test_worked_scenario_example.py` keeps invoking `python -m examples.worked_scenario`, which is exactly the thing still worth smoke-testing |
| `run.py` | stays at root; body unchanged, imports repointed | whether to promote its body into an app is **FK5** — recommendation: *not in this phase* |
| `run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py` | stay; one or two import lines each | `run_trade.py` has two (both modes) |
| `pyproject.toml` | packaging tables removed (**FK1**) | survives as the home for tool config |
| `requirements.txt` | unchanged, becomes the single dependency list | |
| `docs/` (untracked, ~1 MB) | **deleted**; `/docs/` added to `.gitignore` | pure LaTeX build output; no `.tex` inside; nothing references it |
| all `__pycache__/` | purged in the same pass | includes CPython-3.14 strays and a `cli.cpython-*.pyc` for a module that no longer exists |
| `dev/`, `temp/`, `temporary/`, `.claude/`, `output/` | untouched | `output/` changes only in *where it is created* (cwd-relative) |

---

<a id="ss4"></a>
## SS4. Layering rules, import surface, guard tests

### SS4.1 The layering, stated as a law

```
            apps/_shared/        apps/input/   apps/analysis/   apps/optimization/   apps/control/
                  │                    │              │                 │                 │
                  └────────────────────┴──────┬───────┴─────────────────┴─────────────────┘
                                              ▼
                                      apps/sim/schema.py          (the input vocabulary + assemble())
                                              │
                                              ▼
                                      apps/sim/engine/            (THE PINNED CORE)
                                              │
                                              ▼
                                   numpy / scipy / matplotlib / stdlib
```

Four rules, every one of them mechanically checkable:

| # | Rule | Why |
|---|---|---|
| **L1** | No module under `apps/sim/engine/` imports anything outside `apps.sim.engine` (except stdlib / numpy / scipy / matplotlib). | The core is pinned; anything it imports can move a pin. This is today's "`sim/` never imports `apps`/`examples`/`controllers`" rule, tightened and now enforceable in one expression. |
| **L2** | `apps/sim/schema.py` imports `apps.sim.engine.*` and nothing else from the product. | `schema` is the engine's front door, not a peer of the apps. Verified today: `schema.py → sim.*` only, `sim ↛ schema`. |
| **L3** | Apps import `apps.sim.*`, `apps._shared.*`, and `apps.input.*`; apps do **not** import each other across type buckets otherwise. | Keeps buckets independently movable. **Amended at Step 131** (verification step): `apps.input.*` (literal config data — `demo_scenario.py` since Step 130, `study_vehicle.py` since Step 131) is a legitimate third exception alongside `_shared`/`sim` — it holds data other buckets are meant to consume, the same role `_shared` plays for code. `apps.analysis.*`/`apps.optimization.*` import `apps.input.*` for exactly this reason; no bucket imports another analysis/optimization/control bucket directly. |
| **L4** | Nothing in `apps/` imports `examples.*` or `tests.*`. | The product must not depend on its own tutorial. This is the backwards dependency the superseded document found (4 modules) and Step 130 removes it. |

**Data direction note that must survive in prose**, because no test can express it: `apps/control/*`
is the one app type whose code is *called by* the integrator during a run. Import direction is still
`apps → engine`; execution direction is the reverse. Registration happens as a runtime side effect of
importing `apps.control.flight_software`, which is why the move cannot touch a numeric pin.

### SS4.2 Offline / determinism invariant, restated

> `apps/sim/engine/` performs no I/O other than reading data files through `datafiles.resolve()`, and
> opens no network connection. The project's only networked module is
> `apps/input/sounding_fetch/fetch_sounding.py`; it is run manually, never imported at module level by
> any app, and never imported by the engine.

### SS4.3 Import surface — deliberately flat, no facades

Phase 2.18 built `configs/__init__.py` as a convenience re-export. Decision 3 retires it and this
document does **not** re-create the pattern anywhere:

- `apps/__init__.py`, `apps/sim/__init__.py`, `apps/sim/engine/__init__.py` and every bucket
  `__init__.py` are **bare docstrings**. No re-exports.
- Reason beyond "no API surface to keep stable": an `__init__.py` that re-exports makes
  `import apps.sim.anything` pull in numpy, scipy, matplotlib and all 30 engine modules, and it creates
  two spellings for every name — which is how a 336-line mechanical rewrite acquires inconsistency.
- The canonical imports therefore read:
  ```python
  from apps.sim.schema import Rocket, Motor, LaunchSite, Weather, Scenario, assemble
  from apps.sim.engine.params import Thrust, Aero, Atmosphere, Wind, Soundings, Solver
  from apps.sim.engine.integrate import run_sim
  from apps._shared.flight_stats import ascent_stats
  ```
- `__init__.py` files are added everywhere nonetheless (they are currently absent from `apps/` and
  `examples/` entirely). With no install they are not strictly required — implicit namespace packages
  work — but they make every package a *regular* package, which (a) wins over a same-named directory
  earlier on `sys.path` instead of silently merging with it, and (b) makes the "every module is
  importable by dotted name" guard meaningful.

### SS4.4 The guard tests — `tests/test_layering.py`, written **before** anything moves

These are the safety net for the whole phase. Each must pass against **today's** tree when written
(Step 126), so that a later failure means "the move broke something", not "the test was aspirational".

| id | Guard | Implementation sketch |
|---|---|---|
| **G1** | L1/L4 import-direction: AST-walk every `.py` under the engine directory; assert no `import`/`from` targets `apps` (other than `apps.sim.engine`), `examples`, `tests`, `tools`, `controllers`. | `ast.parse` + `ast.walk`, directory given by a module-level constant so the move is a one-line test edit |
| **G2** | Every module is importable by dotted name: walk the whole `apps/` tree, `importlib.import_module` each module, assert no failure. **This is the guard that catches a module orphaned by a `git mv`** — the failure mode where a file moves but nothing imports it any more and it silently rots. | `pkgutil.walk_packages` after `__init__.py` files exist (Step 131); before that, a path walk |
| **G3** | Network isolation: assert no module outside `fetch_sounding.py` imports `urllib`, `http`, `socket`, `requests`. | same AST walk |
| **G4** | Output anchoring: with `monkeypatch.chdir(tmp_path)`, the artifact helper and `report.DEFAULT_OUTPUT_DIR` resolve under `tmp_path`, **not** under the repo. | the regression test for SS1.2 |
| **G5** | Fixture-root consistency: `datadir.MOTORS_DIR` and `datafiles.resolve("placeholder.csv", "motors")` agree, and the resolved path lies under `<repo>/examples/data`. | the single assertion that keeps the test-side and library-side notions of "the bundled tree" from drifting |
| **G6** | No leftovers: assert `sim/`, `configs/`, `controllers/`, `tools/`, `apps/common/`, `docs/` do **not** exist at the repo root. Added at the end of each step that deletes one — an empty leftover directory is how a half-move hides. | `os.path.isdir` assertions |

### SS4.5 Why no install is needed for any of this — measured

| Fact | Evidence |
|---|---|
| The project is **not** editable-installed in the project interpreter today | `importlib.metadata.distribution('rocket-physics')` → `PackageNotFoundError`; no `__editable__*` or `*.egg-info` in site-packages |
| `import sim` works anyway, because the repo root is `sys.path[0]` | `find_spec('sim').origin` → `<repo>\sim\__init__.py` |
| pytest puts the repo root on `sys.path` by itself: `tests/__init__.py` exists, so the `prepend` import mode walks up past the package and inserts the repo root | `python -m pytest tests/test_datafiles.py -q` → 16 passed, with nothing installed |
| `python run.py` and `python -m apps.<type>.<name>.<mod>` from the repo root both get the repo root as `sys.path[0]` | CPython script/`-m` semantics |

So the Phase 2.18 packaging machinery is already dormant in the working environment. Removing it costs
nothing and removes a list that would otherwise have to be rewritten at four separate steps of this
migration.

---

<a id="ss5"></a>
## SS5. Ordered step sequence (Step 126 … Step 135)

**Ordering principle.** Three rules decide the order:

1. **Guards before motion.** A structural guard written after the move only proves the move's own
   result; written before, it proves the move preserved something.
2. **Silent failures before loud ones.** The five `__file__` anchors (SS1.2) break *quietly*. Every
   other breakage in this phase is an `ImportError` or a `FileNotFoundError` — loud, and the suite
   catches it. So the anchors are neutralised first, while the tree is still the one everybody knows.
3. **Independent moves before coupled ones**, smallest blast radius first, with the 336-line engine
   move isolated into a step of its own so its diff is reviewable as *pure motion*.

**Every step ends with:** `python -m pytest -q` in the background (~220-390 s), confirmation that no
numeric pin moved, `git status` sanity (the project is in cloud sync; see `CLAUDE.md`), one commit
named `Step NN (Phase 2.19): …`.

Numbering continues from the tracker's highest, **Step 125** (Phase 2.18). Decision ids continue from
**D-142** → `D-143` onward.

---

### [Step 126] Structural guard suite — pure addition, no production change
- **Module/boundaries:** `tests/test_layering.py` (new, only file touched)
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true
- **Moves:** nothing.
- **Imports changed:** none.
- **Tests affected:** one new file.
- **Content:** guards G1 (engine import direction), G2 (every module importable by dotted name — walk
  `sim/`, `apps/`, `configs/`, `controllers/` as they are *today*), G3 (network isolation).
- **Safety net before commit:** the three guards must **pass on the current tree unmodified**. If G1 or
  G3 fails today, that is a real finding and the step stops for a decision rather than relaxing the
  guard. Full suite.

### [Step 127] De-anchor every `__file__`-derived output path (SS1.2)
- **Module/boundaries:** `sim/report.py`, `sim/datafiles.py`, `apps/common/artifacts.py`,
  `apps/cfd_conditions/select_conditions.py`, `tools/fetch_sounding.py`, `tests/test_layering.py`,
  `tests/test_airbrake_sizing.py`, `tests/test_weight_aero_tradeoff.py`, `tests/test_report.py`
- **Assignee:** developer
- **depends_on:** [Step 126]
- **parallel_safe:** false
- **Moves:** nothing.
- **Changes:**
  - `apps/common/artifacts.py`: the module-level `OUTPUT_DIR` constant becomes a function
    `output_dir() -> Path` returning `Path.cwd() / "output"`, **evaluated at call time** (a constant
    would freeze the importing process's cwd). Keep a deprecated module-level alias only if a call site
    genuinely cannot be converted — preferably none.
  - `sim/report.py:32`: `DEFAULT_OUTPUT_DIR` → the same cwd rule. This keeps the engine free of any
    repo-root knowledge, which is a precondition for moving it.
  - `apps/cfd_conditions/select_conditions.py:94`: its hand-rolled `_OUTPUT_DIR` folds into the shared
    helper (the TODO its own docstring already carries).
  - `--out-dir` added to the apps that lack it (`scenario_sweep.py` already has one — copy its shape).
  - `tools/fetch_sounding.py:351`: stops computing a repo root; writes under the cwd + `--out-dir`.
  - `sim/datafiles.py:45`: `_BUNDLED` keeps pointing at `<repo>/data` for now, but gains an
    **import-time existence check** that raises a named, explanatory error. This converts the one
    remaining anchor from "silently wrong" to "loudly wrong" before it is moved twice (Steps 129, 133).
- **Imports changed:** 5 call sites of `OUTPUT_DIR`/`ensure_dir`.
- **Tests affected:** `test_airbrake_sizing.py`, `test_weight_aero_tradeoff.py` (the two that reference
  the output dir), `test_report.py`; plus new guard **G4**.
- **Safety net before commit:** G4 (`monkeypatch.chdir(tmp_path)` → artifacts land in `tmp_path`, and
  **nothing** appears under the repo). Grep for tests that write into the repo's `output/` — it is
  gitignored, so `git status` will not reveal them. Behaviour from the repo root must be byte-identical
  to today. Full suite.

### [Step 128] Retire the packaging mechanism + top-level cleanup (**gated on FK1**)
- **Module/boundaries:** `pyproject.toml`, `.gitignore`, `requirements.txt`, root `docs/`, every
  `__pycache__/`, `tests/test_layering.py`
- **Assignee:** developer
- **depends_on:** [Step 127]
- **parallel_safe:** false
- **Changes (under the recommended FK1 answer R2):**
  - `[build-system]`, `[project]` dependency tables and `[tool.setuptools]` removed from
    `pyproject.toml`; the file survives as the home for tool configuration. `requirements.txt` becomes
    the single dependency declaration.
  - `pip uninstall rocket-physics` **in every environment the user has one** — verified absent in the
    project interpreter (SS4.5), but the user may have installed it into an fx27 venv; delete any
    `*.egg-info/` and `__editable__*` leftovers.
  - Root `docs/` deleted; `/docs/` added to `.gitignore`.
  - All `__pycache__/` purged (removes the CPython-3.14 strays and the orphaned `cli.cpython-*.pyc`).
- **Tests affected:** none functionally; the old packaging-boundary expectations, if any, are dropped.
- **Safety net before commit:** full suite **with nothing installed**; `python run.py` and one
  `python -m apps.…` invocation from the repo root; confirm `importlib.metadata.distribution(
  'rocket-physics')` raises. Confirm root `docs/` contained no `.tex` before deleting (it does not).
- **Why here:** doing this *before* the moves means the `packages` list never has to be rewritten —
  otherwise it would be edited at Steps 129, 131, 132, 133 and 134.

### [Step 129] `data/` → `examples/data/`; create the gitignored user `/data`
- **Module/boundaries:** `data/**` → `examples/data/**`, `sim/datafiles.py`, `.gitignore`,
  new `data/README.md`, new `tests/datadir.py`, 13 test files, `tools/fetch_sounding.py`
- **Assignee:** developer
- **depends_on:** [Step 128]
- **parallel_safe:** false
- **Moves:** all 14 tracked files per SS3.1, as `git mv` (preserve history/blame).
- **Changes:**
  - `sim/datafiles.py:45` `_BUNDLED` → `<repo>/examples/data`. **One line.** The three resolver rules
    key off the *shape* of the given string, never off the bundled root, and every bundled-data string
    in the repo is a bare name (verified exhaustively in the superseded doc's SS9) — so the loaded
    bytes, the parsed records and every numeric pin are untouched.
  - New `tests/datadir.py` (~15 lines): `DATA`, `MOTORS_DIR`, `AERO_DIR`, `SOUNDINGS_DIR`. The 13 test
    files that hand-roll `os.path.join(dirname(__file__), "..", "data", …)` import it instead:
    `test_aero.py` (3 sites), `test_aero_fb.py`, `test_aero_v2.py`, `test_atmosphere.py`,
    `test_datafiles.py`, `test_motor_file.py`, `test_qa_phase217_m1.py`, `test_report.py`,
    `test_scenario_sweep.py`, `test_soundings.py`, `test_step114_review_fixes.py`,
    `test_thrust_curve.py`, `test_wind.py`.
  - `.gitignore`: `/data/` + `!/data/README.md`; new tracked `data/README.md` (Russian; the
    explicit-relative-path contract from SS3.1).
  - `examples/data/motors/README.md` rewritten (its `configs/…` citations are already dead).
- **Tests affected:** the 13 above + new guard **G5**.
- **Safety net before commit:** G5; assert the old root `data/` holds nothing but `README.md`; pin
  `datafiles.resolve("placeholder.csv", "motors")` to the new absolute path; full suite — the
  sounding/aero/motor pins are the ones that would reveal a mis-move.

### [Step 130] Demo scenario leaves `examples/` (removes the backwards dependency L4)
- **Module/boundaries:** `examples/worked_scenario.py` → `apps/input/demo_scenario.py` (+ a new thin
  `examples/worked_scenario.py`), `apps/cfd_conditions/select_conditions.py:89`,
  `apps/motor_selection/scenario_sweep.py:54`, `apps/airbrake_sizing/solve_cda.py:86`, `run.py:34`,
  ~14 test files
- **Assignee:** developer
- **depends_on:** [Step 129]
- **parallel_safe:** false
- **Moves:** the annotated literal, **with every `REQ|OPT` comment verbatim**, keeping the exported
  names `DEMO_SCENARIO`, `rocket`, `motor`, `site`, `weather` (three test files import the individual
  pieces, not only the scenario). The `__main__` block stays behind in the thin runner.
- **Imports changed:** `from examples.worked_scenario import …` → `from apps.input.demo_scenario import
  …` in 3 apps + `run.py` + ~14 tests (20 files mention it in total).
- **Tests affected:** the ~14 importers; `tests/test_worked_scenario_example.py` keeps running
  `python -m examples.worked_scenario` as a subprocess — pointed at the thin runner, which is precisely
  what still needs smoke-testing.
- **Safety net before commit:** a **temporary bridge test** in the Step-122 pattern — a recursive
  dataclass/NamedTuple field-walker asserting that `assemble(DEMO_SCENARIO)` from the new module is
  field-for-field equal to the old import path's, while both still resolve; **deleted at the end of the
  same step**. This is the one step in the phase that could silently move a pin, because ~10 pins are
  computed from these literals. Full suite.

### [Step 131] The `apps/` taxonomy move + `apps/common/` split
- **Module/boundaries:** all of `apps/**`, `run_motor_sweep.py`, `run_airbrake.py`,
  `run_cfd_conditions.py`, `run_trade.py`, `run.py`, ~12 test files, `tests/test_configs.py:209-214`
- **Assignee:** developer
- **depends_on:** [Step 130]
- **parallel_safe:** false
- **Moves:** exactly the SS2.2 layout for `input/`, `analysis/`, `optimization/`, `_shared/`; `__init__.py`
  added to `apps/` and every package under it; `apps/common/` deleted.
- **Imports changed:** all `apps.*` dotted paths; 8 app modules' internal imports; the 4-5 runners.
- **Tests affected:** `config_variants.py`, `test_airbrake_sizing.py`, `test_apps_common.py` (**rename**
  — it no longer tests a thing called `common`), `test_configs.py`, `test_demo_physics.py`,
  `test_ensemble.py`, `test_mach_warning.py`, `test_motor_selection.py`, `test_qa_phase217_m1.py`,
  `test_scenario_sweep.py`, `test_step114_review_fixes.py`, `test_weight_aero_tradeoff.py`.
  **`tests/test_configs.py:211,214` read two app source files by path** — those two literals move too,
  and they fail as `FileNotFoundError`, which reads like a real failure rather than an import error.
- **Safety net before commit:** guard **G2** is the point of this step — after the move, every module
  under `apps/` must still be importable by dotted name, so a file orphaned by a `git mv` fails loudly.
  Plus G6 (`apps/common/` is gone, not empty). Re-verify `apps/analysis/ensemble`'s
  `ProcessPoolExecutor` path on Windows `spawn` (the child must import the module defining the
  callable). Docstring line 1 of every moved file updated. Full suite.

### [Step 132] `controllers/` → `apps/control/flight_software/`; `tools/` → `apps/input/sounding_fetch/` (**gated on FK4**)
- **Module/boundaries:** `controllers/**`, `tools/fetch_sounding.py`, `sim/control.py`, `sim/params.py`,
  `sim/roll.py`, `sim/sensors.py` (docstrings only), `tests/test_controllers.py`, `tests/test_control.py`,
  `tests/test_sensors.py`, `tests/test_fetch_sounding.py`, `tests/test_layering.py`
- **Assignee:** developer
- **depends_on:** [Step 131]
- **parallel_safe:** false
- **Moves:** 3 controller files + 1 tool file. `controllers/` and `tools/` both deleted afterwards.
- **Imports changed:** internal `from controllers import X` → `from apps.control.flight_software import
  X`; the registration trigger becomes `import apps.control.flight_software`.
- **Tests affected:** `test_controllers.py` (imports + docstring), `test_control.py:473-474,675` (the
  "law name unresolvable until the package is imported" pin — its *behaviour* is unaffected, it asserts
  an unregistered name, not a module location), `test_sensors.py:118` (docstring),
  `test_fetch_sounding.py`.
- **Safety net before commit:** G1 (the engine still imports nothing from `apps`), G3 updated to the
  fetcher's new path, G6 (`controllers/`, `tools/` gone). The new docstring **must** restate both the
  import-direction rule and the data-direction nuance (SS4.1). Full suite — `test_control.py` is where
  a registration regression would show.

### [Step 133] **The engine move** — `sim/` → `apps/sim/engine/`
- **Module/boundaries:** all 30 files of `sim/`, plus every one of the 82 files that import it
- **Assignee:** developer
- **depends_on:** [Step 132]
- **parallel_safe:** false
- **Moves:** `git mv sim apps/sim/engine` (one rename, history preserved); new bare
  `apps/sim/__init__.py`.
- **Imports changed:** **336 lines across 82 files** — `from sim.X import` → `from apps.sim.engine.X
  import`, `import sim.X` → `import apps.sim.engine.X`. This is a scripted, mechanical rewrite; it must
  be applied by a script and then reviewed, not typed.
- **Also:** `_BUNDLED` depth corrected (`apps/sim/engine/datafiles.py` → `parents[3]`), the import-time
  existence check from Step 127 is what catches an off-by-one here. Docstring line 1 of all 30 files.
- **Tests affected:** 45 test files (every one that imports the engine).
- **Safety net before commit:** this step is the single highest-risk one and should get its own
  session.
  1. A **content-equality check**: for each moved module, diff `git show HEAD:sim/<m>.py` against the
     new file **ignoring lines that start with `from `/`import `** and the docstring's first line —
     the result must be empty. That turns "is this really pure motion?" into a mechanical answer
     instead of a 1.3 MB eyeball review.
  2. `git diff -M --stat` must show renames, not delete+add.
  3. G1/G2/G5/G6; `datafiles.resolve` path pin still points into `examples/data`.
  4. Full suite, twice if the known flaky Windows `scipy.integrate._ivp` access violation appears
     (`CLAUDE.md` documents it as not-a-failure).
  5. Explicit confirmation that **no numeric pin changed** — the whole phase's acceptance criterion.

### [Step 134] `configs/` retires — `schema.py` → `apps/sim/schema.py`, shim deleted
- **Module/boundaries:** `configs/**` (deleted), `apps/sim/schema.py` (new), 22 importing files
- **Assignee:** developer
- **depends_on:** [Step 133]
- **parallel_safe:** false
- **Moves:** `git mv configs/schema.py apps/sim/schema.py`; `configs/__init__.py` **deleted**;
  `configs/` removed.
- **Imports changed:** 22 lines → direct imports from the two real homes
  (`apps.sim.schema` for the dataclasses + `assemble()`, `apps.sim.engine.params` for the ten parameter
  groups the shim used to re-export). Expect ~6 sites to become two lines.
- **Tests affected:** 14 test files import `configs.*` (`config_variants.py`, `test_aero_fb.py`,
  `test_aero_oob.py`, `test_config_pieces.py`, `test_configs.py`, `test_demo_physics.py`,
  `test_ensemble.py`, `test_inertia.py`, `test_motor_pieces.py`, `test_qa_phase217_m1.py`,
  `test_scenario_sweep.py`, `test_step114_review_fixes.py`, `test_thrust_scatter.py`,
  `test_worked_scenario_example.py`) + 7 app modules + `examples/worked_scenario.py`.
  `tests/test_configs.py` **should be renamed** (it no longer tests a thing called `configs`) — flag it,
  do the rename here or log it as backlog.
- **Safety net before commit:** G6 (`configs/` gone); `git grep -n "configs" -- '*.py' ':!dev/archive'`
  returns nothing; the content-equality check of Step 133 applied to `schema.py` (only import lines and
  the docstring path may differ); full suite. `assemble()`'s signature and keyword set must be
  byte-identical — it is pinned API shape from D-141/D-142.

### [Step 135] Documentation, navigation and profile sync
- **Module/boundaries:** `README.md`, `dev/docs/architecture.md`, `dev/docs/roadmap.md`,
  `dev/docs/{index,log,tag}.md`, `examples/data/*/README.md`, `data/README.md`, engine docstring path
  references
- **Assignee:** documentation (+ readme-keeper in `apply` mode; `CLAUDE.md` is the orchestrator's)
- **depends_on:** [Step 134]
- **parallel_safe:** false
- **Changes:** the ~20 engine docstrings citing `data/<kind>/` and `controllers/`; `README.md`'s
  structure/invocation/install sections; the cross-cutting `dev/docs/architecture.md` gains the new
  tree and the SS4.1 layering law; `dev/docs/roadmap.md` gains Phase 2.19.
- **Explicitly NOT touched:** `dev/docs/latex/**` (project rule). Its prose references to `configs/`
  and `data/` will drift — flag this to the user as an accepted, logged consequence.
- **Safety net:** full suite (docstring-only changes can still break the two source-text assertions in
  `test_configs.py`); `dev/docs/{index,log,tag}.md` updated for this document.

---

### SS5.1 Parallelism and sequencing summary

| Step | parallel_safe | Why |
|---|---|---|
| 126 | **true** | new file only |
| 127-135 | **false** | each shares files with its neighbours, and the project's one-step-one-commit discipline wants every step reviewable against its own ticket |

There is no useful parallelism in this phase. Two agents editing overlapping import lines in a
bit-for-bit-pinned suite costs far more than the sequential run saves.

### SS5.2 Where bridge/equality tests are genuinely warranted

Only **Step 130** (an equality bridge over `assemble(DEMO_SCENARIO)`, deleted in the same step) and
**Step 133** (the import-line-ignoring content diff). Steps 131, 132 and 134 are import-graph changes:
they either work or raise `ImportError`, and G2 converts "silently orphaned" into "loudly broken".
Step 129's risk is covered by the resolved-path pin (G5) plus the proof in the superseded doc's SS4.1
that the resolver's rules are shape-driven, not root-driven.

---

<a id="ss6"></a>
## SS6. Open forks — `decision_required`

Five. Numbering is local to this document (`FK1`-`FK5`), deliberately distinct from the superseded
document's `F1`-`F17`. Adopted answers become **D-143** onward.

<a id="fk1"></a>
### FK1 — The packaging mechanism: keep the editable install, or retire it?

**Purpose:** decide whether `pip install -e .` remains how this project is made importable, now that
there is no external consumer to install it for.

| | R1 — keep editable install, update `packages` | **R2 — retire the install, keep `pyproject.toml` as tool config (recommended)** | R3 — delete `pyproject.toml` entirely |
|---|---|---|---|
| What exists after | `pyproject.toml` with `[build-system]`, `[project]`, `[tool.setuptools] packages = [~12 names]`, optionally `[project.scripts]` | `pyproject.toml` with tool sections only (pytest config, future linters); `requirements.txt` owns deps | only `requirements.txt` |
| How code becomes importable | editable finder **and** repo-root-on-`sys.path` (both, today) | repo root on `sys.path` — already the only mechanism actually in use (**measured**: nothing is installed, the suite passes) | same as R2 |
| Cost during this migration | the `packages` list must be rewritten at Steps 129, 131, 132, 133, 134; `pip install -e .` re-run after entry-point changes | zero | zero |
| What you lose | — | console scripts (`rp-airbrake …`) become unavailable until/unless the install returns; running a module from outside the repo root needs `python -m` from the root | same, plus a home for future tool config |
| What you gain | a path back to an installed/distributable package with no re-work | the dead CORE/REFERENCE boundary concept stops being visible in the tree; one fewer thing to keep honest | maximal simplicity |
| Reversibility | — | **high** — re-adding 6 lines of `[tool.setuptools]` is trivial, and with `__init__.py` everywhere (SS4.3) a plain `packages.find` works without `namespaces = true` | high |
| `cost_impact` | ~1 h spread across the phase, recurring | 0 | 0, minus a future tool-config home |

**Recommendation: R2.** The decisive fact is measured, not argued: the project is **not installed
today** and everything works (SS4.5). The install therefore buys nothing currently used, while costing
a `packages` list that must be rewritten five times during this very phase. R2 keeps the door open —
`__init__.py` files land everywhere anyway, so re-enabling a package is a 6-line edit the day a real
consumer or a console-script ergonomic appears.

**What would change this answer:** if the user wants `rp-airbrake`-style global commands *in this
phase*, pick R1 — console scripts are an install-time feature and there is no non-install equivalent.
The cheap middle ground is to keep the five `run*.py` wrappers (which this document does anyway) and
revisit console scripts when the vision-phase CLI is designed.

<a id="fk2"></a>
### FK2 — Engine depth: `apps/sim/engine/` or `apps/sim/` flat?

**Purpose:** fix the import spelling that 336 lines and all future code will use.

| | **A — `apps/sim/engine/` (recommended)** | B — `apps/sim/` flat | C — `apps/sim/core/` |
|---|---|---|---|
| Canonical import | `from apps.sim.engine.integrate import run_sim` | `from apps.sim.integrate import run_sim` | `from apps.sim.core.integrate import run_sim` |
| Where a future simulation app goes | `apps/sim/<app_name>/`, unambiguous sibling of `engine/` | a subdirectory among 30 loose physics modules | as A |
| Layering rule | one sentence: nothing under `apps/sim/engine/` imports outside it | needs a carve-out as soon as sibling dirs appear | as A |
| "Did a pin move?" | diff one directory | diff a directory that also holds app code | as A |
| Typing cost | 4 components | 3 components | 4 components |
| `cost_impact` | identical for all three — one `git mv`, the same 336 rewritten lines | identical | identical |

**Recommendation: A.** The naming word matters less than the fencing; `engine` is what the code
actually is and what `controllers/`'s docstring already calls it implicitly. C is offered because
"core" is the other natural word — if the user prefers it, it is a free swap made now and expensive
later.

<a id="fk3"></a>
### FK3 — Where does `schema.py` live?

**Purpose:** the dataclasses + `assemble()` are the single most-imported surface after the engine
(22 files today, and every future user scenario).

| | **A — `apps/sim/schema.py` (recommended)** | B — `apps/sim/engine/schema.py` | C — `apps/input/schema.py` |
|---|---|---|---|
| Layering | strict: `schema → engine`, engine untouched and purely numeric | schema joins the pinned package | the input bucket becomes load-bearing infrastructure for every other bucket |
| Import | `from apps.sim.schema import Rocket, Motor, assemble` | `from apps.sim.engine.schema import …` — one import covers schema **and** engine names | `from apps.input.schema import …` |
| Pros | the pinned core stays exactly the 30 files it is today, so "what is pinned" has a crisp boundary; `apps/sim/` reads as "the model: what it is, and how it is integrated" | single front door for a user scenario | matches the user's own word for this activity ("input apps = describe my rocket") |
| Cons | two imports in a typical user scenario (schema + a params group) | grows the pinned package by 28.6 K of churn-prone vocabulary; the Step-133 content-equality check gets a special case | makes `apps/input/` a dependency of `analysis`/`optimization`/`control`, violating L3 (buckets do not import each other) |
| `cost_impact` | identical (one `git mv`, 22 import lines) | identical | identical |

**Recommendation: A.** C is the most tempting on vocabulary grounds and the worst on layering: it would
make the `input` bucket a mandatory dependency of every other bucket, which is precisely the kind of
coupling the taxonomy exists to prevent.

<a id="fk4"></a>
### FK4 — `tools/fetch_sounding.py`: move into `apps/input/sounding_fetch/`, or keep `tools/`?

**Purpose:** it is the project's only networked code, and the user's own "input" category is the
natural home for "acquire external data".

| | **A — move to `apps/input/sounding_fetch/` (recommended)** | B — keep `tools/` as "manual developer helpers, outside the product" |
|---|---|---|
| Taxonomy | `apps/input/` gains a real *app* (otherwise it holds only two literals) | `input/` stays literal-only for now |
| Network invariant | restated as "no module under `apps/sim/engine/` imports it, no app imports it at module level", and **enforced by guard G3** (stronger than today's docstring-only rule) | stays trivially true — the networked file is outside `apps/` entirely, which is the easiest possible statement to audit |
| New risk | somebody later imports `apps.input.sounding_fetch` from an app, and a "simulation" run can touch the network. G3 is the mitigation | none |
| Vision alignment | vision §7.5 wants "accept an external measurement" as a first-class product action; this is its first instance | defers that |
| `cost_impact` | ~0.5 h: 1 file, 1 test file, 1 `CLAUDE.md` row, `tools/` deleted | 0 |

**Recommendation: A, conditional on G3 being in place first** (it is — Step 126). If the user values
"the only place network can happen is a folder the product never imports" as a *structural* guarantee
rather than a tested one, B is entirely defensible and costs nothing.

<a id="fk5"></a>
### FK5 — Promote `run.py`'s body into `apps/sim/baseline_run/` now, or later?

**Purpose:** `run.py` today is a demo run plus two model-comparison sweeps. The superseded document's
F8 wanted it promoted to populate the `simulation` bucket.

| | **A — not in this phase (recommended)** | B — promote now to `apps/sim/baseline_run/` + `apps/sim/model_comparison/` |
|---|---|---|
| What this phase is | pure motion: nothing is invented, every file lands somewhere and keeps doing exactly what it did | the phase also creates two new apps and decides their interfaces |
| `apps/sim/` after | `engine/` + `schema.py`; the first real simulation app arrives with the vision phase, as a sibling of `engine/` — the shape is already correct | populated immediately |
| Risk | the `simulation` slot temporarily holds no app (cosmetic) | app-interface design decisions get made inside a restructuring diff, where they are hard to review |
| Vision interaction | vision §3.2/§11.3 wants a *summary* app with run identity and provenance — a different, better app than `run.py`'s body. Promoting `run.py` now likely builds the wrong thing | pre-empts that design |
| `cost_impact` | 0 | ~1.5 h + two tests + the `test_configs.py:209` source-text assertion moves |

**Recommendation: A.** This phase should not invent a single app. The right first simulation app is the
one vision describes ("give me a summary of my rocket", with a run identity), and it should be designed
as product work, not as a by-product of a `git mv`.

### SS6.1 Questions to stress-test with the user (beyond picking an option)

1. **Are the real candidate curves (`cspace`, `euroc-sweep`) actually going to live in `/data`?**
   They are not in this repo today (SS1.3). If they currently live in an fx27 folder, the new gitignored
   `/data` is a *destination*, and somebody has to copy them in — worth confirming that is the intent,
   because if the user expects the repo to already contain them, the split looks like it lost data.
2. **Does `/data` being gitignored match the user's backup reality?** The repo is in Yandex.Disk, so the
   files are synced — but they are no longer versioned, and "which curve did I use in October?" stops
   being answerable from git. That is a real loss against vision's reproducibility goal (§9.4) and may
   argue for tracking `/data` after all, or for a run-provenance mechanism in the next phase.
3. **Is `cfd_conditions` an analysis app or an input app?** It *computes* a reduction over a trajectory
   (analysis) but *produces* an input for an external CFD tool. The answer reveals whether apps are
   classified by what they compute or what they produce — which decides where the *next* app goes too.
   This document puts it in `analysis/`.
4. **How much invocation churn is acceptable?** `python -m apps.airbrake_sizing.solve_cda` becomes
   `python -m apps.optimization.airbrake_sizing.solve_cda`. The five `run*.py` wrappers hide this, but
   any note or habit outside the repo breaks.
5. **`dev/docs/latex/` will drift.** The report's prose cites `configs/` and `data/` paths that will no
   longer exist. The project rule forbids agents editing it. Confirm that drift is accepted (and that
   the user will fix it by hand when they next touch the report), or carve a one-time exception.

---

<a id="ss7"></a>
## SS7. Implications for `CLAUDE.md` «Профиль проекта»

**The architect does not edit `CLAUDE.md`** — this section describes the implied new values for the
orchestrator to apply, after Step 135 and only once the whole phase is merged. Rows not listed are
unchanged.

### SS7.1 Profile table rows

| Row | Today | **Implied new value** |
|---|---|---|
| Стек | `Python 3.12 (numpy, scipy, matplotlib — requirements.txt), pytest; отчёт — LaTeX (dev/docs/latex/)` | unchanged |
| Код backend / ядро | `sim/` (физическая модель…), `configs/` (…), `apps/` (прикладные утилиты), `tools/` (ручные сетевые хелперы), `data/` (моторы, аэро, зондирования) | `apps/` — корень продукта: `apps/sim/engine/` (физическая модель, интегратор, отчёты, численные пины), `apps/sim/schema.py` (Rocket/Motor/LaunchSite/Weather/Scenario + `assemble()`), `apps/input/`, `apps/analysis/`, `apps/optimization/`, `apps/control/`, `apps/_shared/`; `examples/data/` (демо/фикстуры), `data/` (личные данные пользователя, гитигнор) |
| Код frontend | нет | unchanged |
| Запуск приложения | `python run.py`; `python run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py` (или `python -m apps.<app>.<module>`) | same five `run*.py`; the module form becomes `python -m apps.<type>.<name>.<module>` (e.g. `python -m apps.optimization.airbrake_sizing.solve_cda`). **Always from the repo root** |
| Тесты backend — точечно / полный | `python -m pytest tests/test_<name>.py -q` / `python -m pytest -q` | unchanged |
| Платные / внешние API | `…Единственная сеть — tools/fetch_sounding.py …; sim/ всегда офлайн и детерминирован` | `…Единственная сеть — apps/input/sounding_fetch/fetch_sounding.py (запуск вручную); apps/sim/engine/ всегда офлайн и детерминирован` (**gated on FK4**) |
| Тип деплоя | `нет — локальная библиотека + скрипты` | `нет — локальный инструмент, запуск из корня репозитория; устанавливаемого пакета нет` (**gated on FK1 = R2/R3**) |

### SS7.2 New / changed entries in the «ловушки окружения» list

| Trap | Action |
|---|---|
| `sim/` офлайн и детерминирован… | **reword** to `apps/sim/engine/`; add that the invariant is now enforced by `tests/test_layering.py` (G1/G3), not only by docstring |
| `Чужой пакет tests в site-packages… поэтому tests/__init__.py обязателен` | **keep, and strengthen**: with no editable install, `tests/__init__.py` is also what puts the repo root on `sys.path` under pytest's `prepend` import mode |
| *(new)* **Запуск только из корня репозитория.** Устанавливаемого пакета больше нет; `import apps.…` работает потому, что корень репозитория — `sys.path[0]`. Запуск скрипта из подпапки импортов не найдёт. | add (gated on FK1) |
| *(new)* **Личные данные в `/data` не версионируются** (гитигнор, кроме `data/README.md`). Бэкап — только облачная синхронизация папки. | add |
| *(new)* **Бэйр-имена файлов данных резолвятся в `examples/data/`**, не в `/data`. Свои файлы указывать явным относительным путём от корня. | add |
| `LaTeX не редактировать` | keep; add the note that its path citations are knowingly stale after Phase 2.19 |

### SS7.3 Other documents the orchestrator will need to touch

`README.md` (structure, invocation, no-install note), `dev/docs/architecture.md` (the cross-cutting
reference gains SS2.2's tree and SS4.1's layering law), `dev/docs/roadmap.md` (Phase 2.19 + Steps
126-135), `dev/docs/{index,log,tag}.md` (this document; `documentation` agent owns them).

---

<a id="ss8"></a>
## SS8. Proposed stage id and slug

**Proposed:** `2.19` — **`apps-root-restructure`**.

Full title for the tracker (Russian, per the user-facing language rule):

> **Phase 2.19 — пивот: `apps/` становится корнем продукта (движок в `apps/sim/engine/`, `configs/`
> уходит, `data/` расщепляется, упаковка снимается)**

Rationale for the number: this is the direct continuation of the packaging/structure lineage —
2.15 (configs split) → 2.16 (motor-config separation) → 2.18 (registry retirement + packaging) →
**2.19** (packaging retirement + product-root restructure). It is not physics, so it must not take a
Phase 3.x number; and 2.17 (paper-alignment) and 3 (3D dynamics) are both still `in_progress`, so 2.19
slots in without disturbing either.

Tracker bookkeeping this phase implies:

- Steps **126-135**; decisions **D-143** onward (one per adopted fork FK1-FK5, plus any sub-decision
  taken mid-step).
- Backlog items **B-40** onward for the two known cosmetic leftovers surfaced here:
  `tests/test_apps_common.py` and `tests/test_configs.py` carry names that stop being true (B38/B39
  already cover similar naming drift from Phase 2.18 — these are the same class).
- Git-flow: one `feature/apps-root-restructure` branch off `develop`, merged `--no-ff` only after the
  user's "да". Given Step 133's size, a tag before it (`pre-engine-move`) is cheap insurance.

---

<a id="ss9"></a>
## SS9. Rejected options

Recorded so they are not re-proposed. Options rejected *inside* a fork are in SS6; these are rejected
at the design level.

| # | Rejected | Why |
|---|---|---|
| 1 | **Start from an empty folder and copy code in fresh.** | Same edit volume either way, and it discards git history/blame on 1.3 MB of pinned physics plus the `D-NN`/`Step NN`/`B-NN` institutional numbering. Already settled with the user; recorded here so it stays settled. |
| 2 | **Keep `sim/` top-level and only reorganise `apps/`** (the superseded document's premise). | Overtaken by decision 2. Its justification was "it breaks the external consumer's import", and there is no external consumer. |
| 3 | **An umbrella package `rocket_physics.{…}`** (superseded F7 option 2). | It existed to stop generic top-level names (`sim`, `configs`, `apps`) colliding in a shared `site-packages`. With no install there is no `site-packages` and no collision. `apps/` as the product root achieves the same single-front-door effect for free. |
| 4 | **Make `/data` a second bundled root** so the user's real curves resolve by bare name. | Changes the semantics of `datafiles.resolve()`, which Phase 2.18 settled as three shape-driven rules, and introduces a silent ambiguity (which root won?) over data that numeric pins depend on. The explicit-relative-path contract (SS3.1) costs the user one path prefix and keeps the resolver provable. |
| 5 | **Back-compat shim packages** (`sim/__init__.py` re-exporting `apps.sim.engine.*`, a `configs` alias). | The project's own precedent is a clean break per step (Step 125). Shims would make G2 and the Step-133 content-equality check meaningless, and there is nobody outside the repo to be compatible with. |
| 6 | **Re-export facades in `__init__.py`** (`from apps.sim import Rocket, run_sim`). | Two spellings per name across a 336-line mechanical rewrite is how inconsistency enters; and it makes `import apps.sim.anything` pull in all 30 engine modules plus matplotlib. Revisit only when a deliberate user-facing API is designed (vision phase). |
| 7 | **Promoting `flight_stats.py` or `ensemble.py` into the engine.** | `ensemble` reverses a standing decision that the engine is single-run; `flight_stats` is an apps-layer reduction over a `Result` and would grow the pinned package for no gain. |
| 8 | **Moving `tests/` under `apps/` or installing it.** | `tests/__init__.py` exists because of a real top-level-name collision (`eventkit` ships a `tests` package). Nothing in the user's decisions touches the suite's location. |
| 9 | **Fixing `dev/docs/latex/` path references as part of this phase.** | Explicit project rule: agents do not edit the LaTeX tree. The drift is logged (SS6.1 Q5) instead. |
| 10 | **Doing the engine move and the taxonomy move in one commit.** | ~1.4 MB of renames plus two independent import rewrites in one diff is unreviewable, and it would make "which move broke the pin?" unanswerable. |
| 11 | **`apps/common/` kept as a sixth sibling.** | `common` is not an app type; three of its four files belong in boxes that describe them (SS3.4), and the fourth pair is infrastructure that `_shared` names honestly. |

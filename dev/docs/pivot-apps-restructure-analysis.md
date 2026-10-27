# Pivot 2: `apps/` rejoins the installed package, app-type taxonomy, `data/` → `examples/`, folder cleanup

## Кратко (RU)

- Документ — анализ развилок (НЕ решение; **17 развилок F1-F17**, нумерация своя, с `F1-F16` прошлого
  документа `pivot-configs-and-packaging-analysis.md` она НЕ связана) для второго пивота: пользователь
  хочет (1) вернуть `apps/` внутрь устанавливаемого пакета, (2) разложить приложения по
  `apps/<тип>/<имя>/` (input / simulation / optimization / control), (3) перенести `data/` в
  `examples/`, (4) «заархивировать ненужные папки, в т.ч. `/docs` и `/configs`».
- **Главная находка: четыре приложения из `apps/` импортируют `examples.worked_scenario.DEMO_SCENARIO`,
  а `examples/` в пакет не входит.** То есть «просто добавить apps в `packages`» даёт `ImportError` из
  внешней папки. Зависимость направлена неправильно (библиотека зависит от своей папки примеров) — это
  надо развернуть до переезда файлов (F3).
- **Второй баг того же класса, что лечил Step 120:** `apps/common/artifacts.py` считает `OUTPUT_DIR` от
  `__file__` репозитория, поэтому установленное приложение будет писать CSV/PNG в `output/` *библиотеки*,
  а не в папку пользователя. Лечится как в `sim/datafiles.py` — якорь на `cwd` + `--out-dir` (F4).
- Новых зависимостей apps не требуют: только `numpy`/`scipy`/`matplotlib`, все уже в `[project.dependencies]`
  (проверено по всем импортам `apps/`, `controllers/`, `examples/`, `run*.py`).
- Таксономия: четыре категории пользователя почти подходят, но `weight_aero_tradeoff` и `cfd_conditions`
  — это **не** оптимизация, а характеризация/чувствительность. Рекомендация — «ваши четыре + `analysis/`»
  (F8). `controllers/` — складывать в `apps/control/` можно без риска для пинов: правило односторонней
  связи (`sim/` никогда не импортирует контроллеры) сохраняется дословно, регистрация законов —
  рантаймовый эффект импорта, от расположения не зависит (F11).
- `data/` → `examples/data/` стоит **одну строку** в библиотеке (`sim/datafiles.py:45 _BUNDLED`): все три
  правила резолвера и все строки в конфигах — «голые имена», поведение не меняется. Основная работа —
  13 тестовых файлов со своими путями `../data/...` (рекомендация: один общий `tests/datadir.py`, F14).
- `configs/` **нельзя** удалить: это `schema.py` (все датаклассы + `assemble()`) + 20-строчный шим.
  Вопрос «переименовать ли» уже задавался и был закрыт «нет» в Phase 2.18 — здесь он подан как
  «пересматривать ли» (F15); не исключено, что пользователь имел в виду уже заархивированный
  `dev/archive/configs-registry-2026-10/`.
- Корневой `docs/` — мусор сборки LaTeX (untracked, ~1 МБ `.aux/.pdf/.synctex.gz`), настоящее дерево —
  `dev/docs/latex/`. Это не развилка: удалить.

---

## Table of contents

- [SS1. Current-state inventory (verified this session)](#ss1)
- [SS2. Area A — `apps/` rejoins the installed package (F1-F7)](#ss2)
- [SS3. Area B — the `apps/<app_type>/<app_name>` taxonomy (F8-F11)](#ss3)
- [SS4. Area C — `data/` → `examples/` (F12-F14)](#ss4)
- [SS5. Area D — "archive unnecessary folders" (F15-F17)](#ss5)
- [SS6. Recommended ordered step sequence, with safety nets](#ss6)
- [SS7. What breaks / what needs updating — file by file](#ss7)
- [SS8. Fork summary table + questions to stress-test with the user](#ss8)
- [SS9. Verified facts (grounding)](#ss9)

**Relationship to the previous pivot document.** `dev/docs/pivot-configs-and-packaging-analysis.md`
(Phase 2.18, D-137..D-142, implemented and merged) is the input to this one. Its fork numbering `F1`-`F16`
is **closed**; the `F1`-`F17` below are a new, independent set. Settled ground that this document does
**not** reopen: the registry retirement itself; `Motor`/`Rocket`/`LaunchSite`/`Weather`/`Scenario` as
plain dataclasses; the `assemble()` → `run_sim()` API shape; the 3-rule `sim/datafiles.py` resolver
*semantics*; `pyproject.toml` + editable install as the packaging mechanism; the `_TEMPLATE_*` →
`examples/worked_scenario.py` consolidation. What this document **does** revise is exactly the
CORE/REFERENCE classification of `apps/` and `data/` recorded in that document's SS1.1 and its forks
F2 and F10 — the user has changed their mind, and the previous recommendation ("leave `apps/` in place,
excluded from `packages`") was explicitly conditional on that.

---

<a id="ss1"></a>
## SS1. Current-state inventory (verified this session)

### SS1.1 Top-level map

| Dir / file | Tracked | Installed today (`packages = ["sim","configs"]`) | Size | What it is | Touched by this pivot? |
|---|---|---|---|---|---|
| `sim/` | yes | **yes** | 1.3 M, 26 modules | the physics engine; regular package (`sim/__init__.py` exists) | one line (`datafiles._BUNDLED`) + docstrings |
| `configs/` | yes | **yes** | 72 K, **2 files**: `__init__.py` (28-line re-export shim) + `schema.py` (28.6 K) | the dataclass/`assemble()` surface | only if F15 says rename |
| `apps/` | yes | no | 440 K, 13 modules in 5 dirs, **no `__init__.py` anywhere** (implicit namespace packages) | the 4 study apps + shared helpers | **yes — the subject** |
| `controllers/` | **yes** (committed in the Phase 2.17/2.18 merge) | no | 36 K, 3 files | flight software under design: `estimator.py`, `laws.py`, `__init__.py` whose import registers the two sampled laws into `sim.control` | **yes (F11)** |
| `examples/` | yes | no | 24 K, 1 file (`worked_scenario.py`), no `__init__.py` | the REQ/OPT worked example **and** the single source of `DEMO_SCENARIO` for `run.py`, 3 apps and ~10 tests | **yes (F3, F12)** |
| `data/` | yes | no (reachable only because the editable install leaves `sim.__file__` inside the repo) | 52 K, 13 files | bundled motor curves / aero table / soundings | **yes — moves (F12)** |
| `tests/` | yes | no (boundary measured: `import tests` fails from an external cwd) | 3.4 M, 49 files | the suite, incl. the numeric pins | **yes, as collateral (13 + 12 + 10 files)** |
| `tools/` | yes | no | 36 K, 1 file (`fetch_sounding.py`, manual, the project's only network code) | sounding downloader | **F6** |
| `run*.py` | yes (5 files) | n/a (root modules, not packages) | ~8 K | thin `main()` wrappers | **yes (F5)** |
| `dev/` | yes | no | — | tracker + docs + `dev/archive/configs-registry-2026-10/` | only `dev/docs/*` (orchestrator-owned); **F16** |
| `docs/` | **no (untracked)** | no | ~1 M | `docs/latex/{main.aux,.fdb_latexmk,.fls,.log,.out,.pdf,.synctex.gz,.toc}` — pure LaTeX build output | **not a fork — delete (SS5.1)** |
| `output/` | no (gitignored) | no | — | generated CSV/PNG | behaviour changes via F4 |
| `temp/` | no (gitignored) | no | — | scratch (user's MATLAB prototypes; also this session's packaging mock) | out of scope |
| `temporary/` | no (gitignored) | no | — | drafts | **explicitly out of scope per project convention** |

### SS1.2 The `apps/` tree in detail

| Module | Lines | What it answers | Third-party imports | Repo-anchored paths | Imports `examples.*` |
|---|---|---|---|---|---|
| `apps/cfd_conditions/select_conditions.py` | 217 | which (V, AoA, M, Re) points deserve a CFD run | numpy | `_OUTPUT_DIR = Path(__file__).parent.parent.parent/"output"` (l. 94) | **yes** (l. 89) |
| `apps/motor_selection/compare_motors.py` | 347 | of these N motors on this airframe, which flies highest (legacy `MotorEntry`/`overrides` path) | numpy, matplotlib | `OUTPUT_DIR` (l. 82, 337) | no |
| `apps/motor_selection/motors.py` | 70 | the per-motor dry-vehicle literal (`MOTORS`) | — | — | no |
| `apps/motor_selection/scenario_sweep.py` | 452 | App 3 v2: sweep a `Motor` list over one `Scenario`, rank vs target + constraints | numpy, matplotlib | `OUTPUT_DIR` default, **but already has `--out-dir`** (l. 442); uses private `motor_file._motors_path` (l. 130) | **yes** (l. 54) |
| `apps/airbrake_sizing/solve_cda.py` | 688 | solve the brake `C_dA` that hits a target apogee (`scipy.optimize.brentq`) | numpy, scipy, matplotlib | `OUTPUT_DIR` (l. 83, 678) | **yes** (l. 86) |
| `apps/airbrake_sizing/targets.py` | 55 | the target-apogee literals (`SPECS`) | — | — | no |
| `apps/weight_aero_tradeoff/trade_surface.py` | 433 | the 2-D (mass × C_dA) apogee surface + local exchange rate | numpy, scipy, matplotlib | `OUTPUT_DIR` (l. 108, 423) | no |
| `apps/weight_aero_tradeoff/compare_configs.py` | 241 | A/B two whole configurations the surface's axes cannot express | numpy, matplotlib | `OUTPUT_DIR` (l. 51, 231) | no |
| `apps/weight_aero_tradeoff/scenarios.py` | 114 | the default trade box (`SCENARIOS`, `default_axes`) | — | — | no |
| `apps/common/artifacts.py` | 30 | `OUTPUT_DIR` + `ensure_dir` | — | **`Path(__file__).parents[2]/"output"`** (l. 21) | no |
| `apps/common/flight_stats.py` | 229 | the shared ascent-window reduction over a `Result` (3 apps use it) | numpy | — | no |
| `apps/common/ensemble.py` | 393 | Monte-Carlo ensemble driver (`Dispersion`, `run_ensemble`, `ProcessPoolExecutor`) | numpy | — | no |
| `apps/common/study_vehicle.py` | 83 | the 1.5 kg / 75 mm constant-mass study vehicle literal | — | — | no |

Entry points: `run.py` (demo run + 2 model-comparison sweeps; imports `examples.worked_scenario`),
`run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py` (thin `main()`
forwarders, 5-40 lines each).

### SS1.3 The five couplings that decide every fork below

These are facts, measured this session, not judgements.

1. **`apps/` → `examples/` is a backwards dependency.** Four modules
   (`cfd_conditions/select_conditions.py:89`, `motor_selection/scenario_sweep.py:54`,
   `airbrake_sizing/solve_cda.py:86`, plus `run.py:34`) do
   `from examples.worked_scenario import DEMO_SCENARIO`. `examples/` is **not** in
   `[tool.setuptools] packages`. So adding `"apps"` to that list produces a package whose apps raise
   `ModuleNotFoundError: No module named 'examples'` the moment they are imported from anywhere but the
   repo root. A library must not depend on its own examples folder; this has to be reversed (F3) before
   any file moves.
2. **`apps/` writes to a repo-anchored output directory.** `apps/common/artifacts.py:21` is
   `OUTPUT_DIR = Path(__file__).parents[2] / "output"`, and `cfd_conditions` hand-rolls the same thing
   at line 94. Under an editable install `__file__` stays inside the repo, so an installed app invoked
   from the user's own folder silently writes its CSV/PNG into **the library's** `output/`. This is
   precisely the bug class Step 120 fixed for *reading* data; it is still open for *writing* artifacts
   (F4). Precedent for the fix already exists in-repo: `scenario_sweep.py --out-dir`.
3. **`apps/` and `examples/` have no `__init__.py` at all** — they are implicit (PEP 420) namespace
   packages, working today only because the repo root is `sys.path[0]`. Measured consequences in
   [SS9](#ss9): an explicit `packages = [...]` list *does* install them correctly, but
   `[tool.setuptools.packages.find]` **without** `namespaces = true` silently drops them, and a
   namespace package installed under a generic name can be *merged with* a same-named directory in the
   user's own working folder. That makes "add `__init__.py`" a real fork, not cosmetics (F2).
4. **The bundled-data anchor is exactly one line.** Every loader now goes through
   `sim.datafiles.resolve()`; the only place that knows where the bundled tree lives is
   `sim/datafiles.py:45` (`_BUNDLED`). `sim/motor_file.py:80 _motors_path()` is a thin back-compat
   wrapper over it (kept because `apps/motor_selection/scenario_sweep.py:130` and
   `tests/test_scenario_sweep.py` stat the file directly). So the `data/` move is one library edit plus
   callers that compute their own paths: `tools/fetch_sounding.py:281` and 13 test files.
5. **`controllers/` is injected into `sim/`, not consumed by it.** `controllers/__init__.py` imports
   `sim.control` and calls `register_sampled_law(...)` at import time; `sim/` never imports
   `controllers` (7 docstring references only, in `sim/control.py`, `sim/params.py`, `sim/roll.py`,
   `sim/sensors.py`). `tests/test_control.py:675` pins the "law name unresolvable until the package is
   imported" behaviour. The registration is a *runtime* side effect of importing, so it is entirely
   independent of where the package lives — moving it cannot move a physics pin (F11).

### SS1.4 Dependency check (F1's precondition)

Every third-party import across `apps/`, `controllers/`, `examples/`, `run*.py`, collected
exhaustively: `numpy`, `scipy.interpolate.RegularGridInterpolator`, `scipy.optimize.brentq`,
`matplotlib.pyplot`. Standard library: `argparse, csv, dataclasses, functools, hashlib, json, math, os,
sys, time, pathlib, typing, concurrent.futures`. **No new `[project.dependencies]` entry is required** —
`numpy==2.5.4`, `scipy>=1.18,<2`, `matplotlib>=3.11,<4` are already declared.

Two nuances worth recording:

- **matplotlib becomes a hard runtime dependency of the package's *apps* layer, not just its plotting
  layer.** It already is a declared dependency, so nothing changes mechanically; but if a `[project
  .optional-dependencies] plots` split is ever wanted, installing `apps/` is the moment that choice
  gets harder (4 of 13 app modules import `pyplot` at module level). Not a fork I would open now —
  flagged so it is a decision rather than a drift.
- **`apps/common/ensemble.py` uses `ProcessPoolExecutor`**, and on Windows (`spawn`) the child process
  must be able to **import the module that defines the callable** —
  `functools.partial(_safe_evaluate, evaluate)` where `_safe_evaluate` is top-level in
  `apps.common.ensemble` (the module docstring documents this constraint deliberately). Installing
  `apps/` makes that import work from *any* cwd, which is a genuine robustness improvement over today
  (where it relies on inherited `sys.path`). The user's own `evaluate` function must still be a
  top-level function in an importable module of *their* project — worth one line in the docs.

---

<a id="ss2"></a>
## SS2. Area A — `apps/` rejoins the installed package (F1-F7)

### SS2.1 What "`apps/` is installable" actually requires

Five things, in dependency order. Only the first is what the user asked for; the other four are what it
costs.

1. `"apps"` (and, per F2, its subpackages) joins `[tool.setuptools] packages`.
2. The `apps → examples` dependency is reversed (SS1.3 #1), otherwise the installed apps are
   import-broken from any external cwd. **F3.**
3. Artifact output stops being repo-anchored (SS1.3 #2), otherwise installed apps write into the
   library's folder. **F4.**
4. The packages become *regular* packages or the `find` directive learns about namespaces
   (SS1.3 #3), otherwise either the install silently omits them or a same-named folder in the user's
   project can merge with them. **F2.**
5. Someone decides how the user *invokes* them now that `python -m apps.X.Y` from the repo root is no
   longer the only option. **F5.**

Nothing else is needed: no new dependency (SS1.4), no change to `sim/`, no change to any numeric pin.

<a id="f1"></a>
### F1 — Which top-level things are installed?

**Purpose:** define the new package boundary, i.e. what an external script can `import` after
`pip install -e .`.

| | L1 "install everything runnable" | L2 "install the library + apps, keep `examples/` as examples" (recommended) | L3 "umbrella package" |
|---|---|---|---|
| `packages = [...]` | `sim, configs, apps(+subs), controllers, examples` | `sim, configs, apps(+subs)` — `controllers` folds into `apps/control/` (F11), `examples/` stays out | `rocket_physics` (+subs), everything moves inside it |
| `examples/` role | an installed package; `DEMO_SCENARIO` keeps living there and apps keep importing it | not installed: runnable scripts + the bundled data tree (SS4); **the demo scenario literal moves into the package** (F3) | inside or outside, free choice |
| File moves | **zero** | the demo scenario (1 file), `controllers/` (3 files), plus the taxonomy moves of Area B | ~all of them |
| Pros | cheapest possible ("add two names to a list"); `python -m examples.worked_scenario` keeps working verbatim | the dependency arrow points the right way (examples → library, never library → examples); `examples/` means what its name says; the package contains only things that are somebody's dependency | one front door, one import name, no generic-name collisions (see F7) |
| Cons | institutionalises the backwards dependency; makes **`examples`** an installed top-level import name — the single most likely name to also exist in the user's own project folder (namespace merge hazard, SS9 fact 4); the tutorial file becomes load-bearing library code that can no longer be freely edited | the demo scenario has to move, and ~10 test files + 3 apps + `run.py` follow it (all 1-line import edits) | 90-110 files touched; needs its own phase and full-suite gate |
| Cost | ~0.5 h | ~3-4 h (bundled into Area B's moves anyway) | ~6-10 h, separate phase |

**Recommendation: L2.** It is the only option that leaves the import graph defensible: an installed
library must not import out of its own `examples/` folder, and `examples` is the worst possible
top-level name to publish (F7). L1's zero-move appeal is real, but it buys the cheap thing now and
pays for it on every future edit to the tutorial file. L3 is the right *eventual* answer and is kept
alive as F7.

<a id="f2"></a>
### F2 — Declaration mechanism and package kind (`__init__.py` or not)

**Purpose:** make the install both complete (nothing silently omitted) and unshadowable.

| | (a) explicit list, keep namespace dirs | (b) explicit list + add `__init__.py` to every app package (recommended) | (c) `[tool.setuptools.packages.find]` + `namespaces = true` |
|---|---|---|---|
| `pyproject.toml` | `packages = ["sim","configs","apps","apps.common","apps.<type>",...]` | same list (now it is also literally true that these are packages) | `include = ["sim*","configs*","apps*"]`, `namespaces = true` |
| Measured behaviour | works; editable install maps the top-level name to the live dir, submodules import fine even when only `"apps"` is listed | works; additionally a *regular* package beats a same-named namespace dir earlier on `sys.path` | works, and auto-discovers; but with `namespaces=true` it also discovers every **non-code** subdirectory as a package (measured: `apps.motor_selection.data_tables` from a plain CSV folder) |
| Wheel-correctness | a non-editable wheel copies only the listed names — an unlisted `apps.common` would vanish | same, but the list is easy to keep honest | best: nothing to forget |
| Shadowing risk | a user folder named `apps/` merges with the installed namespace package → `import apps.common` can resolve out of *their* tree, silently | eliminated for our packages | same as (a) — `find` does not change package kind |
| Maintenance | every new app dir must be added to the list | same + one empty `__init__.py` per dir | zero |
| Cost | ~0.2 h | ~0.5 h (13 tiny files) | ~0.3 h |

**Recommendation: (b) — explicit list *and* `__init__.py` in `apps/` and each app package.** The
shadowing argument is decisive once `apps` is a published import name: namespace-package *merging* is
the worst failure mode in this whole document, because it produces a half-working import instead of an
error. The explicit list is also the project's established boundary marker (prior F7/A2), and the extra
maintenance is one empty file per new app. If the list's upkeep is judged annoying, (c) can be layered
on top of (b) later — with `__init__.py` present, plain `find` (no `namespaces`) suffices and the
data-dir over-discovery disappears.

Note for the implementer: `examples/` under L2 stays a namespace dir (not installed), so
`python -m examples.worked_scenario` keeps working from the repo root exactly as today. If F3's
sub-option keeps a literal there, consider `__init__.py` there too.

<a id="f3"></a>
### F3 — Where does the shared demo scenario live?

**Purpose:** one source of truth for the K570-on-54 mm demo, importable by the package without the
package importing `examples/`. (This is the direct continuation of the previous pivot's F16/D-139-140,
which deliberately made it one shared constant.)

| | (a) install `examples/` (= F1 L1) | (b) move the annotated literal into the package; `examples/worked_scenario.py` becomes a thin runner (recommended) | (c) duplicate: package gets the literal, `examples/` keeps its own copy + a bridge test | (d) each app owns its own scenario literal |
|---|---|---|---|---|
| Mechanics | add `"examples"` to `packages` | `git mv examples/worked_scenario.py apps/input/demo_scenario.py` (per Area B's taxonomy), keeping every `REQ|OPT` comment; `examples/worked_scenario.py` shrinks to ~20 lines: import it, `assemble`, `run_sim`, print, plus "copy `apps/input/demo_scenario.py` to start your own" | as (b) plus a second full literal in `examples/` + a field-by-field equality test | delete the shared constant |
| Who imports what | apps → examples (backwards) | apps → apps.input (fine); examples → apps.input (fine) | both, plus a drift guard | nobody shares |
| Pros | zero moves | one literal, right dependency direction, comments preserved verbatim, the "copy this file" story still works (the file is in the editable repo) | the tutorial file stays a self-contained standalone artefact | apps become independent |
| Cons | see F1 L1 | the crib sheet now lives under `apps/`, which is slightly surprising for a tutorial; `tests/test_worked_scenario_example.py`'s `python -m examples.worked_scenario` invocation and ~10 test imports move | two copies of ~15 numbers is how pins drift — the exact failure the previous pivot's F16 avoided | ~4 copies of the demo; pins drift; reverses D-139/D-140 |
| Cost | 0 | ~1.5 h (1 move + ~14 one-line import edits) | ~2.5 h + a permanent test | ~2 h and a regression |

**Recommendation: (b).** The dependency direction is the whole point of F1 L2, and (b) is the only
option that fixes it without duplicating literals. Name the new home honestly — `apps/input/
demo_scenario.py` under Area B's taxonomy (a demo scenario *is* an input definition), exporting
`DEMO_SCENARIO`, `rocket`, `motor`, `site`, `weather` exactly as today (three test files import the
individual pieces, not only the scenario: `tests/test_demo_physics.py:30-32`,
`tests/test_motor_pieces.py:39`).

Reject (c) on the previous pivot's own evidence; reject (d) outright.

<a id="f4"></a>
### F4 — Where do installed apps write their CSV/PNG?

**Purpose:** stop an installed app from writing into the library's own folder (SS1.3 #2).

| | (a) status quo: repo-anchored `__file__` | (b) cwd-anchored default + `--out-dir` on every app (recommended) | (c) env var `ROCKET_PHYSICS_OUTPUT` + cwd default | (d) no default — `--out-dir` required |
|---|---|---|---|---|
| `apps/common/artifacts.py` | `Path(__file__).parents[2]/"output"` | `OUTPUT_DIR = Path.cwd()/"output"` evaluated **at call time**, not import time (a module-level constant would freeze the cwd of the importing process) → make it `output_dir()` returning `Path.cwd()/"output"` | as (b) + `os.environ` lookup | helper just validates |
| Behaviour when run from the repo root | unchanged | **unchanged** (cwd == repo root → `<repo>/output/`), so every existing test and habit survives | unchanged | breaks `python run.py` ergonomics |
| Behaviour from the user's folder | writes into the library — wrong | writes `./output/` next to their script — right | configurable | explicit |
| Consistency with `sim/datafiles.py` | — | **exactly rule 2** of the resolver ("relative → the caller's cwd"); one mental model for reads and writes | adds the ambient global state the previous pivot's F5 rejected for data roots, for the same reason (determinism contract) | — |
| Cost | 0 | ~2 h: 1 helper + 5 call sites + `--out-dir` on the 4 apps that lack it (one already has it) | ~2.5 h | ~1.5 h + churn |

**Recommendation: (b).** It is behaviour-preserving for every current invocation, it removes the whole
bug class, and it reuses the resolver's existing mental model. Fold `cfd_conditions`'s hand-rolled
`_OUTPUT_DIR` into the shared helper in the same step (the Step-64 TODO in `artifacts.py`'s own
docstring). Reject (c) for the same "no ambient global state" reason the data-root fork was rejected;
the env var buys nothing a `--out-dir` flag does not.

**Test consequence:** any test asserting a written path must pass `tmp_path` (or `monkeypatch.chdir`)
rather than relying on the repo's `output/`. Worth a grep during implementation — `output/` is
gitignored, so a test writing there today is invisible in `git status`.

<a id="f5"></a>
### F5 — How are apps invoked once they are installed?

**Purpose:** give an external user a front door that does not require `cd`-ing into the library repo.

| | (a) keep the five `run*.py` only | (b) add `[project.scripts]` console scripts (recommended now) | (c) one `rocket-physics <subcommand>` CLI | (d) both (b) and (c) |
|---|---|---|---|---|
| What the user types | `python run_airbrake.py` from the repo root only | `rp-airbrake --target 3850` from anywhere in the venv | `rp airbrake ...` | both |
| `pyproject.toml` | — | `[project.scripts]` with 5 entries → `"apps.optimization.airbrake_sizing.solve_cda:main"` etc. Zero code. | a new ~60-line dispatcher module | — |
| Pros | zero work | the real payoff of installing `apps/`; also makes the 3-level module paths (Area B) irrelevant to ergonomics | one discoverable front door; `rp --help` lists every app | — |
| Cons | the restructure delivers nothing invocation-wise | 5 global command names in the venv; names need bikeshedding (`rp-*` vs `rocket-*`) | a new maintained surface; `main(argv)` signatures must be uniform (they are not quite: `run_trade.py` already multiplexes two modes) | most work |
| Cost | 0 | ~0.5 h | ~2 h | ~2.5 h |

**Recommendation: (b) now, keep `run*.py` as-is, consider (c) later.** The `run*.py` wrappers cost
nothing to keep and two tests read `run.py`'s source text (`tests/test_configs.py:221`). Console
scripts are 5 lines of metadata for the single most visible benefit of this pivot. One caveat to
verify at implementation time: `[project.scripts]` entry points are generated at install time, so the
user must re-run `pip install -e .` after this step (editable installs do *not* pick up new entry
points automatically).

<a id="f6"></a>
### F6 — Do `tests/`, `tools/` and `run*.py` change classification too?

**Purpose:** decide whether the reclassification is apps-only or wider.

| Item | Options | Recommendation |
|---|---|---|
| `tests/` | (a) stay out of the package (status quo; measured: `import tests` fails from an external cwd); (b) install as `rocket_physics.tests`; (c) move under `sim/tests/` | **(a), unchanged.** 3.4 MB of pins that import `apps`, `examples` and write temp files into the bundled data tree. Shipping them would publish a `tests` top-level name — the exact collision the project was already bitten by (`eventkit`), and `tests/__init__.py` exists *because* of it. Nothing in the user's request touches this. |
| `tools/fetch_sounding.py` | (a) stay as `tools/`, not installed; (b) **become an input app**: `apps/input/sounding_fetch/`, installed; (c) archive it | **(b).** It is the clearest "input app" in the repo under the user's own taxonomy: it produces a simulation input (a sounding case) from an external source. Moving it also makes its repo-anchored write path (`fetch_sounding.py:281`) get fixed by F4's cwd rule instead of being a second special case. **Two caveats to state in the move:** (i) it is the project's only network code — the invariant "`sim/` is offline and deterministic" must be restated as "no module under `sim/` imports `apps.input.sounding_fetch`, and no app imports it at module level"; (ii) if `tools/` empties out, the `CLAUDE.md` profile row that lists `tools/` needs an update (orchestrator-owned). |
| `run*.py` | (a) keep all five at the root; (b) delete in favour of console scripts (F5); (c) move under `examples/` | **(a).** They are 5-40 line forwarders, they are the documented invocation in `CLAUDE.md`'s profile, and two tests read `run.py`'s source. Their import lines change with Area B's moves; that is all. |

<a id="f7"></a>
### F7 — Import-name strategy: flat generic names, or the `rocket_physics` umbrella?

**Purpose:** decide what names this package publishes into a shared `site-packages`.

This is the previous pivot's F8 re-opened by new facts, and it is the one fork where I think the user's
own framing ("simulator is part of the whole rocket-physics app") points at the bigger answer.

| | (1) flat: `sim, configs, apps, controllers` (recommended for *this* phase) | (2) umbrella: `rocket_physics.{sim, config, apps, ...}` | (3) facade: keep flat, add a thin `rocket_physics` re-export package |
|---|---|---|---|
| Published top-level names | 4-5, all generic: `sim`, `configs`, `apps` (+`examples` under L1) | 1 | 5 + 1 |
| Shadowing / merge hazard in the user's project | **high and newly worse**: `apps/`, `configs/`, `data/`, `examples/` are all names a user plausibly has as folders in their own working directory; for *namespace* packages the two even merge (mitigated by F2(b), not eliminated — a user folder with its own `__init__.py` still wins) | none | unchanged for the real imports |
| PyPI dist-name collisions | `configs` is a live distribution (v3.0.3, measured in the previous pivot) | none | unchanged |
| Blast radius | 0 beyond Area B's own moves | ~70 files import `sim.*`, ~22 import `configs.*`, 13 app modules + 12 test files + 5 runners already moving in Area B | ~1 new file |
| Risk to numeric pins | none | none mechanically (pure rename), but a ~100-file mechanical edit over a bit-for-bit-pinned suite is where a typo hides; needs the full-suite gate and a careful diff | none |
| Breaks the external consumer (`fx27/simulation`) | no | **yes** — its imports must be rewritten | no |
| Cost | 0 | ~6-10 h, own phase | ~0.5 h, and arguably confusing (two ways to import the same thing) |

**Recommendation: (1) for this phase, with (2) scheduled as the immediately-following phase if the user
wants it.** Reasoning: this restructure already rewrites every `apps.*` import once; doing the umbrella
*in the same phase* would make one unreviewable diff, but doing it *in the very next phase* costs
almost nothing extra beyond `sim`/`configs` (the `apps.*` lines get touched twice either way, and that
second touch is a mechanical prefix). Sequencing the other way around (umbrella first, taxonomy second)
is also defensible and arguably cheaper by one pass — worth asking the user, because it is purely an
ordering preference. Reject (3): a facade that does not change the underlying names leaves every
hazard in place and adds a second import spelling.

---

<a id="ss3"></a>
## SS3. Area B — the `apps/<app_type>/<app_name>` taxonomy (F8-F11)

### SS3.1 Mapping what exists onto the four stated categories

The user's categories are **input**, **simulation**, **optimization**, **control**. Mapping the
existing code honestly:

| Existing thing | What it actually does | Natural bucket | Friction |
|---|---|---|---|
| `examples/worked_scenario.py` (`DEMO_SCENARIO`) | defines a vehicle + motor + site + weather | **input** | none — F3 moves it here |
| `tools/fetch_sounding.py` | downloads a real sounding into a case folder | **input** | none — F6 moves it here |
| `apps/common/study_vehicle.py` | the 1.5 kg / 75 mm study vehicle literal | **input** | it is a *shared* input (3 apps + their tests use it), so "input app" overstates it — but so does "common helper" |
| `run.py` (demo run + gravity/atmosphere comparison sweeps) | runs the simulator and compares model variants | **simulation** | today it is a root script, not an app. Promoting its body to `apps/simulation/baseline_run/` is what populates the otherwise-empty `simulation` bucket |
| `apps/cfd_conditions/select_conditions.py` | runs one trajectory, reduces it to a weighted (V, AoA, M, Re) condition set for CFD | **input**? **analysis**? | **real friction.** It *characterizes* a flight (analysis) in order to *produce an input* for an external CFD tool whose product (an aero table) is in turn a sim input. Either label is defensible; "optimization" is clearly wrong |
| `apps/motor_selection/{compare_motors, scenario_sweep, motors}` | sweeps N candidate motors, ranks by distance to target under constraints | **optimization** (discrete search over a candidate set) | mild: it is selection, not numerical optimization, but it *does* search a design space against an objective |
| `apps/airbrake_sizing/{solve_cda, targets}` | `scipy.optimize.brentq` on brake `C_dA` to hit a target apogee | **optimization** (genuine, solver-in-the-loop) | none. Also control-adjacent: it sizes the effector that `controllers/` actuates — but it sizes *hardware*, it is not flight software |
| `apps/weight_aero_tradeoff/{trade_surface, compare_configs, scenarios}` | builds a 2-D apogee surface, reports a local iso-apogee exchange rate; A/B-compares two configurations | **not optimization** | **real friction.** Nothing is optimized: no objective is minimized, no best point is chosen. It is sensitivity analysis + comparison |
| `apps/common/ensemble.py` | Monte-Carlo ensemble over dispersed inputs | **not optimization** | it is uncertainty analysis, and it is a *driver* (an app-shaped thing), not a helper — yet it lives in `common/` |
| `apps/common/{artifacts, flight_stats}` | output-dir helper; shared ascent-window reduction | none of the four | genuinely shared infrastructure |
| `controllers/{__init__, laws, estimator}` | flight software: estimator + sampled airbrake laws | **control** | the only occupant; currently outside `apps/` entirely (F11) |

Two of the four existing apps therefore do **not** fit "optimization", and the "simulation" bucket is
empty unless `run.py`'s body is promoted into it.

<a id="f8"></a>
### F8 — The bucket set

**Purpose:** the first path component of `apps/<app_type>/<app_name>/` — a classification a reader can
apply to a new app without guessing.

| | (a) exactly the four stated buckets | (b) **the four + `analysis/`** (recommended) | (c) four, with `optimization/` renamed `design/` | (d) no type layer: flat `apps/<app_name>/` with a documented `APP_TYPE` constant |
|---|---|---|---|---|
| Layout | `apps/{input, simulation, optimization, control}/` | `apps/{input, simulation, analysis, optimization, control}/` | `apps/{input, simulation, design, control}/` | `apps/<name>/` as today |
| Where the awkward three go | `cfd_conditions` → input (or simulation); `weight_aero_tradeoff` → optimization (wrong); `ensemble` → ? | `cfd_conditions`, `weight_aero_tradeoff`, `ensemble` → `analysis/`; `motor_selection`, `airbrake_sizing` → `optimization/` | all of sizing/selection/trade → `design/`; `ensemble` → ? | unchanged |
| Rule a future app can apply | fuzzy: "is a trade study an optimization?" | **crisp: does it *search* a design space against an objective/target (optimization) or *characterize* behaviour without choosing a best (analysis)?** | crisp but coarse — collapses "solve for the answer" and "show me the landscape" into one word | none needed, but nothing is grouped either |
| Resulting balance | 1 / 1 / 3 / 1 | 2 / 1 / 3 / 2 / 1 | 1 / 1 / 4 / 1 | 8 flat dirs |
| Pros | exactly what the user asked for | honours the user's four and adds the one word the existing code demands; `analysis/` is also the natural home for the next obvious app (stability/margin reports, dispersion summaries) | fewest buckets, no new vocabulary | zero taxonomy risk; shortest module paths |
| Cons | forces a wrong label on 2 of 4 existing apps, and mislabelling is contagious (the next trade study goes in the wrong box too) | 5 buckets instead of 4 — a deviation from the user's words, which must be explicitly agreed | "design" is vaguer than either word it replaces; also an unfamiliar term for `ensemble` | loses the thing the user explicitly asked for |
| Cost | ~3 h | ~3 h | ~3 h | ~0 |

**Recommendation: (b), "your four plus `analysis/`".** The distinction that matters operationally is
*search vs. characterize*: an optimizer answers "what value should I pick", an analysis answers "how
does it behave / what does it cost". `weight_aero_tradeoff` and `cfd_conditions` and `ensemble` are all
on the characterize side; `motor_selection` and `airbrake_sizing` are both on the search side (one
discrete, one continuous — both search). Forcing the first group into `optimization/` is the kind of
wrong label that propagates.

Proposed concrete layout under (b):

```
apps/
  __init__.py
  _shared/                  <- F10
    __init__.py  artifacts.py  flight_stats.py
  input/
    __init__.py
    demo_scenario.py        <- from examples/worked_scenario.py (F3)
    study_vehicle.py        <- from apps/common/study_vehicle.py (F10)
    sounding_fetch/         <- from tools/fetch_sounding.py (F6)
  simulation/
    baseline_run/           <- run.py's body (model-comparison sweeps)
  analysis/
    cfd_conditions/         <- select_conditions.py
    weight_aero_tradeoff/   <- trade_surface.py, compare_configs.py, scenarios.py
    ensemble/               <- from apps/common/ensemble.py (F10)
  optimization/
    motor_selection/        <- compare_motors.py, scenario_sweep.py, motors.py
    airbrake_sizing/        <- solve_cda.py, targets.py
  control/
    flight_software/        <- from controllers/ (F11)
```

Open sub-question worth asking the user explicitly: **is `cfd_conditions` input or analysis?** I put it
in `analysis/` because its computation is a reduction over a trajectory; its *product* happens to be a
CFD input. If the user thinks of apps by what they produce rather than what they compute,
`input/cfd_conditions/` is the right answer and I would not argue.

<a id="f9"></a>
### F9 — Nesting depth and per-app shape

**Purpose:** whether every app is a directory, and how long the dotted module paths get.

| | (a) uniform `apps/<type>/<name>/<module>.py` (recommended) | (b) one module per app where possible: `apps/<type>/<name>.py` | (c) `apps/<type>/<name>/` with a mandatory `__main__.py` front door |
|---|---|---|---|
| Example path | `apps.optimization.airbrake_sizing.solve_cda` (4 components) | `apps.input.study_vehicle` for single-module apps, directories only for multi-module ones | `python -m apps.optimization.airbrake_sizing` |
| Pros | one predictable shape; multi-module apps (3 of 4 have a separate study-input literal module) need a directory anyway | shorter paths for the 3 single-module items (`demo_scenario`, `study_vehicle`) | nicest invocation; `__main__.py` is the conventional "this is the entry point" marker |
| Cons | long dotted paths — mitigated entirely by F5's console scripts | two shapes to remember; a single-module app that grows must be converted | 6 new tiny files; `main(argv)` plumbing duplicated |
| Cost | ~3 h | ~3 h | +~1 h on top |

**Recommendation: (a) uniform directories for anything that is an app, plain modules for the two shared
input literals** (`apps/input/demo_scenario.py`, `apps/input/study_vehicle.py` — these are data, not
runnable apps). Add (c)'s `__main__.py` only if F5 picks the single-CLI option (c), where a uniform
entry-point shape starts paying for itself.

<a id="f10"></a>
### F10 — `apps/common/` fate

**Purpose:** `common/` is not an app type; it currently holds four unrelated things.

| | (a) keep `apps/common/` as a sixth sibling | (b) rename to `apps/_shared/` | (c) **split by what each thing actually is** (recommended) | (d) promote `flight_stats`/`ensemble` into `sim/` |
|---|---|---|---|---|
| `artifacts.py` (30 ln) | stays | stays | → `apps/_shared/artifacts.py` | → `sim/`? no (it is an apps-layer concern) |
| `flight_stats.py` (229 ln) | stays | stays | → `apps/_shared/flight_stats.py` | → `sim/flight_stats.py` |
| `ensemble.py` (393 ln) | stays | stays | → `apps/analysis/ensemble/` (it is a driver with no app consumers — only `tests/test_ensemble.py` imports it) | → `sim/` **contradicts an existing decision**: `sim/` is deliberately single-run, Monte Carlo lives in the apps layer (SS35.4.5) |
| `study_vehicle.py` (83 ln) | stays | stays | → `apps/input/study_vehicle.py` (it is an input literal, same kind as `motors.py`/`targets.py`/`scenarios.py`) | — |
| Pros | zero extra moves | one-word signal that this is not an app type | every file ends up in the box that describes it; `_shared/` shrinks to 2 small infrastructure modules | fewest top-level app dirs |
| Cons | reader must learn that one of the six `apps/*` dirs is not a type | same, plus a rename on top of the moves | 4 moves instead of 1, and ~8 import-line edits in apps + ~4 in tests | (d) for `ensemble` reverses a documented decision; for `flight_stats` it pushes an apps-layer reduction into the pinned physics package |
| Cost | 0 | ~0.3 h | ~1 h | ~1.5 h + a decision reversal |

**Recommendation: (c).** The two genuinely shared infrastructure modules keep a home with a name that
says "not an app" (`_shared`, leading underscore so it sorts and reads as private); the two that were
only in `common/` by accident of history move to the box that fits. Explicitly reject (d) for
`ensemble.py`: `sim/` staying single-run is a standing decision, and `ensemble` is exactly the kind of
churn-prone driver the apps layer exists for.

<a id="f11"></a>
### F11 — `controllers/` fate

**Purpose:** the user's "control apps" bucket exists; `controllers/` is the only candidate occupant,
but it sits outside `apps/` today with a documented architectural rule of its own.

What the rule actually says (`controllers/__init__.py:1-11`): *"Imports `sim/` and registers into
`sim.control` at import time; `sim/` never imports this package (rationale: controller experiments churn
constantly and must not touch the physics package or its pins)."* That is a statement about **import
direction**, and it is identical to the rule every app already obeys (`apps.* → sim.*`, never the
reverse). What is *different* about `controllers/` is the **data direction**: a registered law is called
*by* the integrator during a run, so control code executes inside `sim/`'s loop, whereas an app merely
consumes `sim/`'s output.

| | (a) **fold into `apps/control/flight_software/`** (recommended) | (b) keep top-level `controllers/`, installed as its own package, with the difference documented | (c) `apps/control/controllers/` (fold, minimal rename) | (d) move under `sim/` |
|---|---|---|---|---|
| Import name | `apps.control.flight_software` (`import apps.control.flight_software` is the new registration trigger) | `controllers` (unchanged) | `apps.control.controllers` | `sim.controllers` |
| One-way decoupling rule | **preserved verbatim** — still `apps → sim`, still `sim ↛ apps` | preserved | preserved | **destroyed**: churn-prone controller code inside the pinned physics package |
| Risk to physics pins | none (registration is a runtime import side effect, location-independent) | none | none | real |
| Files touched | 3 moved; 7 `sim/` docstring references; `tests/test_controllers.py`, `tests/test_control.py` (2 places); `sim/params.py:231`'s comment | 0 (plus `"controllers"` added to `packages`) | as (a) | as (a) + a layering reversal |
| Pros | matches the user's stated bucket; everything the user experiments with is under `apps/`; the name `flight_software` is what the docstring already calls it | publishes the architectural difference as a folder-level fact; zero churn | cheapest fold; keeps the familiar word | — |
| Cons | publishes one more generic top-level name? no — it *removes* one (`controllers`); the "flight software is not an app" nuance must survive in prose rather than in the tree | `controllers` is another generic installed top-level name (F7 hazard); the user asked for a control bucket and this leaves it empty | `apps.control.controllers.laws` is repetitive | rejected |
| Cost | ~1.5 h | ~0.2 h | ~1.3 h | ~1.5 h |

**Recommendation: (a).** The decoupling rule is about import direction and survives the move untouched;
the user explicitly wants a control bucket; and folding removes a generic published top-level name
rather than adding one. Two conditions I would attach to the move:

1. **Restate the rule in the new location's docstring**, including the data-direction nuance above —
   that `apps/control/*` is the one app type whose code runs *inside* the integrator's loop.
2. **Add a one-test import-direction guard** (new, cheap, generalises the rule the project currently
   enforces only by docstring): walk every module under `sim/` and assert none of them imports
   `apps`/`examples`. This is the safety net that makes the whole restructure safe to repeat, and it
   belongs in the first step of implementation, not the last (see [SS6](#ss6)).

If the user prefers (b), the reasoning to put in the tracker is "flight software is not a consumer of
the simulator, it is a participant in it" — a defensible position, just not the one the user's own
category list implies.

---

<a id="ss4"></a>
## SS4. Area C — `data/` → `examples/` (F12-F14)

### SS4.1 Why this is cheap in the library and not cheap in the tests

The library side is **one line**. Phase 2.18 Step 120 already funnelled all three loaders through
`sim.datafiles.resolve()`, so the only place that knows where the bundled tree lives is:

```python
# sim/datafiles.py:45
_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
```

Confirmed call sites (nothing else computes a bundled path): `sim/aero.py:371`,
`sim/motor_file.py:87, 257, 301`, `sim/soundings.py:216`. `sim/motor_file.py:80 _motors_path()` is a
thin wrapper over `resolve()` kept for two external callers
(`apps/motor_selection/scenario_sweep.py:130`, `tests/test_scenario_sweep.py`) — unaffected.

**No behaviour changes, and this is provable rather than hopeful:** `resolve()`'s three rules key off
the *shape* of the given string (absolute / contains a separator / bare name), never off the location
of the bundled tree. Every data string anywhere in this repo is a bare name — verified exhaustively:
`motor_curve` ∈ {`""`, `Cesaroni_2060K570-17A.eng`, `placeholder.csv`, `motor.csv`, `test_curve.csv`,
`synthetic_{small,large,medium_long,medium_punchy}.csv`}, `table` ∈ {`example.csv`, `example_v2.csv`,
test-written names}, `case` ∈ {`""`, `example`, `example_live`, `field_example`}. All take rule 3; rule
3's output changes its prefix and nothing else. The loaded bytes, the parsed records and therefore every
numeric pin are untouched.

The cost is in the **callers that compute their own paths** rather than going through `resolve()`:
13 test files and `tools/fetch_sounding.py:281`. Enumerated in [SS7](#ss7).

<a id="f12"></a>
### F12 — Target layout under `examples/`

**Purpose:** where exactly the 13 bundled files land.

| | (a) `examples/data/{motors,aero,soundings}/` (recommended) | (b) `examples/<topic>/data/...` (data next to the example that uses it) | (c) `examples/assets/` or `examples/datasets/` | (d) leave `data/` at the root |
|---|---|---|---|---|
| Layout | straight move, the three `kind` subfolders preserved | e.g. `examples/worked_scenario/data/motors/...` | rename of (a) | status quo |
| `resolve()` impact | `_BUNDLED` → `<repo>/examples/data`; **rules unchanged** | **breaks rule 3's shape**: `resolve(name, kind)` has exactly one bundled root per `kind`; per-topic trees need a second lookup dimension (or a search path) — a real semantic change to the load-bearing resolver | one-line, as (a) | none |
| Pros | one-line library change; zero semantic change; the `kind` convention that `Thrust.motor_curve`/`Aero.table`/`Soundings.case` comments document stays true | each example is self-contained and copyable as a unit | "assets" reads less like "the user's data" than `data` does | zero work |
| Cons | `examples/` now contains a tree that is *library data*, not an example script — slight name stretch | would require reopening the previous pivot's settled resolver semantics; the three kinds are shared by all examples anyway | gratuitous new vocabulary; the `data/<kind>/` phrasing in ~20 docstrings would all have to change wording, not just prefix | does not do what the user asked |
| Cost | ~2.5 h incl. tests | ~6 h + a resolver redesign | ~2.7 h | 0 |

**Recommendation: (a) `examples/data/{motors,aero,soundings}/`.** It is the only variant that keeps the
resolver's semantics and the documented `data/<kind>/` convention intact; the move becomes a pure
`git mv` + one constant + the caller list. Reject (b) specifically because it reopens settled ground
(the 3-rule resolver) for an ergonomic gain examples do not need — all three current example/demo paths
share the same three files.

<a id="f13"></a>
### F13 — The bundled-data anchor mechanism

**Purpose:** how `sim/` finds `examples/data/` once it is no longer `sim/`'s sibling.

| | (a) edit the constant: `<sim's parent>/examples/data` (recommended now) | (b) make `examples/` an installed package and use `importlib.resources.files("examples") / "data"` + `[tool.setuptools.package-data]` | (c) move the bundled tree *inside* the package (`sim/_data/`) |
|---|---|---|---|
| Change | `_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "data")` | `_BUNDLED` becomes a resources lookup; `examples/__init__.py` added; `package-data = {"examples" = ["data/**"]}` | `git mv data sim/_data`, `_BUNDLED = .../"_data"` |
| Works under `pip install -e .` | yes (the repo root is still `sim.__file__`'s grandparent) | yes | yes |
| Works under a real wheel (`pip install .`) | **no** — the same documented limitation as today (previous pivot F13(a)): `examples/` is outside every declared package, so it is not copied into `site-packages` | **yes** — this is the first time a wheel becomes possible | yes |
| Interaction | none | pulls F1 toward installing `examples/` (L1-ish) and F3 toward keeping the demo literal there | contradicts the user's explicit "data should go to examples" |
| Pros | one line; zero new concepts; preserves today's documented editable-only limitation unchanged | unlocks wheels; immune to "where is the repo root"; `importlib.resources` is the modern correct answer | wheel-ready and keeps the data inside the thing that reads it |
| Cons | still editable-only | `importlib.resources` paths are not plain `str` on every backend (needs `as_file`/`str()` care with the `glob` in `soundings.load_case`); couples the library's data lookup to the examples package's existence | ignores the user's request |
| Cost | ~0.2 h | ~1.5 h + a wheel-install smoke test | ~1 h |

**Recommendation: (a) now; (b) written down as the step that makes a wheel possible, to be taken when
(and only when) somebody other than the user installs this.** Note the pleasant side effect worth
telling the user: by moving `data/` *under* a directory that could become a package, their instinct
makes the eventual wheel **easier**, not harder — the previous pivot's F13 blocker was precisely "the
data sits at the repo root, outside every package".

<a id="f14"></a>
### F14 — How the 13 test files find the data tree

**Purpose:** 13 test files each hand-roll `os.path.join(os.path.dirname(__file__), "..", "data", ...)`,
mostly in order to *write* a temporary fixture into the bundled tree and delete it afterwards.

Files (verified): `test_aero.py` (3 sites), `test_aero_fb.py:66`, `test_aero_v2.py:20`,
`test_atmosphere.py:36`, `test_datafiles.py:18`, `test_motor_file.py:19`, `test_qa_phase217_m1.py:21`,
`test_report.py:18`, `test_scenario_sweep.py:21`, `test_soundings.py:29`,
`test_step114_review_fixes.py:23`, `test_thrust_curve.py:118`, `test_wind.py:27`.

| | (a) 13 mechanical edits | (b) **one shared `tests/datadir.py`** (recommended) | (c) a `conftest.py` fixture |
|---|---|---|---|
| Shape | each file's literal gains `"examples"` before `"data"` | new ~15-line module exporting `DATA`, `MOTORS_DIR`, `AERO_DIR`, `SOUNDINGS_DIR`; the 13 files import it | `@pytest.fixture def aero_dir()` etc., injected per test |
| Next move of the tree costs | 13 edits again | **1 edit** | 1 edit |
| Pros | no new module; smallest conceptual change | the same "one shared source" lesson the previous pivot learned with `DEMO_SCENARIO` (its F16); makes the directory a named thing instead of 13 string literals | idiomatic pytest; fixtures can clean up the temp files they create (several of these tests hand-roll `try/finally` removal) |
| Cons | 13 chances to typo a path; the knowledge stays duplicated | one more import in 13 files; `tests/datadir.py` is a non-test module in `tests/` (precedent exists: `tests/config_variants.py`) | touching 13 files' *function signatures*, not just a constant — a bigger diff in a pinned suite; and module-level constants (`_AERO_DIR`) cannot consume a fixture without restructuring |
| Cost | ~1.5 h | ~1.5 h | ~3 h |

**Recommendation: (b).** Same cost as (a) now and a tenth of the cost next time. Pin it with one
assertion (`datadir.AERO_DIR == os.path.join(datadir.DATA, "aero")` and `datafiles.resolve("x.csv",
"aero")` landing inside `datadir.AERO_DIR`) so the test-side and library-side notions of "the bundled
tree" cannot drift apart — that single assertion is the real safety net of this whole area.

### SS4.2 Specific items the brief asked about

- **`examples/worked_scenario.py`'s own `motor_curve` reference needs no change.** It is
  `motor_curve="Cesaroni_2060K570-17A.eng"` (line 125) — a bare name, rule 3, so it keeps resolving to
  the bundled tree at its new location automatically. There is an *option* to make it an explicit path
  (pedagogically more honest: "this is how you point at your own file"), but that would break the moment
  a user copies the file elsewhere, which is exactly what the file tells them to do. **Keep it bare**,
  and keep the `# REQ, filename under data/motors/` comment accurate by updating the wording to the new
  location.
- **No loader behaviour changes.** `motor_file.load()`'s `#designation` partition, the `.eng`/`.csv`
  extension dispatch, `aero._load_table()`'s rectangular-grid validation, `soundings.load_case()`'s
  `glob("*.csv")` over the case directory, and all six `lru_cache` layers key off the *resolved
  absolute path* (Step 120's own design) — the prefix changing is invisible to every one of them.
- **`tools/fetch_sounding.py:281`** computes `os.path.join(repo_root, "data", "soundings", case, fname)`
  itself. Under F6(b) it moves into `apps/input/sounding_fetch/` and should stop being repo-anchored
  altogether (F4's cwd rule + an explicit `--out-dir`), which is strictly better than re-pointing it at
  `examples/data`. If F6 keeps it in `tools/`, it is a one-line prefix edit.
- **External consumer impact (`fx27/simulation`): none from this area.** Its own data lives in its own
  folder and is referenced by path (rules 1-2), and bare-name resolution of *bundled* files keeps
  working. The only way this move could reach it is if that repo references a bundled file by bare name
  **and** pins the absolute string it resolves to — worth one grep when the orchestrator updates it.

---

<a id="ss5"></a>
## SS5. Area D — "archive unnecessary folders: /docs, /configs and others" (F15-F17)

### SS5.1 The stray root `docs/` — not a fork, just delete it

**Stated plainly, as the brief asks:** the top-level `docs/` directory is **disposable build output and
is not something to design around.** It is untracked (`git status` shows `?? docs/`), it contains
exactly one subdirectory `docs/latex/` holding only LaTeX by-products —
`main.aux` (15 K), `main.fdb_latexmk` (26 K), `main.fls` (30 K), `main.log` (37 K), `main.out` (6.5 K),
`main.pdf` (442 K), `main.synctex.gz` (415 K), `main.toc` (6 K), ~1 MB total — and **no `.tex` source at
all**. It is what a `latexmk`/`pdflatex` run with a stray `-output-directory ../docs/latex` (or a run
from the wrong cwd) leaves behind.

The real documentation tree is `dev/docs/` and the real LaTeX source is `dev/docs/latex/` (tracked;
`CLAUDE.md` rule: read-only for agents, no toolchain in this environment). `.gitignore` already ignores
`dev/docs/latex/*.{aux,fdb_latexmk,fls,log,out,pdf,synctex.gz,toc}` — the same patterns, one directory
over — which is further evidence that root `docs/` is the same artefacts emitted to the wrong place.

**No decision needed:** delete `docs/` (the orchestrator confirms with the user and does it directly;
nothing references it — grep over `*.py` and `dev/docs/*.md` finds no reference to a root `docs/` path).
Optional one-line hygiene the user may want: add `/docs/` to `.gitignore` so a repeat of the stray
`-output-directory` run never shows up as untracked noise again. Noting it, not forking on it.

**Related stale-artefact observation (free find, no action required):** `apps/airbrake_sizing/
__pycache__/solve_cda.cpython-**314**.pyc` and `apps/common/__pycache__/artifacts.cpython-314.pyc`
exist alongside the `cpython-312` ones — i.e. this tree was at some point imported by a CPython 3.14
interpreter, while the project pins 3.12. They are gitignored and harmless, but they are the same class
of thing as the already-documented "stale compiled artefact still carrying the old repo name
`rocket-trajectory`" note in `CLAUDE.md`. If the orchestrator is deleting `docs/` anyway, purging every
`__pycache__/` in the same pass is free and removes both oddities.

<a id="f15"></a>
### F15 — `configs/`: revisit the name/location, yes or no?

**First, the facts that bound this fork:**

- `configs/` is **not emptyable**. After Phase 2.18 it is exactly two files: `configs/schema.py`
  (28.6 K — `Config`, `Variant`, `Airframe`, `Sections`, `Motor`, `Rocket`, `LaunchSite`, `Weather`,
  `Scenario`, `assemble()`, `_pad_state()`, `_weight_from_pieces()`) and `configs/__init__.py`
  (28 lines: a re-export shim for those plus the ten `sim.params` groups). This is the load-bearing CORE
  surface — `apps/`, `examples/`, `tests/` and the external consumer all construct their inputs from it.
  "Archive `configs`" cannot mean "delete".
- **The registry layer the name used to describe is already archived** — `dev/archive/
  configs-registry-2026-10/` (D-137..D-142), git tag `pre-pivot-configs-registry`.
- **This exact question was already asked and answered "not now"** during the Phase 2.18 grilling
  ("смущает ли пользователя имя `configs`" → previous pivot F8, recommendation "Name-1, zero rename";
  decisions D-137..D-142). So this is a **revisit (y/n)**, not a fresh question.
- What *has* changed since that answer: the rename is now cheaper (the registry's own files are gone —
  **22 Python files** import `configs.*` today: 7 under `apps/`, 14 under `tests/`, 1 under `examples/`),
  and ~13 of those 22 are being edited anyway by Areas A-C.

**Two readings of the user's "/configs" remark, both worth putting to them:**

- **Reading 1 (likely): they mean the already-archived registry.** Their sentence lists `/docs` and
  `/configs` together as "unnecessary folders"; `/docs` is indeed pure garbage, and until Phase 2.18
  `configs/` *was* the 13-file registry tree they wanted gone. It is plausible they are remembering the
  pre-pivot `configs/` (or are thinking of `dev/archive/configs-registry-2026-10/`, which is the
  literal archive of it) and have not registered that only `schema.py` remains. If so, the honest answer
  is "already done last phase — here is what is left and why it must stay", and F15 closes as (a).
- **Reading 2: the *name* bothers them**, now that nothing in there configures anything. Then:

| | (a) no change — `configs/` stays (recommended default) | (b) `configs/schema.py` → `sim/schema.py`, retire the `configs` name | (c) rename `configs/` → something else (`model/`, `design/`, `vehicle/`) | (d) defer into the F7 umbrella (`rocket_physics/config.py`) |
|---|---|---|---|---|
| User script writes | `from configs import Motor, Rocket, assemble` | `from sim.schema import Motor, Rocket, assemble` (or re-export from `sim/__init__.py`) | `from model import ...` | `from rocket_physics import ...` |
| Files touched | 0 | 22 one-line import edits + 1 move + docstrings | 22 + 1 move | all of F7's ~100 |
| Removes the PyPI collision (`configs` v3.0.3) and the "user has a `configs/` folder" shadowing hazard | no | **yes** | yes (if the new name is distinctive — `model`/`design` are *not*) | yes |
| Honest-name quality | poor: nothing is configured; it is the input *schema* | good | depends on the word; all the obvious ones are as generic as `configs` | best |
| Risk | none | low (mechanical; `schema.py` imports only `sim.*`, so no cycle is created by moving it into `sim/`); full-suite gate catches a typo | same | needs its own phase |
| Cost | 0 | ~2-3 h | ~2-3 h | ~6-10 h |

**Recommendation: (a) stands, *unless* the user confirms Reading 2 — in which case (b), and do it in
this phase.** Rationale for the conditional: the previous phase already weighed this and chose no-rename
for good reasons that still hold; but if the name genuinely bothers them, (b) is the cheapest it will
ever be and it is the one option that also removes a real collision/shadowing hazard (F7). Do **not**
pick (c): swapping one generic name for another generic name pays the full cost for none of the benefit.
If F7's umbrella is adopted, (a) now and (d) later is strictly better than (b) then (d).

<a id="f16"></a>
### F16 — `dev/archive/configs-registry-2026-10/` fate

**Purpose:** the Phase 2.18 archive is one phase old; the user is now asking to archive more things, so
its own lifetime is a fair question.

| | (a) keep as is (recommended) | (b) delete it — the git tag `pre-pivot-configs-registry` is the real archive | (c) prune to the 4 instance modules, drop the 5 registry `__init__.py` |
|---|---|---|---|
| Pros | still readable in place while the user is building their own scenarios; `examples/worked_scenario.py`'s docstring (lines 23-39) **cites those five files by path** as the provenance of its numbers | a clean tree; the tag is a genuine safety net | keeps the valuable half (the numbers) and drops the dead machinery |
| Cons | ~55 K of dead text that `Grep` keeps hitting | makes the worked example's provenance citations dangle; resurrection becomes `git show <tag>:...` | still needs the citation lines rewritten |
| Cost | 0 | ~0.2 h + rewriting ~8 docstring lines in `examples/worked_scenario.py` | ~0.3 h + same rewrite |

**Recommendation: (a) for now.** It costs nothing but `Grep` discipline (already a project habit), and
it is still actively cited by the worked example. Revisit when the user has finished mining the old demo
numbers — at which point (b) plus a docstring rewrite is the right cleanup, and the tag makes it safe.

<a id="f17"></a>
### F17 — Remaining top-level inventory: anything else stale or unclear?

A full pass over every top-level entry, so the answer to "and others" is complete rather than
anecdotal. Only the first row is a genuine fork; the rest are verdicts offered for confirmation.

| Entry | Verdict | Note |
|---|---|---|
| `tools/` | **fork, resolved in F6**: becomes `apps/input/sounding_fetch/` (recommended) or stays | if it empties, delete the directory and update the `CLAUDE.md` profile row (orchestrator) |
| `output/` | keep, gitignored | F4 changes *where* it gets created (cwd-relative); the repo's own `output/` keeps being used when running from the repo root |
| `temp/` | leave alone | gitignored scratch; holds the user's MATLAB prototypes (`AB_01.m` etc., cited by `apps/airbrake_sizing`'s docstring as the precedent for that app) **and** this session's packaging mock `temp/pkgmock/` (deletable, see SS9) |
| `temporary/` | **out of scope by project convention** | not read, not touched, not recommended about |
| `.claude/` | keep | agent kit |
| `dev/` | untouched by this pivot | tracker files are orchestrator-owned; `dev/docs/*.md` get the usual index/log/tag update |
| `requirements.txt` | keep (4 lines) | redundant with `pyproject.toml` for runtime deps (previous pivot F14 chose `[project.optional-dependencies] dev`); not worth reopening here |
| `data/` | moves (F12) | after the move the root `data/` directory must be **gone**, not left empty — an empty leftover is how a half-move hides |
| `docs/` | delete, not a fork (SS5.1) | untracked LaTeX build output |
| `examples/` | stays, role changes (F1/F3/F12) | becomes "runnable examples + the bundled data tree" |
| `controllers/` | moves (F11) | |
| `run*.py` | stay (F6) | import lines change |

---

<a id="ss6"></a>
## SS6. Recommended ordered step sequence, with safety nets

Ordering principle: **fix the two external-cwd bug classes and the backwards dependency *before* moving
any file**, so that the big move step is pure motion against a green suite. Every step ends with the
full suite (`python -m pytest -q`, background, ~220-390 s) and a check that no numeric pin moved.

| # | Step | Touches | Safety net | `parallel_safe` |
|---|---|---|---|---|
| **1** | **Import-direction guard + packaging-boundary test.** New test that (i) no module under `sim/` imports `apps`/`examples`/`controllers`, (ii) the declared `packages` list in `pyproject.toml` matches the set of directories that are supposed to be installed. Pure addition, no production change. | 1 new test file | *is* the net for every later step; it fails loudly if a later move inverts a layer | yes |
| **2** | **Add `__init__.py` to `apps/` and each app package** (F2b). Behaviour-neutral: `python -m apps.X.Y` and all 12 app-importing tests keep working. | 6-13 empty files | full suite; plus one test asserting `apps.__file__ is not None` (i.e. it is a regular package, not a namespace portion) | yes (disjoint from 1) |
| **3** | **Cwd-anchor the artifact output** (F4b): `apps/_shared`-to-be `artifacts.py` grows `output_dir()`; `cfd_conditions`'s `_OUTPUT_DIR` folds into it; `--out-dir` added to the 4 apps that lack it. | `apps/common/artifacts.py`, 5 app modules, their tests | tests use `tmp_path`; one test pinning "run from a different cwd → writes there, not into the repo" (the regression this exists to prevent) | no (shares files with 5) |
| **4** | **Move the demo scenario into the package** (F3b): `examples/worked_scenario.py` → `apps/input/demo_scenario.py` (comments verbatim), `examples/worked_scenario.py` becomes the thin runner; repoint 3 apps + `run.py` + ~10 tests. | ~15 files | **bridge test** (the Step-122 pattern, delete it at the end of the step): assert the new module's `DEMO_SCENARIO.config.params` and `.s0` are field-for-field equal to the old import path's, while both still resolve. This is the one step that could silently move a pin | no |
| **5** | **`data/` → `examples/data/`** (F12a/F13a/F14b): `git mv`, `_BUNDLED` one-liner, new `tests/datadir.py`, 13 test files repointed, `tools/fetch_sounding.py` path. | ~17 files | pin `datafiles.resolve("Cesaroni_2060K570-17A.eng","motors")` to the new absolute path **and** assert the old root `data/` no longer exists (prevents a half-move); the `datadir`↔`datafiles` consistency assertion from F14 | no |
| **6** | **The taxonomy move** (F8b/F9a/F10c/F11a/F6b): one commit of pure `git mv` + import rewrites — `apps/<type>/<name>/`, `controllers/` → `apps/control/flight_software/`, `apps/common/` split, `tools/fetch_sounding.py` → `apps/input/sounding_fetch/`, `run.py`'s body → `apps/simulation/baseline_run/`. | ~13 app modules, 3 controller files, 5 runners, ~20 test files | **before the move**: add a test that imports every app module by dotted name from an explicit list (so a module orphaned by the move fails loudly instead of silently never being imported again). Keep no back-compat shims — clean break, one commit, full suite as the gate | no |
| **7** | **`pyproject.toml`**: `packages` list updated to the new tree, `[project.scripts]` added (F5b), boundary test updated. Re-run `pip install -e .` (entry points are install-time). | 1 file + 1 test | the Step-1 boundary test now asserts the real list; plus a from-an-external-cwd smoke test of one app | no |
| **8** | **Cleanup + docs**: delete the stray root `docs/`, purge `__pycache__`, update `README.md`, `CLAUDE.md`'s profile table (orchestrator), `dev/docs/{index,log,tag}.md` (documentation agent), and the external consumer `fx27/simulation`. | docs only | — | no |
| **9** | *(optional, separate phase)* **F7(2) umbrella rename** to `rocket_physics.*`, and/or F15(b) `configs/` retirement, and/or F13(b) wheel-capable `package-data`. | ~100 files | own phase, own full-suite gate, own review pass | no |

Steps 1 and 2 are mutually `parallel_safe` (disjoint files). Everything from 3 onward is sequential —
steps 3-7 all touch overlapping sets of app modules and test files, and the project's one-step-one-commit
discipline wants each of them reviewable against its own ticket.

**Where a bridge test is genuinely warranted** (the pattern the registry→plain-class migration used):
only steps **4** and **5**. Step 4 relocates the literals that ~10 numeric pins are computed from — the
same risk profile as the previous pivot's step 6, and the same mitigation (field-by-field equality while
both sides exist, then delete the bridge). Step 5 relocates the bytes those pins are computed *over*;
its bridge is cheaper (one resolved-path assertion plus "the old directory is gone"), because the loader
behaviour is provably unchanged (SS4.1). Steps 2, 6 and 7 are import-graph changes that either work or
raise `ImportError` — they need coverage (the enumerated-import test in step 6) but not an equality
bridge.

**What explicitly must not move in any step:** `sim/`'s module set and every numeric pin; `configs/schema.py`'s
contents (F15 pending); the three `resolve()` rules; `assemble()`'s pinned keyword set.

---

<a id="ss7"></a>
## SS7. What breaks / what needs updating — file by file

Assuming the recommended option on every fork (L2 + F2b + F3b + F4b + F5b + F6b + F8b + F9a + F10c +
F11a + F12a + F13a + F14b + F15a + F16a).

### SS7.1 `sim/` — one functional line, the rest is docstring honesty

| File | Change | Kind |
|---|---|---|
| `sim/datafiles.py:45` | `_BUNDLED` gains `"examples"` | **functional** (step 5) |
| `sim/datafiles.py` docstring (ll. 1-41) | "`data/<kind>/`" → "`examples/data/<kind>/`" in 4 places | doc |
| `sim/aero.py:41,70,363,669` | `data/aero/...` → `examples/data/aero/...` | doc |
| `sim/motor_file.py:248,252,257,297,301` + `_motors_path` docstring (ll. 80-87) | path wording; the `scenario_sweep.py` caller reference moves to its new dotted path | doc |
| `sim/soundings.py:19,204,209` | path wording | doc |
| `sim/thrust_curve.py:8` | path wording | doc |
| `sim/params.py:64,98,172` | the three field comments "file under `data/motors|aero/`", "case folder under `data/soundings/`" | doc |
| `sim/control.py:78,440,442`, `sim/params.py:231`, `sim/roll.py:13`, `sim/sensors.py:2,16,18,74` | "`controllers/`" → "`apps/control/flight_software/`" (7 references) | doc |

No `sim/` module imports `apps`, `examples` or `controllers` today, and step 1's guard test keeps it
that way. **Zero numeric pins live in `sim/`'s own files.**

### SS7.2 `apps/` — every module moves; 6 modules change code

| File | New location (F8b) | Code change beyond the move |
|---|---|---|
| `apps/common/artifacts.py` | `apps/_shared/artifacts.py` | **yes** — `OUTPUT_DIR` constant → cwd-anchored `output_dir()` (F4) |
| `apps/common/flight_stats.py` | `apps/_shared/flight_stats.py` | import lines only |
| `apps/common/ensemble.py` | `apps/analysis/ensemble/ensemble.py` (or `.../ensemble/__init__.py`) | import lines; re-check the `ProcessPoolExecutor` picklability docstring (SS1.4) |
| `apps/common/study_vehicle.py` | `apps/input/study_vehicle.py` | import lines |
| `apps/cfd_conditions/select_conditions.py` | `apps/analysis/cfd_conditions/select_conditions.py` | **yes** — `_OUTPUT_DIR` folds into `_shared` (F4); `from examples.worked_scenario import DEMO_SCENARIO` → `from apps.input.demo_scenario import ...` (F3) |
| `apps/weight_aero_tradeoff/{trade_surface,compare_configs,scenarios}.py` | `apps/analysis/weight_aero_tradeoff/...` | **yes** in 2 of 3 — `OUTPUT_DIR`/`ensure_dir` call sites (F4) |
| `apps/motor_selection/{compare_motors,scenario_sweep,motors}.py` | `apps/optimization/motor_selection/...` | **yes** in 2 of 3 — `OUTPUT_DIR` (F4), the `DEMO_SCENARIO` import (F3); `motor_file._motors_path` call at `scenario_sweep.py:130` keeps working unchanged |
| `apps/airbrake_sizing/{solve_cda,targets}.py` | `apps/optimization/airbrake_sizing/...` | **yes** in 1 of 2 — `OUTPUT_DIR` (F4), `DEMO_SCENARIO` import (F3) |
| *(new)* `apps/__init__.py` + one per app package | — | 6-13 empty files (F2b) |

### SS7.3 Moved-in from elsewhere

| From | To | Code change |
|---|---|---|
| `examples/worked_scenario.py` | `apps/input/demo_scenario.py` | keeps `DEMO_SCENARIO`, `rocket`, `motor`, `site`, `weather` and every `REQ|OPT` comment; drops the `__main__` block (which moves to the thin `examples/worked_scenario.py`); docstring rewritten (its "no `__init__.py`, run with `python -m examples.worked_scenario`" paragraph, ll. 46-51, becomes false under F2b) |
| `controllers/{__init__,laws,estimator}.py` | `apps/control/flight_software/` | internal `from controllers import X` → `from apps.control.flight_software import X`; the `register_sampled_law` side effect is unchanged; docstring restates the one-way rule (F11 condition 1) |
| `tools/fetch_sounding.py` | `apps/input/sounding_fetch/fetch_sounding.py` | line 281's repo-anchored write path → cwd-anchored + `--out-dir` (F4); network-isolation caveat in the docstring (F6) |
| `run.py`'s body (ll. 40-99) | `apps/simulation/baseline_run/baseline_run.py` | `run.py` becomes the 6th thin wrapper — **but** `tests/test_configs.py:221` asserts `"DEMO_SCENARIO" in <run.py source>`, which must move with the body |
| `data/**` (13 files) | `examples/data/**` | pure `git mv` |

### SS7.4 Root scripts and packaging

| File | Change |
|---|---|
| `run.py` | import `apps.simulation.baseline_run` (+ see the source-text test above) |
| `run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py` | one import line each (`apps.optimization.*` / `apps.analysis.*`); `run_trade.py` has two (both modes) |
| `pyproject.toml` | `packages` → `["sim","configs","apps","apps._shared","apps.input","apps.input.sounding_fetch","apps.simulation","apps.simulation.baseline_run","apps.analysis","apps.analysis.cfd_conditions","apps.analysis.weight_aero_tradeoff","apps.analysis.ensemble","apps.optimization","apps.optimization.motor_selection","apps.optimization.airbrake_sizing","apps.control","apps.control.flight_software"]`, plus `[project.scripts]`. (With F2b's `__init__.py` files in place, this list can later be replaced by a plain `[tool.setuptools.packages.find] include = ["sim*","configs*","apps*"]` — **no** `namespaces = true` needed, which is the variant that avoids the data-dir over-discovery measured in SS9.) |
| `.gitignore` | optional `/docs/` line (SS5.1) |
| `requirements.txt` | unchanged |

### SS7.5 `tests/` — 49 files; ~28 touched, all mechanically

| Group | Files | Change |
|---|---|---|
| **Data paths** (13) | `test_aero.py` (3 sites), `test_aero_fb.py`, `test_aero_v2.py`, `test_atmosphere.py`, `test_datafiles.py`, `test_motor_file.py`, `test_qa_phase217_m1.py`, `test_report.py`, `test_scenario_sweep.py`, `test_soundings.py`, `test_step114_review_fixes.py`, `test_thrust_curve.py`, `test_wind.py` | import the new `tests/datadir.py` instead of hand-rolling `../data/...` (F14b). `test_datafiles.py` additionally pins the resolver's bundled root, so its `_DATA` is a real assertion, not a convenience |
| **`apps.*` imports** (12) | `config_variants.py`, `test_airbrake_sizing.py`, `test_apps_common.py`, `test_configs.py`, `test_demo_physics.py`, `test_ensemble.py`, `test_mach_warning.py`, `test_motor_selection.py`, `test_qa_phase217_m1.py`, `test_scenario_sweep.py`, `test_step114_review_fixes.py`, `test_weight_aero_tradeoff.py` | dotted paths follow the taxonomy. `test_apps_common.py`'s *name* becomes stale (it tests `apps/_shared` + the split-out modules) — rename or split |
| **`examples.worked_scenario` imports** (14) | the 12 above minus `test_apps_common.py`/`test_ensemble.py`/`config_variants.py`, plus `test_aero_fb.py`, `test_aero_oob.py`, `test_dynamics.py` (2 local imports), `test_motor_pieces.py`, `test_worked_scenario_example.py` | → `apps.input.demo_scenario`. `test_worked_scenario_example.py` additionally runs `python -m examples.worked_scenario` in a subprocess — keep it pointed at the thin runner (that is precisely what still needs smoke-testing) |
| **`controllers` name** (2 + 1 doc) | `test_controllers.py` (imports + docstring), `test_control.py:473-474, 675` (comment + the un-imported-law KeyError pin), `test_sensors.py:118` (docstring) | dotted path; the KeyError pin's *behaviour* is unaffected (it asserts an unregistered name, not a module location) |
| **Source-text assertions** (1) | `test_configs.py:221,228` reads `run.py` and `apps/cfd_conditions/select_conditions.py` **by path** | both paths change (F3/F8) — this test is the one that fails in a way that looks like a real failure rather than an import error, so it is worth touching in the same commit as the move |
| **Output paths** | any test asserting a written artifact path | must switch to `tmp_path`/`monkeypatch.chdir` (F4). `output/` is gitignored, so grep rather than trust `git status` |
| **New** | `tests/datadir.py`, the import-direction guard, the packaging-boundary test, the enumerate-every-app-module test, and (temporarily) the two bridge tests of steps 4-5 | ~5 files |
| **Untouched** | the ~21 pure-physics files (`test_integrate.py`, `test_mass.py`, `test_gravity.py`, `test_config_pieces.py`, …) | — |

### SS7.6 Documentation and outside-the-repo

| Item | Owner | Change |
|---|---|---|
| `README.md` | readme-keeper | the "what ships in the package" section, the invocation list (console scripts), the data path |
| `CLAUDE.md` «Профиль проекта» | orchestrator | the code-layout row (`apps/`, `controllers/`, `tools/`, `data/` all change), the run commands, the test commands are unchanged |
| `dev/docs/{index,log,tag}.md` | documentation | this document + the architecture doc for the phase |
| `dev/docs/architecture.md`, `roadmap.md` | architect (next round) | the taxonomy and the new boundary belong in the cross-cutting reference |
| `dev/docs/architecture-3x-*.md` (historical) | nobody | **do not retro-edit**; they are the record of what was decided then |
| `dev/docs/latex/` | **never edit** (project rule) | its prose mentions `configs/`/`data/` paths; leave it, flag to the user that the report's path references will drift |
| `D:\Projects - Ongoing\fx27\simulation` (external consumer, not this repo) | orchestrator, after step 7 | nothing breaks from steps 1-6 (it cannot import `apps` today and its data is path-referenced); step 7 *adds* `apps.*` and the console scripts; a later F7 umbrella **would** break its imports |

---

<a id="ss8"></a>
## SS8. Fork summary table + questions to stress-test with the user

Each fork is separately answerable and carries a recommendation. **None is decided by this document.**
Numbering is local to this document (`F1`-`F17`, independent of the previous pivot's `F1`-`F16`). The
decision log in `dev/status.json` continues from **D-142**, so adopted answers become D-143 onward.

| # | Fork | Options | Recommendation | Cost of getting it wrong |
|---|---|---|---|---|
| **F1** | What is installed | L1 install everything runnable / **L2 library + apps, `examples/` stays out** / L3 umbrella | **L2** — the only layout where the library does not import its own examples folder | medium: L1 is reversible but institutionalises a backwards dependency |
| **F2** | Declaration mechanism + package kind | explicit list w/ namespace dirs / **explicit list + `__init__.py` everywhere** / `find` + `namespaces=true` | **(b)** — namespace *merging* with a same-named folder in the user's project is the worst failure mode here (silent half-import) | **high** — the failure is silent |
| **F3** | Home of the shared demo scenario | install `examples/` / **move the literal to `apps/input/demo_scenario.py`** / duplicate + bridge test / per-app copies | **(b)** — one literal, right dependency direction, comments preserved | medium: duplication is how pins drift (previous pivot's own lesson) |
| **F4** | Artifact output anchoring | status quo repo-anchored / **cwd default + `--out-dir`** / env var / mandatory flag | **(b)** — mirrors `datafiles.resolve` rule 2; behaviour-identical when run from the repo root | **high** — status quo means installed apps write into the library |
| **F5** | Invocation | keep `run*.py` only / **add `[project.scripts]`** / single `rp` CLI / both | **(b) now, (c) later** — 5 lines of metadata for the most visible benefit of installing `apps/` | low |
| **F6** | `tests/`, `tools/`, `run*.py` classification | per-item | **`tests/` unchanged (not installed); `tools/fetch_sounding.py` → `apps/input/sounding_fetch/`; `run*.py` stay** | low-medium: moving the network tool needs the "never imported by `sim/`" invariant restated |
| **F7** | Published import names | **flat `sim/configs/apps` now** / `rocket_physics` umbrella / thin facade | **flat now, umbrella as the *next* phase if wanted** — but ask: doing the umbrella *first* saves one pass over the `apps.*` imports | medium — renames get more expensive, and generic names are a live shadowing hazard |
| **F8** | Bucket set | the stated four / **four + `analysis/`** / four with `design/` / no type layer | **(b)** — 2 of 4 existing apps characterize rather than search; forcing them into `optimization/` mislabels every future trade study too | medium: a wrong taxonomy is contagious |
| **F9** | Nesting / per-app shape | **uniform `apps/<type>/<name>/`** / module-per-app where possible / mandatory `__main__.py` | **(a)**, with plain modules for the 2 shared input literals; long dotted paths are neutralised by F5 | low |
| **F10** | `apps/common/` | keep / rename `_shared/` / **split by what each file is** / promote into `sim/` | **(c)**: `_shared/{artifacts,flight_stats}`, `study_vehicle` → `input/`, `ensemble` → `analysis/`. Reject promoting `ensemble` into `sim/` — reverses a standing decision | low |
| **F11** | `controllers/` | **fold into `apps/control/flight_software/`** / stay top-level / `apps/control/controllers/` / under `sim/` | **(a)** — the one-way rule is about import direction and survives verbatim; registration is a runtime side effect, so pins cannot move. Attach: restate the rule + add the import-direction guard test | low-medium (zero pin risk; prose risk if the rule is not restated) |
| **F12** | Data layout under `examples/` | **`examples/data/{motors,aero,soundings}/`** / per-example data / `assets/` / stay | **(a)** — the only variant that leaves the 3-rule resolver's semantics untouched | medium: (b) reopens settled resolver ground |
| **F13** | Bundled-data anchor | **edit `_BUNDLED`** / `importlib.resources` + `package-data` / move inside `sim/` | **(a) now**, (b) as the step that first makes a real wheel possible (the user's instinct helps here) | low |
| **F14** | Test-side data paths | 13 edits / **one `tests/datadir.py`** / conftest fixtures | **(b)** — same cost now, 1/13 the cost next time; pin it against `datafiles.resolve` | low |
| **F15** | `configs/` revisit | **(a) no change** / `sim/schema.py` / another generic rename / defer to the umbrella | **(a) stands unless the user confirms the name bothers them → then (b), in this phase.** Already asked and answered "no" in Phase 2.18; cheaper now (22 files). Note they may actually mean the already-archived registry | medium |
| **F16** | `dev/archive/configs-registry-2026-10/` | **keep** / delete (tag is the archive) / prune | **(a)** — still cited by the worked example's provenance docstring; delete later, with that docstring rewritten | very low |
| **F17** | Other top-level entries | per-item (SS5.1, F17 table) | **root `docs/` → delete (not a fork); `temp`/`temporary` untouched; `output/` keeps working; `tools/` per F6** | very low |

### SS8.1 Questions to stress-test with the user (beyond picking an option)

1. **Is `cfd_conditions` an input app or an analysis app?** It computes a reduction over a trajectory
   (analysis) whose product is an input to an external CFD tool (input). The answer reveals whether the
   user classifies apps by *what they compute* or *what they produce* — which decides where the next
   app goes too, not just this one.
2. **Order of the umbrella rename vs. this restructure (F7).** Doing `rocket_physics.*` *before* the
   taxonomy move touches the `apps.*` import lines once instead of twice. Doing it after keeps each diff
   smaller. Pure sequencing preference; worth 30 seconds of their opinion because it is worth ~1-2 h.
3. **Did "/configs" mean `configs/schema.py`, or the registry that is already archived (F15)?** The
   whole fork hinges on this, and the honest default answer is "already done last phase".
4. **Does the user want `apps/` to be *stable public API* or *their own churn space*?** Installing it
   publishes it: a 1.5 kg/75 mm study vehicle, a target-apogee list and a trade box become importable
   library content. If these are expected to keep churning (they have, repeatedly), the package version
   number starts meaning less — worth agreeing now whether `apps.*` carries any stability promise.
5. **Should `examples/` eventually hold more than one example?** `examples/` after this pivot = one thin
   runner + the bundled data tree. If the plan is several worked examples (a sounding-driven flight, an
   airbrake flight, an external-data flight), `examples/` earns its name; if not, consider whether the
   bundled data would rather live in `sim/_data/` (F13c) and `examples/` stay a single tutorial file.
6. **Is `run.py`'s model-comparison sweep really an app** (`apps/simulation/baseline_run/`), or is it a
   demo that belongs in `examples/`? This is the only thing that would populate the `simulation/`
   bucket; if the user would rather `simulation/` hold future things (a batch runner, a trajectory
   replayer), leaving `run.py` alone and accepting an initially-empty bucket is also fine.
7. **How much invocation churn is acceptable?** After F8, `python -m apps.airbrake_sizing.solve_cda`
   becomes `python -m apps.optimization.airbrake_sizing.solve_cda` (and `rp-airbrake` under F5). The
   `run*.py` wrappers hide this, but any muscle memory and any note outside the repo breaks.

---

<a id="ss9"></a>
## SS9. Verified facts (grounding)

Everything below was measured in this session, not recalled, so later rounds and the implementing
developer do not re-derive it.

### SS9.1 Packaging facts — measured on a mock of this repo's exact layout

Built `temp/pkgmock/` (a flat-layout repo with `sim/`, `configs/`, `controllers/` as regular packages
and `apps/`, `apps/common/`, `apps/motor_selection/` as `__init__.py`-less namespace dirs), installed it
editable into its own venv with setuptools 84.2.1, and imported from an unrelated cwd.

| # | Fact | How verified |
|---|---|---|
| 1 | `[tool.setuptools] packages = ["sim","configs","apps","apps.common","apps.motor_selection","controllers"]` installs cleanly **even though `apps/` has no `__init__.py`**; from an external cwd `import apps` succeeds (as a namespace package, `__file__ is None`) and `apps.common.artifacts` / `apps.motor_selection.compare` resolve to the **live repo source** | `pip install -e .` then `importlib.import_module` from `temp/pkgmock/outside/` |
| 2 | Listing only `"apps"` (without the subpackages) **also** makes `apps.common.artifacts` importable under an *editable* install — because the editable finder maps the top-level name to the directory. This is an editable-install artefact: a real wheel copies only the listed packages, so the explicit list must still enumerate subpackages (or use `find`) to be wheel-correct | same mock, second pyproject variant |
| 3 | `[tool.setuptools.packages.find] include=["sim*","configs*","apps*","controllers*"]` **with `namespaces = true`** discovers `['apps','apps.common','apps.motor_selection','apps.motor_selection.data_tables','configs','controllers','sim']` — i.e. it also turns a plain **data** directory into a declared package (it does correctly skip `__pycache__`). Without `namespaces = true` the same include list discovers only `['configs','controllers','sim']` — **`apps` is silently dropped** | `setuptools.discovery.PEP420PackageFinder.find` vs `PackageFinder.find`, after planting `apps/motor_selection/data_tables/t.csv` |
| 4 | Import precedence: a *regular* package (with `__init__.py`) found later on `sys.path` wins over a same-named directory earlier on the path; two namespace *portions* with the same name **merge**. Hence the F2(b) recommendation — with generic published names (`apps`, `examples`, `configs`), a same-named folder in the user's own working directory is a realistic hazard, and the namespace variant fails silently rather than loudly | CPython `FileFinder`/PEP 420 semantics; (2)'s measurement confirms namespace portions resolve at all |
| 5 | `import tests` still raises `ModuleNotFoundError` from an external cwd with `apps` installed — the CORE/REFERENCE boundary continues to be exactly the `packages` list | same mock |
| 6 | `setuptools` is **not** installed in the project interpreter (global CPython 3.12.10, not a venv); build isolation fetches it (84.2.1 at time of writing). Unchanged from the previous pivot | `python -c "import setuptools"` → `ModuleNotFoundError` |
| 7 | The mock lives at `temp/pkgmock/` (gitignored; includes a ~50 MB venv). **Safe to delete** — every fact above is recorded here | — |

### SS9.2 Codebase facts

| Fact | How verified |
|---|---|
| `controllers/` **is tracked now** (3 files: `__init__.py`, `laws.py`, `estimator.py`) — this corrects the previous pivot document's SS7.1 "`controllers/` does not exist in git", which was true at the time and stopped being true with the Phase 2.17 merge | `git ls-files controllers` |
| `apps/` and `examples/` contain **no `__init__.py` at any level** | `ls apps/*/__init__.py` → no such file |
| **4 modules import `examples.worked_scenario`**: `apps/cfd_conditions/select_conditions.py:89`, `apps/motor_selection/scenario_sweep.py:54`, `apps/airbrake_sizing/solve_cda.py:86`, `run.py:34`; **14 test files** do too | `grep -rn "worked_scenario\|DEMO_SCENARIO"` |
| Repo-anchored write paths in the apps layer: `apps/common/artifacts.py:21` (`Path(__file__).parents[2]/"output"`), `apps/cfd_conditions/select_conditions.py:94`, `tools/fetch_sounding.py:281`. `apps/motor_selection/scenario_sweep.py:442` already honours an `--out-dir` | `grep -rn "parents\[\|__file__\|OUTPUT_DIR"` over `apps/`, `tools/`, `run*.py` |
| Third-party imports across `apps/`+`controllers/`+`examples/`+`run*.py`: **only** numpy, scipy (`interpolate.RegularGridInterpolator`, `optimize.brentq`), matplotlib.pyplot — all already in `[project.dependencies]`. **No new dependency needed** | exhaustive `grep` of all `^import`/`^from` lines, deduplicated |
| The bundled-data anchor is a single constant, `sim/datafiles.py:45`; all five resolver call sites go through `datafiles.resolve` (`aero.py:371`, `motor_file.py:87,257,301`, `soundings.py:216`) | `grep -n "datafiles.resolve" sim/*.py` |
| **Every bundled-data string in the repo is a bare name** (no separator), so all of them take `resolve()` rule 3 and the move changes only the prefix: `motor_curve` ∈ {`""`, `Cesaroni_2060K570-17A.eng`, `placeholder.csv`, `motor.csv`, `test_curve.csv`, `synthetic_small.csv`, `synthetic_large.csv`, `synthetic_medium_long.csv`, `synthetic_medium_punchy.csv`} | `grep -rho 'motor_curve="[^"]*"' \| sort -u`; a separator-matching grep over `motor_curve=`/`table=`/`case=` returns only one hit, which is a comment |
| 13 test files compute their own `../data/...` paths; `tools/fetch_sounding.py:281` is the only non-test one | `grep -rn '"data"' tests/ tools/` |
| `configs/` is 2 files (`__init__.py` 28 lines, `schema.py` 28.6 K); **22 Python files** import `configs.*` (7 in `apps/`, 14 in `tests/`, 1 in `examples/`) | `ls configs/`, `grep -rln "from configs\|import configs"` |
| `sim/` contains **zero** imports of `apps`, `examples` or `controllers` (7 docstring mentions of `controllers/` only) | `grep -rn "controllers" sim/` |
| `tests/` is 49 tracked files, 3.4 MB; `tests/__init__.py` exists and must (the documented `eventkit` top-level-`tests` collision) | `git ls-files tests \| wc -l`, `du -sh` |
| Root `docs/` is untracked and contains only `docs/latex/main.{aux,fdb_latexmk,fls,log,out,pdf,synctex.gz,toc}` — no `.tex` | `git status --porcelain`, `ls docs/latex/` |
| Stale `__pycache__` entries compiled by **CPython 3.14** exist under `apps/` while the project pins 3.12 | the `grep` output flagged `solve_cda.cpython-314.pyc`, `artifacts.cpython-314.pyc` |
| The external consumer `D:\Projects - Ongoing\fx27\simulation` exists and contains `README.md`, `data/`, `requirements.txt`, `scenario_template.py` (not part of this repo; listed only, not inspected further) | `ls` |

### SS9.3 Facts carried over from the previous pivot (not re-measured)

Still true and relied on above: the editable install resolves to live repo source; a bare
`pyproject.toml` fails on this flat layout ("Multiple top-level packages discovered"); a non-editable
wheel cannot see a repo-root `data/`; adding `pyproject.toml` does not change pytest's `rootdir`;
`configs` is a live PyPI distribution (v3.0.3); `assemble()` reads the motor file at composition time
via `_weight_from_pieces` → `motor_file.load`.

# Pivot: retire the `configs/` registry, ship `rocket-physics` as an installable package

## Кратко (RU)

- Документ — анализ развилок (НЕ решение, 16 развилок F1-F16 в SS6) для пивота: пользователь хочет (1) убрать конвенцию «файл-на-экземпляр + реестр» в `configs/*`, (2) собирать `Motor`/`Rocket`/… как обычные классы со своими числами в собственном скрипте, (3) ставить репозиторий как пакет и работать из чистой внешней папки, где лежат ЕГО файлы данных. GUI — вне скоупа.
- `configs/schema.py` (`Motor`, `Rocket`, `LaunchSite`, `Weather`, `Scenario`, `assemble()`) — уже ровно то, что просит пункт 2: зависит только от `sim.*`, на реестры не смотрит. Пункт 2 не надо реализовывать, надо снять слой сверху.
- **Главная находка (проверено запуском): абсолютные пути к файлам данных уже работают во всех трёх загрузчиках без правок кода** — `os.path.join` отбрасывает префикс, когда последний компонент абсолютный. Не работают два случая: путь без буквы диска (`/abs/x.eng` молча становится `D:/abs/x.eng`) и путь относительно cwd (уезжает в `data/` репозитория). То есть задача не «сделать», а «поддержать, задокументировать, покрыть тестами».
- Рекомендация по путям: **Опция 1** — новый `sim/datafiles.py` с 3 правилами (абсолютный → как дан; есть разделитель → относительно cwd; голое имя → встроенный `data/<kind>/`, как сегодня). Ни один существующий тест не меняется. Опция 2 (глобальный изменяемый data-root) отклонена: противоречит контракту «офлайн и детерминирован». Опция 3 (данные в памяти) — только для мотора и отдельным поздним шагом (это тот шов, который понадобится GUI).
- Упаковка: **Опция A** — `pyproject.toml` + `pip install -e .`. Проверено на макете репозитория: «пустой» `pyproject.toml` падает («Multiple top-level packages discovered in a flat-layout»), а с явным `packages = ["sim", "configs"]` всё ставится, импортируется из внешней папки, и `import apps`/`import tests` оттуда НЕдоступны — то есть этот список и есть граница пакета. `pytest`/`python run.py` не ломаются.
- Ставить **в venv внутри папки пользователя**, не в глобальный Python: `configs` — занятое имя на PyPI (v3.0.3), а проект уже один раз страдал от коллизии верхнего имени (`eventkit`/`tests`).
- Переименование в `rocket_physics.*` — **не сейчас** (~70 + ~32 файла); дешёвая середина `configs/schema.py` → `sim/schema.py` (~32 файла) как второй выбор.
- Архив реестров — папкой `dev/archive/configs-registry-2026-10/` плюс git-тег. `apps/*` и `run*.py` — не удалять и не архивировать: оставить на месте как референсные примеры, просто не включать в `packages`.
- Цена: ~25 файлов, ~11-15 ч, 5-7 шагов трекера. Числовые пины физики не двигаются; единственный риск — перенос ~10 пинов с `configs.get("demo")` на inline-`Scenario` (страхуется временным bridge-тестом).
- Поправка к вводным: `controllers/` в git не существует (пустая папка со старым `__pycache__`), законы управления — в `sim/control.py`.

---

## Table of contents

- [SS1. What is actually retired, kept, moved](#ss1)
- [SS2. Data file path resolution — the load-bearing fork](#ss2)
- [SS3. Packaging mechanism](#ss3)
- [SS4. What breaks, and roughly how big the fix is](#ss4)
- [SS5. Recommendation — one coherent proposal](#ss5)
- [SS6. Open forks for the grilling session](#ss6)
- [SS7. Verified facts (grounding)](#ss7)

---

<a id="ss1"></a>
## SS1. What is actually retired, kept, moved

### SS1.1 The three buckets

The pivot sorts every top-level thing in the repo into one of three buckets. The boundary being drawn
is **"is this part of the physics library, or is this somebody's input to / consumer of it?"**

| Bucket | Meaning | Contents |
|---|---|---|
| **CORE** | ships inside the installable package; the import surface an external script sees | `sim/` (26 modules), the dataclasses + `assemble()` of `configs/schema.py` |
| **REFERENCE** | stays in this repo, stays in git, stays runnable — but is *not* part of the installed import surface; the user copies from it | `apps/` (5 app packages), `run*.py` (5 scripts), `tools/`, `data/` (13 committed files), the 5 `_TEMPLATE_*.py` modules |
| **ARCHIVED** | leaves the live import path; reversible | the 5 registry `__init__.py` files, the 4 library-shipped instance modules, `configs/__init__.py`'s registry delegation |

### SS1.2 CORE — stays exactly as is

- **`sim/` — zero changes required by the pivot itself.** Verified: nothing under `sim/` or `tools/`
  imports `configs` at all (grep: no hits). The import DAG really is one-directional
  (`configs.schema` → `sim.*`), so retiring the registry cannot reach `sim/`. The only edits `sim/`
  needs are the three data-path ones in [SS2](#ss2) — a separate concern that happens to be a
  prerequisite for the same user goal.
- **`configs/schema.py` — kept whole, 0 structural changes.** Your reading in the brief is correct and
  I verified it line by line:
  - It defines `Config`, `Variant`, `Airframe`, `Sections`, `Motor`, `Rocket`, `LaunchSite`,
    `Weather`, `Scenario`, plus `assemble()`, `_pad_state()`, `_weight_from_pieces()`.
  - Its only imports are `dataclasses`, `math`, `typing`, and `sim.{mass, motor_file, params, state}`.
    **It has no dependency on any registry subpackage**, by explicit design (the module docstring
    states the rule: piece modules do `from configs.schema import X`, never `from configs import X`,
    specifically so `schema.py` never depends on `configs/__init__.py`).
  - `assemble()` takes a `Scenario` and returns a `Config`. No name lookup, no registry, no
    filesystem access except through `motor_file.load()` (see SS1.5 below).
  - So point 2 of the user's request ("classes like motor, rocket, etc. that just are inputted
    variables") **is already implemented**. The pivot does not build it; it removes the layer sitting
    on top of it.

Correction to the brief: **`controllers/` does not exist.** `git ls-files controllers` returns
nothing, and the directory on disk contains only a stale `__pycache__`. The control laws live in
`sim/control.py`. There is nothing to put in the package core under that name.

### SS1.3 ARCHIVED — the registry layer

Exactly 13 files, ~2 400 lines (of which ~1 100 lines are the 5 `_TEMPLATE_*` modules, which I argue
below should *not* be archived):

| File | Size | Action |
|---|---|---|
| `configs/rockets/__init__.py` | 1.8 K | archive |
| `configs/sites/__init__.py` | 1.7 K | archive |
| `configs/weather/__init__.py` | 2.0 K | archive |
| `configs/motors/__init__.py` | 2.1 K | archive |
| `configs/scenarios/__init__.py` | 1.8 K | archive |
| `configs/rockets/demo.py` | 5.0 K | archive (becomes a reference example — see SS1.4) |
| `configs/motors/cti_k570.py` | 1.4 K | archive (becomes a reference example) |
| `configs/sites/origin_msl.py` | 1.0 K | archive (becomes a reference example) |
| `configs/weather/isa_dry_calm.py` | 1.0 K | archive (becomes a reference example) |
| `configs/scenarios/demo.py` | 2.2 K | archive (becomes a reference example) |
| `configs/__init__.py` | 3.8 K | **edit, not archive** — see SS1.5 |
| `configs/{rockets,sites,weather,motors,scenarios}/_TEMPLATE_*.py` | ~43 K | **keep as REFERENCE** — see SS1.4 |

What is *mechanically* retired is small: 5 × (`_MODULES` tuple + `NAMES` dict + `names()` + `get()`),
i.e. ~5 × 25 lines of lookup code, plus the top-level `CONFIGS`/`names()`/`get()`/`get_scenario()`.
The bulk of the line count is docstrings and worked data, not machinery.

### SS1.3.1 Archive mechanism — two options

| | Option Arch-1: `dev/archive/configs-registry-2026-10/` | Option Arch-2: git tag / branch only |
|---|---|---|
| **What it is** | `git mv` the files into `dev/archive/configs-registry-2026-10/configs/...`, preserving the directory shape; add a one-page `README.md` in the archive root saying what this was, which decisions created it (D-49…D-83), what replaced it, and how to resurrect it | delete the files in one commit; tag the parent commit `pre-pivot-configs-registry` (and/or keep a `archive/configs-registry` branch); nothing left in the working tree |
| **Pros** | the content is *readable in place* — you can open `demo.py` next to your new hand-written script and copy numbers out of it without any git gymnastics; survives a `pip install -e .` + fresh clone workflow; an agent can `Grep` it | zero clutter in the working tree; zero risk of the archive drifting / being mistaken for live code; true "reversible" semantics (git history is the archive) |
| **Cons** | ~55 K of dead text in the tree that `Grep` will keep hitting (needs the usual `--glob '!dev/archive/**'` discipline); risk of somebody later "fixing" archived code | resurrection is `git show <tag>:configs/motors/cti_k570.py` — fine for you, friction for an agent mid-task; invisible to anyone who did not read this document |
| **Cost** | ~15 min | ~5 min |

**Recommendation: do both, Arch-1 as the primary.** The tag costs nothing and is the real safety net;
the folder is what makes the archive *useful* rather than merely *existing*. The user's own words
("maybe when app is implemented") say they expect to read this material again, which argues strongly
for readable-in-place. Add the archive path to the project's `Grep`-exclusion habits in `CLAUDE.md`.

One wrinkle to be explicit about: archived modules will have **stale imports** the moment the pivot
changes anything (e.g. if `configs.schema` is renamed later). That is fine and expected — archived code
is not expected to import. Say so in the archive `README.md` so nobody tries to make it do so.

### SS1.4 REFERENCE — stays in the repo, outside the installed package

This is the bucket the scope correction adds, and it is the right call: `apps/*` consume simulation
results and are calibrated to one specific synthetic vehicle
(`apps/common/study_vehicle.py`: a 1.5 kg / 75 mm constant-mass airframe — verified, with hard-coded
`S=0.00442, d_ref=0.075, C_x=0.5`). That is a *study input*, not a library capability. Nobody
`pip install`ing a trajectory engine wants it.

| Item | Why it is REFERENCE, not CORE | Why it is REFERENCE, not ARCHIVED |
|---|---|---|
| `apps/motor_selection/`, `apps/airbrake_sizing/`, `apps/cfd_conditions/`, `apps/weight_aero_tradeoff/`, `apps/common/` | each hard-codes a study vehicle and a study question; downstream consumers of `run_sim`, not physics | ~100 K of working, tested code (4 of them have dedicated test files); the single best worked example of "drive the engine from outside" the project has |
| `run.py`, `run_motor_sweep.py`, `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py` | thin `main()` wrappers; the user's own script replaces them | they are *literally* the "how do I call this from a script" example the pivot needs |
| `data/` (13 committed files) | the user's own curves/tables/soundings live in *their* folder | the repo's own tests depend on them byte-for-bit; the `.eng` K570 curve and the LKPR sounding are the worked examples |
| `configs/*/\_TEMPLATE_*.py` (5 files, ~43 K) | registry-era "fill in, rename, register" instructions | **highest-value thing in the whole `configs/` tree**: every field annotated `REQ`/`OPT` + units + description. Exactly the crib sheet a user hand-writing `Motor(...)` needs. See SS1.4.2 |

#### SS1.4.1 Where does REFERENCE material physically live?

Three sub-options:

| | Ref-1: leave in place at repo root | Ref-2: move under `examples/` | Ref-3: move into the archive |
|---|---|---|---|
| **Layout** | `apps/`, `run*.py`, `data/` stay exactly where they are; packaging metadata simply does not list them as packages | `examples/apps/`, `examples/run_*.py`; `data/` stays (tests need it) or becomes `examples/data/` | everything joins `dev/archive/` |
| **Pros** | **zero file moves, zero import churn, zero test churn.** `python run.py` and `python -m apps.X.Y` keep working verbatim from the repo root | signals the boundary visually; matches a common convention for libraries with demo code | maximal cleanliness of the live tree |
| **Cons** | the CORE/REFERENCE boundary exists only in `pyproject.toml` + this document, not in the folder tree — someone will assume `apps/` is part of the package | every `from apps.common import ...` in 4 test files breaks; `python -m apps...` invocation strings change; ~25 doc references go stale; `python run.py` becomes `python examples/run.py` | throws away working, tested code and its tests for a boundary that packaging already enforces; `data/` cannot move (tests) |
| **Cost** | 0 | ~2–4 h incl. tests + docs + `CLAUDE.md` profile update | ~1 h + loss of 4 test files' worth of coverage |

**Recommendation: Ref-1 (leave in place).** The package boundary is enforced by the one place that
actually matters — the explicit `packages = [...]` list in `pyproject.toml` (SS3). Moving directories
buys a visual cue at the price of real churn in tests, docs and muscle memory, and the pivot already
has enough moving parts. Make the boundary legible with prose instead: one short
`## What ships in the package` section in the root `README.md` and a one-line header comment in
`pyproject.toml`. Revisit Ref-2 if and when the GUI arrives and `apps/` genuinely needs to be
somebody's dependency.

#### SS1.4.2 The `_TEMPLATE_*` modules — do not throw these away

The brief did not ask about these, so flagging explicitly: the 5 `_TEMPLATE_*.py` files are ~43 K of
per-field `REQ|OPT` + units + description annotations (that is a documented project convention — see
`CLAUDE.md` § "Шаблоны конфигов"). Once there is no registry, their "step 3: register it" instructions
are wrong, but their field documentation is the single most useful artefact for somebody hand-writing
`Motor(name=..., thrust=Thrust(...), mass_model="endpoints", m_total=..., ...)`.

Three ways to carry that value forward:

- **T-1 (recommended):** keep the files, rename the live copies to drop the registry framing — e.g. one
  consolidated `examples/worked_scenario.py` (a single runnable script that builds rocket + motor +
  site + weather + scenario inline, carrying the `REQ|OPT` comments) and let the 5 per-kind templates
  go to the archive. One file the user actually runs beats five they have to assemble mentally.
- **T-2:** keep all 5 `_TEMPLATE_*.py` where they are, strip the "register" step from each docstring.
  Cheapest; keeps 5 non-runnable files.
- **T-3:** fold the `REQ|OPT` field documentation into the dataclass field comments in
  `configs/schema.py` / `sim/params.py` themselves (several already have them) and archive all 5
  templates. Best long-term single-source-of-truth, most work, and it bloats the two most-read modules.

### SS1.5 The one file that needs an edit to survive: `configs/__init__.py`

Currently 92 lines: a long "how do I add my own" docstring, `from configs import rockets, scenarios,
sites, weather`, re-exports of `Config`/`LaunchSite`/`Rocket`/`Scenario`/`Variant`/`Weather` from
`configs.schema`, then `CONFIGS`/`names()`/`get()` aliased onto `configs.scenarios`, plus
`get_scenario()`.

After the pivot, everything registry-shaped goes. The open question is what the file becomes:

- **Cfg-1 (recommended): a thin, honest re-export shim.** Keep `from configs.schema import Airframe,
  Config, LaunchSite, Motor, Rocket, Scenario, Sections, Variant, Weather, assemble` plus `__all__`,
  and a short docstring pointing at the worked example. ~20 lines. Benefit: a user script can write
  `from configs import Motor, Rocket, Scenario, assemble` — one import line instead of two, and the
  deep-module seam stays at `configs`, not `configs.schema`. Note `Thrust`, `Aero`, `Soundings`,
  `Lengths`, `Site`, `Atmosphere`, `Wind`, `Recovery`, `Control`, `Solver` live in `sim/params.py`, so a
  realistic user script imports from both; the shim could re-export those too (it currently does not),
  which would make `from configs import *`-style single-line imports actually sufficient. That is a
  small genuine improvement the pivot is a good moment for.
- **Cfg-2: empty `__init__.py`**, user scripts always say `from configs.schema import ...`. Most
  explicit, zero magic, one extra import line per script.
- **Cfg-3: delete `configs/` as a package**, move `schema.py` up/elsewhere — that is the naming fork,
  handled in [SS3.3](#ss33-one-top-level-package-or-three).

Also note, for SS2's benefit: `assemble()` **does** touch the filesystem — `_weight_from_pieces` calls
`sim.motor_file.load(motor.thrust.motor_curve)` (line 449 of `configs/schema.py`) whenever
`motor.mass_model != "none"`, to read `m_prop`/`m_total`/`length`/`diameter`/total impulse out of the
`.eng` header. So motor-file path resolution has to work at **`assemble()` time**, not only at
`run_sim()` time. This is the fact that rules out "just resolve paths inside the integrator".

---

<a id="ss2"></a>
## SS2. Data file path resolution — the load-bearing fork

### SS2.1 The three call sites, verbatim

| Site | Code | Consumes |
|---|---|---|
| `sim/motor_file.py:72-76` `_motors_path()` | `repo_root = os.path.dirname(os.path.dirname(__file__))` → `os.path.join(repo_root, "data", "motors", filename)` | `Thrust.motor_curve` (via `thrust_curve._load_motor_curve` at run time, **and** via `_weight_from_pieces` at `assemble()` time) |
| `sim/aero.py:135-136` `_load_table()` | same `repo_root` → `os.path.join(repo_root, "data", "aero", name)` | `Aero.table`, only when `Aero.model == "table"` |
| `sim/soundings.py:200-202` `load_case()` | same `repo_root` → `os.path.join(repo_root, "data", "soundings", case)` then `glob.glob(<case_dir>/*.csv)` | `Soundings.case`, for `Atmosphere.model in {sounding, field}` and `Wind.model in {sounding, field}` |

All three are `@functools.lru_cache(maxsize=None)` keyed on the bare string (plus
`thrust_curve._load_motor_curve`, a second cache layer on the same key). Tests call `.cache_clear()`
~40 times across `test_aero.py`, `test_atmosphere.py`, `test_soundings.py`, `test_wind.py`.

### SS2.2 The finding that changes the economics of this fork

**Absolute paths already work today, in all three loaders, with zero code change.** I verified this
empirically (ran all three loaders against files in an external scratch directory, outside the repo):

- `motor_file.load(r"C:\...\scratchpad\ext_curve.eng")` → loaded, `designation="K570"`, 11 points,
  J = 2062.2 N·s. The `#designation` fragment also works (`...\ext_curve.eng#K570`), because
  `load()` does `spec.partition("#")` *before* any path handling.
- `aero._load_table(r"C:\...\ext_table.csv")` → `_AeroTable` returned.
- `soundings.load_case(r"C:\...\extcase")` → 1 station loaded.

The reason is `os.path.join` semantics: a later component that is absolute **discards** every preceding
component. So `os.path.join(repo_root, "data", "motors", r"D:\my\x.eng")` evaluates to
`D:\my\x.eng`. Verified on this machine:

```
'D:\\my\\x.eng'      -> 'D:\\my\\x.eng'          # works
'D:/my/x.eng'        -> 'D:/my/x.eng'            # works
'/abs/x.eng'         -> 'D:/abs/x.eng'           # SILENTLY WRONG (repo's drive letter grafted on)
'sub/x.eng'          -> '<repo>\\data\\motors\\sub/x.eng'   # relative: joined under repo data
'x.eng'              -> '<repo>\\data\\motors\\x.eng'       # bare name: today's behaviour
```

So the honest framing of this fork is **not** "how do we make external data work" (it already does, by
accident) but **"how do we make it supported, documented, tested, and free of the two silent-failure
modes above"**:

- **Gap A:** a drive-less POSIX-style absolute path (`/home/me/x.eng`, or a user typing `/data/x.eng`
  on Windows) gets the repo's drive letter prefixed and fails with a confusing `FileNotFoundError`.
- **Gap B:** a **cwd-relative** path (`motors/x.eng`, `./x.eng`) resolves under
  `<repo>/data/motors/`, not under the user's working folder. This is the one that bites the stated
  workflow hardest: "I work in a clean folder" naturally produces `motor_curve="motors/K570.eng"`,
  which will fail pointing at a directory the user has never heard of.
- **Gap C:** nothing is tested or documented, so a refactor could remove the behaviour without anyone
  noticing. (It *has* already survived one refactor — the Step 76 split of `thrust_curve.py` into
  `motor_file.py` — by luck, not by test.)

### SS2.3 Option 1 — path-as-given, with a bare-name fallback to the bundled `data/`

**Shape.** Replace each of the three 2-line path helpers with one shared helper:

```python
# sim/datafiles.py (new, ~30 lines)
_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def resolve(given: str, kind: str) -> str:
    """`kind` in {"motors", "aero", "soundings"}.
    1. absolute -> used as given
    2. contains a path separator -> resolved against os.getcwd()
    3. bare name -> <bundled>/data/<kind>/<given>   (today's behaviour)
    """
    if os.path.isabs(given):
        return given
    if os.sep in given or "/" in given:
        return os.path.abspath(given)
    return os.path.join(_BUNDLED, kind, given)
```

**What it does to the 3 call sites.** Each loses its 2-line `repo_root` computation and gains
`path = datafiles.resolve(filename, "motors")`. Net: 3 one-line edits + 1 new ~30-line module + its
test file. `sim/soundings.py` additionally keeps its `glob` on the resolved directory.

**Backward compatibility.** Perfect, by construction: every existing string in the repo
(`"Cesaroni_2060K570-17A.eng"`, `"placeholder.csv"`, `"example.csv"`, `"example"`,
`"test_bad_grid.csv"`, `"field_example"`, …) is a bare name with no separator, so rule 3 reproduces
today's path byte-for-byte. **Zero existing test needs to change**, including the ~15 tests that write
a temp `.csv` into the repo's own `data/aero/` or `data/soundings/<case>/` (verified: `tests/` computes
those write paths with its own `os.path.dirname(__file__), "..", "data", ...`, independent of `sim/`).

**Interaction with `#designation`.** None — `load()` partitions on `#` first. Caveat worth one test: a
directory name containing a literal `#` would break `partition`. Risk: negligible, but a user folder
named `C:\rockets\#2 build\` would fail obscurely; document "no `#` in data paths".

**Interaction with `lru_cache`.** Rule 2's `os.path.abspath()` resolves against the cwd *inside* the
cached function, so a relative key cached before an `os.chdir()` returns a stale path. Fix: resolve in
the caller, or key the cache on the resolved path (`load()` is the public entry — have it resolve, then
delegate to a cached `_load_resolved(abspath)`). Small, worth getting right once.

**Pros:** smallest diff of the three; preserves every existing numeric pin and test; makes the already-
working absolute-path behaviour explicit and testable; closes Gaps A and B; the user's day-one workflow
becomes literally "paste the absolute path" with nothing to configure.
**Cons:** the user repeats a long absolute path in every field (mitigable in *their own* script with a
`DATA = Path(__file__).parent / "data"` constant — arguably the right place for it); "bare name means
the library's bundled data" is a mild surprise once the user has their own file of the same name;
heuristic dispatch on "does it contain a separator" is a tiny bit of magic.

### SS2.4 Option 2 — an injectable data root

**Shape.** The three loaders consult a module-level setting instead of a hardcoded root:

```python
# sim/datafiles.py
_root = os.environ.get("ROCKET_PHYSICS_DATA") or <bundled data dir>
def set_data_root(path: str) -> None: ...      # also clears the three caches
def data_root() -> str: ...
```

Sub-variants: (a) env var only, (b) `set_data_root()` function only, (c) both, env var as the default
and the function as the override, (d) threaded as a `Params`-level field (e.g. `Solver`-sibling group
`Paths`) so a `Config` is self-describing.

**What it does to the 3 call sites.** Same 3 one-line edits as Option 1, plus the mutable-state
plumbing.

**What it does to existing tests.** If the default stays the bundled `data/`, nothing breaks. But the
~40 `cache_clear()` call sites become a correctness hazard: changing the root must invalidate three
independent `lru_cache`s plus `thrust_curve._load_motor_curve`'s second layer, or a test that sets a
root gets a stale answer from a previous root. Either `set_data_root` clears all four caches (easy to
forget when a fifth cache appears) or the root joins each cache key.

**Pros:** no long paths in the user's script — one `set_data_root("D:/my-rockets/data")` at the top and
every field stays a short, readable bare name, which is close to today's ergonomics; env var makes it
configurable without editing code; variant (d) makes a `Config` reproducible without ambient state.
**Cons:** introduces **global mutable state into a package whose stated contract is "offline and
deterministic"** (`CLAUDE.md`) — the determinism argument is strong here and I weight it heavily;
requires one `data/<kind>/` subfolder layout in the user's folder (they must mirror the library's
convention: `motors/`, `aero/`, `soundings/`); does not help a user whose motor curve and aero table
live in unrelated places; variant (d) is a 13th `Params` group, which the pinned
`dataclasses.fields(Params)` test in `tests/test_config_pieces.py` deliberately makes a loud,
explicit decision rather than a quiet one.

### SS2.5 Option 3 — in-memory data, bypassing the file layer

**Shape.** Allow the already-parsed object/arrays to be supplied directly, *in addition to* a filename.

Cost is wildly different per loader, which matters:

| Loader | In-memory shape | Cost | Hashability problem |
|---|---|---|---|
| motor | `Thrust(curve=((t0,T0),(t1,T1),…))` — a tuple of float pairs | **low**: ~15 lines in `thrust_curve.py` + ~20 in `_weight_from_pieces` (which also needs `m_prop`/`m_total`/`length`/`diameter`/`total_impulse`, so really it needs a whole `MotorRecord`, and those fields already exist on `Motor` itself as explicit overrides — verified: `Motor.m_total`, `.m_prop`, `.length`, `.diameter` are all real fields) | tuple-of-pairs is hashable → `lru_cache` and the frozen-dataclass `==` pins both keep working. Passing a `MotorRecord` instead would break both: it is a frozen dataclass holding `np.ndarray`, so `hash()` raises and `==` is ambiguous |
| aero | `_AeroTable` — a `NamedTuple` of 7 arrays on an `(n_M, n_alpha)` grid | **medium**: the grid must be rectangular and validated; the existing loader does that validation during parsing, so an in-memory path needs the validation extracted | `NamedTuple` of arrays: `==` ambiguous, unhashable |
| soundings | `tuple[Sounding, ...]`, each a `NamedTuple` of 6 arrays + 5 scalars, then `_resample_case` (itself `lru_cache`d) on top | **high**: two cache layers and a resampling grid downstream | same |

**What it does to existing tests.** Nothing, if purely additive (new optional field, default keeps the
file path). New tests needed for each in-memory path.

**Pros:** the only option that serves "my data is not in a file at all" — a measured curve from a load
cell, a curve fetched from thrustcurve.org, a parametric sweep, a CFD-derived aero grid. For a GUI
later this is *the* needed seam (a GUI has an in-memory table, not a filename), so this is the
future-proofing move. Also the only option with no path semantics at all, hence no silent-wrong-path
failure mode.
**Cons:** does not by itself solve the stated request (the user has `.eng` files); three very different
amounts of work; two of the three shapes are unhashable, so they cannot be cached or compared the way
the current code assumes; "two ways to say the same thing" needs a validation rule
(`motor_curve` and `curve` both set → error, not precedence).

### SS2.6 Recommendation for SS2

**Option 1 now, Option 3 for the motor only, Option 2 rejected.**

1. **Option 1 (full).** New `sim/datafiles.py` with the 3-rule `resolve()`, the three call sites
   converted, cache keys moved onto the resolved absolute path, plus a test file pinning: bare name →
   bundled data (today's behaviour, 3 cases); absolute path → as given (3 cases, one per loader); POSIX
   root-absolute path → no drive-letter grafting; cwd-relative with a separator → relative to cwd;
   `#designation` surviving an absolute path. This is the whole of the user's stated need, with the two
   silent-failure gaps closed.
2. **Option 3, motor only.** Add `Thrust.curve: tuple[tuple[float, float], ...] = ()` as an
   alternative to `motor_curve`, with "both set → `ValueError`". Cheap (hashable, no cache churn), and
   it is the seam that a GUI, a measured curve, or a synthetic sweep all need. `Motor` already carries
   explicit `m_total`/`m_prop`/`length`/`diameter` overrides, so `_weight_from_pieces` can run off an
   in-memory curve provided those are given — the only genuinely file-derived quantity left is total
   impulse, which is computed from the curve itself. **Flagged as deferrable**: it is additive and can
   be a later step without blocking anything.
3. **Option 2 rejected** for the core reason that a mutable global data root contradicts the project's
   own "offline and deterministic" contract and silently couples four `lru_cache`s to ambient state.
   Note its one real ergonomic win is fully recoverable *inside the user's own script*:
   `D = Path(__file__).parent / "data"` then `motor_curve=str(D / "motors" / "K570.eng")`. That puts the
   base-directory concept where it belongs — in the user's code, explicit, per-script, not in library
   global state.

---

<a id="ss3"></a>
## SS3. Packaging mechanism

### SS3.1 Starting conditions (verified)

- **No packaging metadata of any kind.** No `pyproject.toml`, `setup.py` or `setup.cfg`. Confirmed.
- `requirements.txt` is 4 lines: `numpy==2.5.4`, `scipy>=1.18,<2`, `matplotlib>=3.11,<4`, `pytest>=8`.
- **The interpreter is a global CPython 3.12.10, not a venv** (`sys.prefix == sys.base_prefix`).
- **Neither `setuptools` nor `hatchling` is installed** (`import setuptools` → `ModuleNotFoundError`).
  PyPI is reachable (verified: downloaded `setuptools-84.2.1`), so build isolation will fetch a backend
  on first install — but this is a real prerequisite, not a given.
- pytest 9.1.1; current pytest `rootdir` is already `D:\Projects - Ongoing\rocket-physics` with no
  `configfile`.
- Top-level directories git tracks: `apps`, `configs`, `data`, `dev`, `sim`, `tests`, `tools` +
  5 `run*.py` + `CLAUDE.md` + `requirements.txt`. (`controllers/`, `output/`, `temp/`, `temporary/`,
  `docs/` are untracked; `docs/` is LaTeX build output.)

### SS3.2 Option A (pyproject + editable install) vs Option B (PYTHONPATH / .pth)

I built a mock of this repo's exact layout in a scratch directory and ran both paths through a scratch
venv. Everything below is measured, not assumed.

#### Finding A1: a *bare* `pyproject.toml` fails on this layout

With only `[build-system]` + `[project]`, setuptools 84.2.1 refuses to build:

```
error: Multiple top-level packages discovered in a flat-layout: ...
  1. set up custom discovery (`find` directive with `include` or `exclude`)
  2. use a `src-layout`
  3. explicitly set `py_modules` or `packages` with a list of names
error: metadata-generation-failed
```

So the brief's "no `src/` layout move required" holds, **but only if the package list is explicit.**
That is not a workaround — it is the mechanism that enforces the CORE/REFERENCE boundary from SS1.

#### Finding A2: the explicit-package form works, and the boundary is real

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "rocket-physics"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["numpy==2.5.4", "scipy>=1.18,<2", "matplotlib>=3.11,<4"]

[tool.setuptools]
packages = ["sim", "configs"]        # CORE only. apps/, tests/, tools/ are deliberately absent.
```

Measured result after `pip install -e .`, running from an unrelated clean directory:

```
sim.params        -> <repo>\sim\params.py          # editable, points at live source
configs           -> importable
apps              -> ModuleNotFoundError: No module named 'apps'       (boundary holds)
tests             -> ModuleNotFoundError                               (boundary holds)
```

Three consequences worth stating explicitly:

1. **Editable install points at the live repo source**, so the user's clean external folder and the
   repo stay in sync with no rebuild step. Edits in `sim/` take effect on the next `python` run.
2. **The bundled-`data/` fallback from SS2 keeps working under an editable install**, because
   `os.path.dirname(os.path.dirname(sim.__file__))` is still the real repo root. This is load-bearing
   for "zero existing test changes".
3. **It would NOT work under a non-editable `pip install .`**: `data/` sits at the repo root, outside
   any declared package, so it is simply not copied into site-packages, and every bare-name path in
   the repo's own tests would break. **Therefore: recommend editable install only**, and if a real
   wheel is ever wanted, `data/` must first move inside the package (e.g. `sim/_data/`) and be declared
   as package data. Record this as a known limit rather than discovering it later.

#### Finding A3: adding `pyproject.toml` does not disturb pytest or `python run.py`

Measured, mock repo, pytest 9.1.1:

| | rootdir | result |
|---|---|---|
| with `pyproject.toml` | `<repo>` | `1 passed`, header adds `configfile: pyproject.toml` |
| without | `<repo>` | `1 passed`, no `configfile` line |

So `rootdir` is unchanged (it was already the repo root), and test collection/`sys.path` insertion is
unaffected — that mechanism depends on `tests/__init__.py` existing (which it does, and must, per the
documented `eventkit` collision), not on any ini file. One nuance: pytest 9 reports
`configfile: pyproject.toml` **even with no `[tool.pytest.ini_options]` table**, i.e. the file becomes
the config file. Harmless while the table is absent; a good place to later move the project's pytest
settings if any are ever added.

`python run.py` / `python -m apps.X.Y` from the repo root: unaffected either way — cwd is on
`sys.path[0]`, which is how they already work.

#### Option B — `PYTHONPATH` or a `.pth` file

| | Option A: `pyproject.toml` + `pip install -e .` | Option B: `PYTHONPATH` / `.pth` |
|---|---|---|
| **Mechanism** | one ~15-line file in the repo; `pip install -e .` once | either set `PYTHONPATH=D:\Projects - Ongoing\rocket-physics` in the user's environment, or drop `rocket-physics.pth` containing that path into site-packages |
| **Setup cost** | one command, needs PyPI once to fetch the build backend (setuptools is not installed) | zero; no build backend, no network |
| **Dependency declaration** | `dependencies = [...]` installs/validates numpy/scipy/matplotlib for the user's project | none — the user's project has no machine-readable dependency on anything |
| **Version pin** | `version = "0.1.0"`; the external project can record `rocket-physics==0.1.x`; `pip list` shows it | none; "whatever is in that folder today" |
| **CORE/REFERENCE boundary** | **enforced** — `apps`/`tests`/`tools` are genuinely not importable (measured) | **not enforced** — the whole repo root is on the path, so `import apps`, `import tests`, `import tools` all work from the user's folder, i.e. the boundary this pivot is about does not exist |
| **Uninstall / know what is installed** | `pip uninstall rocket-physics` | edit an env var or hunt for a `.pth` |
| **Portability** | standard; works in any venv, CI, another machine | per-machine, per-shell; a classic "works on my machine" |
| **Risk here** | installs into the **global** Python (user has no venv) → two very generic top-level names, `sim` and `configs`, become globally importable. **`configs` is a live PyPI distribution (v3.0.3)** — verified — so this is a concrete collision class, and this project has already been bitten by exactly this failure mode (`eventkit` shipping a top-level `tests`, documented in `CLAUDE.md`) | same global-name exposure, with no record that it happened |
| **Cost** | ~30 min incl. a test that the boundary holds | ~5 min |

**Recommendation: Option A**, with one addition — **create a venv in the user's clean external folder**
and `pip install -e "D:\Projects - Ongoing\rocket-physics"` into *that*, not into the global
interpreter. That keeps the two generic top-level names out of the global environment, makes the
numpy/scipy pins explicit for the user's project, and makes "which version of the engine is this run
against" answerable. `requirements.txt` then becomes redundant for the library's own runtime deps —
recommend keeping it, reduced to the dev/test extras (`pytest>=8`) plus a comment pointing at
`pyproject.toml`, or expressed as `[project.optional-dependencies] dev = ["pytest>=8"]`.

Backend choice: **setuptools**, not hatchling. Neither is installed, so there is no incumbency
advantage; setuptools is what the empirical test above validated on this exact layout, and hatchling's
flat-layout `packages` directive would need the same explicit list anyway. No churn either way, so
go with the one that is measured to work.

### SS3.3 One top-level package or three?

Today's importable top-level names would be `sim` and `configs` (not three — `controllers/` does not
exist). The fork is whether packaging is the moment to consolidate into
`rocket_physics.{sim, schema, ...}`.

| | Name-1: keep `sim` + `configs` | Name-2: `rocket_physics` namespace | Name-3: keep `sim`, retire `configs` as a name |
|---|---|---|---|
| **User script writes** | `from sim.integrate import run_sim`, `from configs import Motor, Rocket` | `from rocket_physics.sim.integrate import run_sim`, `from rocket_physics import Motor, Rocket` | `from sim.integrate import run_sim`, `from sim.schema import Motor` (move `configs/schema.py` → `sim/schema.py`) |
| **Blast radius** | **0 files** | **~70 files** contain `from sim.` / `import sim` and **~32** contain `configs.schema` / `from configs import` (measured by grep over `*.py`, overlapping sets) — plus every docstring cross-reference in `sim/`, `configs/`, `apps/`, `tests/`, every `dev/docs/architecture-*.md`, `CLAUDE.md`'s own Profile table, and the LaTeX report's prose (which **must not be edited**, per project rule) | **~32 files** (the `configs.*` importers), 1 file moved, `configs/` deleted |
| **Collision safety** | **poor**: `configs` is taken on PyPI (v3.0.3); `sim` is not a PyPI dist name but is a plausible module name for someone | **good**: one distinctive namespace, no plausible collision | **medium**: removes the one name that is actually taken; `sim` remains generic |
| **Deep-module quality** | the seam is two unrelated-looking top-level names for one library | one obvious front door; `rocket_physics.__init__` can re-export the ~20 names a user script needs in one import | one front door, honestly named for what it is (a simulator) |
| **Risk to numeric pins** | none | none *mechanically* (pure rename), but a ~70-file mechanical rename across a codebase whose tests pin results bit-for-bit is exactly where a typo hides; needs a full suite run (~220 s) and a careful diff review | low |
| **Cost** | 0 | ~4–8 h incl. docs, plus a dedicated review pass | ~1.5–3 h |

**Recommendation: Name-1 (zero rename) for this pivot, and raise Name-2 as a separate, later,
single-purpose step if the user wants it.** Reasoning:

- The user's three stated goals are all achievable with zero renaming. Bundling a 70-file rename into
  the same change makes the pivot's own diff unreviewable, and this project's discipline is explicitly
  one step = one commit = one reviewable diff with pins verified.
- The collision risk is real but *fully mitigated* by the venv recommendation in SS3.2 — a private venv
  containing only this project and numpy/scipy/matplotlib cannot collide with PyPI's `configs`.
- If the rename does happen later, it should be its own phase with its own full-suite gate, and it
  should be done **after** the registry archive (fewer files to rename) — so sequencing argues for
  deferring regardless.
- Honest counter-argument, which the user should hear: a rename gets cheaper the earlier it happens,
  and this pivot is already touching `configs/` heavily, so there is a "while we're in here" argument.
  If the user's instinct is that `configs.schema` is the wrong name for the thing (it is a bit odd once
  no configs registry exists), **Name-3 is the cheap middle**: it removes the one genuinely bad name
  (`configs`, both taken on PyPI and semantically wrong post-pivot) for ~1/3 of Name-2's cost, and it
  leaves `rocket_physics` available as a later wrapper. My own second choice.

---

<a id="ss4"></a>
## SS4. What breaks, and roughly how big the fix is

Measured by grep over `*.py` for `configs.get`, `configs.motors`, `configs.rockets`, `configs.sites`,
`configs.weather`, `configs.scenarios`, `get_scenario`, `from configs import`, `import configs`.
`motor_registry` and `resolve_motor` have **zero** hits anywhere — they do not exist in this codebase.

**16 files total** are registry-coupled. Nothing in `sim/` or `tools/` is (verified: zero hits).

### SS4.1 `apps/` and `run*.py` — 5 files, ~770 lines, small localised fixes

Re-scoped per the orchestrator's correction: these are being **repositioned**, not archived, and their
dependency on `sim` / `configs.schema` is *fine and unchanged* — an external consumer importing a
package is exactly the intended shape. Only the *registry* calls break.

| File | hits | lines | What breaks | Fix |
|---|---|---|---|---|
| `run.py` | 2 | 103 | `configs.get("demo")` (line 47) | construct the demo `Scenario` inline, or import it from the new worked-example module → ~5 lines |
| `apps/cfd_conditions/select_conditions.py` | 2 | 217 | `configs.get("demo")` (line 202) | same → ~5 lines |
| `apps/common/cli.py` | 3 | 69 | the **whole premise**: `--config NAME` and `--list-configs` only mean something with a name registry | see SS4.1.1 — this is a design question, not a mechanical fix |
| `apps/common/study_vehicle.py` | 2 | 75 | `from configs.sites import origin_msl` / `from configs.weather import isa_dry_calm` (lines 31-32) | inline the two pieces; they are 1-line objects (`Site()` all-defaults and `Atmosphere(model="isa")` + `Soundings()` + `Wind(model="none")` — verified from `tests/test_config_registries.py:191-195`, which pins `origin_msl.site == Site()`) → ~8 lines |
| `apps/weight_aero_tradeoff/compare_configs.py` | 4 | 310 | `configs.get(names[0])`, list-comprehension over `names`, `--list-configs`-style notes print | this app's *purpose* is "compare N named configs"; see SS4.1.1 |

Note `apps/motor_selection/` and `apps/airbrake_sizing/` have **zero** registry hits in their own code
(only their tests do) — they already run off `apps/common/study_vehicle.py`.

#### SS4.1.1 The one genuine design casualty: `--config NAME`

`apps/common/cli.py` and `apps/weight_aero_tradeoff/compare_configs.py` are built on "resolve a string
to a config". Without a registry there is nothing to resolve. Three ways out, in increasing cost:

- **CLI-1 (recommended):** drop `--config`/`--list-configs`; each app takes its vehicle from a
  module-level constant it owns (which 2 of the 4 already do). `compare_configs.py`'s N-config mode
  becomes "the module defines a `SCENARIOS` list" — which is exactly how
  `apps/motor_selection/motors.py` already defines its `MOTORS` list, so this is *consistency*, not
  regression. ~40 lines deleted, ~20 changed, 1 test file touched.
- **CLI-2:** `--config path/to/my_scenario.py`, loaded via `importlib.util.spec_from_file_location`,
  expecting a module-level `SCENARIO` or `CONFIG`. This is the genuinely nice answer for the user's
  stated workflow (their scenario files live in their own folder, and `python -m apps.airbrake_sizing
  --config ./my_rocket.py` just works) — and it is a *registry-free* mechanism, so it does not reverse
  the pivot. ~50 new lines + tests. **Worth flagging to the user as an upgrade, not a cost.**
- **CLI-3:** keep a registry but make it user-owned (the user's folder has its own `_MODULES`). This
  reverses the pivot and should be rejected.

Also affected, trivially: `tests/test_configs.py:247,254` assert the literal string
`'configs.get("demo")'` appears in `run.py` and `select_conditions.py`. Those two assertions die with
the registry.

### SS4.2 `tests/` — 11 files; ~3 files rewritten/removed outright, ~8 touched lightly

| File | hits | lines | Verdict |
|---|---|---|---|
| `tests/test_config_registries.py` | 37 | 229 | **delete.** 100 % registry: `_MODULES` shape, name↔`CONFIG.name` consistency, `_TEMPLATE_*` not-registered, per-registry parametrisation. Nothing in it survives the pivot. Its two useful physics facts (`origin_msl.site == Site()`, the `isa_dry_calm` group values, the `cti_k570` `motor_curve` string, `_weight_from_pieces` on the K570) should be **lifted into** the schema-level test file before deleting |
| `tests/test_config_migration.py` | 30 | 275 | **mostly delete.** It exists to pin the Step-73 migration (`configs.get` delegating to `configs.scenarios`) — a migration that is itself being reversed. The ~6 numeric pins it carries (`weight.m_d`, `I_sp == 212.41`, endpoints-vs-isp comparison) are real physics and must be **relocated** to a schema-level test built on an inline `Scenario`, not on `configs.get("demo")` |
| `tests/test_configs.py` | 8 | 268 | **rewrite, keep ~60 %.** Much of it is `Params`/`s0` literal pins for the demo config (real physics value); the registry parts (`configs.get("nope")` `KeyError`, name parametrisation, the fresh-interpreter `import configs` checks, the two `'configs.get("demo")' in <source>` string assertions) go |
| `tests/test_template_docs.py` | 11 | 164 | **delete or rewrite**, depends on fork T-1/T-2/T-3 in SS1.4.2. It pins that each `_TEMPLATE_*` documents every field with `REQ|OPT` — a genuinely valuable convention test. Under T-1 it becomes "the worked example documents every field"; under T-2 it survives nearly as-is; under T-3 it should point at the dataclass modules |
| `tests/test_motor_pieces.py` | 7 | 447 | **light touch.** Mostly schema-level (`Motor` frozen, `_weight_from_pieces` cases). The registry-coupled part is the D-70 test "`import configs` performs no filesystem access" (lines 403-445) — which **loses its reason to exist**, because with no registry, importing `configs` cannot read a motor file at all. Simplify to a one-line assertion or delete. ~45 lines |
| `tests/test_weight_aero_tradeoff.py` | 4 | 626 | **light touch**, ~15 lines: the `monkeypatch.setitem(... .SCENARIOS, "toy_05kg", ...)` at line 530-533 (registry injection) and `configs.get("demo")` at 605-612 |
| `tests/test_airbrake_sizing.py` | 3 | 338 | **light touch**, ~6 lines: 2 × `configs.get("demo")` |
| `tests/test_dynamics.py` | 4 | 1038 | **light touch**, ~8 lines: 2 local `import configs` + `configs.get("demo")` |
| `tests/test_motor_selection.py` | 2 | 554 | **light touch**, ~4 lines |
| `tests/test_mach_warning.py` | 2 | 78 | **light touch**, ~4 lines (one fixture) |
| `tests/config_variants.py` | 2 | 139 | **light touch**, ~8 lines: the two piece imports (SS4.1 says they inline to ~8 lines) |
| `tests/test_config_pieces.py` | 0 | 343 | **unaffected** — pure schema/`assemble()` level, including the pinned `dataclasses.fields(Params)` keyword-set test. This file is the proof that the schema layer stands on its own |

**The single highest-leverage move:** all eight "light touch" files break on exactly one thing —
`configs.get("demo")` no longer existing. Give them **one shared source of the demo `Scenario`** (a
module-level `DEMO_SCENARIO` living either in the worked-example module or in `tests/config_variants.py`,
which already holds test-only pieces by design — D-80) and every one of them becomes a 1-line import
change. That is the difference between "~8 files, ~60 lines" and "~8 files, rewritten".

### SS4.3 Size summary

| Area | Files | Rough effort |
|---|---|---|
| `sim/` data-path change (SS2 Option 1) | 3 edited + 1 new module + 1 new test file | ~2 h |
| `configs/` archive + `__init__.py` shim | 10 archived, 1 edited | ~1 h |
| worked example / `DEMO_SCENARIO` single source | 1 new file | ~1 h |
| `apps/` + `run*.py` registry decoupling | 5 files, ~80 lines net | ~2 h (more if CLI-2 is chosen: +~2 h) |
| `tests/` rewrite + relocation of pins | 3 rewritten/deleted (~670 lines), 8 light (~90 lines) | ~4–6 h |
| `pyproject.toml` + boundary test | 1 new file | ~0.5 h |
| **Total** | **~25 files** | **~11–15 h**, i.e. 5–7 tracker steps |

**Numeric-pin risk: low but non-zero.** The physics is untouched by every option recommended here
(SS2 Option 1 reproduces today's resolved path byte-for-byte for every existing bare name; the archive
touches no numbers). The risk is concentrated in **relocating** the pins currently expressed as
`configs.get("demo").params.weight.I_sp == pytest.approx(212.41)` onto an inline `Scenario`: if the
inline scenario is not byte-identical to `configs/scenarios/demo.py` + `configs/rockets/demo.py` +
`configs/motors/cti_k570.py`, pins move and it will look like a physics regression. Mitigation: build
the inline demo by *copying the three archived modules' literals verbatim* and verify the composed
`Params` equals the pre-pivot one field-by-field in the same step, before touching anything else.

---

<a id="ss5"></a>
## SS5. Recommendation — one coherent proposal

### SS5.1 The proposal in one paragraph

Keep `sim/` and `configs/schema.py` untouched as the package core; archive the five registry
subpackages and the four library-shipped instance modules into `dev/archive/configs-registry-2026-10/`
plus a git tag; reduce `configs/__init__.py` to a ~20-line re-export shim so a user script gets every
dataclass from one import; add `sim/datafiles.py` with a 3-rule path resolver (absolute → as given,
has-a-separator → relative to cwd, bare name → bundled `data/<kind>/`) and point the three loaders at
it; add a `pyproject.toml` whose `[tool.setuptools] packages = ["sim", "configs"]` list *is* the
CORE/REFERENCE boundary, installed with `pip install -e .` into a venv that lives in the user's clean
external folder; leave `apps/`, `run*.py`, `tools/` and `data/` exactly where they are as reference
material that is deliberately not on the installed import path; and keep today's `sim` / `configs`
import names, deferring any `rocket_physics` rename to its own later phase.

### SS5.2 Ordered steps (suggested tracker sequence)

Independent-first so the risky parts land on a green suite:

1. **`sim/datafiles.py` + the three loaders + its test file.** Fully independent of the registry
   question; proves external data works *before* anything is archived. Zero existing tests change.
   Full-suite gate.
2. **`pyproject.toml` + a test asserting the boundary** (`apps`/`tests` are not in `packages`). Also
   fully independent. Verify `python run.py`, `python -m apps.*`, `python -m pytest -q` all still work
   unchanged from the repo root.
3. **The worked example + single `DEMO_SCENARIO` source**, with a test that the composed `Params`
   is field-identical to `configs.get("demo").params` — a *bridge* test that exists only during this
   step and proves the inline copy is faithful while both sides still exist.
4. **Repoint the 8 light-touch tests + `run.py` + `select_conditions.py`** at `DEMO_SCENARIO`. Full
   suite still green against the still-present registry.
5. **Decouple `apps/`** (`cli.py` per fork CLI-1 or CLI-2, `study_vehicle.py`'s two inlined pieces,
   `compare_configs.py`'s N-config mode) and update their 3 test files.
6. **Archive**: delete the bridge test from step 3, relocate the surviving pins out of
   `test_config_registries.py` / `test_config_migration.py` / `test_configs.py`, `git mv` the 10 files
   into `dev/archive/`, reduce `configs/__init__.py` to the shim, tag the parent commit. Full-suite
   gate; this is the step where pins are at risk.
7. *(optional, later, separate)* `Thrust.curve` in-memory motor input (SS2 Option 3).
8. *(optional, later, separate phase)* the `rocket_physics` / `sim.schema` rename.

Steps 1 and 2 are `parallel_safe` against each other (disjoint files: `sim/` + one new test vs. one new
root file). Everything from 3 onward is sequential.

### SS5.3 The user's day-one workflow afterwards

External clean folder, e.g. `D:\rockets\`:

```
D:\rockets\
  .venv\                       <- python -m venv .venv ; .venv\Scripts\pip install -e "D:\Projects - Ongoing\rocket-physics"
  data\
    motors\Cesaroni_2060K570-17A.eng
    aero\my_54mm.csv
  my_rocket.py
```

`my_rocket.py` — every field name below is verified against the current source
(`configs/schema.py`, `sim/params.py`, `configs/rockets/demo.py`, `configs/motors/cti_k570.py`):

```python
from pathlib import Path

from configs import Airframe, Motor, Rocket, Scenario, Sections, assemble
from sim.params import Aero, Lengths, Recovery, Solver, Thrust
from sim.params import Site, Atmosphere, Soundings, Wind
from configs import LaunchSite, Weather
from sim import report
from sim.integrate import run_sim

DATA = Path(__file__).parent / "data"

rocket = Rocket(
    name="my54",
    airframe=Airframe(m=1.5, I=0.15, l=0.55),          # kg, kg*m^2, m (CoG station aft of the nose tip)
    lengths=Lengths(l1=0.3, l2=0.4),                   # CoP->CoG, CoP->thrust point, m
    aero=Aero(S=0.00229, d_ref=0.054, l_ref=1.10, C_x=0.5),
    sections=Sections(L_total=1.10, l_nose=0.25,
                      l_fin_root_fwd=0.92, l_fin_root_aft=1.02,
                      l_motor_aft=1.10),
    recovery=Recovery(model="deploy", trigger="apogee", Cd=0.8, S=1.23),
)

motor = Motor(
    name="k570",
    thrust=Thrust(motor_curve=str(DATA / "motors" / "Cesaroni_2060K570-17A.eng")),
    mass_model="endpoints",                            # none | isp | endpoints
)

site = LaunchSite(name="pad", site=Site(lat0_deg=0.0, h0_m=0.0,
                                       azimuth_deg=90.0, L_rail=0.0, rail_angle_deg=90.0))
weather = Weather(name="isa", atmosphere=Atmosphere(model="isa"),
                  soundings=Soundings(), wind=Wind(model="none"))

scenario = Scenario(name="my54_k570", rocket=rocket, motor=motor,
                    site=site, weather=weather, solver=Solver(t_max=1200.0))

cfg = assemble(scenario)                               # -> Config(name, params, s0, notes)
result = run_sim(cfg.params, cfg.s0)
report.print_run_summary(result, cfg.params, cfg.s0)
```

Two things to notice, because they are the measure of whether this pivot delivered:

- **No name strings resolve to anything.** `name=` is now pure labelling (used in plot titles and
  report headers), not a lookup key. That is the whole of point 2.
- **The only thing that made this impossible before is the `str(DATA / "motors" / ...)` line.** Without
  SS2, that string is silently re-rooted under the repo's own `data/motors/`.

Multi-case studies, which the registry used to serve, become ordinary Python:

```python
for S_brake in (0.0, 0.002, 0.004):
    cfg = assemble(dataclasses.replace(scenario,
        rocket=dataclasses.replace(rocket,
            control=Control(airbrake_model="proportional", airbrake_S_max=S_brake, ...))))
    ...
```

— or via `Scenario.overrides` (dotted paths, already supported: `assemble()` runs
`sim.params.replace(p, sc.overrides)` after composition), which is what `Variant` was built for and
which survives the pivot untouched.

### SS5.4 What this proposal deliberately does *not* do

- It does not rename anything (SS3.3 Name-1). Two generic top-level names stay, mitigated by the venv.
- It does not move `apps/` or `data/` on disk (SS1.4.1 Ref-1). The boundary is in `pyproject.toml`.
- It does not design for the GUI. The one forward-looking concession is SS2 Option 3's in-memory motor
  curve, explicitly deferred to an optional later step, because a GUI needs an in-memory seam and
  nothing else here would give it one cheaply.
- It does not produce an installable wheel (`pip install .` without `-e`) — see SS3.2 finding A3's
  third consequence. If that is ever wanted, `data/` must move inside the package first.

---

<a id="ss6"></a>
## SS6. Open forks for the grilling session

Each is separately answerable and carries my recommended answer. **None is decided by this document.**
Numbering is local (`F1`…`F16`); the decision log in `dev/status.json` continues from **D-130**, so if
these are adopted they become D-131 onward.

| # | Fork | Options | My recommendation | Cost of getting it wrong |
|---|---|---|---|---|
| **F1** | Archive mechanism for the registry layer | (a) `dev/archive/configs-registry-2026-10/` folder; (b) git tag/branch only; (c) both | **(c), folder primary.** The tag is free insurance; the folder is what makes the archive readable next to the new hand-written script, which the user's "maybe when app is implemented" implies they want | low — reversible either way |
| **F2** | Where does REFERENCE material (`apps/`, `run*.py`) physically live? | (a) in place at repo root, excluded from `packages`; (b) move to `examples/`; (c) archive it | **(a).** The `pyproject.toml` `packages` list already enforces the boundary (measured). Moving dirs breaks ~4 test files, 5 invocation strings and ~25 doc references for a visual cue | medium — (b) later is a mechanical but tedious move |
| **F3** | Fate of the five `_TEMPLATE_*.py` (~43 K of `REQ`/`OPT`/unit annotations) | (a) one consolidated runnable `worked_scenario.py`, archive the five; (b) keep all five, strip the "register" step; (c) fold the field docs into `configs/schema.py` + `sim/params.py` | **(a).** One file the user actually runs beats five they assemble mentally. (c) is the best long-term single source of truth but bloats the two most-read modules | medium — this is the user's main crib sheet; losing it would hurt |
| **F4** | What `configs/__init__.py` becomes | (a) ~20-line re-export shim; (b) empty; (c) delete the `configs` package (→ F8) | **(a), and extend it** to also re-export the ten `sim.params` groups (`Thrust`, `Aero`, `Site`, `Atmosphere`, `Wind`, `Soundings`, `Lengths`, `Recovery`, `Control`, `Solver`) so a user script needs one import line, not three | low |
| **F5** | Data-file path resolution | (1) path-as-given + bare-name fallback; (2) injectable data root (env var / setter / `Params` group); (3) in-memory data on the dataclasses | **(1) now, (3) for the motor only and deferred, (2) rejected.** (2) puts mutable global state into a package whose contract is "offline and deterministic", and couples four `lru_cache`s to ambient state | **high — this is the load-bearing decision** |
| **F6** | Should a **bare filename** still fall back to the bundled `data/<kind>/`? | (a) yes (today's behaviour preserved → zero test changes); (b) no, bare names become an error, forcing explicit paths | **(a).** (b) is arguably cleaner — no hidden second search location — but it breaks every existing path string in the repo's own tests (~30 call sites) for a purity gain | medium — (b) can be adopted later behind a deprecation |
| **F7** | Packaging mechanism | (A) `pyproject.toml` + `pip install -e .`; (B) `PYTHONPATH` / `.pth` | **(A).** Measured: (B) puts the *whole repo root* on the path, so `import apps`/`import tests` work — i.e. the CORE/REFERENCE boundary this pivot is about would not exist | medium |
| **F8** | Importable top-level name(s) | (1) keep `sim` + `configs`; (2) consolidate into `rocket_physics.*` (~70 + ~32 files); (3) keep `sim`, move `configs/schema.py` → `sim/schema.py` and retire the `configs` name (~32 files) | **(1) for this pivot, (3) as a cheap later step, (2) only as its own phase.** Note **`configs` is a taken PyPI name (v3.0.3)** and this project has already been bitten by a top-level-name collision (`eventkit`'s `tests`) | medium — renames get more expensive over time, so there is a real "while we're in here" counter-argument |
| **F9** | Install target for `pip install -e .` | (a) a venv inside the user's clean external folder; (b) the global CPython 3.12 they use today | **(a).** (b) makes two very generic names (`sim`, `configs`) globally importable, one of which collides with a real PyPI distribution | medium — fixable later, annoying meanwhile |
| **F10** | `apps/` CORE/REFERENCE status (the orchestrator's scope correction, stated explicitly) | (a) REFERENCE, excluded from `packages`, stays in repo; (b) CORE, shipped with the package; (c) archived; (d) its own second installable distribution | **(a).** Apps hard-code a 1.5 kg / 75 mm study vehicle and a study question — study inputs, not library capability. But they are the best worked example of driving the engine from outside, so not (c) | low |
| **F11** | `--config NAME` / `--list-configs` in `apps/common/cli.py` | (1) drop both; apps own their vehicle as a module constant (2 of 4 already do); (2) `--config path/to/my_scenario.py` loaded via `importlib`; (3) keep a registry, user-owned | **(1) as the floor, (2) as an upgrade worth +~2 h** — (2) is registry-free *and* serves the stated workflow (`python -m apps.airbrake_sizing --config ./my_rocket.py`). (3) reverses the pivot; reject | low |
| **F12** | Build backend | setuptools / hatchling | **setuptools** — measured working on this exact flat layout; neither is currently installed, so there is no incumbency to respect | very low |
| **F13** | Support a real (non-editable) wheel? | (a) no — editable only, documented; (b) yes — move `data/` inside the package and declare it as package data | **(a) now.** (b) is the right answer the day someone other than the user installs this; it is a self-contained later step | low |
| **F14** | `requirements.txt` after `pyproject.toml` exists | (a) keep, reduced to dev/test deps + a pointer; (b) delete, use `[project.optional-dependencies] dev`; (c) keep both in full (duplicated) | **(b)**, falling back to (a) if any tooling still reads the file. Avoid (c) — two places to update one pin is how pins drift | very low |
| **F15** | `Thrust.curve` in-memory motor input (SS2 Option 3) | (a) now, in this pivot; (b) later, own step; (c) never | **(b).** Purely additive, no blocker, and it is the seam a GUI will need — so it should exist eventually, just not inside a pivot that already touches 25 files | low |
| **F16** | The `demo` scenario itself | (a) survives as one shared `DEMO_SCENARIO` constant (worked example + test fixture in one); (b) duplicated into each consumer; (c) becomes test-only in `tests/config_variants.py` | **(a).** This is the single highest-leverage decision in SS4: it turns 8 "light touch" test files from rewrites into 1-line import changes | medium — (b) means ~8 copies of the same literals, which is how pins drift |

### SS6.1 Questions to stress-test with the user (beyond picking an option above)

1. **"I work in a clean folder" — how clean, exactly?** Does the user expect the external folder to
   contain a `data/motors|aero|soundings` tree mirroring the library's convention (which would make
   F5 Option 2 more attractive than I judged), or arbitrary paths wherever files happen to be? My
   recommendation assumes the latter. This directly flips F5/F6.
2. **Does the user intend to ever run `python run.py` / `python -m apps.*` from the repo again**, or is
   the repo becoming purely a dependency they never `cd` into? If the latter, F2's "move to
   `examples/`" gets stronger and `run*.py` could go to the archive.
3. **How much does `configs` as a *name* bother them?** They did not raise it; I am flagging it (F8).
   If it does bother them, F8 option (3) is cheap now and expensive later.
4. **Is `assemble()` the API they want, or would they rather `Scenario(...).config` / a direct
   `Scenario → run` call?** `Scenario.config` already exists as a property (verified,
   `configs/schema.py:325-327`). A one-line `run(scenario)` convenience is trivial to add and would
   shorten the day-one script by two lines — but it hides the `Params`/`State` seam the whole codebase
   is built around.
5. **Do they want the archived registry to stay importable** (i.e. do they foresee ever running the old
   demo as-is), or is "readable text I can copy numbers out of" enough? My recommendation assumes the
   latter and explicitly allows archived imports to rot.
6. **Pin-relocation risk tolerance.** Step 6 of SS5.2 relocates ~10 numeric pins
   (`I_sp == 212.41`, the demo `Params`/`s0` literals) off `configs.get("demo")` onto an inline
   `Scenario`. My mitigation is a temporary bridge test asserting field-by-field equality while both
   exist. Is that acceptable, or does the user want the demo pins frozen as literal numbers instead?

---

<a id="ss7"></a>
## SS7. Verified facts (grounding)

Everything below was measured in this session, not recalled. Recorded so later rounds and the
implementing developer do not re-derive it.

### SS7.1 Codebase facts

| Fact | How verified |
|---|---|
| `configs/schema.py` imports only `dataclasses`, `math`, `typing`, `sim.{mass, motor_file, params, state}` — **no registry dependency** | read lines 1-95 |
| `sim/` and `tools/` contain **zero** `import configs` | `grep -rn "import configs\|from configs" sim/ tools/` → no hits |
| `assemble()` reads a motor file at composition time: `motor_file.load(motor.thrust.motor_curve)` | `configs/schema.py:449`, inside `_weight_from_pieces`, reached when `mass_model != "none"` |
| `Scenario.config` property already exists | `configs/schema.py:325-327` |
| `Thrust`, `Aero`, `Soundings`, `Lengths`, `Site`, `Atmosphere`, `Wind`, `Recovery`, `Control`, `Solver`, `Weight`, `Gravity`, `Params` live in **`sim/params.py`**, not `configs/schema.py` | read `sim/params.py` whole (233 lines) |
| `controllers/` **does not exist in git**; on-disk dir holds only a stale `__pycache__`. Control laws are in `sim/control.py` | `git ls-files controllers` → empty; `ls controllers/` |
| `motor_registry` / `resolve_motor` do not exist anywhere | grep → 0 hits |
| 16 files are registry-coupled; per-file hit counts in [SS4](#ss4) | grep over `tests/`, `apps/`, `run*.py` |
| `tests/test_config_pieces.py` (343 lines) has **0** registry hits — the schema layer stands alone | grep |
| Tests write temp data files into the repo's own `data/` using **their own** `tests/../data/...` path, independent of `sim/`'s resolution | `tests/test_aero.py:107,398,635`; `tests/test_atmosphere.py:36`; `tests/test_soundings.py:29`; `tests/test_wind.py:27` |
| ~40 `.cache_clear()` call sites across 4 test files; `lru_cache` on `motor_file.load`, `motor_file.records`, `thrust_curve._load_motor_curve`, `aero._load_table`, `soundings.load_case`, `soundings._resample_case` | grep |
| `_AeroTable` and `Sounding` are `NamedTuple`s of numpy arrays; `MotorRecord` is a frozen dataclass of numpy arrays → all three are unhashable and have ambiguous `==` | read the class definitions |
| `data/` has 13 committed files (5 motor curves incl. the K570 `.eng`, 1 aero table, 3 soundings in 3 cases, 2 READMEs) | `git ls-files data` |

### SS7.2 Path-resolution facts (the SS2 finding)

| Fact | How verified |
|---|---|
| **All three loaders already accept an absolute path, unmodified** | ran `motor_file.load`, `aero._load_table`, `soundings.load_case` against copies in an external scratch dir — all succeeded (K570: 11 points, J = 2062.2 N·s; 1 sounding station) |
| `#designation` survives an absolute path | `motor_file.load(r"...\ext_curve.eng#K570")` → OK (`load()` partitions on `#` before path handling) |
| A drive-less absolute path is **silently re-rooted**: `/abs/x.eng` → `D:/abs/x.eng` | `os.path.join` behaviour, measured |
| A **cwd-relative** path is joined under the repo's `data/<kind>/` — the real gap | measured |

### SS7.3 Packaging facts

| Fact | How verified |
|---|---|
| No `pyproject.toml` / `setup.py` / `setup.cfg` exists | `ls` |
| Interpreter is global CPython 3.12.10, **not a venv** | `sys.prefix == sys.base_prefix` |
| `setuptools` and `hatchling` are **not installed**; PyPI is reachable | `import setuptools` → `ModuleNotFoundError`; `pip download setuptools` → `setuptools-84.2.1-py3-none-any.whl` |
| A **bare** `pyproject.toml` fails on this flat layout: *"Multiple top-level packages discovered in a flat-layout"* | built a mock of the repo layout, ran `pip install -e .` with setuptools 84.2.1 → `metadata-generation-failed` |
| `[tool.setuptools] packages = ["sim", "configs"]` works; editable install resolves to **live repo source**; `import apps` / `import tests` raise `ModuleNotFoundError` from an external cwd | same mock, measured |
| Therefore the bundled-`data/` fallback keeps working under `-e` (because `sim.__file__` is the real repo path) but would **not** under a non-editable `pip install .` | by construction of the editable install path above |
| Adding `pyproject.toml` does **not** change pytest `rootdir` (already the repo root) and does not change collection; pytest 9.1.1 does start reporting `configfile: pyproject.toml` even with no `[tool.pytest.ini_options]` table | ran pytest in the mock with and without the file; ran `pytest --co` in the real repo |
| **`configs` is a live PyPI distribution, v3.0.3.** `sim` and `rocket-physics` are not taken as dist names | `pip index versions configs` / `sim` / `rocket-physics` |
| Installed tooling: pytest 9.1.1, pip 25.0.1, numpy 2.5.4 / scipy ≥1.18 / matplotlib ≥3.11 per `requirements.txt` | `pytest --version`, `pip --version`, `requirements.txt` |

### SS7.4 Superseded input

`dev/docs/configs-layout-analysis.md` (2026-10-26) analysed four ways to tidy the registry's folder
layout (`_library/` subfolders etc.) and recommended option B. **Entirely moot** under this pivot —
the layer it reorganises is the layer being archived. Skimmed; contains no fact needed here.

### SS7.5 History this pivot reverses

The registry was designed deliberately, over four phases, and it is worth saying what is being given up
so the reversal is a decision rather than an oversight:

- `architecture-30-apps-4-5-and-configs.md` SS30.3/30.4 — `Config`/`Variant` and the shared `configs`
  package, so every app takes the same consumption-level type.
- `architecture-31-config-separation.md` SS31.4/31.5/31.6 — piece separation
  (`Rocket`/`LaunchSite`/`Weather`), the one-owner-per-`Params`-group invariant (D-49), the registry
  shape (explicit `_MODULES`, never directory auto-discovery, "so a half-finished draft cannot become
  real by merely existing"), and `get_scenario()`.
- `architecture-32-motor-separation.md` SS32.2/32.3 — `Motor` as a piece, `thrust` moving from
  `Rocket` to `Motor`, `_weight_from_pieces` (D-56/D-57).
- `architecture-33-configs-one-demo.md` SS33.2 — the cull to one template + one demo per kind (D-78).

**What survives the reversal:** every one of the *type* and *invariant* decisions above
(`Config`/`Variant`/`Rocket`/`Motor`/`LaunchSite`/`Weather`/`Scenario`, one-owner-per-group,
`_weight_from_pieces`, `assemble()`'s pinned keyword set). **What is given up:** only the name-binding
layer — `_MODULES`, `names()`, `get()`, and "a config is a file in a known directory". The explicit
rationale for `_MODULES` ("a half-finished draft must not become real by merely existing") is fully
satisfied, trivially, by the user writing their scenario in their own script: nothing is registered,
so nothing can accidentally become real.

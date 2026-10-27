# Archive: the `configs/` file+registry convention (retired 2026-10, Step 125)

## Кратко (RU)

- Это архив старой конвенции `configs/{rockets,sites,weather,motors,scenarios}/`: один файл — один экземпляр
  (ракета/площадка/погода/мотор/сценарий), явные кортежи `_MODULES`, один шаблон `_TEMPLATE_*.py` и один демо-файл
  на вид, плюс реестр (`configs.get(name)`, `configs.names()`) в `configs/__init__.py`.
- Решения, которые построили эту конвенцию: D-45..D-55 (разделение на Rocket/LaunchSite/Weather/Scenario,
  architecture-31), D-56/D-57 (владение группами Params, тот же документ), D-73 (отдельный `configs/motors/`,
  architecture-32), D-78 (сведение к одному демо на пакет, architecture-33).
- Решения, которые её заменили (Phase 2.18 pivot): D-137..D-142 — убрать реестр целиком, конструировать
  `Motor`/`Rocket`/`LaunchSite`/`Weather`/`Scenario` как обычные классы напрямую в пользовательском скрипте;
  `configs/schema.py` остаётся (чистые датаклассы), `configs/__init__.py` становится тонким re-export шимом
  (Cfg-1), `examples/worked_scenario.py` — рабочий пример/шпаргалка вместо пяти `_TEMPLATE_*.py`. Полный разбор
  развилок — `dev/docs/pivot-configs-and-packaging-analysis.md`.
- Архивные модули **не обязаны** импортироваться чисто в будущем (их импорты `configs.schema` и т.п. могут
  протухнуть, если этот модуль когда-нибудь переедет) — это ожидаемо, не баг.
- Восстановление: файлы лежат прямо здесь, читаемы напрямую; либо `git show
  pre-pivot-configs-registry:configs/motors/cti_k570.py` после того, как оркестратор поставит этот тег.

## What this was

Through Phase 2.17, `configs/` was a **file + registry** convention: one Python module per concrete instance,
grouped into five subpackages by piece kind --

- `configs/rockets/` -- one file per `Rocket` (airframe/motor-mount geometry, aero, recovery, control)
- `configs/sites/` -- one file per `LaunchSite` (pad geodesy, rail)
- `configs/weather/` -- one file per `Weather` (atmosphere, soundings, wind)
- `configs/motors/` -- one file per `Motor` (thrust curve file plus mass model)
- `configs/scenarios/` -- one file per `Scenario` (a named rocket + motor + site + weather combination)

Each subpackage's `__init__.py` held an explicit `_MODULES` tuple naming every instance module in that
subpackage, built a `dict[str, <piece>]` registry keyed by each piece's own `.name`, and exposed `names()`/
`get(name)` for string-keyed lookup. `configs/__init__.py` sat on top, delegating `get`/`names`/`CONFIGS` to
`configs.scenarios` and adding one piece-level API, `get_scenario(name)`.

Each subpackage also shipped exactly one `_TEMPLATE_<kind>.py` -- a non-runnable module with every field of
that dataclass commented `REQ|OPT`, its unit or accepted values, and a one-line description -- and exactly one
real, library-shipped instance: `demo.py` in each of the five subpackages, composing into the single worked
example `configs.scenarios.demo` (`Scenario(name="demo", ...)`, a real Cesaroni K570 motor on a 54 mm
mass-modelled airframe, `origin_msl` / `isa_dry_calm`).

## The 15 archived files

```
configs/rockets/__init__.py        configs/rockets/demo.py        configs/rockets/_TEMPLATE_rocket.py
configs/sites/__init__.py          configs/sites/origin_msl.py    configs/sites/_TEMPLATE_site.py
configs/weather/__init__.py        configs/weather/isa_dry_calm.py configs/weather/_TEMPLATE_weather.py
configs/motors/__init__.py         configs/motors/cti_k570.py     configs/motors/_TEMPLATE_motor.py
configs/scenarios/__init__.py      configs/scenarios/demo.py      configs/scenarios/_TEMPLATE_scenario.py
```

Five registry `__init__.py` files, five library-shipped demo instances, five `_TEMPLATE_*.py` field-documentation
modules -- moved here with `git mv`, preserving their relative path under `configs/`, so they are tracked as
renames rather than delete+add.

## Which decisions built this convention

- **D-45..D-55** (`dev/docs/architecture-31-config-separation.md`): the Step-71..74 split of a single flat
  `Config` module into `Rocket`/`LaunchSite`/`Weather`/`Scenario` pieces, the four-subpackage layout, and the
  one-owner-per-`Params`-group invariant.
- **D-56/D-57** (same document): `assemble()`'s merge-free composition rule, later amended for the one derived
  group (`weight`).
- **D-73** (`dev/docs/architecture-32-motor-separation.md`): `configs/motors/` as a fifth, parallel subpackage
  (Step 79), carrying `Motor`/`Airframe`/`Sections` and the mass-model composition (`_weight_from_pieces`).
- **D-78** (`dev/docs/architecture-33-configs-one-demo.md`): collapsing every subpackage down to exactly one
  library-shipped demo instance plus its template (Step 85..92) -- the shape this archive captures.

## What replaced it (Phase 2.18 pivot)

The user's own workflow was always "write a short Python script that builds my rocket, not edit a file under a
library's own `configs/` tree and register it by name." The registry's value (worked examples, `REQ|OPT` field
documentation, one `configs.get(name)` lookup) was real but came at the cost of indirection the user's workflow
never needed.

- **D-137..D-142** (`dev/docs/pivot-configs-and-packaging-analysis.md`): retire the registry entirely. Construct
  `Motor`/`Rocket`/`LaunchSite`/`Weather`/`Scenario` directly as plain dataclasses in a user script, `assemble()`
  (or `Scenario.config`) them into a `Config`, `run_sim()` it -- no registration step, no string-keyed lookup.
- `configs/schema.py` is unchanged -- the dataclasses and `assemble()`/`_weight_from_pieces` themselves were
  never registry-coupled.
- `configs/__init__.py` became a thin re-export shim (**Cfg-1** in the pivot analysis, SS1.5): re-exports the
  `configs.schema` dataclasses plus the `sim.params` groups a realistic user script also needs
  (`Aero`/`Atmosphere`/`Control`/.../`Wind`), so `from configs import Motor, Rocket, Scenario, assemble` is one
  import line instead of two, with no registry behind it.
- `examples/worked_scenario.py` replaced the five `_TEMPLATE_*.py` files as the `REQ|OPT` crib sheet -- one
  runnable, commented script (built at Step 122, proven field-identical to the old `configs.scenarios.demo` by
  the now-also-deleted `tests/test_bridge_demo_scenario_equivalence.py`) instead of five files a user had to
  assemble mentally (option **T-1** in the pivot analysis, SS1.4).

## Resurrecting an archived module

These files are not going anywhere unreachable:

- Read them directly -- they are still ordinary, committed files, just under `dev/archive/` instead of
  `configs/`.
- Or, once the orchestrator tags the pre-pivot commit as `pre-pivot-configs-registry`:
  `git show pre-pivot-configs-registry:configs/motors/cti_k570.py` (etc., for any of the 15 paths above, using
  their *original* `configs/...` path against that tag -- the tag predates the `git mv`).

## A note on staleness

**Archived modules are not expected to import cleanly going forward.** Every one of them does
`from configs.schema import ...` (or similar) using an import path that assumes it still lives under
`configs/`; if `configs/schema.py` is ever renamed or moved, every archived module's import breaks. This is
expected, not a bug -- these files are historical record, not a maintained code path. If you need to actually
run one again, copy its content out and fix its imports for wherever `configs/schema.py` (or its replacement)
lives at that point.

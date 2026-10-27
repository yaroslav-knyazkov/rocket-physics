# Architecture §33 — `configs/` down to one template + one demo per piece; D-76 (`s0.m = weight.m`) (Phase 2.16, design only)

> Superseded 2026-10 by the Phase 2.18 pivot (`dev/docs/pivot-configs-and-packaging-analysis.md`); the
> registry this document describes is archived at `dev/archive/configs-registry-2026-10/`.

## Кратко (RU)

- Документ — дизайн чистки `configs/` (D-78): в каждом подпакете остаются `_TEMPLATE_*` и **один** demo; один сценарий `demo` = ракета `demo` (бывшая 54-мм `demo_75mm_k570`) + мотор `cti_k570` + `origin_msl` + `isa_dry_calm`.
- Удаляются: ракеты `toy_05kg`, `demo_75mm`; моторы `placeholder`, `synthetic_large`, `cti_k570_isp`; площадка `highland_1500m`; погода `breezy_isa`; сценарии `toy_05kg`, `demo_75mm`, `demo_75mm_airbrake`, `demo_75mm_highland`. Файлы `data/` не трогаются (D-72).
- Главная находка: Apps 3 и 5 — исследования с **постоянной массой**, откалиброванные под 1.5 кг / 75 мм. На demo с включённой масс-моделью ось массы App 5 и per-motor `weight.m` App 3 молча перестают работать (динамика берёт массу из `y[M]`, а не из `weight.m`). Поэтому рекомендация D-79: этот аппарат переезжает из `configs/` в `apps/common/study_vehicle.py` как входные данные исследований (рядом с их `MOTORS`/`SCENARIOS`), а не «второе demo».
- run.py, App 2 (CFD) и App 4 (аэротормоз) переходят на `demo`; цели App 4 (`targets.py`) пересчитаны под demo (перезапись значений, список ниже).
- Тестовые варианты (toy, highland/breezy, `cti_k570_isp`) — в `tests/config_variants.py`; точные пины остаются бит-в-бит, тавтологичный пин `demo_75mm` заменяется настоящим (против независимого литерала).
- D-76: `assemble()` ставит `s0.m = weight.m`, если масс-модель включена и `s0.m == 0.0`; ни один пин не сдвигается.
- Новые решения D-79…D-83 (рекомендации внутри); тикеты — Steps 85-91.

## Contents

- [33.1 Findings](#331-findings)
- [33.2 Keep / remove table](#332-keep--remove-table)
- [33.3 Where each removed variant goes](#333-where-each-removed-variant-goes)
- [33.4 Apps and `run.py`](#334-apps-and-runpy)
- [33.5 D-76 — `s0.m` from the composed mass](#335-d-76--s0m-from-the-composed-mass)
- [33.6 Test changes, file by file](#336-test-changes-file-by-file)
- [33.7 Re-records vs. bit-for-bit pins](#337-re-records-vs-bit-for-bit-pins)
- [33.8 Decision log (D-79 … D-83)](#338-decision-log-d-79--d-83)
- [33.9 Risks](#339-risks)
- [33.10 Implementation tickets (Steps 85-91)](#3310-implementation-tickets-steps-85-91)
- [33.11 Not in this ticket set](#3311-not-in-this-ticket-set)

Numbering: last decision on record is **D-78** (the user's "one demo" direction), D-77 is the RK45
re-pin, D-76 is the `s0.m` fix — so new forks start at **D-79**. Last step is **Step 84** (LaTeX sync,
deferred) — tickets start at **Step 85**. LaTeX (`dev/docs/latex/`) is out of scope (frozen).

---
## 33.1 Findings

Measured on this branch (2026-10-15, probes in a scratch dir, `PYTHONPATH=.`), not recalled.

**F1 — who reads which registry entry (Grep, `*.py`, LaTeX excluded).** The orchestrator's list was
right but incomplete: **App 5 also defaults to `demo_75mm`** (`apps/weight_aero_tradeoff/trade_surface.py:398`
`add_config_arg(parser, default="demo_75mm")`, `compare_configs.py:256` `default="demo_75mm"`) and its
tests pin the comma mode with two registry names (`tests/test_weight_aero_tradeoff.py:526`
`"demo_75mm,toy_05kg"`).

| entry | readers outside `configs/` |
|---|---|
| `toy_05kg` | `run.py:47`, App 2 `select_conditions.py:203`; tests: `test_configs` (pins, source pins), `test_config_migration`, `test_motor_pieces` (names), `test_weight_aero_tradeoff` (comma mode) |
| `demo_75mm` | App 3 `compare_motors.py:295,319`, App 5 defaults; tests: `test_configs`, `test_config_migration`, `test_weight_aero_tradeoff`, `test_motor_selection` (only via `_demo_baseline()`) |
| `demo_75mm_airbrake` | App 4 `solve_cda.py:638`; `test_airbrake_sizing.py:39`; `test_config_migration` |
| `demo_75mm_highland`, `highland_1500m`, `breezy_isa`, `demo_75mm_k570`, `cti_k570_isp` | tests only |
| `synthetic_large` (motor) | nobody (App 3/4 read the `.csv` directly) |
| `placeholder` (motor) | the four constant-mass scenarios; `_TEMPLATE_scenario.py:98` |

**F2 — `test_demo_75mm_params_pin_demo_baseline_exactly` is a tautology today.** `_demo_baseline()`
is `return configs.get("demo_75mm").params` (Step 69), so the "pin" compares the registry entry with
itself. Only the two `toy_05kg` pins compare against an independent literal (`_toy_05kg_literal()` in
`tests/test_configs.py`). Moving `demo_75mm` is the chance to make its pin real (§33.6).

**F3 — with the mass model on, `weight.m` is inert after assembly.** `sim/dynamics.py:230-239`:
`m = p.weight.m` only when `p.weight.m_d is None`; otherwise `m = y[M]`, i.e. the **initial state's**
mass. So a `params_replace(cfg.params, {"weight.m": …})` on a mass-model-on config changes nothing in
flight. App 5's whole mass axis (`trade_surface.build_surface`, `params_replace(... "weight.m": m)`) and
its `heavy_sleek` variant, and App 3's per-motor `weight.m` overrides, would be **silently flat** on the
K570 demo. This is the fact that decides D-79.

**F4 — App 3 and App 5 are calibrated to the 1.5 kg / 75 mm constant-mass vehicle by literal.**
`apps/weight_aero_tradeoff/scenarios.py`: mass axis `[1.0, 2.5] kg` is "F10's measured band around
demo_75mm's 1.5 kg baseline"; both `Variant`s are absolute literals "against demo_75mm's own
baseline". `apps/motor_selection/motors.py`: per-motor casings sized against that airframe, the two
H-class entries override-free on purpose; module docstring: "constant mass … deliberately NOT
enabled". `test_motor_selection.py` checks closed-form `T/m` at 1.5 kg against `_demo_baseline()`.

**F5 — the K570 demo as built** (`demo_75mm_k570`, RK45): `weight.m = 3.185`, `m_d = 2.195`,
`s0.m = 3.185` (local patch), apogee **5946.74 m** at **t = 29.61 s**, burnout **3.59 s**, ground at
57.6 s, **V_max ≈ 874 m/s (Mach ≈ 2.6)** with the constant `C_x = 0.5` model, 0.07 s wall per flight
(vs 0.03 s for `demo_75mm`: 372 m, apogee 9.19 s, burnout 2.0 s).

**F6 — the demo works for run.py / App 2 / App 4 unchanged in code.** Gravity sweep:
5946.74 / 5949.77 / 5956.17 m (constant/radial/wgs84). run.py's LKPR comparison (linearized aero,
`h0_m=380`, **without** the toy `aero.S/d_ref` overrides): ISA 6107.01 m, sounding 6118.62 m — the
LKPR file reaches 10 000 m MSL, apogee ~6.5 km MSL stays inside it. App 2 `select_cfd_conditions`
returns 10 conditions (M ≈ 1.05 … 2.6). App 4 solves all four spec kinds on the demo (numbers in
§33.4.4; a deploy time of 30.0 s > apogee 29.61 s raises the flat-objective error as it should).

**F7 — `_TEMPLATE_scenario.py` imports `configs.motors.placeholder`** (line 98) and docstring-references
`configs.rockets.demo_75mm`; it must keep importing cleanly (`test_config_registries`,
`test_template_docs`). Its inline rocket has no `Airframe.l` / `Sections`, so it cannot simply switch
to `cti_k570` (mass model on needs `l`).

**F8 — `tests/` is a package and already imports across files** (`test_config_migration.py:35`
`from tests.test_configs import _toy_05kg_literal`), so a non-collected helper module
`tests/config_variants.py` works with no conftest.

---

## 33.2 Keep / remove table

End state: every subpackage holds `__init__.py`, its `_TEMPLATE_*.py`, and **exactly one** registered
piece. `configs/__init__.py` and `configs/schema.py` stay (schema gains the D-76 line). `data/` is
untouched (D-72) except the prose of `data/motors/README.md`.

| file | verdict | replaced by / goes to |
|---|---|---|
| the five `_TEMPLATE_*.py` | **keep** | only `_TEMPLATE_scenario.py` is edited (inline motor, docstring, §33.4.6); the other four name no removed module (Grep-checked) |
| `rockets/demo_75mm_k570.py` | **keep → `rockets/demo.py`**, `name="demo"` (D-80) | numbers unchanged (D-83) |
| `scenarios/demo_75mm_k570.py` | **keep → `scenarios/demo.py`**, `name="demo"`; local `s0` patch deleted (D-76) | — |
| `motors/cti_k570.py`, `sites/origin_msl.py`, `weather/isa_dry_calm.py` | **keep** (the one motor / site / weather; the last two pin `sim/params.py` defaults) | — |
| `rockets/demo_75mm.py`, `scenarios/demo_75mm.py` | remove | **`apps/common/study_vehicle.py`** (D-79): the constant-mass baseline Apps 3/5 are calibrated to (F4); `demo` cannot replace it without re-baselining both studies (F3) |
| `rockets/toy_05kg.py`, `scenarios/toy_05kg.py` | remove | `demo` for run.py and App 2; numbers verbatim to `tests/config_variants.py` so the exact `run.py`-literal pin keeps testing the composition's pass-through path |
| `scenarios/demo_75mm_airbrake.py` | remove | `demo` — App 4 owns `control.airbrake_*` (SS30.6) and layers its brake onto any config; it never needed its own scenario |
| `scenarios/demo_75mm_highland.py`, `sites/highland_1500m.py`, `weather/breezy_isa.py` | remove | `demo` / `origin_msl` / `isa_dry_calm` for users; pieces verbatim to `tests/config_variants.py` (`HIGHLAND`) |
| `motors/cti_k570_isp.py` | remove | `cti_k570`; piece verbatim to `tests/config_variants.py` (D-59 tests) |
| `motors/placeholder.py` | remove | `cti_k570`; `study_vehicle.py`, `config_variants.py` and the template build `Motor(thrust=Thrust(motor_curve="placeholder.csv"))` inline |
| `motors/synthetic_large.py` | remove | `cti_k570`; it has no reader (F1); the `.csv` stays (App 3/4 read it directly) |

Registry `_MODULES` after: rockets `(demo,)`, motors `(cti_k570,)`, sites `(origin_msl,)`,
weather `(isa_dry_calm,)`, scenarios `(demo,)`. `--list-configs` prints one line.

## 33.3 Where each removed variant goes

### 33.3.1 `apps/common/study_vehicle.py` — the constant-mass study vehicle (D-79)

One module, one home, used by App 3 (`_demo_baseline()`, `main()`), App 5 (default when `--config`
is omitted), and by the tests of Apps 3/4/5. It is a **study input**, the same kind as
`apps/motor_selection/motors.py::MOTORS`, `apps/weight_aero_tradeoff/scenarios.py::SCENARIOS` and
`apps/airbrake_sizing/targets.py::SPECS` (the §30.3 two-kinds convention): it is not registered, it is
not listed by `--list-configs`, and it is not a template for users.

```python
# apps/common/study_vehicle.py  -- shape only; docstring carries demo_75mm's provenance verbatim
from configs.schema import Airframe, Config, Motor, Rocket, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm
from sim.params import Aero, Lengths, Thrust

ROCKET = Rocket(name="study_75mm", airframe=Airframe(m=1.5, I=0.08), lengths=Lengths(l1=0.3, l2=0.4),
                aero=Aero(S=0.00442, d_ref=0.075, l_ref=0.75, C_x=0.5, C_z=0.0, C_m=0.0))
MOTOR = Motor(name="placeholder", thrust=Thrust(motor_curve="placeholder.csv"))  # mass_model "none"
SCENARIO = Scenario(name="study_75mm", rocket=ROCKET, motor=MOTOR,
                    site=origin_msl.SITE, weather=isa_dry_calm.WEATHER, notes=<demo_75mm's notes, verbatim>)
CONFIG: Config = SCENARIO.config
```

- Numbers are `configs/rockets/demo_75mm.py` + `configs/motors/placeholder.py` **byte-for-byte**, so
  `CONFIG.params` equals today's `configs.get("demo_75mm").params` exactly (the Step-86 gate).
- Name: `study_75mm` (not `demo_75mm`) — the user asked for one demo; a second thing called "demo"
  outside `configs/` would read as the request ignored. Cost: App 5 prints `study_75mm+heavy_sleek`
  instead of `demo_75mm+heavy_sleek`, and a few test string asserts follow (§33.6).
- Imports go `apps → configs.{schema, sites, weather}` only — no import of a removed module, no edge
  back into `apps` from `configs`.

### 33.3.2 `tests/config_variants.py` — test-only pieces and configs

A plain module (not `test_*`, so not collected; no conftest; `tests/` is a package, F8). Every piece
is moved **verbatim** from the deleted `configs/` module (numbers, comments, notes), so exact-equality
pins keep their meaning:

| symbol | content | used by |
|---|---|---|
| `TOY_05KG_ROCKET`, `TOY_05KG: Config` | `rockets/toy_05kg.py` + inline placeholder motor + `origin_msl` + `isa_dry_calm`, `name="toy_05kg"` | `test_configs` toy pins; `test_config_migration` rocket-groups; `test_weight_aero_tradeoff` comma mode (registered via `monkeypatch.setitem`) |
| `HIGHLAND_SITE`, `BREEZY_WEATHER`, `HIGHLAND: Config` | `sites/highland_1500m.py`, `weather/breezy_isa.py`, composed with `study_vehicle.ROCKET`/`MOTOR`, `name="demo_75mm_highland"` → rename `"study_75mm_highland"` | the three highland tests in `test_config_migration` |
| `CTI_K570_ISP: Motor` | `motors/cti_k570_isp.py` | `test_config_registries` D-59 composition test; `test_config_migration` end-to-end equivalence |
| `ALL: tuple[Config, ...]` | `(TOY_05KG, HIGHLAND)` | new parametrised "every test variant flies" (keeps flight coverage of the tilted rail + analytic wind that the registry parametrisation used to give) |

`demo_75mm_airbrake` gets **no** fixture: its params were identical to `demo_75mm`'s (the identity
test proves it), so App 4's property tests use `study_vehicle.CONFIG` directly.

---

## 33.4 Apps and `run.py`

### 33.4.1 `run.py` → `demo`

- `cfg = configs.get("demo")`; comments citing `configs/toy_05kg.py` rewritten to name the demo.
- Sweep (b) (ISA vs LKPR sounding): **drop `"aero.S": 0.005` and `"aero.d_ref": 0.08`** from
  `atmo_base` — they are the toy body's area/diameter and would put a 0.005 m² reference area on a
  54 mm airframe. Keep `aero.model="linearized"`, `C_A0/C_N_alpha/C_m_alpha`, `site.h0_m=380.0`,
  `soundings.case="example"`. Measured (F6): 6107.01 / 6118.62 m; apogee stays inside the LKPR column.
- Nothing pins run.py's printed numbers; only the source pin in `tests/test_configs.py` changes.

### 33.4.2 App 2 `apps/cfd_conditions/select_conditions.py` → `demo`

`cfg = configs.get("demo")`, comment updated. Output changes (unpinned): the ten weighted
conditions now span supersonic Mach (≈ 1.05 … 2.6), which is what a K-class demo honestly produces
(D-83).

### 33.4.3 App 3 `apps/motor_selection/compare_motors.py` → study vehicle (D-79)

- `_demo_baseline()` keeps its name and signature (imported unedited by `tests/test_motor_selection.py`);
  body becomes `return study_vehicle.CONFIG.params` (`from apps.common import study_vehicle`).
- `main()`: `cfg = study_vehicle.CONFIG`. Docstrings: "configs/demo_75mm.py" → the study module.
- Guard (D-82): `compare_motors(...)`'s existing pre-flight pass (or `build_params`) raises
  `ValueError` if `baseline.weight.m_d is not None` — "App 3 is a constant-mass study (F3): per-motor
  curve/weight overrides are meaningless on a mass-model-on baseline". Placed in the function
  `compare_motors` already uses to fail fast before any integration.
- Output: **bit-for-bit unchanged** (same `Params`, same `s0`).

### 33.4.4 App 4 `apps/airbrake_sizing/` → `demo`

- `solve_cda.py:638`: `add_config_arg(parser, default="demo")`; docstrings updated.
- `targets.py`: re-sized to the demo (**re-record**, numbers from F6; the developer re-measures and
  reports any last-digit difference):

  | spec | today (on `demo_75mm_airbrake`) | after (on `demo`) |
  |---|---|---|
  | `burnout_240m` → **`burnout_3850m`** | target 240 m, after_burnout | target **3850.0 m** (~65 % of 5947 m), after_burnout → expect `C_dA ≈ 0.0016031` |
  | `timer_240m` → **`timer_3850m`** | 240 m, after_time 4.0 s | **3850.0 m**, after_time **8.0 s** (post-burnout 3.59 s, pre-apogee 29.6 s) → expect `C_dA ≈ 0.011837` |
  | `when_to_pop` | 240 m, `cda_bounds=(0.01171,)*2`, `deploy_time_bounds=(0, 8)` | **3850.0 m**, `cda_bounds=(0.0016, 0.0016)` (burnout spec's own answer, 2 s.f.), `deploy_time_bounds=(0.0, 25.0)` → expect ≈ 3.58 s |
  | `descent_demo` | unchanged | unchanged |

  The module docstring's 372 m / 9.19 s / burnout-2.0 s narrative is rewritten against 5947 m /
  29.6 s / 3.59 s. `SPECS` key order keeps the burnout solve first (it is the CLI default via
  `next(iter(SPECS))`).
- App 4 tests: property tests stay on `study_vehicle.CONFIG` (bit-for-bit, their 9.3 s "too late"
  literal stays valid); the end-to-end `SPECS` test moves to `configs.get("demo")` because SPECS are
  now sized for it (§33.6).

### 33.4.5 App 5 `apps/weight_aero_tradeoff/` → study vehicle by default (D-79)

- `apps/common/cli.py`: `add_config_arg(parser, default: "str | None")` — `None` means "the app
  supplies its own vehicle"; help text then says `(default: the app's study vehicle)`.
  `resolve_config(args, fallback: "Config | None" = None)`: if `args.config is None`, return
  `fallback` (raise `ValueError` if both are `None`). App 4 keeps passing a string — no behaviour change.
- `trade_surface.main`: `add_config_arg(parser, default=None)`, `cfg = resolve_config(args, fallback=study_vehicle.CONFIG)`.
- `compare_configs.main`: `--config` default `None`; `_resolve_configs(None)` → `[study] + variants`;
  a single registry name keeps today's meaning (baseline + variants); 2+ names unchanged.
- Guard (D-82): `build_surface` raises `ValueError` if `cfg.params.weight.m_d is not None` (its mass
  axis would be flat, F3); `_resolve_configs` raises the same for a single-name baseline with the mass
  model on (the `SCENARIOS` variants override `weight.m`). Multi-name mode is unaffected (no
  `weight.m` overrides), so `--config demo,<other>` still works.
- `scenarios.py` docstrings: "demo_75mm" → "the study vehicle (`apps/common/study_vehicle.py`)";
  literals unchanged.
- Output: numbers **bit-for-bit**, printed names `study_75mm…` instead of `demo_75mm…`.

### 33.4.6 `configs/` itself

- `configs/scenarios/_TEMPLATE_scenario.py`: replace `from configs.motors.placeholder import MOTOR`
  by an inline module-level `_placeholder_motor = Motor(name="my_motor", thrust=Thrust(motor_curve="placeholder.csv"))`
  with a `# REQ|OPT, …` comment on **every** keyword (the `test_template_docs` inline-comment rule
  applies to every module-level constructor call); `motor=_placeholder_motor`. Docstring: drop the
  Step-72 "forward reference / not working code today" paragraph; the example import becomes
  `from configs.rockets.demo import ROCKET` (true now) and the live-import list names
  `configs.sites.origin_msl`, `configs.weather.isa_dry_calm`. No `### Motor` table is added (Motor
  is in `_OTHER_PIECES`, referenced not tabled).
- `configs/__init__.py` docstring: the `demo_75mm_highland` worked-example paragraph is replaced by
  one pointing at `configs/scenarios/demo.py` (a real motor + an airframe with `Sections`, mass
  model on) — the subpackage list stays.
- Registry `__init__.py` docstrings (five): history lines naming removed modules are trimmed to
  the current one-entry state (one sentence each; no behaviour).
- `configs/schema.py:98` comment example `"demo_75mm"` → `"demo"`.
- `data/motors/README.md`: "used by" cells for `Cesaroni_2060K570-17A.eng` and `placeholder.csv`
  updated (no file added or removed in `data/`).

---

## 33.5 D-76 — `s0.m` from the composed mass

**Where:** `configs/schema.py::assemble`, step (3), immediately after `s0` is chosen. Nowhere else —
not `_pad_state` (it takes only `site`, and an explicit `sc.s0` needs the same treatment), not
`Config.derive`.

```python
s0 = sc.s0 if sc.s0 is not None else _pad_state(p.site)
# (4) D-76: with the mass model on, the integrator reads mass from y[M], not
#     weight.m (sim/dynamics.py) -- start it at the composed launch mass.
if p.weight.m_d is not None and s0.m == 0.0:
    s0 = s0._replace(m=p.weight.m)
return Config(name=sc.name, params=p, s0=s0, notes=sc.notes)
```

**Condition (D-81):** mass model on (`p.weight.m_d is not None`, evaluated *after* `overrides`, so an
override that turns the model on or changes `weight.m` is honoured) **and** `s0.m == 0.0` (the `State`
default, never a valid mass with the model on since `m >= m_d > 0`). A caller-supplied non-zero
`s0.m` is kept verbatim. The check runs **before** `_replace`, so with the model off `s0` is the very
object `_pad_state`/`sc.s0` produced — `tests/test_config_pieces.py::test_explicit_s0_is_passed_through_untouched`
(`is` identity, mass model off) keeps passing.

**Removes:** the `dataclasses.replace(... s0=_config.s0._replace(m=...))` patch at the bottom of
`configs/scenarios/demo_75mm_k570.py` (back to `CONFIG = SCENARIO.config`) and the same patch in
`tests/test_config_migration.py::test_demo_75mm_k570_isp_and_endpoints_motors_agree_on_apogee`.

**Pins it must not move — all of them** (the full list is §33.7): every constant-mass config keeps
`s0.m == 0.0` (so the toy / study `State` pins with default `m=0.0` hold), and the one mass-on config
already had `s0.m = weight.m` through the patch (so `configs.get("demo_75mm_k570")` is equal before
and after, and the Step-81 block holds).

**New tests (append to `tests/test_config_pieces.py`):** (1) mass-on scenario, derived `s0` →
`config.s0.m == config.params.weight.m`; (2) mass-on, explicit `s0` without `m` → filled;
(3) mass-on, explicit `s0` with `m=2.5` → kept 2.5; (4) mass model switched on through
`overrides={"weight.m_d": ...}` over a mass-off motor → filled from the overridden params;
(5) mass-off → `s0.m == 0.0`. Use an `"isp"` motor with every mass field explicit (the
`test_motor_pieces` style) so no motor file is read.

**Known limit, not fixed here (R3):** `Config.derive`/`Variant.apply` keep `s0` as-is, so a later
`weight.m` override on a mass-on `Config` does not re-sync `s0.m`. D-82's guards cover the two apps
that do this; the general fix is a backlog candidate (§33.11).

## 33.6 Test changes, file by file

Only these files change; every change is listed. "Re-point" = same assertion, different source.

| file | change |
|---|---|
| `tests/config_variants.py` | **new** (§33.3.2) |
| `tests/test_config_pieces.py` | append the five D-76 tests (§33.5); nothing else |
| `tests/test_configs.py` | Toy pins: LHS → `config_variants.TOY_05KG` (RHS literals unchanged). `test_demo_75mm_params_pin_demo_baseline_exactly` → `study_vehicle.CONFIG.params == _study_75mm_literal()`, a **new independent `Params` literal** in this file (the §33.3.1 numbers, typed out) — F2's tautology becomes a real pin; the s0 pin → `study_vehicle.CONFIG.s0`. Derive/variant tests: `configs.get("demo_75mm")` → `study_vehicle.CONFIG`, expected name `"study_75mm+heavier"`. Fresh-interpreter test imports `configs.scenarios.demo`. Source pins: run.py/select_conditions → `'configs.get("demo")'` (the `"Weight("` / `"math.pi / 2"` absence checks stay); compare_motors → `'return study_vehicle.CONFIG.params'` and `'study_vehicle.CONFIG'` present, `"Weight(m=1.5"` absence stays. Registry-integrity tests unchanged (generic). |
| `tests/test_config_migration.py` | **Delete** `test_demo_75mm_airbrake_params_equal_demo_75mm_params`, `test_toy_05kg_notes_pin_exactly`, `test_demo_75mm_notes_pin_exactly`, `test_demo_75mm_airbrake_notes_pin_exactly` (`--list-configs` text / identity of entries that no longer exist). `get_scenario` test → `"demo"`; asserts rocket `"demo"`, motor `"cti_k570"`, site/weather unchanged. Flat-module test → `study_vehicle.CONFIG.params/.s0`. Rocket-groups tests → `study_vehicle.ROCKET`/`.CONFIG` and `config_variants.TOY_05KG_ROCKET`/`TOY_05KG`. Highland tests → `config_variants.HIGHLAND` (same assertions; group equality against `study_vehicle.CONFIG`). **Add** `test_every_test_variant_flies`, parametrised over `config_variants.ALL`. Step-81 block: `"demo_75mm_k570"` → `"demo"`, `from configs.rockets import demo`; the equivalence test uses `config_variants.CTI_K570_ISP`; its patch line goes in Step 85. |
| `tests/test_config_registries.py` | `test_scenarios_registry_is_populated_by_step_73`: subset → `{"demo"}`. D-59 composition test: `configs.motors.get("cti_k570_isp")` → `config_variants.CTI_K570_ISP`. |
| `tests/test_motor_pieces.py` | `test_configs_names_after_step_81` → `set(configs.names()) == {"demo"}` (rename to `..._after_step_91`); docstring of the D-70 import test ("the four pre-phase seeds still read nothing") → one sentence; its assertion holds unchanged (the only registered scenario reads exactly the K570 file). |
| `tests/test_weight_aero_tradeoff.py` | `_demo_cfg()` → `study_vehicle.CONFIG`. `test_compare_main_default_scenarios_writes_artifacts` → `compare_main([])`, names `study_75mm...`. Comma test → `monkeypatch.setitem(configs.scenarios.SCENARIOS, "toy_05kg", config_variants.TOY_05KG)`, then `["--config", "demo,toy_05kg"]`; assert the CSV name column is exactly `{demo, toy_05kg}`. Derive labels like `demo_75mm_t5_test` may stay (free text). **Add** two D-82 guard tests (surface refuses `configs.get("demo")`; single-name compare refuses it). |
| `tests/test_motor_selection.py` | **No edit to existing tests** (`_demo_baseline()` keeps name and value). **Append** one D-82 guard test (mass-on baseline refused before any `run_sim`, monkeypatched to fail if called). |
| `tests/test_airbrake_sizing.py` | `_CFG = study_vehicle.CONFIG` (Step 88). `test_end_to_end_against_demo_75mm_airbrake_for_every_named_spec` → runs `SPECS` against `configs.get("demo")`, renamed `..._against_demo_...` (Step 90). Nothing else. |

Expected count after Step 91: 485 − 4 (deleted notes/identity tests) − 8 (the two
registry-parametrised "flies" tests drop from 5 cases to 1 each) + 2 (variants fly) + 5 (D-76) +
3 (D-82) = **483**. The developer reports the exact count per step against this arithmetic.

## 33.7 Re-records vs. bit-for-bit pins

**Must stay bit-for-bit (any movement means the step is wrong):** the two toy exact pins (now
against the fixture composition); the study-vehicle params/s0 pins (now non-tautological); all of
`test_motor_selection.py`; every numeric expectation in `test_weight_aero_tradeoff.py` and in the
`test_airbrake_sizing.py` property tests; the Step-81 composed-mass / `I_sp` / burnout / equivalence
checks; the D-77 RK45 pins in `test_integrate.py`; everything not named in §33.6.

**Intended changes (re-records, user-visible):**

1. `apps/airbrake_sizing/targets.py` `SPECS` — keys and numbers per §33.4.4.
2. Default runs of `run.py`, `run_cfd_conditions.py`, `run_airbrake.py` fly the K570 demo
   (single-run apogee 5946.74 m; gravity sweep 5946.74 / 5949.77 / 5956.17 m; atmosphere sweep
   6107.01 / 6118.62 m; CFD conditions M ≈ 1.05–2.6; airbrake burnout solve `C_dA ≈ 0.0016031`).
   None of these is pinned by a test.
3. `--list-configs` prints one line (`demo: ...`) instead of five.
4. App 5 printed/CSV names `study_75mm`, `study_75mm+heavy_sleek`, `study_75mm+light_draggy`
   (numbers unchanged).
5. The test-string re-records listed in §33.6 (names only, no numbers).

---

## 33.8 Decision log (D-79 … D-83)

Each fork carries a recommendation; none is decided by this document. D-78 (one demo) and D-76
(`s0.m`) are user-approved inputs.

| ID | recommendation | why, in one line | step |
|---|---|---|---|
| D-79 | (a) the 1.5 kg / 75 mm constant-mass vehicle leaves `configs/` for `apps/common/study_vehicle.py` as the baseline of Apps 3/5 | on the mass-model-on demo their mass axes go silently flat (F3) and their literals are calibrated to 1.5 kg (F4) — following the demo is a study re-baselining, not a cleanup | 86 |
| D-80 | (a) rename rocket + scenario `demo_75mm_k570` → `demo`; keep `cti_k570`, `origin_msl`, `isa_dry_calm` | the old name is wrong (the airframe is 54 mm); the other three names describe real content | 89 |
| D-81 | (b) fill `s0.m` whenever the mass model is on **and** `s0.m == 0.0` | catches the same bug for an explicit `s0` written without `m`, never overwrites a deliberate mass | 85 |
| D-82 | (a) fail-fast `ValueError` in App 3 / App 5 on a mass-model-on baseline | turns F3's silent flat axis into a clear message; costs three small checks | 87 |
| D-83 | (a) keep the demo's numbers as built (Mach ≈ 2.6, 5.95 km) | Step 81 is approved as built; a cleanup should not re-tune physics | — |

**D-79 — where the constant-mass study vehicle lives.** *Purpose: Apps 3 and 5 need a baseline whose
`weight.m` actually drives the flight and matches their 1.5 kg literals.*

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **(a) `apps/common/study_vehicle.py`, an unregistered study input (recommended)** | `configs/` holds exactly one demo, as asked; App 3/5 outputs and **all** their tests stay bit-for-bit; same home rule as `MOTORS`/`SCENARIOS`/`SPECS` (§30.3); F2's tautological pin becomes a real one | a second vehicle still exists in the tree (outside `configs/`), which the user may read as "two demos"; App 5's `--config` needs a "no name = study vehicle" default (`cli.py` +1 parameter) | ~1 step, no re-records in Apps 3/5 |
| (b) Apps 3/5 follow `demo` with a constant-mass adapter (`weight.m_d=None`) and re-tuned literals (mass band, variants, per-motor casings re-sized to a 54 mm / 3.2 kg vehicle) | literally one vehicle everywhere | a **study re-baselining** (the D-72(c) kind): `motors.py`/`scenarios.py` literals re-derived, closed-form checks in `test_motor_selection.py` re-pinned, App 3's H-class motors on 3.2 kg barely fly; a design task, not a cleanup | 2-3 steps, every App 3/5 number moves |
| (c) Apps 3/5 follow `demo` with the mass model on, and become mass-model-aware (sweep `s0.m` and airframe mass instead of `weight.m`) | the most physical end state | a new feature in two apps plus (b)'s re-tuning | a phase of its own |
| (d) keep `demo_75mm` registered in `configs/` | zero work | contradicts D-78 | — |

**Recommendation: (a).** (b)/(c) are honest later options if the user wants the studies on a real
motor; they belong with the B24/B25 mass-geometry backlog, not here.

**D-80 — registry naming.** (a) **`demo` for rocket and scenario (recommended)** — one obvious name
(`--config demo`), fixes the "75mm" misnomer on a 54 mm airframe; cost: one rename step, Step-81
tests re-pointed by name. (b) keep `demo_75mm_k570` — zero churn, a wrong diameter in the only
demo's name forever. (c) `demo_54mm_k570` — descriptive, but long and implies "one of several".
Motor/site/weather keep their names under every option (`cti_k570` is a real product;
`origin_msl`/`isa_dry_calm` name the defaults they pin).

**D-81 — which `s0` D-76 fills.** (a) derived `s0` only — narrowest, but an explicit `State(...)`
without `m=` silently re-creates the bug. **(b) mass on and `s0.m == 0.0` (recommended)** — covers
both paths; `0.0` is never valid with the model on; a deliberate `s0.m` is respected. (c) always
overwrite when the model is on — simplest, but discards a caller's deliberate mass (e.g. a mid-flight
start state).

**D-82 — guarding the constant-mass studies.** **(a) `ValueError` when the baseline has
`weight.m_d is not None` — App 3 `compare_motors` pre-flight, App 5 `build_surface` and single-name
`_resolve_configs` (recommended)**: F3 can never produce a plausible-looking flat result, and
`--config demo` on App 5 explains itself; it blocks a mass-aware use of these apps until D-79 (c)
exists. (b) warn and continue — output still wrong. (c) no guard — `--config demo` on App 5 prints a
flat surface with no hint. `MotorEntry` overrides that would themselves switch the model on are left
alone (`motors.py` promises that path) — R4.

**D-83 — the demo's numbers.** **(a) keep as built (recommended)** — Step 81 is approved as built, no
churn in the Step-81 block; but peak Mach ≈ 2.6 under a constant `C_x = 0.5`, the regime
`demo_75mm`'s own notes called "not defensible", and App 2's CFD set becomes supersonic. (b) re-size
the airframe (measured: 75 mm / 3.0 kg → 3606 m, Mach ≈ 1.55; 98 mm / 5.0 kg → 2265 m, Mach ≈ 1.0) —
still transonic under a constant drag model; a physics edit inside a cleanup. (c) keep, add a
Mach-dependent drag table later — fixes the cause, needs aero data (backlog). With (a), one sentence
in `configs/scenarios/demo.py`'s module docstring states the Mach caveat.

---

## 33.9 Risks

- **R1 — reading "study vehicle" as a second demo.** D-79(a) keeps a 75 mm vehicle in the tree. The
  orchestrator should put this to the user in plain words: "configs/ has one demo; Apps 3 and 5 keep
  their own fixed test vehicle next to their motor list / variant list, because they are
  constant-mass studies calibrated to it."
- **R2 — `test_motor_pieces` purges `configs.*` from `sys.modules` and re-imports it** (D-70 test).
  Objects built before the purge (`study_vehicle`, `config_variants`) are instances of the *old*
  `configs.schema` classes; dataclass `==` across old/new classes is `False`. Compare `Params`
  groups (`sim.*` classes, never purged) and names, not `Rocket`/`Motor`/`Scenario` objects — the
  §33.6 assertions already do. The developer also runs each touched test file in isolation.
- **R3 — stale `s0.m` after `derive`.** See §33.5; guarded for Apps 3/5 by D-82, open elsewhere.
- **R4 — App 3 entries that switch the mass model on** would start at `s0.m` from the study
  vehicle (`0.0`) — the same bug D-76 fixes at assembly. Not reachable today (no entry does it);
  backlog note, not code.
- **R5 — slower default runs.** A demo flight is 57.6 s simulated / 0.07 s wall vs 0.03 s; App 4's
  end-to-end test grows from ~4 to ~8 s of solves. Suite time impact is seconds, not minutes.
- **R6 — stale comments** in tests that say "run.py's placeholder scenario" (`test_dynamics`,
  `test_control`, `test_plotting`) describe their own literal Params, not `configs/`; left as
  history, not edited (keeps the test diff to the named set).
- **R7 — docs drift.** `dev/docs/architecture.md`, `roadmap.md`, `CLAUDE.md` § «Особенности проекта»
  (configs line) and `dev/docs/index.md` mention the old names; owned by documentation/orchestrator
  after Step 91, not by these tickets. LaTeX stays frozen.

---

## 33.10 Implementation tickets (Steps 85-91)

Same Files/Spec/Do/Check/Commit shape as §32.11. One step = one commit; full suite after each
(`python -m pytest -q`, background, ~4 min; baseline **485/485**). Phase gate for every step:
(1) suite green with the count reported against §33.6's arithmetic; (2) no pin from §33.7's
bit-for-bit list moved; (3) `git diff --stat` = the ticket's boundaries; (4) no `dev/docs/latex/` file.

```
85 (D-76) ───────────────┐
                         ├─→ 88 (tests off doomed entries) ─┐
86 (study vehicle) ──────┤                                  ├─→ 89 (rename) → 90 (apps → demo) → 91 (delete)
                         └─→ 87 (guards) ───────────────────┘
```

- **85 ∥ 86** have disjoint boundaries (`parallel_safe: true`), but worktree mode is off — run them
  one after the other in the main tree. Everything else is strictly sequential (shared test files).

### [Step 85] D-76 — `assemble()` starts the mass state at the composed mass

- **Module/boundaries:** `configs/schema.py` (`assemble` only); `configs/scenarios/demo_75mm_k570.py`
  (delete the patch, `CONFIG = SCENARIO.config`, drop `import dataclasses`); `tests/test_config_pieces.py`
  (append); `tests/test_config_migration.py` (delete the patch lines + their comment in the
  equivalence test only).
- **Assignee:** developer · **depends_on:** [] · **parallel_safe:** true (vs 86)
- **Spec slice:** §33.5; D-81.
- **Do:** the four-line block in §33.5, condition exactly `p.weight.m_d is not None and s0.m == 0.0`,
  evaluated after overrides, `_replace` only inside the `if`. Five new tests (§33.5).
- **Check:** suite 485 + 5 = 490; `configs.get("demo_75mm_k570").s0` equal to its pre-step value
  (assert in the report, measured before/after); `test_explicit_s0_is_passed_through_untouched` green
  unedited; every toy/demo_75mm s0 pin green.
- **Commit:** `Step 85 (Phase 2.16): assemble() seeds s0.m from weight.m when the mass model is on (D-76)`

### [Step 86] The constant-mass study vehicle moves next to its studies (D-79)

- **Module/boundaries:** new `apps/common/study_vehicle.py`; `apps/common/cli.py`;
  `apps/motor_selection/compare_motors.py` (`_demo_baseline`, `main`, docstrings);
  `apps/weight_aero_tradeoff/{trade_surface,compare_configs,scenarios}.py` (defaults, docstrings);
  `tests/test_configs.py`; `tests/test_weight_aero_tradeoff.py`. **No `configs/` file** — `demo_75mm`
  stays registered (unused by apps) until Step 91.
- **Assignee:** developer · **depends_on:** [] · **parallel_safe:** true (vs 85)
- **Spec slice:** §33.3.1, §33.4.3 (minus the guard), §33.4.5 (minus the guards), §33.6 rows
  `test_configs.py` (study-vehicle pins, derive/variant, compare_motors source pins — **not** the
  run.py/select_conditions/toy rows) and `test_weight_aero_tradeoff.py` (minus the comma test and
  guard tests).
- **Do:** create the module (numbers byte-for-byte from `configs/rockets/demo_75mm.py` +
  `configs/motors/placeholder.py`, notes verbatim from `configs/scenarios/demo_75mm.py`); add
  `_study_75mm_literal()` to `test_configs.py` and point both demo pins at the study vehicle;
  `cli.py` `default=None` + `resolve_config(args, fallback=...)`; App 5 defaults; App 3 sources.
- **Check:** `study_vehicle.CONFIG.params == configs.get("demo_75mm").params` and `.s0` equal (probe
  in the report — the move is a no-op); `tests/test_motor_selection.py` untouched and green;
  `python -m apps.weight_aero_tradeoff.compare_configs` prints `study_75mm` rows with the same apogees
  as before; App 4 `--config` still works with a string default. Count unchanged (490 after 85).
- **Commit:** `Step 86 (Phase 2.16): apps/common/study_vehicle -- Apps 3/5 own their constant-mass baseline`

### [Step 87] Constant-mass studies refuse a mass-model-on baseline (D-82)

- **Module/boundaries:** `apps/motor_selection/compare_motors.py` (pre-flight guard);
  `apps/weight_aero_tradeoff/trade_surface.py` (`build_surface`), `compare_configs.py`
  (`_resolve_configs`); append-only `tests/test_motor_selection.py`; `tests/test_weight_aero_tradeoff.py`.
- **Assignee:** developer · **depends_on:** [86] · **parallel_safe:** false
- **Spec slice:** §33.4.3/§33.4.5 guard bullets; D-82; F3.
- **Do:** three `ValueError`s naming the config and saying why (mass read from `y[M]`, `weight.m`
  inert); raised before any `run_sim`. Tests build the mass-on input from
  `configs.get("demo_75mm_k570")` (renamed in 89 — the name edit then belongs to 89).
- **Check:** +3 tests (493); `run_sim` monkeypatched to fail proves no integration happens; all App 3/5
  numbers unchanged.
- **Commit:** `Step 87 (Phase 2.16): Apps 3/5 refuse a mass-model-on baseline instead of a flat result`

### [Step 88] Tests stop reading the entries that are about to go

- **Module/boundaries:** new `tests/config_variants.py`; `tests/test_configs.py` (toy pins),
  `tests/test_config_migration.py`, `tests/test_config_registries.py` (D-59 test only),
  `tests/test_weight_aero_tradeoff.py` (comma test), `tests/test_airbrake_sizing.py` (`_CFG` only).
  **No `configs/` or `apps/` file.**
- **Assignee:** developer · **depends_on:** [85, 86] · **parallel_safe:** false
- **Spec slice:** §33.3.2; §33.6 rows for those files. Where a row says `"demo"`, use the interim
  name `demo_75mm_k570` (Step 89 renames); the run.py/select_conditions source pins are Step 90's.
- **Do:** build the variants by moving piece literals verbatim; re-point per §33.6; delete the four
  tests listed there; add `test_every_test_variant_flies`. The comma test may keep
  `"demo_75mm_k570,toy_05kg"` until Step 89 renames it.
- **Check:** `rg -n 'get\("(toy_05kg|demo_75mm|demo_75mm_airbrake|demo_75mm_highland)"\)|motors\.(get\("cti_k570_isp"\)|cti_k570_isp)|sites import highland|weather import breezy' tests/test_*.py`
  returns only the two `test_configs.py` source-pin strings (Step 90 changes them); toy pins and
  highland assertions unchanged in value; count 493 − 4 + 2 = 491.
- **Commit:** `Step 88 (Phase 2.16): tests/config_variants -- test-only pieces leave the registry`

### [Step 89] The one demo is called `demo` (D-80)

- **Module/boundaries:** `configs/rockets/demo_75mm_k570.py` → `configs/rockets/demo.py`;
  `configs/scenarios/demo_75mm_k570.py` → `configs/scenarios/demo.py` (`git mv`, then edit names and
  the D-83 Mach sentence in the docstring); `configs/rockets/__init__.py`, `configs/scenarios/__init__.py`
  (`_MODULES` lines); tests that name `demo_75mm_k570` (`test_config_migration`, `test_motor_pieces`
  names set — interim set with `"demo"` in place of `"demo_75mm_k570"`, `test_weight_aero_tradeoff`,
  `test_motor_selection` guard test); `test_configs.py` fresh-interpreter import.
- **Assignee:** developer · **depends_on:** [87, 88] · **parallel_safe:** false
- **Spec slice:** §33.2 (rename rows), D-80, D-83.
- **Do:** pure rename — no number in either module changes.
- **Check:** `configs.get("demo")` equals the pre-step `configs.get("demo_75mm_k570")` field by field
  except `name`; count unchanged (491); `rg demo_75mm_k570` over `configs/ apps/ tests/ run*.py` empty.
- **Commit:** `Step 89 (Phase 2.16): rename the K570 demo to demo (D-80)`

### [Step 90] run.py, App 2 and App 4 fly the demo

- **Module/boundaries:** `run.py`; `apps/cfd_conditions/select_conditions.py`;
  `apps/airbrake_sizing/{solve_cda,targets}.py`; `tests/test_configs.py` (two source pins);
  `tests/test_airbrake_sizing.py` (end-to-end test only).
- **Assignee:** developer · **depends_on:** [89] · **parallel_safe:** false
- **Spec slice:** §33.4.1, §33.4.2, §33.4.4; §33.7 re-record list items 1-2.
- **Do:** as specified; re-measure every `SPECS` number on the demo and write the measured values
  (F6 is the expectation, the measurement is the authority).
- **Check:** count unchanged (491); the report lists the **before/after table** of §33.7 item 2 as
  actually printed by `python run.py`, `python run_cfd_conditions.py`, `python run_airbrake.py`
  (each `--spec`); `timer_3850m` deploy time sits between burnout and apogee; `when_to_pop` returns
  ≈ burnout time.
- **Commit:** `Step 90 (Phase 2.16): run.py, CFD conditions and airbrake sizing default to the demo`

### [Step 91] Delete everything the demo replaces

- **Module/boundaries:** delete `configs/rockets/{toy_05kg,demo_75mm}.py`,
  `configs/motors/{placeholder,synthetic_large,cti_k570_isp}.py`, `configs/sites/highland_1500m.py`,
  `configs/weather/breezy_isa.py`, `configs/scenarios/{toy_05kg,demo_75mm,demo_75mm_airbrake,demo_75mm_highland}.py`;
  edit the five registry `__init__.py`, `configs/__init__.py` (docstring), `configs/schema.py:98`
  (comment), `configs/scenarios/_TEMPLATE_scenario.py`; `tests/test_config_registries.py`
  (scenarios-populated set), `tests/test_motor_pieces.py` (names set `{"demo"}`, docstring);
  `data/motors/README.md` ("used by" cells). **No `data/` file deleted.**
- **Assignee:** developer · **depends_on:** [90] · **parallel_safe:** false
- **Spec slice:** §33.2 in full; §33.4.6; §33.6 rows for those two test files.
- **Do:** delete, then fix every importer the suite reports (there should be none outside the named
  files — if there is one, stop and report rather than widen the boundary).
- **Check:** each subpackage lists `__init__.py`, one `_TEMPLATE_*.py`, one piece; `configs.names() ==
  ["demo"]`; `rg -n "toy_05kg|demo_75mm|highland_1500m|breezy_isa|synthetic_large|cti_k570_isp|motors\.placeholder" configs apps run*.py`
  returns nothing (hits in `tests/config_variants.py`, `apps/common/study_vehicle.py` docstring
  provenance and `data/` file names are expected — list them); templates import cleanly; suite
  **483** (§33.6).
- **Commit:** `Step 91 (Phase 2.16): configs/ holds one template and one demo per piece (D-78)`

## 33.11 Not in this ticket set

- Docs sync (`architecture.md`, `roadmap.md`, `dev/docs/index.md`, CLAUDE.md configs line) — after
  Step 91, documentation agent / orchestrator. LaTeX — frozen (Step 84 deferred).
- D-79 (b)/(c) — Apps 3/5 on a real motor with the mass model on; backlog candidate next to B24/B25.
- `Config.derive` re-syncing `s0.m` (R3) and App 3 mass-on entries (R4) — backlog candidate.
- A Mach-dependent drag table for the demo (D-83 (c)).
- `data/` trimming — D-72 stands.

---

## 33.12 User decisions (2026-10-15) and the added Step 92

- **D-79 → (a)** study vehicle in `apps/common/study_vehicle.py`. **D-80 → (a)** `demo`. **D-81 → (a)**. **D-82 → (a)**.
- **D-83 → (a) keep the numbers, amended by the user:** "raise a warning that Mach is > 0.8". The
  docstring caveat alone is not enough — the run itself must say so.

### [Step 92] Mach > 0.8 under a Mach-blind drag model warns at run time (D-83)

- **Module/boundaries:** the module that owns the post-run result (`sim/integrate.py` or
  `sim/report.py` — the developer picks the narrowest seam that every entry point, `run.py` and all
  five apps, passes through, and states why); a new test file `tests/test_mach_warning.py`. No
  `configs/` file, no other test file.
- **depends_on:** [Step 90] (the demo is then the default everywhere, so the warning is visible).
- **Do:** after a run, compute the peak flight Mach number over the trajectory (speed relative to
  the air mass, i.e. wind-relative, divided by the local speed of sound from the same atmosphere
  model the run used). If it exceeds **0.8** and `params.aero.model` is Mach-independent
  (`"constant"` or `"linearized"`; `"table"` is exempt because it can encode Mach), emit one
  `warnings.warn(..., MachRangeWarning)` (a `UserWarning` subclass defined next to the check) with
  the peak Mach, the time it occurs and the aero model name, e.g.
  `peak Mach 2.61 at t=1.9 s exceeds 0.8 with Mach-independent aero model "constant" -- drag is not
  credible above ~0.8; use aero.model="table" with Mach-dependent data`. Pure diagnostic: the
  integration result is unchanged, no numeric pin moves.
- **Check:** the demo run warns (peak Mach ≈ 2.6); a subsonic run (`study_75mm` / placeholder
  motor) does not; a `"table"` run above 0.8 does not; `pytest.warns` / `warnings.catch_warnings`
  based. Full suite green with the same count + the new tests, no expected value edited.
- **Commit:** `Step 92 (Phase 2.16): warn when peak Mach exceeds 0.8 under a Mach-independent drag model`

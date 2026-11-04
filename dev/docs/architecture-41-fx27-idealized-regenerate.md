## Кратко (RU)

- Документ описывает Phase 2.23, Step 148 (D-176): roadmap F2 ("automate the idealized rocket
  workflow"), подход (b) — regenerate-script, решённый пользователем 2026-11-03/04.
- Ключевая находка (уже зафиксирована в D-176): `rockets_ideal.py`/`rockets_dm.py` сегодня хранят
  ТОЛЬКО fx27-портированные числа — 4 из них это AC-3 оракул (неприкосновенный, `tests/
  test_fx27_port.py`), 4 остальных (dm "## DM" половина) — тоже портированная арифметика fx27, не
  вывод солвера этого проекта. Значит "модуля с собственным решённым идеалом этого проекта" пока
  вообще не существует — его нужно создать с нуля, а не "регенерировать" что-то старое.
- Решение: новый модуль `projects/fx27/campaigns/cspace/rockets_ideal_own.py` — 8 констант + 8
  вариантов `Rocket` (pro54_transition/pro75 x dc/dm x mass/drag), вычисленных через уже
  существующий `apps/optimization/apogee_targeting/solve.py` (B41) против текущих `rockets.py`/
  `rockets_dm.py`. Плюс одноразовый скрипт `generate_rockets_ideal_own.py` рядом — ручной запуск
  при изменении базовой ракеты, переписывает ровно 8 именованных строк по regex-якорю на имя
  константы, больше ничего в файле не трогает.
- **Гвардрейл**: скрипт физически не открывает `rockets_ideal.py`/`rockets_dm.py` на запись (путь
  записи — захардкоженная константа на новый файл); громкое предупреждение в докстринге обоих
  новых файлов противопоставляет "это НАШ вывод солвера, не оракул fx27" явно. Существующие файлы
  не редактируются вообще — ноль правок, весь гвардрейл живёт в новых файлах.
- `SCENARIOS`/`SCENARIOS_DM` **не трогаются** — их словари запинены тестом на точное множество из
  7 ключей (`test_cspace_has_exactly_the_seven_comparison_rows` и dm-аналог); добавление 8 новых
  строк туда сломало бы эти пины. Новый тестовый файл строит свои Scenario-объекты сам, locally.
- Новые тесты только в новом файле `tests/test_rockets_ideal_own.py` (не трогает
  `test_fx27_port.py`): 8 параметризованных сборочных тестов + unit-тесты механизма записи
  (regex-замена, round-trip через `tmp_path`, без вызова реального солвера) + 1-2
  plausibility-теста (не числовой пин — эти значения ожидаемо дрейфуют).
- 4 тикета (RIO-1..RIO-4), последовательные (каждый зависит от предыдущего) — маленький,
  плотно связанный шаг, параллельный запуск не даёт выгоды. Approval-гейта пользователя не
  требуется (additive, уже одобренный стек, без новых зависимостей).

## Table of contents

- [SS41.1 Scope](#ss411-scope)
- [SS41.2 Module name and placement](#ss412-module-name-and-placement)
- [SS41.3 Solver-call mapping (the subtlety: cx vs. cx_scale)](#ss413-solver-call-mapping-the-subtlety-cx-vs-cx_scale)
- [SS41.4 `rockets_ideal_own.py` — code skeleton](#ss414-rockets_ideal_ownpy--code-skeleton)
- [SS41.5 `generate_rockets_ideal_own.py` — write mechanism and code skeleton](#ss415-generate_rockets_ideal_ownpy--write-mechanism-and-code-skeleton)
- [SS41.6 Guardrail against touching the oracle files](#ss416-guardrail-against-touching-the-oracle-files)
- [SS41.7 Why `SCENARIOS`/`SCENARIOS_DM` are not extended](#ss417-why-scenariosscenarios_dm-are-not-extended)
- [SS41.8 Test plan](#ss418-test-plan)
- [SS41.9 Directory structure diff](#ss419-directory-structure-diff)
- [SS41.10 Rejected options](#ss4110-rejected-options)
- [SS41.11 Tickets](#ss4111-tickets)
- [SS41.12 Open decisions for the user gate](#ss4112-open-decisions-for-the-user-gate)

## SS41.1 Scope

Phase 2.23, Step 148 (D-176). Closes roadmap F2 (`projects/fx27/docs/vehicle-dynamics-roadmap.md`
section "F2 — automate the 'idealized rocket' workflow"), approach (b) — already decided by the
user (2026-11-03): a regenerate-script, same shape as architecture-40's aero-table generator
(`campaigns/cspace/data/aero/generate_dm_tables.py`).

D-176's own pre-flight check (orchestrator, before handoff) found that neither existing idealized
module is actually "this project's own idealized rocket, solved by this project's own solver":

- `rockets_ideal.py`'s 4 constants are the **AC-3 acceptance oracle** — fx27's own already-solved
  figures, hardcoded, immutable (D-172). `tests/test_fx27_port.py` grades this project's solver
  *against* them. Never touched by anything built here.
- `rockets_dm.py`'s 4 "## DM" constants are likewise ported fx27 arithmetic (the module's own
  comments show the fx27 math, e.g. `5.835 - 0.9267`), not this project's solver output either.
  Also never touched.

So this step **creates a new module from scratch** holding this project's own solved idealized
variants, computed via the already-promoted, campaign-agnostic solver
(`apps/optimization/apogee_targeting/solve.py`, B41/architecture-39) against the current base
rockets (`rockets.py`/`rockets_dm.py`), plus a one-off script to (re)compute and commit those 8
numbers whenever the base rocket's mass/C_x changes. Target apogee 3000 m AGL throughout (matches
every existing cspace idealized variant).

Scope boundary — zero edits to any existing file:

| File | Touched? |
|---|---|
| `rockets.py`, `rockets_dm.py`, `rockets_ideal.py` | No — read-only inputs |
| `scenarios.py`, `scenarios_dm.py` | No — see SS41.7 |
| `apps/optimization/apogee_targeting/solve.py` | No — used as-is, already generic |
| `tests/test_fx27_port.py` | No — new tests go in a new file |

Only 3 new files are created (SS41.9).

## SS41.2 Module name and placement

`projects/fx27/campaigns/cspace/rockets_ideal_own.py` — sibling of `rockets_ideal.py`/
`rockets_dm.py`, same directory, same `dataclasses.replace`-onto-base-rocket shape. The `_own`
suffix is the whole point: it must read, at a glance, as "the project's *own* solve", in direct
lexical contrast with `rockets_ideal`/`rockets_dm` (fx27's own ported figures). Alternatives
considered and rejected in SS41.10.

The regenerate script lives next to the module it writes, not in `data/aero/` (that precedent's
location is about being a sibling of the CSVs it produces, not a general "generators" directory):
`projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py`.

## SS41.3 Solver-call mapping (the subtlety: cx vs. cx_scale)

All 8 values are produced via `apps/optimization/apogee_targeting/solve.py`, target apogee 3000 m
AGL — but **not uniformly through the two named wrappers**. `estimate_cx` overrides
`scenario.overrides["aero.C_x"]`; that is the correct quantity for the dc base rockets (`Aero.
model="constant"`, `C_x` used directly) but `C_x` has no effect under `model="table"` — the dm
base rockets' idealized-drag quantity is `Aero.cx_scale` (the Step 105 dispersion-scale hook,
applied after table dispatch regardless of model — `rockets_dm.py`'s own docstring, confirmed
against `apps/sim/engine/aero.py` line ~847: `if p.aero.cx_scale != 1.0: base = base._replace(C_x
= base.C_x * p.aero.cx_scale)`). `estimate_cx` cannot be reused unmodified for the dm case.

Mapping actually used:

| Quantity | Config | Solver call | Overridden field |
|---|---|---|---|
| mass | dc (pro54_transition, pro75) | `estimate_airframe_mass(scenario, target_apogee_agl=3000.0)` | `rocket.airframe.m` (generic, same for dc/dm) |
| mass | dm (pro54_transition_dm, pro75_dm) | `estimate_airframe_mass(scenario, target_apogee_agl=3000.0)` | ditto — no dm-specific change needed |
| drag | dc | `estimate_cx(scenario, target_apogee_agl=3000.0)` | `overrides["aero.C_x"]` |
| drag | dm | `solve_for_target_apogee(scenario, with_cx_scale, baseline=scenario.rocket.aero.cx_scale, bracket=(0.0, 2.0), target_apogee_agl=3000.0)` with a local `with_cx_scale(s, x) -> dataclasses.replace(s, overrides={**s.overrides, "aero.cx_scale": x})` | `overrides["aero.cx_scale"]` |

`"aero.cx_scale"` is a valid override key for the same reason `"aero.C_x"` already is:
`apps/sim/engine/params.replace` (the function `Scenario.overrides` is applied through, `apps/
sim/schema.py` line ~398) is a fully generic dotted-path `dataclasses.replace` — it does not special-
case field names, so no change to `apps/sim/engine/params.py` is needed.

Bracket `(0.0, 2.0)` for `cx_scale` mirrors `estimate_cx`'s own default bracket (same shape,
dimensionless multiplicative quantity) and comfortably contains fx27's own ported dm-ideal
`cx_scale` figures (0.5843, 1.4954 — `rockets_dm.py`) as an order-of-magnitude sanity check, even
though this project's own solved values are expected to differ from those (different solver,
different baseline — SS41.1).

Scenario inputs: `SCENARIOS["pro54_transition"]` / `SCENARIOS["pro75"]` (dc,
`campaigns/cspace/scenarios.py`) and `SCENARIOS_DM["pro54_transition_dm"]` /
`SCENARIOS_DM["pro75_dm"]` (dm, `campaigns/cspace/scenarios_dm.py`) — read-only imports, exactly
how `runs/cspace/ideal_mass.py`/`ideal_drag.py` already source their scenario.

## SS41.4 `rockets_ideal_own.py` — code skeleton

```python
"""projects/fx27/campaigns/cspace/rockets_ideal_own.py -- THIS PROJECT's OWN
solved idealized cspace variants (Phase 2.23, Step 148, architecture-41,
roadmap F2 approach (b)), for pro54_transition and pro75 (dc AND dm base),
target apogee 3000 m AGL.

CONTRAST WITH rockets_ideal.py / rockets_dm.py -- read those two modules'
own docstrings first if this is confusing. Both hold fx27's OWN
already-solved figures, hardcoded, ported verbatim from fx27's own
data/cspace/rockets_ideal.py -- the AC-3 acceptance ORACLE this project's
solver is graded against (tests/test_fx27_port.py). Those 8 numbers are a
frozen regression oracle and MUST NEVER be touched, regenerated, or
overwritten by anything, ever.

This module is the opposite: every constant below is THIS project's OWN
apps/optimization/apogee_targeting/solve.py output, re-derived by running
generate_rockets_ideal_own.py (same directory) against the current
rockets.py/rockets_dm.py base figures. These numbers are EXPECTED TO
DRIFT whenever the base rocket's mass/C_x changes (e.g. once real
CAD/CFD data lands -- roadmap F2's whole motivation) -- they are not a
pin, not an oracle, not fx27 data. Never add one of these values to an
oracle comparison; never copy an fx27-sourced number in here; never let
this module's values leak into rockets_ideal.py/rockets_dm.py.

Re-run after any rockets.py/rockets_dm.py base mass/C_x edit (from the repo root -- `-m`,
not a bare script path, see SS41.5's own note):
    python -m projects.fx27.campaigns.cspace.generate_rockets_ideal_own

Mirrors rockets_ideal.py's and rockets_dm.py's own `dataclasses.replace`-
onto-base-rocket shape exactly (one field group changed per variant,
never two) -- only the source of the solved number differs.
"""

from __future__ import annotations

import dataclasses

from projects.fx27.campaigns.cspace import rockets, rockets_dm

# >>> GENERATED -- do not hand-edit the 8 lines below. Run
# generate_rockets_ideal_own.py instead: it replaces exactly these 8
# lines by name (regex-anchored, see that script's _substitute_constant),
# nothing else in this file. Placeholders below are pre-first-run guesses
# only, order-of-magnitude, not solved. <<<
PRO54_TRANSITION_IDEAL_OWN_MASS_KG = 4.2900          # PLACEHOLDER -- run the generator
PRO54_TRANSITION_IDEAL_OWN_DRAG_CX = 0.2500          # PLACEHOLDER -- run the generator
PRO75_IDEAL_OWN_MASS_KG = 8.0000                     # PLACEHOLDER -- run the generator
PRO75_IDEAL_OWN_DRAG_CX = 0.8300                     # PLACEHOLDER -- run the generator
PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG = 4.9000       # PLACEHOLDER -- run the generator
PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE = 0.5800  # PLACEHOLDER -- run the generator
PRO75_DM_IDEAL_OWN_MASS_KG = 7.9000                  # PLACEHOLDER -- run the generator
PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE = 1.5000            # PLACEHOLDER -- run the generator
# <<< GENERATED <<<

_NOTE = "This project's own apps/optimization/apogee_targeting solve, target 3000 m AGL -- NOT fx27 data; re-derive via generate_rockets_ideal_own.py."

PRO54_TRANSITION_IDEAL_OWN_MASS = dataclasses.replace(
    rockets.PRO54_TRANSITION,
    name="pro54_transition_ideal_own_mass",
    airframe=dataclasses.replace(rockets.PRO54_TRANSITION.airframe, m=PRO54_TRANSITION_IDEAL_OWN_MASS_KG),
    notes=_NOTE,
)

PRO54_TRANSITION_IDEAL_OWN_DRAG = dataclasses.replace(
    rockets.PRO54_TRANSITION,
    name="pro54_transition_ideal_own_drag",
    aero=dataclasses.replace(rockets.PRO54_TRANSITION.aero, C_x=PRO54_TRANSITION_IDEAL_OWN_DRAG_CX),
    notes=_NOTE,
)

PRO75_IDEAL_OWN_MASS = dataclasses.replace(
    rockets.PRO75,
    name="pro75_ideal_own_mass",
    airframe=dataclasses.replace(rockets.PRO75.airframe, m=PRO75_IDEAL_OWN_MASS_KG),
    notes=_NOTE,
)

PRO75_IDEAL_OWN_DRAG = dataclasses.replace(
    rockets.PRO75,
    name="pro75_ideal_own_drag",
    aero=dataclasses.replace(rockets.PRO75.aero, C_x=PRO75_IDEAL_OWN_DRAG_CX),
    notes=_NOTE,
)

PRO54_TRANSITION_DM_IDEAL_OWN_MASS = dataclasses.replace(
    rockets_dm.PRO54_TRANSITION_DM,
    name="pro54_transition_dm_ideal_own_mass",
    airframe=dataclasses.replace(rockets_dm.PRO54_TRANSITION_DM.airframe, m=PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG),
    notes=_NOTE,
)

PRO54_TRANSITION_DM_IDEAL_OWN_DRAG = dataclasses.replace(
    rockets_dm.PRO54_TRANSITION_DM,
    name="pro54_transition_dm_ideal_own_drag",
    aero=dataclasses.replace(rockets_dm.PRO54_TRANSITION_DM.aero, cx_scale=PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE),
    notes=_NOTE,
)

PRO75_DM_IDEAL_OWN_MASS = dataclasses.replace(
    rockets_dm.PRO75_DM,
    name="pro75_dm_ideal_own_mass",
    airframe=dataclasses.replace(rockets_dm.PRO75_DM.airframe, m=PRO75_DM_IDEAL_OWN_MASS_KG),
    notes=_NOTE,
)

PRO75_DM_IDEAL_OWN_DRAG = dataclasses.replace(
    rockets_dm.PRO75_DM,
    name="pro75_dm_ideal_own_drag",
    aero=dataclasses.replace(rockets_dm.PRO75_DM.aero, cx_scale=PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE),
    notes=_NOTE,
)
```

Naming convention note: `_OWN` is inserted immediately before the quantity suffix
(`_MASS_KG`/`_DRAG_CX`/`_DRAG_CX_SCALE`), in the same slot `_DM` already occupies relative to the
family name — e.g. `PRO54_TRANSITION_IDEAL_MASS_KG` (fx27, dc) vs.
`PRO54_TRANSITION_IDEAL_OWN_MASS_KG` (this project, dc) vs.
`PRO54_TRANSITION_DM_IDEAL_MASS_KG` (fx27, dm) vs.
`PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG` (this project, dm). Reading any one name tells you both
axes (whose solve, dc or dm) without needing to open the file.

## SS41.5 `generate_rockets_ideal_own.py` — write mechanism and code skeleton

**Write mechanism decision: per-name regex line substitution, not AST codegen.** Justification:
exactly 8 well-known constant names, each already a single `NAME = <literal>` line with a stable,
greppable left-hand side; a full AST-based rewrite (e.g. `libcst`) would need a new dependency and
far more code to achieve the same guarantee this regex gives directly: match
`^{NAME} = .+$` (MULTILINE) and assert the count is **exactly 1** before writing anything — if the
module's structure ever drifts (name typo'd, line duplicated, line removed), the script raises
loudly instead of silently writing 0 or N replacements. This mirrors `generate_dm_tables.py`'s own
"manual tool, re-run on source change, output checked into git" spirit while being simpler than
CSV regeneration (no header/grid logic — 8 independent line replacements).

```python
#!/usr/bin/env python
"""projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py -- ONE-OFF
regenerate script (architecture-41 SS41.5, roadmap F2 approach (b)). Run
manually whenever rockets.py/rockets_dm.py's base dry mass or C_x change
(e.g. once real CAD/CFD data lands). NOT imported at runtime; NOT
exercised by pytest's collection (its pure string-substitution helper is
unit-tested directly in tests/test_rockets_ideal_own.py -- the solver
calls themselves are not re-run under pytest, see that file's own
docstring).

Computes the 8 solved constants rockets_ideal_own.py hand-types
(2 configs [pro54_transition, pro75] x 2 base-types [dc, dm] x 2
quantities [mass, drag]), target apogee 3000 m AGL, via
apps/optimization/apogee_targeting/solve.py against this project's own
SCENARIOS/SCENARIOS_DM (campaigns/cspace/scenarios.py,
campaigns/cspace/scenarios_dm.py), then rewrites rockets_ideal_own.py's
own 8 named constant lines in place (regex-anchored by name) -- nothing
else in that file is touched.

GUARDRAIL (explicit, not just by convention): this script's only write
target is _TARGET below, HARDCODED to rockets_ideal_own.py -- there is
no code path, flag, or argument that points it anywhere else. It does
import rockets_dm.py (via scenarios_dm.SCENARIOS_DM) to build its dm
solver INPUTS -- that is a read of the dm BASE rockets' current dry
mass/C_x, not of rockets_dm.py's own _IDEAL_ constants, and never
produces a write back to that file or to rockets_ideal.py. Those two
modules hold the AC-3 oracle (tests/test_fx27_port.py) and a frozen
ported arithmetic record respectively -- never open either for writing,
from this script or any other.

Run (from the repo root -- `-m`, not a bare script path, a plain
`python path/to/this_file.py` puts the script's own directory on
sys.path[0] instead of the repo root, breaking the apps.*/projects.*
absolute imports above with ModuleNotFoundError; confirmed during RIO-4,
same convention as every runs/* entry point):
    python -m projects.fx27.campaigns.cspace.generate_rockets_ideal_own
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from apps.optimization.apogee_targeting.solve import (
    estimate_airframe_mass,
    estimate_cx,
    solve_for_target_apogee,
)
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM

TARGET_APOGEE_M = 3000.0
_TARGET = Path(__file__).resolve().parent / "rockets_ideal_own.py"
_CX_SCALE_BRACKET = (0.0, 2.0)  # SS41.3 -- same shape as estimate_cx's own default bracket


def _with_cx_scale(scenario, x: float):
    return dataclasses.replace(scenario, overrides={**scenario.overrides, "aero.cx_scale": x})


def _solved_values() -> "dict[str, float]":
    dc_t, dc_75 = SCENARIOS["pro54_transition"], SCENARIOS["pro75"]
    dm_t, dm_75 = SCENARIOS_DM["pro54_transition_dm"], SCENARIOS_DM["pro75_dm"]
    return {
        "PRO54_TRANSITION_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dc_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_IDEAL_OWN_DRAG_CX": estimate_cx(dc_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dc_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_IDEAL_OWN_DRAG_CX": estimate_cx(dc_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dm_t, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE": solve_for_target_apogee(
            dm_t, _with_cx_scale, dm_t.rocket.aero.cx_scale, _CX_SCALE_BRACKET, TARGET_APOGEE_M
        ).required,
        "PRO75_DM_IDEAL_OWN_MASS_KG": estimate_airframe_mass(dm_75, target_apogee_agl=TARGET_APOGEE_M).required,
        "PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE": solve_for_target_apogee(
            dm_75, _with_cx_scale, dm_75.rocket.aero.cx_scale, _CX_SCALE_BRACKET, TARGET_APOGEE_M
        ).required,
    }


def _substitute_constant(source: str, name: str, value: float) -> str:
    """Pure string transform -- no file I/O -- so tests/test_rockets_ideal_own.py
    can unit-test it directly against synthetic strings/tmp_path files,
    never against the real committed module."""
    pattern = re.compile(rf"^{re.escape(name)} = .+$", re.MULTILINE)
    n = len(pattern.findall(source))
    if n != 1:
        raise RuntimeError(
            f"generate_rockets_ideal_own: expected exactly 1 line matching "
            f"{name!r}, found {n} -- refusing to write (module structure "
            "drifted from what this script expects; fix rockets_ideal_own.py "
            "by hand before re-running)."
        )
    return pattern.sub(f"{name} = {value:.4f}", source, count=1)


def _rewrite_file(path: Path, values: "dict[str, float]") -> None:
    source = path.read_text(encoding="utf-8")
    for name, value in values.items():
        source = _substitute_constant(source, name, value)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    values = _solved_values()
    _rewrite_file(_TARGET, values)
    for name, value in values.items():
        print(f"{name} = {value:.4f}")
    print(f"wrote {_TARGET}")


if __name__ == "__main__":
    main()
```

Atomicity: a direct overwrite (`write_text`) is used rather than write-to-temp-then-`os.replace`.
Justified by context: manual, infrequent, git-tracked — if a run is interrupted mid-write (or the
guardrail `RuntimeError` fires, which happens strictly *before* any write since `_rewrite_file`
only calls `path.write_text` once, after every substitution has already succeeded in memory), the
file is simply reverted with `git checkout` (project convention — ask before running it, per
`CLAUDE.md`'s git-safety section). `_rewrite_file`'s all-substitutions-before-one-write structure
already means a partial/garbled write cannot happen from a substitution failure; the only residual
risk is an OS-level crash mid-`write_text`, which is an acceptable, extremely low-probability risk
for a manual one-off tool with git as the safety net.

## SS41.6 Guardrail against touching the oracle files

Two layers, both static (no runtime enforcement needed, per the task's own framing — "keep it
simple"):

1. **Code-level**: `_TARGET` in `generate_rockets_ideal_own.py` is a hardcoded `Path` constant
   pointing only at `rockets_ideal_own.py`. There is no parameter, flag, or code path that can
   redirect a write anywhere else. The script's only *reads* of `rockets_dm.py`/`rockets.py` go
   through `SCENARIOS`/`SCENARIOS_DM` (importing the current *base* rockets as solver inputs) —
   it never opens either file's source text, and the regex substitution logic (`_substitute_
   constant`) is only ever invoked against `_TARGET`'s own text.
2. **Docstring-level**: both new files' module docstrings open with an explicit contrast against
   `rockets_ideal.py`/`rockets_dm.py` (quoted in full in SS41.4/SS41.5) — framed so a future reader
   skimming either file cannot come away thinking these are oracle data, or that the generator
   might ever touch the oracle files.

Deliberately **not done**: no comment is added to `rockets_ideal.py`/`rockets_dm.py` pointing at
the new module. This keeps the step's edit footprint at exactly zero existing files touched
(SS41.1's table) — see SS41.10 for the explicit rejection of that alternative.

## SS41.7 Why `SCENARIOS`/`SCENARIOS_DM` are not extended

Both dicts are part of the AC-3 pin surface: `tests/test_fx27_port.py::test_cspace_has_exactly_
the_seven_comparison_rows` and `::test_cspace_dm_has_exactly_the_seven_comparison_rows` assert
`set(SCENARIOS) == {<exactly 7 keys>}` / `set(SCENARIOS_DM) == {<exactly 7 keys>}`. Adding 8 new
rows (4 dc + 4 dm) across the two dicts would fail both pins immediately, and `scenarios.py`'s own
docstring already documents this naming convention as "LOAD-BEARING" for `point/plots.py`'s
styling — not a boundary to lean on casually. Per this step's own scope (SS41.1: zero edits to
existing files), the 8 new `Rocket` variants stay in `rockets_ideal_own.py` as plain importable
constants; any test or future run-script that wants a `Scenario` wrapping one of them builds it
locally (same literal shape `scenarios.py`'s own rows already use — `Scenario(name=..., rocket=...,
motor=..., site=SITE, weather=WEATHER)`), the same way `tests/test_rockets_ideal_own.py` does
(SS41.8).

## SS41.8 Test plan

New file only: `tests/test_rockets_ideal_own.py` (does not touch `tests/test_fx27_port.py`, per
that file's own "ONLY test file this port touches" boundary note — this is a new, separate step's
test surface, same precedent as architecture-39's `tests/test_apogee_targeting.py`).

**No new numeric pin/oracle.** These 8 values are *expected* to drift whenever `rockets.py`/
`rockets_dm.py` change (by design — that is the entire point of F2). Any assertion against a
specific decimal value here would be a false pin.

1. **Assembly smoke tests** (mirrors `test_fx27_port.py::test_cspace_scenario_assembles`'s
   pattern) — parametrized over the 8 new `Rocket` constants, each wrapped in a locally-built
   `Scenario` (SS41.7) and run through `assemble()`:
   ```python
   @pytest.mark.parametrize("rocket_name", sorted(_ALL_EIGHT))
   def test_rocket_ideal_own_variant_assembles(rocket_name):
       cfg = assemble(_scenario_for(rocket_name))
       assert cfg.params.weight.m > 0.0
       assert cfg.params.weight.m_d is not None
   ```
2. **Write-mechanism unit tests**, against `_substitute_constant`/`_rewrite_file` directly — pure
   string/`tmp_path` tests, **never call `_solved_values()`/`main()`** (that would invoke the real
   solver and, if `_TARGET` were not also faked, could overwrite the real committed module — both
   must be avoided):
   - `test_substitute_constant_replaces_the_named_line_only`: synthetic multi-line source string
     with 2+ `NAME = value` lines; assert only the targeted name's line changes, byte-for-byte
     identical otherwise.
   - `test_substitute_constant_raises_if_name_not_found_exactly_once`: 0-match and 2-match
     synthetic fixtures both raise `RuntimeError`, no exception swallowed.
   - `test_rewrite_file_round_trips_through_tmp_path`: write a synthetic file (containing all 8
     real constant names with dummy values, same shape as the real module's generated block) to
     `tmp_path`, call `_rewrite_file(tmp_file, {name: new_value, ...})`, re-read the file, assert
     every targeted line now shows the new value and every other line (docstring, blank lines,
     `Rocket` constructions) is untouched. This is the "write once, re-read, matches" round-trip
     the task asked for.
3. **Plausibility checks (optional, included)** — same style as
   `test_dm_scenario_apogee_is_plausible_against_its_dc_namesake`: 1-2 representative cases (one
   dc, one dm — not all 8, to bound runtime; a full `run_sim` per case), asserting the *committed*
   module's variants fly to something near 3000 m AGL within a generous band (e.g. 1500-6000 m, or
   whatever band the developer finds sensible — this is a wiring sanity check only, not a solver-
   accuracy check: a wildly different apogee would indicate the wrong field was overridden, a
   typo'd bracket, or a stale regenerate run, not a tight numeric regression).

## SS41.9 Directory structure diff

```
projects/fx27/campaigns/cspace/
    rockets_ideal_own.py              (NEW -- SS41.4)
    generate_rockets_ideal_own.py     (NEW -- SS41.5)
    rockets_ideal.py                  (untouched -- AC-3 oracle)
    rockets_dm.py                     (untouched -- ported dm arithmetic)
    rockets.py, scenarios.py, scenarios_dm.py   (untouched)

tests/
    test_rockets_ideal_own.py         (NEW -- SS41.8)
    test_fx27_port.py                 (untouched)
```

## SS41.10 Rejected options

- **Module name alternatives** — `rockets_ideal_solved.py` (rejected: `rockets_ideal.py` is
  *also* "solved", by fx27, so this name does not contrast anything); `rockets_own_ideal.py`
  (rejected: less readable sort-order next to its two siblings; `_own` as a suffix groups
  alphabetically right after `rockets_ideal.py` in a directory listing, which is a small but real
  readability win). `rockets_ideal_own.py` (chosen) contrasts cleanly and sorts adjacently.
- **Approach (a), live-compute at import time** (roadmap F2's own alternative) — already rejected
  by the user 2026-11-03 before this step was scoped (slower import, couples a plain-data config
  module to a numerical solver, against this project's "config modules are plain data" convention
  elsewhere). Not revisited here.
- **Full AST-based rewrite (e.g. `libcst`) for the regenerate script** — rejected: new dependency,
  materially more code, for a guarantee the regex approach already gives (exactly-one-match
  assertion before any write). Appropriate if this module ever needed to *add or remove* constants
  programmatically; it does not — the 8 names are fixed.
- **Single-dict/table-driven constant store instead of 8 named `float` literals** (e.g. a
  `dict[str, float]` or a small dataclass) — rejected to keep `rockets_ideal_own.py` visually and
  structurally identical to `rockets_ideal.py`/`rockets_dm.py` (named module-level constants,
  immediately diffable against those two files by a future reader); a different shape here would
  undercut the explicit "same pattern, different source" contrast this module is trying to convey.
- **Cross-reference comment added to `rockets_ideal.py`/`rockets_dm.py` pointing at the new
  module** — rejected (SS41.6) to keep this step's edit footprint at zero existing files touched;
  the new files' own docstrings already carry the contrast in the direction a reader is more
  likely to need it (arriving at the new module and wondering how it relates to the old ones).
- **Wiring the 8 new variants into `SCENARIOS`/`SCENARIOS_DM`** — rejected, would break the
  existing exact-7-key pins (SS41.7); not requested by the task either.

## SS41.11 Tickets

### [RIO-1] New module: `rockets_ideal_own.py` (placeholder constants + 8 `Rocket` variants)
- **Module/boundaries:** `projects/fx27/campaigns/cspace/rockets_ideal_own.py` (new file only). No
  existing file under `projects/fx27/` is edited.
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true
Spec: this doc, SS41.4 (full code skeleton — write it close to verbatim, including the
module-level contrast docstring and the `# >>> GENERATED <<<` marker comment) + SS41.2 (naming
rationale). Placeholder numeric values are fine at this stage (real values land in RIO-4) as long
as the module imports cleanly and every one of the 8 `Rocket` variants assembles. Follow the `tdd`
skill: write `tests/test_rockets_ideal_own.py`'s assembly tests (ticket RIO-3) alongside this, not
strictly after.

### [RIO-2] New regenerate script: `generate_rockets_ideal_own.py`
- **Module/boundaries:** `projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py` (new file
  only).
- **Assignee:** developer
- **depends_on:** [RIO-1] (the script's regex substitution is anchored against RIO-1's exact 8
  constant names/lines — must exist first, same identifiers, same single-line-per-constant shape)
- **parallel_safe:** false
Spec: this doc, SS41.5 (full code skeleton: `_solved_values`, `_substitute_constant`,
`_rewrite_file`, `main`) + SS41.3 (the dc-vs-dm solver-call mapping — `estimate_cx` for dc,
`solve_for_target_apogee` + a local `_with_cx_scale` setter for dm; do not try to force the dm
case through `estimate_cx`, it overrides the wrong field) + SS41.6 (guardrail: `_TARGET` hardcoded,
no write path to `rockets_ideal.py`/`rockets_dm.py`). Do **not** run `main()` against the real
file as part of this ticket's own dev-loop testing — exercise `_substitute_constant`/`_rewrite_
file` against synthetic/`tmp_path` fixtures only (ticket RIO-3 owns those tests); the real run
happens once, deliberately, in RIO-4.

### [RIO-3] New tests: `tests/test_rockets_ideal_own.py`
- **Module/boundaries:** `tests/test_rockets_ideal_own.py` (new file only). Does not edit `tests/
  test_fx27_port.py` or any other existing test file.
- **Assignee:** developer
- **depends_on:** [RIO-1, RIO-2] (imports both new modules)
- **parallel_safe:** false
Spec: this doc, SS41.8 (all three test groups: 8 parametrized assembly tests, 3 write-mechanism
unit tests against `_substitute_constant`/`_rewrite_file` via `tmp_path`/synthetic strings, 1-2
plausibility checks). Follow `test_fx27_port.py`'s/`test_apogee_targeting.py`'s house style (plain
`assert`, no fixtures/`conftest.py`). Hard constraint, repeated from SS41.8: no test in this file
may call `generate_rockets_ideal_own.main()` or `_solved_values()` against the real committed
module path — every write-mechanism test must target a `tmp_path` file, never `_TARGET` itself.

### [RIO-4] Run the generator for real; verify the oracle is untouched
- **Module/boundaries:** `projects/fx27/campaigns/cspace/rockets_ideal_own.py` (content only — the
  8 placeholder values are overwritten with real solved values by running RIO-2's script, not by
  hand-editing). No other file is touched.
- **Assignee:** developer (closing gate for this step) or qa
- **depends_on:** [RIO-1, RIO-2, RIO-3]
- **parallel_safe:** false
Spec: this doc, SS41.1's scope table + SS41.6's guardrail. Run `python projects/fx27/campaigns/
cspace/generate_rockets_ideal_own.py` once from the repo root; `git diff` the result and confirm
**only** `rockets_ideal_own.py` changed (the 8 generated lines, nothing else in that file) and
that `rockets_ideal.py`/`rockets_dm.py` show zero diff (`git status`/`git diff --stat` both — this
is the guardrail's actual proof, not just a code-review read-through). Then run `tests/
test_rockets_ideal_own.py` and the full suite per this project's chunking convention (`CLAUDE.md`
"Профиль проекта" ловушки) and confirm every numeric pin outside this step's own two new files
is unchanged — in particular `tests/test_fx27_port.py`'s 4 AC-3 oracle tests must show the exact
same pass/fail outcome and measured values as before this step.

## SS41.12 Open decisions for the user gate

None found that need a user "yes" before implementation starts. This is an incremental,
additive-only step on an already-approved stack (no new dependency, no new external service, no
stack pivot, and — per SS41.1's table — zero edits to any existing file): per this role's own
"incremental architecture of an already existing stage" rule, it goes through the standard flow
(this document) without a `grilling` round, same precedent as architecture-39/40's own conclusion.

Approach (b) itself (regenerate-script over live-compute) was already decided by the user on
2026-11-03 (roadmap F2's own "Decided" note) and reconfirmed in D-176 — not re-opened here.

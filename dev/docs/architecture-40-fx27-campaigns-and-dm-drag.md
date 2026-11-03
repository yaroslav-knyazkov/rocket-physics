## Кратко (RU)

- Документ описывает Phase 2.22, Step 145 (решение D-174): два аддитивных изменения над уже
  принятым портом fx27 (architecture-38/39), без смены стека.
- **Часть A** — пользователь уже одобрил целевые формы (AskUserQuestion, 2026-11-03): `cspace/` +
  `euroc/` (код и их CSV) переезжают в `campaigns/cspace/` и `campaigns/euroc/`; `runs/` делится
  по соревнованию (`runs/cspace/*.py`, `runs/euroc/*.py`), убирая префиксы `cspace_`/`euroc_` из
  имён файлов. Чисто механический рефактор: обновляются все внутренние импорты, `_paths.py`,
  `README.md`, импорт-блок `tests/test_fx27_port.py`. **Важная поправка к брифу**: в
  `tests/test_apogee_targeting.py` импортов `projects.fx27.*` на самом деле нет (проверено grep) —
  только упоминание в докстринге; трогать этот файл в Части A не нужно.
- **Часть B** — порт недостающего Mach-зависимого ("dm") контента cspace из коммита-прародителя
  порта (сиблинг `fx27/simulation`'s `data/cspace/rockets.py`/`rockets_ideal.py`, секции "DRAG
  MACH DEPENDENT" / "## DM"): 3 новых `Rocket` (`pro54_transition_dm`/`pro54_equal_dm`/`pro75_dm`,
  `aero.model="table"`) + 4 идеализированных dm-варианта (только transition/pro75, как и у dc).
- **Ключевое техническое решение**: голая 2-колонная кривая `Mach,Cd` fx27 (rocketpy'шный формат)
  превращается в валидную v1-таблицу `apps/sim/engine/aero.py` (`alpha_deg,M,C_A,C_N,C_m,l1_m`) —
  минимальная прямоугольная сетка из 2 точек `alpha_deg` (-1/+1°, значения идентичны), `C_N=C_m=0`
  на каждой точке (инвариант Option C сохраняется), `l1_m=1.0` (тот же инертный плейсхолдер, что и
  у dc-ракет), без колонки `c_mq` (достаточно уже выставленного `Aero.c_mq=0.0`, наследуется из
  dc-родителя при `dataclasses.replace`). Таблицы — **генерируются один раз одноразовым скриптом**
  и коммитятся как статические файлы (`campaigns/cspace/data/aero/*.csv`), не строятся в runtime:
  `aero.py`'s загрузчик ожидает путь к файлу, а не программные данные, и соседний репозиторий не
  должен быть runtime-зависимостью.
- Подтверждено чтением `apps/sim/engine/aero.py`/`params.py`: идеализированный drag-вариант (`*
  0.5843`/`* 1.4954`) не требует второго файла — это `Aero.cx_scale` (готовый хук Step 105),
  применяемый ПОСЛЕ диспетчера модели независимо от `model`. Идеализированная масса — обычная
  подмена `airframe.m`.
- Новый отдельный словарь `SCENARIOS_DM` (НЕ смешивается с существующим `SCENARIOS`, который —
  часть поверхности пинов AC-3), новый run-скрипт `runs/cspace/comparison_dc_dm.py` (dc+dm, 14
  строк). `point/` не меняется вообще — его стиль именования (`"<family> (ideal mass)"`) уже
  обрабатывает `"pro75_dm"` как отдельную "семью" без всякого кода.
- Гейта одобрения пользователя не требуется — это аддитивный шаг на уже одобренном стеке (как
  D-173/Step 144), целевые формы Части A уже одобрены отдельным вопросом. Один момент для внимания
  оркестратора: новые "ideal" dm-числа (4.9083 кг и т.п.) — НЕ AC-3-подобный оракул (в отличие от
  dc), fx27 не даёт для них решённого апогея для проверки; это задокументировано явно, тесты их
  не пинуют численно, только sanity-проверка.

## Table of contents

- [SS40.1 Scope](#ss401-scope)
- [SS40.2 Part A — directory reorg](#ss402-part-a--directory-reorg)
- [SS40.3 Part B — the table-format design problem](#ss403-part-b--the-table-format-design-problem)
- [SS40.4 New Rocket/Scenario content — code skeletons](#ss404-new-rocketscenario-content--code-skeletons)
- [SS40.5 The generator script](#ss405-the-generator-script)
- [SS40.6 New run entry point: `comparison_dc_dm.py`](#ss406-new-run-entry-point-comparison_dc_dmpy)
- [SS40.7 Directory structure diff (before / after)](#ss407-directory-structure-diff-before--after)
- [SS40.8 Test plan](#ss408-test-plan)
- [SS40.9 Rejected options](#ss409-rejected-options)
- [SS40.10 Tickets](#ss4010-tickets)
- [SS40.11 Open decisions for the user gate](#ss4011-open-decisions-for-the-user-gate)

## SS40.1 Scope

Phase 2.22, Step 145 (D-174). Two independent, additive changes to `projects/fx27/`:

- **Part A** (SS40.2): reorganize `cspace/`+`euroc/`(+their data) into `campaigns/cspace/`+
  `campaigns/euroc/`, and split `runs/` by competition. Target shapes already approved by the user
  via `AskUserQuestion` on 2026-11-03 — not open for re-litigation here, only the mechanics.
- **Part B** (SS40.3-40.6): port the sibling repo's own "DRAG MACH DEPENDENT"/"## DM" content
  (cspace only — confirmed no euroc dm content exists, and the user declined speculative euroc dm
  work) that the original port scaffold (architecture-38) cut before picking it up.

**Correction to the task brief**: `tests/test_apogee_targeting.py` has **zero**
`projects.fx27.*` imports (`grep` confirms — only a docstring mention of "fx27" in an unrelated
context, no import line). Part A's test-file edit therefore touches `tests/test_fx27_port.py`
only; `test_apogee_targeting.py` needs no change in this step.

Out of scope (confirmed by reading): `projects/fx27/docs/` (another session's in-flight
brainstorming, untracked, explicitly out of scope per the brief); `dev/docs/architecture-38-*`/
`architecture-39-*`/`*-progress-notes.md`/`journal.md`/`status.json` (historical record, owned by
the orchestrator, left stale on purpose); any `apps/` engine change (the whole point of Part B is
that `apps/sim/engine/aero.py`'s existing `"table"` model already does everything needed — see
SS40.3); euroc dm content (none exists in the sibling, confirmed, and declined by the user).

## SS40.2 Part A — directory reorg

### SS40.2.1 Target tree (approved, mechanics only)

```
projects/fx27/
  _paths.py                      (unchanged location; anchors repointed, SS40.2.3)
  campaigns/
    __init__.py                  (new, empty docstring module)
    cspace/
      __init__.py, motors.py, rockets.py, rockets_ideal.py, scenarios.py, site.py, weather.py
      data/motors/*.csv          (2 files, was projects/fx27/data/motors/cspace/)
      [Part B adds rockets_dm.py, scenarios_dm.py, data/aero/ -- SS40.4/40.5]
    euroc/
      __init__.py, motors.py, rockets.py, scenarios.py, site.py, weather.py
      data/motors/*.csv          (27 files, was projects/fx27/data/motors/euroc-sweep/ --
                                   "-sweep" dropped, redundant once nested under euroc/)
  point/                         (unchanged -- not part of this reorg)
  runs/
    __init__.py                  (unchanged)
    cspace/
      __init__.py (new), point.py, comparison.py, ideal_mass.py, ideal_drag.py, airbrake.py
      [Part B adds comparison_dc_dm.py -- SS40.6]
    euroc/
      __init__.py (new), comparison.py, sweep.py
  docs/                          (untouched, out of scope)
```

Top-level `projects/fx27/data/` disappears entirely (both its CSV subtrees moved, its stray
`README.md` deleted — SS40.2.4).

### SS40.2.2 File-by-file git-mv map

Pure renames/moves, content unchanged except the import-line edits in SS40.2.3:

| Old path | New path |
|---|---|
| `cspace/__init__.py` | `campaigns/cspace/__init__.py` |
| `cspace/motors.py` | `campaigns/cspace/motors.py` |
| `cspace/rockets.py` | `campaigns/cspace/rockets.py` |
| `cspace/rockets_ideal.py` | `campaigns/cspace/rockets_ideal.py` |
| `cspace/scenarios.py` | `campaigns/cspace/scenarios.py` |
| `cspace/site.py` | `campaigns/cspace/site.py` |
| `cspace/weather.py` | `campaigns/cspace/weather.py` |
| `data/motors/cspace/*.csv` (2 files) | `campaigns/cspace/data/motors/*.csv` |
| `euroc/__init__.py` | `campaigns/euroc/__init__.py` |
| `euroc/motors.py` | `campaigns/euroc/motors.py` |
| `euroc/rockets.py` | `campaigns/euroc/rockets.py` |
| `euroc/scenarios.py` | `campaigns/euroc/scenarios.py` |
| `euroc/site.py` | `campaigns/euroc/site.py` |
| `euroc/weather.py` | `campaigns/euroc/weather.py` |
| `data/motors/euroc-sweep/*.csv` (27 files) | `campaigns/euroc/data/motors/*.csv` |
| `runs/cspace_point.py` | `runs/cspace/point.py` |
| `runs/cspace_comparison.py` | `runs/cspace/comparison.py` |
| `runs/cspace_ideal_mass.py` | `runs/cspace/ideal_mass.py` |
| `runs/cspace_ideal_drag.py` | `runs/cspace/ideal_drag.py` |
| `runs/cspace_airbrake.py` | `runs/cspace/airbrake.py` |
| `runs/euroc_comparison.py` | `runs/euroc/comparison.py` |
| `runs/euroc_sweep.py` | `runs/euroc/sweep.py` |
| `data/README.md` | **deleted** (confirmed byte-identical to the unrelated root `projects/data/README.md`, not about this folder — see the diff inspection recorded during this step's research) |
| — (new) | `campaigns/__init__.py`, `runs/cspace/__init__.py`, `runs/euroc/__init__.py` |

`_paths.py` **stays at `projects/fx27/_paths.py`** (not moved under `campaigns/`) — it is a pure
absolute-path anchor module; every caller (`cspace/motors.py`, `euroc/motors.py`) already imports
it as `from projects.fx27._paths import cspace_motor`/`euroc_motor`, an import line that needs NO
edit under this choice (only the module's *internal* anchor values change, SS40.2.3) — minimizes
the diff versus moving it too.

### SS40.2.3 Import-line edits (complete list — grep-verified, no other file in `projects/fx27/` imports `projects.fx27.*`)

Pattern: every `projects.fx27.cspace.X` -> `projects.fx27.campaigns.cspace.X`; every
`projects.fx27.euroc.X` -> `projects.fx27.campaigns.euroc.X`. `projects.fx27.point.*` and
`projects.fx27._paths` import lines are **unchanged** (neither moved).

| File (new path) | Import line(s) to edit |
|---|---|
| `campaigns/cspace/rockets_ideal.py` | `from projects.fx27.cspace.rockets import ...` -> `.campaigns.cspace.rockets` |
| `campaigns/cspace/scenarios.py` | `from projects.fx27.cspace import motors, rockets, rockets_ideal` -> `.campaigns.cspace`; `from projects.fx27.cspace.site import SITE` -> `.campaigns.cspace.site`; same for `.weather` |
| `campaigns/euroc/scenarios.py` | `from projects.fx27.euroc.motors import ...` -> `.campaigns.euroc.motors`; same for `.rockets`, `.site`, `.weather` |
| `runs/cspace/point.py` | `from projects.fx27.cspace.scenarios import SCENARIOS` -> `.campaigns.cspace.scenarios` |
| `runs/cspace/comparison.py` | same `cspace.scenarios` edit |
| `runs/cspace/ideal_mass.py` | `from projects.fx27.cspace.rockets_ideal import ...` -> `.campaigns.cspace.rockets_ideal`; `.cspace.scenarios` -> `.campaigns.cspace.scenarios` |
| `runs/cspace/ideal_drag.py` | same two edits as `ideal_mass.py` |
| `runs/cspace/airbrake.py` | `from projects.fx27.cspace.scenarios import SCENARIOS` -> `.campaigns.cspace.scenarios` |
| `runs/euroc/comparison.py` | `from projects.fx27.euroc.scenarios import generate_scenarios` -> `.campaigns.euroc.scenarios` |
| `runs/euroc/sweep.py` | `from projects.fx27.euroc.motors import ...` -> `.campaigns.euroc.motors`; same for `.rockets`, `.scenarios`, `.site`, `.weather` |
| `tests/test_fx27_port.py` | `from projects.fx27.cspace.rockets_ideal import (...)` -> `.campaigns.cspace.rockets_ideal`; `from projects.fx27.cspace.scenarios import SCENARIOS as CSPACE_SCENARIOS` -> `.campaigns.cspace.scenarios`; `from projects.fx27.euroc.motors import DEFERRED_MOTORS` -> `.campaigns.euroc.motors`; `from projects.fx27.euroc.scenarios import CANDIDATES, generate_scenarios` -> `.campaigns.euroc.scenarios` |

`_paths.py` itself needs its two anchor values (not import lines) repointed:

```python
MOTORS_CSPACE = _HERE / "campaigns" / "cspace" / "data" / "motors"
MOTORS_EUROC = _HERE / "campaigns" / "euroc" / "data" / "motors"
```

and (Part B, same file) a new third anchor added — see SS40.4.

`_paths.py`'s own docstring cites `projects/fx27/data/README.md` as the convention it deliberately
deviates from (rule 2 vs rule 1 of `datafiles.resolve`) — that file is deleted in this step
(SS40.2.4). Update the docstring's citation to point at the real surviving doc with the same
cwd-relative convention, `projects/data/README.md` (the unrelated, root-level personal-data doc —
confirmed identical content to the one being deleted, SS40.2.4), rather than leave a dangling
reference to a file that no longer exists.

### SS40.2.4 `data/README.md` deletion — confirmed safe

Read both files byte-for-byte during this step's research: `projects/fx27/data/README.md` and the
root `projects/data/README.md` are identical (the personal-data convention doc, not about this
port's bundled campaign data at all — `_paths.py`'s own docstring already calls this out as a
stray/misleading duplicate). Delete `projects/fx27/data/README.md` outright; the root copy is the
canonical one and is untouched.

### SS40.2.5 README.md updates

`projects/fx27/README.md`'s "Layout" section (data/motors paths, `runs/` filenames) and "How to
run" section (module paths) must be rewritten for the new tree — e.g.:

```
python -m projects.fx27.runs.cspace.point [--scenario NAME] [--validity]
python -m projects.fx27.runs.cspace.comparison [--validity]
python -m projects.fx27.runs.cspace.ideal_mass
python -m projects.fx27.runs.cspace.ideal_drag
python -m projects.fx27.runs.cspace.airbrake
python -m projects.fx27.runs.euroc.comparison [--validity]
python -m projects.fx27.runs.euroc.sweep
python -m projects.fx27.runs.cspace.comparison_dc_dm [--validity]     # new, Part B, SS40.6
```

The "Layout" tree block should be replaced with the structure in SS40.2.1 (abbreviated, matching
this doc's own tree). Every other section of the README (Option C explanation, AC-3 table, the
Mach>0.8 caveat, the 3 deferred motors) is prose that does not reference a file path and needs no
edit — leave it exactly as is except where it literally names a moved path.

## SS40.3 Part B — the table-format design problem

### SS40.3.1 Source data (given, not re-derived)

Three bare `Mach,Cd` CSVs (rocketpy's own `power_off_drag`/`power_on_drag` convention — no header,
2 columns, 121 rows, Mach 0.0 to 3.0 in steps of 0.025) from the sibling repo:
`import/aerodynamics/cspace/{pro54-transition,pro54-equal,pro75}-drag.csv`.

### SS40.3.2 Target format (`apps/sim/engine/aero.py`'s v1 table, confirmed by reading the loader)

Mandatory columns `alpha_deg,M,C_A,C_N,C_m` + exactly one of `l1_m`/`l_p_m`; a rectangular
`(M, alpha)` grid (`_load_table_impl`: every `M` value must repeat the identical `alpha_deg` set,
`M_col.size == n_M * n_a` exactly, or it raises `ValueError`). `c_mq` is optional (falls back to
`Params.aero.c_mq`, Step 44).

### SS40.3.3 Decisions, each confirmed against the loader/dispatch code read in full for this step

| Decision | Choice | Why |
|---|---|---|
| `alpha_deg` grid | 2 points, `{-1, +1}` deg, **identical** `C_A`/`C_N`/`C_m`/`l1_m` at both | Minimum rectangular grid `_load_table_impl` accepts (every existing shipped table in this repo uses >=3 points; a verified 1-point grid is plausible from reading `_reshape`/`np.interp`'s behaviour with a length-1 array, but relying on that undocumented edge case is needless risk for zero benefit — 2 points costs nothing and matches the module's own documented example shape). Both `-1 < 0 < +1` deg, so `table.alpha[0] > -90 deg` and `table.alpha[-1] < 90 deg` — `_table_axial_factor` applies `axial_flow_factor(alpha)` to `C_A`, the SAME treatment the dc rockets already get via `_constant_coeffs`. Since Option C keeps `|alpha|` tiny throughout every dm flight (frozen attitude), `axial_flow_factor` evaluates to exactly `1.0` everywhere it matters (`axial_flow_factor`'s own docstring: exactly `1.0` for `\|alpha\| <= 85 deg`) — the multiplication is a no-op in practice, bit-identical to not having it. |
| `C_N`, `C_m` | `0.0` at every grid point | Preserves `C_z = C_m = 0` exactly — the Option C invariant is unconditional (not model-dependent): a table model that returns nonzero `C_N`/`C_m` would silently break it. |
| `c_mq` column | **Omitted** — rely on the scalar fallback | `_table_coeffs`: no `c_mq` column + `cm_convention == "code"` (default, no header line needed) -> `C_mq_code = p.aero.c_mq`. The dm `Rocket`'s `Aero` is `dataclasses.replace`d from its dc sibling, which already carries `c_mq=0.0` — so the fallback gives `0.0` automatically, with less code than adding a redundant all-zero column. |
| `l1_m` vs `l_p_m` | **`l1_m`**, value `1.0` everywhere | Mirrors `cspace/rockets.py`'s own `_LENGTHS.l1 = 1.0` DYNAMICALLY INERT placeholder exactly (same reasoning: `C_z=C_m=c_mq=0` means this value never multiplies a nonzero quantity). Confirmed by reading `uses_l_p`/`_resolve_arm`: an `l1_m` (not `l_p_m`) table makes `uses_l_p(p)` return `False` for the table model, so `_resolve_arm` is a no-op (`return base` unchanged) — exactly the same "legacy arm, inert" code path the dc rockets already use via `Lengths.l1`, not the v2 station path. Using `l_p_m` instead would needlessly opt into `uses_l_p`'s extra `cg_station`/`misalign_deg==0` validation (`aero.py::validate`) for zero benefit. |
| `cx_scale` for the idealized-drag dm variants | **Confirmed**: `Aero.cx_scale` (Step 105 dispersion hook, `apps/sim/engine/params.py`), applied in `aero.py::coefficients` AFTER the model dispatch (`if p.aero.cx_scale != 1.0: base = base._replace(C_x=base.C_x * p.aero.cx_scale)`) — regardless of whether the model is `"constant"` or `"table"`. No second, pre-scaled CSV is needed; `*0.5843`/`*1.4954` become `dataclasses.replace(aero, cx_scale=0.5843)` etc., exactly mirroring how the dc idealized-drag variants already replace `aero.C_x` with a solved constant. | Read `aero.py` lines ~845-848 and `params.py`'s `Aero.cx_scale` field docstring directly to confirm this for this step — matches the task brief's reading. |
| Idealized-mass dm variants | Plain `airframe.m` override, `dataclasses.replace` | Identical in shape to the existing dc idealized-mass variants (`rockets_ideal.py`'s `PRO54_TRANSITION_IDEAL_MASS`/`PRO75_IDEAL_MASS`) — no new mechanism. |
| Static vs runtime table generation | **Generated once, committed as static files** | `apps/sim/engine/aero.py`'s `_load_table`/`datafiles.resolve` take a file path, not programmatic data — building the table at import time would mean writing a temp file as an import-time side effect (this project's established convention keeps config modules side-effect-free at import, same spirit as `_paths.py`'s own "one module owns the anchor" rule). The sibling repo is a one-time inventory source (same precedent as every other number in `cspace/`/`euroc/`, per `projects/fx27/README.md`'s "Provenance" section) and must not become a runtime dependency of `projects/fx27/campaigns/cspace/`. Matches the existing convention that `data/motors/*.csv` are themselves committed static files, not regenerated per run. |

## SS40.4 New Rocket/Scenario content — code skeletons

### SS40.4.1 `_paths.py` addition (same file as SS40.2.3's edits)

```python
AERO_CSPACE = _HERE / "campaigns" / "cspace" / "data" / "aero"

def cspace_aero(filename: str) -> str:
    """Absolute path to a cspace aero-table CSV under `campaigns/cspace/data/aero/`
    (SS40.4/SS40.5) -- same rationale as `cspace_motor`: an absolute path sidesteps
    `datafiles.resolve`'s cwd-relative rule 2, which is a silent foot-gun for a
    config literal imported from anywhere but the repo root."""
    return str(AERO_CSPACE / filename)
```

### SS40.4.2 New file: `campaigns/cspace/rockets_dm.py`

New file (existing `rockets.py`/`rockets_ideal.py` content stays byte-for-byte unchanged — purely
additive). Full skeleton:

```python
"""projects/fx27/campaigns/cspace/rockets_dm.py -- Mach-dependent ("dm")
drag variants of the 3 base cspace airframes (dev/docs/architecture-40-
fx27-campaigns-and-dm-drag.md SS40.4), porting the "DRAG MACH DEPENDENT"
half of fx27's own data/cspace/rockets.py that the original port scaffold
never picked up (SS40.1).

Each `*_DM` Rocket is `dataclasses.replace` of its already-ported dc
sibling (`rockets.PRO54_TRANSITION`/`PRO54_EQUAL`/`PRO75`) with `aero`
swapped to `model="table"` pointing at the Mach-dependent C_A(M) table
generated by `data/aero/generate_dm_tables.py` (SS40.5) -- nothing else
changes: same radius/S/d_ref (same body), same `c_mq=0.0` placeholder
(carried through unedited from the dc Aero), same inert `lengths`/
`sections`/`airframe.I`/`l` (Option C, C_z=C_m=c_mq=0 is still true: the
table's own C_N/C_m columns are 0.0 at every grid point -- SS40.3).

4 "ideal" dm variants mirror `rockets_ideal.py`'s existing pattern
exactly (only `pro54_transition`/`pro75` get one, `pro54_equal` never
does) -- idealized MASS is a plain `airframe.m` override; idealized DRAG
is `Aero.cx_scale` (Step 105 dispersion hook, applied after the table
dispatch regardless of model, `apps/sim/engine/aero.py`'s `coefficients`)
rather than a second, rescaled CSV -- SS40.3's confirmed reading.
"""

from __future__ import annotations

import dataclasses

from projects.fx27._paths import cspace_aero
from projects.fx27.campaigns.cspace import rockets

_TABLE_PRO54_TRANSITION = cspace_aero("pro54-transition-drag.csv")
_TABLE_PRO54_EQUAL = cspace_aero("pro54-equal-drag.csv")
_TABLE_PRO75 = cspace_aero("pro75-drag.csv")


def _dm_aero(base, table_path: str):
    # REQ: swap model+table only -- S/d_ref/c_mq/cx_scale/l_p/cm_convention all carried
    # through unedited from the dc sibling's own Aero (same radius, Option C invariant
    # preserved: the table's own C_N/C_m columns are 0.0, SS40.3).
    return dataclasses.replace(base, model="table", table=table_path)


PRO54_TRANSITION_DM = dataclasses.replace(
    rockets.PRO54_TRANSITION,
    name="pro54_transition_dm",
    aero=_dm_aero(rockets.PRO54_TRANSITION.aero, _TABLE_PRO54_TRANSITION),
    notes=(
        "fx27 data/cspace/rockets.py pro54_transition_dm: Mach-dependent C_A(M) table "
        "ported from import/aerodynamics/cspace/pro54-transition-drag.csv (SS40.3/SS40.5)."
    ),
)

PRO54_EQUAL_DM = dataclasses.replace(
    rockets.PRO54_EQUAL,
    name="pro54_equal_dm",
    aero=_dm_aero(rockets.PRO54_EQUAL.aero, _TABLE_PRO54_EQUAL),
    notes=(
        "fx27 data/cspace/rockets.py pro54_equal_dm: Mach-dependent C_A(M) table ported "
        "from import/aerodynamics/cspace/pro54-equal-drag.csv (SS40.3/SS40.5)."
    ),
)

PRO75_DM = dataclasses.replace(
    rockets.PRO75,
    name="pro75_dm",
    aero=_dm_aero(rockets.PRO75.aero, _TABLE_PRO75),
    notes=(
        "fx27 data/cspace/rockets.py pro75_dm: Mach-dependent C_A(M) table ported from "
        "import/aerodynamics/cspace/pro75-drag.csv (SS40.3/SS40.5)."
    ),
)

# fx27 hardcoded dm "ideal" figures (data/cspace/rockets_ideal.py's "## DM" half) -- NOT
# an AC-3-style solved oracle (unlike rockets_ideal.py's 4 dc figures): fx27's own
# comments ("- 0.9267 kg", "* 0.5843") read as a measured mass/drag delta applied to the
# dm rocket, not a fresh root-find against a stated target apogee -- no apples-to-apples
# oracle number exists to test these against (SS40.8). Kept as named constants for
# provenance/traceability only, same style as rockets_ideal.py's own constants.
PRO54_TRANSITION_DM_IDEAL_MASS_KG = 4.9083          # 5.835 - 0.9267
PRO54_TRANSITION_DM_IDEAL_DRAG_CX_SCALE = 0.5843
PRO75_DM_IDEAL_MASS_KG = 7.8663                     # 6.225 + 1.6413
PRO75_DM_IDEAL_DRAG_CX_SCALE = 1.4954

PRO54_TRANSITION_DM_IDEAL_MASS = dataclasses.replace(
    PRO54_TRANSITION_DM,
    name="pro54_transition_dm_ideal_mass",
    airframe=dataclasses.replace(PRO54_TRANSITION_DM.airframe, m=PRO54_TRANSITION_DM_IDEAL_MASS_KG),
    notes="fx27 data/cspace/rockets_ideal.py pro54_transition_dm_im: dry mass 5.835 - 0.9267 kg.",
)

PRO54_TRANSITION_DM_IDEAL_DRAG = dataclasses.replace(
    PRO54_TRANSITION_DM,
    name="pro54_transition_dm_ideal_drag",
    aero=dataclasses.replace(PRO54_TRANSITION_DM.aero, cx_scale=PRO54_TRANSITION_DM_IDEAL_DRAG_CX_SCALE),
    notes="fx27 data/cspace/rockets_ideal.py pro54_transition_dm_id: whole drag curve * 0.5843.",
)

PRO75_DM_IDEAL_MASS = dataclasses.replace(
    PRO75_DM,
    name="pro75_dm_ideal_mass",
    airframe=dataclasses.replace(PRO75_DM.airframe, m=PRO75_DM_IDEAL_MASS_KG),
    notes="fx27 data/cspace/rockets_ideal.py pro75_dm_im: dry mass 6.225 + 1.6413 kg.",
)

PRO75_DM_IDEAL_DRAG = dataclasses.replace(
    PRO75_DM,
    name="pro75_dm_ideal_drag",
    aero=dataclasses.replace(PRO75_DM.aero, cx_scale=PRO75_DM_IDEAL_DRAG_CX_SCALE),
    notes="fx27 data/cspace/rockets_ideal.py pro75_dm_id: whole drag curve * 1.4954.",
)
```

### SS40.4.3 New file: `campaigns/cspace/scenarios_dm.py`

```python
"""projects/fx27/campaigns/cspace/scenarios_dm.py -- `SCENARIOS_DM`, the
7-row Mach-dependent ("dm") cspace comparison set (dev/docs/architecture-
40-fx27-campaigns-and-dm-drag.md SS40.4): the dm mirror of `scenarios.py`'s
existing 7-row `SCENARIOS` (3 base dm rockets + 4 ideal-dm variants), same
motors/site/weather.

Deliberately a SEPARATE dict, not merged into `scenarios.py`'s `SCENARIOS`
(SS40.1): that dict's 7 keys/values are part of the AC-3 pin surface
(tests/test_fx27_port.py) and `point/plots.py`'s naming-convention-driven
styling -- adding rows there risks disturbing either. `point/plots.py`
needs NO change either way: its `_family`/`_variant` split on `"<family>"`
/ `"<family> (ideal mass)"` / `"<family> (ideal drag)"` already treats
`"pro75_dm"` as its own family, distinct from `"pro75"` -- exactly the
dc-vs-dm side-by-side comparison `runs/cspace/comparison_dc_dm.py`
(SS40.6) wants, for free.
"""

from __future__ import annotations

from apps.sim.schema import Scenario

from projects.fx27.campaigns.cspace import motors, rockets_dm
from projects.fx27.campaigns.cspace.site import SITE
from projects.fx27.campaigns.cspace.weather import WEATHER

SCENARIOS_DM: "dict[str, Scenario]" = {
    "pro54_transition_dm": Scenario(
        name="pro54_transition_dm", rocket=rockets_dm.PRO54_TRANSITION_DM,
        motor=motors.PRO54_2060K570, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets.py pro54_transition_dm + pro54_2060K570.",
    ),
    "pro54_equal_dm": Scenario(
        name="pro54_equal_dm", rocket=rockets_dm.PRO54_EQUAL_DM,
        motor=motors.PRO54_2060K570, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets.py pro54_equal_dm + pro54_2060K570.",
    ),
    "pro75_dm": Scenario(
        name="pro75_dm", rocket=rockets_dm.PRO75_DM,
        motor=motors.PRO75_3419L645, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets.py pro75_dm + pro75_3419L645.",
    ),
    "pro54_transition_dm (ideal mass)": Scenario(
        name="pro54_transition_dm (ideal mass)", rocket=rockets_dm.PRO54_TRANSITION_DM_IDEAL_MASS,
        motor=motors.PRO54_2060K570, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro54_transition_dm_im.",
    ),
    "pro54_transition_dm (ideal drag)": Scenario(
        name="pro54_transition_dm (ideal drag)", rocket=rockets_dm.PRO54_TRANSITION_DM_IDEAL_DRAG,
        motor=motors.PRO54_2060K570, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro54_transition_dm_id.",
    ),
    "pro75_dm (ideal mass)": Scenario(
        name="pro75_dm (ideal mass)", rocket=rockets_dm.PRO75_DM_IDEAL_MASS,
        motor=motors.PRO75_3419L645, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro75_dm_im.",
    ),
    "pro75_dm (ideal drag)": Scenario(
        name="pro75_dm (ideal drag)", rocket=rockets_dm.PRO75_DM_IDEAL_DRAG,
        motor=motors.PRO75_3419L645, site=SITE, weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro75_dm_id.",
    ),
}
```

Naming note: family strings are `"pro54_transition_dm"`/`"pro54_equal_dm"`/`"pro75_dm"` (the `_dm`
suffix lives in the *family* name, not as a parenthesized variant) so `point/plots.py`'s
`_family_colors` assigns the dm rockets their own distinct colour, separate from their dc
namesakes — required for a legible dc-vs-dm comparison plot, and achieved with zero `point/`
changes.

## SS40.5 The generator script

New file `campaigns/cspace/data/aero/generate_dm_tables.py` — a one-off tool, **not** imported by
any `apps/` or `projects/fx27/` runtime module, **not** exercised by pytest, run manually once by
a developer with the sibling repo checked out locally. Its three output CSVs are committed to
source control (SS40.3.3's "static, not runtime" decision).

```python
#!/usr/bin/env python
"""projects/fx27/campaigns/cspace/data/aero/generate_dm_tables.py -- ONE-OFF
generator (dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.5).
Run manually once; NOT imported at runtime; NOT exercised by pytest.

Reads fx27's own bare `Mach,Cd` curve (rocketpy's own power_off_drag/
power_on_drag CSV convention: no header, 121 rows, Mach 0..3.0 step 0.025)
and reshapes it into this project's apps/sim/engine/aero.py v1 table
format (alpha_deg,M,C_A,C_N,C_m,l1_m -- a rectangular (M, alpha) grid):
two bogus alpha_deg rows per Mach value (-1, +1 deg, IDENTICAL C_A at
both -- the minimum rectangular grid _load_table_impl accepts, SS40.3.3),
C_N=C_m=0.0 at every point (Option C invariant), l1_m=1.0 (the same
DYNAMICALLY INERT placeholder cspace/rockets.py's _LENGTHS.l1 already
uses). No c_mq column -- the dm Rocket's own Aero.c_mq=0.0 fallback,
carried through unedited from its dc sibling by dataclasses.replace,
already gives the same answer a c_mq column full of zeros would.

Run once, from anywhere (paths below are absolute):
    python projects/fx27/campaigns/cspace/data/aero/generate_dm_tables.py
Output is committed -- SS40.3.3's rationale for a generated static file,
not a runtime transform.
"""

from __future__ import annotations

import csv
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Absolute path to the sibling repo's own source curves (orchestrator's inventory,
# same provenance convention as projects/fx27/README.md's "Provenance" section).
_SIBLING_AERO_DIR = Path(r"D:\Projects - Ongoing\fx27\simulation\import\aerodynamics\cspace")

_SOURCES = ("pro54-transition-drag.csv", "pro54-equal-drag.csv", "pro75-drag.csv")


def _convert_one(src: Path, dst: Path) -> None:
    with open(src, newline="") as f:
        mach_cd = [(float(m), float(cd)) for m, cd in csv.reader(f) if m.strip()]
    with open(dst, "w", newline="") as f:
        f.write(
            f"# Mach-dependent C_A(M), ported from fx27's own rocketpy power_off_drag/"
            f"power_on_drag curve ({src.name}, orchestrator's inventory of the sibling "
            "repo, 2026-11) -- dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.5.\n"
            "# C_N=C_m=0.0 at every point (Option C invariant); l1_m=1.0 is the same inert\n"
            "# placeholder cspace/rockets.py's _LENGTHS.l1 uses; two alpha rows per Mach\n"
            "# (-1, +1 deg, identical C_A) are the minimum rectangular (M, alpha) grid\n"
            "# apps/sim/engine/aero.py's loader accepts.\n"
        )
        w = csv.writer(f)
        w.writerow(["alpha_deg", "M", "C_A", "C_N", "C_m", "l1_m"])
        for m, cd in mach_cd:
            for alpha in (-1.0, 1.0):
                w.writerow([alpha, m, cd, 0.0, 0.0, 1.0])


def main() -> None:
    for name in _SOURCES:
        _convert_one(_SIBLING_AERO_DIR / name, _HERE / name)
        print(f"wrote {_HERE / name}")


if __name__ == "__main__":
    main()
```

Developer note: validate the row count after running (121 Mach values x 2 alpha rows = 242 data
rows per output file, plus the 6-line comment header and the column header) and spot-check a
couple of `C_A` values against the source CSV (the brief's own samples: `pro75-drag.csv` row 1
`Mach=0, Cd=1.466`, last row `Mach=3, Cd=0.374`) before committing.

## SS40.6 New run entry point: `comparison_dc_dm.py`

New file `runs/cspace/comparison_dc_dm.py` (Part A's reorg must land first — this file lives at
the post-reorg path). Merges `scenarios.SCENARIOS` (7 dc rows) and `scenarios_dm.SCENARIOS_DM` (7
dm rows) into one 14-row table + the two existing comparison figures, reusing `point/comparison.py`
and `point/plots.py` completely unchanged (both are already campaign/variant-agnostic — verified
by reading them in full for this step, SS40.1).

```python
"""projects/fx27/runs/cspace/comparison_dc_dm.py -- dc-vs-dm side-by-side
comparison (dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md SS40.6):
all 14 rows (scenarios.SCENARIOS's existing 7 + scenarios_dm.SCENARIOS_DM's
new 7), one table + the two existing comparison figures (point/plots.py
already treats every "<family>_dm" name as its own family/colour, SS40.4,
so the dc/dm pairs land side by side with no point/ change).

Unlike runs/cspace/comparison.py's single Mach-warning summary line (every
dc row uses aero.model="constant", so a Mach>0.8 flight always warns),
this script's dm rows use aero.model="table" and are EXEMPT from
MachRangeWarning (apps/sim/engine/mach_warning.py: "table" is Mach-aware
by construction, _MACH_INDEPENDENT_MODELS = ("constant", "linearized")) --
the printed summary is split into a dc caveat line and a dm informational
line so a reader does not read "Mach > 0.8" as a caveat for the rows where
it specifically is not one.

Run: `python -m projects.fx27.runs.cspace.comparison_dc_dm [--validity]`.
"""

from __future__ import annotations

import argparse
import warnings

from apps._shared.artifacts import ensure_dir, output_dir
from apps.sim.engine.mach_warning import MachRangeWarning, peak_mach

from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.point.comparison import print_table, run_many, save_csv
from projects.fx27.point.metrics import row_from_flight
from projects.fx27.point.plots import plot_displacement_comparison, plot_kinematics_comparison
from projects.fx27.point.validity import check_validity, print_validity

_ALL = {**SCENARIOS, **SCENARIOS_DM}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--validity", action="store_true",
        help="also print Option C's measured error bound per scenario (SS38.5.7)",
    )
    args = ap.parse_args(argv)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MachRangeWarning)
        runs = run_many(_ALL)
    mach_warns = [w for w in caught if issubclass(w.category, MachRangeWarning)]

    rows = [row_from_flight(name, fr) for name, fr in runs.items()]
    print_table(rows, title="cspace dc-vs-dm comparison (14 rows)")

    if mach_warns:
        print(
            f"\nNOTE: {len(mach_warns)} dc row(s) exceeded Mach 0.8 under a Mach-blind "
            "drag model (C_x constant) -- those apogees are not credible above that point "
            "(SS38.4.4/R4, inherited from fx27)."
        )
    dm_supersonic = [
        name for name, fr in runs.items()
        if name in SCENARIOS_DM and peak_mach(fr.result)[0] > 0.8
    ]
    if dm_supersonic:
        print(
            f"\nNOTE (informational, NOT a caveat): {len(dm_supersonic)} dm row(s) reached "
            f"Mach > 0.8 ({', '.join(dm_supersonic)}) -- their drag is Mach-dependent "
            "(aero.model=\"table\"), so this does not affect credibility."
        )

    if args.validity:
        for name, fr in runs.items():
            print_validity(name, check_validity(fr.result, fr.cfg.params))

    out_dir = ensure_dir(output_dir())
    csv_path = out_dir / "fx27_cspace_dc_dm_comparison.csv"
    disp_path = out_dir / "fx27_cspace_dc_dm_displacement.png"
    kin_path = out_dir / "fx27_cspace_dc_dm_kinematics.png"
    save_csv(rows, csv_path)

    results = {name: fr.result for name, fr in runs.items()}
    plot_displacement_comparison(results, title="cspace dc-vs-dm displacement comparison").savefig(disp_path)
    plot_kinematics_comparison(results, title="cspace dc-vs-dm kinematics comparison").savefig(kin_path)

    print(f"\nSaved {csv_path}")
    print(f"Saved {disp_path}")
    print(f"Saved {kin_path}")


if __name__ == "__main__":
    main()
```

`runs/cspace/ideal_mass.py`/`ideal_drag.py` (post-reorg names) are **NOT** extended to the dm
rockets in this step: fx27 gives no fresh target-apogee-solved oracle for the dm "ideal" variants
(SS40.4.2's note — their numbers read as a measured delta applied to the dm rocket, not a root-find
result), so there is nothing to validate `estimate_airframe_mass`/`estimate_cx` against for them.
Extending those two scripts to merely *run* the solver on the dm rockets without an oracle to check
against would add output with no acceptance value; `comparison_dc_dm.py` already surfaces the dm
rockets' measured apogee for inspection. See SS40.9.

## SS40.7 Directory structure diff (before / after)

Before (current):

```
projects/fx27/
  _paths.py, README.md, __init__.py
  data/
    README.md                              (stray, deleted)
    motors/cspace/*.csv (2), motors/euroc-sweep/*.csv (27)
  cspace/   __init__.py, motors.py, rockets.py, rockets_ideal.py, scenarios.py, site.py, weather.py
  euroc/    __init__.py, motors.py, rockets.py, scenarios.py, site.py, weather.py
  point/    __init__.py, flight.py, comparison.py, metrics.py, estimate.py, airbrake.py, plots.py, validity.py
  runs/     __init__.py, cspace_point.py, cspace_comparison.py, cspace_ideal_mass.py,
            cspace_ideal_drag.py, cspace_airbrake.py, euroc_comparison.py, euroc_sweep.py
  docs/     (out of scope, untouched)
```

After (this step):

```
projects/fx27/
  _paths.py, README.md, __init__.py
  campaigns/
    __init__.py
    cspace/
      __init__.py, motors.py, rockets.py, rockets_ideal.py, rockets_dm.py (new),
      scenarios.py, scenarios_dm.py (new), site.py, weather.py
      data/
        motors/*.csv (2)
        aero/
          generate_dm_tables.py (new, one-off tool)
          pro54-transition-drag.csv, pro54-equal-drag.csv, pro75-drag.csv (new, generated+committed)
    euroc/
      __init__.py, motors.py, rockets.py, scenarios.py, site.py, weather.py
      data/motors/*.csv (27)
  point/    (unchanged, zero edits)
  runs/
    __init__.py
    cspace/
      __init__.py, point.py, comparison.py, comparison_dc_dm.py (new), ideal_mass.py,
      ideal_drag.py, airbrake.py
    euroc/
      __init__.py, comparison.py, sweep.py
  docs/     (out of scope, untouched)
```

## SS40.8 Test plan

Extend `tests/test_fx27_port.py` only (same file the existing AC-1..AC-3 acceptance tests live in
— this port's own established convention of keeping fx27 acceptance tests in one file). No other
test file is touched; no existing test's body or numeric pin changes.

1. **Import-path edits** (SS40.2.3's table) — mechanical, zero behavior change.
2. **AC-1-style assembly smoke test, extended to the dm scenarios**: `@pytest.mark.parametrize`
   over `sorted(SCENARIOS_DM)`, same assertions as the existing `test_cspace_scenario_assembles`
   (mass > 0, mass model on). This is the real guard against a typo in `rockets_dm.py`'s
   `dataclasses.replace` calls or a malformed generated CSV.
3. **Aero-table round-trip/value check** (the brief's "new aero-table loader/generator round-trip
   check at minimum"): for each of the 3 generated CSVs, pick 2-3 known `(Mach, Cd)` pairs from the
   source samples quoted in this doc's SS40.5 (`pro75-drag.csv`: `Mach=0 -> Cd=1.466`,
   `Mach=3 -> Cd=0.374`) and assert `apps.sim.engine.aero.C_A(alpha=0.0, M=<mach>, p)` (built from
   the corresponding dm `Rocket`'s assembled `Params`) equals the expected `Cd` within a tight
   tolerance (`axial_flow_factor(0.0) == 1.0` exactly, so no fudge factor is needed here).
4. **Sanity check that the dm scenarios run and produce plausible apogees**: run `point/flight.run`
   (or `point/comparison.run_many`) on `SCENARIOS_DM`, assert each flight's apogee AGL is positive
   and finite, and — as a cross-check, not a pin — within a generous band (e.g. 500-10000 m) of its
   dc namesake's own apogee (same motor, same approximate mass/drag order of magnitude; a wildly
   different apogee would indicate a wiring bug in `rockets_dm.py`, not a result worth pinning
   numerically since there is no fx27 oracle for it per SS40.4.2/SS40.9).
5. **Confirm the 4 existing AC-3 pins and the rest of `test_fx27_port.py` stay bit-for-bit
   unchanged** after the reorg's import-path edits — run the file in isolation first
   (`python -m pytest tests/test_fx27_port.py -q`), then the full suite per this project's
   chunking convention (`CLAUDE.md` "Профиль проекта" ловушки), confirming no numeric pin outside
   this one file moved.

Follow the `tdd` skill: write 2-4 above before/alongside `rockets_dm.py`/`scenarios_dm.py`, not
after.

## SS40.9 Rejected options

- **Appending the dm rockets/scenarios to the existing `rockets.py`/`rockets_ideal.py`/
  `scenarios.py` files** instead of new `rockets_dm.py`/`scenarios_dm.py` — rejected: the task
  brief is explicit that the existing dc content in those 3 files must stay byte-for-byte
  unchanged (part of the AC-3 pin surface via `scenarios.py`'s `SCENARIOS`), and a same-file
  append still risks an accidental diff to the untouched lines during review. A new file is zero
  risk by construction.
- **Building the dm aero tables at import time from the raw `Mach,Cd` CSVs** (a runtime
  reshape, no generator script) — rejected per SS40.3.3: the sibling repo's raw CSVs are not a
  dependency this project should read at runtime, and `aero.py`'s loader API is file-path-based,
  not data-based; a generate-once-and-commit static file matches every other data file in this
  port.
- **A single rescaled second CSV per idealized-drag dm variant** (literally multiplying every
  `C_A` row by `0.5843`/`1.4954` and writing a 4th/5th/6th CSV) — rejected per SS40.3.3: redundant
  given `Aero.cx_scale` already does exactly this, applied once, after the dispatch, for any
  model — zero new data files needed.
- **Extending `runs/cspace/ideal_mass.py`/`ideal_drag.py` to also report the dm "ideal" figures**
  — rejected for this step (SS40.6): there is no fx27-solved target-apogee oracle for the dm
  idealized variants to validate against (unlike the dc ones' AC-3 numbers), so running the
  root-finder against them would produce a number with nothing to compare it to. If a future step
  supplies such a target, a small follow-up ticket can add it then.
- **A combined single `runs/cspace/comparison.py` emitting both the dc-only 7-row table (today's
  behavior) and the dc+dm 14-row table under a flag** — rejected: `comparison.py`'s existing
  behavior/output filenames are part of this port's already-shipped, documented surface
  (`projects/fx27/README.md`'s "How to run" section, screenshots/examples elsewhere may reference
  its exact output names); a new, separate `comparison_dc_dm.py` keeps that surface untouched and
  make the new 14-row view opt-in by file choice rather than by flag.

## SS40.10 Tickets

### [FX40-1] Part A: `campaigns/`+`runs/` reorg across `projects/fx27/`
- **Module/boundaries:** every file under `projects/fx27/cspace/`, `projects/fx27/euroc/`,
  `projects/fx27/data/`, `projects/fx27/runs/` (moves/renames per SS40.2.2); `projects/fx27/
  _paths.py` (anchor repoint, SS40.2.3); `projects/fx27/README.md` (SS40.2.5);
  `tests/test_fx27_port.py` (import lines only, SS40.2.3). Does NOT touch `projects/fx27/point/`
  or `tests/test_apogee_targeting.py` (SS40.1's correction — it has no `projects.fx27` import to
  update).
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (touches nearly every file in `projects/fx27/` plus a test file — keep
  this ticket atomic; do not interleave with any other change to this tree)

Spec: this doc, SS40.2 (full map, import-line table, README rewrite, `data/README.md` deletion).
Do every file move with `git mv` (preserves history) before editing import lines inside the moved
files. After all moves+edits, grep-verify zero remaining `from projects.fx27.cspace` / `from
projects.fx27.euroc` (without `.campaigns.`) anywhere under `projects/` or `tests/`. Run
`tests/test_fx27_port.py` in isolation and confirm its existing AC-1..AC-3 assertions (including
the 4 AC-3 numeric values) are unaffected — this ticket changes zero logic, only paths.

### [FX40-2] Part B: generate + commit the 3 dm aero table CSVs
- **Module/boundaries:** new `campaigns/cspace/data/aero/generate_dm_tables.py` and its 3 output
  CSVs (`pro54-transition-drag.csv`, `pro54-equal-drag.csv`, `pro75-drag.csv`) under the same
  directory. No other file touched.
- **Assignee:** developer
- **depends_on:** [FX40-1] (needs the `campaigns/cspace/` tree to exist)
- **parallel_safe:** false (sequential after FX40-1; FX40-3 needs its output filenames to exist)

Spec: this doc, SS40.5 (full generator skeleton) + SS40.3 (format decisions table — alpha grid,
zeroed C_N/C_m, l1_m=1.0, no c_mq column). Run the script once against the sibling repo checkout,
spot-check the row count (242 data rows + header + 6 comment lines per file) and the 2-3 sample
values quoted in SS40.5 against the source CSVs, then commit the 3 generated CSVs as static files.

### [FX40-3] Part B: new `Rocket`/`Scenario` content
- **Module/boundaries:** new `campaigns/cspace/rockets_dm.py`, new `campaigns/cspace/
  scenarios_dm.py`, plus the one new anchor function in `_paths.py` (`cspace_aero`, SS40.4.1). Does
  NOT edit `rockets.py`/`rockets_ideal.py`/`scenarios.py` (byte-for-byte unchanged, purely
  additive).
- **Assignee:** developer
- **depends_on:** [FX40-1, FX40-2]
- **parallel_safe:** false

Spec: this doc, SS40.4 (full code skeletons for both new files) + SS40.3.3 (the `cx_scale`/`l1_m`/
`c_mq`-fallback decisions, already confirmed against the engine code — do not re-derive, just
implement as specced).

### [FX40-4] Part B: new run entry point `runs/cspace/comparison_dc_dm.py`
- **Module/boundaries:** new `runs/cspace/comparison_dc_dm.py` only.
- **Assignee:** developer
- **depends_on:** [FX40-1, FX40-3]
- **parallel_safe:** true (file boundary is disjoint from FX40-5's `tests/test_fx27_port.py`
  edits, and this ticket does not depend on FX40-5 or vice versa — safe to run alongside it once
  FX40-3 has landed)

Spec: this doc, SS40.6 (full script skeleton) — note the split dc-caveat/dm-informational
Mach-warning summary (dm rows are exempt from `MachRangeWarning` by construction, do not conflate
the two in one summary line).

### [FX40-5] Part B: tests
- **Module/boundaries:** `tests/test_fx27_port.py` only (append new tests; the import-path edits
  from FX40-1 are already in place by the time this ticket starts).
- **Assignee:** developer
- **depends_on:** [FX40-1, FX40-3]
- **parallel_safe:** true (disjoint file boundary from FX40-4; both depend only on FX40-3, not on
  each other)

Spec: this doc, SS40.8 (all 5 test items: assembly smoke test over `SCENARIOS_DM`, aero-table
round-trip value check, apogee-plausibility sanity check, full-suite pin-stability confirmation).
Follow the `tdd` skill: write these before/alongside `rockets_dm.py`/`scenarios_dm.py` if sequencing
allows, or immediately after if FX40-3 already landed.

### [FX40-6] Verification: confirm zero behavior change end to end
- **Module/boundaries:** none (verification only).
- **Assignee:** developer (closing gate) or qa
- **depends_on:** [FX40-1, FX40-2, FX40-3, FX40-4, FX40-5]
- **parallel_safe:** false

Spec: run the full suite per this project's chunking convention (`CLAUDE.md` "Профиль проекта"
ловушки) and confirm (a) the 4 AC-3 numeric values in `tests/test_fx27_port.py` are bit-for-bit
unchanged from before this step, (b) no numeric pin anywhere else in the suite moved, (c)
`python -m projects.fx27.runs.cspace.comparison_dc_dm` runs end to end from the repo root and
produces 3 output files without raising, (d) `projects/fx27/README.md`'s "How to run" commands
all resolve to real modules under the new tree.

## SS40.11 Open decisions for the user gate

None found that need a user "yes" before implementation starts. Part A's target shapes are
already approved (2026-11-03 `AskUserQuestion`); Part B is additive-only on the already-approved
stack (`aero.model="table"` is an existing, already-shipped engine feature — Step 55/Step 99 — not
a new dependency or external service), matching the precedent set by D-173/Step 144/architecture-
39's own "incremental architecture of an already existing stage" rule. The one item worth the
orchestrator's attention (not the user's): SS40.9's closing note that the dm "ideal" variants have
no fx27-solved oracle to pin against is a genuine gap versus the dc side's AC-3 table — flagged
explicitly in the README/tests as "sanity-checked, not oracle-validated" rather than silently
treated as equivalent to AC-3; if the user later supplies a target apogee for the dm idealized
variants, extending `ideal_mass.py`/`ideal_drag.py` to them is a small, well-scoped follow-up, not
reopening this step.

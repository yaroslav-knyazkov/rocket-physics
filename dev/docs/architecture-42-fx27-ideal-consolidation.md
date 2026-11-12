## Кратко (RU)

- Документ описывает консолидацию всех данных "идеализированной ракеты" fx27-порта в ОДИН файл
  `rockets_ideal.py` вместо трёх (`rockets_ideal.py` + `rockets_ideal_own.py` + хвост `rockets_dm.py`).
- Файл получает два явно разделённых раздела: **Section A** — 4 оракульных константы fx27 (байт-в-байт
  без изменений, тест AC-3 их не теряет) и **Section B** — всё, что считает/хранит сам этот проект:
  B1 — 8 констант собственного dc+dm решения (мигрируют из `rockets_ideal_own.py`, те же имена), B2 — 4
  константы измеренной fx27-дельты для dm (мигрируют из хвоста `rockets_dm.py`, те же имена, НЕ оракул).
  Коллизий имён между A и B нет (B всегда с инфиксом `_OWN_`/`_DM_`, A — без).
  Section B же физически добавляется ПОСЛЕ существующих 57 строк, ничего из Section A не редактируется.
- Скрипт регенерации переименован `generate_rockets_ideal_own.py` → `regenerate_ideal_own.py`, цель
  перенацелена на `rockets_ideal.py` (пишет только 8 B1-констант по тому же regex-механизму — структурно
  не может задеть ни Section A, ни B2, так как их имена не входят в множество из 8 ключей).
- Новая публичная функция `apps/optimization/apogee_targeting/solve.py::estimate_cx_scale` (зеркало
  `estimate_cx`, но для рычага `aero.cx_scale`) заменяет приватный инлайн-замыкание в скрипте регенерации
  и используется новыми dm-строками `ideal_drag.py`.
- `ideal_mass.py`/`ideal_drag.py` получают по 2 новые dm-строки, `airbrake.py` — 4 новые dm-сайзинга;
  вывод dm-строк явно помечен "NOT an oracle" (SS40.8), чтобы не перепутать с dc-строчной рамкой
  "error vs fx27 solved".
- Удаляются `rockets_ideal_own.py` и старый `generate_rockets_ideal_own.py` — только после того, как
  миграция верифицирована (раздел SS42.9/SS42.11).
- Не найдено ничего вне `campaigns/cspace/` и `tests/`, что импортирует retiring-модули по имени —
  проверено grep'ом (SS42.11). `tests/test_fx27_port.py` не меняется совсем: импортирует Section A по
  тем же именам из того же пути `rockets_ideal`.
- Это инкрементальный шаг на уже одобренном стеке (без новых зависимостей/сервисов/пивота) — проходит
  по стандартному флоу без грилинга, тот же вывод, что и architecture-39/40/41.

## Table of contents

- [SS42.1 Scope and background](#ss421-scope-and-background)
- [SS42.2 Final structure of `rockets_ideal.py`](#ss422-final-structure-of-rockets_idealpy)
- [SS42.3 `rockets_dm.py` trimmed shape](#ss423-rockets_dmpy-trimmed-shape)
- [SS42.4 Regenerate script: rename + retarget + guardrail](#ss424-regenerate-script-rename--retarget--guardrail)
- [SS42.5 `solve.py::estimate_cx_scale`](#ss425-solvepyestimate_cx_scale)
- [SS42.6 Updated import sites: `scenarios.py` / `scenarios_dm.py`](#ss426-updated-import-sites-scenariospy--scenarios_dmpy)
- [SS42.7 Test file rename/retarget; `test_fx27_port.py` zero-change confirmation](#ss427-test-file-renameretarget-test_fx27_portpy-zero-change-confirmation)
- [SS42.8 `ideal_mass.py`/`ideal_drag.py`/`airbrake.py` extensions](#ss428-ideal_masspyideal_dragpyairbrakepy-extensions)
- [SS42.9 Delete list](#ss429-delete-list)
- [SS42.10 Tickets](#ss4210-tickets)
- [SS42.11 Risk/verification note](#ss4211-riskverification-note)
- [SS42.12 Rejected options and open decisions](#ss4212-rejected-options-and-open-decisions)

---

## SS42.1 Scope and background

Supersedes `dev/docs/architecture-41-fx27-idealized-regenerate.md`'s SS41.2/SS41.4/SS41.5 (the module
placement/skeleton decisions for the now-retiring `rockets_ideal_own.py` + `generate_rockets_ideal_own.py`
split) and `dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md` SS40.8's point about `rockets_dm.py`'s
tail half not having an oracle counterpart. Architecture-41/40 themselves are left on disk unedited (they
are historical decision records, not living specs) — this document is the new source of truth for the
file layout from Step 151 forward. The roadmap item this fulfills is `projects/fx27/docs/vehicle-dynamics-
roadmap.md` section F2 (lines 94-111), confirmed via two `AskUserQuestion` rounds (2026-11-12): "one file,
two sections" over "replace the oracle constants", and "extend all three" (`ideal_mass.py`/`ideal_drag.py`/
`airbrake.py`) over leaving the dm tool-parity gap open.

Hard constraint restated (unchanged from architecture-38 SS38.9/architecture-41 SS41.6): the 4 numbers
`PRO54_TRANSITION_IDEAL_MASS_KG`, `PRO54_TRANSITION_IDEAL_DRAG_CX`, `PRO75_IDEAL_MASS_KG`,
`PRO75_IDEAL_DRAG_CX` are the AC-3 acceptance oracle (`tests/test_fx27_port.py`). They and the 4
`dataclasses.replace`d `Rocket` objects built from them must never change value, never move import path,
and the surrounding lines that define them must not be edited byte-for-byte. Everything in this document
is designed around that constraint never being touched, not merely "probably fine".

---

## SS42.2 Final structure of `rockets_ideal.py`

**Section A — unchanged, lines 1-57 of today's file, zero edits.** Do not touch a single character.
Re-read `projects/fx27/campaigns/cspace/rockets_ideal.py` yourself before editing to confirm the current
line count still matches (58 lines incl. trailing newline) — if it has drifted since this doc was written,
stop and flag it (`needs_input`), do not guess.

**Section B is appended strictly after Section A's last line.** One exception to "strictly after": the
single new import line `rockets_dm` needs is inserted directly below Section A's own existing import line
(so both import statements sit together at the top, idiomatic placement) — this is an *insertion*, not an
edit of any existing line; Section A's existing line (`from projects.fx27.campaigns.cspace.rockets import
PRO54_TRANSITION, PRO75`) is not touched, only a new line is added immediately after it. Confirm via diff
after editing that every line of today's file appears unmodified (not merely "same length") — a line-level
diff against pre-edit `rockets_ideal.py`, not a visual read, is the way to check this (see SS42.11).

Final file shape, in order:

```python
"""<Section A's existing 14-line module docstring, byte-identical>
"""

from __future__ import annotations

import dataclasses

from projects.fx27.campaigns.cspace.rockets import PRO54_TRANSITION, PRO75
from projects.fx27.campaigns.cspace.rockets_dm import PRO54_TRANSITION_DM, PRO75_DM  # Section B only

# fx27 hardcoded solved figures ... (Section A's existing 4 constants, byte-identical)
PRO54_TRANSITION_IDEAL_MASS_KG = 4.2864
PRO54_TRANSITION_IDEAL_DRAG_CX = 0.2351
PRO75_IDEAL_MASS_KG = 8.0654
PRO75_IDEAL_DRAG_CX = 0.8304

PRO54_TRANSITION_IDEAL_MASS = dataclasses.replace(...)   # byte-identical
PRO54_TRANSITION_IDEAL_DRAG = dataclasses.replace(...)   # byte-identical
PRO75_IDEAL_MASS = dataclasses.replace(...)              # byte-identical
PRO75_IDEAL_DRAG = dataclasses.replace(...)              # byte-identical

# ============================================================================
# SECTION B -- everything in this file that is NOT fx27's AC-3 oracle above.
# Two sub-blocks, B1 (machine-regenerated, this project's own solve) and B2
# (static, fx27's own dm measured-delta provenance figures, NOT an oracle).
# Neither sub-block's constant names collide with Section A's (A has no
# `_OWN_`/`_DM_` infix; B always does) -- verified, see architecture-42 SS42.2.
# ============================================================================

# ----------------------------------------------------------------------------
# B1 -- THIS PROJECT'S OWN apps/optimization/apogee_targeting solve, target
# 3000 m AGL, re-derived against rockets.py/rockets_dm.py's current base
# figures. EXPECTED TO DRIFT whenever those base figures change (roadmap F2's
# whole motivation) -- not a pin, not an oracle, not fx27 data. Migrated
# verbatim (same 8 names) from the now-retired rockets_ideal_own.py.
# Re-run after any rockets.py/rockets_dm.py base mass/C_x edit (from the repo
# root, `-m` required -- see regenerate_ideal_own.py's own docstring):
#     python -m projects.fx27.campaigns.cspace.regenerate_ideal_own
# ----------------------------------------------------------------------------

# >>> GENERATED -- do not hand-edit the 8 lines below. Run
# regenerate_ideal_own.py instead: it replaces exactly these 8 lines by
# name (regex-anchored, see that script's _substitute_constant), nothing
# else in this file -- structurally cannot reach Section A or B2's constants,
# their names are not in this script's 8-key write-set. <<<
PRO54_TRANSITION_IDEAL_OWN_MASS_KG = 4.3840
PRO54_TRANSITION_IDEAL_OWN_DRAG_CX = 0.2524
PRO75_IDEAL_OWN_MASS_KG = 8.1205
PRO75_IDEAL_OWN_DRAG_CX = 0.8400
PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG = 4.9985
PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE = 0.6263
PRO75_DM_IDEAL_OWN_MASS_KG = 7.9238
PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE = 1.5123
# <<< GENERATED <<<

_OWN_NOTE = "This project's own apps/optimization/apogee_targeting solve, target 3000 m AGL -- NOT fx27 data; re-derive via regenerate_ideal_own.py."

PRO54_TRANSITION_IDEAL_OWN_MASS = dataclasses.replace(
    PRO54_TRANSITION,
    name="pro54_transition_ideal_own_mass",
    airframe=dataclasses.replace(PRO54_TRANSITION.airframe, m=PRO54_TRANSITION_IDEAL_OWN_MASS_KG),
    notes=_OWN_NOTE,
)

PRO54_TRANSITION_IDEAL_OWN_DRAG = dataclasses.replace(
    PRO54_TRANSITION,
    name="pro54_transition_ideal_own_drag",
    aero=dataclasses.replace(PRO54_TRANSITION.aero, C_x=PRO54_TRANSITION_IDEAL_OWN_DRAG_CX),
    notes=_OWN_NOTE,
)

PRO75_IDEAL_OWN_MASS = dataclasses.replace(
    PRO75,
    name="pro75_ideal_own_mass",
    airframe=dataclasses.replace(PRO75.airframe, m=PRO75_IDEAL_OWN_MASS_KG),
    notes=_OWN_NOTE,
)

PRO75_IDEAL_OWN_DRAG = dataclasses.replace(
    PRO75,
    name="pro75_ideal_own_drag",
    aero=dataclasses.replace(PRO75.aero, C_x=PRO75_IDEAL_OWN_DRAG_CX),
    notes=_OWN_NOTE,
)

PRO54_TRANSITION_DM_IDEAL_OWN_MASS = dataclasses.replace(
    PRO54_TRANSITION_DM,
    name="pro54_transition_dm_ideal_own_mass",
    airframe=dataclasses.replace(PRO54_TRANSITION_DM.airframe, m=PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG),
    notes=_OWN_NOTE,
)

PRO54_TRANSITION_DM_IDEAL_OWN_DRAG = dataclasses.replace(
    PRO54_TRANSITION_DM,
    name="pro54_transition_dm_ideal_own_drag",
    aero=dataclasses.replace(PRO54_TRANSITION_DM.aero, cx_scale=PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE),
    notes=_OWN_NOTE,
)

PRO75_DM_IDEAL_OWN_MASS = dataclasses.replace(
    PRO75_DM,
    name="pro75_dm_ideal_own_mass",
    airframe=dataclasses.replace(PRO75_DM.airframe, m=PRO75_DM_IDEAL_OWN_MASS_KG),
    notes=_OWN_NOTE,
)

PRO75_DM_IDEAL_OWN_DRAG = dataclasses.replace(
    PRO75_DM,
    name="pro75_dm_ideal_own_drag",
    aero=dataclasses.replace(PRO75_DM.aero, cx_scale=PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE),
    notes=_OWN_NOTE,
)

# ----------------------------------------------------------------------------
# B2 -- fx27's own hardcoded dm "ideal" figures (data/cspace/rockets_ideal.py's
# "## DM" half) -- NOT an AC-3-style solved oracle (unlike Section A's 4 dc
# figures): fx27's own comments ("- 0.9267 kg", "* 0.5843") read as a measured
# mass/drag delta applied to the dm rocket, not a fresh root-find against a
# stated target apogee -- no apples-to-apples oracle number exists to test
# these against (architecture-40 SS40.8). Kept as named constants for
# provenance/traceability only. Migrated verbatim (same 4 names + 4 Rocket
# names) from the now-trimmed bottom half of rockets_dm.py. STATIC -- never
# touched by regenerate_ideal_own.py (not in its 8-key write-set) or by
# anything else; there is no regenerate step for these.
# ----------------------------------------------------------------------------

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

Notes on the migration mechanics:
- B1's body is copied from `rockets_ideal_own.py` lines 45-111 verbatim, with two textual substitutions
  only: `rockets.PRO54_TRANSITION`/`rockets.PRO75` → bare `PRO54_TRANSITION`/`PRO75` (already imported by
  Section A, no need for a second qualified reference) and `rockets_dm.PRO54_TRANSITION_DM`/
  `rockets_dm.PRO75_DM` → bare `PRO54_TRANSITION_DM`/`PRO75_DM` (now imported by the one new Section-B
  import line). The constant *names*, *values*, and the `_NOTE` constant's *text* are unchanged — only its
  Python identifier is renamed `_NOTE` → `_OWN_NOTE` (collision-avoidance: Section B2 below has its own
  per-constant inline note strings, not a shared `_NOTE`, so this rename costs nothing and makes a future
  reader searching for "the B1 note" unambiguous without reading surrounding context).
- B2's body is copied from `rockets_dm.py` lines 73-110 verbatim, with the same `PRO54_TRANSITION_DM`/
  `PRO75_DM` references already bare in the source (no substitution needed — `rockets_dm.py` already
  referenced its own module-local `PRO54_TRANSITION_DM`/`PRO75_DM` without a qualifier).
- No name in B1 or B2 collides with Section A (checked already by the orchestrator's prompt, confirmed by
  inspection above: A uses no `_OWN_`/`_DM_` infix) nor with each other (B1 uses `_OWN_`, B2 does not, and
  B2's names all contain `_DM_` where B1's dc names do not — the 4 B1 dc names vs. the 4 B2 dm names are
  textually distinct on that basis alone, and B1's dm names carry the extra `_OWN_` infix B2's dm names
  lack: `PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG` vs. `PRO54_TRANSITION_DM_IDEAL_MASS_KG`).

---

## SS42.3 `rockets_dm.py` trimmed shape

Delete lines 73-110 (the "fx27 hardcoded dm 'ideal' figures" comment block through the last
`PRO75_DM_IDEAL_DRAG = dataclasses.replace(...)` call) wholesale — this entire block moved verbatim into
`rockets_ideal.py` Section B2 (SS42.2 above), nothing paraphrased or re-derived.

Also trim the module docstring's paragraph that describes the 4 "ideal" dm variants (today's lines 16-21,
starting "4 'ideal' dm variants mirror `rockets_ideal.py`'s existing pattern exactly...") — that paragraph
describes code that no longer lives in this file. Final docstring keeps only the paragraphs describing the
3 base `*_DM` Rocket objects and the `_dm_aero` helper (today's lines 1-15 plus the closing paragraph
structure, i.e. everything except the "4 'ideal' dm variants..." paragraph) — add one replacement sentence
at the same spot: "The 4 'ideal' dm variants that used to live at the bottom of this file moved to
`rockets_ideal.py` Section B2 (architecture-42 SS42.2/SS42.3) — see that module, not this one, for them."

Final shape: module docstring (trimmed) + `from __future__ import annotations` + `import dataclasses` +
`from projects.fx27._paths import cspace_aero` + `from projects.fx27.campaigns.cspace import rockets` +
the 3 `_TABLE_*` path constants + `_dm_aero` helper + the 3 `*_DM` = `dataclasses.replace(...)` blocks
(`PRO54_TRANSITION_DM`, `PRO54_EQUAL_DM`, `PRO75_DM`) — i.e. today's lines 1-71, docstring paragraph edit
aside. Nothing else changes: `PRO54_EQUAL_DM` (which never got an "ideal" variant in any of the 3 files)
is completely unaffected by this ticket.

---

## SS42.4 Regenerate script: rename + retarget + guardrail

New name/path: `projects/fx27/campaigns/cspace/regenerate_ideal_own.py` (was
`generate_rockets_ideal_own.py`). Rationale for this exact name: it keeps the already-established `_own`
vocabulary every surrounding docstring/comment/constant name uses (`PRO54_TRANSITION_IDEAL_OWN_MASS_KG`
etc. — renaming the script to drop "own" entirely would desynchronize it from the vocabulary it writes),
while "regenerate" (not "generate") signals it rewrites an existing shared file in place rather than
producing a standalone module of its own — which is no longer true after this consolidation (there is no
longer a dedicated `rockets_ideal_own.py` for it to "generate").

Retarget: `_TARGET = Path(__file__).resolve().parent / "rockets_ideal.py"` (was `rockets_ideal_own.py`).

Guardrail, restated under the new name/target (architecture-41 SS41.6's point, now sharper because the
write target is a shared file): `_solved_values()` returns the *same 8 keys, unchanged*, as the function it
replaces — `PRO54_TRANSITION_IDEAL_OWN_MASS_KG`, `PRO54_TRANSITION_IDEAL_OWN_DRAG_CX`,
`PRO75_IDEAL_OWN_MASS_KG`, `PRO75_IDEAL_OWN_DRAG_CX`, `PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG`,
`PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE`, `PRO75_DM_IDEAL_OWN_MASS_KG`,
`PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE`. `_rewrite_file` only ever calls `_substitute_constant(source, name,
value)` for `name` drawn from that dict's keys — Section A's 4 oracle names and Section B2's 4 fx27-dm
provenance names are never in that dict, so they are **structurally unreachable** by this script (not
merely "the script is written not to touch them" — there is no code path by which one of those 8 other
names could ever reach `_substitute_constant`). `_substitute_constant`'s own `n != 1` guard (raises if a
name's line isn't found exactly once) is unchanged and still the second line of defense if `rockets_ideal.py`
ever drifts out of the expected shape.

Update the module's own docstring: replace every mention of `rockets_ideal_own.py` with `rockets_ideal.py`
(Section B1 specifically), keep the "GUARDRAIL" paragraph's substance (now reads "this script's only write
target is `_TARGET` below, hardcoded to `rockets_ideal.py` — ... it never writes a byte outside its own
8-key Section-B1 slice, by construction (SS42.4)") and keep the existing paragraph about reading
`rockets_dm.py`'s *base* rockets (unchanged: it still reads `scenarios_dm.SCENARIOS_DM`, which still points
at `rockets_dm.PRO54_TRANSITION_DM`/`PRO75_DM`, now the *only* thing left in `rockets_dm.py` after SS42.3's
trim — this makes the "reads bases, never writes `rockets_dm.py`'s own ideal constants" sentence trivially
true rather than merely asserted, since those constants no longer exist in that file at all).

Body changes beyond the rename/retarget:
- Remove the private `_with_cx_scale` closure and the `_CX_SCALE_BRACKET` constant — both now redundant
  (SS42.5).
- Remove the `solve_for_target_apogee` import (no longer called directly) and `dataclasses` import (only
  user was `_with_cx_scale`) — confirm nothing else in the file still needs either before deleting the
  import line.
- Add `from apps.optimization.apogee_targeting.solve import estimate_cx_scale` alongside the existing
  `estimate_airframe_mass`, `estimate_cx` import line.
- In `_solved_values()`, replace both `solve_for_target_apogee(dm_t, _with_cx_scale, dm_t.rocket.aero.
  cx_scale, _CX_SCALE_BRACKET, TARGET_APOGEE_M).required` / `..._DRAG_CX_SCALE` calls with
  `estimate_cx_scale(dm_t, target_apogee_agl=TARGET_APOGEE_M).required` / `estimate_cx_scale(dm_75,
  target_apogee_agl=TARGET_APOGEE_M).required` respectively — same bracket default `(0.0, 2.0)` lives
  inside `estimate_cx_scale` now (SS42.5), so dropping `_CX_SCALE_BRACKET` here changes no behavior.

---

## SS42.5 `solve.py::estimate_cx_scale`

New public function in `apps/optimization/apogee_targeting/solve.py`, placed directly after `estimate_cx`
(mirrors its shape exactly, only the overridden field differs):

```python
def estimate_cx_scale(
    scenario: Scenario,
    target_apogee_agl: float = 3000.0,
    cx_scale_bracket: "tuple[float, float]" = (0.0, 2.0),
    xtol: float = 1.0e-6,
) -> ApogeeTargetResult:
    """The `Aero.cx_scale` multiplier (Step 105 dispersion hook, applied after model
    dispatch regardless of `aero.model` -- `apps/sim/engine/aero.py`'s `coefficients`)
    that puts this scenario's apogee at `target_apogee_agl` -- the Mach-table analogue
    of `estimate_cx`'s constant-C_x root-find. On a `model="table"` Aero this scales the
    WHOLE Mach-dependent drag curve by one factor rather than solving a single coefficient
    (the distinction architecture-41 SS41.3 first worked out for the one-off
    `generate_rockets_ideal_own.py` closure this function now replaces). Same bracket/xtol
    defaults as `estimate_cx`, via `Scenario.overrides` (never a post-hoc `params.replace`
    -- module docstring)."""

    def with_cx_scale(s: Scenario, x: float) -> Scenario:
        return dataclasses.replace(s, overrides={**s.overrides, "aero.cx_scale": x})

    return solve_for_target_apogee(
        scenario, with_cx_scale, scenario.rocket.aero.cx_scale, cx_scale_bracket, target_apogee_agl, xtol
    )
```

`Aero.cx_scale` (`apps/sim/engine/params.py` line 130) defaults to `1.0` and exists on every `Aero`
regardless of `model` (`"constant"` or `"table"`), so this function is just as usable against a dc scenario
as a dm one — no special-casing needed, same as `estimate_cx`.

Also extend the thin fx27-local re-export wrapper `projects/fx27/point/estimate.py` with a third name, same
pattern as the existing two:

```python
from apps.optimization.apogee_targeting.solve import ApogeeTargetResult as EstimateResult
from apps.optimization.apogee_targeting.solve import estimate_airframe_mass, estimate_cx, estimate_cx_scale

__all__ = ["EstimateResult", "estimate_airframe_mass", "estimate_cx", "estimate_cx_scale"]
```

Update that module's docstring's "Re-exports the two names..." sentence to "three names" and add
`ideal_drag.py`'s new dm rows to the list of callers it names (SS42.8 below is the only new caller).

Two call sites consume `estimate_cx_scale`, both via the `projects.fx27.point.estimate` re-export (matching
how the dc rows already import `estimate_cx` from that same module, not directly from `apps.*`):
1. `regenerate_ideal_own.py`'s `_solved_values()` (SS42.4) — for B1's 2 dm-drag constants.
2. `runs/cspace/ideal_drag.py`'s new dm rows (SS42.8) — for the live re-solve printed alongside fx27's
   measured-delta figure.

---

## SS42.6 Updated import sites: `scenarios.py` / `scenarios_dm.py`

Both files currently do `from projects.fx27.campaigns.cspace import motors, rockets, rockets_ideal_own`
(`scenarios.py`) / `from projects.fx27.campaigns.cspace import motors, rockets_dm, rockets_ideal_own`
(`scenarios_dm.py`) and reference `rockets_ideal_own.PRO54_TRANSITION_IDEAL_OWN_MASS` etc.

Change: drop `rockets_ideal_own` from both import lines, add `rockets_ideal` instead (already imported by
neither file today — new import), and change every `rockets_ideal_own.X` attribute access to
`rockets_ideal.X` — the attribute names themselves (`PRO54_TRANSITION_IDEAL_OWN_MASS`,
`PRO54_TRANSITION_IDEAL_OWN_DRAG`, `PRO75_IDEAL_OWN_MASS`, `PRO75_IDEAL_OWN_DRAG` in `scenarios.py`;
`PRO54_TRANSITION_DM_IDEAL_OWN_MASS`, `PRO54_TRANSITION_DM_IDEAL_OWN_DRAG`, `PRO75_DM_IDEAL_OWN_MASS`,
`PRO75_DM_IDEAL_OWN_DRAG` in `scenarios_dm.py`) are unchanged — only the module they're looked up on moves.

```python
# scenarios.py
from projects.fx27.campaigns.cspace import motors, rockets, rockets_ideal
...
rocket=rockets_ideal.PRO54_TRANSITION_IDEAL_OWN_MASS,   # was rockets_ideal_own.PRO54_TRANSITION_IDEAL_OWN_MASS
```

```python
# scenarios_dm.py
from projects.fx27.campaigns.cspace import motors, rockets_dm, rockets_ideal
...
rocket=rockets_ideal.PRO54_TRANSITION_DM_IDEAL_OWN_MASS,   # was rockets_ideal_own.PRO54_TRANSITION_DM_IDEAL_OWN_MASS
```

Both files' `_IDEAL_OWN_NOTE` string constants reference the regenerate command by its old module path
(`` `python -m projects.fx27.campaigns.cspace.generate_rockets_ideal_own` ``) — update both to
`` `python -m projects.fx27.campaigns.cspace.regenerate_ideal_own` ``. Everything else in both files
(dict keys, motor/site/weather wiring, docstrings' surrounding prose) is unchanged — this ticket is import
+ one attribute-prefix + one command-string edit only, no behavior change, no new/removed scenario keys.

---

## SS42.7 Test file rename/retarget; `test_fx27_port.py` zero-change confirmation

Rename `tests/test_rockets_ideal_own.py` → `tests/test_regenerate_ideal_own.py` (mirrors the script's new
name, SS42.4). Retarget its imports:

```python
from projects.fx27.campaigns.cspace import motors, rockets_ideal          # was: rockets_ideal_own
from projects.fx27.campaigns.cspace.regenerate_ideal_own import (          # was: generate_rockets_ideal_own
    _rewrite_file,
    _substitute_constant,
)
```

Every `rockets_ideal_own.X` attribute access in the file's `_VARIANTS` dict (section 1) becomes
`rockets_ideal.X` — same 8 attribute names, same dict keys/structure, zero behavior change. Sections 2
(write-mechanism unit tests against synthetic strings/`tmp_path`), 3 (plausibility checks), and 4 (on-target
checks against `SCENARIOS`/`SCENARIOS_DM`) need no changes beyond that import/prefix swap — none of them
reference `rockets_ideal_own`/`generate_rockets_ideal_own` by any other name, and the hard constraint
(docstring lines 17-21: no test may call the real solver against the real committed module) is preserved
unchanged — `_rewrite_file`/`_substitute_constant` are still pure/`tmp_path`-only in this file, same as
today. Update the module's own docstring's references to `rockets_ideal_own.py`/`generate_rockets_ideal_
own.py` to `rockets_ideal.py`/`regenerate_ideal_own.py` and its `dev/docs/architecture-41...` cross-
reference to also cite this document (architecture-42).

**`tests/test_fx27_port.py` needs ZERO changes.** Its only import touching this consolidation is:

```python
from projects.fx27.campaigns.cspace.rockets_ideal import (
    PRO54_TRANSITION_IDEAL_DRAG_CX,
    PRO54_TRANSITION_IDEAL_MASS_KG,
    PRO75_IDEAL_DRAG_CX,
    PRO75_IDEAL_MASS_KG,
)
```

Reasoning: this import names both the module (`rockets_ideal`) and the 4 attributes (`PRO54_TRANSITION_
IDEAL_DRAG_CX` etc.) that live in **Section A**, which SS42.2 keeps at its current file path, current
module name, and byte-identical content. The module this file imports from does not move, rename, or have
its Section-A content edited in any way by this consolidation — it only grows a Section B appended after
the content this file reads. A Python import of 4 specific names from an unchanged module at an unchanged
path cannot observe an unrelated append to that same module below the names it imports. No other line in
`test_fx27_port.py` references `rockets_ideal_own`, `rockets_dm`'s dm-ideal constants (only `rockets_dm`'s
*base* rockets via `SCENARIOS_DM`, itself unaffected — SS42.6), or `generate_rockets_ideal_own` by any
name (confirmed by direct read of the file during this design, not inferred) — see SS42.11 for the grep
that backs this claim.

---

## SS42.8 `ideal_mass.py`/`ideal_drag.py`/`airbrake.py` extensions

### `ideal_mass.py` — 2 new dm rows

Add imports:

```python
from projects.fx27.campaigns.cspace.rockets_ideal import (
    PRO54_TRANSITION_DM_IDEAL_MASS_KG,       # fx27 measured-delta figure, NOT an oracle (SS40.8)
    PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG,   # this project's own last regen (B1)
    PRO75_DM_IDEAL_MASS_KG,
    PRO75_DM_IDEAL_OWN_MASS_KG,
)
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
```

Add a second mapping (dc's `_FX27_SOLVED` dict is untouched) and a second loop in `main()`:

```python
# name -> (this project's own last regen from rockets_ideal.py B1, fx27's own dm
# measured-delta figure from rockets_ideal.py B2 -- NOT a target-apogee-solved
# oracle, SS40.8/architecture-40; kept for provenance only, printed for context,
# never framed as "error vs" the way the dc rows above are).
_OWN_AND_FX27_DM: "dict[str, tuple[float, float]]" = {
    "pro54_transition_dm": (PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG, PRO54_TRANSITION_DM_IDEAL_MASS_KG),
    "pro75_dm": (PRO75_DM_IDEAL_OWN_MASS_KG, PRO75_DM_IDEAL_MASS_KG),
}


def main(argv=None) -> None:
    for name, fx27_value in _FX27_SOLVED.items():
        ...  # unchanged dc loop

    for name, (own_regen, fx27_measured) in _OWN_AND_FX27_DM.items():
        res = estimate_airframe_mass(SCENARIOS_DM[name], target_apogee_agl=TARGET_APOGEE_M)
        drift_pct = 100.0 * (res.required - own_regen) / own_regen
        print(
            f"{name}: baseline={res.baseline:.4f} kg, required={res.required:.4f} kg "
            f"(this project's own last regen={own_regen:.4f} kg, drift {drift_pct:+.2f}%), "
            f"fx27 measured-delta figure={fx27_measured:.4f} kg [NOT an oracle -- SS40.8: no "
            "target-apogee solve backs this number, provenance only], "
            f"achieved apogee={res.achieved_apogee_m:.1f} m, reachable={res.reachable}"
        )
```

Update the module docstring to mention the 2 new dm rows and point readers at SS40.8/this document for why
their print format differs from the dc rows above them (no "error" framing against `fx27_measured`).

### `ideal_drag.py` — 2 new dm rows

Same shape, `estimate_cx_scale` instead of `estimate_airframe_mass`, `..._CX_SCALE` constants instead of
`..._MASS_KG`:

```python
from projects.fx27.campaigns.cspace.rockets_ideal import (
    PRO54_TRANSITION_DM_IDEAL_DRAG_CX_SCALE,
    PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE,
    PRO75_DM_IDEAL_DRAG_CX_SCALE,
    PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE,
)
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.point.estimate import estimate_cx, estimate_cx_scale   # add estimate_cx_scale

_OWN_AND_FX27_DM: "dict[str, tuple[float, float]]" = {
    "pro54_transition_dm": (PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE, PRO54_TRANSITION_DM_IDEAL_DRAG_CX_SCALE),
    "pro75_dm": (PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE, PRO75_DM_IDEAL_DRAG_CX_SCALE),
}


def main(argv=None) -> None:
    for name, fx27_value in _FX27_SOLVED.items():
        ...  # unchanged dc loop

    for name, (own_regen, fx27_measured) in _OWN_AND_FX27_DM.items():
        res = estimate_cx_scale(SCENARIOS_DM[name], target_apogee_agl=TARGET_APOGEE_M)
        drift_pct = 100.0 * (res.required - own_regen) / own_regen
        print(
            f"{name}: baseline={res.baseline:.4f}, required={res.required:.4f} "
            f"(this project's own last regen={own_regen:.4f}, drift {drift_pct:+.2f}%), "
            f"fx27 measured-delta figure={fx27_measured:.4f} [NOT an oracle -- SS40.8: no "
            "target-apogee solve backs this number, provenance only], "
            f"achieved apogee={res.achieved_apogee_m:.1f} m, reachable={res.reachable}"
        )
```

Note the `_CAVEAT` dict (today's `pro54_transition`-only AC-3-tolerance caveat) is dc-only and untouched —
it keys off scenario names that never collide with the new dm names, so no guard is needed to keep it from
accidentally firing on a dm row.

### `airbrake.py` — 4 new dm ideal-variant brake sizings

`size_airbrake` is model-agnostic (operates on `cfg: Config`, reads whatever `aero.model` the config
carries) — no new estimator needed, just a second loop over the dm scenario dict:

```python
from projects.fx27.campaigns.cspace.scenarios import SCENARIOS
from projects.fx27.campaigns.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.point.airbrake import print_brake_report, size_airbrake

TARGET_APOGEE_M = 2500.0

IDEAL_VARIANTS_DC = (
    "pro54_transition (ideal mass)",
    "pro54_transition (ideal drag)",
    "pro75 (ideal mass)",
    "pro75 (ideal drag)",
)

IDEAL_VARIANTS_DM = (
    "pro54_transition_dm (ideal mass)",
    "pro54_transition_dm (ideal drag)",
    "pro75_dm (ideal mass)",
    "pro75_dm (ideal drag)",
)


def main(argv=None) -> None:
    for name in IDEAL_VARIANTS_DC:
        cfg = SCENARIOS[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()

    for name in IDEAL_VARIANTS_DM:
        cfg = SCENARIOS_DM[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()
```

No "NOT an oracle" labeling is needed here: `airbrake.py`'s report never compared a sizing result against
any fx27-solved reference value in the first place (dc rows don't either) — it only sizes a brake against
a stated target apogee for whatever config it's handed, so there is no pre-existing "error vs X" framing a
reader could mistake the dm rows for. `IDEAL_VARIANTS` (today's single dc-only tuple name) is renamed
`IDEAL_VARIANTS_DC` to make room for `IDEAL_VARIANTS_DM` alongside it — check nothing outside this file
imports `IDEAL_VARIANTS` by name before renaming (grep confirms nothing does, SS42.11).

---

## SS42.9 Delete list

Delete only after SS42.10's tickets 1-5 have all landed and the full verification in SS42.11 has passed:

1. `projects/fx27/campaigns/cspace/rockets_ideal_own.py`
2. `projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py` (the *old*-named script — the new
   `regenerate_ideal_own.py` is a new file, not a `git mv`-preserving rename, since its body changes
   materially per SS42.4; either a `git mv` + edit or a fresh `Write` + `rm` of the old one is acceptable,
   developer's choice, as long as the old path no longer exists afterward).

Do not delete `tests/test_rockets_ideal_own.py` as a separate step — it is *renamed* (SS42.7), not deleted;
by the time ticket 5 lands there is no file left at that path (the rename already removed it).

---

## SS42.10 Tickets

### [FX27C-1] `apps/optimization/apogee_targeting/solve.py::estimate_cx_scale` + `projects/fx27/point/estimate.py` re-export
- **Module/boundaries:** `apps/optimization/apogee_targeting/solve.py`, `projects/fx27/point/estimate.py`
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true
Add `estimate_cx_scale` per SS42.5's exact signature/body, placed after `estimate_cx`. Extend
`projects/fx27/point/estimate.py`'s import/`__all__`/docstring per SS42.5. No existing test's import list
needs to change for this ticket alone (nothing yet calls the new function) — add a small new unit test
(same house style as the rest of `tests/test_apogee_targeting.py` if that file exists, otherwise a new
`test_estimate_cx_scale_...` case in whichever file already covers `estimate_cx` — check first) confirming
it solves against a `model="table"` scenario's `aero.cx_scale`, mirroring whatever existing test pattern
covers `estimate_cx`.

### [FX27C-2] `rockets_ideal.py` Section B migration + `rockets_dm.py` trim
- **Module/boundaries:** `projects/fx27/campaigns/cspace/rockets_ideal.py`,
  `projects/fx27/campaigns/cspace/rockets_dm.py`
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (touches two files that ticket FX27C-3/4/5 all read from; land this first so
  later tickets aren't racing a half-migrated file)
Implement SS42.2 (append Section B to `rockets_ideal.py`, insert the one new import line, leave Section A's
existing lines byte-for-byte untouched — diff-check, not eyeball-check, per SS42.2's own instruction) and
SS42.3 (trim `rockets_dm.py`'s tail + docstring paragraph). Do this as one ticket/one commit even though
two files move — a half-done migration (constants duplicated in both files, or present in neither) is a
broken intermediate state no other ticket should ever see on disk.

### [FX27C-3] `regenerate_ideal_own.py` (rename + retarget from `generate_rockets_ideal_own.py`)
- **Module/boundaries:** `projects/fx27/campaigns/cspace/regenerate_ideal_own.py` (new),
  `projects/fx27/campaigns/cspace/generate_rockets_ideal_own.py` (removed)
- **Assignee:** developer
- **depends_on:** [FX27C-1, FX27C-2]
- **parallel_safe:** false
Implement SS42.4: new file at the new path, `_TARGET` repointed at `rockets_ideal.py`, body updated to call
`estimate_cx_scale` (from FX27C-1) instead of the inline closure, docstring updated per SS42.4. Delete the
old-named script only once this ticket's new file is verified working (don't delete-then-rewrite — write
the new file, verify, then remove the old one in the same commit).

### [FX27C-4] `scenarios.py` / `scenarios_dm.py` import retarget
- **Module/boundaries:** `projects/fx27/campaigns/cspace/scenarios.py`,
  `projects/fx27/campaigns/cspace/scenarios_dm.py`
- **Assignee:** developer
- **depends_on:** [FX27C-2]
- **parallel_safe:** false (both files are read by FX27C-5/6's tests/scripts — land before those run)
Implement SS42.6: swap `rockets_ideal_own` import for `rockets_ideal`, update the 8 attribute references
(4 per file), update both `_IDEAL_OWN_NOTE` strings' regenerate-command text to the new script path.

### [FX27C-5] Test rename/retarget: `tests/test_rockets_ideal_own.py` → `tests/test_regenerate_ideal_own.py`
- **Module/boundaries:** `tests/test_rockets_ideal_own.py` (removed), `tests/test_regenerate_ideal_own.py` (new)
- **Assignee:** developer
- **depends_on:** [FX27C-2, FX27C-3, FX27C-4]
- **parallel_safe:** false
Implement SS42.7. Run this file in isolation (`python -m pytest tests/test_regenerate_ideal_own.py -q`)
before moving on — it is the fastest signal that FX27C-2/3/4 wired together correctly.

### [FX27C-6] `ideal_mass.py`/`ideal_drag.py`/`airbrake.py` dm extensions
- **Module/boundaries:** `projects/fx27/runs/cspace/ideal_mass.py`, `projects/fx27/runs/cspace/ideal_drag.py`,
  `projects/fx27/runs/cspace/airbrake.py`
- **Assignee:** developer
- **depends_on:** [FX27C-1, FX27C-2, FX27C-4]
- **parallel_safe:** false (needs FX27C-1's `estimate_cx_scale` re-export and FX27C-2's Section B constants
  to exist at their final names/paths before writing these imports)
Implement SS42.8's three extensions exactly as specified (print formats are load-bearing, not a suggestion
— the "NOT an oracle" wording must survive). Run each script manually once
(`python -m projects.fx27.runs.cspace.ideal_mass`, `...ideal_drag`, `...airbrake`) and paste the printed
output into the ticket's own commit message or a scratch note, so a reviewer can see the dm rows' wording
without re-running the scripts themselves.

### [FX27C-7] Delete `rockets_ideal_own.py` + old `generate_rockets_ideal_own.py`; full verification
- **Module/boundaries:** delete-only, per SS42.9's list; plus the verification run in SS42.11
- **Assignee:** developer
- **depends_on:** [FX27C-1, FX27C-2, FX27C-3, FX27C-4, FX27C-5, FX27C-6]
- **parallel_safe:** false
Delete the two files in SS42.9. Grep the whole repo one more time for `rockets_ideal_own` and
`generate_rockets_ideal_own` (both as module names and as strings inside docstrings/comments in *code* files
— `dev/docs/*` historical records are exempt, do not edit them) to confirm zero remaining references outside
documentation. Then run the full verification sequence in SS42.11 and report its results (pass/fail per
item) in the final commit message.

None of these 7 tickets is `parallel_safe: true` except FX27C-1 — the whole chain after it is a strict
sequential dependency (each ticket reads files the previous one just moved/renamed), so the orchestrator
should expect this to run developer→developer in series (or FX27C-1 once in parallel with nothing else
useful to pair it against in this slice), not as a fan-out.

---

## SS42.11 Risk/verification note

**Tests that must remain passing byte-for-bit (the AC-3 boundary):**
- `tests/test_fx27_port.py::test_ac3_estimate_airframe_mass_pro54_transition`
- `tests/test_fx27_port.py::test_ac3_estimate_airframe_mass_pro75`
- `tests/test_fx27_port.py::test_ac3_estimate_cx_pro75`
- `tests/test_fx27_port.py::test_ac3_estimate_cx_pro54_transition_wider_tolerance`

These assert against `PRO54_TRANSITION_IDEAL_MASS_KG`/`PRO75_IDEAL_MASS_KG`/`PRO75_IDEAL_DRAG_CX`/
`PRO54_TRANSITION_IDEAL_DRAG_CX`, imported from `rockets_ideal` — per SS42.7's reasoning these values and
their import path are untouched, so these 4 tests' pass/fail status (and the measured `res.required` values
they compare against, which depend only on `estimate_airframe_mass`/`estimate_cx`'s own code in `solve.py`,
also untouched by this consolidation) cannot move. `test_cspace_scenario_assembles` and
`test_cspace_has_exactly_the_seven_comparison_rows` must also stay green — `scenarios.py`'s dict *keys*
don't change (SS42.6), only the module the 4 ideal rows' `rocket=` values are looked up from.

**Numeric pins possibly affected by an import-path change:** none identified. The only numeric pins in this
area are AC-3's 4 oracle constants (unaffected, above) and `tests/test_regenerate_ideal_own.py`'s section-4
"on-target" checks (`_IDEAL_TOLERANCE_M = 1.0`, not a decimal pin on the constants themselves — it re-flies
the scenario and checks the *achieved apogee* lands within 1 m of 3000, which depends on the actual
floating-point values in Section B1, not on where they're imported from) — these should be bit-identical
post-migration since the *values* B1 holds are the migration source's values, unedited.

**Cross-check — nothing outside `cspace/` and `tests/` imports the retiring names.** Grepped during this
design (not assumed):
- `rockets_ideal_own` / `generate_rockets_ideal_own`: hits only in `dev/status.json`, `dev/status-archive.
  json`, `dev/journal.md` (tracker/journal — historical, not code, not edited by this consolidation),
  `dev/docs/step-149-notes.md`, `dev/docs/architecture-41-fx27-idealized-regenerate.md` (historical design
  docs — left alone, superseded in substance by this document but not edited), and the 4 code files this
  document already covers (`scenarios.py`, `scenarios_dm.py`, `tests/test_rockets_ideal_own.py`,
  `rockets_ideal_own.py`, `generate_rockets_ideal_own.py` itself). Nothing in `apps/`, `projects/fx27/point/`,
  `projects/fx27/runs/`, or `projects/fx27/campaigns/euroc/` references either name.
- `rockets_dm` (broader search, to catch the dm-ideal constants specifically): hits in `dev/status.json`,
  `dev/status-archive.json`, `dev/journal.md`, `dev/docs/step-149-notes.md`, `dev/docs/architecture-41-...
  md`, `dev/docs/architecture-40-fx27-campaigns-and-dm-drag.md` (all historical/tracker, untouched),
  `projects/fx27/README.md` (2 hits — a prose mention of `rockets_dm.py`/`scenarios_dm.py` existing as a
  pair and an `AeroRangeWarning` note; neither references the dm-ideal constants specifically, no edit
  required by this ticket set, though `readme-keeper` may want an audit pass after this lands since the
  file inventory prose technically still describes the pre-consolidation shape accurately for the *base*
  rockets it's describing — the ideal constants were never mentioned there), `tests/test_fx27_port.py`
  (1 hit, a docstring comment at line 261, not an import — confirmed by reading the line), and the 4 files
  this document already covers. No other `apps/*` or `projects/fx27/point/*` or `projects/fx27/runs/*` file
  references `rockets_dm` at all.
- `IDEAL_VARIANTS` (the tuple being renamed `IDEAL_VARIANTS_DC` in `airbrake.py`, SS42.8): no match outside
  `projects/fx27/runs/cspace/airbrake.py` itself.

**What to independently re-run to prove the refactor is behavior-preserving at the AC-3 boundary:**
1. `python -m pytest tests/test_fx27_port.py -q` — full file, not just the AC-3 tests, both before starting
   (capture a baseline) and after FX27C-7 lands. Zero changes in pass/fail status or count is the bar; this
   file's own docstring says it is the *only* test file the original fx27 port ticket boundary touches, and
   this consolidation's own design goal is that it still needs zero edits (SS42.7) — a failing run here is
   an immediate stop, not a "investigate later".
2. `python -m pytest tests/test_regenerate_ideal_own.py -q` (new name) — confirms the renamed/retargeted
   test file's own assertions (assembly, write-mechanism, plausibility, on-target) all still pass against
   the new file layout.
3. Manually diff `rockets_ideal.py` before/after FX27C-2 (`git diff -- projects/fx27/campaigns/cspace/
   rockets_ideal.py`) and confirm every line of the diff is an *addition* (`+` lines only in the hunk that
   used to be the end of the file, plus the one inserted import line) — zero `-` lines and zero lines that
   are both removed-and-re-added-with-a-change count as a hard failure of SS42.2's own constraint, not a
   style nit.
4. Run `python -m projects.fx27.campaigns.cspace.regenerate_ideal_own` once for real (from the repo root)
   after FX27C-3 lands, and confirm its printed output's 8 values match what was already committed in
   `rockets_ideal.py` Section B1 (i.e. the base rockets haven't changed since the last regen, so re-running
   it now should be a no-op write) — this is the same "prove it reproduces" check architecture-41's own
   ticket RIO-4 specified for the original script, now re-run against the new target.
5. Run the 3 extended scripts manually (`ideal_mass`, `ideal_drag`, `airbrake` under `runs/cspace/`) and
   visually confirm the new dm rows' printed wording matches SS42.8's "NOT an oracle" framing — there is no
   automated test asserting exact print strings for these 3 scripts today (dc rows aren't pinned either),
   so this is a manual read, not a `pytest` assertion.

---

## SS42.12 Rejected options and open decisions

**Rejected: hoist all of Section B's new imports into one block separate from Section A's imports, lower
in the file, right before Section B's code starts.** Considered as an alternative to inserting the one new
`rockets_dm` import line directly below Section A's existing import (SS42.2). Rejected because Python
import-at-top convention is more idiomatic and the insertion-not-edit distinction (SS42.2) already satisfies
the "Section A byte-identical" constraint regardless of where the new line goes — there is no actual benefit
to the mid-file placement, only a minor PEP8 departure if chosen.

**Rejected: a `git mv` for the regenerate script instead of a fresh file + delete.** Considered for
`generate_rockets_ideal_own.py` → `regenerate_ideal_own.py` (SS42.4/ticket FX27C-3). Left as "developer's
choice" rather than mandated, since the body changes materially (new target, new estimator call, removed
closure) — a `git mv` followed by a large edit and a plain `Write` of a new file followed by `rm` of the old
one produce an equivalent end state; forcing one over the other would be a style preference with no
behavioral consequence, not a real architectural fork.

**No `decision_required`/`needs_approval` items.** This is an incremental, additive-and-reorganizing step on
an already-approved stack: no new dependency, no new external service, no stack pivot, no paid/external
service touched. Per this role's own "incremental architecture of an already existing stage" rule it goes
through the standard flow (this document) without a `grilling` round — same conclusion architecture-39/40/41
each reached for their own incremental steps. The two forks the user already resolved via `AskUserQuestion`
("one file, two sections" and "extend all three") are treated here as settled inputs, not re-opened.

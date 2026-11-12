"""projects/fx27/campaigns/cspace/rockets_ideal.py -- the 4 "ideal" cspace variants
(dev/docs/architecture-38-fx27-port.md SS38.3.1/SS38.5.2): fx27's
`data/cspace/rockets_ideal.py` carries the already-SOLVED outputs of its
own mass/drag estimators, hardcoded, target apogee 3000 m AGL.

These 4 numbers are the **AC-3 acceptance oracle** (SS38.9): this port's
`projects/fx27/point/estimate.estimate_airframe_mass`/`estimate_cx` must
reproduce them within 5% -- the whole Option C physics argument rests on
it (see `tests/test_fx27_port.py`).

Each variant overrides exactly one field of its base rocket (`cspace/
rockets.py`), never both -- `dataclasses.replace` down to the one group
that changed, nothing else touched.
"""

from __future__ import annotations

import dataclasses

from projects.fx27.campaigns.cspace.rockets import PRO54_TRANSITION, PRO75
from projects.fx27.campaigns.cspace.rockets_dm import PRO54_TRANSITION_DM, PRO75_DM  # Section B only

# fx27 hardcoded solved figures (data/cspace/rockets_ideal.py), target
# apogee 3000 m AGL -- the AC-3 oracle. Kept here as named constants so
# tests/test_fx27_port.py and the estimate.py run scripts cite the same
# source instead of three separately hand-typed copies of each number.
PRO54_TRANSITION_IDEAL_MASS_KG = 4.2864
PRO54_TRANSITION_IDEAL_DRAG_CX = 0.2351
PRO75_IDEAL_MASS_KG = 8.0654
PRO75_IDEAL_DRAG_CX = 0.8304

PRO54_TRANSITION_IDEAL_MASS = dataclasses.replace(
    PRO54_TRANSITION,
    name="pro54_transition_ideal_mass",
    airframe=dataclasses.replace(PRO54_TRANSITION.airframe, m=PRO54_TRANSITION_IDEAL_MASS_KG),
    notes="fx27 data/cspace/rockets_ideal.py pro54_transition_ideal_mass: solved dry mass for 3000 m AGL.",
)

PRO54_TRANSITION_IDEAL_DRAG = dataclasses.replace(
    PRO54_TRANSITION,
    name="pro54_transition_ideal_drag",
    aero=dataclasses.replace(PRO54_TRANSITION.aero, C_x=PRO54_TRANSITION_IDEAL_DRAG_CX),
    notes="fx27 data/cspace/rockets_ideal.py pro54_transition_ideal_drag: solved constant C_D for 3000 m AGL.",
)

PRO75_IDEAL_MASS = dataclasses.replace(
    PRO75,
    name="pro75_ideal_mass",
    airframe=dataclasses.replace(PRO75.airframe, m=PRO75_IDEAL_MASS_KG),
    notes="fx27 data/cspace/rockets_ideal.py pro75_ideal_mass: solved dry mass for 3000 m AGL.",
)

PRO75_IDEAL_DRAG = dataclasses.replace(
    PRO75,
    name="pro75_ideal_drag",
    aero=dataclasses.replace(PRO75.aero, C_x=PRO75_IDEAL_DRAG_CX),
    notes="fx27 data/cspace/rockets_ideal.py pro75_ideal_drag: solved constant C_D for 3000 m AGL.",
)

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

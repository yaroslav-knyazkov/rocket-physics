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

Re-run after any rockets.py/rockets_dm.py base mass/C_x edit (from the
repo root -- a bare script-path invocation breaks the absolute imports
below, see that script's own docstring):
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
PRO54_TRANSITION_IDEAL_OWN_MASS_KG = 4.3840
PRO54_TRANSITION_IDEAL_OWN_DRAG_CX = 0.2524
PRO75_IDEAL_OWN_MASS_KG = 8.1205
PRO75_IDEAL_OWN_DRAG_CX = 0.8400
PRO54_TRANSITION_DM_IDEAL_OWN_MASS_KG = 4.9985
PRO54_TRANSITION_DM_IDEAL_OWN_DRAG_CX_SCALE = 0.6263
PRO75_DM_IDEAL_OWN_MASS_KG = 7.9238
PRO75_DM_IDEAL_OWN_DRAG_CX_SCALE = 1.5123
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

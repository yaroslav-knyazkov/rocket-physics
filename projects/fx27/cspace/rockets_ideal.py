"""projects/fx27/cspace/rockets_ideal.py -- the 4 "ideal" cspace variants
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

from projects.fx27.cspace.rockets import PRO54_TRANSITION, PRO75

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

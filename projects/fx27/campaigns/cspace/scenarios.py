"""projects/fx27/campaigns/cspace/scenarios.py -- `SCENARIOS`, the 7-row cspace
comparison set (dev/docs/architecture-38-fx27-port.md SS38.5.2): the 3
base rockets + the 4 `rockets_ideal` variants, each paired with its motor,
site and weather.

Naming convention (SS38.5.2, LOAD-BEARING for plot styling,
`projects/fx27/point/plots.py`'s `_family_colors`/`_variant_style`):
`"<family>"` for a base rocket, `"<family> (ideal mass)"` /
`"<family> (ideal drag)"` for the two solved variants -- these are the
`Scenario.name`/dict-key strings, independent of the underlying `Rocket`
piece's own (unsuffixed) `name` field.

`Solver` is left at its library default (`t_max=300.0`) -- SS38.4.1: large
enough for every one of these 7 flights' apogee event to fire (verified
by `tests/test_fx27_port.py`'s assembly/estimate tests actually running
them).
"""

from __future__ import annotations

from apps.sim.schema import Scenario

from projects.fx27.campaigns.cspace import motors, rockets, rockets_ideal
from projects.fx27.campaigns.cspace.site import SITE
from projects.fx27.campaigns.cspace.weather import WEATHER

SCENARIOS: "dict[str, Scenario]" = {
    "pro54_transition": Scenario(
        name="pro54_transition",
        rocket=rockets.PRO54_TRANSITION,
        motor=motors.PRO54_2060K570,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets.py pro54_transition + pro54_2060K570.",
    ),
    "pro54_equal": Scenario(
        name="pro54_equal",
        rocket=rockets.PRO54_EQUAL,
        motor=motors.PRO54_2060K570,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets.py pro54_equal + pro54_2060K570.",
    ),
    "pro75": Scenario(
        name="pro75",
        rocket=rockets.PRO75,
        motor=motors.PRO75_3419L645,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets.py pro75 + pro75_3419L645.",
    ),
    "pro54_transition (ideal mass)": Scenario(
        name="pro54_transition (ideal mass)",
        rocket=rockets_ideal.PRO54_TRANSITION_IDEAL_MASS,
        motor=motors.PRO54_2060K570,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro54_transition_ideal_mass -- the AC-3 mass oracle.",
    ),
    "pro54_transition (ideal drag)": Scenario(
        name="pro54_transition (ideal drag)",
        rocket=rockets_ideal.PRO54_TRANSITION_IDEAL_DRAG,
        motor=motors.PRO54_2060K570,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro54_transition_ideal_drag -- the AC-3 drag oracle.",
    ),
    "pro75 (ideal mass)": Scenario(
        name="pro75 (ideal mass)",
        rocket=rockets_ideal.PRO75_IDEAL_MASS,
        motor=motors.PRO75_3419L645,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro75_ideal_mass -- the AC-3 mass oracle.",
    ),
    "pro75 (ideal drag)": Scenario(
        name="pro75 (ideal drag)",
        rocket=rockets_ideal.PRO75_IDEAL_DRAG,
        motor=motors.PRO75_3419L645,
        site=SITE,
        weather=WEATHER,
        notes="fx27 data/cspace/rockets_ideal.py pro75_ideal_drag -- the AC-3 drag oracle.",
    ),
}

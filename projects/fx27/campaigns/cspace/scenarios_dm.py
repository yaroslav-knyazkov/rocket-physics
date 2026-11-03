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

"""projects/fx27/campaigns/cspace/scenarios_dm.py -- `SCENARIOS_DM`, the
7-row Mach-dependent ("dm") cspace comparison set (dev/docs/architecture-
40-fx27-campaigns-and-dm-drag.md SS40.4): the dm mirror of `scenarios.py`'s
existing 7-row `SCENARIOS` (3 base dm rockets + 4 ideal-dm variants), same
motors/site/weather.

The 4 ideal-dm rows (Phase 2.24, Step 149, architecture-41 SS41.7
addendum; re-sourced Phase 2.26, Step 151, architecture-42 SS42.6) fly
THIS project's OWN `apps/optimization/apogee_targeting` solve
(`rockets_ideal.py` Section B1's dm variants), not fx27's own dm
measured-delta provenance figures (`rockets_ideal.py` Section B2, moved
there from `rockets_dm.py`'s tail by architecture-42 SS42.3) -- B2 is
NOT an AC-3-style solved oracle either (architecture-40 SS40.8), it is
kept for provenance only; it must never be re-used as a flown scenario
regardless. The dict's 7 keys are unchanged; only the `rocket=` each of
the last 4 keys points at moved.

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

from projects.fx27.campaigns.cspace import motors, rockets_dm, rockets_ideal
from projects.fx27.campaigns.cspace.site import SITE
from projects.fx27.campaigns.cspace.weather import WEATHER

# Shared `notes=` text for the 4 idealized-dm rows below (Step 149) -- hoisted
# to one constant, same pattern as rockets_ideal_own.py's own `_NOTE` and
# scenarios.py's `_IDEAL_OWN_NOTE`.
_IDEAL_OWN_NOTE = (
    "This project's own apps/optimization/apogee_targeting solve "
    "against the 3000 m AGL target (NOT fx27's rockets_dm.py "
    "oracle) -- re-derive via "
    "`python -m projects.fx27.campaigns.cspace.regenerate_ideal_own`."
)

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
        name="pro54_transition_dm (ideal mass)", rocket=rockets_ideal.PRO54_TRANSITION_DM_IDEAL_OWN_MASS,
        motor=motors.PRO54_2060K570, site=SITE, weather=WEATHER,
        notes=_IDEAL_OWN_NOTE,
    ),
    "pro54_transition_dm (ideal drag)": Scenario(
        name="pro54_transition_dm (ideal drag)", rocket=rockets_ideal.PRO54_TRANSITION_DM_IDEAL_OWN_DRAG,
        motor=motors.PRO54_2060K570, site=SITE, weather=WEATHER,
        notes=_IDEAL_OWN_NOTE,
    ),
    "pro75_dm (ideal mass)": Scenario(
        name="pro75_dm (ideal mass)", rocket=rockets_ideal.PRO75_DM_IDEAL_OWN_MASS,
        motor=motors.PRO75_3419L645, site=SITE, weather=WEATHER,
        notes=_IDEAL_OWN_NOTE,
    ),
    "pro75_dm (ideal drag)": Scenario(
        name="pro75_dm (ideal drag)", rocket=rockets_ideal.PRO75_DM_IDEAL_OWN_DRAG,
        motor=motors.PRO75_3419L645, site=SITE, weather=WEATHER,
        notes=_IDEAL_OWN_NOTE,
    ),
}

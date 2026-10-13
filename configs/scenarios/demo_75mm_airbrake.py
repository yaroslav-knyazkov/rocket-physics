"""configs/scenarios/demo_75mm_airbrake.py -- the airbrake-capable variant
of demo_75mm, registered for App 4 (airbrake sizing, roadmap Step 66, not
yet built) to default to (Step 63, roadmap.md,
`docs/architecture-30-apps-4-5-and-configs.md` SS30.3/SS30.4; recomposed
at Step 73, `docs/architecture-31-config-separation.md` SS31.7).

SS30.6 explains why there is nothing of substance for *this* module to
carry beyond the vehicle itself: "The app [4] owns control.airbrake_*
entirely. Whatever the incoming Config set there is overwritten by
brake_overrides" -- so a `control.airbrake_*` override placed here would
simply be discarded at solve time, and the target apogee is explicitly
not a vehicle property (it is a *study* input, carried in
`apps/airbrake_sizing/targets.py`). Under the flat-`Config` scheme this
meant `demo_75mm.CONFIG.derive(name=..., overrides={})` plus an
apologetic docstring explaining why the overrides dict was empty.
Composition replaces both: this scenario is simply **the same three
pieces** as `configs.scenarios.demo_75mm` (the `demo_75mm` rocket,
`origin_msl` site, `isa_dry_calm` weather) registered under its own
scenario name, so App 4 has an explicit default to point at without
reaching into App 3's motor-selection scenario, and a future vehicle
change made specifically for the airbrake demo still gets its own git
history (`configs/rockets/demo_75mm.py`'s) rather than a second literal.
"""

from __future__ import annotations

from configs.rockets import demo_75mm
from configs.schema import Config, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm

SCENARIO = Scenario(
    name="demo_75mm_airbrake",
    rocket=demo_75mm.ROCKET,
    site=origin_msl.SITE,
    weather=isa_dry_calm.WEATHER,
    notes=(
        "demo_75mm, unchanged, registered under its own name as App 4's "
        "(airbrake sizing) default vehicle. No control.airbrake_* override "
        "lives here: the app owns that group entirely at solve time "
        "(architecture-30 SS30.6), and the target apogee is a study input "
        "carried in apps/airbrake_sizing/targets.py, not a vehicle property."
    ),
)

CONFIG: Config = SCENARIO.config

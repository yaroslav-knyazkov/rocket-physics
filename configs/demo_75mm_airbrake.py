"""configs/demo_75mm_airbrake.py -- the airbrake-capable variant of
demo_75mm, registered for App 4 (airbrake sizing, roadmap Step 66, not yet
built) to default to (Step 63, roadmap.md,
`docs/architecture-30-apps-4-5-and-configs.md` SS30.3/SS30.4).

Judgment call, flagged in the Step 63 developer report: SS30.4's own
seed-config table describes this module as
`demo_75mm.CONFIG.derive(...) + a target apogee ~65% of the brake-closed
apogee`, then immediately qualifies it -- "the target is a *study* input,
so it is carried in apps/airbrake_sizing/targets.py and this config only
sets the vehicle side." SS30.6 explains why there is nothing of substance
left for *this* module to carry: "The app [4] owns control.airbrake_*
entirely. Whatever the incoming Config set there is overwritten by
brake_overrides" -- so a `control.airbrake_*` override placed here would
simply be discarded at solve time, and the target apogee is explicitly
not a vehicle property. This module therefore follows the qualifying
sentence and SS30.6's "owns entirely" rule over the table's own prose
aside: `demo_75mm` with an *empty* `derive()` overrides dict -- same
vehicle, new registry name, so App 4 has an explicit default to point at
without reaching into App 3's motor-selection vehicle, and so a future
vehicle change made specifically for the airbrake demo gets its own git
history separate from demo_75mm's.
"""

from __future__ import annotations

from configs.demo_75mm import CONFIG as _DEMO_75MM
from configs.schema import Config

CONFIG: Config = _DEMO_75MM.derive(
    name="demo_75mm_airbrake",
    overrides={},
    notes=(
        "demo_75mm, unchanged, registered under its own name as App 4's "
        "(airbrake sizing) default vehicle. No control.airbrake_* override "
        "lives here: the app owns that group entirely at solve time "
        "(architecture-30 SS30.6), and the target apogee is a study input "
        "carried in apps/airbrake_sizing/targets.py, not a vehicle property."
    ),
)

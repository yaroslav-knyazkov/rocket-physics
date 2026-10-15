"""configs/scenarios/demo_75mm_highland.py -- demo_75mm, unmodified, flown
from a different site in different weather (Step 74,
dev/docs/architecture-31-config-separation.md SS31.12).

The one worked mix-and-match demo this phase was built for: the
**existing, unmodified** `configs.rockets.demo_75mm.ROCKET` -- not
re-typed, not derived, not touched -- paired with the two new pieces
(`configs.sites.highland_1500m`, `configs.weather.breezy_isa`) instead
of `demo_75mm`'s usual `origin_msl` + `isa_dry_calm`. `s0` is omitted,
so it derives `theta = math.radians(85.0)` from `highland_1500m`'s
tilted rail (SS31.2 F5, D-51a) -- the first scenario in this project
where that derivation does something other than reproduce
`math.pi / 2` (SS31.2 F6, which is what every other registered
scenario's derived `s0` still does).
"""

from __future__ import annotations

from configs.rockets import demo_75mm
from configs.schema import Config, Scenario
from configs.sites import highland_1500m
from configs.weather import breezy_isa

SCENARIO = Scenario(
    name="demo_75mm_highland",
    rocket=demo_75mm.ROCKET,
    site=highland_1500m.SITE,
    weather=breezy_isa.WEATHER,
    notes="One vehicle, two sites, zero duplication.",
)

CONFIG: Config = SCENARIO.config

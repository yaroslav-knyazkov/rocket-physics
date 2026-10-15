"""configs/weather/isa_dry_calm.py -- the placeholder weather (Step 72,
dev/docs/architecture-31-config-separation.md SS31.7).

ISA, dry air, no wind, no sounding case (D-53).

`Weather(name="isa_dry_calm")` below takes **no arguments** for its
`atmosphere`/`soundings`/`wind` groups -- not `Atmosphere(model="isa",
humid_air=False)`, `Soundings(case="", ...)`, `Wind(model="none", ...)`
spelled out. The two are equal today, but they are not the same
promise: every pre-split seed config relied on *whatever
`sim/params.py`'s own defaults are* for these three groups, and this
module keeps relying on them rather than freezing today's values in
here. Spelling the fields out would make a future `sim/params.py`
default change a silent divergence between this module and every
other caller that still reads the bare defaults -- the argument-free
construction is the point, not an oversight.
"""

from __future__ import annotations

from configs.schema import Weather

WEATHER = Weather(name="isa_dry_calm")

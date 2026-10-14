"""configs/sites/origin_msl.py -- the placeholder launch site (Step 72,
docs/architecture-31-config-separation.md SS31.7).

"lat 0, lon 0, sea level, no rail" -- honest that this is a
placeholder, not a field anyone actually flies from (D-53).

`Site()` below is constructed with **no arguments at all**, not
`Site(lat0_deg=0.0, lon0_deg=0.0, h0_m=0.0, azimuth_deg=90.0,
L_rail=0.0, rail_angle_deg=90.0)` spelled out. The two are equal
today, but they are not the same promise: every pre-split seed config
relied on *whatever `sim/params.py`'s `Site` defaults are*, and this
module keeps relying on them rather than freezing today's values in
here. Spelling the fields out would make a future `sim/params.py`
default change a silent divergence between this module and every
other caller that still reads the bare default -- the argument-free
literal is the point, not an oversight.
"""

from __future__ import annotations

from configs.schema import LaunchSite
from sim.params import Site

SITE = LaunchSite(name="origin_msl", site=Site())

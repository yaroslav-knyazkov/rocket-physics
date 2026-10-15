"""configs/weather/breezy_isa.py -- ISA air with a steady analytic wind
(Step 74, dev/docs/architecture-31-config-separation.md SS31.12).

`Atmosphere(model="isa")` -- same air model as `isa_dry_calm`, so
pairing this piece with a non-default site is a clean test of SS31.2
F1 (the ISA column is evaluated at whatever `LaunchSite` piece's
`site.h0_m` says, with no change to this piece's own fields). The one
difference from `isa_dry_calm` is `wind`: `Wind(model="analytic",
ref_ms=6.0, dir_deg=225.0)` -- a steady 6 m/s wind out of the
southwest, rotated into the flight plane by whichever site's
`azimuth_deg` it is composed with (SS31.2 F3), not by anything this
piece owns.

Deliberately **no sounding case** -- `soundings` is left at its bare
default (`Soundings()`, `case=""`), not a real station's data. This is
the one thing SS31.10 risk 3 says to get right: a `Weather` piece may
safely be paired with *any* `LaunchSite` only as long as its wind is
tier-1 analytic (location-independent, a pure function of `ref_ms`/
`dir_deg` plus whichever site rotates it) or carries no sounding case
at all. A sounding-backed `Weather` (tiers 2/3) is projected into a
local tangent plane anchored at one specific site's
`lat0_deg`/`lon0_deg` (`sim/soundings.py:462-478`) -- composing it with
a *different* site would silently produce a plausible-looking,
physically meaningless wind field. This module exists precisely so
`demo_75mm_highland` (and any other scenario) can mix-and-match it with
whichever site it likes, with no such hazard.
"""

from __future__ import annotations

from configs.schema import Weather
from sim.params import Atmosphere, Wind

WEATHER = Weather(
    name="breezy_isa",
    atmosphere=Atmosphere(model="isa"),
    wind=Wind(model="analytic", ref_ms=6.0, dir_deg=225.0),
    notes=(
        "ISA air (same model as isa_dry_calm) plus a steady 6 m/s analytic "
        "wind from the southwest. No sounding case -- deliberately safe to "
        "pair with any site (SS31.10 risk 3)."
    ),
)

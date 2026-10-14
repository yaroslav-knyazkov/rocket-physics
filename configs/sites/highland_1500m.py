"""configs/sites/highland_1500m.py -- the architect's own synthetic
high-altitude launch site (Step 74,
docs/architecture-31-config-separation.md SS31.12).

A synthetic site, not a surveyed one -- `lat0_deg=39.7` is only
illustrative of "somewhere on the high desert/mountain plains of the
western US" (roughly the latitude band of real high-altitude amateur
rocketry fields such as Spaceport America, NM and the Colorado high
desert; not any specific field's actual coordinates). `h0_m=1500.0` is
the one number this module exists to carry: 1500 m of MSL elevation
feeds straight into the ISA/atmosphere column via
`altitude_msl = altitude_agl + site.h0_m` (SS31.2 F1), so pairing this
site with `configs.weather.breezy_isa` flies the *same* `demo_75mm`
rocket through measurably thinner air than `origin_msl`'s sea level,
with zero duplicated vehicle numbers.

The rail: a short, 3 m rod tilted to `rail_angle_deg=85.0` (not the
90.0 every other registered site uses) -- a deliberately non-default
choice so that `configs.schema._pad_state`'s derivation of `s0.theta`
from the rail angle (SS31.2 F5, D-51a) does something other than
reproduce `math.pi / 2` for the first time in this project
(`math.radians(85.0)`, SS31.2 F6). `azimuth_deg` is left at the
`Site` default (90.0, downrange along +x) -- this site demonstrates the
elevation/rail-tilt axis, not the heading axis.
"""

from __future__ import annotations

from configs.schema import LaunchSite
from sim.params import Site

SITE = LaunchSite(
    name="highland_1500m",
    site=Site(
        lat0_deg=39.7,          # illustrative high-desert latitude, not a surveyed field
        lon0_deg=-104.9,        # illustrative; paired only with analytic (location-independent) weather
        h0_m=1500.0,            # the number this module exists for -- feeds the atmosphere column
        L_rail=3.0,             # a short rail/rod, m
        rail_angle_deg=85.0,    # tilted off vertical -- drives a non-trivial s0.theta (F5/D-51a)
    ),
    notes=(
        "The architect's own synthetic high-altitude site -- 1500 m MSL and "
        "an 85 deg rail tilt, picked to exercise the site-elevation-feeds-"
        "atmosphere coupling (SS31.2 F1) and the rail-angle-drives-s0 "
        "derivation (SS31.2 F5) end to end. Not a surveyed field; lat/lon "
        "are illustrative only."
    ),
)

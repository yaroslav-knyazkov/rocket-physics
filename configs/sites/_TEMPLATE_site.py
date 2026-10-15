"""configs/sites/_TEMPLATE_site.py -- TEMPLATE, fill in your own
numbers (Step 72, dev/docs/architecture-31-config-separation.md SS31.5).

This file is a blank `LaunchSite` piece: one place you fly from, and
the pad standing on it. Every field below is commented with its unit,
its meaning, and the consequence of leaving it at the placeholder
value.

This module is **never registered** -- it is deliberately absent from
`configs/sites/__init__.py`'s `_MODULES` tuple, and must stay absent.
It still imports cleanly on its own --
`python -c "import configs.sites._TEMPLATE_site"` must succeed -- so
the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

To use this template:
  1. Fill in every `# <-- fill this in` field below with your own numbers.
  2. Rename this file (and the `name="my_site"` string below) to
     whatever you want your site called.
  3. Add `from configs.sites import <your_module_name>` and one line
     to `configs/sites/__init__.py`'s `_MODULES` tuple.
"""

from __future__ import annotations

from configs.schema import LaunchSite
from sim.params import Site

SITE = LaunchSite(
    name="my_site",  # <-- rename this string to match the filename once you rename it

    site=Site(
        lat0_deg=0.0,          # <-- fill this in: launch site latitude, deg (0.0 = placeholder)
        lon0_deg=0.0,          # <-- fill this in: launch site longitude, deg (0.0 = placeholder)
        h0_m=0.0,              # <-- fill this in: launch site elevation above MSL, m
        azimuth_deg=90.0,      # <-- direction of +x (downrange), deg clockwise from North
        L_rail=0.0,            # <-- launch rail/rod length, m; 0.0 = no rail modelled
        rail_angle_deg=90.0,   # <-- rail elevation from horizontal, deg; keep equal
        # to the s0.theta angle below if your scenario sets an explicit
        # s0 -- nothing enforces that automatically (SS31.3.4). With
        # s0=None on the Scenario (the usual case), s0.theta is instead
        # DERIVED from this angle, so that foot-gun does not apply.
    ),

    notes=(
        "My actual launch site -- <say where these numbers came from: "
        "GPS survey, map, estimate, date>."
    ),
)

"""configs/scenarios/_TEMPLATE_scenario.py -- TEMPLATE, fill in your
own numbers (Step 72, dev/docs/architecture-31-config-separation.md
SS31.5).

This file is a blank `Scenario`: one named combination of a rocket, a
motor, a site, and a day's weather, plus the run-level groups nobody
reuses by name (gravity/solver/g0). It demonstrates the thing this
whole phase is for -- referencing named pieces **by import** instead
of re-specifying them every time.

This module is **never registered** -- it is deliberately absent from
`configs/scenarios/__init__.py`'s `_MODULES` tuple, and must stay
absent. It still imports cleanly on its own --
`python -c "import configs.scenarios._TEMPLATE_scenario"` must
succeed -- so the file does not silently rot; pinned by
`tests/test_config_registries.py` (SS31.8 #6).

Referencing pieces by import, once you have some registered, looks
like this:

    from configs.rockets.demo_75mm import ROCKET  # <-- replace with your own once you have one

`configs.rockets.demo_75mm` does not exist yet as of this step (Step
72 only builds the four registries -- `rockets`' and `scenarios`' are
still empty; Step 73 is what moves the seed rockets in) -- the import
above is illustrative, a forward reference to the shape Step 73
produces, **not working code today**. This template builds its
placeholder rocket inline below instead, exactly so the file can still
import cleanly before any real rocket piece exists; the motor, site and
weather pieces below, however, really do exist already
(`configs.motors.placeholder`, `configs.sites.origin_msl`,
`configs.weather.isa_dry_calm`), so those three imports are live,
working examples of the pattern.

A flat, whole-`Config` scenario module -- one `Config(...)` literal
with no `Rocket`/`Motor`/`LaunchSite`/`Weather`/`Scenario` pieces at
all, the shape the user's own `configs/_TEMPLATE_my_rocket.py` uses --
remains legal and registrable here, forever (SS31.5, SS31.8 #7): the
scenario registry only requires a module to expose `CONFIG: Config`;
`SCENARIO` below is optional metadata for anyone who wants the
piece-composed form instead. Splitting into pieces is not mandatory
just because this package exists.

To use this template:
  1. Fill in every `# <-- fill this in` field below (and build or
     import a real `Rocket` rather than the inline placeholder here,
     once you have one -- see configs/rockets/_TEMPLATE_rocket.py).
  2. Rename this file (and the `name="my_scenario"` string below) to
     whatever you want your scenario called.
  3. Add `from configs.scenarios import <your_module_name>` and one
     line to `configs/scenarios/__init__.py`'s `_MODULES` tuple.
"""

from __future__ import annotations

from configs.motors.placeholder import MOTOR
from configs.schema import Airframe, Rocket, Scenario
from configs.sites import origin_msl
from configs.weather import isa_dry_calm

# Normally you would import a registered rocket piece, e.g.:
#     from configs.rockets.demo_75mm import ROCKET  # <-- replace with your own once you have one
# `configs.rockets` has no registered rockets yet as of this step, so
# this template builds a minimal placeholder inline instead. See
# configs/rockets/_TEMPLATE_rocket.py for every field, with comments.
_placeholder_rocket = Rocket(
    name="my_rocket",                  # <-- rename to match whatever rocket you actually use
    airframe=Airframe(m=1.5, I=0.08),  # <-- fill this in (see _TEMPLATE_rocket.py for the full field set)
)

SCENARIO = Scenario(
    name="my_scenario",  # <-- rename this string to match the filename once you rename it

    rocket=_placeholder_rocket,    # <-- fill this in: your own Rocket, built inline or imported
    motor=MOTOR,                   # <-- fill this in: your own Motor, see configs/motors/_TEMPLATE_motor.py
    site=origin_msl.SITE,          # <-- fill this in: swap for your own LaunchSite once you have one
    weather=isa_dry_calm.WEATHER,  # <-- fill this in: swap for your own Weather once you have one

    # gravity, solver, g0 default to the constant/RK45/9.80665 trio
    # every demo scenario uses -- leave them unless you specifically
    # need a different integrator, tolerance, or gravity model.

    overrides={},  # <-- dotted-path tweaks applied AFTER assembly, e.g. {"site.rail_angle_deg": 85.0}
    # s0 defaults to None, which derives "on the pad, nose along the
    # rail" from site.rail_angle_deg (SS31.4) -- leave it unless you
    # need a non-pad initial state.

    notes=(
        "My actual scenario -- <say what this combination is for and "
        "where the numbers came from>."
    ),
)

CONFIG = SCENARIO.config

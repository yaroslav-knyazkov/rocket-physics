"""configs/ -- the plain-class config surface (Phase 2.18, D-141/Cfg-1).

No registry: construct Motor/Rocket/LaunchSite/Weather/Scenario directly
with your own values, assemble() into a Config, run_sim() it. See
apps/input/demo_scenario.py for a complete, commented example (the
REQ/OPT crib sheet the old configs/*/_TEMPLATE_*.py files used to be;
moved out of examples/worked_scenario.py at Phase 2.19, Step 130) --
`python -m examples.worked_scenario` runs it end to end.

The former file+registry convention (one file per instance, explicit
_MODULES tuples, `configs.get(name)` lookup by string) is archived at
dev/archive/configs-registry-2026-10/ (git tag pre-pivot-configs-registry) --
D-137..D-142, dev/docs/pivot-configs-and-packaging-analysis.md.
"""

from __future__ import annotations

from configs.schema import (
    Airframe, Config, LaunchSite, Motor, Rocket, Scenario, Sections, Variant, Weather, assemble,
)
from apps.sim.engine.params import (
    Aero, Atmosphere, Control, Lengths, Recovery, Site, Solver, Soundings, Thrust, Wind,
)

__all__ = [
    "Airframe", "Config", "LaunchSite", "Motor", "Rocket", "Scenario", "Sections", "Variant",
    "Weather", "assemble", "Aero", "Atmosphere", "Control", "Lengths", "Recovery", "Site",
    "Solver", "Soundings", "Thrust", "Wind",
]

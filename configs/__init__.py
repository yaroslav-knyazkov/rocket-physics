"""configs/ -- the shared configuration package (Step 63, roadmap.md,
`docs/architecture-30-apps-4-5-and-configs.md` SS30.3/SS30.4; rewritten
to delegate to `configs.scenarios` at Step 73,
`docs/architecture-31-config-separation.md` SS31.6/SS31.7; this
docstring turned into the package's "how do I add my own" guide at
Step 74, SS31.12).

`get(name)` resolves a **scenario** name -- a named combination of a
rocket, a launch site and a day's weather (`configs.schema.Scenario`,
assembled into the ordinary `Config` every tool already takes), or a
flat, hand-written `Config` module for anyone who prefers one file.
Either shape registers the same way: `configs.scenarios` only requires a
module to expose `CONFIG: Config`. `CONFIGS`, `names()` and `get()` below
are direct references to that package's own registry, not a second
implementation of the same lookup logic.

The pieces behind a scenario -- which rocket, which site, which
weather -- are reachable through `get_scenario(name)`, which returns the
`Scenario` object for a piece-composed scenario module or `None` for a
flat `Config`-only one (SS31.6's one *additive* API: `configs.get`,
`.names()` and every existing caller see no change at all).

Anyone adding their own rocket, site, weather or scenario should start
under the matching subpackage rather than here:

  - `configs/rockets/`  -- vehicles: airframe, motor, aero, recovery, control
  - `configs/sites/`    -- launch sites: pad geodesy and rail
  - `configs/weather/`  -- a flying day's air: atmosphere, soundings, wind
  - `configs/scenarios/` -- named rocket + site + weather combinations
    (what this package's registry is built from); a flat whole-`Config`
    module is also legal here, forever (SS31.5, SS31.8 #7)

Each subpackage ships a `_TEMPLATE_*` module with every field commented;
see that module's own docstring for the three-step "fill in, rename,
register" instructions. Registration is the only place a name is bound:
`CONFIGS` is keyed off each module's `CONFIG.name`, not the module's
filename, so a name/filename mismatch is possible in principle --
`tests/test_configs.py` pins that it cannot happen silently.

`configs/scenarios/demo_75mm_highland.py` is one worked example of the
whole point of this package: the **same, unmodified**
`configs/rockets/demo_75mm.py` rocket piece, flown from a different
site (`configs/sites/highland_1500m.py`, 1500 m MSL, a tilted rail) in
different weather (`configs/weather/breezy_isa.py`, a steady analytic
wind) -- one vehicle, two sites, zero duplication. Reading those three
modules side by side is the fastest way to see what "start under the
matching subpackage" buys you in practice.
"""

from configs import rockets, scenarios, sites, weather
from configs.schema import Config, LaunchSite, Rocket, Scenario, Variant, Weather

_MODULES = scenarios._MODULES

CONFIGS: dict[str, Config] = scenarios.SCENARIOS
names = scenarios.names
get = scenarios.get


def get_scenario(name: str) -> "Scenario | None":
    """The `Scenario` object behind the registered config named `name`,
    or `None` if that config is a flat, whole-`Config` module with no
    piece composition behind it (SS31.6).

    Raises `KeyError` (via `get`, same message) if `name` is not
    registered at all -- this only distinguishes piece-composed from
    flat *among registered* names.
    """
    get(name)  # raises KeyError with the usual message if unregistered
    for mod in scenarios._MODULES:
        if mod.CONFIG.name == name:
            return getattr(mod, "SCENARIO", None)
    return None


__all__ = [
    "Config",
    "Variant",
    "Rocket",
    "LaunchSite",
    "Weather",
    "Scenario",
    "CONFIGS",
    "names",
    "get",
    "get_scenario",
    "rockets",
    "sites",
    "weather",
    "scenarios",
]

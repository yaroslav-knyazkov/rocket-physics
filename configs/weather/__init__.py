"""configs/weather/ -- the weather-piece registry (Step 72,
docs/architecture-31-config-separation.md SS31.5, D-53).

This is the user's *atmosphere* axis; it carries wind and the
sounding case too, because a sounding measures both (SS31.3.3, F4).
"Weather" rather than "atmosphere" is the one vocabulary gap this
project's naming has -- `Weather` would otherwise collide with
`sim.params.Atmosphere`, which the piece itself contains
(`from sim.params import Atmosphere` and a same-named `configs.schema`
class in one file is a real hazard D-53 rejected on those grounds).

Same registry shape as `configs/__init__.py`: an explicit `_MODULES`
tuple (never directory auto-discovery), `WEATHER` keyed off each
module's `WEATHER.name`, `names()`, and `get()` whose `KeyError` lists
every available name.

Piece modules do `from configs.schema import Weather`, never
`from configs import Weather` and never reach up into
`configs.scenarios` or the `configs` package itself (SS31.5's import
DAG).

`isa_dry_calm` -- ISA, dry air, no wind, no sounding case (SS31.7) --
and `breezy_isa`, ISA air plus a steady analytic wind added at Step 74
(SS31.12), are the two registered weather pieces as of this step.
`configs.weather._TEMPLATE_weather` imports cleanly (SS31.8 #6) but is
deliberately never in `_MODULES` -- see that module's docstring.
"""

from configs.schema import Weather
from configs.weather import breezy_isa, isa_dry_calm

_MODULES = (isa_dry_calm, breezy_isa)

WEATHER: dict[str, Weather] = {m.WEATHER.name: m.WEATHER for m in _MODULES}


def names() -> "list[str]":
    """Every registered weather name, in registration order."""
    return [m.WEATHER.name for m in _MODULES]


def get(name: str) -> Weather:
    """The registered `Weather` named `name`.

    Raises `KeyError` listing every available name -- the one error
    message a typo'd weather name has to produce.
    """
    try:
        return WEATHER[name]
    except KeyError:
        raise KeyError(
            f"unknown weather {name!r}; available: {', '.join(names())}"
        ) from None


__all__ = ["Weather", "WEATHER", "names", "get"]

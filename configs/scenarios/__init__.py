"""configs/scenarios/ -- the scenario registry (Step 72,
docs/architecture-31-config-separation.md SS31.5).

This is what `configs.get()` delegates to, as of Step 73
(`docs/architecture-31-config-separation.md` SS31.7): `toy_05kg`,
`demo_75mm` and `demo_75mm_airbrake` moved under this package and are
what first fill `_MODULES` in. `demo_75mm_highland` -- the
one-rocket-two-sites mix-and-match demo -- was added at Step 74
(SS31.12).

Same registry shape as `configs/__init__.py`, which this package is
modelled on directly: an explicit `_MODULES` tuple (never directory
auto-discovery), `SCENARIOS` keyed off each module's `CONFIG.name` --
**not** `SCENARIO.name` -- because a scenario module is only required
to expose `CONFIG: Config`; a `SCENARIO` piece-composition object is
optional metadata (SS31.5, SS31.8 #7). This is what lets a flat,
hand-written `Config(...)` module (the shape the user's own
`configs/_TEMPLATE_my_rocket.py` uses) register here unchanged, side
by side with a piece-composed scenario, with nothing downstream able
to tell the difference.

`names()` and `get()` follow the same `KeyError`-lists-every-name
convention as every other registry in this project.
"""

from configs.schema import Config
from configs.scenarios import (
    demo_75mm,
    demo_75mm_airbrake,
    demo_75mm_highland,
    demo_75mm_k570,
    toy_05kg,
)

_MODULES = (toy_05kg, demo_75mm, demo_75mm_airbrake, demo_75mm_highland, demo_75mm_k570)

SCENARIOS: dict[str, Config] = {m.CONFIG.name: m.CONFIG for m in _MODULES}


def names() -> "list[str]":
    """Every registered scenario name, in registration order."""
    return [m.CONFIG.name for m in _MODULES]


def get(name: str) -> Config:
    """The registered `Config` named `name`.

    Raises `KeyError` listing every available name -- the one error
    message a typo'd scenario name has to produce.
    """
    try:
        return SCENARIOS[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario {name!r}; available: {', '.join(names())}"
        ) from None


__all__ = ["Config", "SCENARIOS", "names", "get"]

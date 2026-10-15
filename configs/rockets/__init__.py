"""configs/rockets/ -- the rocket-piece registry (Step 72,
dev/docs/architecture-31-config-separation.md SS31.5).

Same registry shape as `configs/__init__.py`, one level down: an
explicit `_MODULES` tuple (never directory auto-discovery -- a
half-finished draft rocket must not become real by merely existing,
and "who uses this rocket" stays one grep), `ROCKETS` keyed off each
module's `ROCKET.name`, `names()`, and `get()` whose `KeyError` lists
every available name.

Piece modules do `from configs.schema import Rocket`, never
`from configs import Rocket` and never reach up into
`configs.scenarios` or the `configs` package itself -- pieces sit at
the bottom of the import DAG (SS31.5): `configs/__init__` ->
`configs.scenarios` -> `configs.{rockets, sites, weather}` ->
`configs.schema` -> `sim.*`, with no edge back up.

One registered rocket, `demo` (Phase 2.16, Step 91,
`dev/docs/architecture-33-configs-one-demo.md` SS33.2).
`configs.rockets._TEMPLATE_rocket` imports
cleanly (SS31.8 #6) but is deliberately never in `_MODULES` -- see that
module's docstring.
"""

from configs.rockets import demo
from configs.schema import Rocket

_MODULES = (demo,)

ROCKETS: dict[str, Rocket] = {m.ROCKET.name: m.ROCKET for m in _MODULES}


def names() -> "list[str]":
    """Every registered rocket name, in registration order."""
    return [m.ROCKET.name for m in _MODULES]


def get(name: str) -> Rocket:
    """The registered `Rocket` named `name`.

    Raises `KeyError` listing every available name -- the one error
    message a typo'd rocket name has to produce.
    """
    try:
        return ROCKETS[name]
    except KeyError:
        raise KeyError(
            f"unknown rocket {name!r}; available: {', '.join(names())}"
        ) from None


__all__ = ["Rocket", "ROCKETS", "names", "get"]

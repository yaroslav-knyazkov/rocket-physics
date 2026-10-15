"""configs/motors/ -- the motor-piece registry (Phase 2.16, Step 79,
dev/docs/architecture-32-motor-separation.md SS32.2.1, SS31.5 -- the fifth
time this project uses the registry shape SS31.5 first set out).

Same registry shape as `configs/rockets/__init__.py` (and
`configs/sites/__init__.py`, `configs/weather/__init__.py`,
`configs/scenarios/__init__.py`): an explicit `_MODULES` tuple (never
directory auto-discovery -- a half-finished draft motor must not become
real by merely existing, and "who uses this motor" stays one grep),
`MOTORS` keyed off each module's `MOTOR.name`, `names()`, and `get()`
whose `KeyError` lists every available name.

Piece modules do `from configs.schema import Motor`, never `from
configs import Motor` and never reach up into `configs.scenarios` or
the `configs` package itself -- pieces sit at the bottom of the import
DAG (SS31.5): `configs/__init__` -> `configs.scenarios` ->
`configs.{rockets, sites, weather, motors}` -> `configs.schema` ->
`sim.*`, with no edge back up.

One registered motor, `cti_k570` (the real `.eng` curve, "endpoints"
mass model; Phase 2.16, Step 91, `dev/docs/architecture-33-configs-one-demo.md`
SS33.2). `configs.motors._TEMPLATE_motor` imports cleanly (SS31.8 #6)
but is deliberately never in `_MODULES` -- see that module's docstring,
and never add it there.

"""

from configs.motors import cti_k570
from configs.schema import Motor

_MODULES = (cti_k570,)

MOTORS: dict[str, Motor] = {m.MOTOR.name: m.MOTOR for m in _MODULES}


def names() -> "list[str]":
    """Every registered motor name, in registration order."""
    return [m.MOTOR.name for m in _MODULES]


def get(name: str) -> Motor:
    """The registered `Motor` named `name`.

    Raises `KeyError` listing every available name -- the one error
    message a typo'd motor name has to produce.
    """
    try:
        return MOTORS[name]
    except KeyError:
        raise KeyError(
            f"unknown motor {name!r}; available: {', '.join(names())}"
        ) from None


__all__ = ["Motor", "MOTORS", "names", "get"]

"""configs/ -- the shared configuration package (Step 63, roadmap.md,
`docs/architecture-30-apps-4-5-and-configs.md` SS30.3/SS30.4).

The registry **is** the package API: `CONFIGS`, `names()`, `get()`. An
explicit module tuple, not directory auto-discovery -- `pkgutil`/
`importlib` globbing would make a config appear by merely existing, which
is convenient exactly until a half-finished draft file breaks every app's
import; explicit is also greppable ("who uses this config" is one
search). Registration is the only place a name is bound: `CONFIGS` is
keyed off each module's `CONFIG.name`, not the module's filename, so a
name/filename mismatch is possible in principle -- `tests/test_configs.py`
pins that it cannot happen silently.
"""

from configs import demo_75mm, demo_75mm_airbrake, toy_05kg
from configs.schema import Config, Variant

_MODULES = (toy_05kg, demo_75mm, demo_75mm_airbrake)

CONFIGS: dict[str, Config] = {m.CONFIG.name: m.CONFIG for m in _MODULES}


def names() -> "list[str]":
    """Every registered config name, in registration order."""
    return [m.CONFIG.name for m in _MODULES]


def get(name: str) -> Config:
    """The registered `Config` named `name`.

    Raises `KeyError` listing every available name -- the one error
    message a typo'd `--config` has to produce.
    """
    try:
        return CONFIGS[name]
    except KeyError:
        raise KeyError(
            f"unknown config {name!r}; available: {', '.join(names())}"
        ) from None


__all__ = ["Config", "Variant", "CONFIGS", "names", "get"]

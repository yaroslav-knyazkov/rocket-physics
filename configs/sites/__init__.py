"""configs/sites/ -- the launch-site-piece registry (Step 72,
docs/architecture-31-config-separation.md SS31.5).

Same registry shape as `configs/__init__.py`: an explicit `_MODULES`
tuple (never directory auto-discovery), `SITES` keyed off each
module's `SITE.name`, `names()`, and `get()` whose `KeyError` lists
every available name.

Piece modules do `from configs.schema import LaunchSite`, never
`from configs import LaunchSite` and never reach up into
`configs.scenarios` or the `configs` package itself (SS31.5's import
DAG -- see `configs/rockets/__init__.py`'s docstring for the full
chain).

`origin_msl` is the only registered site as of this step --
"lat 0, lon 0, sea level, no rail", honest that it is a placeholder,
not a field anyone actually flies from (SS31.7). `configs.sites.
_TEMPLATE_site` imports cleanly (SS31.8 #6) but is deliberately never
in `_MODULES` -- see that module's docstring.
"""

from configs.schema import LaunchSite
from configs.sites import origin_msl

_MODULES = (origin_msl,)

SITES: dict[str, LaunchSite] = {m.SITE.name: m.SITE for m in _MODULES}


def names() -> "list[str]":
    """Every registered site name, in registration order."""
    return [m.SITE.name for m in _MODULES]


def get(name: str) -> LaunchSite:
    """The registered `LaunchSite` named `name`.

    Raises `KeyError` listing every available name -- the one error
    message a typo'd site name has to produce.
    """
    try:
        return SITES[name]
    except KeyError:
        raise KeyError(
            f"unknown site {name!r}; available: {', '.join(names())}"
        ) from None


__all__ = ["LaunchSite", "SITES", "names", "get"]

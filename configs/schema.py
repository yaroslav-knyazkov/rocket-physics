"""configs/schema.py -- `Config` and `Variant` (Step 63, roadmap.md,
`docs/architecture-30-apps-4-5-and-configs.md` SS30.4).

Both frozen dataclasses, both trivially constructible, no inheritance, no
builders. `Config` is one complete, runnable scenario (`Params` + initial
`State` + provenance notes) -- vehicle-and-environment level, reusable by
every tool including `run.py`. `Variant` is a *named delta* against some
`Config` -- the generalisation of App 3's `MotorEntry.overrides`, for
studies that compare N perturbations of one baseline.

Importing this module: config modules (`configs/<name>.py`) must do
`from configs.schema import Config`, **never** `from configs import
Config`. `configs/__init__.py` imports every config module to build the
registry, so a config module reaching back into the package's own (at
that point still partially-initialised) namespace would be a circular
import. Importing this submodule directly, as above, is always safe --
`configs/schema.py` has no dependency on `configs/__init__.py`.

Step 71 (`docs/architecture-31-config-separation.md` SS31.4) adds four
more frozen dataclasses -- `Rocket`, `LaunchSite`, `Weather`, `Scenario`
-- and the module-level `assemble(sc)` / `_pad_state(site)` that turn a
`Scenario` into an ordinary `Config`. **`Config` and `Variant` above are
unchanged** and remain the only consumption-level API `apps/` and every
`run*.py` ever take -- the pieces are a construction-time convenience
that assembles down to the same `Config` nothing downstream needs to
know came from pieces at all.

The one-owner invariant (SS31.4, D-49): every one of `Params`' twelve
groups has exactly one owning piece (`weight`/`lengths`/`thrust`/`aero`/
`recovery`/`control` from `Rocket`; `site` from `LaunchSite`;
`atmosphere`/`soundings`/`wind` from `Weather`; `gravity`/`solver`/`g0`
as plain `Scenario` fields, SS31.3.2). `assemble` has no merge logic, no
"last writer wins" and no partial-group updates -- the keyword set of
its single `Params(...)` call is pinned, structurally, against
`{f.name for f in dataclasses.fields(Params)}` by
`tests/test_config_pieces.py` (SS31.8 #1), so a thirteenth `Params`
group would fail that test loudly instead of silently taking its
default in every scenario.

The import rule above now also applies to pieces: piece modules do
`from configs.schema import Rocket`, **never** `from configs import
Rocket`, and a piece never reaches up into `configs.scenarios`,
`configs.rockets`, `configs.sites` or `configs.weather` -- those
subpackages do not exist yet as of this step (Step 72 adds them); this
step only adds the piece *types* and the assembly function they
compose through.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from sim.params import Aero
from sim.params import Atmosphere
from sim.params import Control
from sim.params import Gravity
from sim.params import Lengths
from sim.params import Params
from sim.params import Recovery
from sim.params import Site
from sim.params import Solver
from sim.params import Soundings
from sim.params import Thrust
from sim.params import Weight
from sim.params import Wind
from sim.params import replace as params_replace
from sim.state import State

__all__ = [
    "Config",
    "Variant",
    "Rocket",
    "LaunchSite",
    "Weather",
    "Scenario",
    "assemble",
]


@dataclasses.dataclass(frozen=True)
class Config:
    """One complete, runnable scenario: the `Params`, the initial `State`,
    and where the numbers came from."""

    name: str                  # registry key, e.g. "demo_75mm"
    params: Params
    s0: State
    notes: str = ""            # provenance: source of the numbers, date, what it is for

    def derive(
        self,
        name: str,
        overrides: dict[str, Any],
        notes: str = "",
        s0: State | None = None,
    ) -> "Config":
        """A new `Config`, `overrides` applied via `sim.params.replace` --
        one call, arbitrarily many dotted keys (architecture.md SS29 F1),
        so no untouched field anywhere in `Params` is silently reset.
        `s0` defaults to this `Config`'s own (inherited unless overridden
        here). Frozen dataclasses throughout: this `Config` is never
        mutated, and the result is a new, independent object."""
        return dataclasses.replace(
            self,
            name=name,
            params=params_replace(self.params, overrides),
            s0=self.s0 if s0 is None else s0,
            notes=notes,
        )

    def with_variant(self, v: "Variant") -> "Config":
        """`v` applied to this config, named `f"{self.name}+{v.name}"`."""
        return self.derive(name=f"{self.name}+{v.name}", overrides=v.overrides, notes=v.notes)


@dataclasses.dataclass(frozen=True)
class Variant:
    """A *named delta* against some `Config` -- the generalisation of App
    3's `MotorEntry.overrides`, for studies that compare N perturbations
    of one baseline (App 5 mode (a), and any future what-if sweep)."""

    name: str
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    def apply(self, cfg: Config) -> Config:
        """`== cfg.with_variant(self)` -- implemented in terms of it so
        the two can never drift apart."""
        return cfg.with_variant(self)


# ----------------------------------------------------------------------
# Step 71 (architecture-31-config-separation.md SS31.4): the four piece
# types, and the `assemble` function that composes them into a `Config`.
# ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Rocket:
    """One vehicle: airframe, motor installation, aerodynamics, and the
    recovery/control hardware bolted to it (SS31.3.1)."""

    name: str
    weight: Weight  # the only required group
    lengths: Lengths = dataclasses.field(default_factory=Lengths)
    thrust: Thrust = dataclasses.field(default_factory=Thrust)
    aero: Aero = dataclasses.field(default_factory=Aero)
    recovery: Recovery = dataclasses.field(default_factory=Recovery)
    control: Control = dataclasses.field(default_factory=Control)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class LaunchSite:
    """One place you fly from, and the pad standing on it (SS31.3.4)."""

    name: str
    site: Site = dataclasses.field(default_factory=Site)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class Weather:
    """One flying day's air: the atmosphere model, the sounding case it may
    read, and the wind -- one piece because a sounding measures all three
    (SS31.3.3, F4)."""

    name: str
    atmosphere: Atmosphere = dataclasses.field(default_factory=Atmosphere)
    soundings: Soundings = dataclasses.field(default_factory=Soundings)
    wind: Wind = dataclasses.field(default_factory=Wind)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One named combination of a rocket, a site and a day's weather, plus
    the run-level groups nobody reuses by name (SS31.3.2). `.config`
    assembles it into the ordinary `Config` every tool already takes."""

    name: str
    rocket: Rocket
    site: LaunchSite
    weather: Weather
    gravity: Gravity = dataclasses.field(default_factory=Gravity)
    solver: Solver = dataclasses.field(default_factory=Solver)
    g0: float = 9.80665
    s0: State | None = None  # None -> derived from the rail (D-51)
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    @property
    def config(self) -> Config:
        return assemble(self)


def assemble(sc: Scenario) -> Config:
    """SS31.4. Exactly one owner per `Params` group -- no merge, no
    precedence rule, no partial groups. The keyword set below is
    `dataclasses.fields(Params)` exactly (pinned by test, SS31.8 #1)."""
    # (1) gather groups from the pieces -- one keyword per group, each
    #     sourced from exactly one owning piece
    p = Params(
        weight=sc.rocket.weight,
        lengths=sc.rocket.lengths,
        thrust=sc.rocket.thrust,
        aero=sc.rocket.aero,
        recovery=sc.rocket.recovery,
        control=sc.rocket.control,
        site=sc.site.site,
        atmosphere=sc.weather.atmosphere,
        soundings=sc.weather.soundings,
        wind=sc.weather.wind,
        gravity=sc.gravity,
        solver=sc.solver,
        g0=sc.g0,
    )
    # (2) the scenario's own last word, dotted paths over the whole tree
    if sc.overrides:
        p = params_replace(p, sc.overrides)  # sim.params.replace, SS29 F1
    # (3) s0 AFTER overrides -- so an overridden rail angle moves the
    #     initial attitude with it (F5, D-51); getting this order backwards
    #     would re-create F5's foot-gun inside the mechanism that
    #     advertises fixing it.
    s0 = sc.s0 if sc.s0 is not None else _pad_state(p.site)
    return Config(name=sc.name, params=p, s0=s0, notes=sc.notes)


def _pad_state(site: Site) -> State:
    """At rest on the pad, nose along the rail. `math.radians(90.0)` is
    exactly `math.pi / 2` (F6), so this reproduces every existing config's
    `s0` bit-for-bit."""
    return State(
        x=0.0,
        z=0.0,
        vx=0.0,
        vz=0.0,
        theta=math.radians(site.rail_angle_deg),
        omega=0.0,
    )

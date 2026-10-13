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
"""

from __future__ import annotations

import dataclasses
from typing import Any

from sim.params import Params
from sim.params import replace as params_replace
from sim.state import State


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

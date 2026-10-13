"""apps/weight_aero_tradeoff/scenarios.py -- the default trade-surface
grid (Step 67, roadmap.md; docs/architecture-30-apps-4-5-and-configs.md
SS30.7.1).

Per the project's D-23 convention (a Python literal, every number
commented with *why*, same style as `apps/motor_selection/motors.py`):
this module carries F10's measured default box, not a derivation buried
in `trade_surface.py`.

**Two different kinds of literal on the two axes, deliberately:**

- The **C_dA axis is relative**: `[0.5, 1.5] x` whatever config's own
  baseline `C_dA = aero.S * aero.C_x` happens to be. This is what makes
  the default grid "bracket the baseline" (SS30.7.1) for *any* `--config`
  the app is pointed at, not just `demo_75mm` -- a config with a very
  different C_dA still gets a box centred on its own value.
- The **mass axis is an absolute literal**, `[1.0, 2.5] kg`: it is F10's
  measured band around `demo_75mm`'s own 1.5 kg baseline, the same way
  `apps/motor_selection/motors.py`'s motor list is specific to that one
  demo airframe rather than derived from whatever config is loaded. A
  vehicle with a very different mass scale (a 50 kg vehicle, say) would
  want its own band -- this is a known limitation of a literal default,
  not a bug (flagged in the Step 67 developer report as a judgment call:
  the alternative, scaling the mass axis off `cfg.params.weight.m` the
  same way the C_dA axis scales off the baseline product, was considered
  and rejected here because F10's own measurement fixed absolute numbers,
  1.0-2.5 kg, not a multiplier -- "redo exactly what was measured" beats
  "generalise a literal the design doc did not ask to be generalised").

11x11 (121 grid points) because that is what F10 measured: smooth,
strictly monotone decreasing along both axes over this exact box, 121
runs in ~5.75 s (47.5 ms/run) on the architect's own measurement. This
tree's own measured wall-clock against `demo_75mm`'s registered
`"placeholder.csv"` motor is higher (~39 s / ~320 ms per grid point,
Step 67 developer report) -- `run_sim` itself is still ~45 ms/run, in
line with F10, but `apps.common.flight_stats.flight_stats`'s own
ascent-window reduction (re-evaluating `dynamics.derivatives`/`flow_state`
over a ~4000-point grid per flight) dominates at this config's longer
flight times. Not re-pinned here (expected order of magnitude, not an
exact number, per the roadmap ticket) -- see
`tests/test_weight_aero_tradeoff.py`'s end-to-end test.
"""

from __future__ import annotations

import numpy as np

from apps.weight_aero_tradeoff.trade_surface import TradeAxes
from configs.schema import Config, Variant

# C_dA axis: relative multipliers of cfg's own baseline C_dA = aero.S * aero.C_x.
_CDA_LOW_MULT = 0.5
_CDA_HIGH_MULT = 1.5

# Mass axis: F10's measured absolute band around demo_75mm's 1.5 kg baseline.
_MASS_LOW_KG = 1.0
_MASS_HIGH_KG = 2.5

_GRID_N = 11  # F10: 11x11 = 121 runs, ~5.75 s measured, smooth and monotone


def default_axes(cfg: Config) -> TradeAxes:
    """The default 11x11 grid: C_dA in `[0.5, 1.5] * cfg`'s own baseline
    `aero.S * aero.C_x` (brackets whatever config is loaded), mass in the
    literal `[1.0, 2.5] kg` band (F10, specific to the demo vehicle's own
    mass scale -- see module docstring)."""
    cda_baseline = cfg.params.aero.S * cfg.params.aero.C_x
    cda_values = tuple(
        np.linspace(_CDA_LOW_MULT * cda_baseline, _CDA_HIGH_MULT * cda_baseline, _GRID_N)
    )
    mass_values = tuple(np.linspace(_MASS_LOW_KG, _MASS_HIGH_KG, _GRID_N))
    return TradeAxes(cda_values=cda_values, mass_values=mass_values)


# ----------------------------------------------------------------------
# App 5 mode (a) (Step 68, roadmap.md; docs/architecture-30-apps-4-5-and-
# configs.md SS30.7.2): named-scenario comparison inputs.
# ----------------------------------------------------------------------

# Each `Variant` below is a *literal, absolute-value* override against
# `demo_75mm`'s own baseline (`weight.m=1.5 kg`, `aero.C_x=0.5` at
# `aero.S=0.00442 m^2`), applied via `Variant.apply`/`Config.with_variant`
# -- the same "literal tuned to one demo vehicle's own scale" convention
# `default_axes`'s own mass band already uses above (not a relative delta
# computed off whatever `--config` baseline happens to be loaded).
# Applying these two variants against a very different baseline config
# would still set `weight.m`/`aero.C_x` to these exact absolute numbers,
# which may not be a meaningful perturbation at that vehicle's own scale
# -- a known limitation of a literal default, not a bug (flagged as a
# judgment call in the Step 68 developer report, same reasoning as the
# mass-axis literal above).
SCENARIOS: list[Variant] = [
    Variant(
        name="heavy_sleek",
        overrides={"weight.m": 1.8, "aero.C_x": 0.425},
        notes=(
            "+0.3 kg over demo_75mm's 1.5 kg baseline (a heavier battery "
            "pack and avionics bay -- a rough budget guess, not weighed) "
            "together with C_x x0.85 (0.5 -> 0.425: a sleeker nose cone "
            "profile, read off a vendor's CFD run on a similar-OD "
            "airframe, not measured on this one)."
        ),
    ),
    Variant(
        name="light_draggy",
        overrides={"aero.C_x": 0.65},
        notes=(
            "Baseline mass unchanged (1.5 kg); C_x x1.3 (0.5 -> 0.65), "
            "representing a flat payload-bay door left un-faired -- a "
            "conservative estimate from the aero team's own notes, not a "
            "measurement."
        ),
    ),
]

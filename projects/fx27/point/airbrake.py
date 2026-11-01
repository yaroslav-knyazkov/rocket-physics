"""projects/fx27/point/airbrake.py -- fx27's `air_brake_size_estimation`
(dev/docs/architecture-38-fx27-port.md SS38.5.5): a thin wrapper around
`apps.optimization.airbrake_sizing.solve_cda.solve_airbrake` plus the
three bits of margin/panel arithmetic `apps/` does not do.

`(a)` direct call into `solve_airbrake` (SS38.2.4: it has no `weight.m_d`
guard, unlike `compare_motors`/`build_surface`, so it works with the mass
model on). `trigger="after_burnout"` is the semantic match for fx27's
`power_off_drag` convention (the brake acts from burnout onward).
"""

from __future__ import annotations

import dataclasses

from apps.optimization.airbrake_sizing.solve_cda import (
    AirbrakeSolution,
    AirbrakeSpec,
    print_solution,
    solve_airbrake,
)
from apps.sim.schema import Config


@dataclasses.dataclass(frozen=True)
class BrakeSizing:
    """`solve_airbrake`'s solution plus fx27's own design-margin arithmetic
    (SS38.5.5): `area_min` is `solve_airbrake`'s own `s_max_m2` (identical
    formula, renamed for fx27's report); `area_design`/`area_per_panel` are
    pure arithmetic `apps/` does not compute."""

    solution: AirbrakeSolution
    area_min_m2: float  # = solution.s_max_m2 -- the minimum brake area that reaches the target
    area_design_m2: float  # = area_min_m2 * margin
    area_per_panel_m2: float  # = area_design_m2 / brake_count


def size_airbrake(
    cfg: Config,
    target_apogee_m: float = 2500.0,
    cda_bounds: "tuple[float, float]" = (0.0, 0.05),
    cd_brake: float = 1.0,
    margin: float = 2.0,
    brake_count: int = 3,
) -> BrakeSizing:
    """fx27's `estimate_air_brake`: `target_apogee=2500`,
    `c_da_bracket=(0, 0.05)`, `brake_c_d=1.0`, design margin x2, 3
    panels (SS38.2.4/SS38.5.5's own defaults)."""
    spec = AirbrakeSpec(
        target_apogee_m=target_apogee_m,
        trigger="after_burnout",  # == fx27's power_off_drag semantics (SS38.2.4)
        solve_for="cda",
        cd_brake=cd_brake,
        cda_bounds=cda_bounds,
    )
    sol = solve_airbrake(cfg, spec)
    area_min = sol.s_max_m2
    area_design = area_min * margin
    area_per_panel = area_design / brake_count
    return BrakeSizing(
        solution=sol,
        area_min_m2=area_min,
        area_design_m2=area_design,
        area_per_panel_m2=area_per_panel,
    )


def print_brake_report(sizing: BrakeSizing, config_name: "str | None" = None) -> None:
    """`solve_cda.print_solution`'s own block, plus the two extra fx27
    lines (design area, per-panel area) this module adds (SS38.5.5)."""
    print_solution(sizing.solution, config_name=config_name)
    margin = sizing.area_design_m2 / sizing.area_min_m2 if sizing.area_min_m2 else float("nan")
    print(f"  area, design (x{margin:.1f} margin)  {sizing.area_design_m2:.6f} m^2")
    print(f"  area, per panel            {sizing.area_per_panel_m2:.6f} m^2")

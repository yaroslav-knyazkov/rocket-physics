"""projects/fx27/runs/euroc/sweep.py -- Variant B (dev/docs/architecture-
38-fx27-port.md SS38.5.3): the richer `apps.optimization.motor_selection.
scenario_sweep.sweep_scenario` view, one call per airframe config (12
calls), rows concatenated -- `J_total`, `t_burn`, `T/W`, `q_max`,
`m_burnout` on top of fx27's own column set (Variant A,
`runs/euroc/comparison.py`).

`Constraints(min_tw=0.0, min_margin_cal=-math.inf)`: the default
`min_margin_cal=1.0` would stamp `INFEASIBLE: static_margin` on a
fabricated figure (SS38.2.5/R6) -- fx27 carries no fin/CP geometry, so
`Lengths.l1`/`l2` here are inert placeholders (SS38.2.1), not a real
static margin. Printed loudly, above the table, per SS38.5.3 condition 1.

Motor pieces are renamed `"<config>/<motor id>"` before being handed to
`sweep_scenario` (SS38.5.3 condition 2): `sweep_scenario` raises on a
duplicate motor name *within* one call, and is silent across calls when
rows from several calls are merged (as they are here) -- this repo's own
euroc data has no actual name collision across configs, but the rename
is cheap insurance against SS38.5.3's own documented failure mode.

Run: `python -m projects.fx27.runs.euroc.sweep`.
"""

from __future__ import annotations

import dataclasses
import math

from apps._shared.artifacts import ensure_dir, output_dir
from apps.optimization.motor_selection.scenario_sweep import Constraints, print_table, save_csv, sweep_scenario
from apps.sim.schema import Scenario

from projects.fx27.campaigns.euroc.motors import DEFERRED_MOTORS, MOTORS
from projects.fx27.campaigns.euroc.rockets import ROCKETS
from projects.fx27.campaigns.euroc.scenarios import CANDIDATES
from projects.fx27.campaigns.euroc.site import SITE
from projects.fx27.campaigns.euroc.weather import WEATHER

_CONSTRAINTS = Constraints(min_tw=0.0, min_margin_cal=-math.inf)


def main(argv=None) -> None:
    print(
        "Static margin is not available for this port (fx27 carries no fin/CP geometry; "
        "SS38.2.5) -- running with Constraints(min_tw=0.0, min_margin_cal=-inf) so no row "
        "is marked INFEASIBLE on a fabricated static-margin figure (R6)."
    )

    all_rows = []
    all_results = {}
    for config_name, motor_ids in CANDIDATES.items():
        runnable_ids = [mid for mid in motor_ids if mid not in DEFERRED_MOTORS]
        if not runnable_ids:
            continue
        rocket = ROCKETS[config_name]
        # The scenario's own `motor` field is a placeholder: sweep_scenario
        # replaces it per entry in `motors` below (evaluate_motor).
        scenario = Scenario(
            name=config_name, rocket=rocket, motor=MOTORS[runnable_ids[0]], site=SITE, weather=WEATHER,
        )
        motors = [dataclasses.replace(MOTORS[mid], name=f"{config_name}/{mid}") for mid in runnable_ids]
        out = sweep_scenario(scenario, motors, _CONSTRAINTS)
        all_rows.extend(out.rows)
        all_results.update(out.results)

    print_table(all_rows)

    out_dir = ensure_dir(output_dir())
    csv_path = out_dir / "fx27_euroc_sweep.csv"
    save_csv(all_rows, csv_path)
    print(f"\nSaved {csv_path}")


if __name__ == "__main__":
    main()

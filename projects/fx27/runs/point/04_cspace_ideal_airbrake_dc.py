"""projects/fx27/runs/point/04_cspace_ideal_airbrake_dc.py -- roadmap
General id 1.4 (see projects/fx27/_docs/roadmap.md). fx27 `runs/cspace/
air_brake_estimation.py` equivalent (dev/docs/architecture-38-fx27-
port.md SS38.5.5, #15): brake sizing for the 4 ideal dc variants only --
fx27 deliberately excludes the 3 un-ideal-ised base rockets, kept here
(dc-only half of the old consolidated runs/point/ideal_open_airbrake.py).

No "NOT an oracle" labeling is needed here (unlike
`02_cspace_ideal_mass_dc.py`/`03_cspace_ideal_drag_dc.py`'s dm
counterparts): this report never compared a sizing result against any
fx27-solved reference value in the first place -- it only sizes a brake
against a stated target apogee for whatever config it's handed.

Run: `python -m projects.fx27.runs.point.04_cspace_ideal_airbrake_dc`.
"""

from __future__ import annotations

from projects.fx27.data.cspace.scenarios import SCENARIOS
from projects.fx27.solvers.point.ideal_open_airbrake import print_brake_report, size_airbrake

TARGET_APOGEE_M = 2500.0

IDEAL_VARIANTS_DC = (
    "pro54_transition (ideal mass)",
    "pro54_transition (ideal drag)",
    "pro75 (ideal mass)",
    "pro75 (ideal drag)",
)


def main(argv=None) -> None:
    for name in IDEAL_VARIANTS_DC:
        cfg = SCENARIOS[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()


if __name__ == "__main__":
    main()

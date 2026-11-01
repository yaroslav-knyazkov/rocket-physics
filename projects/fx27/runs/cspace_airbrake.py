"""projects/fx27/runs/cspace_airbrake.py -- fx27 `runs/cspace/
air_brake_estimation.py` equivalent (dev/docs/architecture-38-fx27-
port.md SS38.5.5, #15): brake sizing for the 4 ideal variants only --
fx27 deliberately excludes the 3 un-ideal-ised base rockets, kept here.

Run: `python -m projects.fx27.runs.cspace_airbrake`.
"""

from __future__ import annotations

from projects.fx27.cspace.scenarios import SCENARIOS
from projects.fx27.point.airbrake import print_brake_report, size_airbrake

TARGET_APOGEE_M = 2500.0

IDEAL_VARIANTS = (
    "pro54_transition (ideal mass)",
    "pro54_transition (ideal drag)",
    "pro75 (ideal mass)",
    "pro75 (ideal drag)",
)


def main(argv=None) -> None:
    for name in IDEAL_VARIANTS:
        cfg = SCENARIOS[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()


if __name__ == "__main__":
    main()

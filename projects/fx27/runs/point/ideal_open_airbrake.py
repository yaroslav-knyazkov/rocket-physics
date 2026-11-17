"""projects/fx27/runs/point/ideal_open_airbrake.py -- fx27 `runs/cspace/
air_brake_estimation.py` equivalent (dev/docs/architecture-38-fx27-
port.md SS38.5.5, #15): brake sizing for the 4 ideal variants only --
fx27 deliberately excludes the 3 un-ideal-ised base rockets, kept here.

Architecture-42 SS42.8 adds the 4 dm ideal variants below the dc ones
above. `size_airbrake` is model-agnostic (operates on `cfg: Config`,
reads whatever `aero.model` the config carries) -- no new estimator
needed, just a second loop over the dm scenario dict. No "NOT an oracle"
labeling is needed here (unlike `ideal_mass.py`/`ideal_drag.py`'s dm
rows): this report never compared a sizing result against any
fx27-solved reference value in the first place (dc rows don't either) --
it only sizes a brake against a stated target apogee for whatever config
it's handed.

Run: `python -m projects.fx27.runs.point.ideal_open_airbrake`.
"""

from __future__ import annotations

from projects.fx27.data.cspace.scenarios import SCENARIOS
from projects.fx27.data.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.solvers.point.ideal_open_airbrake import print_brake_report, size_airbrake

TARGET_APOGEE_M = 2500.0

IDEAL_VARIANTS_DC = (
    "pro54_transition (ideal mass)",
    "pro54_transition (ideal drag)",
    "pro75 (ideal mass)",
    "pro75 (ideal drag)",
)

IDEAL_VARIANTS_DM = (
    "pro54_transition_dm (ideal mass)",
    "pro54_transition_dm (ideal drag)",
    "pro75_dm (ideal mass)",
    "pro75_dm (ideal drag)",
)


def main(argv=None) -> None:
    for name in IDEAL_VARIANTS_DC:
        cfg = SCENARIOS[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()

    for name in IDEAL_VARIANTS_DM:
        cfg = SCENARIOS_DM[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()


if __name__ == "__main__":
    main()

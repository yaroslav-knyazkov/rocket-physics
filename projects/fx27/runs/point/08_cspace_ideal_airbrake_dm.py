"""projects/fx27/runs/point/08_cspace_ideal_airbrake_dm.py -- roadmap
General id 1.8 (see projects/fx27/_docs/roadmap.md). dm-only half of the
old consolidated runs/point/ideal_open_airbrake.py (architecture-42
SS42.8). `size_airbrake` is model-agnostic (operates on `cfg: Config`,
reads whatever `aero.model` the config carries) -- no new estimator
needed, just the dm scenario dict in place of dc's. No "NOT an oracle"
labeling is needed here (unlike `06_cspace_ideal_mass_dm.py`/
`07_cspace_ideal_drag_dm.py`'s dm rows): this report never compared a
sizing result against any fx27-solved reference value in the first place
(dc rows in `04_cspace_ideal_airbrake_dc.py` don't either) -- it only
sizes a brake against a stated target apogee for whatever config it's
handed.

Run: `python -m projects.fx27.runs.point.08_cspace_ideal_airbrake_dm`.
"""

from __future__ import annotations

from projects.fx27.data.cspace.scenarios_dm import SCENARIOS_DM
from projects.fx27.solvers.point.ideal_open_airbrake import print_brake_report, size_airbrake

TARGET_APOGEE_M = 2500.0

IDEAL_VARIANTS_DM = (
    "pro54_transition_dm (ideal mass)",
    "pro54_transition_dm (ideal drag)",
    "pro75_dm (ideal mass)",
    "pro75_dm (ideal drag)",
)


def main(argv=None) -> None:
    for name in IDEAL_VARIANTS_DM:
        cfg = SCENARIOS_DM[name].config
        sizing = size_airbrake(cfg, target_apogee_m=TARGET_APOGEE_M)
        print_brake_report(sizing, config_name=name)
        print()


if __name__ == "__main__":
    main()

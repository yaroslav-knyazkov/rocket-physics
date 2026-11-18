"""projects/fx27/runs/controller_pd/01_p_analytical_burnout_linear_drag.py --
Rung-1 closed-loop demo for the 4 ideal cspace variants (dc only -- see
dev/docs/task-152-fx27-point-controller-rung1.md S3 for why not the base
rockets or the dm set yet).

Run: `python -m projects.fx27.runs.controller_pd.01_p_analytical_burnout_linear_drag`.
"""

from __future__ import annotations

from projects.fx27.data.cspace import airbrake_data
from projects.fx27.data.cspace.scenarios import SCENARIOS
from projects.fx27.solvers.controller_pd.controller import print_rung1_report, run_rung1_demo

TARGET_APOGEE_M = 2500.0          # matches runs/point/ideal_open_airbrake.py's own target
# Picked empirically (dev/docs/task-152-fx27-point-controller-rung1.md S1's
# own note -- fx27's ~4-8 kg/~2500-3000 m scale has no existing tuned gain,
# unlike tests/test_harness.py's own 0.5 kg/500 m oracle, _KP=0.001 there).
# Swept kp in {0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01} against all 4
# IDEAL_VARIANTS_DC below (achieved apogee / apogee error / actuator
# saturation fraction / actuator travel, over each variant's own active
# [burnout, apogee] window):
#   kp=0.0001  err +437..+444 m   sat ~0.25-0.27%   travel ~0.06
#   kp=0.001   err +218..+233 m   sat ~0.27-0.80%   travel ~4.3-7.6
#   kp=0.005   err  +46..+58  m   sat ~22.7-23.5%   travel ~90-104
#   kp=0.01    err  +19..+29  m   sat ~33.6-34.5%   travel ~125-140
# kp=0.01 is the chosen value: smallest apogee error of the sweep for every
# one of the 4 variants (~1% of the 2500 m target), and the actuator is
# still only commanded to its f_max rail ~1/3 of the active window (not
# saturating the WHOLE flight) -- room is left before the law degenerates
# into an on/off bang-bang controller. Re-derive via this module's own
# sweep if `kp` is revisited.
KP = 0.01

# (scenario dict key, rocket-family hardware data) -- one hardware file per
# physical airframe family, reused by both its "ideal mass" and "ideal
# drag" variant (same airframe body, same brake, S4).
IDEAL_VARIANTS_DC = (
    ("pro54_transition (ideal mass)", airbrake_data.PRO54_TRANSITION_AIRBRAKE),
    ("pro54_transition (ideal drag)", airbrake_data.PRO54_TRANSITION_AIRBRAKE),
    ("pro75 (ideal mass)", airbrake_data.PRO75_AIRBRAKE),
    ("pro75 (ideal drag)", airbrake_data.PRO75_AIRBRAKE),
)


def main(argv=None) -> None:
    for name, hardware in IDEAL_VARIANTS_DC:
        scenario = SCENARIOS[name]
        demo = run_rung1_demo(scenario, hardware, target_apogee_m=TARGET_APOGEE_M, kp=KP)
        print_rung1_report(demo, config_name=name)
        print()


if __name__ == "__main__":
    main()

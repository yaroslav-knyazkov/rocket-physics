"""Root wrapper 2 of 5 (roadmap.md Step 69, D-29): the motor selection
sweep app, `apps/motor_selection/compare_motors.py`'s `main()` -- a front
door so `python run_motor_sweep.py` works the same way `python run.py`
does, without replacing the app's own
`python -m apps.motor_selection.compare_motors` invocation
(architecture-30-apps-4-5-and-configs.md SS30.3).

Step 100 (Phase 2.17): `--scenario NAME --motors a,b,c [--target M]` routes to
the Scenario/Motor sweep (`apps/motor_selection/scenario_sweep.py`); without
`--scenario` the legacy App 3 runs unchanged."""

import sys

from apps.motor_selection.compare_motors import main as legacy_main
from apps.motor_selection.scenario_sweep import main as scenario_main

if __name__ == "__main__":
    if any(a == "--scenario" or a.startswith("--scenario=") for a in sys.argv[1:]):
        scenario_main()
    else:
        legacy_main()

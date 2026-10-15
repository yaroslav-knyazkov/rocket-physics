"""configs/motors/synthetic_large.py -- the App-3 "large" synthetic motor,
seeded as a `Motor` piece (Phase 2.16, Step 79,
docs/architecture-32-motor-separation.md SS32.2.1, D-73).

`Thrust(motor_curve="synthetic_large.csv")`, `mass_model="none"` (the
default) -- same shape as `placeholder`, pointed at the curve
`apps/motor_selection/motors.py`, `apps/motor_selection/
compare_motors.py` and `apps/airbrake_sizing/targets.py` already use
(`data/motors/synthetic_large.csv`, §32.9's keep list). Registering it
here does not change any of those callers -- they still own their own
`MotorEntry`/override machinery (D-73's own note: App 3's sweep list is
not migrated into `configs/motors/`) -- this module exists so a config
piece can reference the same curve by name, the same way `placeholder`
does for `"placeholder.csv"`.
"""

from __future__ import annotations

from configs.schema import Motor
from sim.params import Thrust

MOTOR = Motor(
    name="synthetic_large",
    thrust=Thrust(motor_curve="synthetic_large.csv"),
    # mass_model left at its default "none" -- constant-mass flight.
)

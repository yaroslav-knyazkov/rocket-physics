"""configs/motors/placeholder.py -- the no-mass-model seed motor (Phase
2.16, Step 79, docs/architecture-32-motor-separation.md SS32.2.1, D-73).

`Thrust(motor_curve="placeholder.csv")`, `mass_model="none"` (the
default) -- this is the motor every pre-Step-80 seed rocket uses, and
what `configs/rockets/{demo_75mm,toy_05kg}.py`'s own `thrust=Thrust(...)`
field moves to once Step 80 wires motors into `Scenario` instead of
`Rocket`.

NOTE on `thrust.motor_curve` (the same judgment call `demo_75mm`'s own
docstring has carried since Step 63/73, preserved here verbatim in
spirit): `docs/architecture-30-apps-4-5-and-configs.md` SS30.4's seed-
config table says a demo motor should carry
`thrust.motor_curve="synthetic_large.csv"` "so it is runnable on its
own", but `tests/test_configs.py` pins
`get("demo_75mm").params == _demo_baseline()` as an *exact* dataclass
equality against `apps/motor_selection/compare_motors.py`'s
`_demo_baseline()`, which itself uses `"placeholder.csv"` (its own
docstring: "replaced per entry; never read as-is", since every App-3
caller overrides `thrust.motor_curve` per `MotorEntry` before running).
The exact-equality pin is the literal, testable instruction, so this
module keeps `"placeholder.csv"` -- it still flies on its own (162.75
N*s on 1.5 kg clears the pad easily; see `tests/test_configs.py`'s
"every config runs" check), which is all "runnable on its own" requires
in practice. **Do NOT "fix" `motor_curve` to `"synthetic_large.csv"`** --
the exact-equality pin against `_demo_baseline()` depends on it staying
exactly `"placeholder.csv"`.
"""

from __future__ import annotations

from configs.schema import Motor
from sim.params import Thrust

MOTOR = Motor(
    name="placeholder",
    thrust=Thrust(motor_curve="placeholder.csv"),  # replaced per entry; never read as-is
    # mass_model left at its default "none" -- constant-mass flight,
    # the only model every current seed rocket uses.
)

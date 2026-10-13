"""configs/demo_75mm.py -- the 1.5 kg / 75 mm vehicle (Step 63,
roadmap.md, `docs/architecture-30-apps-4-5-and-configs.md` SS30.4).

Copied number-for-number, including its justifying docstring, from
`apps/motor_selection/compare_motors.py`'s `_demo_baseline()` (D-26,
user-approved at Step 62) -- this is the config `tests/test_configs.py`
pins byte-equal against that function (`s0` included, reconstructed from
`compare_motors.main()`'s own literal), which is what makes a later
migration (roadmap Step 69) a provable no-op.

NOTE on `thrust.motor_curve` (flagged as a judgment call, see the Step 63
developer report): SS30.4's own seed-config table says this config should
carry `thrust.motor_curve="synthetic_large.csv"` "so it is runnable on
its own", but the same document's test strategy (SS30.8) and the Step-63
roadmap ticket both pin `get("demo_75mm").params == _demo_baseline()` as
an *exact* dataclass equality, and `_demo_baseline()` itself uses
`"placeholder.csv"` (its own docstring: "replaced per entry; never read
as-is", since every App-3 caller overrides `thrust.motor_curve` per
`MotorEntry` before running). The exact-equality pin is the literal,
testable instruction and the step's stated primary gate, so this module
keeps `"placeholder.csv"` -- it still flies on its own (162.75 N*s on 1.5
kg clears the pad easily; see `tests/test_configs.py`'s
"every config runs" check), which is all "runnable on its own" requires
in practice.
"""

from __future__ import annotations

import math

from configs.schema import Config
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.state import State

CONFIG = Config(
    name="demo_75mm",
    params=Params(
        weight=Weight(m=1.5, I=0.08),                 # launch mass, mass model OFF (m_d=None)
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),  # replaced per entry; never read as-is
        aero=Aero(
            S=0.00442, d_ref=0.075, l_ref=0.75,        # 75 mm body: S = pi*d^2/4 = 0.004418 m^2
            C_x=0.5, C_z=0.0, C_m=0.0,
        ),
    ),
    s0=State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0),
    notes=(
        "The architect's own synthetic 1.5 kg / 75 mm vehicle. Deliberately "
        "NOT run.py's 0.5 kg toy scenario: 338 N*s (the largest new fixture) "
        "on 0.5 kg gives an ideal delta-v of ~676 m/s (~Mach 2), where a "
        "constant C_x = 0.5 is not a defensible aerodynamic model and the "
        "ISA extrapolation ceiling starts to matter. 1.5 kg keeps every "
        "fixture subsonic (largest motor: ideal delta-v ~225 m/s before "
        "gravity/drag losses, <~ Mach 0.7) while still leaving the smallest "
        "motor just barely flyable -- itself informative. C_z = C_m = 0.0 "
        "makes this a vertical, attitude-frozen 1-D shot, the same "
        "simplification run.py and App 2 already carry, appropriate for a "
        "motor comparison (one variable at a time) and, per SS29.4.1/F5, "
        "the reason the ascent window is mandatory."
    ),
)

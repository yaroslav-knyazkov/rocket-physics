"""configs/rockets/demo_75mm.py -- the 1.5 kg / 75 mm vehicle (Step 63,
roadmap.md, `dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.4; moved
here and reduced to a `Rocket` at Step 73,
`dev/docs/architecture-31-config-separation.md` SS31.7).

Copied number-for-number, including its justifying docstring, from
`apps/motor_selection/compare_motors.py`'s `_demo_baseline()` (D-26,
user-approved at Step 62) -- this is the vehicle `tests/test_configs.py`
pins byte-equal against that function (`s0` included, reconstructed from
`compare_motors.main()`'s own literal), which is what makes a later
migration (roadmap Step 69, and this piece-split, Step 73) a provable
no-op.

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
in practice. Step 73 re-confirms this call: do NOT change it to
`"synthetic_large.csv"` -- the exact-equality pin against
`_demo_baseline()` still depends on it.

The `s0`/`notes` this module's flat `Config` used to carry now live in
`configs/scenarios/demo_75mm.py` -- `s0` because it is derived from the
rail (SS31.4, D-51a) rather than a vehicle property, `notes` because it
is what `--list-configs` prints for the scenario, not the vehicle.

Step 80 (`dev/docs/architecture-32-motor-separation.md` SS32.2.3): this
rocket's motor (including the "replaced per entry; never read as-is"
judgment call on `motor_curve`) now lives in
`configs/scenarios/demo_75mm.py`, imported from
`configs.motors.placeholder`. `sections` is left at its default
(`Sections()`) -- this rocket has no measured section geometry.
"""

from __future__ import annotations

from configs.schema import Airframe, Rocket
from sim.params import Aero, Lengths

ROCKET = Rocket(
    name="demo_75mm",
    airframe=Airframe(m=1.5, I=0.08),              # launch mass, mass model OFF (m_d=None)
    lengths=Lengths(l1=0.3, l2=0.4),
    # sections left at its default -- no measured section geometry for
    # this rocket (SS32.2.3).
    aero=Aero(
        S=0.00442, d_ref=0.075, l_ref=0.75,        # 75 mm body: S = pi*d^2/4 = 0.004418 m^2
        C_x=0.5, C_z=0.0, C_m=0.0,
    ),
)

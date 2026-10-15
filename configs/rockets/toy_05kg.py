"""configs/rockets/toy_05kg.py -- the 0.5 kg / S=0.005 / C_x=0.5 placeholder
vehicle (Step 63, roadmap.md,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.4; moved here and
reduced to a `Rocket` at Step 73, `dev/docs/architecture-31-config-separation.md`
SS31.7).

Copied number-for-number, including its justifying comments, from
`run.py`'s own `Params`/`State` literal (in place since Step 1/Step 4) --
also App 2's (`apps/cfd_conditions/select_conditions.py`) identical
`main()` literal. This is the vehicle `tests/test_configs.py` pins
byte-equal against `run.py`'s literal, which is what makes a later
migration (roadmap Step 69, and this piece-split, Step 73) a provable
no-op rather than a rewrite.

The `s0`/`notes` this module's flat `Config` used to carry now live in
`configs/scenarios/toy_05kg.py` -- `s0` because it is derived from the
rail (SS31.4, D-51a) rather than a vehicle property, `notes` because it
is what `--list-configs` prints for the scenario, not the vehicle.

Step 80 (`dev/docs/architecture-32-motor-separation.md` SS32.2.3): this
rocket's motor now lives in `configs/scenarios/toy_05kg.py`, imported
from `configs.motors.placeholder`. `sections` is left at its default
(`Sections()`) -- this rocket has no measured section geometry.
"""

from __future__ import annotations

from configs.schema import Airframe, Rocket
from sim.params import Aero, Lengths

ROCKET = Rocket(
    name="toy_05kg",
    airframe=Airframe(
        m=0.5,      # 0.5 kg dry+propellant mass
        I=0.05,     # kg*m^2, rough estimate for a small rocket
    ),
    lengths=Lengths(
        l1=0.3,     # m, CoP -> CoG distance
        l2=0.4,     # m, CoP -> thrust point distance
    ),
    # sections left at its default -- no measured section geometry for
    # this rocket (SS32.2.3).
    aero=Aero(
        # Step 55 (architecture-28-rewrite.md SS28.5.4): "constant"'s
        # C_x/C_z/C_m are true, q-scaled coefficients now, not raw
        # Newton/Newton-metre placeholders -- S/d_ref are therefore
        # required for any nonzero force/moment to result at all
        # (pre-Step-55, C_x=0.5 alone meant "0.5 N of drag for the
        # whole flight", which was never physical). Values match the
        # atmosphere-sweep scenario further down in run.py.
        S=0.005,    # m^2, reference area
        d_ref=0.08,  # m, reference length (moment arm + Reynolds number)
        C_x=0.5,    # axial-force coefficient [-]
        C_z=0.0,    # normal-force coefficient [-]
        C_m=0.0,    # pitching-moment coefficient [-]
    ),
)

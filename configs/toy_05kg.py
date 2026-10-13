"""configs/toy_05kg.py -- the 0.5 kg / S=0.005 / C_x=0.5 placeholder
scenario (Step 63, roadmap.md,
`docs/architecture-30-apps-4-5-and-configs.md` SS30.4).

Copied number-for-number, including its justifying comments, from
`run.py`'s own `Params`/`State` literal (in place since Step 1/Step 4) --
also App 2's (`apps/cfd_conditions/select_conditions.py`) identical
`main()` literal. This is the config `tests/test_configs.py` pins
byte-equal against `run.py`'s literal, which is what makes a later
migration (roadmap Step 69) a provable no-op rather than a rewrite.
"""

from __future__ import annotations

import math

from configs.schema import Config
from sim.params import Aero, Lengths, Params, Thrust, Weight
from sim.state import State

CONFIG = Config(
    name="toy_05kg",
    params=Params(
        weight=Weight(
            m=0.5,      # 0.5 kg dry+propellant mass
            I=0.05,     # kg*m^2, rough estimate for a small rocket
        ),
        lengths=Lengths(
            l1=0.3,     # m, CoP -> CoG distance
            l2=0.4,     # m, CoP -> thrust point distance
        ),
        thrust=Thrust(motor_curve="placeholder.csv"),  # Step 14: real (time, thrust) curve
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
    ),
    # At rest on the pad, pointing straight up (theta = pi/2, nose-up
    # from horizontal), z = 0 at the launch point.
    s0=State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0),
    notes=(
        "run.py's / App 2's historical placeholder scenario: a generic "
        "small model-rocket scale, unchanged since Step 1/Step 4."
    ),
)

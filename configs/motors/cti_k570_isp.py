"""configs/motors/cti_k570_isp.py -- the same CTI K570 curve,
mass_model="isp" with a hand-entered `I_sp` (Phase 2.16, Step 79,
docs/architecture-32-motor-separation.md SS32.2.1, D-73, D-59).

This module exists specifically so D-59's "isp" vs "endpoints"
equivalence -- same mass model, two different ways of specifying it --
is directly comparable against `cti_k570.py`: same curve
(`Cesaroni_2060K570-17A.eng`), but `I_sp=212.41` is hand-entered here
rather than derived from the curve's own total impulse at assembly time.
212.41 matches `cti_k570.py`'s own notes (`I_sp_eff ~= 212.41 s`) to two
decimal places, which is what makes the two motors' compositions agree
to 1e-3 relative against a common `Airframe`/`Sections` -- the cheapest
possible check on D-59's claim (SS32.10).
"""

from __future__ import annotations

from configs.schema import Motor
from sim.params import Thrust

MOTOR = Motor(
    name="cti_k570_isp",
    thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng"),
    mass_model="isp",
    I_sp=212.41,
    notes=(
        "Same real Cesaroni K570 curve as cti_k570.py, 'isp' mass model "
        "with I_sp hand-entered (212.41 s, matching cti_k570.py's own "
        "measured I_sp_eff to 2 decimal places) instead of derived from "
        "the curve's own total impulse -- the direct D-59 comparison "
        "point for the 'isp' vs 'endpoints' models."
    ),
)

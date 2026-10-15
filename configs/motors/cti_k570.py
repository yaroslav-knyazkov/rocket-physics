"""configs/motors/cti_k570.py -- the real CTI K570, mass_model="endpoints"
(Phase 2.16, Step 79, dev/docs/architecture-32-motor-separation.md SS32.2.1,
D-73).

Every mass/geometry field below is left `None` so
`data/motors/Cesaroni_2060K570-17A.eng`'s own RASP header supplies them
(`sim/motor_file.py`'s reader) -- a genuinely three-line `Motor` literal,
which is the entire point of a reader that keeps the header instead of
discarding it (SS32.2.1).

This is the worked demo Step 81 builds a full scenario around, and one
half of D-59's "isp" vs "endpoints" equivalence -- see `cti_k570_isp.py`,
the same curve under the other mass model.
"""

from __future__ import annotations

from configs.schema import Motor
from sim.params import Thrust

MOTOR = Motor(
    name="cti_k570",
    thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng"),
    mass_model="endpoints",
    # every mass/geometry field left None -- all come from the .eng header
    notes=(
        "Cesaroni K570 (17A delay), real vendor-published RASP file "
        "(data/motors/Cesaroni_2060K570-17A.eng). Measured/derived from "
        "the file itself (SS32.3.1 F5): I_sp_eff ~= 212.41 s, J ~= 2062.22 "
        "N*s (trapezoid over the loaded curve, including the (0,0) prepend "
        "sim/motor_file.py applies to RASP records), m_prop=0.990 kg, "
        "m_total=1.685 kg from the header's own fields 5/6."
    ),
)

"""configs/rockets/demo_75mm_k570.py -- a 54 mm airframe sized for the
real Cesaroni K570 (Phase 2.16, Step 81,
dev/docs/architecture-32-motor-separation.md SS32.2/SS32.3.3/SS32.5).

Demonstrates a real vendor motor, with its own measured mass history,
composed with an airframe that knows where the motor sits -- the first
rocket piece in this tree to carry a non-default `Sections` and an
`Airframe.l`, because it is the first paired with a `mass_model !=
"none"` motor (`configs.motors.cti_k570`, Step 79). A *new* piece, not an
edit to `demo_75mm` -- that module's numbers are pinned by
`tests/test_configs.py`'s exact-equality tests.

Every number below is synthetic but plausible (the same voice
`configs/sites/highland_1500m.py` already uses), sized from the K570's
own header (`data/motors/Cesaroni_2060K570-17A.eng`:
`K570  54.0 488.00 7-17 0.99000 1.68500 CTI`, SS32.3.1 F5) rather than
measured off a real kit:

- `aero.S`/`d_ref` use the K570's own 54 mm casing diameter --
  `S = pi*d^2/4 = pi*0.054^2/4 ~= 0.002290 m^2` -- rather than
  `demo_75mm`'s 75 mm body, because this airframe is sized to the motor
  it flies, not reused from the 75 mm demo.
- `sections.L_total=1.10` gives the K570 (0.488 m long) a forward margin
  of ~0.61 m for nose, body tube, recovery bay and avionics ahead of the
  motor mount -- a plausible proportion for a 54 mm minimum-diameter
  airframe, not a specific kit's drawing.
- `sections.l_nose=0.25`, `l_fin_root_fwd=0.92`, `l_fin_root_aft=1.02`
  place the fin can at the aft end, overlapping the motor-mount tube --
  the ordinary arrangement for this class of airframe.
- `sections.l_motor_aft=L_total` is an aft-flush install (SS32.2.2): the
  motor's forward face then resolves to `L_total - motor.length` inside
  `_weight_from_pieces`, with no station typed in by hand for it.
- `airframe.m=1.5`, `airframe.I=0.15` keep `demo_75mm`'s mass (a 54 mm
  minimum-diameter build is not necessarily lighter than a 75 mm one with
  more empty body tube) but scale the MOI up for this airframe's longer
  overall length (1.10 m vs demo_75mm's implicit ~0.75 m), roughly
  tracking `I ~ m*L^2/12` without reproducing it exactly (that estimate
  gives ~0.15 for a uniform rod of this mass/length, which is why 0.15 was
  picked rather than `demo_75mm`'s 0.08).
- `airframe.l=0.55` puts the dry (motor-excluded) CoG a little forward of
  the airframe's own midpoint -- plausible for a vehicle whose recovery
  bay and avionics sit ahead of an aft-mounted motor.

`lengths=Lengths(l1=0.3, l2=0.4)` reuses `demo_75mm`'s own CoP/thrust-arm
pair unchanged: this module's purpose is the motor/mass-model demo
(SS32.3.3/SS32.3.4), not a new aero moment-arm derivation, and the
`"constant"` aero model this rocket uses (via `demo_75mm`'s own
`Aero(...)` triple, below) does not read `Sections` for its own arms
(SS32.5's D-68: `Lengths.l1`/`l2` stay hand-entered and authoritative,
`Sections` is additive/informational except for `l_motor_fwd`/
`l_motor_aft`).
"""

from __future__ import annotations

from configs.schema import Airframe, Rocket, Sections
from sim.params import Aero, Lengths

ROCKET = Rocket(
    name="demo_75mm_k570",
    # launch mass EXCLUDING the motor -- mass model ON once paired with a
    # mass_model != "none" motor (SS32.2.2), so `l` (the airframe's own
    # CoG station aft of the nose tip) is now required.
    airframe=Airframe(m=1.5, I=0.15, l=0.55),
    lengths=Lengths(l1=0.3, l2=0.4),  # reused from demo_75mm, see module docstring
    aero=Aero(
        S=0.00229, d_ref=0.054, l_ref=1.10,  # 54 mm body: S = pi*d^2/4 = 0.002290 m^2
        C_x=0.5, C_z=0.0, C_m=0.0,
    ),
    sections=Sections(
        L_total=1.10,            # overall length, nose tip to tail -- 0.49 m K570 + margin
        l_nose=0.25,             # nose cone length / nose-body joint station
        l_fin_root_fwd=0.92,     # fin root leading edge, near the aft end
        l_fin_root_aft=1.02,     # fin root trailing edge
        l_motor_aft=1.10,        # aft-flush install (SS32.2.2); forward face
        #                          resolves to L_total - motor.length at assembly
    ),
)

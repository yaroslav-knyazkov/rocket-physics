"""projects/fx27/cspace/rockets.py -- the 3 base cspace airframes
(dev/docs/architecture-38-fx27-port.md SS38.4.1/SS38.5.2), paired with
motors.py in scenarios.py.

All three share one `radius=0.040` m body (fx27 data/cspace/rockets.py:
every `PointMassRocket` in this campaign uses it) -> `Aero.S = pi*r^2`,
`Aero.d_ref = 2*r`; and one `power_off_drag == power_on_drag == 0.5` ->
this project's single `Aero.C_x = 0.5` (SS38.4.1: no burn/coast split
exists here, and fx27 sets both to the same constant everywhere, so
nothing is lost).

`C_z = C_m = c_mq = 0.0` is the Option C (D-A) frozen-attitude config
itself (SS38.2.1/SS38.3.2) -- not a simplification of fx27, the same
approximation class fx27's own `PointMassRocket` runs under.
"""

from __future__ import annotations

import math

from apps.sim.schema import Airframe, Rocket, Sections
from apps.sim.engine.params import Aero, Lengths

_RADIUS_M = 0.040  # REQ, m -- fx27 PointMassRocket(radius=0.040), all 3 cspace airframes

_AERO = Aero(
    S=math.pi * _RADIUS_M**2,  # REQ, m^2 -- reference area = pi*r^2 (rocketpy's own meaning for `radius`)
    d_ref=2.0 * _RADIUS_M,  # REQ, m -- reference length (body diameter)
    C_x=0.5,  # REQ, - -- fx27 power_off_drag == power_on_drag == 0.5 (one constant here)
    C_z=0.0,  # REQ, - -- Option C (D-A): frozen attitude, MUST be exactly 0.0 (SS38.2.1)
    C_m=0.0,  # REQ, - -- ditto
    c_mq=0.0,  # REQ, - -- ditto
)

_LENGTHS = Lengths(
    l1=1.0,  # OPT, m -- DYNAMICALLY INERT placeholder (SS38.2.1): with C_z=C_m=c_mq=0 the total
    #                    pitching moment is identically zero, so l1 never multiplies a nonzero
    #                    A_z. fx27 carries no fin/CP geometry at all (SS38.2.5), so there is no
    #                    honest value to put here either way. BECOMES A SILENT BUG if this
    #                    scenario is ever switched to an alpha-dependent aero model (R3, SS38.10).
    l2=1.0,  # OPT, m -- ditto (CoP-to-thrust-point arm; also inert, same reason)
)

_SECTIONS = Sections(
    l_motor_fwd=0.0,  # REQ, m -- zero-geometry recipe (SS38.2.8). INERT, same reason as above:
    #                            becomes a silent bug under an alpha-dependent aero model (R3).
)


def _airframe(dry_mass_kg: float) -> Airframe:
    return Airframe(
        m=dry_mass_kg,  # REQ, kg -- airframe mass, motor EXCLUDED (fx27 PointMassRocket mass=<dry>)
        I=0.5,  # REQ, kg*m^2 -- DYNAMICALLY INERT placeholder (SS38.2.1): omega_dot = M_y/I is
        #                        identically 0/I == 0 regardless of I's value; I must still be
        #                        > 0 (0.0/0.0 would be nan). BECOMES A SILENT BUG if this
        #                        scenario is ever switched to an alpha-dependent aero model
        #                        (R3, SS38.10).
        l=0.6,  # OPT, m -- placeholder CoG station; REQ in practice because the paired motor
        #                   has mass_model != "none". DYNAMICALLY INERT, same reason as I above.
    )


PRO54_TRANSITION = Rocket(
    name="pro54_transition",
    airframe=_airframe(5.835),  # REQ, kg -- fx27 data/cspace/rockets.py pro54_transition dry mass
    lengths=_LENGTHS,
    aero=_AERO,
    sections=_SECTIONS,
    notes="fx27 data/cspace/rockets.py pro54_transition; motor pro54_2060K570 (cspace/scenarios.py).",
)

PRO54_EQUAL = Rocket(
    name="pro54_equal",
    airframe=_airframe(6.393),  # REQ, kg -- fx27 data/cspace/rockets.py pro54_equal dry mass
    lengths=_LENGTHS,
    aero=_AERO,
    sections=_SECTIONS,
    notes="fx27 data/cspace/rockets.py pro54_equal; motor pro54_2060K570 (cspace/scenarios.py).",
)

PRO75 = Rocket(
    name="pro75",
    airframe=_airframe(6.225),  # REQ, kg -- fx27 data/cspace/rockets.py pro75 dry mass
    lengths=_LENGTHS,
    aero=_AERO,
    sections=_SECTIONS,
    notes="fx27 data/cspace/rockets.py pro75; motor pro75_3419L645 (cspace/scenarios.py).",
)

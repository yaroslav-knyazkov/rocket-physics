"""projects/fx27/campaigns/euroc/rockets.py -- the 12 euroc airframe configs
(dev/docs/architecture-38-fx27-port.md SS38.4.1), built from one data
table, same `_airframe`/`_AERO`/`_LENGTHS`/`_SECTIONS` shape as
`cspace/rockets.py`.

All 12 share `radius=0.040` m and `drag=0.5` -- fx27 states explicitly
this is a SHARED PLACEHOLDER, no drag variation across the 12 airframes
yet (the orchestrator's own inventory note, carried verbatim here: do not
mistake this for 12 independently measured drag figures).
"""

from __future__ import annotations

import math

from apps.sim.schema import Airframe, Rocket, Sections
from apps.sim.engine.params import Aero, Lengths

_RADIUS_M = 0.040  # REQ, m -- shared placeholder across all 12 euroc airframes (see module docstring)

_AERO = Aero(
    S=math.pi * _RADIUS_M**2,  # REQ, m^2 -- reference area = pi*r^2
    d_ref=2.0 * _RADIUS_M,  # REQ, m -- reference length (body diameter)
    C_x=0.5,  # REQ, - -- shared placeholder drag (see module docstring); NOT independently measured per config
    C_z=0.0,  # REQ, - -- Option C (D-A): frozen attitude, MUST be exactly 0.0 (SS38.2.1)
    C_m=0.0,  # REQ, - -- ditto
    c_mq=0.0,  # REQ, - -- ditto
)

_LENGTHS = Lengths(
    l1=1.0,  # OPT, m -- DYNAMICALLY INERT placeholder (SS38.2.1): C_z=C_m=c_mq=0 makes the total
    #                    pitching moment identically zero. fx27 carries no fin/CP geometry
    #                    (SS38.2.5). BECOMES A SILENT BUG under an alpha-dependent aero model (R3).
    l2=1.0,  # OPT, m -- ditto
)

_SECTIONS = Sections(
    l_motor_fwd=0.0,  # REQ, m -- zero-geometry recipe (SS38.2.8); INERT, same reason as above (R3)
)


def _airframe(dry_mass_kg: float) -> Airframe:
    return Airframe(
        m=dry_mass_kg,  # REQ, kg -- airframe mass, motor EXCLUDED
        I=0.5,  # REQ, kg*m^2 -- DYNAMICALLY INERT placeholder (SS38.2.1); must be > 0. R3.
        l=0.6,  # OPT, m -- placeholder CoG station; REQ because every paired motor has
        #                   mass_model != "none". DYNAMICALLY INERT, same reason as I above (R3).
    )


# config name -> dry mass [kg] (fx27 data/euroc/rockets.py)
_DRY_MASS_KG: "dict[str, float]" = {
    "pro54_2G": 5.636,
    "pro54_3G": 5.709,
    "pro54_6GXL": 5.962,
    "pro75_2G": 6.112,
    "pro75_3G": 6.225,
    "pro75_4G": 6.406,
    "pro75_5G": 6.553,
    "pro75_6GXL": 6.842,
    "pro98_3G": 6.553,
    "pro98_4G": 6.769,
    "pro98_6G": 7.202,
    "pro98_6GXL": 7.523,
}

ROCKETS: "dict[str, Rocket]" = {
    config_name: Rocket(
        name=config_name,
        airframe=_airframe(dry_mass_kg),
        lengths=_LENGTHS,
        aero=_AERO,
        sections=_SECTIONS,
        notes=f"fx27 data/euroc/rockets.py {config_name}: dry_mass={dry_mass_kg} kg.",
    )
    for config_name, dry_mass_kg in _DRY_MASS_KG.items()
}

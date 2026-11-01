"""projects/fx27/cspace/motors.py -- the 2 cspace motors, zero-geometry
recipe (dev/docs/architecture-38-fx27-port.md SS38.2.8/SS38.4.1).

Both CSVs are bare `time, thrust` rows with no header (confirmed to parse
via `apps.sim.engine.motor_file._read_csv`, SS38.2.8) -- every mass field
below must therefore be given explicitly, there is no header to derive it
from.

INERT PLACEHOLDERS (l_case/l_prop/I_case/I_prop0 = 0.0), all four, because
the total pitching moment is identically zero under this port's Option C
(D-A) aero config (`C_z = C_m = c_mq = 0`, SS38.2.1): no motor-internal
mass-distribution value here can influence the trajectory. **This becomes
a silent bug if any cspace scenario is ever switched to an alpha-dependent
aero model** ("linearized" | "table") -- R3, SS38.10.
"""

from __future__ import annotations

from apps.sim.schema import Motor
from apps.sim.engine.params import Thrust

from projects.fx27._paths import cspace_motor

PRO54_2060K570 = Motor(
    name="pro54_2060K570",  # REQ, - -- identifies this piece
    thrust=Thrust(
        motor_curve=cspace_motor("pro54-2060K570.csv"),  # REQ -- bare time,thrust CSV, no header
    ),
    mass_model="endpoints",  # REQ, none | isp | endpoints -- derives I_sp from the curve's own
    #                                total impulse (SS32.3.4); matches fx27's PointMassMotor
    m_total=1.685,  # REQ, kg -- 0.695 (dry) + 0.99 (propellant); fx27 data/cspace/motors.py
    m_prop=0.99,  # REQ, kg -- fx27 propellant_initial_mass
    l_case=0.0,  # REQ, m -- INERT placeholder, see module docstring
    l_prop=0.0,  # REQ, m -- INERT placeholder
    I_case=0.0,  # REQ, kg*m^2 -- INERT placeholder
    I_prop0=0.0,  # REQ, kg*m^2 -- INERT placeholder
    notes=(
        "fx27 data/cspace/motors.py pro54_2060K570: dry_mass=1.685-0.99=0.695 kg, "
        "propellant_initial_mass=0.99 kg -> m_total=1.685, m_prop=0.99."
    ),
)

PRO75_3419L645 = Motor(
    name="pro75_3419L645",  # REQ, - -- identifies this piece
    thrust=Thrust(
        motor_curve=cspace_motor("pro75-3419L645.csv"),  # REQ -- bare time,thrust CSV, no header
    ),
    mass_model="endpoints",  # REQ
    m_total=3.7518,  # REQ, kg -- 1.6798 (dry) + 2.072 (propellant)
    m_prop=2.072,  # REQ, kg
    l_case=0.0,  # REQ, m -- INERT placeholder, see module docstring
    l_prop=0.0,  # REQ, m -- INERT placeholder
    I_case=0.0,  # REQ, kg*m^2 -- INERT placeholder
    I_prop0=0.0,  # REQ, kg*m^2 -- INERT placeholder
    notes=(
        "fx27 data/cspace/motors.py pro75_3419L645: dry_mass=3.7518-2.072=1.6798 kg, "
        "propellant_initial_mass=2.072 kg -> m_total=3.7518, m_prop=2.072."
    ),
)

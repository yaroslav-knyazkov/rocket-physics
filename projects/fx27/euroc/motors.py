"""projects/fx27/euroc/motors.py -- the 27 euroc candidate motors, built
from one data table (dev/docs/architecture-38-fx27-port.md SS38.2.8/
SS38.4.1/SS38.7.1). Provenance for every row: fx27 data/euroc/motors.py
(masses) + `projects/fx27/data/motors/euroc-sweep/*.csv` (curves, the
orchestrator's own inventory of the sibling repo, 2026-11).

Zero-geometry recipe (SS38.2.8), applied identically to every motor below,
same as cspace/motors.py: `l_case=l_prop=I_case=I_prop0=0.0` -- INERT
placeholders under this port's Option C (D-A) config (`C_z=C_m=c_mq=0`,
SS38.2.1). **Becomes a silent bug if any euroc scenario is ever switched
to an alpha-dependent aero model** -- R3, SS38.10.

`m_total`/`m_prop` below are `dry_mass + propellant_initial_mass` /
`propellant_initial_mass` straight from fx27's own motor table -- the same
"pass straight through to m_total/m_prop" recipe the task brief gives
verbatim, no re-derivation.

Three CSVs are 4-byte `null` stubs (`DEFERRED_MOTORS`, SS38.7.1): the
corresponding `Motor` pieces below are still fully specified (so that
supplying real data later is a one-line CSV swap, not a code change), but
`euroc/scenarios.py::generate_scenarios()` excludes every `(config,
motor)` combination that uses one of these three names from its runnable
set.
"""

from __future__ import annotations

from apps.sim.schema import Motor
from apps.sim.engine.params import Thrust

from projects.fx27._paths import euroc_motor

# motor id -> (m_total kg, m_prop kg, csv filename). motor id is the bare
# designation used as both this dict's key and the Motor.name below;
# euroc/scenarios.py composes the Scenario-level name as "<config>/<motor
# id>" (SS38.5.3 condition 2 -- see that module for why).
_TABLE: "dict[str, tuple[float, float, str]]" = {
    "pro54-838J293": (0.84, 0.416, "pro54-838J293.csv"),
    "pro54-1211J140": (1.2798, 0.68, "pro54-1211J140.csv"),
    "pro54-3147L935": (2.542, 1.567, "pro54-3147L935.csv"),
    "pro75-2412K1085": (2.43, 1.199, "pro75-2412K1085-todo.csv"),  # DEFERRED, see below
    "pro75-2430K661": (2.5278, 1.182, "pro75-2430K661.csv"),
    "pro75-3618L995": (3.591, 1.912, "pro75-3618L995.csv"),
    "pro75-3683L851": (3.789, 2.11, "pro75-3683L851.csv"),
    "pro75-3727L1050": (3.4477, 1.774, "pro75-3727L1050.csv"),
    "pro75-4025L1355": (4.962, 3.012, "pro75-4025L1355.csv"),
    "pro75-4864L2375": (4.161, 2.322, "pro75-4864L2375.csv"),
    "pro75-4895L1395": (4.323, 2.3649, "pro75-4895L1395.csv"),
    "pro75-5015L1115": (4.404, 2.394, "pro75-5015L1115.csv"),
    "pro75-5198M1101": (4.938, 2.993, "pro75-5198M1101.csv"),
    "pro75-5506M1230": (4.844, 2.9, "pro75-5506M1230.csv"),
    "pro75-6026M1670": (5.231, 2.9561, "pro75-6026M1670.csv"),
    "pro75-6128M1810": (5.416, 3.196, "pro75-6128M1810.csv"),
    "pro75-9977M2245": (8.182, 5.074, "pro75-9977M2245.csv"),
    "pro98-7441M1060": (6.673, 3.622, "pro98-7441M1060.csv"),
    "pro98-7450M2505": (6.25, 3.339, "pro98-7450M2505.csv"),
    "pro98-7649M1290": (7.411, 4.295, "pro98-7649M1290.csv"),
    "pro98-9876M1890": (8.823, 5.28, "pro98-9876M1890-todo.csv"),  # DEFERRED, see below
    "pro98-9955M1450": (8.578, 4.83, "pro98-9955M1450.csv"),
    "pro98-14200N3180": (12.198, 7.46, "pro98-14200N3180-todo.csv"),  # DEFERRED, see below
    "pro98-15227N2501": (13.308, 8.496, "pro98-15227N2501.csv"),
    "pro98-17790N4100": (14.748, 9.101, "pro98-17790N4100.csv"),
    "pro98-17907N2540": (16.2805, 10.7, "pro98-17907N2540.csv"),
    "pro98-19318N3301": (16.525, 10.658, "pro98-19318N3301.csv"),
}

# SS38.7.1: the 3 motors whose CSV is a 4-byte `null` stub -- data not
# ready yet. Exactly these 3 names; a test
# (`tests/test_fx27_port.py`) pins this set.
DEFERRED_MOTORS = frozenset(
    {"pro75-2412K1085", "pro98-9876M1890", "pro98-14200N3180"}
)

MOTORS: "dict[str, Motor]" = {
    motor_id: Motor(
        name=motor_id,  # REQ, - -- bare motor id; euroc/scenarios.py builds "<config>/<motor id>"
        thrust=Thrust(motor_curve=euroc_motor(csv_name)),  # REQ -- bare time,thrust CSV, no header
        mass_model="endpoints",  # REQ -- derives I_sp from the curve's own total impulse (SS32.3.4)
        m_total=m_total,  # REQ, kg -- dry_mass + propellant_initial_mass (fx27 data/euroc/motors.py)
        m_prop=m_prop,  # REQ, kg -- propellant_initial_mass
        l_case=0.0,  # REQ, m -- INERT placeholder, see module docstring
        l_prop=0.0,  # REQ, m -- INERT placeholder
        I_case=0.0,  # REQ, kg*m^2 -- INERT placeholder
        I_prop0=0.0,  # REQ, kg*m^2 -- INERT placeholder
        notes=(
            f"fx27 data/euroc/motors.py {motor_id}: m_total={m_total} kg, m_prop={m_prop} kg."
            + (" DEFERRED: CSV is a 4-byte 'null' stub, data not ready." if motor_id in DEFERRED_MOTORS else "")
        ),
    )
    for motor_id, (m_total, m_prop, csv_name) in _TABLE.items()
}

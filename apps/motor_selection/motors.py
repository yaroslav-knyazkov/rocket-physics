"""Per-motor dry-rocket configuration (Step 62,
`dev/docs/architecture-29-motor-selection.md` SS29.7/SS29.8, decision D-23).

The user's own framing: "for each motor I can also select dry rocket
parameters (for smaller motors the casing is smaller)." This module is
*that* configuration: one `MotorEntry` per candidate motor, each carrying
its own `overrides` dict of dotted `sim.params.replace` paths -- the
dry-rocket consequences of flying *this* airframe with *that* motor
installed (casing mass, casing length, the body diameter it forces, the
resulting CoG/CoP geometry). `data/motors/*.csv` stays pure thrust-versus-
time; the vehicle consequences of a motor choice live here, not there
(SS29.7's "Why `MotorEntry` is the right home for per-motor vehicle data").

Why a Python literal and not JSON/CSV/YAML (D-23, SS29.8, user-approved):
`None` is a meaningful override value in this schema (`weight.m_d = None`
is the variable-mass model's own off switch, F1); the key set is open and
per-entry sparse (different motors override different things); and every
number in this repo's configuration is commented with *why* right next to
it -- none of that survives a round trip through a tabular/JSON format
without a parser this project would then have to own and validate.

Field names are `sim/params.py`'s actual nested names:
`Weight(m, I, m_d, l_d, l_p, I_d, I_sp)`, `Aero(model, S, d_ref, l_ref,
C_x, C_z, C_m, C_A0, C_N_alpha, C_m_alpha, table, c_mq)`,
`Lengths(l1, l2, u_B, u_C, misalign_deg)`.

The variable-mass model (`weight.m_d`/`l_d`/`l_p`/`I_d`/`I_sp`) is
specified but deliberately NOT enabled here (B15): enabling it needs
per-motor propellant mass and specific impulse, data a two-column thrust
curve does not carry. When real motor data arrives, enabling it is a
config edit, not a code change.
"""

from __future__ import annotations

from apps.motor_selection.compare_motors import MotorEntry

MOTORS: list[MotorEntry] = [
    MotorEntry(
        name="E small (39.75 Ns)",
        motor_curve="synthetic_small.csv",
        overrides={
            "weight.m": 0.90,       # 38 mm casing, lighter airframe  [kg]
            "weight.I": 0.045,      # pitch MOI about the CoG         [kg m^2]
            "aero.S": 0.00114,      # 38 mm body: pi*d^2/4            [m^2]
            "aero.d_ref": 0.038,    # moment/static-margin reference  [m]
            "aero.l_ref": 0.55,     # Reynolds reference length       [m]
            "lengths.l1": 0.22,     # CoP -> CoG                      [m]
            "lengths.l2": 0.30,     # CoG -> thrust point              [m]
        },
    ),
    # The equal-impulse pair (SS29.5): both H-class entries stay
    # override-free ON PURPOSE, so the comparison isolates burn-profile
    # effects (punchy vs sustained) on an otherwise-identical airframe.
    MotorEntry(name="H punchy (169.2 Ns)", motor_curve="synthetic_medium_punchy.csv"),
    MotorEntry(name="H sustainer (169.5 Ns)", motor_curve="synthetic_medium_long.csv"),
    MotorEntry(
        name="I large (338 Ns)",
        motor_curve="synthetic_large.csv",
        overrides={
            "weight.m": 2.40,       # 98 mm casing, heavier airframe
            "weight.I": 0.160,
            "aero.S": 0.00754,      # 98 mm body
            "aero.d_ref": 0.098,
            "aero.l_ref": 1.10,
            "lengths.l1": 0.38,
            "lengths.l2": 0.52,
        },
    ),
]

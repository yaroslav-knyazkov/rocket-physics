"""Simulation parameters.

Units: strict SI throughout (kg, m, s, N, N*m). Angles are in radians
internally; degrees only ever appear at the edges (run.py inputs, plot
labels).

Frame convention (see architecture.md SS2): a single NED-like inertial
frame with z pointing DOWN. This makes main.tex's W = m*g*z_hat_g literally
true with g > 0. Altitude is -z; nothing in the physics ever refers to
"altitude" directly.

Phase 2.11 rewrite, Step 50 (architecture-28-rewrite.md SS28.3): `Params`
is now composed of twelve small group dataclasses (`Weight`, `Thrust`,
`Lengths`, `Aero`, `Gravity`, `Site`, `Atmosphere`, `Soundings`, `Wind`,
`Recovery`, `Control`, `Solver`) instead of one ~70-field flat dataclass --
"one group per module that owns a dispatch", so the group structure
mirrors sim/'s own module structure.

This step is a **pure rename**: every group's field keeps the exact
physics/semantics its flat predecessor had (including, deliberately, the
"constant" aero model's un-scaled-by-q `A_x`/`A_z`/`A_m` placeholder bug --
that is fixed at Step 55, not here). `Aero.C_x`/`C_z`/`C_m` are today's
`A_x`/`A_z`/`A_m` field *names*, renamed to match the shape Step 55 will
give them meaning under; the formula that uses them is untouched in this
step (sim/forces.py still reads them as raw-Newton placeholders under
`aero.model == "constant"`).

Step 52 deleted the transitional flat shim (`Params.flat`, the hand-written
flat-routing `__init__`, and the read-only flat-name `@property` aliases)
once Step 51 had migrated every caller outside `sim/` to native nested
construction and the dotted-path `replace()` helper below. `Params` is now
a plain, ordinary `@dataclass(frozen=True)` with an auto-generated
`__init__` taking only the twelve real group fields plus `g0`.
"""

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional


# ----------------------------------------------------------------------
# The twelve group dataclasses (architecture-28-rewrite.md SS28.3)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Weight:
    m: float                      # initial (wet) mass [kg]
    I: float                      # pitch MOI about the CoG [kg*m^2]
    m_d: Optional[float] = None   # dry mass [kg]; None = mass model off (Step 36 gate)
    l_d: float = 0.0
    l_p: float = 0.0
    I_d: float = 0.0
    I_sp: float = 0.0
    I_p_spec: Optional[float] = None  # propellant MOI per unit mass about its own centroid [m^2]
                                       # ("radius of gyration squared"), i.e. the propellant's own
                                       # specific moment of inertia about its own centroid, per unit
                                       # mass. None -> fall back to the pre-Step-77 placeholder
                                       # (I_d/m_d) -- bit-for-bit unchanged when left None.


@dataclass(frozen=True)
class Thrust:
    motor_curve: str = ""         # file under data/motors/
    A_e: float = 0.0              # nozzle exit area [m^2]; 0.0 = pressure correction inert
    p_ref: float = 101325.0       # ambient pressure the curve was measured at [Pa]


@dataclass(frozen=True)
class Lengths:                    # geometry, all nose-tip-referenced, metres
    l1: float = 0.0               # CoP(D) -> CoG(B)
    l2: float = 0.0               # CoG -> thrust point(C) offset along the axis
    u_B: float = 0.0              # lateral offset of the CoG
    u_C: float = 0.0              # lateral offset of the thrust point
    misalign_deg: float = 0.0     # fixed nozzle cant delta [deg]  (was thrust_misalign_deg)


@dataclass(frozen=True)
class Aero:
    model: str = "constant"       # constant | linearized | table
    # shared by all three models
    S: float = 0.0                # reference area [m^2]
    d_ref: float = 0.0            # reference length for the moment and the static margin [m]
    l_ref: float = 0.0            # Reynolds reference length [m] (NOT the moment length)
    # model == "constant"
    C_x: float = 0.0              # axial-force coefficient [-]   (was A_x, raw Newtons until Step 55)
    C_z: float = 0.0              # normal-force coefficient [-]  (was A_z, raw Newtons until Step 55)
    C_m: float = 0.0              # pitching-moment coefficient [-] (was A_m, raw Newton-metres until Step 55)
    # model == "linearized"
    C_A0: float = 0.0
    C_N_alpha: float = 0.0        # [1/rad]
    C_m_alpha: float = 0.0        # [1/rad]
    # model == "table"
    table: str = ""               # file under data/aero/      (was aero_table)
    # all three models
    c_mq: float = 0.0             # pitch-damping derivative [-]


@dataclass(frozen=True)
class Gravity:
    model: str = "constant"       # constant | radial | wgs84      (magnitude)
    direction: str = "parallel"   # parallel | radial | elliptical (direction)
    R_e: float = 6371000.0        # mean Earth radius [m]
    earth_rotation: bool = False  # in-plane Coriolis correction (Step 37)


@dataclass(frozen=True)
class Site:                       # the launch site and the pad standing on it
    lat0_deg: float = 0.0
    lon0_deg: float = 0.0
    h0_m: float = 0.0             # site elevation above MSL
    azimuth_deg: float = 90.0     # direction of +x, deg clockwise from North
    L_rail: float = 0.0           # launch rail length [m]; 0.0 = off
    rail_angle_deg: float = 90.0  # rail elevation from horizontal


@dataclass(frozen=True)
class Atmosphere:
    model: str = "isa"            # isa | sounding | field
    humid_air: bool = False


@dataclass(frozen=True)
class Soundings:                  # the shared data layer for atmosphere AND wind tiers 2/3
    case: str = ""                # case folder under data/soundings/
    horizontal_interp: str = "idw"  # idw | rbf
    grid_top_m: float = 30000.0
    grid_step_m: float = 100.0
    idw_epsilon_m: float = 500.0


@dataclass(frozen=True)
class Wind:
    model: str = "none"           # none | analytic | sounding | field
    ref_ms: float = 0.0
    dir_deg: float = 0.0          # meteorological, from North, clockwise
    ref_h_m: float = 10.0
    shear_exp: float = 0.143
    turbulence_model: str = "none"  # none | dryden
    turbulence_sigma_high_ms: float = 0.0
    turbulence_ref_speed_ms: float = 100.0
    turbulence_seed: int = 0


@dataclass(frozen=True)
class Recovery:
    model: str = "none"           # none | deploy      (was parachute_model)
    trigger: str = "apogee"       # apogee | timer
    deploy_time: float = 0.0
    Cd: float = 0.8
    S: float = 0.0                # canopy reference area [m^2]; 0.0 = inert even if deployed


@dataclass(frozen=True)
class Control:
    airbrake_model: str = "none"          # none | proportional
    airbrake_target_apogee_m: float = 0.0
    airbrake_kp: float = 0.0
    airbrake_Cd: float = 1.0
    airbrake_S_max: float = 0.0
    airbrake_trigger: str = "after_burnout"    # after_burnout | after_time | after_apogee
    airbrake_deploy_time: float = 0.0          # s, read only when airbrake_trigger == "after_time"
    aero_coeff_model: str = "none"        # Step 57 seam; "none" = identity


@dataclass(frozen=True)
class Solver:
    method: str = "RK45"          # RK45 (or any scipy name) | rk4
    rtol: float = 1e-8
    atol: float = 1e-10
    t_max: float = 300.0
    dt: float = 0.001             # fixed-step path only
    sample_rate_hz: float = 0.0   # Step 59; 0.0 = no sampled-data mode


@dataclass(frozen=True)
class Params:
    """Every symbol from main.tex, composed into twelve groups (SS28.3)."""

    weight: Weight                              # the only required group
    g0: float = 9.80665                         # standard gravity, shared constant (see note)
    lengths:    Lengths    = field(default_factory=Lengths)
    thrust:     Thrust     = field(default_factory=Thrust)
    aero:       Aero       = field(default_factory=Aero)
    gravity:    Gravity    = field(default_factory=Gravity)
    site:       Site       = field(default_factory=Site)
    atmosphere: Atmosphere = field(default_factory=Atmosphere)
    soundings:  Soundings  = field(default_factory=Soundings)
    wind:       Wind       = field(default_factory=Wind)
    recovery:   Recovery   = field(default_factory=Recovery)
    control:    Control    = field(default_factory=Control)
    solver:     Solver     = field(default_factory=Solver)


# ----------------------------------------------------------------------
# architecture-28-rewrite.md SS28.4: the dotted-path `dataclasses.replace`
# helper, and the `Solver`-group convenience sugar.
# ----------------------------------------------------------------------


def replace(p: Params, changes: "dict[str, Any]") -> Params:
    """`replace(p, {"gravity.model": "wgs84", "aero.S": 0.005})` -- a nested
    `dataclasses.replace` that only ever rebuilds the groups it touches, so
    no untouched field in a changed group (or any other group) can be
    silently reset to its default. Unknown paths raise `TypeError` from
    `dataclasses.replace` itself (no input validation, SS7).

    A single-segment key (`"g0"`) passes straight through to `Params`
    itself. Only two levels of nesting exist in this schema, but the
    grouping-by-first-segment below supports arbitrary depth.
    """
    by_group: "dict[str, dict[str, Any]]" = {}
    top_level: "dict[str, Any]" = {}
    for path, value in changes.items():
        head, sep, rest = path.partition(".")
        if not sep:
            top_level[head] = value
        else:
            by_group.setdefault(head, {})[rest] = value

    group_updates: "dict[str, Any]" = {}
    for group_name, sub_changes in by_group.items():
        current_group = getattr(p, group_name)
        group_updates[group_name] = dataclasses.replace(current_group, **sub_changes)

    return dataclasses.replace(p, **group_updates, **top_level)


def with_solver(p: Params, **kw: Any) -> Params:
    """`with_solver(p, method="rk4", dt=1e-3)` -- convenience sugar for the
    one group almost every test touches (F6, ~60 call sites)."""
    return dataclasses.replace(p, solver=dataclasses.replace(p.solver, **kw))

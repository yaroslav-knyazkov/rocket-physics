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
    k_J: float = 1.0              # total-impulse factor (impulse = k_J*J, independent of k_t); 1.0 = as in the file
    k_t: float = 1.0              # time scale of the curve (burn-time scatter); 1.0 = as in the file


@dataclass(frozen=True)
class Lengths:                    # geometry, all nose-tip-referenced, metres
    l1: float = 0.0               # CoP(D) -> CoG(B)
    l2: float = 0.0               # CoP(D) -> thrust point(C) distance along the axis
    u_B: float = 0.0              # lateral offset of the CoG
    u_C: float = 0.0              # lateral offset of the thrust point
    misalign_deg: float = 0.0     # fixed nozzle cant delta [deg]  (was thrust_misalign_deg)
    l_g: float = 0.0              # CoG station from the nose [m], used only with an Aero.l_p / l_p_m CP and the
                                  # mass model OFF (Step 99); with the mass model on the CoG comes from sim/mass.py


@dataclass(frozen=True)
class Aero:
    model: str = "constant"       # constant | linearized | table
    # shared by all three models
    S: float = 0.0                # reference area [m^2]
    d_ref: float = 0.0            # reference length for the moment and the static margin [m]
    l_ref: float = 0.0            # Reynolds reference length [m] (NOT the moment length); 0.0 -> falls back to d_ref
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
    # pitch-damping derivative [-]. CODE sign (positive = damping). Step 115 (conventions audit
    # §1.3): the scalar IS flipped by `cm_convention="standard"` for the constant/linearized models
    # (same `_cm_to_code` conversion as `C_m`/`C_m_alpha`), matching the table's c_mq column, which
    # was already flipped there since Step 114.
    c_mq: float = 0.0
    # Step 99 (D-111): moment reference station from the nose [m] (x_ref) for the
    # constant/linearized models
    # (arm = l_p - CoG(t)); 0.0 = off, Lengths.l1 is the arm. A table carries its own l_p_m column.
    l_p: float = 0.0
    # C_m sign convention of the constant/linearized coefficients: "code" (positive C_m = nose-down,
    # restoring for a positive slope) | "standard" (textbook, restoring = negative slope; flipped on use).
    # A table declares its own via a `# cm_convention:` header line.
    cm_convention: str = "code"
    # Step 112 (D-120): out-of-range alpha policy of the table model. "clamp" = hold the edge value (legacy,
    # bit-identical; warns once per run); "jorgensen" = large-alpha extension (potential + crossflow terms),
    # needs S_p and l_pc. All fields below are inert under "clamp".
    table_oob: str = "clamp"
    oob_blend_deg: float = 10.0   # width of the blend band beyond the table edge [deg]
    S_p: float = 0.0              # planform area [m^2]; REQ iff jorgensen
    l_pc: float = 0.0             # planform-centroid station from the nose [m]; REQ iff jorgensen
    C_dn: float = 1.2             # crossflow drag coefficient of a cylinder [-] (Mach/Re dependence not modelled)
    eta: float = 0.0              # finite-length factor; 0.0 -> from fineness S_p/d_ref^2
    C_x180: float = 0.0           # axial coefficient magnitude, tail-first flow; 0.0 -> C_x(0) of the table
    S_base: float = 0.0           # base area of the potential term [m^2]; 0.0 -> S
    # Step 105 (architecture-35-paper-alignment.md SS35.4.1/SS35.4.5, D-105 dispersion
    # hooks): multiplier on C_x, applied in sim/aero.py's `coefficients` choke point
    # (the single place every downstream consumer of C_x reads from). 1.0 (the default)
    # is skipped entirely -- not multiplied by 1.0 -- so every pinned flight is
    # bit-for-bit unchanged; only a Monte-Carlo dispersion run (apps/common/ensemble.py)
    # sets this away from 1.0.
    cx_scale: float = 1.0


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
    # Step 105 (architecture-35-paper-alignment.md SS35.4.1/SS35.4.5, dispersion
    # hooks): ISA launch-day temperature offset [K], applied in sim/atmosphere.py's
    # "isa" tier only. 0.0 (the default) is skipped entirely, so every pinned flight
    # is bit-for-bit unchanged; a Monte-Carlo dispersion run (apps/common/ensemble.py)
    # sets this away from 0.0.
    dT_K: float = 0.0


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
    # Step 102 (D-109): how the brake enters the aerodynamics. "additive" = the legacy axial term
    # q*Cd*S_max*f_b (default, bit-identical); "table" = the aero table's f_b axis supplies the brake's
    # C_A/C_N/C_m/l_p (needs Aero.model == "table" with an f_b column; the additive term is then off).
    airbrake_aero: str = "additive"       # additive | table


@dataclass(frozen=True)
class Actuator:
    """Step 103 (architecture-35-paper-alignment.md SS35.6, D-114): the
    sampled-data airbrake's own actuator dynamics -- rate limit,
    deployment range, and command delay, closed form (no servo-lag model;
    D-114 explicitly rejected a second-order model -- no parameters known
    yet -- and rejected staying ideal-only).

    `model = "ideal"` (the default) is exactly the Step 59 zero-order
    hold: the held command IS the deploy fraction for the whole tick,
    bit-for-bit unchanged, and every field below is unused. `model =
    "full"` adds the rate/range/delay mechanics
    (`sim/control.py`'s `AirbrakeHold`/`_ramp`); `rate_open = rate_close =
    inf` (the default even under `"full"`) makes the rate limit
    unconditionally unbounded (never `rate*dt`, which would be `inf*0.0 ==
    nan` at a tick's own first instant) -- so it reduces to exactly the
    same zero-order hold, bit-for-bit (this group's own acceptance test).
    """
    model: str = "ideal"              # ideal | full
    rate_open: float = float("inf")   # fraction/s, opening (cmd > current)
    rate_close: float = float("inf")  # fraction/s, closing (cmd < current)
    f_min: float = 0.0
    f_max: float = 1.0
    delay_ticks: int = 0              # command delay, whole sample ticks


@dataclass(frozen=True)
class Solver:
    method: str = "RK45"          # RK45 (or any scipy name) | rk4 | rk45_seg (Step 104, D-116 -- requires sample_rate_hz>0.0)
    rtol: float = 1e-8
    atol: float = 1e-10
    t_max: float = 300.0
    dt: float = 0.001             # fixed-step path only
    sample_rate_hz: float = 0.0   # Step 59; 0.0 = no sampled-data mode


@dataclass(frozen=True)
class Params:
    """Every symbol from main.tex, composed into groups (SS28.3) -- twelve
    at Step 50, plus `Actuator` (Step 103, architecture-35-paper-
    alignment.md SS35.6)."""

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
    actuator:   Actuator   = field(default_factory=Actuator)
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

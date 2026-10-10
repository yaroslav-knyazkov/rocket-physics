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

### The transitional flat shim (deleted at Step 52)

Every module outside `sim/` (`tests/`, `run.py`, `apps/`) still builds
`Params` with the pre-Step-50 flat keyword names -- `Params.flat(m=...,
I=..., l1=..., aero_table=...)` -- and still calls `dataclasses.replace(p,
<old_flat_name>=...)` throughout. Both must keep working unmodified until
Step 51 migrates those call sites to the native nested constructors and
`replace()` below.

The mechanism: `Params.__init__` is written by hand (`@dataclass(init=False)`
below) instead of letting `@dataclass` generate it. It accepts the twelve
real nested group fields *and* arbitrary extra keyword arguments -- every
old flat name from Step-49-and-earlier `Params`, routed through
`_FLAT_TO_GROUP` into the group/field it now lives on. This one seam makes
three different call shapes work with no special-casing anywhere else:

  * `Params.flat(m=0.5, I=0.05, aero_table="x.csv")` -- a brand-new nested
    `Params` built entirely from old flat names. `Params.flat` is nothing
    more than `cls(**kwargs)`; the real work is in `__init__`.
  * `dataclasses.replace(p, aero_model="table")` -- `dataclasses.replace`
    (stdlib) always passes every *real* dataclass field's current value
    forward explicitly (`fields(p)` only ever sees the twelve groups +
    `g0`), plus whatever override kwargs the caller gave it, then calls
    `Params(**that_dict)`. So `__init__` receives the previous `p.aero`
    *object* (unchanged) alongside the flat override `aero_model="table"`;
    it rebuilds just the `aero` group from the passed-in object plus the
    matching override, leaving every other field of that group (and every
    other group entirely) untouched. This is exactly `replace()`'s own
    dotted-path logic (SS28.4 below), just reached through the flat name
    instead of a dotted one.
  * `Params(weight=Weight(...), aero=Aero(...))` -- plain nested
    construction (what Step 51 migrates everything to) -- no flat kwargs
    present, works exactly like an ordinary dataclass `__init__`.

`T` (Phase 1's constant-thrust magnitude) is dead code since Step 14
(`thrust_body` reads the motor curve, never `p.T`) and is deleted as a
field here (SS28.3's D-14) -- but `tests/test_forces.py` still passes
`T=...` to two `Params(...)` constructions as a harmless leftover. Routed
to nothing, silently: accepted and discarded, not rejected, since rejecting
it would be a behaviour change this step is not allowed to make.
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
    aero_coeff_model: str = "none"        # Step 57 seam; "none" = identity


@dataclass(frozen=True)
class Solver:
    method: str = "RK45"          # RK45 (or any scipy name) | rk4
    rtol: float = 1e-8
    atol: float = 1e-10
    t_max: float = 300.0
    dt: float = 0.001             # fixed-step path only
    sample_rate_hz: float = 0.0   # Step 59; 0.0 = no sampled-data mode


# ----------------------------------------------------------------------
# The old flat name -> (group attribute, group field name) map. Every key
# here is a Params kwarg some caller (tests/, run.py, apps/) could still
# pass today, pre-Step-51. "g" (-> top-level g0) and "T" (-> deleted,
# silently discarded) are handled outside this dict -- see __init__ below.
# ----------------------------------------------------------------------

_FLAT_TO_GROUP: "dict[str, tuple[str, str]]" = {
    # Weight
    "m": ("weight", "m"),
    "I": ("weight", "I"),
    "m_d": ("weight", "m_d"),
    "l_d": ("weight", "l_d"),
    "l_p": ("weight", "l_p"),
    "I_d": ("weight", "I_d"),
    "I_sp": ("weight", "I_sp"),
    # Thrust
    "motor_curve": ("thrust", "motor_curve"),
    "A_e": ("thrust", "A_e"),
    "p_ref": ("thrust", "p_ref"),
    # Lengths
    "l1": ("lengths", "l1"),
    "l2": ("lengths", "l2"),
    "u_B": ("lengths", "u_B"),
    "u_C": ("lengths", "u_C"),
    "thrust_misalign_deg": ("lengths", "misalign_deg"),
    # Aero
    "aero_model": ("aero", "model"),
    "S": ("aero", "S"),
    "d_ref": ("aero", "d_ref"),
    "l_ref": ("aero", "l_ref"),
    "A_x": ("aero", "C_x"),
    "A_z": ("aero", "C_z"),
    "A_m": ("aero", "C_m"),
    "C_A0": ("aero", "C_A0"),
    "C_N_alpha": ("aero", "C_N_alpha"),
    "C_m_alpha": ("aero", "C_m_alpha"),
    "aero_table": ("aero", "table"),
    "c_mq": ("aero", "c_mq"),
    # Gravity
    "gravity_model": ("gravity", "model"),
    "gravity_direction": ("gravity", "direction"),
    "R_e": ("gravity", "R_e"),
    "earth_rotation": ("gravity", "earth_rotation"),
    # Site
    "lat0_deg": ("site", "lat0_deg"),
    "lon0_deg": ("site", "lon0_deg"),
    "h0_m": ("site", "h0_m"),
    "azimuth_deg": ("site", "azimuth_deg"),
    "L_rail": ("site", "L_rail"),
    "rail_angle_deg": ("site", "rail_angle_deg"),
    # Atmosphere
    "atmosphere_model": ("atmosphere", "model"),
    "humid_air": ("atmosphere", "humid_air"),
    # Soundings
    "sounding_case": ("soundings", "case"),
    "horizontal_interp": ("soundings", "horizontal_interp"),
    "grid_top_m": ("soundings", "grid_top_m"),
    "grid_step_m": ("soundings", "grid_step_m"),
    "idw_epsilon_m": ("soundings", "idw_epsilon_m"),
    # Wind
    "wind_model": ("wind", "model"),
    "wind_ref_ms": ("wind", "ref_ms"),
    "wind_dir_deg": ("wind", "dir_deg"),
    "wind_ref_h_m": ("wind", "ref_h_m"),
    "wind_shear_exp": ("wind", "shear_exp"),
    "turbulence_model": ("wind", "turbulence_model"),
    "turbulence_sigma_high_ms": ("wind", "turbulence_sigma_high_ms"),
    "turbulence_ref_speed_ms": ("wind", "turbulence_ref_speed_ms"),
    "turbulence_seed": ("wind", "turbulence_seed"),
    # Recovery
    "parachute_model": ("recovery", "model"),
    "parachute_deploy_trigger": ("recovery", "trigger"),
    "parachute_deploy_time": ("recovery", "deploy_time"),
    "parachute_Cd": ("recovery", "Cd"),
    "parachute_S": ("recovery", "S"),
    # Control
    "airbrake_model": ("control", "airbrake_model"),
    "airbrake_target_apogee_m": ("control", "airbrake_target_apogee_m"),
    "airbrake_kp": ("control", "airbrake_kp"),
    "airbrake_Cd": ("control", "airbrake_Cd"),
    "airbrake_S_max": ("control", "airbrake_S_max"),
}

# Old flat names silently accepted and discarded -- dead fields with no
# new-shape equivalent. "T": Params.T, dead since Step 14 (D-14).
_FLAT_DISCARDED = frozenset({"T"})

# Group attribute name -> its dataclass type, used by __init__ below to
# construct/rebuild a group from a dict of its own field overrides.
_GROUP_TYPES = {
    "weight": Weight,
    "thrust": Thrust,
    "lengths": Lengths,
    "aero": Aero,
    "gravity": Gravity,
    "site": Site,
    "atmosphere": Atmosphere,
    "soundings": Soundings,
    "wind": Wind,
    "recovery": Recovery,
    "control": Control,
    "solver": Solver,
}


@dataclass(frozen=True, init=False)
class Params:
    """Every symbol from main.tex, composed into twelve groups (SS28.3).

    `__init__` is hand-written (see module docstring) so that old flat
    keyword arguments keep working through Step 51 via the transitional
    shim; everything else about this class (`fields()`, `__repr__`,
    `__eq__`, frozen `__setattr__` protection, `dataclasses.replace`) is
    the ordinary `@dataclass(frozen=True)` machinery, unaffected by
    `init=False`.
    """

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

    def __init__(
        self,
        weight: "Weight | None" = None,
        g0: float = 9.80665,
        lengths: "Lengths | None" = None,
        thrust: "Thrust | None" = None,
        aero: "Aero | None" = None,
        gravity: "Gravity | None" = None,
        site: "Site | None" = None,
        atmosphere: "Atmosphere | None" = None,
        soundings: "Soundings | None" = None,
        wind: "Wind | None" = None,
        recovery: "Recovery | None" = None,
        control: "Control | None" = None,
        solver: "Solver | None" = None,
        **flat_kwargs: Any,
    ) -> None:
        groups: "dict[str, Any]" = {
            "weight": weight, "lengths": lengths, "thrust": thrust,
            "aero": aero, "gravity": gravity, "site": site,
            "atmosphere": atmosphere, "soundings": soundings, "wind": wind,
            "recovery": recovery, "control": control, "solver": solver,
        }

        # Collect per-group field overrides coming in through flat kwargs
        # (old names) before constructing/rebuilding each group once.
        per_group_overrides: "dict[str, dict[str, Any]]" = {}
        for key, value in flat_kwargs.items():
            if key in ("g0", "g"):  # "g" is the old (Phase 1) flat name for g0
                g0 = value
                continue
            if key in _FLAT_DISCARDED:
                continue  # e.g. "T" -- dead field, accepted and dropped (D-14)
            if key not in _FLAT_TO_GROUP:
                raise TypeError(
                    f"Params() got an unexpected keyword argument {key!r}"
                )
            group_name, field_name = _FLAT_TO_GROUP[key]
            per_group_overrides.setdefault(group_name, {})[field_name] = value

        for group_name, group_type in _GROUP_TYPES.items():
            base = groups[group_name]
            overrides = per_group_overrides.get(group_name)
            if base is None:
                resolved = group_type(**overrides) if overrides else group_type()
            elif overrides:
                resolved = dataclasses.replace(base, **overrides)
            else:
                resolved = base
            object.__setattr__(self, group_name, resolved)
            # Note: `weight` has no explicit "is it present" check here --
            # `Weight.m`/`Weight.I` have no defaults, so `Weight()`/
            # `Weight(**overrides)` above already raises TypeError on its
            # own when neither `weight=` nor the flat `m=`/`I=` kwargs were
            # given, exactly like the pre-Step-50 flat dataclass did.

        object.__setattr__(self, "g0", g0)

    @classmethod
    def flat(cls, **old_kwargs: Any) -> "Params":
        """Construct a `Params` from pre-Step-50 flat keyword arguments
        only -- `Params.flat(m=0.5, I=0.05, l1=0.3, l2=0.4,
        aero_table="x.csv")`. A thin, explicitly-named alias for
        `cls(**old_kwargs)` (the real routing lives in `__init__`), kept
        as its own classmethod so call sites read as "this is the
        transitional flat constructor" rather than looking like ordinary
        nested construction (architecture-28-rewrite.md SS28.11's S50
        ticket: "`tests/`, `run.py` and `apps/` are touched only by a
        mechanical `Params(` -> `Params.flat(` substitution"). Deleted at
        Step 52 along with the rest of the shim.
        """
        return cls(**old_kwargs)

    # ------------------------------------------------------------------
    # Read-only flat-name aliases (deleted at Step 52). Every pre-Step-50
    # `Params` field is reachable here under its old name, so any `p.<old
    # name>` read outside sim/ (tests/, run.py, apps/) keeps working
    # unmodified until Step 51 migrates those reads too.
    # ------------------------------------------------------------------

    @property
    def g(self) -> float:
        return self.g0

    # Weight
    @property
    def m(self) -> float:
        return self.weight.m

    @property
    def I(self) -> float:
        return self.weight.I

    @property
    def m_d(self) -> "Optional[float]":
        return self.weight.m_d

    @property
    def l_d(self) -> float:
        return self.weight.l_d

    @property
    def l_p(self) -> float:
        return self.weight.l_p

    @property
    def I_d(self) -> float:
        return self.weight.I_d

    @property
    def I_sp(self) -> float:
        return self.weight.I_sp

    # Thrust
    @property
    def motor_curve(self) -> str:
        return self.thrust.motor_curve

    @property
    def A_e(self) -> float:
        return self.thrust.A_e

    @property
    def p_ref(self) -> float:
        return self.thrust.p_ref

    # Lengths
    @property
    def l1(self) -> float:
        return self.lengths.l1

    @property
    def l2(self) -> float:
        return self.lengths.l2

    @property
    def u_B(self) -> float:
        return self.lengths.u_B

    @property
    def u_C(self) -> float:
        return self.lengths.u_C

    @property
    def thrust_misalign_deg(self) -> float:
        return self.lengths.misalign_deg

    # Aero
    @property
    def aero_model(self) -> str:
        return self.aero.model

    @property
    def S(self) -> float:
        return self.aero.S

    @property
    def d_ref(self) -> float:
        return self.aero.d_ref

    @property
    def l_ref(self) -> float:
        return self.aero.l_ref

    @property
    def A_x(self) -> float:
        return self.aero.C_x

    @property
    def A_z(self) -> float:
        return self.aero.C_z

    @property
    def A_m(self) -> float:
        return self.aero.C_m

    @property
    def C_A0(self) -> float:
        return self.aero.C_A0

    @property
    def C_N_alpha(self) -> float:
        return self.aero.C_N_alpha

    @property
    def C_m_alpha(self) -> float:
        return self.aero.C_m_alpha

    @property
    def aero_table(self) -> str:
        return self.aero.table

    @property
    def c_mq(self) -> float:
        return self.aero.c_mq

    # Gravity
    @property
    def gravity_model(self) -> str:
        return self.gravity.model

    @property
    def gravity_direction(self) -> str:
        return self.gravity.direction

    @property
    def R_e(self) -> float:
        return self.gravity.R_e

    @property
    def earth_rotation(self) -> bool:
        return self.gravity.earth_rotation

    # Site
    @property
    def lat0_deg(self) -> float:
        return self.site.lat0_deg

    @property
    def lon0_deg(self) -> float:
        return self.site.lon0_deg

    @property
    def h0_m(self) -> float:
        return self.site.h0_m

    @property
    def azimuth_deg(self) -> float:
        return self.site.azimuth_deg

    @property
    def L_rail(self) -> float:
        return self.site.L_rail

    @property
    def rail_angle_deg(self) -> float:
        return self.site.rail_angle_deg

    # Atmosphere
    @property
    def atmosphere_model(self) -> str:
        return self.atmosphere.model

    @property
    def humid_air(self) -> bool:
        return self.atmosphere.humid_air

    # Soundings
    @property
    def sounding_case(self) -> str:
        return self.soundings.case

    @property
    def horizontal_interp(self) -> str:
        return self.soundings.horizontal_interp

    @property
    def grid_top_m(self) -> float:
        return self.soundings.grid_top_m

    @property
    def grid_step_m(self) -> float:
        return self.soundings.grid_step_m

    @property
    def idw_epsilon_m(self) -> float:
        return self.soundings.idw_epsilon_m

    # Wind
    @property
    def wind_model(self) -> str:
        return self.wind.model

    @property
    def wind_ref_ms(self) -> float:
        return self.wind.ref_ms

    @property
    def wind_dir_deg(self) -> float:
        return self.wind.dir_deg

    @property
    def wind_ref_h_m(self) -> float:
        return self.wind.ref_h_m

    @property
    def wind_shear_exp(self) -> float:
        return self.wind.shear_exp

    @property
    def turbulence_model(self) -> str:
        return self.wind.turbulence_model

    @property
    def turbulence_sigma_high_ms(self) -> float:
        return self.wind.turbulence_sigma_high_ms

    @property
    def turbulence_ref_speed_ms(self) -> float:
        return self.wind.turbulence_ref_speed_ms

    @property
    def turbulence_seed(self) -> int:
        return self.wind.turbulence_seed

    # Recovery
    @property
    def parachute_model(self) -> str:
        return self.recovery.model

    @property
    def parachute_deploy_trigger(self) -> str:
        return self.recovery.trigger

    @property
    def parachute_deploy_time(self) -> float:
        return self.recovery.deploy_time

    @property
    def parachute_Cd(self) -> float:
        return self.recovery.Cd

    @property
    def parachute_S(self) -> float:
        return self.recovery.S

    # Control
    @property
    def airbrake_model(self) -> str:
        return self.control.airbrake_model

    @property
    def airbrake_target_apogee_m(self) -> float:
        return self.control.airbrake_target_apogee_m

    @property
    def airbrake_kp(self) -> float:
        return self.control.airbrake_kp

    @property
    def airbrake_Cd(self) -> float:
        return self.control.airbrake_Cd

    @property
    def airbrake_S_max(self) -> float:
        return self.control.airbrake_S_max


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

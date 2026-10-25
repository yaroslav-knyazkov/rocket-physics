"""configs/schema.py -- `Config` and `Variant` (Step 63, roadmap.md,
`dev/docs/architecture-30-apps-4-5-and-configs.md` SS30.4).

Both frozen dataclasses, both trivially constructible, no inheritance, no
builders. `Config` is one complete, runnable scenario (`Params` + initial
`State` + provenance notes) -- vehicle-and-environment level, reusable by
every tool including `run.py`. `Variant` is a *named delta* against some
`Config` -- the generalisation of App 3's `MotorEntry.overrides`, for
studies that compare N perturbations of one baseline.

Importing this module: config modules (`configs/<name>.py`) must do
`from configs.schema import Config`, **never** `from configs import
Config`. `configs/__init__.py` imports every config module to build the
registry, so a config module reaching back into the package's own (at
that point still partially-initialised) namespace would be a circular
import. Importing this submodule directly, as above, is always safe --
`configs/schema.py` has no dependency on `configs/__init__.py`.

Step 71 (`dev/docs/architecture-31-config-separation.md` SS31.4) adds four
more frozen dataclasses -- `Rocket`, `LaunchSite`, `Weather`, `Scenario`
-- and the module-level `assemble(sc)` / `_pad_state(site)` that turn a
`Scenario` into an ordinary `Config`. **`Config` and `Variant` above are
unchanged** and remain the only consumption-level API `apps/` and every
`run*.py` ever take -- the pieces are a construction-time convenience
that assembles down to the same `Config` nothing downstream needs to
know came from pieces at all.

The one-owner invariant (SS31.4, D-49): every one of `Params`' twelve
groups has exactly one owning piece (`weight`/`lengths`/`thrust`/`aero`/
`recovery`/`control` from `Rocket`; `site` from `LaunchSite`;
`atmosphere`/`soundings`/`wind` from `Weather`; `gravity`/`solver`/`g0`
as plain `Scenario` fields, SS31.3.2). `assemble` has no merge logic, no
"last writer wins" and no partial-group updates -- the keyword set of
its single `Params(...)` call is pinned, structurally, against
`{f.name for f in dataclasses.fields(Params)}` by
`tests/test_config_pieces.py` (SS31.8 #1), so a thirteenth `Params`
group would fail that test loudly instead of silently taking its
default in every scenario. Amended at Step 80 (D-57,
`dev/docs/architecture-32-motor-separation.md` SS32.2.3/SS32.3.3): `weight`
is now the one DERIVED group -- a function of two disjoint-field-set
inputs, `Rocket.airframe` (+ `Rocket.sections`) and `Scenario.motor`,
composed by `_weight_from_pieces`, not a merge with a precedence rule.
Every other group keeps its single owning piece unchanged, and `thrust`
moves from `Rocket` to `Scenario.motor`. Step 103 (architecture-35-paper-
alignment.md SS35.6, D-114) adds one more group, `actuator`, owned by
`Rocket` alongside `control` -- the sampled-data airbrake's own actuator
(rate/range/delay) is the same kind of vehicle control hardware `control`
already is, not a run-level concern.

The import rule above now also applies to pieces: piece modules do
`from configs.schema import Rocket`, **never** `from configs import
Rocket`, and a piece never reaches up into `configs.scenarios`,
`configs.rockets`, `configs.sites` or `configs.weather` -- those
subpackages do not exist yet as of this step (Step 72 adds them); this
step only adds the piece *types* and the assembly function they
compose through.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from sim import aero
from sim import mass
from sim import motor_file
from sim.params import Actuator
from sim.params import Aero
from sim.params import Atmosphere
from sim.params import Control
from sim.params import Gravity
from sim.params import Lengths
from sim.params import Params
from sim.params import Recovery
from sim.params import Roll
from sim.params import Sensors
from sim.params import Site
from sim.params import Solver
from sim.params import Soundings
from sim.params import Thrust
from sim.params import Weight
from sim.params import Wind
from sim.params import replace as params_replace
from sim.state import State

__all__ = [
    "Config",
    "Variant",
    "Rocket",
    "LaunchSite",
    "Weather",
    "Scenario",
    "assemble",
    "Airframe",
    "Sections",
    "Motor",
]


@dataclasses.dataclass(frozen=True)
class Config:
    """One complete, runnable scenario: the `Params`, the initial `State`,
    and where the numbers came from."""

    name: str                  # registry key, e.g. "demo"
    params: Params
    s0: State
    notes: str = ""            # provenance: source of the numbers, date, what it is for

    def derive(
        self,
        name: str,
        overrides: dict[str, Any],
        notes: str = "",
        s0: State | None = None,
    ) -> "Config":
        """A new `Config`, `overrides` applied via `sim.params.replace` --
        one call, arbitrarily many dotted keys (architecture.md SS29 F1),
        so no untouched field anywhere in `Params` is silently reset.
        `s0` defaults to this `Config`'s own (inherited unless overridden
        here). Frozen dataclasses throughout: this `Config` is never
        mutated, and the result is a new, independent object."""
        return dataclasses.replace(
            self,
            name=name,
            params=params_replace(self.params, overrides),
            s0=self.s0 if s0 is None else s0,
            notes=notes,
        )

    def with_variant(self, v: "Variant") -> "Config":
        """`v` applied to this config, named `f"{self.name}+{v.name}"`."""
        return self.derive(name=f"{self.name}+{v.name}", overrides=v.overrides, notes=v.notes)


@dataclasses.dataclass(frozen=True)
class Variant:
    """A *named delta* against some `Config` -- the generalisation of App
    3's `MotorEntry.overrides`, for studies that compare N perturbations
    of one baseline (App 5 mode (a), and any future what-if sweep)."""

    name: str
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    def apply(self, cfg: Config) -> Config:
        """`== cfg.with_variant(self)` -- implemented in terms of it so
        the two can never drift apart."""
        return cfg.with_variant(self)


# ----------------------------------------------------------------------
# Phase 2.16 (dev/docs/architecture-32-motor-separation.md SS32.2, SS32.3):
# `Airframe`, `Sections`, `Motor` -- the pieces the motor's own mass/CoG/
# MOI history is split out into -- and the assembly-time composition
# `_weight_from_pieces` (below `assemble`) that turns them (plus
# `Rocket`'s other groups, unchanged) into the one `Weight` the engine
# consumes. Added standalone and unwired at Step 78; wired up at Step 80,
# where `Rocket` gained `airframe`/`sections` (replacing `weight`/
# `thrust`) and `Scenario` gained `motor`, and `assemble` started calling
# `_weight_from_pieces` instead of reading `sc.rocket.weight` directly.
# Defined here, ahead of `Rocket`, because `Rocket.sections`' default
# factory needs the `Sections` class object to already exist.
# ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Airframe:
    """The vehicle WITHOUT its motor: structure, nose, fins, recovery
    hardware, avionics, ballast -- one rigid lump.

    Deliberately NOT called "dry": in this project "dry" (`Weight.m_d`)
    has always meant "without propellant, casing included", and these
    numbers exclude the motor entirely. B25 replaces this lump with a
    per-section mass distribution; until then it is two measured numbers,
    plus a third (`l`) once a mass-modelled motor is fitted.

    `l` is a station: POSITIVE, measured aft of the nose tip A (SS32.5).
    """

    m: float  # REQ, kg      -- airframe mass, motor excluded
    I: float  # REQ, kg*m^2  -- pitch MOI about the airframe's OWN CoG (`l`)
    l: float | None = None  # OPT, m -- airframe CoG station aft of A; REQ
    #                                   whenever the paired Motor has
    #                                   mass_model != "none"


@dataclasses.dataclass(frozen=True)
class Sections:
    """Named airframe stations, every one a POSITIVE distance aft of the
    nose tip A (rocket-2d.tex SSGeometry; SS32.5 restates the convention).

    Exactly ONE field is read by any code today -- `l_motor_fwd` (or
    `l_motor_aft`), which places the motor for the SS32.3 composition.
    Everything else is documentation with a structure: the landing spot
    for B25's per-section mass distribution, and the provenance for
    `Lengths.l1`/`l2`, which stay authoritative and are NOT derived from
    these (D-68) -- this step does not implement that derivation, it only
    states the non-goal here.
    """

    L_total: float = 0.0  # OPT, m -- overall length, nose tip to tail
    l_nose: float = 0.0  # OPT, m -- nose cone length == station of the nose/body joint
    l_fin_root_fwd: float = 0.0  # OPT, m -- fin root leading-edge station
    l_fin_root_aft: float = 0.0  # OPT, m -- fin root trailing-edge station
    l_motor_fwd: float | None = None  # OPT, m -- station of the motor's FORWARD face
    l_motor_aft: float | None = None  # OPT, m -- station of the motor's AFT face; the
    #                                              forward face resolves to
    #                                              l_motor_aft - motor.length
    tubes: tuple[tuple[str, float], ...] = ()  # OPT -- ((name, aft-end station m), ...), informational
    notes: str = ""  # OPT -- where these dimensions came from


@dataclasses.dataclass(frozen=True)
class Motor:
    """One motor installation: its thrust curve, and its OWN mass / CoG /
    MOI history (SS32.3).

    Geometry is MOTOR-LOCAL: the origin is the motor's forward
    (nose-ward) face and distances are POSITIVE aft, the same sense the
    airframe uses from the nose tip A (SS32.5). That is what makes one
    motor reusable across airframes -- the rocket supplies the mounting
    station (`Sections.l_motor_fwd`), the motor never knows where it is
    installed.

    Every `None` below means "derive it": from the motor file's own
    header if it has one (`.eng`/`.rasp`), otherwise from the
    uniform-cylinder defaults in SS32.3.3. A `.csv` curve carries no
    header, so a `.csv` motor with `mass_model != "none"` must spell the
    masses out.
    """

    name: str  # REQ, registry key, e.g. "cti_k570"
    thrust: Thrust = dataclasses.field(default_factory=Thrust)  # REQ in practice; owns Params.thrust whole

    # --- which m(t) model is active (SS32.3.4) --------------------------
    mass_model: str = "none"  # OPT, none | isp | endpoints; "none" = constant-mass flight

    # --- masses ---------------------------------------------------------
    m_total: float | None = None  # OPT, kg  -- loaded mass at ignition  (.eng header field 6)
    m_prop: float | None = None  # OPT, kg  -- propellant mass          (.eng header field 5)
    I_sp: float | None = None  # OPT, s   -- specific impulse; REQ when mass_model == "isp"

    # --- the motor's own geometry, motor-local, positive aft -------------
    length: float | None = None  # OPT, m -- overall length   (.eng header field 3, mm)
    diameter: float | None = None  # OPT, m -- casing diameter  (.eng header field 2, mm)
    l_case: float | None = None  # OPT, m -- casing centroid;      None -> length/2
    l_prop: float | None = None  # OPT, m -- propellant centroid;  None -> length/2
    I_case: float | None = None  # OPT, kg*m^2 -- casing MOI about its own centroid;  None -> uniform cylinder
    I_prop0: float | None = None  # OPT, kg*m^2 -- propellant MOI about its own centroid at t=0;
    #                                              None -> uniform cylinder

    # --- the user's endpoint parameterisation, SS32.3.5 (an alternative
    #     to l_prop / I_prop0 above; give one form OR the other) ---------
    l_cog_0: float | None = None  # OPT, m      -- motor-local CoG at ignition
    l_cog_f: float | None = None  # OPT, m      -- motor-local CoG at burnout
    I_0: float | None = None  # OPT, kg*m^2 -- motor's own MOI at ignition, about its own CoG
    I_f: float | None = None  # OPT, kg*m^2 -- motor's own MOI at burnout,  about its own CoG

    d_exit: float | None = None  # OPT, m -- nozzle exit diameter; assemble sets Thrust.A_e = pi/4*d_exit^2
    #                                      (None -> Thrust.A_e as given; both given and A_e != 0 -> ValueError)

    notes: str = ""  # OPT -- provenance: vendor, datasheet, date, measured or estimated


# ----------------------------------------------------------------------
# Step 71 (architecture-31-config-separation.md SS31.4): the four piece
# types, and the `assemble` function that composes them into a `Config`.
# ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Rocket:
    """One airframe: structure, geometry, aerodynamics, and the
    recovery/control hardware bolted to it -- but NOT its motor (SS32.1).

    Changed at Step 80 (`dev/docs/architecture-32-motor-separation.md`
    SS32.2.3): `weight: Weight` -> `airframe: Airframe` (the
    `Params.weight` group is now DERIVED by `assemble` from this piece
    plus the `Scenario.motor` piece, SS32.3); `thrust: Thrust` REMOVED
    (the `Motor` piece owns it now); `sections: Sections` added.
    """

    name: str
    airframe: Airframe  # the only required group
    lengths: Lengths = dataclasses.field(default_factory=Lengths)
    aero: Aero = dataclasses.field(default_factory=Aero)
    recovery: Recovery = dataclasses.field(default_factory=Recovery)
    control: Control = dataclasses.field(default_factory=Control)
    # Step 103 (architecture-35-paper-alignment.md SS35.6, D-114): the
    # sampled-data airbrake's own actuator (rate/range/delay) -- same
    # owning piece as `control` above, the vehicle's own control hardware,
    # not a run-level/weather/site concern (SS31.3.2's one-owner
    # invariant).
    actuator: Actuator = dataclasses.field(default_factory=Actuator)
    # Step 109 (task-109-roll-reaction-wheel.md SS109.7b): the roll DOF and
    # its reaction wheel -- same owning piece as control/actuator above,
    # vehicle control hardware, not a run-level/weather/site concern
    # (SS31.3.2's one-owner invariant).
    roll: Roll = dataclasses.field(default_factory=Roll)   # Step 109
    # Step 108 (architecture-35-paper-alignment.md SS35.4.4, D-115): the
    # baro channel's own hardware characteristics -- same owning piece as
    # control/actuator above (vehicle control/sensing hardware, not a
    # run-level/weather/site concern).
    sensors: Sensors = dataclasses.field(default_factory=Sensors)
    sections: Sections = dataclasses.field(default_factory=Sections)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class LaunchSite:
    """One place you fly from, and the pad standing on it (SS31.3.4)."""

    name: str
    site: Site = dataclasses.field(default_factory=Site)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class Weather:
    """One flying day's air: the atmosphere model, the sounding case it may
    read, and the wind -- one piece because a sounding measures all three
    (SS31.3.3, F4)."""

    name: str
    atmosphere: Atmosphere = dataclasses.field(default_factory=Atmosphere)
    soundings: Soundings = dataclasses.field(default_factory=Soundings)
    wind: Wind = dataclasses.field(default_factory=Wind)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One named combination of a rocket, a MOTOR, a site and a day's
    weather, plus the run-level groups nobody reuses by name (SS31.3.2).
    `.config` assembles it into the ordinary `Config` every tool already
    takes."""

    name: str
    rocket: Rocket
    motor: Motor  # NEW at Step 80, required -- SS32.1, D-58
    site: LaunchSite
    weather: Weather
    gravity: Gravity = dataclasses.field(default_factory=Gravity)
    solver: Solver = dataclasses.field(default_factory=Solver)
    g0: float = 9.80665
    s0: State | None = None  # None -> derived from the rail (D-51)
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    @property
    def config(self) -> Config:
        return assemble(self)


def assemble(sc: Scenario) -> Config:
    """SS31.4, amended by SS32.3/D-57. Exactly one owner per `Params`
    group, with ONE named exception: `weight` is DERIVED from two pieces
    with disjoint field sets (`Rocket.airframe`/`Rocket.sections` +
    `Scenario.motor`) by `_weight_from_pieces` below -- a function of two
    inputs, not a merge with a precedence rule, so no field can come from
    two places (the property D-49 actually protects). The keyword set
    below is still `dataclasses.fields(Params)` exactly (pinned by test,
    SS31.8 #1) -- this change moves *sources*, not keywords."""
    # (1) gather groups from the pieces -- one keyword per group, each
    #     sourced from exactly one owning piece
    thrust = sc.motor.thrust  # owner moved: Rocket -> Motor (Step 80)
    if sc.motor.d_exit is not None:  # Step 98 (D-112): nozzle exit diameter -> exit area
        if not sc.motor.d_exit >= 0.0:  # QA-5: negative / NaN would be silently squared
            raise ValueError(f"Motor {sc.motor.name!r}: d_exit must be >= 0, got {sc.motor.d_exit}")
        if thrust.A_e != 0.0:
            raise ValueError(
                f"Motor {sc.motor.name!r}: give either d_exit or Thrust.A_e, not both"
            )
        thrust = dataclasses.replace(thrust, A_e=math.pi / 4.0 * sc.motor.d_exit**2)
    p = Params(
        weight=_weight_from_pieces(sc.rocket.airframe, sc.rocket.sections, sc.motor, sc.g0),  # DERIVED, SS32.3
        lengths=sc.rocket.lengths,
        thrust=thrust,
        aero=sc.rocket.aero,
        recovery=sc.rocket.recovery,
        control=sc.rocket.control,
        actuator=sc.rocket.actuator,
        roll=sc.rocket.roll,
        sensors=sc.rocket.sensors,
        site=sc.site.site,
        atmosphere=sc.weather.atmosphere,
        soundings=sc.weather.soundings,
        wind=sc.weather.wind,
        gravity=sc.gravity,
        solver=sc.solver,
        g0=sc.g0,
    )
    # (2) the scenario's own last word, dotted paths over the whole tree
    if sc.overrides:
        p = params_replace(p, sc.overrides)  # sim.params.replace, SS29 F1
    # (2b) Step 99: fail-fast on the aero v2 options (CP station needs a CoG
    #      station and zero cant; known C_m convention) -- a no-op for legacy configs.
    aero.validate(p)
    # (2c) QA-4: thrust-scatter factors scale impulse / burn time; non-positive values are
    #      meaningless (k_t = 0 divides by zero inside the RHS).
    for _f in ("k_J", "k_t"):
        if not getattr(p.thrust, _f) > 0.0:
            raise ValueError(f"Thrust.{_f} must be > 0, got {getattr(p.thrust, _f)}")
    # (2d) Step 114: propellant consistency. The solver burns J/(I_sp g0) of mass (k_t cancels,
    #      k_J does not scale the flow); more than the loaded propellant (+1 %) means the mass
    #      floor in `dynamics.derivatives` would freeze dm/dt while thrust continues.
    if p.weight.m_d is not None and p.weight.I_sp and p.thrust.motor_curve:
        J = motor_file.load(p.thrust.motor_curve).total_impulse
        burned = J / (p.weight.I_sp * p.g0)
        m_prop = p.weight.m - p.weight.m_d
        if burned > 1.01 * m_prop:
            raise ValueError(
                f"Motor {sc.motor.name!r}: I_sp={p.weight.I_sp:g} s implies {burned:.4g} kg of propellant "
                f"burned (J={J:.4g} N*s / (I_sp*g0)) but m_prop={m_prop:.4g} kg: inconsistent "
                "I_sp / m_prop (thrust would continue after the mass floor)"
            )
    # (3) s0 AFTER overrides -- so an overridden rail angle moves the
    #     initial attitude with it (F5, D-51); getting this order backwards
    #     would re-create F5's foot-gun inside the mechanism that
    #     advertises fixing it.
    s0 = sc.s0 if sc.s0 is not None else _pad_state(p.site)
    # (4) D-76: with the mass model on, the integrator reads mass from y[M], not
    #     weight.m (sim/dynamics.py) -- start it at the composed launch mass.
    if p.weight.m_d is not None and s0.m == 0.0:
        s0 = s0._replace(m=p.weight.m)
    return Config(name=sc.name, params=p, s0=s0, notes=sc.notes)


def _pad_state(site: Site) -> State:
    """At rest on the pad, nose along the rail. `math.radians(90.0)` is
    exactly `math.pi / 2` (F6), so this reproduces every existing config's
    `s0` bit-for-bit."""
    return State(
        x=0.0,
        z=0.0,
        vx=0.0,
        vz=0.0,
        theta=math.radians(site.rail_angle_deg),
        omega=0.0,
    )


def _weight_from_pieces(airframe: Airframe, sections: Sections, motor: Motor, g0: float) -> Weight:
    """SS32.3. Compose the airframe lump and the motor's own lumps into
    the one `Params.weight` group the engine consumes (D-56, D-57).

    Signature note, deliberate: takes `(airframe, sections, motor, g0)`,
    NOT `(rocket, motor, g0)` -- so it works unchanged against both
    today's `Rocket` (no `airframe`/`sections` fields yet) and the
    Step-80 `Rocket` (which will have them); Step 80's `assemble` calls
    this as `_weight_from_pieces(sc.rocket.airframe, sc.rocket.sections,
    sc.motor, sc.g0)`. Recorded here so Step 80 does not need to
    re-derive the rationale.

    Four cases, in this order (SS32.3.3):

    (0) `motor.mass_model == "none"` -- PASS-THROUGH, and an explicit
        early return rather than `combine()` of one lump (F4 --
        `combine()` is not an exact identity even for a single lump): the
        airframe's own numbers ARE the vehicle's, the mass model stays
        off, and every pre-Step-80 config comes out bit-for-bit.
    (1) resolve the motor's own numbers: header fields from
        `sim.motor_file.load(motor.thrust.motor_curve)` for every field
        left `None` on `motor` (D-67) -- an explicit `Motor` field always
        overrides the file -- then geometry defaults (`l_case`/`l_prop`
        -> `length/2`, `I_case`/`I_prop0` -> the uniform-cylinder default),
        OR the exact SS32.3.5 endpoint inversion when the motor gives
        `l_cog_0`/`l_cog_f`/`I_0`/`I_f` instead of `l_prop`/`I_prop0`
        directly.
    (2) place the motor: motor-local stations become nose-tip stations by
        adding `l_fwd = sections.l_motor_fwd` (or
        `sections.l_motor_aft - motor.length`). Raises, naming the two
        fields, if neither or both of `l_motor_fwd`/`l_motor_aft` are
        given; raises, naming the field, if `airframe.l is None` -- both
        only while `mass_model != "none"`.
    (3) compose with `sim.mass.Lump`/`combine` and emit the five
        mass-model `Weight` fields.

    Six properties of this function (SS32.3.3), each one load-bearing:

    1. Pass-through is bit-for-bit, by construction (case 0 above).
    2. `m`/`I` are the composed values at t=0, i.e. the loaded (wet)
       vehicle -- `Weight.m`/`I`'s meaning all along. `m_d`/`l_d`/`I_d`
       are the composed DRY assembly (airframe + casing) -- same meaning
       as before, different provenance: they used to be typed in by
       hand, now they are computed.
    3. `l_p` is a nose-tip station, exactly like `l_d` -- safe because
       every consumer reads it only as a difference (F6).
    4. This function runs once per scenario, at import (assembly time),
       not once per RHS evaluation -- F2's two-body reduction is what
       makes that true.
    5. It touches the filesystem only when `mass_model != "none"` (D-70):
       every existing seed stays on the "none" pass-through path, which
       never calls `sim.motor_file`.
    6. Its two preconditions (above, case (2)) raise with a message
       naming the offending field, not a bare `TypeError` from `None +
       float`.
    """
    if motor.mass_model == "none":
        # (0) PASS-THROUGH -- explicit early return, not combine() of one
        # lump (F4): the airframe's own numbers ARE the vehicle's.
        return Weight(m=airframe.m, I=airframe.I)

    # (1) resolve the motor's own numbers ---------------------------------
    # Touches the filesystem (D-70) -- only reached when mass_model !=
    # "none".
    record = motor_file.load(motor.thrust.motor_curve)

    m_total = motor.m_total if motor.m_total is not None else record.m_total
    m_prop = motor.m_prop if motor.m_prop is not None else record.m_prop
    length = motor.length if motor.length is not None else record.length
    diameter = motor.diameter if motor.diameter is not None else record.diameter
    m_c = m_total - m_prop  # the casing's own mass, m_f in SS32.3.5's notation

    if motor.l_cog_0 is not None:
        # The user's endpoint parameterisation (SS32.3.5) -- inverted,
        # once, at assembly time, into the (l_case, l_prop, I_case,
        # I_prop0) this function needs everywhere else. Exact algebra,
        # re-derived from mass-weighted centroid + parallel axis:
        #   l_cog_f = l_case                           (only casing left at burnout)
        #   l_cog_0 = (m_c*l_case + m_prop*l_prop) / m_total
        #     => l_prop = (m_total*l_cog_0 - m_c*l_cog_f) / (m_total - m_c)
        #   I_f = I_case
        #   I_0 = I_case + m_c*(l_cog_0-l_case)^2 + I_prop0 + m_prop*(l_cog_0-l_prop)^2
        #     => I_prop0 = I_0 - I_f - m_c*(l_cog_0-l_cog_f)^2 - m_prop*(l_cog_0-l_prop)^2
        l_case = motor.l_cog_f
        l_prop = (m_total * motor.l_cog_0 - m_c * motor.l_cog_f) / (m_total - m_c)
        I_case = motor.I_f
        I_prop0 = (
            motor.I_0
            - motor.I_f
            - m_c * (motor.l_cog_0 - motor.l_cog_f) ** 2
            - m_prop * (motor.l_cog_0 - l_prop) ** 2
        )
    else:
        l_case = motor.l_case if motor.l_case is not None else length / 2.0
        l_prop = motor.l_prop if motor.l_prop is not None else length / 2.0
        I_case = (
            motor.I_case
            if motor.I_case is not None
            else mass.uniform_cylinder_I(m_c, length, diameter)
        )
        I_prop0 = (
            motor.I_prop0
            if motor.I_prop0 is not None
            else mass.uniform_cylinder_I(m_prop, length, diameter)
        )

    # (2) place the motor: motor-local stations -> nose-tip stations -----
    fwd_given = sections.l_motor_fwd is not None
    aft_given = sections.l_motor_aft is not None
    if fwd_given == aft_given:
        raise ValueError(
            "exactly one of sections.l_motor_fwd / sections.l_motor_aft "
            "must be given when motor.mass_model != 'none' (got "
            f"l_motor_fwd={sections.l_motor_fwd!r}, l_motor_aft={sections.l_motor_aft!r})"
        )
    l_fwd = sections.l_motor_fwd if fwd_given else sections.l_motor_aft - length

    if airframe.l is None:
        raise ValueError(
            "airframe.l is required when motor.mass_model != 'none' (got airframe.l=None)"
        )

    # (3) compose ----------------------------------------------------------
    airframe_lump = mass.Lump(m=airframe.m, l=airframe.l, I=airframe.I)
    casing_lump = mass.Lump(m=m_c, l=l_fwd + l_case, I=I_case)
    prop_lump = mass.Lump(m=m_prop, l=l_fwd + l_prop, I=I_prop0)

    dry = mass.combine(airframe_lump, casing_lump)  # static -- F2

    if motor.mass_model == "isp":
        I_sp = motor.I_sp
    else:  # "endpoints" -- SS32.3.4, D-59
        I_sp = mass.isp_from_impulse(record.total_impulse, m_prop, g0)

    wet = mass.combine(dry, prop_lump)  # t=0 only, for m and I

    return Weight(
        m=wet.m,
        I=wet.I,
        m_d=dry.m,
        l_d=dry.l,
        I_d=dry.I,
        l_p=prop_lump.l,
        I_sp=I_sp,
        I_p_spec=(prop_lump.I / prop_lump.m) if prop_lump.m else None,
    )

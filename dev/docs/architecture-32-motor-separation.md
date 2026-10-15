# Architecture §32 — Motor separation: a `Motor` config piece, composed mass, real `.eng`/`.rasp` curves (Phase 2.16, design only)

## Summary

**Status: designed 2026-10-15 against the user's own request, relayed by the orchestrator with an
explicit instruction not to block — "decide it yourself, document it as a recommendation".
All eighteen decision forks (D-56 … D-73, §32.10) therefore carry a *recommended* answer rather
than a decided one, and implementation proceeds tonight on those recommendations.
The decision log is what the user confirms (or overturns) tomorrow morning; nothing in §32.2-§32.9
is unimplementable pending that confirmation.** Implementation tickets are §32.11 (Steps 75-84,
Phase 2.16); no code written yet.

The request, in one line: **the motor stops being four fields on the rocket and becomes a piece of
its own** — a sibling to `Rocket`/`LaunchSite`/`Weather`, with `configs/motors/`, its own registry
and template, referenced by `Scenario`. It brings with it its own thrust curve, its own
`m(t)`/`l_COG(t)`/`I(t)`, and the file formats (`.csv`, `.eng`, `.rasp`) real motor data actually
comes in. The rocket keeps the airframe: a dry mass and dry MOI that now **exclude the motor
entirely**, plus named section stations measured from the nose tip `A`.

This promotes a backlog candidate §31.11 wrote down and declined by name — *"Named motor
installations as a fourth piece, if the motor becomes a reused object rather than a sweep entry"* —
and it closes the data half of **B14** (`.eng` import) and **B15** (per-motor mass metadata),
both opened by the §29 design and both blocked on exactly the two things this phase builds: a RASP
reader and somewhere for per-motor mass numbers to live.

**Three results make the whole phase cheap, and all three were measured on this tree, not assumed.**

1. **The two-body composition collapses *exactly* onto the two-lumped-mass model
   `sim/dynamics.py` already implements** (§32.3, F2). An airframe and a motor casing are rigid
   *relative to each other* — only the propellant shrinks — so "two separately-moving centroids" is
   not what this problem is. There is one rigid dry assembly and one shrinking propellant lump,
   which is `main.tex` §`sec:mass`'s model verbatim with `m_d`/`l_d`/`I_d` reinterpreted as the
   *combined* dry assembly. The composition is therefore **static, computed once, at assembly
   time**, and `sim/dynamics.py`'s hot path is untouched.
2. **The "two endpoint masses, no `I_sp`" mass model is algebraically identical to today's `I_sp`
   model** with an effective specific impulse `I_sp_eff = J / (m_prop * g0)`, `J` the curve's own
   total impulse (§32.3, D-59). Shaping `m(t)` by *cumulative impulse fraction* rather than by time
   is both the physically honest choice for a non-constant curve **and** the one that needs no new
   `sim/` code path at all — it is the existing `dm/dt = -T_ref(t)/(I_sp g0)` with a derived
   constant. Measured on the real Cesaroni file: `I_sp_eff = 212.41 s`.
3. **The RASP curve's first row is not at `t = 0`, and that matters by 1%.**
   `data/motors/Cesaroni_2060K570-17A.eng` starts at `(0.04 s, 892.67 N)`. Today's
   `np.interp(..., left=thrusts[0])` would hold 892.67 N from `t = 0`, manufacturing 35.7 N·s the
   motor never produced. Prepending an explicit `(0.0, 0.0)` point gives a total impulse of
   **2062.22 N·s**, which is **0.108 %** from the manufacturer's own designation ("2060"); the
   hold-first reading gives 2080.08 N·s, **0.975 %** high. The prepend is the correct reading, it is
   free (no `.eng` file loads at all today, so no existing run can change), and the 2060 in the
   motor's name is an independent check on the parser (D-64, F5).

**No existing number changes.** `sim/params.py` gains exactly one field (`Weight.I_p_spec`,
`None`-gated, Step 77); `sim/dynamics.py` loses three private helpers to a new `sim/mass.py` and
gains nothing; `sim/thrust_curve.py` delegates file reading to a new `sim/motor_file.py` and keeps
its `thrust(t, s, p)` force-model seam byte-identical in behaviour. The phase's primary gate is the
same four exact-equality pins Phase 2.15 used (§32.11), because every seed's assembled `Params`
must come out bit-for-bit despite being built from five pieces instead of four.

**What this phase does *not* claim to be free: three test files need real edits** (§32.11), and that
is stated up front rather than discovered at Step 80. `Rocket.thrust` goes away and
`Scenario.motor` becomes required, so `tests/test_config_pieces.py`'s `_non_default_rocket()`
helper, `tests/test_config_migration.py`'s two `rocket.thrust` assertions and
`tests/test_config_registries.py`'s four-package parametrisation all move. Unlike Phase 2.15, "zero
test edits" is **not** this phase's gate and was never achievable: a piece type being removed from
`Rocket` is a surface change, not a `git mv`.

**Two backlog items are opened and deliberately not built: B24** (motor mass/CoG/MOI by integrating
real grain geometry and burn regression, replacing the lumped two-point model) and **B25** (rocket
dry mass/CoG/MOI by integrating a per-section mass distribution / BOM, replacing two hand-entered
numbers) — §32.7. Both are the user's own stated TODOs and both now have a structural landing spot
rather than being a rewrite.

---

## Contents

- [§32.1 Problem statement — what moves where](#321-problem-statement--what-moves-where)
- [§32.2 The schemas — `Motor`, `Airframe`, `Sections`, and the new `Rocket`/`Scenario`](#322-the-schemas--motor-airframe-sections-and-the-new-rocketscenario)
  - [§32.2.1 `Motor`](#3221-motor)
  - [§32.2.2 `Airframe` and `Sections`](#3222-airframe-and-sections)
  - [§32.2.3 The new `Rocket`, the new `Scenario`, the new `assemble`](#3223-the-new-rocket-the-new-scenario-the-new-assemble)
- [§32.3 Mass composition — `sim/mass.py`, and the bit-for-bit reduction](#323-mass-composition--simmasspy-and-the-bit-for-bit-reduction)
  - [§32.3.1 The findings this section rests on](#3231-the-findings-this-section-rests-on)
  - [§32.3.2 `sim/mass.py` — the module](#3232-simmasspy--the-module)
  - [§32.3.3 `_weight_from_pieces` — the assembly-time composition](#3233-_weight_from_pieces--the-assembly-time-composition)
  - [§32.3.4 The `m(t)` models, and why the endpoint model needs no new code](#3234-the-mt-models-and-why-the-endpoint-model-needs-no-new-code)
  - [§32.3.5 `l_COG(t)` and `I(t)` — keeping the physical model, accepting the user's inputs](#3235-l_cogt-and-it--keeping-the-physical-model-accepting-the-users-inputs)
- [§32.4 The file readers — `.csv`, `.eng`, `.rasp`](#324-the-file-readers--csv-eng-rasp)
- [§32.5 Rocket sections, and the sign convention stated once](#325-rocket-sections-and-the-sign-convention-stated-once)
- [§32.6 Aero / CoP — confirmation, not redesign](#326-aero--cop--confirmation-not-redesign)
- [§32.7 The two backlog TODOs (B24, B25)](#327-the-two-backlog-todos-b24-b25)
- [§32.8 Templates documentation convention](#328-templates-documentation-convention)
- [§32.9 `configs/` and `data/` cleanup — keep/delete list](#329-configs-and-data-cleanup--keepdelete-list)
- [§32.10 Decision log (D-56 … D-73)](#3210-decision-log-d-56--d-73)
- [§32.11 Implementation tickets (Steps 75-84, Phase 2.16)](#3211-implementation-tickets-steps-75-84-phase-216)
- [§32.12 Risks](#3212-risks)
- [§32.13 Rejected options, and backlog candidates](#3213-rejected-options-and-backlog-candidates)

---

## 32.1 Problem statement — what moves where

One short paragraph per numbered point of the request.

**1 — a `Motor` piece, out of `Rocket`.** `configs/schema.py` gains a fifth frozen dataclass,
`Motor`, and `configs/motors/` joins the four subpackages with the same explicit-tuple registry,
the same `_TEMPLATE_motor.py` rules and the same import-DAG position (§31.5's three rules,
unchanged, now five times over). `Scenario` gains a **required** `motor: Motor` field;
`Rocket.thrust` is **removed**. The `Motor` piece owns `Params.thrust` whole — `motor_curve`,
`A_e`, `p_ref` — so the one-owner invariant (D-49) holds for that group exactly as before, just
with a different owner. §31.11 explicitly left this as a backlog candidate and named the trigger —
"if the user later wants named motor *installations* … rather than a sweep list" — which is what has
happened.

**2 — who owns which half of today's mass model.** Today `Weight(m, I, m_d, l_d, l_p, I_d, I_sp)`
is one rocket-owned group meaning "the whole vehicle, dry structure versus remaining propellant".
After this phase: the **rocket** owns the airframe *excluding the motor* (`Airframe.m`, `.I`, `.l`),
and the **motor** owns its own casing *and* its propellant (`m_total`, `m_prop`, `l_case`, `l_prop`,
`I_case`, `I_prop0`, `I_sp`), in **motor-local** coordinates so one motor is reusable across
airframes. `Params.weight` becomes the first **derived** group: `assemble` composes the two pieces
into it (§32.3). The composition is a two-body parallel-axis/mass-weighted-centroid combination at
the motor's mounting station, and §32.3.1's F2 shows it reduces exactly — same expression, not
merely same value — to today's `_cog_position`/`_moment_of_inertia` whenever there is one dry
assembly and one propellant lump, which is always.

**3 — `m(t)` models.** Two, both explicit: `mass_model="isp"` is today's
`dm/dt = -T_ref(t)/(I_sp g0)`, kept unchanged as the primary model; `mass_model="endpoints"` takes
`m_0 = m_total` and `m_f = m_total - m_prop` — exactly the RASP header's two mass fields — and
shapes `m(t)` by **cumulative impulse fraction**, not by time. That choice is not a compromise: it
is algebraically the `"isp"` model with `I_sp_eff = J/(m_prop g0)`, so it is simultaneously the more
physically honest shaping for a non-constant curve *and* zero new `sim/` code (§32.3.4, D-59).

**4 — `l_COG(t)` and `I(t)`.** The user offered "for now linearly with `l_COG_0`/`l_COG_f` and
`I_0`/`I_f`" and invited something better. There is something better and it is already written and
already tested: the mass-weighted centroid + parallel-axis model in `sim/dynamics.py`, which is
linear in `m_p(t)` rather than in raw time and therefore stays physically consistent whatever shape
the thrust curve has. Recommendation (D-60): **keep that model**, re-homed onto the `Motor` piece —
*and* accept the user's endpoint inputs as an alternative *parameterisation*, because
`(m_0, m_f, l_0, l_f)` inverts **exactly** into `(m_d, l_d, l_p)` (§32.3.5). So the user types what
they wanted to type and gets the physically consistent interpolation in between. Literal
time-linearity is recorded as the rejected alternative, not implemented.

**5 — readers for `.csv`, `.eng`, `.rasp`.** A new `sim/motor_file.py` owns file formats and
returns a `MotorRecord` carrying `(times, thrusts)` **plus** the header metadata the mass model
needs (`m_prop`, `m_total`, diameter, length, designation, manufacturer).
`sim/thrust_curve.py` keeps its `thrust(t, s, p)` force-model seam and delegates loading to it —
bit-for-bit for `.csv`, newly functional for `.eng`. `.rasp` is read as a **multi-record RASP
library** (the historical `rasp.eng` motor-database shape), with record selection by an optional
`#designation` fragment on the existing `motor_curve` string (D-63); since a one-record file is a
library of size one, `.eng` and `.rasp` share a single grammar and a single parser, and the only
real dispatch is CSV-versus-RASP.

**6 — `Rocket` restructuring.** `Rocket.weight: Weight` becomes `Rocket.airframe: Airframe` (dry
mass, dry MOI, dry CoG station — all **excluding** the motor), and `Rocket.sections: Sections`
arrives with named stations measured from the nose tip `A`. **`Lengths.l1`/`l2` stay exactly as they
are** and stay authoritative (D-68): deriving them from absolute stations would change every
existing run's numbers and would invent the `l1(t)`/`l2(t)` physics `architecture.md` §19 is still
blocked on. `Sections` is therefore additive — it *places the motor* (the one station the
composition reads) and documents the airframe for B25. **Nothing in `sim/dynamics.py` or
`sim/forces.py` changes as a consequence**, confirmed in §32.5. The sign convention is restated
there verbatim and unchanged: every length is **input as a positive distance aft of `A`**, and the
negative sign appears exactly once, where a station enters a body-frame vector.

**7 — aero CoP.** Confirmed implemented, nothing to change: §32.6 is one paragraph of confirmation
with file and line references.

**8 — two TODOs, not built.** B24 (grain-geometry integration for the motor) and B25 (per-section
BOM for the airframe), §32.7.

**9 — templates documentation.** Every field of every template gets `# REQ|OPT, <unit or choices>
-- <one-line description>`, **and** each template file ends with a compact per-field table (D-71,
§32.8). Both, not either: the inline comment is what you read while editing, the table is what you
read to find out whether you have missed a field.

**10 — `configs/`/`data/` cleanup.** `configs/` is already exactly "template + small demo set" per
subpackage; nothing to trim. `data/` turns out to have **nothing safely deletable** — every file is
either real data (the `.eng` motor, `soundings/example_live/`) or load-bearing for a test or an
app's demo. The concrete keep list and the three files whose deletion would have a named cost are
in §32.9, framed as a developer ticket with a recommendation, not an action.

---

## 32.2 The schemas — `Motor`, `Airframe`, `Sections`, and the new `Rocket`/`Scenario`

All additions are frozen dataclasses in `configs/schema.py`, in the §30.4 house style: trivially
constructible, no inheritance, no builders, no validation. Units are strict SI (`sim/params.py`'s
module docstring); degrees appear only at this edge. `None` is a meaningful value throughout — it
means "not given, derive it or leave the feature off", the same convention `Weight.m_d` already
uses as the mass model's own off switch.

### 32.2.1 `Motor`

```python
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

    name: str                                                   # REQ, registry key, e.g. "cti_k570"
    thrust: Thrust = dataclasses.field(default_factory=Thrust)   # REQ in practice; owns Params.thrust whole

    # --- which m(t) model is active (SS32.3.4) --------------------------
    mass_model: str = "none"        # OPT, none | isp | endpoints; "none" = constant-mass flight

    # --- masses ---------------------------------------------------------
    m_total: float | None = None    # OPT, kg  -- loaded mass at ignition  (.eng header field 6)
    m_prop:  float | None = None    # OPT, kg  -- propellant mass          (.eng header field 5)
    I_sp:    float | None = None    # OPT, s   -- specific impulse; REQ when mass_model == "isp"

    # --- the motor's own geometry, motor-local, positive aft -------------
    length:   float | None = None   # OPT, m -- overall length   (.eng header field 3, mm)
    diameter: float | None = None   # OPT, m -- casing diameter  (.eng header field 2, mm)
    l_case:   float | None = None   # OPT, m -- casing centroid;      None -> length/2
    l_prop:   float | None = None   # OPT, m -- propellant centroid;  None -> length/2
    I_case:   float | None = None   # OPT, kg*m^2 -- casing MOI about its own centroid;  None -> uniform cylinder
    I_prop0:  float | None = None   # OPT, kg*m^2 -- propellant MOI about its own centroid at t=0;
                                    #                None -> uniform cylinder

    # --- the user's endpoint parameterisation, SS32.3.5 (an alternative
    #     to l_prop / I_prop0 above; give one form OR the other) ---------
    l_cog_0: float | None = None    # OPT, m      -- motor-local CoG at ignition
    l_cog_f: float | None = None    # OPT, m      -- motor-local CoG at burnout
    I_0:     float | None = None    # OPT, kg*m^2 -- motor's own MOI at ignition, about its own CoG
    I_f:     float | None = None    # OPT, kg*m^2 -- motor's own MOI at burnout,  about its own CoG

    notes: str = ""                 # OPT -- provenance: vendor, datasheet, date, measured or estimated
```

Three properties of this shape are deliberate, and each one is a fork in §32.10:

- **`thrust` is the whole `Params.thrust` group, not individual fields.** `motor_curve`, `A_e` and
  `p_ref` are all properties of *this motor in this nozzle*, so the group travels intact and
  `assemble` stays merge-free for it. D-49's one-owner invariant is untouched for `thrust`; only
  `weight` becomes derived (D-57).
- **The header fields default to `None`, meaning "read them from the file".** A complete, physically
  honest motor config for a real RASP file is then three lines (§32.3.3, D-67) — which is the entire
  point of a reader that *keeps* the header instead of discarding it. Spelling a value out overrides
  the header, which is how you model a motor you have re-cased or partially loaded.
- **`mass_model="none"` is the default**, so a `Motor` that is only a thrust curve — what all five
  existing seeds need, and what all four `synthetic_*.csv` fixtures are — is
  `Motor(name=…, thrust=Thrust(motor_curve=…))` and composes to *exactly* today's
  `Weight(m=airframe.m, I=airframe.I, m_d=None)`. That pass-through is what makes the migration
  provable rather than reviewable (§32.3.3).

### 32.2.2 `Airframe` and `Sections`

```python
@dataclasses.dataclass(frozen=True)
class Airframe:
    """The vehicle WITHOUT its motor: structure, nose, fins, recovery
    hardware, avionics, ballast -- one rigid lump.

    Deliberately NOT called "dry": in this project "dry" (`Weight.m_d`)
    has always meant "without propellant, casing included", and these
    numbers exclude the motor entirely. B25 replaces this lump with a
    per-section mass distribution; until then it is two measured numbers,
    plus a third once a mass-modelled motor is fitted.

    `l` is a station: POSITIVE, measured aft of the nose tip A (SS32.5).
    """

    m: float                 # REQ, kg      -- airframe mass, motor excluded
    I: float                 # REQ, kg*m^2  -- pitch MOI about the airframe's OWN CoG (`l`)
    l: float | None = None   # OPT, m       -- airframe CoG station aft of A; REQ whenever the
                             #                 paired Motor has mass_model != "none"


@dataclasses.dataclass(frozen=True)
class Sections:
    """Named airframe stations, every one a POSITIVE distance aft of the
    nose tip A (rocket-2d.tex SSGeometry; SS32.5 restates the convention).

    Exactly ONE field is read by any code today -- `l_motor_fwd` (or
    `l_motor_aft`), which places the motor for the SS32.3 composition.
    Everything else is documentation with a structure: the landing spot
    for B25's per-section mass distribution, and the provenance for
    `Lengths.l1`/`l2`, which stay authoritative and are NOT derived from
    these (D-68).
    """

    L_total:        float = 0.0   # OPT, m -- overall length, nose tip to tail
    l_nose:         float = 0.0   # OPT, m -- nose cone length == station of the nose/body joint
    l_fin_root_fwd: float = 0.0   # OPT, m -- fin root leading-edge station
    l_fin_root_aft: float = 0.0   # OPT, m -- fin root trailing-edge station
    l_motor_fwd:    float | None = None   # OPT, m -- station of the motor's FORWARD face
    l_motor_aft:    float | None = None   # OPT, m -- station of the motor's AFT face; the forward
                                          #           face resolves to l_motor_aft - motor.length
    tubes: tuple[tuple[str, float], ...] = ()   # OPT -- ((name, aft-end station m), ...), informational
    notes: str = ""               # OPT -- where these dimensions came from
```

`l_motor_fwd` / `l_motor_aft` are two ways to say one thing and **exactly one** should be given: a
kit drawing dimensions the motor-mount tube from the nose (`l_motor_fwd`), while an aft-flush
install is naturally dimensioned from the tail (`l_motor_aft = L_total`, the forward face falling
out of the motor's own length, which the `.eng` header supplies). Giving both, or neither while a
mass model is active, raises from the composition with a message naming the two fields (§32.3.3).

### 32.2.3 The new `Rocket`, the new `Scenario`, the new `assemble`

```python
@dataclasses.dataclass(frozen=True)
class Rocket:
    """One airframe: structure, geometry, aerodynamics, and the
    recovery/control hardware bolted to it -- but NOT its motor (SS32.1).

    Changed at Step 80: `weight: Weight` -> `airframe: Airframe` (the
    `Params.weight` group is now DERIVED by `assemble` from this piece
    plus the Motor piece, SS32.3); `thrust: Thrust` REMOVED (the Motor
    piece owns it); `sections: Sections` added.
    """

    name: str                                                      # REQ
    airframe: Airframe                                             # REQ -- the only required group
    lengths:  Lengths  = dataclasses.field(default_factory=Lengths)
    aero:     Aero     = dataclasses.field(default_factory=Aero)
    recovery: Recovery = dataclasses.field(default_factory=Recovery)
    control:  Control  = dataclasses.field(default_factory=Control)
    sections: Sections = dataclasses.field(default_factory=Sections)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One named combination of a rocket, a MOTOR, a site and a day's
    weather, plus the run-level groups nobody reuses by name (SS31.3.2)."""

    name: str
    rocket: Rocket
    motor: Motor                    # NEW at Step 80, required -- SS32.1, D-58
    site: LaunchSite
    weather: Weather
    gravity: Gravity = dataclasses.field(default_factory=Gravity)
    solver:  Solver  = dataclasses.field(default_factory=Solver)
    g0: float = 9.80665
    s0: State | None = None
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    @property
    def config(self) -> Config:
        return assemble(self)
```

```python
def assemble(sc: Scenario) -> Config:
    """SS31.4, amended by SS32.3 / D-57. Exactly one owner per `Params`
    group, with ONE named exception: `weight` is DERIVED from two pieces
    with disjoint field sets (`Rocket.airframe` + `Motor`) by the
    composition function below. That is a function of two inputs, not a
    merge with a precedence rule -- no field can come from two places,
    which is the property D-49 actually protects.

    The keyword set below is `dataclasses.fields(Params)` exactly, still
    pinned by `tests/test_config_pieces.py` (SS31.8 #1) -- and pinned
    UNEDITED, because this change moves *sources*, not keywords.
    """
    p = Params(
        weight=_weight_from_pieces(sc.rocket, sc.motor, sc.g0),   # DERIVED, SS32.3
        lengths=sc.rocket.lengths,
        thrust=sc.motor.thrust,                                   # owner moved: Rocket -> Motor
        aero=sc.rocket.aero,
        recovery=sc.rocket.recovery,
        control=sc.rocket.control,
        site=sc.site.site,
        atmosphere=sc.weather.atmosphere,
        soundings=sc.weather.soundings,
        wind=sc.weather.wind,
        gravity=sc.gravity,
        solver=sc.solver,
        g0=sc.g0,
    )
    if sc.overrides:
        p = params_replace(p, sc.overrides)
    s0 = sc.s0 if sc.s0 is not None else _pad_state(p.site)
    return Config(name=sc.name, params=p, s0=s0, notes=sc.notes)
```

Two things about that call a future reader will want to check:

- **`g0` is passed into the composition.** `I_sp_eff = J/(m_prop·g0)` needs it (§32.3.4), and the
  scenario is where `g0` lives (D-47a). It is read, never written, so `g0`'s single owner is
  unchanged.
- **The keyword set is byte-identical to Step 71's**, so
  `test_assemble_params_call_keyword_set_equals_params_fields_exactly` — which AST-parses
  `assemble`'s own source and compares the keyword set against `dataclasses.fields(Params)` —
  passes **unedited**. That test exists to catch a thirteenth `Params` group; this phase adds none.

**The churn consequence of `Scenario.motor` being required, grepped not assumed:** every
`Scenario(...)` construction in the tree is keyword-only — five modules under `configs/scenarios/`
plus six call sites in `tests/test_config_pieces.py` — so inserting `motor` after `rocket` cannot
break a positional caller, and the edit is one added keyword per site.

---

## 32.3 Mass composition — `sim/mass.py`, and the bit-for-bit reduction

### 32.3.1 The findings this section rests on

Everything below was read from this tree or measured in this interpreter. These are the facts that
decide the design, and they are what a reviewer should re-check first.

**F1 — today's mass model lives in exactly one place, as three private helpers in
`sim/dynamics.py`.** `_propellant_mass(m, p)` (line 132), `_cog_position(m_p, p)` (143),
`_moment_of_inertia(m_p, l_B, p)` (152), gated by `p.weight.m_d is None` at line 257. `Weight` is
the **only one of the twelve `Params` groups with no owning `sim/` module** — the §28.3 house rule
is "one group per module that owns a dispatch", and `weight`'s dispatch is three helpers hidden
inside the EOM module. That is the genuine shallow spot this phase deepens (D-62). Note also that
`configs/rockets/_TEMPLATE_rocket.py:40` *already* tells the user the mass model lives in
"`sim/mass.py`" — a file that does not exist. The template is right and the tree is wrong.

**F2 — the two-body composition reduces *exactly* onto today's two-lumped model, because the two
dry bodies do not move relative to each other.** Write the vehicle as three rigid lumps: airframe
(`m_a`, `l_a`, `I_a`), motor casing (`m_c`, `l_c`, `I_c`) and propellant (`m_p(t)`, `l_p`,
`I_p(t)`). The first two are **static** — bolted together, neither moves during the burn — so they
combine once, at assembly time, into one dry assembly

```
M_d = m_a + m_c
L_d = (m_a*l_a + m_c*l_c) / M_d
I_D = I_a + m_a*(L_d - l_a)^2 + I_c + m_c*(L_d - l_c)^2
```

and the remaining time dependence is a *two*-lump problem — dry assembly plus shrinking propellant —
which is `main.tex` §`sec:mass` verbatim with `(m_d, l_d, I_d) := (M_d, L_d, I_D)`:

```
l_B(t) = (M_d*L_d + m_p(t)*l_p) / (M_d + m_p(t))                             == _cog_position
I(t)   = I_D + M_d*(l_B-L_d)^2 + I_p(t) + m_p(t)*(l_B-l_p)^2                 == _moment_of_inertia
```

So "it is not purely additive once there are two separately-moving centroids" is true in general and
**not the situation here**: there is one moving centroid (the propellant's, and even that is held
fixed by the current placeholder), and the composition is therefore a *static* pre-computation, not
a per-RHS-call one. This is the single most important result in the document.

**F3 — measured: a `sum()`-based generic `combine()` is NOT bit-for-bit identical to today's
written-out expression, by one ULP.** With realistic numbers (`m_d=1.1, l_d=0.62, I_d=0.080,
m_p=0.585, l_p=0.78`, `I_p=(I_d/m_d)*m_p`):

| quantity | today's expression | generic `sum()` form | bitwise equal |
|---|---|---|---|
| `l_B` | `0.6755489614243324` | `0.6755489614243324` | **yes** |
| `I`   | `0.13232207175613706` | `0.13232207175613703` | **no** — rel. diff `2.1e-16` |

The cause is association order, not arithmetic: today's line is
`((I_d + m_d*d_d^2) + I_p) + m_p*d_p^2`, while `sum(k.I + k.m*d^2 for k in lumps)` groups as
`(I_d + m_d*d_d^2) + (I_p + m_p*d_p^2)`, and IEEE addition is not associative. **Therefore the
re-homed `moment_of_inertia` keeps its expression verbatim and is deliberately NOT implemented in
terms of `combine()`** — the two compute the same mathematics and are pinned to agree to ~1e-15
relative, never to agree bitwise (§32.11 Step 75). Anyone who "tidies" one into the other will fail
the Step-75 bit-for-bit gate, which is the point of writing this down.

**F4 — measured: a one-lump `combine()` is not an exact identity either.** `(m*l)/m != l` for **5
of 56** realistic `(m, l)` pairs drawn from this repo's own numbers — e.g. `m=1.5, l=0.4` gives
`0.4000000000000001`; `m=1.685, l=0.075` gives `0.07499999999999998`. So the pass-through path
(`mass_model="none"`, which every existing seed uses) must be an **explicit early return**, not
`combine(one_lump)`. With the early return, all five seeds are bit-for-bit by construction rather
than by luck.

**F5 — measured on the real motor file.** `data/motors/Cesaroni_2060K570-17A.eng`, header
`K570  54.0 488.00 7-17 0.99000 1.68500 CTI`, ten `(t, F)` rows from `(0.04, 892.67)` to
`(3.59, 0.00)`:

| reading of `t < t[0]` | total impulse | vs the designation's "2060" |
|---|---|---|
| prepend `(0.0, 0.0)` — **recommended** | **2062.223 N·s** | **+0.108 %** |
| today's `np.interp(left=thrusts[0])` hold | 2080.076 N·s | +0.975 % |
| trapezoid over the listed rows only | 2044.370 N·s | −0.759 % |

`m_f = m_total − m_prop = 1.68500 − 0.99000 = 0.69500 kg`, and `I_sp_eff = 2062.223/(0.99 × 9.80665)
= **212.4123 s**`. The designation's own impulse figure is an independent check on the parser that
costs nothing to run, and it picks the prepend (D-64).

**F6 — today's `l_d`/`l_p` are only ever read as *differences*, so pinning them to nose-tip
absolute stations changes nothing.** `_cog_position` forms `l_B` from `l_d`/`l_p` and
`_moment_of_inertia` reads only `(l_B − l_d)` and `(l_B − l_p)`; `l_B(t)` is **not** fed back into
`Lengths.l1`/`l2` (`sim/dynamics.py`'s Step-36 note says so explicitly, and `aB` keeps the constant
`p.lengths.l1`). Every consumer is translation-invariant. So §32.5's decision to define every
station as "positive, aft of the nose tip `A`" is a *documentation* fix for an ambiguity that could
never have bitten, and it costs no existing config anything.

**F7 — `sim/thrust_curve.py` already dispatches on a filename, and the extension is already part of
it.** `_load_motor_curve(curve_name)` joins `data/motors/` + `curve_name` where `curve_name` is
`"placeholder.csv"` — extension included, in the config literal. So extension dispatch needs no new
field and no new convention; `Thrust.motor_curve` is already "the file", not "the stem".

### 32.3.2 `sim/mass.py` — the module

**New module, `sim/mass.py`** (D-62): the one home for the mass model, closing F1's gap and
honouring the forward reference `_TEMPLATE_rocket.py` already makes.

```python
"""The mass model: m(t), l_B(t), I(t) -- the one place the
two-lumped-mass model and the rigid-lump composition live
(docs/architecture-32-motor-separation.md SS32.3; main.tex SSsec:mass).

Step 75 is a PURE MOVE of `sim/dynamics.py`'s `_propellant_mass`,
`_cog_position` and `_moment_of_inertia`, expressions unchanged
character for character -- see F3: an equivalent-but-reassociated form
differs by one ULP, and `sim/dynamics.py`'s path must stay bit-for-bit.
`combine()` below computes the same mathematics for the ASSEMBLY-time
composition (once per config, at import) and is deliberately NOT what
`moment_of_inertia` is implemented in terms of.
"""

@dataclasses.dataclass(frozen=True)
class Lump:
    """One rigid body. `l` is a station: POSITIVE, aft of the reference
    point (the nose tip A for airframe/vehicle lumps, the motor's
    forward face for motor-local lumps). `I` is about its OWN centroid."""
    m: float               # kg
    l: float               # m
    I: float = 0.0         # kg*m^2


def combine(*lumps: Lump) -> Lump:
    """Mass-weighted centroid + parallel axis, exact for any number of
    rigid lumps whose positions are fixed relative to one another
    (SS32.3.1 F2). Assembly-time only -- NOT bit-for-bit equal to
    `moment_of_inertia` below (F3), and not an exact identity for a
    single lump (F4), so callers that need pass-through must say so
    explicitly rather than calling this with one argument."""
    M = math.fsum(k.m for k in lumps)
    if M == 0.0:
        return Lump(m=0.0, l=0.0, I=0.0)
    l = math.fsum(k.m * k.l for k in lumps) / M
    I = math.fsum(k.I + k.m * (l - k.l) ** 2 for k in lumps)
    return Lump(m=M, l=l, I=I)


# --- moved verbatim from sim/dynamics.py (Step 75) -------------------
def propellant_mass(m: float, p) -> float:        ...   # was _propellant_mass
def cog_position(m_p: float, p) -> float:         ...   # was _cog_position
def moment_of_inertia(m_p: float, l_B: float, p) -> float:  ...   # was _moment_of_inertia


# --- new, for the endpoint mass model (SS32.3.4) ---------------------
def total_impulse(times, thrusts) -> float:
    """J = integral of T_ref dt over the curve AS THE SIMULATOR SEES IT
    (SS32.4): trapezoid over the loaded points, which already include the
    (0,0) prepend `sim/motor_file.py` applies to RASP records (F5)."""
    return float(np.trapezoid(thrusts, times))


def isp_from_impulse(J: float, m_prop: float, g0: float) -> float:
    """I_sp_eff = J / (m_prop * g0) -- the specific impulse that makes
    today's `dm/dt = -T_ref(t)/(I_sp*g0)` consume exactly `m_prop` over
    exactly this curve (SS32.3.4, D-59)."""
    return J / (m_prop * g0)


def uniform_cylinder_I(m: float, length: float, diameter: float) -> float:
    """Transverse MOI of a uniform solid cylinder about its own centroid,
    `m*(3r^2 + L^2)/12` -- the default motor casing/grain inertia when
    nothing better is known (D-67). B24 replaces this with real grain
    geometry; it is an over-estimate for a thin-walled casing and an
    under-estimate for a cored grain, both by O(r^2/L^2)."""
    r = 0.5 * diameter
    return m * (3.0 * r * r + length * length) / 12.0
```

`math.fsum` rather than `sum` inside `combine` is a free upgrade precisely *because* `combine` is
not on a bit-for-bit path: it removes the association question from the assembly-time number
entirely, so the composed `Weight` is the exactly-rounded result and a future reordering of the lump
list cannot move it by an ULP.

`sim/dynamics.py`'s change is then two lines: `from sim import mass` and the three call sites
becoming `mass.propellant_mass(...)` / `mass.cog_position(...)` / `mass.moment_of_inertia(...)`.
No expression, no gate and no comment in the EOM is touched.

### 32.3.3 `_weight_from_pieces` — the assembly-time composition

Lives in **`configs/schema.py`**, beside `assemble`, not in `sim/mass.py`: it is dataclass glue that
knows about `Rocket`/`Motor`/`Airframe`, and `sim/` must not import `configs/`. All the arithmetic
is `sim.mass`'s; this function is the translation layer.

```python
def _weight_from_pieces(rocket: Rocket, motor: Motor, g0: float) -> Weight:
    """SS32.3. Compose the airframe lump and the motor's own lumps into
    the one `Params.weight` group the engine consumes (D-56, D-57).

    Four cases, in this order:

    (0) `motor.mass_model == "none"` -- PASS-THROUGH, and an explicit
        early return rather than `combine()` of one lump (F4): the
        airframe's own numbers ARE the vehicle's, the mass model stays
        off, and every pre-Step-80 config comes out bit-for-bit.

            return Weight(m=rocket.airframe.m, I=rocket.airframe.I)

    (1) resolve the motor's own numbers: header fields from
        `sim.motor_file.load(motor.thrust.motor_curve)` for every field
        left `None` (D-67), then the uniform-cylinder defaults for any
        geometry still missing.

    (2) place the motor: `l_fwd = sections.l_motor_fwd` if given, else
        `sections.l_motor_aft - length`. Motor-local stations become
        nose-tip stations by adding `l_fwd` -- one addition, and the sign
        convention never changes (SS32.5).

    (3) compose, and emit the five mass-model fields:

            dry  = mass.combine(airframe_lump, casing_lump)   # static, F2
            I_sp = motor.I_sp                     if mass_model == "isp"
                   else mass.isp_from_impulse(J, m_prop, g0)  # "endpoints", D-59
            wet  = mass.combine(dry, prop_lump)    # t = 0, for `m` and `I`

            return Weight(m=wet.m, I=wet.I,
                          m_d=dry.m, l_d=dry.l, I_d=dry.I,
                          l_p=prop_lump.l, I_sp=I_sp,
                          I_p_spec=prop_lump.I / prop_lump.m)   # Step 77
    """
```

Six properties of this function, each one load-bearing:

1. **Pass-through is bit-for-bit, by construction.** Case (0) returns exactly the two literals the
   rocket module carries. The four exact-equality pins in `tests/test_configs.py` are therefore the
   migration's proof, exactly as they were at Step 73.
2. **`m` and `I` are the composed values at `t = 0`**, i.e. the loaded vehicle — which is what
   `Weight.m`/`I` have always meant (`sim/params.py:48`, "initial (wet) mass"). The mass model's
   `m_d`/`l_d`/`I_d` are the composed **dry assembly** (airframe + casing), which is what today's
   hand-entered `m_d`/`l_d`/`I_d` have always meant too. **The reinterpretation is a change of
   *provenance*, not of semantics** — the fields keep their meanings, they just stop being typed in
   by hand.
3. **`l_p` is the propellant centroid as a nose-tip station**, consistent with `l_d`, and F6 proves
   the absolute frame is safe because only differences are read.
4. **The composition runs once per scenario, at import.** Five `combine` calls and (for
   `"endpoints"`) one cached motor-file parse per scenario module — the same order of cost as the
   13 frozen-dataclass constructions §31.4 already accepted.
5. **It touches the filesystem only under `mass_model != "none"`** (D-70). Every existing seed stays
   on the `"none"` path, so the whole `configs/` package import remains filesystem-free and
   `python -c "import configs"` cannot newly fail because a data file is missing.
6. **Its two preconditions raise, with a message naming the field.** `airframe.l is None` with a
   mass-modelled motor, and neither/both of `l_motor_fwd`/`l_motor_aft`, are the two states the
   arithmetic cannot default. This is not the input validation `architecture.md` §7 declines to own:
   `None + float` is already a `TypeError`, and all that is being added is a message that says which
   field to go and fill in.

### 32.3.4 The `m(t)` models, and why the endpoint model needs no new code

**`mass_model="isp"`** — unchanged, and still the primary model: `dm/dt = −T_ref(t)/(I_sp·g0)`,
`sim/dynamics.py:266`, `main.tex` §`sec:mass`. The motor supplies `I_sp`. Nothing about this path
changes except where the number is typed.

**`mass_model="endpoints"`** — the user's "two endpoint masses, no `I_sp`" case, whose natural source
is precisely the RASP header: `m_0 = m_total`, `m_f = m_total − m_prop`. The question the user left
open is how `m(t)` is shaped between them. Three candidates:

| shaping | `dm/dt` | behaviour |
|---|---|---|
| linear in **time** over the burn | constant `−(m_0−m_f)/t_burn` | mass falls at the same rate through a thrust spike and a tail-off; an `m_p` that is still 40 % full when a punchy curve is 90 % done |
| linear in **cumulative impulse** | `−(m_0−m_f)·T(t)/J` | mass falls in proportion to the thrust actually being produced; `m_p` hits zero exactly when the curve runs out |
| linear in burn-*fraction* of a nominal `t_burn` | as above but normalised on time | same defect as the first, with extra machinery |

The second is the physically honest one for any non-constant curve, and — the result that settles it
— **it is algebraically identical to the `"isp"` model**:

```
dm/dt = -(m_0 - m_f) * T(t) / J          [impulse-fraction shaping]
      = -T(t) / (J / (m_0 - m_f))
      = -T(t) / (I_sp_eff * g0),     with   I_sp_eff = J / (m_prop * g0)
```

So the "endpoints" model is implemented by **computing one constant at assembly time and writing it
into `Weight.I_sp`**. There is no second `dm/dt` branch, no new state, no new dispatch in
`sim/dynamics.py`, and the two models cannot drift apart because there is only one of them in the
engine. It also makes the burnout mass *exactly* right rather than approximately:
`∫ T/(I_sp_eff·g0) dt` over the whole curve is `J/(I_sp_eff·g0) = m_prop` identically, so
`m(t_end) = m_f` to solver tolerance — which is a testable assertion, and §32.11 Step 81 makes it
one.

Measured on the real file (F5): `J = 2062.223 N·s`, `m_prop = 0.990 kg` → `I_sp_eff = 212.41 s`, a
thoroughly plausible figure for a Cesaroni composite, which is itself a sanity check on both the
parser and the formula.

**What `J` must be integrated over** is the curve *as the simulator sees it*, not as the file lists
it — because `sim/thrust_curve.thrust` holds the first value for `t < t[0]`. F5 measures the
difference at 0.9 % of total impulse, which would land directly on `I_sp_eff` and hence on burnout
mass. D-64's `(0.0, 0.0)` prepend removes the discrepancy at the source: after the prepend, "as
listed" and "as simulated" are the same curve, and `total_impulse` is a plain trapezoid.

### 32.3.5 `l_COG(t)` and `I(t)` — keeping the physical model, accepting the user's inputs

**Recommendation (D-60): keep the existing mass-weighted-centroid + parallel-axis model, re-homed,
and accept the user's endpoint numbers as an alternative *input parameterisation* by exact
inversion.** The user asked for "for now linearly with `l_COG_0`/`l_COG_f` and `I_0`/`I_f`" and
invited a better proposal; this is better in the one way that matters and *also* lets them type what
they wanted to type.

The existing model is linear in `m_p(t)`, not in `t`. That is the whole difference, and it is not
cosmetic: with a punchy curve, time-linear CoG travel puts the CoG at mid-travel while 85 % of the
propellant is already gone, which moves the static margin — the one quantity the whole rotational
model is sensitive to — in the wrong direction at the wrong moment. The `m_p`-linear model is right
for *every* curve shape with no extra input, is already written, and is already covered by
`tests/test_dynamics.py`.

**The exact inversion.** The user's endpoint inputs are not a different model; they are a different
chart on the same model, and the change of chart is algebraic. For the motor's own two lumps
(casing `m_c`, `l_c`; propellant `m_p0`, `l_prop`) with motor totals `m_0 = m_c + m_p0`,
`m_f = m_c`:

```
l_cog_f = l_c                                  (at burnout, only the casing remains)
l_cog_0 = (m_c*l_c + m_p0*l_prop) / m_0
     =>  l_prop = (m_0*l_cog_0 - m_f*l_cog_f) / (m_0 - m_f)       [exact]

I_f = I_c
I_0 = I_c + m_c*(l_cog_0 - l_c)^2 + I_prop0 + m_p0*(l_cog_0 - l_prop)^2
     =>  I_prop0 = I_0 - I_f - m_f*(l_cog_0 - l_cog_f)^2 - m_p0*(l_cog_0 - l_prop)^2   [exact]
```

So `Motor(l_cog_0=…, l_cog_f=…, I_0=…, I_f=…)` is converted, once, at assembly, into
`(l_c, l_prop, I_c, I_prop0)`, and from there everything proceeds through the single physical model.
The user gets their requested inputs; the simulation gets `m_p`-linear interpolation rather than
time-linear; and there is exactly one `l_COG(t)`/`I(t)` formula in the codebase, not two.

**One honest consequence: the `I_prop0` route needs one new `sim/params.py` field** (D-61).
Today `_moment_of_inertia` hardcodes the propellant's own inertia as
`I_p = (I_d/m_d)·m_p` — `main.tex`'s own `\todo` placeholder, "uniform density, fixed shape",
borrowing the *dry assembly's* radius of gyration for the propellant. Once the composition knows the
motor's real length and diameter, that borrowing is needlessly wrong: a 0.49 m motor grain and a
~1 m airframe do not share a radius of gyration. The fix is one field and one branch:

```python
# sim/params.py, Weight -- Step 77
I_p_spec: Optional[float] = None   # propellant MOI per unit mass about its own centroid [m^2]
                                   # (radius of gyration squared). None -> (I_d/m_d), the
                                   # pre-Step-77 placeholder, bit-for-bit.

# sim/mass.py, moment_of_inertia -- Step 77
I_p = (p.weight.I_d / p.weight.m_d) * m_p if p.weight.I_p_spec is None \
      else p.weight.I_p_spec * m_p
```

`None` is the default, so every existing config and every existing test is bit-for-bit; the field is
*specific* (per unit mass, m²) rather than absolute so that no second field (`m_p0`) is needed to
scale it; and it keeps `I_p ∝ m_p(t)`, which is the same shape `main.tex` states — only the constant
becomes the propellant's own instead of the structure's.

**Rejected, recorded, not implemented (D-60):** literally time-linear `l_COG(t)`/`I(t)`. It needs a
burn duration that the curve already implies (so it introduces a second, derivable source of truth),
it disagrees with `main.tex` §`sec:mass`, and it is *less* accurate for every curve this repo owns.
If the user wants it after reading this, it is a third `mass_model` value and ~15 lines — additive,
and nothing here forecloses it.

---

## 32.4 The file readers — `.csv`, `.eng`, `.rasp`

### What `.rasp` means, and why it is one grammar and not two

RASP is Bruce Lohr's *Rocket Altitude Simulation Program*, and the "RASP format" is the `.eng`
format — the same header-plus-`t F`-rows record. What distinguished the historical artifact was not
the grammar but the **cardinality**: the motor database shipped as a single file (`rasp.eng`) holding
*many* records concatenated, each preceded by its own `;` comment block. Both readings of the user's
`.rasp` are therefore defensible, and the resolution is that **they are the same reading at
different sizes**: a one-record file is a library of one.

**Recommendation (D-63): one RASP parser that always returns a *list* of records; `.eng` and
`.rasp` both go to it; a record is selected by an optional `#designation` fragment on the existing
`motor_curve` string.**

```
thrust.motor_curve = "Cesaroni_2060K570-17A.eng"     # sole record -> no fragment needed
thrust.motor_curve = "rasp.rasp#K570"                # one record out of a library
thrust.motor_curve = "placeholder.csv"               # unchanged, CSV path
```

Why the fragment rather than a new `Thrust` field: `Thrust.motor_curve` is **already** "the file,
extension included" (F7), so this adds no `Params` field, no new convention and no caller edit; it
is one `str.partition("#")`; and — the capability that makes it worth doing — **App 3 can sweep
records inside one library file with no new machinery at all**, because `MotorEntry.overrides`
already sets `thrust.motor_curve` per entry. A multi-record file with no fragment, or a fragment
naming a designation that is not present, raises a `KeyError` listing every designation in the file —
the same "the one error message a typo has to produce" shape all four registries already use.

### Module split

**Recommendation (D-65): a new `sim/motor_file.py` owns formats and metadata;
`sim/thrust_curve.py` keeps its force-model seam and delegates.**

`sim/thrust_curve.py`'s public surface is `thrust(t, s, p) -> float`, deliberately shaped like every
other force model (its own docstring says so), and it depends on `sim.atmosphere` for the pressure
correction. File grammars and header metadata are a different concern with a different consumer:
`configs/schema.py` needs `m_prop`/`m_total`/`length`/`diameter` at **assembly** time and must not
import a force model (and must not drag `sim.atmosphere` into the config import graph) to get them.
Splitting gives each module one job and one reason to change.

```python
# sim/motor_file.py

@dataclasses.dataclass(frozen=True)
class MotorRecord:
    """One motor's curve plus whatever its file told us about it. Every
    metadata field is `None` for a format that does not carry it (every
    `.csv`), never 0.0 -- "unknown" and "zero" are different answers and
    the mass model must be able to tell them apart (SS32.3.3)."""
    designation:  str                  # "K570", or the filename stem for a .csv
    times:        np.ndarray           # s,  ascending, de-duplicated
    thrusts:      np.ndarray           # N
    m_prop:       float | None = None  # kg   <- RASP header field 5
    m_total:      float | None = None  # kg   <- RASP header field 6
    diameter:     float | None = None  # m    <- RASP header field 2 (mm in file)
    length:       float | None = None  # m    <- RASP header field 3 (mm in file)
    delays:       str = ""             #      <- RASP header field 4, free text, never parsed
    manufacturer: str = ""             #      <- RASP header field 7
    source:       str = ""             # the file it came from, for error messages

    @property
    def total_impulse(self) -> float:  # N*s -- SS32.3.4's J
        return float(np.trapezoid(self.thrusts, self.times))


@functools.lru_cache(maxsize=None)
def records(filename: str) -> tuple[MotorRecord, ...]:
    """Every record in `data/motors/<filename>`, dispatched on extension:
    `.csv` -> the two-column reader (one record, no metadata);
    `.eng` / `.rasp` / anything else -> the RASP reader (N records)."""


@functools.lru_cache(maxsize=None)
def load(spec: str) -> MotorRecord:
    """`"<filename>[#designation]"` -> one record. No fragment and one
    record in the file -> that record. No fragment and several -> KeyError
    listing every designation. Unknown designation -> the same KeyError."""
```

### The RASP grammar, as implemented

Stated precisely, because the loose descriptions in circulation disagree with each other:

- Lines whose first non-blank character is `;` are comments. **Discarded**, with one exception worth
  keeping: the comment block above a record is the provenance a user wrote, so it is concatenated
  into nothing today and is a cheap future addition to `MotorRecord.notes` if wanted.
- A **header line** is a non-comment line whose first whitespace-separated token does not parse as a
  float. Seven fields:
  `designation  diameter_mm  length_mm  delays  m_prop_kg  m_total_kg  manufacturer`.
  `delays` is free text (`"7-17"`, `"0"`, `"P"`) and is **never parsed** — it is a list of available
  ejection delays and has no bearing on anything this simulator computes.
- Subsequent non-comment lines are `time thrust` pairs, whitespace-separated. A line with more than
  two tokens keeps the first two (the same tolerance the CSV reader already has).
- A record ends at the next header line, a blank line followed by a header line, or EOF. A trailing
  `;` is a comment and therefore already ignored. **Practical consequence: blank lines are not
  load-bearing** — the "next non-float-leading line starts a new record" rule parses both the
  blank-line-delimited and the run-together conventions, which is why it is the rule chosen.
- `diameter_mm` and `length_mm` are converted to metres at the boundary (`/1000.0`), so nothing
  downstream ever handles millimetres. This matches `sim/params.py`'s "strict SI; degrees only at
  the edges" rule.
- **If `times[0] > 0.0`, an explicit `(0.0, 0.0)` point is prepended** (D-64, F5). A RASP file's
  first row is the first *measured* point after ignition, not a pre-ignition hold; holding it from
  `t = 0` both fires the motor before the data says it ignites and manufactures 0.9 % of impulse that
  the motor never produced. `.eng` files do not load at all today, so this costs no existing run, and
  F5's agreement with the manufacturer's own designation (0.108 % against 0.975 %) is the evidence.
  **`.csv` loading is NOT changed** — the prepend is applied by the RASP reader only, so every
  existing config stays bit-for-bit.

### How `thrust_curve.py` changes, and what stays identical

```python
@functools.lru_cache(maxsize=None)
def _load_motor_curve(curve_name: str) -> tuple[np.ndarray, np.ndarray]:
    """Step 76: delegates to `sim.motor_file.load`, which now owns every
    format. For a `.csv` this is the same sort/de-duplicate/float path as
    before, moved -- the arrays handed to `np.interp` are bit-identical."""
    rec = motor_file.load(curve_name)
    return rec.times, rec.thrusts
```

`thrust(t, s, p)` itself is **not edited at all**: same `np.interp` with `left=thrusts[0],
right=0.0`, same `A_e == 0.0` short-circuit, same "only correct while `T_ref > 0`" rule. The
sort-and-de-duplicate logic moves into the CSV reader inside `motor_file.py` and keeps `np.argsort`
+ `np.unique(return_index=True)` verbatim, so `tests/test_thrust_curve.py` passes unedited.

### How `m_0`/`m_f` reach the mass model

One path, no second mechanism: `configs/schema.py::_weight_from_pieces` calls
`sim.motor_file.load(motor.thrust.motor_curve)` and fills every `Motor` field left `None` from the
record (D-67). So the three-line config in §32.3.3's case (1) is complete:

```python
MOTOR = Motor(
    name="cti_k570",
    thrust=Thrust(motor_curve="Cesaroni_2060K570-17A.eng"),
    mass_model="endpoints",     # m_0 = 1.685 kg, m_f = 0.695 kg, I_sp_eff = 212.41 s -- all from the header
)
```

and the only hand-entered motor numbers left in the whole project are the ones no file format
carries: the grain's centroid and inertia, which default to a uniform cylinder (D-67) until B24.

---

## 32.5 Rocket sections, and the sign convention stated once

### The convention, restated verbatim and unchanged

Every length in `configs/` is **input as a positive number**: a distance measured **aft of the nose
tip `A`**, along the body axis. The **negative sign is applied internally, exactly once**, at the
point where a station becomes a body-frame vector — because `x̂_r` points toward the nose
(`rocket-2d.tex` §Geometry):

```
AB = -l_B·x̂_r - u_B·ẑ_r          AC = -l_C·x̂_r - u_C·ẑ_r          AD = -l_D·x̂_r
```

In code that single place is `sim/dynamics.py:329-330`, and this phase does not touch it:

```python
aA = np.array([-l1_aero, p.lengths.u_B])                                        # CoP position (BD)
aB = np.array([-(p.lengths.l1 + p.lengths.l2), p.lengths.u_B - p.lengths.u_C])  # thrust point (BC)
```

Step 25 (the `l1` sign-convention resolution) and Step 43 (the `u_B`/`u_C` lateral offsets) are
both closed and both stay closed: **no `Lengths` field changes meaning, no sign moves, and
`sim/dynamics.py`/`sim/forces.py` are not edited by any ticket in §32.11 except Step 75's
three-call-site import swap.** The new `Sections` and `Airframe.l` extend the *same* convention to
absolute stations — positive aft of `A`, negative sign applied where it becomes a vector — and
`Motor`'s motor-local stations use the identical sense from the motor's forward face, so there is
exactly one rule in the project and no conversion to get wrong.

For the record, the relation between the absolute stations of `rocket-2d.tex` and the relative
`Lengths` fields of `sim/params.py`, read off the code:

| LaTeX | meaning | code |
|---|---|---|
| `l_B` | CoG station from `A` | `_cog_position`'s return value when the mass model is on; otherwise implicit |
| `l_D` | CoP station from `A` | not stored; `l1 = l_D − l_B` is |
| `l_C` | thrust-point station from `A` | not stored; `l1 + l2 = l_C − l_B` is |

So `Lengths.l1` is the CoP-to-CoG arm and `Lengths.l2` is the **CoP-to-thrust-point** arm
(`l_C − l_D`) — which is what `configs/rockets/_TEMPLATE_rocket.py:46` and
`sim/dynamics.py`'s `aB = aA + AB` comment both say. Worth noting for §32.8's documentation pass:
**`sim/params.py:69`'s comment on `l2` ("CoG -> thrust point(C) offset along the axis") is stale and
contradicts the code**, which uses `l1 + l2` for the CoG-to-`C` arm. A one-line comment fix, no
behaviour change; it is in Step 82's boundaries so that the templates and the group they document
cannot disagree.

### Do `l1`/`l2` become derived?

**Recommendation (D-68): no. `Lengths.l1`/`l2` stay authoritative and hand-entered; `Sections` is
additive and informational, except for the one station that places the motor.** Three reasons, in
order of weight:

1. **Deriving them would change every existing run's numbers.** `l1 = l_D − l_B` needs `l_D`, which
   no config carries and which for the `"table"` aero model is already a function of `(α, M)`
   (`sim/aero.py`'s `AeroCoeffs.l1`). Reconstructing `l1` from sections would therefore either
   duplicate the table's own output or contradict it — and `sim/aero.py` was restructured at Step 55
   *specifically* to stop two selectors disagreeing about the moment arm.
2. **It would invent physics `main.tex` has not stated.** With the mass model on, `l_B` travels, so
   derived arms would become `l1(t)`/`l2(t)` — which is exactly the question `architecture.md` §19
   flags as open ("still blocked on a `main.tex` update … `main.tex`'s own §Current assumptions still
   lists `l_1`, `l_2` as held fixed") and which `sim/dynamics.py`'s Step-36 note deliberately refuses
   to answer. A config-layer refactor is the wrong place to answer it.
3. **The phase's gate is bit-for-bit.** Any derivation that did not reproduce `l1=0.3, l2=0.4` for
   `demo_75mm` to the last bit would fail the four exact-equality pins, and one that did would be a
   more complicated way of writing the same two literals.

**Explicit confirmation of the consequence:** nothing in `sim/dynamics.py` or `sim/forces.py` needs
to change for the section work. `Sections` is read by exactly one function
(`configs/schema.py::_weight_from_pieces`, for `l_motor_fwd`/`l_motor_aft`) and by no `sim/` module
at all. `tests/test_config_pieces.py`'s `Params`-field-set pin is unaffected because `Sections` is a
`configs`-level type and adds no `Params` group.

**The honest residual, recorded as a risk and a backlog candidate:** `Sections` and `Lengths` can now
disagree — a user can state `l_nose`/`L_total`/`l_motor_fwd` that are geometrically incompatible with
`l1`/`l2`, and nothing cross-checks them, exactly as nothing cross-checked `s0.theta` against
`site.rail_angle_deg` before D-51. The difference is that there is no structural fix available here
(the §19 physics is open), so the mitigation is notes-and-documentation: each template says in one
line that `l1`/`l2` are the authoritative arms and `Sections` is descriptive. Deriving `l1`/`l2`
from stations — and with them the §19 `l1(t)`/`l2(t)` question — is listed in §32.13.

---

## 32.6 Aero / CoP — confirmation, not redesign

**Confirmed: all three aero models are implemented, tested, and CoP travel among them is already a
solved problem. Nothing in this phase changes `sim/aero.py`, `Params.Aero` or any aero number.**
`sim/aero.py` carries an explicit three-way dispatch dict,
`_AERO_MODELS = {"constant": _constant_coeffs, "linearized": _linearized_coeffs, "table":
_table_coeffs}`, behind one public seam `coefficients(t, y, p, flow, hold) -> AeroCoeffs`, where
`AeroCoeffs` bundles `C_x`, `C_z`, `C_m`, `C_mq` **and `l1`** — the CoP-to-CoG distance — so the
centre of pressure is returned by the same call as the coefficients it belongs with. `Params.Aero`
(`sim/params.py:73-91`) carries `model: str = "constant"  # constant | linearized | table` plus the
shared `S`/`d_ref`/`l_ref`, the `"constant"` triple `C_x`/`C_z`/`C_m`, the `"linearized"` triple
`C_A0`/`C_N_alpha`/`C_m_alpha`, the `"table"` filename, and `c_mq` for all three. The `"table"`
model reads `data/aero/<table>.csv` with columns `alpha_deg,M,C_A,C_N,C_m,l1_m,c_mq`, which is where
**CoP travel** lives: `l1` becomes a genuine function of `(α, M)` under `"table"` and falls back to
the constant `Params.lengths.l1` under the other two (Step 25, then Step 55, which closed the leak
that let a table drive the moment arm while a different model drove the force). The five
pre-Step-55 per-coefficient functions `C_A`/`C_N`/`C_m`/`C_mq`/`cop_l1` survive as thin wrappers over
the same dispatch, so no caller was stranded. **Naming note for §32.8's documentation pass only:**
the user calls the third model "data"; the code calls it **`"table"`**, in `Params.Aero.model`, in
the dispatch key, in the filename field and in ten test modules. No rename is warranted — it would
touch `sim/aero.py`, `sim/params.py`, every config and ~10 test files to buy a synonym — so the
templates and the documentation should say `table` and, once, parenthetically, "the data-table
model".

---

## 32.7 The two backlog TODOs (B24, B25)

Next free backlog IDs, continuing `docs/roadmap.md`'s table (last used: **B23**, opened by the §30
design and blocked on B17). Both are the user's own stated TODOs, both are explicitly **not**
implemented in this phase, and both now have a structural landing spot rather than requiring a
rewrite to start.

### B24 — Motor mass/CoG/MOI by integrating real grain geometry  *(opened by the §32 design)*
`Motor`'s mass history is the two-lumped placeholder: a casing lump plus a propellant lump whose
centroid `l_prop` is **held fixed** and whose own inertia is `I_p ∝ m_p(t)` with a constant specific
value (`Weight.I_p_spec`, Step 77). `main.tex` §`sec:mass` already says at length what the honest
model is and why this is a placeholder: solid grains come in families (cylindrical/BATES,
tubular/annular, end-burning, star/finocyl), each giving a different burn-area-versus-web-thickness
relation `A_b(w)`; combined with a regression rate `ẇ = r_b = a·pⁿ` (Saint-Robert), the instantaneous
propellant volume, its centroid `l_p(t)` and its own inertia `I_p(t)` all follow by direct
integration over the receding grain. An **end-burning** grain is the case that breaks the placeholder
hardest — its centroid marches along the grain while a radially-burning one barely moves — and it is
also the easiest family to implement first. Inputs needed that no file format carries: grain family,
bore and outer diameter, grain length, inhibition, and for star grains the point count. Entry point:
`Motor` gains a `grain: Grain | None` field and `sim/mass.py` gains the integration; everything
downstream of `Weight` is unchanged, because the composition already reduces to whatever
`(m_p(t), l_p(t), I_p(t))` is handed to it (§32.3.1 F2). Supersedes the data half of **B15**, whose
"per-motor propellant mass and `I_sp`" half this phase closes.

### B25 — Rocket dry mass/CoG/MOI by integrating a per-section mass distribution  *(opened by the §32 design)*
`Airframe` is one lump: two measured numbers and a CoG station, hand-entered. The honest version is a
**bill of materials** — nose cone, each body tube, couplers, bulkheads, fin can and fins, recovery
hardware, avionics bay, ballast — each with its own mass and its own station, composed by exactly the
`sim.mass.combine()` this phase introduces, which is already an N-lump function for this reason.
`Sections` is the landing spot: `tubes: tuple[tuple[str, float], ...]` becomes
`tuple[Section, ...]` with `m` and `I` per section, and `Airframe.m`/`.I`/`.l` become **derived**
exactly as `Params.weight` becomes derived in this phase — the same pattern, one level further in.
The natural interchange is an OpenRocket-style component tree (`.ork` is a zipped XML component list
with masses and positions), so this is also the place an OpenRocket importer would land. Two
capabilities fall out for free once it exists: `Lengths.l1`/`l2` become derivable from the airframe
side (D-68's deferred half, and with it the `architecture.md` §19 `l1(t)`/`l2(t)` question), and App
5's mass axis stops being the "holds `weight.I` fixed" approximation **B22** names — B22 is this gap
seen from App 5's side, and the two should be resolved together.

---

## 32.8 Templates documentation convention

**Requirement (the user's point 9): every field in every config template documented with (a) REQ or
OPT, (b) its unit or its allowed choices, (c) a one-line description.** Six template files are in
scope — `configs/rockets/_TEMPLATE_rocket.py`, the new `configs/motors/_TEMPLATE_motor.py`,
`configs/sites/_TEMPLATE_site.py`, `configs/weather/_TEMPLATE_weather.py`,
`configs/scenarios/_TEMPLATE_scenario.py` — and the convention applies to the real seed pieces too
wherever they already carry comments.

**Recommendation (D-71): both forms — a tightened inline comment on every field, *and* a compact
per-field table at the end of each template's docstring.** They answer different questions and the
duplication is the cheapest part of the file to keep in sync (one table, 5-15 rows, in the same file
as the fields it describes).

### The inline convention, fixed

```python
field_name=value,   # REQ, <unit or choices> -- <one line, what it is and what happens if you leave it>
```

Three rules, so this is mechanically checkable rather than a matter of taste:

1. **`REQ` or `OPT` is the first token after `#`.** `REQ` means the dataclass has no default *or*
   the default is not usable (`Aero.S = 0.0` makes every aerodynamic force identically zero — that is
   a default, but it is not a *sane* default, so `S` is **REQ**). `OPT` means leaving it alone gives
   correct, intentional behaviour, and the description says what that behaviour is.
2. **The second token is the unit, or the choice set.** `kg`, `m`, `kg*m^2`, `s`, `m^2`, `N`, `deg`,
   `Pa`, `-` for dimensionless, `[-]` never. For a string field, the choices verbatim:
   `none | isp | endpoints`, `constant | linearized | table`, `apogee | timer`.
3. **One line, one sentence, present tense, no wrapping.** Where the consequence genuinely needs a
   paragraph (today's templates have several good ones — `demo_75mm`'s motor-curve judgment call,
   `_TEMPLATE_rocket.py`'s `C_z=C_m=0.0` note), that paragraph goes *above* the field as a block
   comment and the inline line still carries the three required parts.

A worked line, from the new motor template:

```python
mass_model="none",   # REQ, none | isp | endpoints -- "none" flies at constant mass (every field below inert)
m_prop=None,         # OPT, kg -- propellant mass; None reads it from the .eng/.rasp header, REQ for a .csv
I_sp=None,           # OPT, s  -- specific impulse; REQ when mass_model == "isp", ignored otherwise
l_prop=None,         # OPT, m  -- propellant centroid, motor-local, positive aft; None -> length/2
```

### The companion table

At the end of each template's module docstring, so `python -c "help(configs.motors._TEMPLATE_motor)"`
prints it and a reader can check for a field they have never noticed:

```
| field | REQ/OPT | unit / choices | default | what it does |
|---|---|---|---|---|
| name       | REQ | -                      | --        | registry key; must equal the filename |
| thrust     | REQ | Thrust group           | Thrust()  | the curve file, nozzle exit area, reference pressure |
| mass_model | REQ | none \| isp \| endpoints | "none"  | which m(t) model; "none" = constant mass |
...
```

The table is the one place `default` appears, because repeating the default inline alongside the
value the user is about to overwrite is noise.

**Why both, rather than one (the fork, D-71):** inline-only means "have I filled in everything?"
requires reading the whole file and spotting omissions among block comments — which is exactly how
`Aero.l_ref` stays unset today. Table-only means the thing you are editing has no annotation where
your cursor is. The table is also where REQ/OPT becomes *auditable*: Step 82's check is that the
table's row set equals `dataclasses.fields(...)` of the type the template constructs, which is a
five-line test per template and catches a field added to `sim/params.py` and never documented.

**Scope boundary:** Step 82 is a documentation step and must produce **zero behaviour change** —
`git diff` shows only comments, docstrings and the one stale `sim/params.py:69` `l2` comment §32.5
identifies. Every template must still import cleanly and still be absent from every registry
(§31.8 #6, already pinned).

---

## 32.9 `configs/` and `data/` cleanup — keep/delete list

Read from the tree, file by file. **The headline finding: almost nothing is actually deletable, and
the user's own two stated exceptions are why.** This is a developer ticket (Step 83) carrying a
recommendation, not an action; nothing is deleted by this design pass.

### `configs/` — already exactly "templates + a small demo set"

| package | contents today | verdict |
|---|---|---|
| `rockets/` | `_TEMPLATE_rocket.py`, `toy_05kg.py`, `demo_75mm.py` | **keep all** — one template + two demos |
| `sites/` | `_TEMPLATE_site.py`, `origin_msl.py`, `highland_1500m.py` | **keep all** — `origin_msl` pins `sim/params.py`'s defaults (§31.7) and deleting it would silently change every seed |
| `weather/` | `_TEMPLATE_weather.py`, `isa_dry_calm.py`, `breezy_isa.py` | **keep all** — same defaults-pinning argument for `isa_dry_calm` |
| `scenarios/` | `_TEMPLATE_scenario.py` + `toy_05kg`, `demo_75mm`, `demo_75mm_airbrake`, `demo_75mm_highland` | **keep all** — four scenarios over two rockets, which is the mix-and-match demonstration Step 74 exists to provide |
| `motors/` | *new* | `_TEMPLATE_motor.py` + the seed set in D-73 |
| top level | `__init__.py`, `schema.py` | keep |

**Nothing to trim.** The only thing `configs/` gains is the `motors/` package, and the one judgment
call is how many seed motors ship (D-73).

### `data/motors/`

| file | keep? | why |
|---|---|---|
| `Cesaroni_2060K570-17A.eng` | **KEEP — and `git add` it** | real vendor data (user's exception (a)). **Currently untracked**; Step 79 commits it. It is also the only file that exercises the RASP reader, the header-derived masses and the `"endpoints"` mass model, so it is a fixture as well as data. |
| `placeholder.csv` | **KEEP** | referenced by **21 Python files**, including `configs/rockets/{demo_75mm,toy_05kg}.py` and the `_demo_baseline()` exact-equality pin. Deleting it breaks the phase's own gate. |
| `synthetic_small.csv` | **KEEP** | App 3's four-motor comparison set (Step 61 fixtures) |
| `synthetic_medium_punchy.csv` | **KEEP** | …and specifically the **equal-impulse pair** (169.2 vs 169.5 N·s) that isolates burn-profile effects — §29.5's deliberate design, and `apps/motor_selection/motors.py`'s own comment says the pair is override-free *on purpose* |
| `synthetic_medium_long.csv` | **KEEP** | the other half of that pair; deleting either destroys the comparison |
| `synthetic_large.csv` | **KEEP** | referenced by `apps/motor_selection/{motors,compare_motors}.py`, `apps/airbrake_sizing/targets.py` and `tests/test_motor_selection.py` |

**Recommendation: keep all six.** The four `synthetic_*.csv` are **not** four examples of one
category — they are one deliberate four-motor comparison set, and App 3's entire demo is ranking
them. Reducing to one makes the app undemonstrable and breaks `tests/test_motor_selection.py` plus
`apps/airbrake_sizing/targets.py`. If the user nonetheless wants the one-example-per-category rule
applied literally here, the honest cost is named and the work is a *separate* ticket: delete three,
re-point App 3's `MOTORS` list at `.eng` records (now that `.eng` works), and re-pin
`tests/test_motor_selection.py`'s expected ordering — a real study-rebaselining, not a cleanup.

### `data/soundings/`

| directory | keep? | why |
|---|---|---|
| `example/` (`LKPR_202605011200.csv`) | **KEEP** | the tier-2 single-station sounding example; read by `tests/test_atmosphere.py`, `tests/test_integrate.py`, `tests/test_wind.py` |
| `field_example/` (`FLDA…`, `FLDB…`) | **KEEP** | a **different category** — two stations, which is what exercises tier-3 horizontal interpolation (`soundings.horizontal_interp`, the IDW/RBF dispatch). `example/` cannot exercise it. Read by `tests/test_atmosphere.py` and `tests/test_wind.py`. |
| `example_live/` (`72672_202401151200.csv`) | **KEEP** | **real fetched data**, not an example: station 72672, 2024-01-15 12 Z, the genuine output of `tools/fetch_sounding.py`. `docs/PROJECT-STATUS.md:1307` records it as "kept, committed, as a genuine artifact". The user's exception (a) covers it exactly. It is the only real-world sounding in the tree and the only check that the fetch tool's output format is still readable. |

**Recommendation: keep all three** — one synthetic example per category (single-station, multi-station
field) plus one real artifact.

### `data/aero/`

`example.csv` only. **Nothing to do**, as the user expected.

### The ISA question

**Confirmed, exactly as the user read it.** `Atmosphere.model = "isa"` is pure code
(`sim/atmosphere.py`'s model dispatch); there is no `data/atmospheres/` directory and no ISA data
file anywhere in the tree. A "default/library model" in this project is a dispatch key, not a file,
so there is nothing to keep or delete. The same is true of `Wind.model = "analytic"`,
`Gravity.model = "constant"|"radial"|"wgs84"` and `Aero.model = "constant"|"linearized"` — four more
library models with no data files. The only dispatch keys that *do* read files are
`atmosphere/wind = "sounding"|"field"` (→ `data/soundings/`), `aero = "table"` (→ `data/aero/`) and
`thrust.motor_curve` (→ `data/motors/`), which is precisely the three directories above.

---

## 32.10 Decision log (D-56 … D-73)

Numbering continues §31.9's D-45 … D-55. **None of these is "Decided" yet** — the user was asleep
when this was written and explicitly instructed the orchestrator not to wait ("decide and
document"), so each fork carries the architect's recommendation and the implementation proceeds on
it tonight. The orchestrator presents this table tomorrow morning; a fork overturned then is a
re-do of the named ticket, not of the phase.

| Fork | Recommended | One-line rationale | Blast radius if overturned |
|---|---|---|---|
| D-56 | (a) compose at **assembly** time into the existing `Weight` group | the dry parts are static relative to each other, so the composition is a constant (F2) — `sim/` stays untouched | Step 78/80 rewrite; a new `Params` group and a `sim/dynamics.py` edit |
| D-57 | (a) `weight` is the one **derived** group; D-49 amended, not relaxed | a function of two disjoint-field inputs is not a merge with precedence — no field has two sources | Steps 78/80 |
| D-58 | (a) `Rocket.weight`→`airframe`, `Rocket.thrust` **removed**, `Scenario.motor` **required** | one owner for `thrust`, and a required field makes "which motor?" unmissable | Step 80 + 3 test files |
| D-59 | (a) endpoint `m(t)` shaped by **cumulative impulse fraction** | algebraically identical to today's `I_sp` model (`I_sp_eff = J/(m_prop·g0)`) → zero new `sim/` code *and* the honest shaping | Step 78 only (one formula) |
| D-60 | (a) keep the **`m_p`-linear** lumped `l_COG(t)`/`I(t)`; accept endpoint inputs by exact inversion | already implemented and tested; correct for any curve shape; the user's inputs are a change of chart, not of model | Step 78 |
| D-61 | (a) add `Weight.I_p_spec`, `None`-gated | lets the propellant use its own radius of gyration instead of borrowing the structure's | Step 77 (droppable — it is its own commit) |
| D-62 | (a) new **`sim/mass.py`** | `weight` is the only `Params` group with no owning module (F1), and the template already points there | Step 75 |
| D-63 | (a) `.rasp` = **multi-record RASP library**, record picked by `#designation` | a one-record file is a library of one, so it is one grammar; gives App 3 in-file sweeps for free | Step 76 (the fragment split) |
| D-64 | (a) **prepend `(0.0, 0.0)`** to a RASP curve whose first row is `t > 0` | reproduces the manufacturer's own impulse to 0.108 % vs 0.975 % for the hold (F5); free, since no `.eng` loads today | Step 76 |
| D-65 | (a) new **`sim/motor_file.py`**; `thrust_curve.py` keeps the force seam | the config layer needs header metadata without importing a force model or `sim.atmosphere` | Step 76 |
| D-66 | (a) motor-local datum = the motor's **forward face**, positive aft | one sign rule for the whole project; `l_motor_aft` is offered for aft-flush builds | Steps 78/79 |
| D-67 | (a) `None` header fields **read from the file**; missing geometry defaults to a **uniform cylinder** | makes a real `.eng` motor a 3-line config; the only honest default available before B24 | Step 78 |
| D-68 | (a) `Lengths.l1`/`l2` stay **authoritative**; `Sections` additive | deriving them would contradict the aero table, invent §19's `l1(t)`, and break the bit-for-bit gate | Step 80 (+ a `sim/` phase of its own if reversed) |
| D-69 | (a) named optional station fields **+** a freeform `tubes` tuple | the physics needs one station today; the tuple absorbs "each body tube" without a fixed field count | Step 78 |
| D-70 | (a) read motor files at **import** time, only under `mass_model != "none"` | gated, so `import configs` stays filesystem-free for every existing seed | Step 78 |
| D-71 | (a) **both** a tightened inline `# REQ\|OPT, unit -- desc` **and** a per-template table | they answer different questions; the table is what makes REQ/OPT auditable by a test | Step 82 |
| D-72 | (a) **delete nothing** from `data/`; `configs/` already clean | every file is real data or load-bearing for a test/app demo (§32.9) | Step 83 |
| D-73 | (a) seed `configs/motors/` with **4 pieces** (see below) | one per format/mass-model combination that must be exercised | Step 79 |

---

**D-56 — where the airframe's and the motor's mass data meet.** *Purpose: the rocket now owns only
airframe numbers and the motor owns its own, but `sim/` consumes one `Weight` group; something has to
combine them, and where it happens decides how much of `sim/` this phase touches.*

| Option | Pros | Cons |
|---|---|---|
| **(a) compose at assembly time into today's `Weight` group (recommended)** | the dry parts are rigid relative to each other, so the composition is a *constant* and belongs in a constant's place (F2); `sim/params.py`'s twelve-group contract, `sim/dynamics.py`'s gate and all 403 tests are untouched; the composition runs once per config at import, not 10⁵ times per flight; pass-through makes the seed migration provable bit-for-bit (F4) | `Params.weight` stops being a literal anyone can read off a config module — "where did `m_d = 1.79` come from?" is now a function call, mitigated by `Config.notes` and by the composition being 20 lines in one place |
| (b) a thirteenth `Params` group (`Propulsion`/`MotorMass`), composed per RHS call in `sim/mass.py` | the authoring literals survive all the way into `Params`, so provenance is perfect; the structural `assemble` test would *require* the new group to be wired, catching omissions | changes the engine's public contract for data that cannot change during a flight; `sim/dynamics.py`, `sim/params.py` and every `Weight` consumer are in scope; `weight.m`/`I` must keep their meaning for ~400 tests while two groups now claim the mass, which is precisely the two-owner ambiguity D-49 exists to prevent |
| (c) no composition — the user hand-enters the combined `m_d`/`l_d`/`I_d` as today, and the `Motor` piece carries only the curve | smallest possible change; nothing to prove | abandons the request: "rocket has dry mass and MOI excluding the motor" is then not expressible, and swapping a motor silently keeps the old motor's mass baked into the rocket's numbers — the exact `.derive()`-indirection failure §31.1 was written to remove |

**Recommendation: (a).** F2 is the deciding fact and it is not a judgment call: a static composition
computed per RHS call is the same number, 10⁵ times, at the cost of the engine's public contract.

**D-57 — the one-owner invariant, and the first derived group.** *Purpose: D-49 is the hinge the
whole `configs/` design hangs on; this phase bends it, and the bend must be stated, not slipped in.*

| Option | Pros | Cons |
|---|---|---|
| **(a) `weight` is a DERIVED group — a pure function of two pieces with disjoint field sets; D-49 amended and the amendment documented in `schema.py` (recommended)** | the property D-49 actually protects is "no field can come from two places", and that still holds exactly: `Airframe.m` and `Motor.m_total` are different fields feeding one computed group, not two writers of one field; `assemble` gains one function call, no precedence rule, no partial groups; the AST keyword-set test passes unedited | the invariant's one-sentence statement ("exactly one owning piece per group") is no longer literally true and has to be restated as "exactly one *producer*"; a future reader may take the exception as licence for merge logic |
| (b) keep `weight` rocket-owned and let the `Motor` piece's mass data be reachable only through `Scenario.overrides` | invariant untouched, literally | the mass composition becomes the user's arithmetic homework in an override dict — the worst version of §31.1's complaint, with physics in it |
| (c) split `Weight` into two `Params` groups (`Weight` rocket-owned, `MotorMass` motor-owned) so each has one owner | invariant untouched *and* both pieces own something | this is D-56(b) with its costs, plus `sim/dynamics.py` now reading two groups to compute one `I(t)` |

**Recommendation: (a)**, with the exception written into `configs/schema.py`'s docstring in the same
breath as the invariant, and `tests/test_config_pieces.py` gaining one test that `weight` is the
**only** derived group (every other keyword in `assemble`'s `Params(...)` call is a bare attribute
access, checkable by the same AST walk that already pins the keyword set).

**D-58 — `Rocket` surgery and a required `Scenario.motor`.** *Purpose: this is the only
backward-incompatible change in the phase, and it decides which test files are edited.*

| Option | Pros | Cons |
|---|---|---|
| **(a) `Rocket.weight: Weight` → `airframe: Airframe`; `Rocket.thrust` removed; `Scenario.motor: Motor` required (recommended)** | one owner for `thrust`, no transitional two-owner state; a required field means no scenario can silently fly a default empty motor (which would be zero thrust — a silent, plausible-looking, wrong answer); every `Scenario(...)` call site is keyword-only (grepped), so the edit is one keyword per site | three test files edited (`test_config_pieces.py`'s `_non_default_rocket`, `test_config_migration.py`'s two `rocket.thrust` assertions, `test_config_registries.py`'s package parametrisation); "zero test edits" is not this phase's gate |
| (b) `Scenario.motor: Motor \| None = None`, falling back to `Rocket.thrust` when `None` | zero caller edits; both shapes work during a transition | **two owners for `thrust`** for an indefinite period — the one thing D-49 forbids — plus a fallback branch in `assemble` that nothing would ever remove |
| (c) keep `Rocket.thrust` as the motor's home and make `Motor` carry only the mass model | smallest diff | the motor piece then does not carry the motor's own curve, so "import the motor" selects its mass but not its thrust: two files to change to swap a motor, and they can disagree |

**Recommendation: (a).** The three test edits are listed per-ticket in §32.11 so none is a surprise
at implementation time. Note the migration test's edit is an *improvement*:
`rockets.get("demo_75mm").thrust == baseline.thrust` becomes
`get("demo_75mm").params.thrust == baseline.thrust`, which tests the composition rather than a
literal.

**D-59 — how `m(t)` is shaped between `m_0` and `m_f`.** *Purpose: the user asked the question
explicitly and left it open.*

| Option | Pros | Cons |
|---|---|---|
| **(a) linear in cumulative impulse fraction (recommended)** | identical to `dm/dt = -T(t)/(I_sp_eff·g0)` with `I_sp_eff = J/(m_prop·g0)`, so there is **no new `sim/` code path** and the two mass models cannot drift; mass falls in proportion to thrust actually produced; burnout mass is exactly `m_f` by construction, which is a testable assertion; the curve is already loaded, so `J` is free | `I_sp_eff` is a derived number the user never typed, so a surprising burn needs one explanatory line in the composition's docstring (and `I_sp_eff` is worth printing in the step report) |
| (b) linear in time over the burn | trivially explainable; matches the user's literal phrasing | physically wrong for every non-constant curve in this repo — a punchy curve would still be "half-fuelled" long after the thrust has collapsed, moving the static margin the wrong way at the wrong moment; needs a burn duration, which the curve already implies, so it adds a second source of truth |
| (c) require `I_sp` always; refuse the endpoint model | one model, no derivation | refuses the user's request, and refuses the data: a RASP header gives two masses and no `I_sp`, so every real motor file would need a hand-looked-up number |

**Recommendation: (a).** The equivalence is the whole argument: the "more physically honest" option
and the "no new code" option are the same option.

**D-60 — the `l_COG(t)` / `I(t)` model.** *Purpose: the user proposed time-linear endpoints "for now"
and explicitly invited a better proposal.*

| Option | Pros | Cons |
|---|---|---|
| **(a) keep the mass-weighted-centroid + parallel-axis model (linear in `m_p(t)`), re-homed onto `Motor`, and accept the user's endpoint numbers as an exactly-invertible input parameterisation (recommended)** | already implemented, already tested (`tests/test_dynamics.py`), already in `main.tex` §`sec:mass`; consistent for any curve shape with no extra input; the endpoint inversion is exact algebra (§32.3.5), so the user types `l_cog_0/l_cog_f/I_0/I_f` and gets the physical interpolation between them; one formula in the codebase, not two | the inversion can produce a non-physical `I_prop0 < 0` from inconsistent endpoint inputs — which is *information* (it means the two endpoints are not reachable by any two-lump motor), and the composition should say so rather than clamp |
| (b) literally time-linear `l_COG(t)`/`I(t)` between the endpoint pairs | exactly what the user described; three lines | contradicts `main.tex`; worse for every curve in the repo; a second mass model to keep tested; needs a burn duration (D-59(b)'s defect again) |
| (c) go straight to grain-geometry integration (B24) now | the right answer eventually | needs grain family, bore/outer diameter, length, inhibition and regression coefficients — none of which any file format carries and none of which the user has chosen; `main.tex` says so at length |

**Recommendation: (a)**, with (b) recorded in §32.13 as a ~15-line additive third `mass_model` value
if the user prefers it after reading this, and (c) booked as **B24**.

**D-61 — `Weight.I_p_spec`: the propellant's own radius of gyration.** *Purpose: today's `I_p =
(I_d/m_d)·m_p` borrows the dry structure's specific inertia for the propellant, which the
composition makes needlessly wrong.*

| Option | Pros | Cons |
|---|---|---|
| **(a) one `None`-gated `Optional[float]` field on `Weight`, read by `sim/mass.py` (recommended)** | bit-for-bit for every existing config by default; *specific* (m², per unit mass) so no second field is needed to scale it; keeps `I_p ∝ m_p(t)`, the shape `main.tex` states, changing only the constant; lands in its own commit with its own gate, so it is independently revertible | the thirteenth field on the one group that was already the most crowded; "specific MOI" needs its one-line explanation (it is a squared radius of gyration) |
| (b) leave the placeholder; accept the structure's radius of gyration for the propellant | zero `sim/` change in the whole phase | the composition knows the motor's real length and diameter and would be throwing them away; for a 0.49 m motor in a ~1 m airframe the borrowed value is wrong by roughly the length ratio squared, in the term that sets pitch response |
| (c) two fields (`I_p0`, `m_p0`) instead of one specific value | mirrors the user's `I_0`/`I_f` phrasing more directly | two fields where one suffices, and `m_p0` is already recoverable as `m − m_d` at `t = 0` |

**Recommendation: (a).** Smallest honest `sim/` change in the phase, and the only one.

**D-62 — where the mass code lives.** *Purpose: the user asked the question directly.*

| Option | Pros | Cons |
|---|---|---|
| **(a) a new `sim/mass.py` (recommended)** | `weight` is the **only** one of the twelve groups with no owning module (F1), against §28.3's explicit "one group per module that owns a dispatch"; `configs/rockets/_TEMPLATE_rocket.py:40` already tells the user the model is in `sim/mass.py`, so the tree is currently wrong about itself; `m(t)` gains a real dispatch (`none`/`isp`/`endpoints`) and dispatches belong in their own module; `sim/dynamics.py` is 387 lines of EOM and does not need to also be the mass model | one more `sim/` module; one `git log` discontinuity for three functions (mitigated: the move is its own commit with no other change, so `git log --follow` is clean) |
| (b) keep them in `sim/dynamics.py`, add the composition there too | zero churn; the three helpers stay next to their only caller | `dynamics.py` grows a second responsibility, and the assembly-time `combine()` would then be imported *from the EOM module* by `configs/schema.py` — a config layer importing the equations of motion to add up masses |
| (c) put the composition in `configs/schema.py` and leave `sim/` alone entirely | smallest diff; no `sim/` step at all | the parallel-axis theorem would then exist twice in the repo, in two layers, with the `configs/` copy untested against the `sim/` one — the exact drift F3 shows is detectable to one ULP and would go unnoticed |

**Recommendation: (a).** Note the split that makes it work: `sim/mass.py` owns the arithmetic,
`configs/schema.py` owns the dataclass glue, and `sim/` never imports `configs/`.

**D-63 — what `.rasp` is, as distinct from `.eng`.** *Purpose: the user named both extensions and
asked for the more useful reading of the difference.*

| Option | Pros | Cons |
|---|---|---|
| **(a) `.rasp` = a multi-record RASP library; `.eng` = conventionally one record; both parsed by one reader that returns a list; record selected by `"<file>#<designation>"` (recommended)** | matches the historical artifact (the RASP motor database shipped as one many-record file); a one-record file is a library of one, so there is one grammar and no duplicated parser; **App 3 gains in-file motor sweeps for free** because `MotorEntry.overrides` already writes `thrust.motor_curve`; adds no `Params` field — `motor_curve` is already "the file, extension included" (F7); a multi-record file with no fragment raises a `KeyError` listing every designation, the same error shape all four registries use | the `#fragment` is a mini-convention inside a string field; a user who writes `.eng` for a library file still gets the right answer, which makes the extension distinction *descriptive* rather than enforced — honest, but it means the two extensions are not really different code paths |
| (b) `.rasp` is a pure synonym for `.eng`: one record, same grammar | nothing new to explain; two extensions, one meaning | then the distinction the user asked about does not exist, and a real `rasp.eng`-style database file cannot be used at all without being split by hand |
| (c) support `.eng` only; reject `.rasp` | smallest surface | refuses a stated requirement for no gain, since the grammar is shared anyway |

**Recommendation: (a).** The ambiguity is recorded here rather than resolved by fiat: if the user
meant (b), (a) *already does* (b) for every single-record file, so nothing has to change — (a) is a
superset, which is why it is safe to implement before the confirmation.

**D-64 — a RASP curve whose first row is `t > 0`.** *Purpose: the real file starts at `t = 0.04 s`
with 892.67 N, and today's loader holds the first value backwards to `t = 0`.*

| Option | Pros | Cons |
|---|---|---|
| **(a) prepend an explicit `(0.0, 0.0)` point in the RASP reader (recommended)** | the first RASP row is the first *measured* point after ignition, not a pre-ignition hold; measured (F5): total impulse 2062.22 N·s = **0.108 %** from the motor's own "2060" designation, against **0.975 %** for the hold; costs nothing — `.eng` files do not load at all today, so no existing run can change; makes `total_impulse` a plain trapezoid and makes "as listed" and "as simulated" the same curve, which is what `I_sp_eff` depends on (§32.3.4); the designation becomes a free independent check on the parser | `.csv` and `.eng` now differ in one documented respect, which must be said in both the reader docstring and the motor template |
| (b) keep `left=thrusts[0]` for every format | one rule for all formats; `thrust_curve.thrust` not reasoned about at all | fires the motor at 892.67 N at `t = 0`, before the data says it ignites, and manufactures 35.7 N·s (0.9 %) of impulse — which lands directly on `I_sp_eff` and so on burnout mass |
| (c) change `thrust_curve.thrust`'s `left=` to `0.0` for every format | one rule, and the physically right one | **breaks bit-for-bit for every existing `.csv` config**, and the `left=thrusts[0]` behaviour is a documented deliberate choice ("allows pre-ignition spike if desired") |

**Recommendation: (a).** Also worth recording as a backlog candidate: auditing whether any
`synthetic_*.csv` fixture relies on the hold, and if none does, unifying on `left=0.0` in a later
step with its own bit-for-bit review (§32.13).

**D-65 — reader module structure.** *Purpose: `sim/thrust_curve.py` is the only motor-file reader
today; the question is whether it grows or splits.*

| Option | Pros | Cons |
|---|---|---|
| **(a) new `sim/motor_file.py` for formats + metadata; `thrust_curve.py` keeps `thrust(t, s, p)` and delegates (recommended)** | `configs/schema.py` needs header metadata at assembly time and must not import a force model, nor pull `sim.atmosphere` into the config import graph; one module, one job, one reason to change; `thrust(t, s, p)`'s force-model shape and its pressure correction stay exactly where they are; `tests/test_thrust_curve.py` passes unedited | one more `sim/` module; two `lru_cache`s in the chain (harmless — the inner one does the work) |
| (b) grow `thrust_curve.py` to ~250 lines with three parsers and a metadata record | no new file | the config layer then imports the force model (and `sim.atmosphere` transitively) to read two numbers out of a header; the module's docstring already has two jobs and would gain a third |
| (c) a `tools/eng_to_csv.py` converter, hand-run, as **B14** originally proposed | matches `tools/fetch_sounding.py`'s precedent; no `sim/` change at all | throws the header away at exactly the moment the mass model needs it — which is why B14's own entry says "the header's propellant/total-mass fields are also exactly the data **B15** needs"; also makes real motor data a manual pre-processing step |

**Recommendation: (a).** This supersedes B14's converter sketch for a good reason, stated in B14
itself.

**D-66 — the motor's own geometric datum.** *Purpose: the motor's `l_case`/`l_prop` must be in some
frame, and the choice decides whether a motor is reusable across airframes.*

| Option | Pros | Cons |
|---|---|---|
| **(a) the motor's forward (nose-ward) face, positive aft (recommended)** | identical sense to the airframe's nose-tip convention, so there is exactly **one** sign rule in the project (§32.5); the rocket's mount station is the forward face of the motor-mount tube, a real buildable dimension; conversion to nose-tip stations is one addition | an aft-flush install is more naturally dimensioned from the tail — handled by offering `Sections.l_motor_aft` and subtracting the motor's own length |
| (b) the motor's aft end, positive forward | matches how a motor is retained in practice (thrust ring at the aft closure) | inverts the sign sense halfway through the vehicle, which is exactly the class of bug Step 25 was spent resolving |
| (c) the motor's own `t = 0` centroid | no length needed to place anything | the datum moves as the propellant burns unless frozen at `t = 0`, which then has to be explained every time; and it is not a dimension anyone can measure on a real motor |

**Recommendation: (a).**

**D-67 — header-derived values and geometry defaults.** *Purpose: how much of a motor must be typed
by hand before it can fly with a mass model.*

| Option | Pros | Cons |
|---|---|---|
| **(a) `None` means "read it from the file"; any geometry still missing defaults to a uniform cylinder from the header's diameter and length (recommended)** | a real `.eng` motor becomes a **three-line** config (§32.4) and the header stops being decoration; a uniform solid cylinder (`m(3r²+L²)/12`, centroid at mid-length) is the only honest default available before B24, and it is stated as an assumption rather than hidden; an explicit value always wins, which is how a re-cased or partially-loaded motor is modelled | the default is wrong in a known direction — over-estimates a thin-walled casing's transverse MOI, under-estimates a cored grain's — by `O(r²/L²)`, which for a 54 mm × 488 mm motor is ~0.3 % of the `L²` term and therefore negligible at this fidelity; still, it must be written down (it is, in `uniform_cylinder_I`'s docstring and B24) |
| (b) require every motor number to be hand-entered; the header is informational only | nothing is ever silently assumed | a real motor needs six hand-looked-up numbers before it flies, four of which are printed in the file being loaded |
| (c) read the header but refuse to default geometry — `mass_model != "none"` requires `l_case`/`l_prop`/`I_case`/`I_prop0` | no hidden assumption, header still useful | the user cannot fly the one real motor in the repo without inventing four inertia numbers, which they would invent *as* a uniform cylinder |

**Recommendation: (a).**

**D-68 — do `Lengths.l1`/`l2` become derived from the new sections?** *Purpose: the user asked
directly, and the answer must not break two closed steps.*

| Option | Pros | Cons |
|---|---|---|
| **(a) no — `l1`/`l2` stay authoritative; `Sections` is additive, and only `l_motor_fwd`/`l_motor_aft` is read by any code (recommended)** | deriving `l1` needs `l_D`, which under `aero.model="table"` is **already** a function of `(α, M)` — so a derived `l1` would duplicate or contradict the table, which Step 55 restructured `sim/aero.py` specifically to prevent; with the mass model on, derived arms become `l1(t)`/`l2(t)`, the open question `architecture.md` §19 is blocked on and `sim/dynamics.py`'s Step-36 note deliberately refuses; keeps the bit-for-bit gate reachable; **confirms: no `sim/dynamics.py`/`sim/forces.py` change** | `Sections` and `Lengths` can state geometrically incompatible things and nothing cross-checks them (§32.5's residual; risk 4) |
| (b) yes — absolute stations become the source of truth, `l1`/`l2` derived properties | one geometry, no redundancy; the obviously right end state | changes every existing run's numbers unless the derivation reproduces `0.3`/`0.4` exactly; answers §19's physics question as a side effect of a config refactor; requires a CoP station the aero table owns |
| (c) hybrid — derive them only when `Sections` is fully populated, else use the literals | incremental | two code paths for the same number, with the active one depending on how much the user filled in: the least predictable option available |

**Recommendation: (a)**, with (b) booked as a backlog candidate paired with B25 (which supplies the
airframe CoG that a derived `l1` needs) and with §19's `l1(t)`/`l2(t)` question.

**D-69 — the shape of the `Sections` field set.** *Purpose: "which sections" was explicitly the
architect's call.*

| Option | Pros | Cons |
|---|---|---|
| **(a) named optional fields for the few stations the physics or the documentation needs, plus a freeform `tubes: tuple[tuple[str, float], ...]` (recommended)** | greppable, readable in a literal, no lookup helper; covers "each body-tube section" without committing to a fixed tube count; `tubes` is the natural landing spot for B25's per-section masses (`tuple[Section, ...]`) | two kinds of thing in one dataclass (named fields + a bag); `tubes` is informational today and a reader may expect it to be read |
| (b) a single freeform `tuple[Station, ...]` with a `station(name)` lookup | perfectly general; B25-ready by construction | station names become an unvalidated string API — "which spelling places the motor?" has no answer a grep can give; needs a lookup helper and a missing-name error path |
| (c) a fixed section list (nose, tube1, tube2, fin can, boat tail) | maximally explicit | wrong for every airframe with a different section count, which is most of them |

**Recommendation: (a).**

**D-70 — reading a motor file at import time.** *Purpose: `mass_model="endpoints"` needs the curve's
total impulse, and `assemble` runs at import.*

| Option | Pros | Cons |
|---|---|---|
| **(a) yes, gated: only when `mass_model != "none"` (recommended)** | every existing seed is on the `"none"` path, so `import configs` stays filesystem-free and cannot newly fail; when it *is* read, a missing file fails loudly at import with the filename — which is exactly when you want to hear it; `lru_cache`d, so N scenarios sharing a motor parse once | a config module's import now has a filesystem precondition in one mode, which is new in this project |
| (b) defer to first `run_sim` — compute `I_sp_eff` lazily in `sim/` | import stays pure in every mode | needs a second mass-model dispatch inside `sim/`, which is the entire cost D-59 avoided; and the failure surfaces mid-study instead of at import |
| (c) require `I_sp` always, forbid `"endpoints"` | no file read at all | D-59(c): refuses the data |

**Recommendation: (a).**

**D-71 — the templates documentation convention.** *Purpose: the user's point 9 asked where this
lives.*

| Option | Pros | Cons |
|---|---|---|
| **(a) both: tightened inline `# REQ\|OPT, <unit/choices> -- <desc>` on every field, and a per-field table in each template's module docstring (recommended)** | the inline comment is what you read while editing; the table is what you read to discover a field you have never noticed (which is how `Aero.l_ref` stays unset today); the table makes REQ/OPT **auditable** — Step 82's check is that its row set equals `dataclasses.fields(...)`, a five-line test per template that catches an undocumented new field | the same information twice in one file, so they can drift — mitigated by the row-set test and by both living in the same file |
| (b) inline comments only, tightened | one source; smallest diff; today's templates are already most of the way there | no completeness check; "did I miss a field?" stays a careful read |
| (c) one companion table per template, in a separate `.md` | the table can be richer, and generated | documentation leaves the file it documents — the one failure mode this project's commented-literal style exists to avoid |

**Recommendation: (a).**

**D-72 — the `configs/`/`data/` cleanup.** *Purpose: the user asked for a keep/delete list.*

| Option | Pros | Cons |
|---|---|---|
| **(a) delete nothing; `git add` the untracked `.eng`; record why each file stays (recommended)** | every single file is either real data (the `.eng` motor; `soundings/example_live/`, recorded in `PROJECT-STATUS.md` as a genuine committed artifact) or load-bearing for a test or an app's demo (§32.9); the four `synthetic_*.csv` are one deliberate four-motor comparison set — including an **equal-impulse pair** built to isolate burn-profile effects — not four examples of one thing | `data/motors/` keeps six files where the user expected ~two, so the recommendation has to be argued rather than executed (it is, per file, in §32.9) |
| (b) apply one-example-per-category literally: delete three `synthetic_*.csv` and `soundings/example_live/` | matches the stated rule exactly; smaller tree | breaks `tests/test_motor_selection.py` and `apps/airbrake_sizing/targets.py`, destroys App 3's demo and the equal-impulse comparison, and deletes the only real-world sounding in the repo plus the only check that the fetch tool's output is still readable |
| (c) delete the three extra synthetics *and* re-point App 3 at `.eng` records now that they load | genuinely tidier end state, and more honest (real motors, not synthetic ones) | a study rebaselining, not a cleanup: App 3's ranked output and its pinned test expectations all move, and it wants its own step with its own review |

**Recommendation: (a)**, with (c) offered as a separate later ticket if the user wants the tree
smaller — framed honestly as "re-baseline App 3 on real motors", which is a feature, not housekeeping.

**D-73 — which motors seed `configs/motors/`.** *Purpose: the registry needs enough entries to
exercise every path, and few enough to stay a demo set (the user's point 10).*

| Option | Pros | Cons |
|---|---|---|
| **(a) four: `placeholder` (`.csv`, `mass_model="none"` — what the seeds use), `synthetic_large` (`.csv`, `"none"`), `cti_k570` (`.eng`, `"endpoints"`, full mass model from the header), `cti_k570_isp` (same curve, `"isp"`, hand-entered `I_sp`) (recommended)** | one per format × mass-model combination that must work, so the registry *is* the integration test; `placeholder` keeps the seeds bit-for-bit; `cti_k570` is the worked demo for Step 81; the `isp`/`endpoints` pair on one curve makes the two models directly comparable, which is the cheapest possible check on D-59's equivalence claim | four entries where one would register |
| (b) two: `placeholder` + `cti_k570` | minimal | the `"isp"` path ships unexercised from the config layer, and nothing demonstrates swapping motors under one rocket |
| (c) one per existing curve file, six entries | symmetric with `data/motors/` | four near-identical `"none"` motors; App 3 already owns the motor-sweep use case as a *study* input (§30.3), and a config piece per sweep entry is the second home §31.11 warned about |

**Recommendation: (a).** Note explicitly what stays out: `apps/motor_selection/motors.py`'s
`MOTORS` list is **not** migrated into `configs/motors/`. §30.3's two-kinds convention and §31.11
both put a sweep list outside `configs/`, and a `MotorEntry` carries per-motor *airframe* overrides
(casing mass, body diameter, geometry) that are a study delta, not a motor. The two coexist, and
§32.13 records the convergence option.

---

## 32.11 Implementation tickets (Steps 75-84, Phase 2.16)

Same Files/Spec/Do/Check/Commit shape every roadmap step uses. Step numbers continue the sequence
(last used: **Step 74**, Phase 2.15, commit `e47c08d`); the latest architecture doc is **31**, so
this is **32**; the backlog's last used ID is **B23**, so this opens **B24**/**B25**. Phase 3 keeps
its reserved 28-32 step block (this phase's numbers are 75+, no collision).

**Ten steps, one commit each, full regression suite after each.** Generous on count by design: the
phase spans three `sim/` modules, a `configs/` surgery, a new subpackage and two documentation
passes, and cramming any two of those together would make the one bit-for-bit gate that matters
(Step 80) unisolatable.

### Dependency and parallelism map

```
75 (sim/mass.py)  ──┐
                    ├─→ 77 (Weight.I_p_spec) ──┐
76 (sim/motor_file) ┴──────────────────────────┴─→ 78 (schema, additive) → 79 (configs/motors/)
                                                                                  │
                                                                      ┌───────────┴─→ 83 (cleanup)
                                                                      │
                                                              80 (THE SWITCH-OVER)
                                                                      │
                                                        ┌─────────────┼─────────────┐
                                                       81 (demo)   82 (templates)   │
                                                                                   84 (LaTeX, parallel-safe)
```

- **75 ∥ 76** — genuinely parallel-safe: disjoint boundaries (`75` creates `sim/mass.py` and edits
  `sim/dynamics.py`; `76` creates `sim/motor_file.py` and edits `sim/thrust_curve.py`; no shared
  file, no shared test file). The first pair in this project since Steps 61/65 that may actually run
  concurrently in two worktrees.
- **77 needs 75** (it edits `sim/mass.py`) and also edits `sim/params.py`.
- **78 needs 75, 76, 77** — it calls all three.
- **79 → 80 → {81, 82}** strictly sequential; 81 and 82 are **not** parallel-safe against each other
  (82 edits `_TEMPLATE_rocket.py`/`_TEMPLATE_motor.py`, 81 may add a motor module next to them and
  both touch `configs/motors/__init__.py`).
- **83 needs 79** (the motor seeds must exist before their data files' keep-list is final) and is
  parallel-safe against 81/82 only if the orchestrator confirms 83 touches no `configs/` file — per
  D-72 it touches **none**, so mark it `parallel_safe: true` against 82 but sequence it after 80 for
  a clean regression baseline.
- **84 is docs-only** (`docs/latex/`), touches no code file, genuinely `parallel_safe: true` — the
  Step-54 precedent — but must land before the phase closes so the document does not contradict the
  code.

### The phase gate, stated once

Every ticket inherits all five; a step that cannot show them is not done.

1. **Full suite green.** 403/403 is the pre-phase baseline, **measured on this branch**
   (`python -m pytest -q`, 388 s). Each step reports its own count and what it added.
2. **Bit-for-bit for Steps 75, 76, 77** — all three are pure moves or `None`-gated additions, so the
   check is literally "403 pass, zero expected values edited". Any test needing a new expected
   number in these three steps means the step is wrong.
3. **The four exact-equality pins in `tests/test_configs.py` are the Step-80 gate**, unedited:
   `test_toy_05kg_params_pin_run_py_literal_exactly`,
   `test_toy_05kg_s0_pins_run_py_literal_exactly`,
   `test_demo_75mm_params_pin_demo_baseline_exactly`,
   `test_demo_75mm_s0_pins_compare_motors_main_literal_exactly`. They compare against independent
   reconstructions (`_toy_05kg_literal()` in the test file, `_demo_baseline()` in App 3) — which is
   why the composition's pass-through path (§32.3.3 case 0) must be an explicit early return (F4).
4. **The three *named* test edits, and no others.** Unlike Phase 2.15 this phase is not "zero test
   edits", and the exact permitted set is fixed here so an unexpected fourth edit is a signal:
   - `tests/test_config_pieces.py` — `_non_default_rocket()` drops `thrust=`, gains
     `airframe=`/`sections=`; a new `_non_default_motor()`; `motor=` added to six `Scenario(...)`
     calls. **No assertion changed**, including both one-owner tests.
   - `tests/test_config_migration.py` — `rocket.weight`→`get(...).params.weight` and
     `rocket.thrust`→`get(...).params.thrust` in the two piece-slice tests (a *strengthening*: it
     now tests the composition, not a literal).
   - `tests/test_config_registries.py` — the four-package parametrisation becomes five.
   Everything else in `tests/` is additions in new files (`tests/test_mass.py`,
   `tests/test_motor_file.py`, `tests/test_motor_pieces.py`), so `git diff --stat -- tests/` stays
   readable.
5. **`git diff --stat` boundary check** — the files touched are exactly the ticket's own
   Module/boundaries list, nothing else.

---

### [Step 75] `sim/mass.py` — the mass model gets its own module

- **Module/boundaries:** new `sim/mass.py`; `sim/dynamics.py` (**delete the three private helpers,
  add one import, change three call sites — nothing else, no comment in the EOM reflowed**); new
  `tests/test_mass.py`. **No other `sim/` file. No `configs/` file, no `apps/` file, no `run*.py`,
  no existing test file.**
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true (against Step 76 only — disjoint files; not against anything later)
- **Spec slice:** §32.3.1 **F1/F3/F4** (why the module exists, and the two measured reasons
  `combine` must not be what `moment_of_inertia` is built from); §32.3.2 in full (the module
  listing). Nothing else. Read `sim/dynamics.py:122-171` and `:257-266` for the code being moved.
- **Do:** create `sim/mass.py` with the §32.3.2 listing. Move `_propellant_mass`/`_cog_position`/
  `_moment_of_inertia` to `propellant_mass`/`cog_position`/`moment_of_inertia` — **expressions
  copied character for character**, every docstring kept verbatim (they carry `main.tex` references
  and the `I_p` placeholder rationale). Add `Lump`, `combine`, `total_impulse`,
  `isp_from_impulse`, `uniform_cylinder_I`. `combine` uses `math.fsum`, and its docstring states F3
  and F4 explicitly — that it is assembly-time only, that it is **not** bit-for-bit equal to
  `moment_of_inertia`, and that a future "tidy" merging the two will fail this step's gate.
  `sim/dynamics.py` gets `from sim import mass` and three call sites; its module docstring gains one
  sentence pointing at `sim/mass.py` for the mass model and keeps every Step-36/37/43 note untouched.
- **Check:** new `tests/test_mass.py`: `combine` of one lump reproduces it to 1e-15 relative **and
  the test states that bitwise equality is not claimed** (F4, with the `m=1.5, l=0.4` counterexample
  as a comment); `combine(a, b)` agrees with `cog_position`/`moment_of_inertia` on the two-lump case
  to 1e-15 relative, **not** bitwise (F3, with the measured `2.1e-16` as a comment); `combine` is
  order-independent (permuting the lumps gives the same result — which `math.fsum` makes exactly
  true); `combine()` of a zero-mass set returns a zero `Lump` rather than dividing by zero;
  `uniform_cylinder_I` against the hand-computed `m(3r²+L²)/12` for the K570's 54 mm × 488 mm;
  `isp_from_impulse(2062.223, 0.99, 9.80665) == pytest.approx(212.4123, abs=1e-4)` (F5);
  `total_impulse` on the `(0,0)`-prepended K570 arrays. **Full suite 403 green, no existing test
  edited, no expected value changed** — the bit-for-bit gate: the three moved functions are the only
  path `tests/test_dynamics.py`'s mass-model tests exercise, so 403/403 *is* the proof the move is
  inert.
- **Commit:** `Step 75 (Phase 2.16): sim/mass.py -- the mass model gets its own module`

---

### [Step 76] `sim/motor_file.py` — `.csv` / `.eng` / `.rasp`

- **Module/boundaries:** new `sim/motor_file.py`; `sim/thrust_curve.py` (**`_load_motor_curve` body
  replaced by a delegation; `thrust()` NOT edited**); new `tests/test_motor_file.py`. **No other
  `sim/` file, no `configs/` file, no `apps/` file, no `run*.py`, no existing test file, and no file
  under `data/`.**
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** true (against Step 75 only)
- **Spec slice:** §32.4 in full (the grammar, the module listing, the dispatch, the `#designation`
  fragment, the `(0,0)` prepend); §32.3.1 **F5** (the measured impulse numbers) and **F7** (the
  extension is already in `motor_curve`). Nothing else. Read `sim/thrust_curve.py` whole (129 lines)
  and `data/motors/Cesaroni_2060K570-17A.eng`.
- **Do:** `MotorRecord`, `records(filename)`, `load(spec)` per §32.4. The CSV reader is today's
  `_load_motor_curve` body moved verbatim — same `csv.reader`, same `#`-comment skip, same
  "allow extra columns", same `np.argsort` + `np.unique(return_index=True)` — returning a
  `MotorRecord` with `designation` = the filename stem and **every metadata field `None`**. The RASP
  reader implements §32.4's grammar: `;` comments discarded, header detected as "first token does not
  parse as a float", seven fields, `delays` kept as free text and never parsed, mm→m at the boundary,
  records delimited by the next header line (so blank lines are not load-bearing), and the `(0.0,
  0.0)` prepend when `times[0] > 0.0` — applied **only** in the RASP reader (D-64). `load` splits on
  `#`; no fragment + one record → that record; no fragment + several → `KeyError` listing every
  designation; unknown designation → the same message. Both functions `lru_cache`d.
  `sim/thrust_curve.py`'s `_load_motor_curve` becomes the two-line delegation in §32.4; its module
  docstring gains a paragraph on the new formats and the prepend; **`thrust()` is not touched**.
- **Check:** new `tests/test_motor_file.py`: the K570 header parses to
  `designation="K570", diameter=0.054, length=0.488, delays="7-17", m_prop=0.99, m_total=1.685,
  manufacturer="CTI"`; ten data rows become **eleven** after the prepend, `times[0] == 0.0` and
  `thrusts[0] == 0.0`; `total_impulse == pytest.approx(2062.223, abs=0.01)` and — stated as the
  parser's independent check — within 0.2 % of the designation's own `2060` (F5);
  `m_total - m_prop == 0.695`; a tmp-path two-record `.rasp` fixture round-trips both records,
  `load("f.rasp#SECOND")` picks the right one, a bare `load("f.rasp")` raises `KeyError` naming both
  designations, and a bogus designation raises naming both; a `;`-only file and a blank-line-free
  concatenation both parse; `.csv` records carry `m_prop is None` (**not** `0.0`) so the mass model
  can tell "unknown" from "zero". **Bit-for-bit gate:** `tests/test_thrust_curve.py` passes
  **unedited**, and `_load_motor_curve("placeholder.csv")` returns arrays `np.array_equal` to a
  pre-step capture for all five existing `.csv` files. Full suite 403 green.
- **Commit:** `Step 76 (Phase 2.16): sim/motor_file.py -- .csv/.eng/.rasp readers, one record type`

---

### [Step 77] `Weight.I_p_spec` — the propellant's own radius of gyration

- **Module/boundaries:** `sim/params.py` (**one field appended to `Weight`, one comment — no other
  group touched**); `sim/mass.py` (`moment_of_inertia`, one branch); `tests/test_mass.py` (append).
  **No other file.**
- **Assignee:** developer
- **depends_on:** [Step 75]
- **parallel_safe:** false
- **Spec slice:** §32.3.5's "one honest consequence" subsection (the field, the branch, the
  rationale); `main.tex` §`sec:mass`'s `I_p(t)` paragraph and its `\todo`; `sim/mass.py`'s
  `moment_of_inertia` docstring as it stands after Step 75. Nothing else.
- **Do:** append `I_p_spec: Optional[float] = None` to `Weight` with the §32.3.5 comment (unit m²,
  "radius of gyration squared", `None` → the pre-Step-77 `(I_d/m_d)` placeholder). Add the one
  `if`/`else` to `moment_of_inertia` and extend its docstring: what the placeholder was borrowing,
  why borrowing the structure's specific inertia for a short grain is wrong once the motor's real
  length is known, and that B24 replaces both.
- **Check:** `I_p_spec=None` reproduces the pre-step `I(t)` **bitwise** for a hand-built `Params`
  (the gate — `None` must short-circuit to the identical expression, not to an algebraically equal
  one); an explicit `I_p_spec` equal to `I_d/m_d` reproduces it to 1e-15 (not bitwise — different
  multiply order, and saying so in the test is the point); a smaller `I_p_spec` gives a smaller
  `I(t)` monotonically in `m_p`; `I_p_spec=0.0` is honoured as zero (a point-mass grain), **not**
  treated as "unset" — the `None`-versus-`0.0` distinction `Weight.m_d` already establishes. Full
  suite 403 green, **no existing test edited, no expected value changed.**
- **Commit:** `Step 77 (Phase 2.16): Weight.I_p_spec -- the propellant's own specific MOI, None-gated`

---

### [Step 78] `configs/schema.py` — `Motor`, `Airframe`, `Sections`, and the composition (additive, unwired)

**Nothing is wired up by this step, deliberately — the Step-71 pattern.** `Rocket`, `Scenario` and
`assemble` are **not** edited; the new types and the composition function exist and are tested on
hand-built pieces only. This is what makes Step 80 a switch-over with the risky part already proven.

- **Module/boundaries:** `configs/schema.py` (**append only** — `Config`, `Variant`, `Rocket`,
  `LaunchSite`, `Weather`, `Scenario`, `assemble`, `_pad_state` are not edited, not reordered, not
  re-docstringed); new `tests/test_motor_pieces.py`. **No other `configs/` file. No `sim/` file, no
  `apps/` file, no `run*.py`, no existing test file.**
- **Assignee:** developer
- **depends_on:** [Step 75, Step 76, Step 77]
- **parallel_safe:** false
- **Spec slice:** §32.2.1, §32.2.2 (the three dataclass listings in full); §32.3.3 (the composition,
  its six properties, its four cases); §32.3.4 (the `I_sp_eff` formula); §32.3.5 (the exact
  inversion of the endpoint parameterisation); §32.3.1 **F2/F4/F6**. Nothing else.
- **Do:** append `Airframe`, `Sections`, `Motor` and `_weight_from_pieces(rocket, motor, g0)` exactly
  as §32.2/§32.3.3 specify — frozen dataclasses, `None` for every derivable field, no validation
  beyond the two named preconditions. `_weight_from_pieces` takes a `Rocket` so it can read
  `rocket.sections`/`rocket.airframe`, and is written to work against **both** the current `Rocket`
  (which has `weight`, not `airframe`) and the Step-80 one — simplest way: have it take
  `(airframe: Airframe, sections: Sections, motor: Motor, g0: float)` and let Step 80's `assemble`
  pass `sc.rocket.airframe, sc.rocket.sections`. State this in the docstring so Step 80 does not
  re-sign it. `__all__` grows by three names. The module docstring gains: the D-57 amendment to the
  one-owner invariant (`weight` is the one **derived** group, a function of disjoint inputs, not a
  merge), and one sentence that `sim/` is never imported from `configs/` for arithmetic beyond
  `sim.mass`/`sim.motor_file`.
- **Check:** new `tests/test_motor_pieces.py`: **pass-through is bitwise** —
  `_weight_from_pieces(Airframe(m=1.5, I=0.08), Sections(), Motor(name="m"), 9.80665)` is
  `Weight(m=1.5, I=0.08)` with `m_d is None`, and the two floats are `is`-identical objects or at
  least `==` with `repr` equality (F4 is why this must be an early return); a two-lump composition
  against a hand-computed parallel-axis number; **the exact-inversion round trip** — build a motor
  from `(l_cog_0, l_cog_f, I_0, I_f)`, compose, and recover `l_cog_0`/`I_0` from the resulting
  `Weight` at `m_p = m_p0` to 1e-12 (§32.3.5, the test that proves the chart change is lossless);
  `mass_model="endpoints"` on the real K570 yields `I_sp == pytest.approx(212.4123, abs=1e-3)`,
  `m == pytest.approx(airframe.m + 1.685)`, `m_d == pytest.approx(airframe.m + 0.695)`;
  `mass_model="isp"` passes `I_sp` through untouched; header fields left `None` are filled from the
  `.eng` file and an explicit value overrides; geometry left `None` defaults to the uniform cylinder;
  `l_motor_aft` places the motor identically to the equivalent `l_motor_fwd`; both preconditions
  raise with the field name in the message; the three new dataclasses are frozen; and
  `import configs` still performs **no** filesystem access for the five existing scenarios (D-70 —
  assert by monkeypatching `sim.motor_file.records` to raise and re-importing). Full suite 403 green
  plus this file's own; `configs.names()` prints the same four names — nothing is wired, by design.
- **Commit:** `Step 78 (Phase 2.16): configs/schema.py -- Motor/Airframe/Sections + mass composition`

---

### [Step 79] `configs/motors/` — the registry, the template, the seed motors

- **Module/boundaries:** new `configs/motors/{__init__.py,_TEMPLATE_motor.py,placeholder.py,
  synthetic_large.py,cti_k570.py,cti_k570_isp.py}`; `git add data/motors/Cesaroni_2060K570-17A.eng`
  (currently untracked); `tests/test_config_registries.py` (**the four-package parametrisation
  becomes five — one permitted edit, named in the phase gate**). **`configs/schema.py` is NOT
  edited. No other `configs/` file, no `sim/` file, no `apps/` file, no `run*.py`.**
- **Assignee:** developer
- **depends_on:** [Step 78]
- **parallel_safe:** false
- **Spec slice:** §31.5 in full (the registry's three rules and the template's three rules —
  unchanged, now a fifth time); §32.2.1 (`Motor`'s field set); D-73 (which four motors and why);
  §32.9's `data/motors/` table (why the `.eng` file is committed here). `configs/rockets/__init__.py`
  as it stands is the template for the new registry file. Nothing else.
- **Do:** `configs/motors/__init__.py`, a ~20-line copy of the existing registry shape — explicit
  `_MODULES` tuple, `MOTORS` keyed off `m.MOTOR.name`, `names()`, `get()` whose `KeyError` lists
  every name, the import-DAG note, and the standing rule that `_TEMPLATE_motor` is never in
  `_MODULES`. Four seed modules per D-73: `placeholder` (`Thrust(motor_curve="placeholder.csv")`,
  `mass_model="none"` — the one the seeds will use, and its docstring must carry forward
  `demo_75mm`'s judgment-call note verbatim: **do not "fix" it to `synthetic_large.csv`**, the
  exact-equality pin depends on it); `synthetic_large` (same shape, the App-3 curve);
  `cti_k570` (`.eng`, `mass_model="endpoints"`, every mass field `None` so the header supplies them —
  a three-line literal, with the measured `I_sp_eff = 212.41 s` and `J = 2062.22 N·s` recorded in
  its `notes` as provenance); `cti_k570_isp` (same curve, `mass_model="isp"`, `I_sp=212.41`
  hand-entered — its docstring says it exists to make D-59's equivalence directly comparable).
  `_TEMPLATE_motor.py` per §31.5's three rules **and** already written to §32.8's documentation
  convention, so Step 82 has nothing to do to it.
- **Check:** `tests/test_config_registries.py`'s five-package parametrisation green (basename
  equality, no duplicate names, `names()` covers the dict, unknown-name `KeyError` lists every name,
  no circular import in a fresh interpreter with `configs.motors.<each>` imported first, template
  imports cleanly and is absent from the registry); `motors.get("cti_k570").thrust.motor_curve ==
  "Cesaroni_2060K570-17A.eng"`; the two CTI motors' compositions against a common airframe give the
  same `m`/`m_d`/`l_d`/`I_d` and `I_sp` agreeing to 1e-3 relative — **D-59's equivalence, as a
  test**. `git status` shows the `.eng` file tracked. Full suite green, count up by the five-package
  parametrisation only; `configs.names()` unchanged (motors are not wired into `assemble` yet).
- **Commit:** `Step 79 (Phase 2.16): configs/motors/ -- registry, template, four seed motors, the real CTI .eng`

---

### [Step 80] The switch-over — `Rocket` loses its motor, `Scenario` gains one

**This is the step the phase's gate exists for.** The only step that can change what an existing
caller sees, and it must be provably a no-op for all five scenario names.

- **Module/boundaries:** `configs/schema.py` (`Rocket`: `weight`→`airframe`, `thrust` removed,
  `sections` added; `Scenario`: `motor` added; `assemble`: two keyword sources changed);
  `configs/rockets/{_TEMPLATE_rocket.py,toy_05kg.py,demo_75mm.py}`;
  `configs/scenarios/{_TEMPLATE_scenario.py,toy_05kg.py,demo_75mm.py,demo_75mm_airbrake.py,
  demo_75mm_highland.py}`; `tests/test_config_pieces.py` and `tests/test_config_migration.py`
  (**the two named edits from the phase gate, and nothing else in them**). **No `sim/` file, no
  `apps/` file, no `run*.py`, no `configs/{sites,weather,motors}/` file, no other test file.**
- **Assignee:** developer
- **depends_on:** [Step 79]
- **parallel_safe:** false
- **Spec slice:** §32.2.3 in full (the new `Rocket`/`Scenario`/`assemble`); §32.3.3 (the
  composition's pass-through case — the whole bit-for-bit argument); §32.3.1 **F4** (why
  pass-through is an early return); the phase gate items 3 and 4 above (the four pins and the three
  permitted test edits). Nothing else.
- **Do:** edit `configs/schema.py` per §32.2.3 — `Rocket.weight: Weight` becomes
  `airframe: Airframe` (still the only required group, still first), `thrust` deleted,
  `sections: Sections` appended before `notes`; `Scenario.motor: Motor` inserted after `rocket`;
  `assemble`'s `weight=` becomes the composition call and `thrust=` becomes `sc.motor.thrust`. The
  module docstring's one-owner paragraph gains D-57's amendment. Then the three rocket modules:
  `weight=Weight(m=…, I=…)` becomes `airframe=Airframe(m=…, I=…)` with **the same two numbers and
  the same justifying comments**, and `thrust=Thrust(...)` is **deleted** — its comment (including
  `demo_75mm`'s judgment-call note) moves to `configs/motors/placeholder.py`, written in Step 79, and
  the rocket's docstring gains one line saying where its motor went. `sections` is left at its
  default for both seeds (they have no measured geometry — say so in one comment rather than
  inventing numbers). Then the five scenario modules: `motor=placeholder.MOTOR` imported
  `from configs.motors.placeholder import MOTOR`, one line each, nothing else changed — `notes`
  strings **byte-for-byte**, `s0` still omitted.
- **Check:** the gate, in this order, pasted into the step report:
  1. **The four exact-equality pins in `tests/test_configs.py` green, unedited** — the proof that
     the composition's pass-through reproduces `Weight(m=1.5, I=0.08)` and `Weight(m=0.5, I=0.05)`
     bit-for-bit and that `thrust` arriving from a different piece changes nothing.
  2. **`git diff -- tests/` shows exactly the two named edits** (`test_config_pieces.py`'s helpers
     and six `Scenario(...)` keywords; `test_config_migration.py`'s two piece-slice tests retargeted
     from `rocket.weight`/`rocket.thrust` to `get(...).params.weight`/`.params.thrust`) and nothing
     else. **No assertion's expected value changes anywhere in the suite.**
  3. `python -c "import configs; print(configs.names())"` prints the same four names;
     `get("demo_75mm").params == get("demo_75mm_airbrake").params` still holds;
     `get("demo_75mm_highland").params.weight == get("demo_75mm").params.weight` still holds (Step
     74's one-rocket-two-sites assertion, now also one-motor-two-sites).
  4. **All five entry points run from a clean checkout** (`run.py`, `run_motor_sweep.py`,
     `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py`), and App 3's printed table and
     `output/motor_selection.csv` are **byte-identical** to a pre-step capture — the Step-64/69/73
     gate, re-run because this step is what could break it.
  5. `python -c "import configs.rockets._TEMPLATE_rocket"` and the scenario template still import
     cleanly and stay absent from every registry.
  6. `git diff --stat` shows only the Module/boundaries files.
- **Commit:** `Step 80 (Phase 2.16): the motor leaves the rocket -- Scenario gains a Motor piece`

---

### [Step 81] One worked demo — the real CTI K570 with the mass model on

Without this step the phase ships with the variable-mass model still unexercised from the config
layer: after Step 80 every scenario uses `placeholder` with `mass_model="none"`, so **nothing in the
tree flies a real motor, and `Weight.m_d` is still `None` everywhere** — which is exactly the state
B15 complained about.

- **Module/boundaries:** new `configs/rockets/demo_75mm_k570.py`; new
  `configs/scenarios/demo_75mm_k570.py`; `configs/rockets/__init__.py`,
  `configs/scenarios/__init__.py` (one `_MODULES` line each); `tests/test_config_migration.py`
  (append only). **No `sim/` file, no `apps/` file, no `run*.py`, no other test file, no
  `configs/motors/` file.**
- **Assignee:** developer
- **depends_on:** [Step 80]
- **parallel_safe:** false
- **Spec slice:** §32.2 (the field sets being filled in); §32.3.3/§32.3.4 (what the composition will
  produce, and that burnout mass must land on `m_f`); §32.5 (the station convention — this is the
  first module to carry real stations); §32.3.1 **F5** (the K570's measured numbers). Nothing else.
- **Do:** one airframe sized for a 54 mm motor — `demo_75mm_k570`, a *new* rocket piece (do **not**
  edit `demo_75mm`, whose numbers are pinned) with `Airframe(m=…, I=…, l=…)` and a real `Sections`:
  `L_total`, `l_nose`, the fin-root pair, and `l_motor_aft = L_total` for an aft-flush install, every
  number commented as synthetic-but-plausible in the same voice `highland_1500m` already uses. One
  scenario pairing it with `cti_k570` at `origin_msl`/`isa_dry_calm`. Its `notes` state in one line
  what it demonstrates: a real vendor motor, its own mass history, composed with an airframe that
  knows where the motor sits.
- **Check:** it flies (picked up by the existing parametrised "every registered scenario flies"
  test — **note in the report that the count rises with no test edit**, expected, not an anomaly);
  `params.weight.m_d is not None` (**the mass model is on for the first time from a config**);
  `params.weight.m == airframe.m + 1.685` and `m_d == airframe.m + 0.695`;
  `params.weight.I_sp == pytest.approx(212.41, abs=0.01)`; `l_d` and `l_p` are both plausible
  nose-tip stations inside `[l_nose, L_total]` — the station-convention sanity check; and the
  headline assertion, **burnout mass lands on `m_f`**: integrate to burnout and assert
  `result.y[M][-1] == pytest.approx(airframe.m + 0.695, rel=1e-4)`, which is D-59's claim measured on
  a real curve rather than argued. Also assert the two CTI motors (`cti_k570` vs `cti_k570_isp`) flown
  on this airframe give apogees agreeing to ~0.1 % — the equivalence, end to end. Full suite green,
  no test file edited (appends only to this phase's own file). `--list-configs` now prints five
  names: an intended, user-visible change; state it.
- **Commit:** `Step 81 (Phase 2.16): demo_75mm_k570 -- a real CTI motor, mass model on, burnout mass pinned`

---

### [Step 82] Templates documentation pass — REQ/OPT, units, one line each

- **Module/boundaries:** `configs/rockets/_TEMPLATE_rocket.py`,
  `configs/motors/_TEMPLATE_motor.py`, `configs/sites/_TEMPLATE_site.py`,
  `configs/weather/_TEMPLATE_weather.py`, `configs/scenarios/_TEMPLATE_scenario.py`;
  `sim/params.py` (**one stale comment on `Lengths.l2`, §32.5 — comment only**); new
  `tests/test_template_docs.py`. **No other file. Zero behaviour change —
  `git diff` must show only comments and docstrings.**
- **Assignee:** developer
- **depends_on:** [Step 80]
- **parallel_safe:** false (shares `configs/motors/` and `configs/rockets/` with Step 81)
- **Spec slice:** §32.8 in full (the inline convention's three rules, the table format, the
  auditability test); §32.5's stale-comment note; §32.6's `table`-not-`data` naming note. Nothing
  else.
- **Do:** bring every field of all five templates to
  `# REQ|OPT, <unit or choices> -- <one line>`, per §32.8's three rules, keeping the existing good
  block comments above the fields they explain. Append the per-field table to each template's module
  docstring, with the `default` column. Fix `sim/params.py:69`'s `l2` comment to say
  **CoP → thrust point** (what the code does, §32.5) — one line, no behaviour. Where a template
  mentions the third aero model, write `table` and note "(the data-table model)" once (§32.6).
- **Check:** new `tests/test_template_docs.py`, parametrised over the five templates: the docstring
  table's row set **equals** `{f.name for f in dataclasses.fields(T)}` for the type each template
  constructs (the auditability check — an undocumented new field fails here); every table row's
  second cell is exactly `REQ` or `OPT`; every inline comment on a line inside the constructor call
  matches `^#\s(REQ|OPT),\s` (parse the file with `ast` + the source lines rather than regexing
  blind). Every template still imports cleanly and is still absent from its registry (§31.8 #6,
  already pinned). Full suite green; **`git diff --stat` shows comment/docstring lines only** — if
  any test's expected value moves, the step has changed behaviour and is wrong.
- **Commit:** `Step 82 (Phase 2.16): every template field documented -- REQ/OPT, unit, one line`

---

### [Step 83] `configs/` and `data/` cleanup — the audit, and the one `git add`

Per D-72 this step **deletes nothing**. It exists so the audit is recorded in the tree rather than
only in this document, and so a future reader does not re-ask "why are there four synthetic motors".

- **Module/boundaries:** new `data/motors/README.md`; new `data/soundings/README.md`;
  `data/aero/` — untouched; `configs/__init__.py` (**docstring only** — the "how do I add my own"
  guide gains the motors directory). **No `.py` file's code, no `sim/`, no `apps/`, no test file, and
  no file deleted anywhere.**
- **Assignee:** developer
- **depends_on:** [Step 79]
- **parallel_safe:** true (against Step 82 — disjoint boundaries; sequence after Step 80 for a clean
  baseline)
- **Spec slice:** §32.9 in full (the three keep tables and the ISA confirmation); D-72. Nothing else.
- **Do:** two short `README.md` files recording, per file, **what it is and who reads it** — the
  §32.9 tables, trimmed to one line per file, so "can I delete this?" is answerable from the
  directory itself. `data/motors/README.md` additionally states the format rules a new file must
  follow (`.csv` = two columns with a `#` header; `.eng`/`.rasp` = RASP, `(0,0)` prepended on load,
  `#designation` selects a record from a library) and that the four `synthetic_*.csv` are **one**
  deliberate comparison set including an equal-impulse pair. `data/soundings/README.md` records the
  three-category split (single-station synthetic, multi-station field, real fetched artifact) and
  that `example_live/` is real data. `configs/__init__.py`'s guide docstring gains `motors/` in its
  directory list. Confirm in the step report that `configs/` needed no trimming and that the ISA
  reading is correct (a dispatch key, not a file).
- **Check:** full suite green, unchanged count (this step adds no test and touches no code);
  `git diff --stat` shows two new `.md` files and one docstring; `git status` shows **no deletions**.
  Report the per-file keep list as the deliverable.
- **Commit:** `Step 83 (Phase 2.16): data/ READMEs -- what each file is and who reads it; nothing deleted`

---

### [Step 84] LaTeX sync — the composition, the effective `I_sp`, the propellant's own inertia

- **Module/boundaries:** `docs/latex/sections-ai/models.tex` (§`sec:mass` only);
  `docs/latex/sections-ai/rocket-2d.tex` (§`sec:geometry`, **one added paragraph** on absolute
  stations). **No code file, no test file.**
- **Assignee:** developer
- **depends_on:** [Step 77]
- **parallel_safe:** true (touches no code file — the Step-54 precedent)
- **Spec slice:** §32.3.1 **F2** (the static reduction, which is the new mathematical content);
  §32.3.4 (the `I_sp_eff` equivalence); §32.3.5 (the exact endpoint inversion and `I_p_spec`);
  §32.5 (the station convention paragraph). Read `models.tex` §`sec:mass` whole (~60 lines) and
  `rocket-2d.tex:77-104`.
- **Do:** in `models.tex` §`sec:mass`, add before the existing two-lump statement a short
  **composition** subsection: an N-lump rigid composition (mass-weighted centroid + parallel axis),
  then the observation that an airframe and a motor casing are static relative to one another, so the
  N-lump vehicle reduces **exactly** to the two-lump model already written there with
  `(m_d, l_d, I_d)` reinterpreted as the combined dry assembly — i.e. the existing equations are
  unchanged and are now *derived* rather than postulated. Add a short **mass-model** paragraph giving
  both `\dot m = -T_{ref}/(I_{sp}g_0)` and the endpoint form, and stating the equivalence
  `I_{sp,eff} = J/(m_p g_0)` with `J` the curve's total impulse. Replace the `I_p(t) \propto m_p(t)`
  placeholder sentence's *implementation* note: the proportionality stands, but the constant is now
  the propellant's own specific inertia where known (`I_p_spec`) rather than the structure's, and the
  `\todo` about grain geometry stays and is now cross-referenced to **B24**. In `rocket-2d.tex`
  §`sec:geometry`, add one paragraph stating the station convention explicitly — every dimension is
  given as a positive distance aft of `A`, the negative sign belongs to the body-frame vector
  equations already on the page, and `l_B`/`l_C`/`l_D` relate to the implementation's relative
  `l_1 = l_D - l_B`, `l_2 = l_C - l_D` (§32.5's table) — which closes a documentation gap that
  predates this phase.
- **Check:** `pdflatex` (or the project's usual build) succeeds with no new warnings; every new
  `\label`/`\autoref` resolves; **no equation already in the document changes**, which is the whole
  claim of F2 and is what a reviewer should verify first; the `\todo` about grain geometry is still
  present. No code touched, so the suite is green by construction — run it anyway and report 403+.
- **Commit:** `Step 84 (Phase 2.16): models.tex -- rigid-lump composition, effective I_sp, propellant inertia`

---

### Not in this ticket set, deliberately

- **B24 and B25** — the two TODOs the user explicitly asked to record and not implement (§32.7).
- **Deriving `Lengths.l1`/`l2` from the new stations**, and with it `architecture.md` §19's
  `l1(t)`/`l2(t)` question (D-68) — needs the §19 physics settled and B25's airframe CoG.
- **Migrating `apps/motor_selection/motors.py`'s `MOTORS` list into `configs/motors/`** (D-73) — a
  sweep list is a study input (§30.3), not a motor piece; convergence options in §32.13.
- **The ad-hoc composition CLI** (`--rocket/--motor/--site/--weather`) — still D-54a's deferred step,
  now with one more axis to add when it happens.
- **Unifying `thrust_curve.thrust`'s `left=` on `0.0` for `.csv` too** (D-64's note) — a bit-for-bit
  review of five fixtures, its own step.
- **Tracker, `docs/roadmap.md` and `status.json` updates** — the orchestrator's, not a developer
  ticket. A `docs/architecture.md` §32 pointer section is also the orchestrator's.

---

## 32.12 Risks

1. **The composition hides provenance that used to be a literal.** After Step 80, "why is `m_d`
   1.79 kg?" is answered by a function, not by a commented number in a config module — the
   indirection complaint §31.1 raised against `.derive()`, now in a different place. *Mitigation:*
   the composition is 20 lines in one place with every intermediate named; Step 79's `cti_k570`
   records its measured `J` and `I_sp_eff` in `notes`; and Step 81's report prints the composed
   `Weight` so the numbers exist in the project's history. A `--explain-mass` dump is a cheap later
   addition if this bites.
2. **Pass-through is the entire bit-for-bit argument, and it is one `if`.** If Step 78's
   `mass_model == "none"` early return is ever "simplified" into `combine(single_lump)`, F4 says five
   of fifty-six realistic numbers move by an ULP — and the four exact-equality pins would fail
   loudly, which is the mitigation. The risk is that someone *fixes the test* instead. *Mitigation:*
   F4's counterexample is written into the function's own docstring and into
   `tests/test_motor_pieces.py`'s pass-through test, both naming the pins they protect.
3. **`combine` and `moment_of_inertia` compute the same thing in two places.** F3's measured
   one-ULP disagreement is *why* they are separate, but two implementations of the parallel-axis
   theorem is still two implementations. *Mitigation:* Step 75's test asserts they agree to 1e-15 on
   the two-lump case, so a real divergence (a sign, a missing term) fails immediately while the ULP
   difference is tolerated by design. Both docstrings point at each other and at F3.
4. **`Sections` and `Lengths` can disagree, and nothing checks it.** A user can state stations that
   are geometrically incompatible with `l1`/`l2` (§32.5's residual). Unlike D-51's rail angle there
   is no structural fix available, because the derivation is blocked on `architecture.md` §19.
   *Mitigation:* notes and documentation only — each template says `l1`/`l2` are authoritative and
   `Sections` is descriptive; `architecture.md` §7's "this project does not own a validator" still
   applies. Recorded as a backlog candidate.
5. **`I_sp_eff` is a derived number that will surprise someone.** A user who enters
   `mass_model="endpoints"` and then reads `params.weight.I_sp = 212.41` may reasonably think the
   project invented a specific impulse. *Mitigation:* the composition's docstring, the motor
   template's comment on `mass_model`, and `cti_k570`'s `notes` all state the equivalence and the
   formula; Step 81 pins the consequence (burnout mass lands on `m_f`) so the number is checkable
   rather than magic.
6. **The uniform-cylinder geometry default is wrong in a known direction.** It over-estimates a
   thin-walled casing's transverse MOI and under-estimates a cored grain's, by `O(r²/L²)` — ~0.3 %
   of the `L²` term for the K570, negligible here, *not* negligible for a short fat motor
   (`L ≈ 2r`). *Mitigation:* `uniform_cylinder_I`'s docstring states the direction and the scaling;
   B24 is the fix; and any motor where it matters can override all four geometry fields.
7. **Reading a motor file at import time is new behaviour for this package.** A missing or malformed
   data file can now break `import configs` where before it broke only `run_sim`. *Mitigation:*
   D-70's gate — only `mass_model != "none"` reads anything, every pre-phase seed stays on the
   `"none"` path, and Step 78's test asserts the five existing scenarios import with
   `sim.motor_file.records` monkeypatched to raise.
8. **Three test files are edited, so "the suite is green" is a weaker gate than it was in Phase
   2.15.** *Mitigation:* the permitted edit set is enumerated in the phase gate *before*
   implementation, every edit is mechanical (a helper's kwargs, a retargeted attribute path, a
   parametrisation list), **no expected value moves anywhere**, and `git diff -- tests/` is a
   per-step check. An unexpected fourth edited file is a design failure, not a gate to relax.
9. **The RASP grammar is inferred, and the only real sample in the repo is one file.** `delays` is
   free text, the record delimiter is "the next non-float-leading line", and some real-world `.eng`
   files carry trailing comments, CRLF line endings, `*` continuation marks or seven-plus header
   fields. *Mitigation:* F5's independent check (the parsed impulse matches the designation to
   0.108 %) is strong evidence for this file; Step 76's tests include a hand-built two-record library
   and a blank-line-free concatenation; and the failure mode of an unparsed variant is a loud
   `ValueError` at load, not a wrong trajectory. Widening the grammar is a localised later edit to
   one function.
10. **Five pieces per scenario is one more place to look.** Phase 2.15's risk 9, now with a motor.
    *Mitigation:* `get_scenario(name)` already exposes the composition, and a scenario module is
    still five imports and a `notes` string — one screen.
11. **`demo_75mm`'s `placeholder.csv` judgment call moves to a new file and could be "fixed" there.**
    Step 63 chose `placeholder.csv` over `synthetic_large.csv` because the exact-equality pin against
    `_demo_baseline()` depends on it; Step 73 re-confirmed it; Step 80 moves that choice into
    `configs/motors/placeholder.py`, one directory further from the test that depends on it.
    *Mitigation:* the note is carried verbatim into the new module's docstring by Step 79's ticket,
    and the pin fails loudly if anyone acts on the temptation.

---

## 32.13 Rejected options, and backlog candidates

**Rejected: a thirteenth `Params` group for motor mass** (D-56b). The composition is a *constant*
(F2), so a per-RHS-call group buys nothing and costs the engine's public contract plus a
`sim/dynamics.py` edit plus two groups claiming the vehicle's mass — the two-owner ambiguity D-49
exists to prevent.

**Rejected: `Scenario.motor: Motor | None = None` with a `Rocket.thrust` fallback** (D-58b). Zero
caller edits, but two owners for `Params.thrust` for an indefinite period and a fallback branch in
`assemble` that nothing would ever remove. Phase 2.15 bought backward compatibility because it was
*free*; here it is not, and the price is the invariant.

**Rejected: time-linear `l_COG(t)`/`I(t)`** (D-60b). Contradicts `main.tex` §`sec:mass`, is worse for
every curve in this repo, needs a burn duration the curve already implies, and would be a second mass
model to keep tested. Recorded as a ~15-line additive third `mass_model` value if the user wants it
after reading §32.3.5 — nothing here forecloses it.

**Rejected: deriving `Lengths.l1`/`l2` from the new stations now** (D-68b). It would contradict the
`"table"` aero model's own `l1(α, M)` — the exact leak Step 55 closed — and would answer
`architecture.md` §19's open `l1(t)`/`l2(t)` question as a side effect of a config refactor.
**Backlog candidate**, paired with B25.

**Rejected: a `tools/eng_to_csv.py` converter** — which is what **B14** originally proposed. It
discards the header at exactly the moment the mass model needs it, which B14's own entry anticipates
("the header's propellant/total-mass fields are also exactly the data **B15** needs"). A reader that
keeps the metadata supersedes it, and B14 should be marked closed-by-§32 rather than done.

**Rejected: changing `thrust_curve.thrust`'s `left=` to `0.0` for every format** (D-64c). Breaks
bit-for-bit for five existing `.csv` configs, and the hold is a documented deliberate choice.
**Backlog candidate:** audit whether any fixture actually relies on the hold and, if none does,
unify in a later step with its own review.

**Rejected: migrating App 3's `MOTORS` list into `configs/motors/`** (D-73c). A sweep list is a
*study* input (§30.3's two-kinds convention, D-32, §31.11), and a `MotorEntry` carries per-motor
**airframe** overrides — casing mass, body diameter, the resulting geometry — which are a study delta,
not properties of a motor. **Backlog candidate:** have `MotorEntry` reference a registered `Motor`
piece by name instead of carrying a bare `motor_curve` string, which would let the mass overrides it
currently fakes come from the real composition. That is the honest convergence, and it is additive.

**Rejected: validating `Sections` against `Lengths`, or the endpoint inputs against physicality,
at assembly.** `architecture.md` §7 — this project does not own a validator. The two *preconditions*
the composition cannot default (a missing `Airframe.l`, an ambiguous motor station) raise with a
field name, which is an error message on an exception that would be raised anyway, not validation.
A negative `I_prop0` from inconsistent endpoint inputs is left to propagate: it is information (the
two endpoints are not reachable by any two-lump motor) and clamping it would hide that.

**Rejected: a `Grain` sub-piece now.** That is **B24**, and `main.tex` §`sec:mass` lists exactly
which inputs it needs and says they are not chosen yet. Designing the field set before the grain
family is chosen would be inventing the data format §29's **B15** deliberately declined to invent.

**Backlog candidates this phase opens** (numbering beyond B24/B25 to be assigned by the orchestrator
against `docs/roadmap.md`, not claimed here):

- `Lengths.l1`/`l2` derived from absolute stations, and with them `architecture.md` §19's
  `l1(t)`/`l2(t)` travelling-CoG question (D-68b; needs B25).
- `MotorEntry` referencing a registered `Motor` piece by name, so App 3's per-motor casing-mass
  overrides come from the real composition instead of being hand-faked (D-73).
- Unifying the pre-ignition convention on `left=0.0` for `.csv` as well as RASP (D-64).
- A `--explain-mass` dump printing the composition's intermediates for a named scenario (risk 1).
- Carrying a RASP record's own `;` comment block into `MotorRecord.notes` and through to the
  `Motor` piece's provenance (§32.4).
- `Weather.site_hint`, the `Fidelity` piece, `s0.m` derived from `weight.m`, and the ad-hoc
  composition CLI — all still open from §31.11, none touched here. The CLI now has a fourth axis.

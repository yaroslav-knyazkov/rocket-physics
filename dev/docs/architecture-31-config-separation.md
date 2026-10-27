# Architecture §31 — Config separation: rocket / launch site / atmosphere (Phase 2.15, design only)

> Superseded 2026-10 by the Phase 2.18 pivot (`dev/docs/pivot-configs-and-packaging-analysis.md`); the
> registry this document describes is archived at `dev/archive/configs-registry-2026-10/`.

## Summary

**Status: user-approved 2026-10-14, all eleven decision forks settled as recommended; implementation
tickets are §31.12 (Steps 71-74); no code written yet.** Design for the user's 2026-10-13 request:
*"start developing config separation between rocket, atmosphere, launch site."*
Today a `configs/<name>.py` module is **one** `Config` carrying a whole `Params` tree (§30.4), so
"my rocket at my field in today's air" and "my rocket at a hypothetical high site" cannot share the
vehicle numbers without copy-paste or a `.derive()` override chain. This document splits the
*authoring* layer into three reusable pieces — **`Rocket`**, **`LaunchSite`**, **`Weather`** — plus a
**`Scenario`** that names one combination of the three and assembles them into exactly the ordinary
`Params` + `State` the simulator already takes.

**`sim/params.py` is not touched.** `Params` and its twelve group dataclasses stay the engine's
public contract; the split lives entirely in `configs/`, and the whole design rests on one invariant:
**every one of the twelve groups has exactly one owning piece**, so assembly is a single 15-line
total function with no merge logic (§31.4, D-49).

Group placement (§31.3): `weight`/`lengths`/`thrust`/`aero`/`recovery`/`control` → **rocket**;
`site` → **launch site**; `atmosphere`/`soundings`/`wind` → **weather** (one piece, because a
sounding *is* one measurement of air **and** wind, and `soundings.case` is read by both
`sim/atmosphere.py` and `sim/wind.py` — the only genuine two-owner conflict in the schema, F4);
`gravity`/`solver`/`g0` → **scenario-level fields**, no fourth registry.

**Backward compatibility is proposed as a first-class goal, not a side effect (D-45).** The blast
radius is smaller than it looks: of the 19 files flagged by the orchestrator, **11 touch the config
API at all**, and all 11 use only `.params`, `.s0`, `.name`, `.notes`, `.derive`, `.with_variant`,
`configs.get`, `configs.names`, `configs.CONFIGS` (§31.6, verified by grep, file by file). Keeping
`Config` byte-identical and having each scenario module still export `CONFIG = SCENARIO.config` makes
the recommended design a **zero-caller-edit, zero-test-edit** change — including
`tests/test_configs.py`'s `configs.CONFIGS[basename] is mod.CONFIG` identity pin, which is what
forces eager, import-time assembly (F8).

The three seed scenarios survive bit-for-bit (§31.7): two new "pin the defaults" pieces
(`sites/origin_msl.py` = `Site()`, `weather/isa_dry_calm.py` = `Atmosphere()`+`Soundings()`+`Wind()`,
both deliberately argument-free) reproduce today's implicit defaults exactly, and the four existing
exact-equality tests in `tests/test_configs.py` become the migration gate unchanged. Measured and
relevant: `math.radians(90.0) == math.pi / 2` is **exactly true** in CPython, so deriving `s0.theta`
from `site.rail_angle_deg` (D-51 — which turns the user's own template comment *"keep equal … nothing
cross-checks them for you"* into a structural guarantee) is provably free for all three seeds.

Eleven decision forks, **D-45 … D-55** (§31.9), continuing §30.10's D-28 … D-42 and skipping
D-43/D-44 (used by Phase 2.14). **All eleven were answered on 2026-10-14 with the recommended
option**, so §31.3-§31.8 read as settled design, not as proposals. Added at approval: each of the
four piece types ships **both** a blank, heavily-commented `_TEMPLATE_*.py` module **and** a filled-in
module built from real migrated seed data (§31.5, §31.12). One honest amendment the ticketing
exposed: D-45's "zero test edits" cannot be literally true alongside D-55a, because
`tests/test_configs.py:206` imports `configs.demo_75mm` *by module path* and that module moves —
so the gate is "no test edits **other than the two module-path strings the move itself renames**",
one test function, no assertion changed (§31.6, Step 73).

---

## Contents

- [§31.1 Scope — what this is, and what it is not](#311-scope--what-this-is-and-what-it-is-not)
- [§31.2 Findings — read from the code, and one measured](#312-findings--read-from-the-code-and-one-measured)
- [§31.3 Where the twelve groups go](#313-where-the-twelve-groups-go)
  - [§31.3.1 `recovery` and `control` — vehicle subsystems or their own axis](#3131-recovery-and-control--vehicle-subsystems-or-their-own-axis)
  - [§31.3.2 `gravity`, `solver`, `g0` — the run-level leftovers](#3132-gravity-solver-g0--the-run-level-leftovers)
  - [§31.3.3 `wind` and `soundings` — the one real two-owner conflict](#3133-wind-and-soundings--the-one-real-two-owner-conflict)
  - [§31.3.4 `site` — pad geodesy and rail, kept whole](#3134-site--pad-geodesy-and-rail-kept-whole)
- [§31.4 Composition: `Scenario` → `Config`](#314-composition-scenario--config)
- [§31.5 Registries and the directory layout](#315-registries-and-the-directory-layout)
- [§31.6 Backward compatibility — the blast radius, file by file](#316-backward-compatibility--the-blast-radius-file-by-file)
- [§31.7 Migrating the three seed configs, provably](#317-migrating-the-three-seed-configs-provably)
- [§31.8 Test strategy (additions only)](#318-test-strategy-additions-only)
- [§31.9 Decision points for the user (D-45 … D-55) — all answered 2026-10-14](#319-decision-points-for-the-user-d-45--d-55--all-answered-2026-10-14)
- [§31.10 Risks](#3110-risks)
- [§31.11 Rejected options, and backlog candidates](#3111-rejected-options-and-backlog-candidates)
- [§31.12 Implementation tickets (Steps 71-74)](#3112-implementation-tickets-steps-71-74)

---

## 31.1 Scope — what this is, and what it is not

### Current state, and why it is being revisited

§30.4 is the design rationale for the current system and this document does not re-derive it. Its
load-bearing decisions stand and are **not** reopened here:

- **One module per config, git *is* the history** (D-30). No registry file, no database, no revision
  scheme.
- **Python literals** (D-23/D-31). `None` is a meaningful value, every number is justified in a
  comment beside it, and this project does not own a parser or a validator (architecture.md §7).
- **The registry is an explicit tuple, not directory auto-discovery.** A half-finished draft must not
  appear by merely existing, and "who uses this config" must stay one grep.
- **Config modules import `from configs.schema import X`, never `from configs import X`** —
  `configs/__init__.py` imports the config modules, so reaching back into the package namespace is a
  circular import.
- **A name is bound at registration**, not inferred from the filename
  (`tests/test_configs.py::test_registry_keys_equal_module_basenames` pins that a mismatch cannot
  happen silently).

What §30.4 did *not* decide, because nothing yet needed it, is whether a `Config` is the right unit of
**authoring**. It is the right unit of **consumption**: `run_sim(params, s0)` needs one complete
`Params`, every app takes a `Config`, and §30.4's "complete, runnable scenario" framing is exactly
what made Step 69's migration provable. The defect is one level up. `configs/demo_75mm.py` and
`configs/demo_75mm_airbrake.py` are two modules that contain the same vehicle (literally — the second
is `derive(overrides={})` of the first), and the user's own template (`_TEMPLATE_my_rocket.py`, their
branch) carries a vehicle *plus* a commented-out launch site *plus* a commented-out atmosphere in one
file, with the instruction "leave this group out entirely to get these exact defaults". Flying the
same vehicle from two sites, or the same site under ISA and under a real sounding, means copying that
file or writing a `.derive()` chain whose overrides silently become the real source of truth for the
numbers they touch.

**The orchestrator's read of the motivation is confirmed**, with one addition: the pain is not only
re-typing. `.derive()` moves a number *out* of the commented literal that justifies it and *into* an
override dict in another file — which is precisely the "every config's actual values become indirect"
failure mode §30.10's D-31(c) rejected. Reuse by composition keeps each number in exactly one
commented literal; reuse by override does not.

### In scope

The `configs/` authoring layer: new piece types, a `Scenario` composition object, the registry and
directory layout, and the migration of the three seeds.

### Explicitly out of scope

- **`sim/` — all of it.** `sim/params.py`, `Params` and the twelve group dataclasses are unchanged.
  This phase has no `sim/` step at all (unlike Phase 2.13, whose Step 65 was its one gate).
- **No new physics, no new dependency, no `docs/latex/` pass.**
- **`apps/*/` study inputs do not move.** `apps/motor_selection/motors.py`,
  `apps/airbrake_sizing/targets.py` and `apps/weight_aero_tradeoff/scenarios.py` are study-level
  deltas per §30.3's two-kinds convention; a motor list is not a rocket piece (see §31.11).
- **`Variant` is unchanged** and keeps operating on `Config`.
- **Implementation tickets.** Per the user's own Phase 2.13 flow (design doc → approval → Steps
  63-69), tickets are written after the forks in §31.9 are answered.

---

## 31.2 Findings — read from the code, and one measured

Everything load-bearing below was read from this tree, not assumed. These are the facts that decide
§31.3 and §31.4.

**F1 — the atmosphere already depends on the site, and it is a clean dependency.**
`sim/gravity.py:291` computes `altitude_msl = altitude_agl(y, p) + getattr(p.site, "h0_m", 0.0)`, and
every atmosphere model is a function of that MSL altitude. So a `Weather` piece's ISA column is
evaluated at the `LaunchSite` piece's elevation — *in effect* coupled, but **not** in field ownership:
the `Atmosphere` group holds only `model` and `humid_air`. No conflict; the coupling is exactly the
mix-and-match the user asked for (same air model, two site elevations, different answers).

**F2 — `gravity.R_e` is consumed as an Earth constant by the sounding geodesy, not only by the
gravity model.** `sim/soundings.py:465-478` projects sounding-station lat/lon into the local tangent
plane with `E = p.gravity.R_e * cos(phi0) * dlon`, `N = p.gravity.R_e * dlat`. So `Gravity` is not a
self-contained "gravity model" group — it also carries the world radius the weather data layer uses.
That rules out attaching `gravity` to the rocket, and weakens attaching it to a *single* site (the
constant is global; only the latitude it is evaluated at is site-specific).

**F3 — wind is rotated into the flight plane by `site.azimuth_deg`.** `sim/wind.py:279`
(`delta = radians(p.wind.dir_deg - p.site.azimuth_deg)`), `:352`, `:379`, and `sim/soundings.py:570`.
Again an effect-level coupling with no field conflict: a meteorological wind direction is
site-independent data; the pad heading that turns it into a crosswind is the site's.

**F4 — `soundings.case` has two consumers, and that is the only two-owner conflict in the schema.**
`sim/atmosphere.py:195`/`:240` and `sim/wind.py:349`/`:377` both read `p.soundings.case` (and
`Soundings`' own docstring, `sim/params.py:119`, says so outright: "the shared data layer for
atmosphere AND wind tiers 2/3"). If `atmosphere` and `wind` were owned by two different pieces, both
would need to write `Soundings`, and assembly would need field-level merge logic with a conflict
policy. Physically there is nothing to merge: one radiosonde flight yields temperature, pressure,
humidity **and** the wind vector for one place at one time.

**F5 — `s0` and `site.rail_angle_deg` are two numbers that must agree, and nothing enforces it.**
`sim/dynamics.py:177` builds the rail direction from `p.site.rail_angle_deg`; the initial attitude
comes from `s0.theta`. The user's own template says it in a comment: *"keep `site.rail_angle_deg`
equal to this angle's degrees value — the rail direction and the initial attitude are two separate
numbers and nothing cross-checks them for you."* A split that gives the site piece the rail is the
natural place to fix this (D-51).

**F6 — measured: `math.radians(90.0) == math.pi / 2` is exactly true** (difference `0.0`, both
`1.5707963267948966`); `math.radians(85.0) == 85 * math.pi / 180` likewise. CPython's `math.radians`
is a single multiply by `pi/180`, and for 90.0 the rounding happens to land on the same double as
`math.pi / 2`. All three seed configs use `theta=math.pi / 2` and would take `rail_angle_deg=90.0`,
so a derived `s0` is **bit-for-bit free for every existing config** — not approximately, exactly.

**F7 — `L_rail`/`rail_angle_deg` in `Site` is already a decided question.**
`docs/architecture-28-rewrite.md:305`: *"`L_rail`/`rail_angle_deg` go in `Site`, not `Recovery`. The
rail is pad infrastructure."* This document does not relitigate it; it only notes that the rail
*angle* is a per-flight choice living in a per-site piece (§31.3.4).

**F8 — the existing registry test pins object *identity*, which forces eager assembly.**
`tests/test_configs.py:82`: `assert configs.CONFIGS[basename] is mod.CONFIG`. A lazily computed
`Scenario.config` property returning a fresh `Config` on each access would fail that `is`. Therefore
each scenario module must bind `CONFIG = SCENARIO.config` once at import (§31.4). This is also the
cheaper option — 13 frozen-dataclass constructions per scenario, once, at import.

**F9 — the real blast radius is 11 files, not 19.** Verified by grep over the orchestrator's list:
`run_airbrake.py`, `run_cfd_conditions.py`, `run_motor_sweep.py`, `apps/common/artifacts.py`,
`apps/common/flight_stats.py`, `apps/airbrake_sizing/targets.py`, `tests/test_apps_common.py` and
`tests/test_control.py` contain the string `config` **only in docstrings, comments and doc
references** — none of them imports `configs` or touches a `Config` object (`flight_stats(result, p)`
takes a `Params`; the wrappers forward `sys.argv` strings). `run_trade.py` forwards `--config` as an
argument string and never resolves it. Full table in §31.6.

**F10 — every real consumer uses six members and nothing else.** Across the 11 files: `cfg.params`,
`cfg.s0`, `cfg.name`, `cfg.notes`, `cfg.derive(...)`, `cfg.with_variant(...)`, plus `configs.get`,
`configs.names`, `configs.CONFIGS`, `configs._MODULES` (tests only) and `Config` as a *type
annotation*. **No `isinstance(x, Config)` check and no `dataclasses.replace(cfg, ...)` exists
anywhere outside `configs/schema.py`** — so the only compatibility requirement is that `configs.get`
keeps returning a real `Config` with those six members.

---

## 31.3 Where the twelve groups go

The three pieces, named for the user's own three axes, plus the leftovers:

| `Params` group | Owner | Why |
|---|---|---|
| `weight` | **Rocket** | the vehicle's mass and pitch inertia |
| `lengths` | **Rocket** | airframe geometry |
| `thrust` | **Rocket** | the motor it flies with (nozzle area, reference pressure, curve) |
| `aero` | **Rocket** | its own aerodynamic model and coefficients |
| `recovery` | **Rocket** | parachute hardware bolted to it (§31.3.1, D-46) |
| `control` | **Rocket** | airbrake hardware bolted to it (§31.3.1, D-46) |
| `site` | **LaunchSite** | pad geodesy + rail, kept whole (§31.3.4, F7) |
| `atmosphere` | **Weather** | the air model for this flying day |
| `soundings` | **Weather** | the shared data layer — must travel with *both* its consumers (F4, D-48) |
| `wind` | **Weather** | same flying day, same radiosonde (§31.3.3, D-48) |
| `gravity` | **Scenario field** | an Earth/fidelity choice, not one of the three axes (§31.3.2, D-47) |
| `solver` | **Scenario field** | "how you want to run this" (§31.3.2, D-47) |
| `g0` (scalar) | **Scenario field** | shared constant, same reasoning as `gravity` |

Four obvious ones (`weight`, `lengths`, `thrust`, `aero` → rocket; `site` → launch site;
`atmosphere` → weather) need no argument. The rest follow.

### 31.3.1 `recovery` and `control` — vehicle subsystems or their own axis

**Recommendation: both to the rocket piece (D-46a).**

`Recovery` is `Cd`, canopy `S`, a trigger and a deploy time; `Control` is airbrake `Cd`, `S_max`,
`kp`, a target apogee, a trigger and a deploy time. Each group is a **mix of hardware and
flight-plan**: `Cd`/`S`/`S_max` are physical articles bolted to the airframe, while
`trigger`/`deploy_time`/`airbrake_target_apogee_m` are what you *program* for one flight. A split
along that seam is exactly the field-level ownership the whole design is built to avoid (D-49), and
it would buy nothing today:

- **App 4 overwrites `control.airbrake_*` wholesale at solve time.** §30.6: *"The app owns
  `control.airbrake_*` entirely. Whatever the incoming `Config` set there is overwritten by
  `brake_overrides`"* — and `apps/airbrake_sizing/solve_cda.py:349` (`_warn_if_airbrake_already_set`)
  exists precisely to say so out loud. A "flight plan" piece owning `control` would have its contents
  discarded by the one app that cares.
- **The flight-plan fields stay reachable** through the scenario `overrides` dict (§31.4) — one line
  in the scenario module, next to the name it belongs to.
- **"My rocket" colloquially includes its parachute.** `Rocket(name="my_rocket", …,
  recovery=Recovery(model="deploy", Cd=0.8, S=0.5))` is one reusable object meaning the whole
  airframe; forcing the user to pair a rocket with a separate "recovery" piece to get their own
  parachute back is a fourth axis they did not ask for.

The honest cost: a scenario that flies the same airframe with a 1.0 m² and a 1.4 m² canopy either
gets two rocket pieces (cheap — `dataclasses.replace` on the piece, or a second module) or one
`overrides={"recovery.S": 1.4}` line. That is a smaller cost than a fourth registry with one entry.

### 31.3.2 `gravity`, `solver`, `g0` — the run-level leftovers

**Recommendation: plain, defaulted fields on `Scenario`; no fourth registry (D-47a).**

`Solver` is uncontroversial: `method`, `rtol`, `atol`, `t_max`, `dt`, `sample_rate_hz` are "how you
want to run this", `sim/params.with_solver` already exists as the one sugar for it (~60 test call
sites), and App 4/App 5 override `solver.t_max`/`sample_rate_hz` per study. Putting it in the rocket
would make `cfg.derive({"solver.t_max": 5.0})` a statement about the vehicle.

`Gravity` is the genuinely ambiguous one, and the code resolves it (F2). The group mixes a **fidelity
choice** (`model`, `direction`, `earth_rotation` — how carefully gravity is modelled) with a **world
constant** (`R_e`, read by `sim/soundings.py`'s tangent-plane projection as well). Neither half is a
property of a particular field:

- The *latitude* `wgs84` gravity is evaluated at already comes from `site.lat0_deg`
  (`sim/gravity.py:110`, `:170`). So the gravity **value** follows the site automatically without the
  model **choice** following it — which is what you want: "constant vs wgs84 at my field" is a
  comparison you run *at one site*, and attaching the model to the site would make switching sites
  silently change fidelity.
- `R_e` is a mean Earth radius, never a per-site number.

So `gravity` belongs with `solver`: things you set per *run*, not per rocket, site or day. The
remaining question is whether they get a named fourth piece with its own registry. Recommended: no.
A `Fidelity` piece would ship with one entry ("the defaults"), and the one plausible reuse case — a
named "high fidelity" bundle (`wgs84` + `earth_rotation=True` + tight tolerances) — is served by a
module-level constant spread into the scenario literal:

```python
# configs/fidelity.py (optional, zero machinery)
HIGH = dict(gravity=Gravity(model="wgs84", direction="radial", earth_rotation=True),
            solver=Solver(rtol=1e-10, atol=1e-12))
# in a scenario module:
SCENARIO = Scenario(name="…", rocket=ROCKET, site=SITE, weather=WEATHER, **HIGH)
```

### 31.3.3 `wind` and `soundings` — the one real two-owner conflict

**Recommendation: `atmosphere` + `soundings` + `wind` in one `Weather` piece (D-48a).**

The `soundings` docstring's "shared data layer for atmosphere AND wind" is the whole argument (F4).
Three ways to resolve it:

1. **One piece owns all three** (recommended). `soundings.case` has exactly one writer; assembly
   stays merge-free; and the piece corresponds to something real — *one flying day's air*, which is
   literally what a radiosonde ascent measures. `Weather(name="launch_day_sounding",
   atmosphere=Atmosphere(model="sounding"), soundings=Soundings(case="2026-05-12_kkb"),
   wind=Wind(model="sounding"))` is one object, internally consistent by construction, and swapping
   it for `isa_dry_calm` swaps the whole weather story — which is the user's "today's ISA vs a real
   sounding from launch day" use case stated verbatim.
2. `soundings` as its own fourth piece, referenced by both an atmosphere piece and a wind piece.
   Honest about the sharing, but it makes the *common* case (ISA, no wind) a three-piece assembly, and
   two pieces can still disagree about which tier they want from one case.
3. `soundings` with atmosphere, and a wind piece forbidden from tiers 2/3. Rejected: it makes
   sounding-driven wind — an existing, tested capability (`sim/wind.py:349`) — unreachable from the
   config layer.

The cost of (1) is that "same air, different wind" needs two `Weather` pieces or a
`overrides={"wind.ref_ms": …}` line. For tier-1 analytic wind that is a one-line cost; for tiers 2/3
"same air, different wind" is not a physically meaningful request anyway, since both come from the
same case folder.

### 31.3.4 `site` — pad geodesy and rail, kept whole

`Site` is owned entirely by the `LaunchSite` piece — `lat0_deg`, `lon0_deg`, `h0_m`, `azimuth_deg`,
`L_rail`, `rail_angle_deg`. F7 already settled that the rail lives in `Site`. The residual tension is
that `rail_angle_deg` (tilt into the wind) and `azimuth_deg` (which way you point downrange) are
**per-flight** choices made at a site, not properties of the field. Two consequences, both handled
without a new concept:

- A site piece's `rail_angle_deg`/`azimuth_deg` are *that site's usual setup*, and a scenario that
  tilts the rail says so in one `overrides` line (`{"site.rail_angle_deg": 85.0}`), which is also
  where a reader looks for a per-flight choice.
- Because `s0.theta` must match (F5), the override must be applied **before** `s0` is derived. That is
  a hard ordering rule in §31.4, not an implementation detail.

---

## 31.4 Composition: `Scenario` → `Config`

### The objects (illustrative sketch — not code to write yet)

`configs/schema.py` keeps `Config` and `Variant` **exactly as they are** and gains four frozen
dataclasses. Every one is trivially constructible, no inheritance, no builders — the §30.4 house
style.

```python
# configs/schema.py  (additions only; Config and Variant unchanged)

@dataclasses.dataclass(frozen=True)
class Rocket:
    """One vehicle: airframe, motor installation, aerodynamics, and the
    recovery/control hardware bolted to it (SS31.3.1)."""
    name: str
    weight: Weight                                   # the only required group
    lengths:  Lengths  = dataclasses.field(default_factory=Lengths)
    thrust:   Thrust   = dataclasses.field(default_factory=Thrust)
    aero:     Aero     = dataclasses.field(default_factory=Aero)
    recovery: Recovery = dataclasses.field(default_factory=Recovery)
    control:  Control  = dataclasses.field(default_factory=Control)
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
    soundings:  Soundings  = dataclasses.field(default_factory=Soundings)
    wind:       Wind       = dataclasses.field(default_factory=Wind)
    notes: str = ""


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One named combination of a rocket, a site and a day's weather, plus
    the run-level groups nobody reuses by name (SS31.3.2). `.config`
    assembles it into the ordinary `Config` every tool already takes."""
    name: str
    rocket: Rocket
    site: LaunchSite
    weather: Weather
    gravity: Gravity = dataclasses.field(default_factory=Gravity)
    solver:  Solver  = dataclasses.field(default_factory=Solver)
    g0: float = 9.80665
    s0: State | None = None                    # None -> derived from the rail (D-51)
    overrides: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: str = ""

    @property
    def config(self) -> Config:
        return assemble(self)
```

### The assembly function, and the invariant it rests on

```python
def assemble(sc: Scenario) -> Config:
    """SS31.4. Exactly one owner per `Params` group -- no merge, no
    precedence rule, no partial groups. The keyword set below is
    `dataclasses.fields(Params)` exactly (pinned by test, SS31.8)."""
    p = Params(
        weight=sc.rocket.weight,
        lengths=sc.rocket.lengths,
        thrust=sc.rocket.thrust,
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
    # (2) the scenario's own last word, dotted paths over the whole tree
    if sc.overrides:
        p = params_replace(p, sc.overrides)     # sim.params.replace, SS29 F1
    # (3) s0 AFTER overrides -- so an overridden rail angle moves the
    #     initial attitude with it (F5, D-51)
    s0 = sc.s0 if sc.s0 is not None else _pad_state(p.site)
    return Config(name=sc.name, params=p, s0=s0, notes=sc.notes)


def _pad_state(site: Site) -> State:
    """At rest on the pad, nose along the rail. `math.radians(90.0)` is
    exactly `math.pi / 2` (F6), so this reproduces every existing
    config's `s0` bit-for-bit."""
    return State(x=0.0, z=0.0, vx=0.0, vz=0.0,
                 theta=math.radians(site.rail_angle_deg), omega=0.0)
```

**The invariant: one group, one owner.** This is the single most important property of the design
(D-49). It means `assemble` has no merge logic, no "last writer wins", no partial-group updates and no
way for a field to come from two places. It is also mechanically checkable: the keyword set of that
`Params(...)` call must equal `{f.name for f in dataclasses.fields(Params)}`, which a two-line test
pins forever (§31.8) — so if `sim/params.py` ever grows a thirteenth group, the test fails loudly
instead of the new group silently taking defaults in every scenario.

**Ordering, stated once:** (1) gather groups from the pieces → (2) apply the scenario's `overrides`
→ (3) derive `s0` if it was not given. Step (3) after step (2) is what makes
`overrides={"site.rail_angle_deg": 85.0}` do the obvious thing. Getting this backwards would
re-create F5's foot-gun *inside* the mechanism that advertises fixing it.

### Eager or lazy

**Eager, at import, bound in the scenario module (D-50a).** F8 is decisive: `tests/test_configs.py`
pins `configs.CONFIGS[basename] is mod.CONFIG`, so the registry and the module must agree on one
object. Each scenario module therefore ends with two names:

```python
SCENARIO = Scenario(name="demo_75mm", rocket=ROCKET, site=SITE, weather=WEATHER, notes="…")
CONFIG: Config = SCENARIO.config      # assembled once, at import; what the registry stores
```

`SCENARIO` is kept (not discarded) because it is the only place that records *which three pieces this
scenario is* — used by `--list-scenarios` and by `configs.get_scenario(name)` (§31.6). Assembly cost
is 13 frozen-dataclass constructions per scenario, once; the whole package import stays
sub-millisecond.

### How overrides work, and at which level

Three levels exist and they do different jobs; the recommendation keeps all three, with the first as
the normal one:

| Level | Mechanism | For |
|---|---|---|
| **Scenario** | `Scenario.overrides`, a dotted-path dict applied in step (2) | the per-flight tweak that belongs to *this combination*: a tilted rail, a longer `t_max`, a programmed deploy time |
| **Piece** | `dataclasses.replace(ROCKET, weight=Weight(m=2.4, I=0.11))` | a near-identical vehicle; still a literal, still commented, still one module and one git history |
| **Config** | `Config.derive` / `Variant.apply` — **unchanged** | what it is today: a *study* delta on a complete scenario (App 3's motors, App 5's scenario list, every test's `cfg.derive(...)`) |

Note what is deliberately *not* proposed: a `Scenario.derive`. A scenario is cheap to write out in
full (four names and a notes string), and a derive chain over compositions is where indirection gets
genuinely hard to read. If one is wanted later it is additive.

---

## 31.5 Registries and the directory layout

**Recommendation (D-52a): four subpackages, each with its own explicit-tuple registry, mirroring the
existing registry's three rules verbatim.**

```
configs/
  __init__.py              # the package API, UNCHANGED in shape: CONFIGS, names(), get()
                           #   -- re-exports the *scenario* registry, plus get_scenario()
  schema.py                # Config, Variant (unchanged) + Rocket, LaunchSite, Weather,
                           #   Scenario, assemble()
  rockets/
    __init__.py            #   ROCKETS, names(), get()        (explicit _MODULES tuple)
    _TEMPLATE_rocket.py    #   blank, every field commented   NOT REGISTERED
    toy_05kg.py            #   ROCKET = Rocket(name="toy_05kg", ...)
    demo_75mm.py           #   ROCKET = Rocket(name="demo_75mm", ...)
  sites/
    __init__.py            #   SITES, names(), get()
    _TEMPLATE_site.py      #   blank, every field commented   NOT REGISTERED
    origin_msl.py          #   SITE = LaunchSite(name="origin_msl", site=Site())  <- pins the defaults
  weather/
    __init__.py            #   WEATHER, names(), get()
    _TEMPLATE_weather.py   #   blank, every field commented   NOT REGISTERED
    isa_dry_calm.py        #   WEATHER = Weather(name="isa_dry_calm")             <- pins the defaults
  scenarios/
    __init__.py            #   SCENARIOS, names(), get()  -- what configs.get() delegates to
    _TEMPLATE_scenario.py  #   blank; shows piece-by-import   NOT REGISTERED
    toy_05kg.py            #   SCENARIO = ...; CONFIG = SCENARIO.config
    demo_75mm.py
    demo_75mm_airbrake.py
```

### Templates: one blank and one filled-in example per piece type

Added at the 2026-10-14 approval, on the user's request: each of the four piece types ships **both** a
blank `_TEMPLATE_*.py` and at least one real, filled-in module. The templates follow the convention
the user's own `configs/_TEMPLATE_my_rocket.py` established — every field on its own line with a
`# <-- fill this in` comment giving units, meaning and the consequence of leaving it alone, and a
docstring saying "fill in, rename, then add one line to this package's `_MODULES`".

Three properties the templates must have, and they are in tension, so they are stated as rules:

1. **Not registered.** A `_TEMPLATE_*` module is never in its package's `_MODULES` tuple. This is the
   §30.4 explicit-tuple rule doing exactly the job it was written for: a half-finished draft must not
   appear by existing, and a template is a permanent half-finished draft.
2. **Importable anyway.** `python -c "import configs.rockets._TEMPLATE_rocket"` must succeed, so each
   template defines a real object with placeholder numbers (`ROCKET = Rocket(name="my_rocket", …)`).
   A template that does not import is a template that silently rots. Pinned by test (§31.8 #6).
3. **The leading underscore is load-bearing.** It keeps the templates sorted together at the top of a
   directory listing and marks them as non-modules-of-record, matching the user's existing filename.

The scenario template additionally demonstrates the thing the whole phase is for: referencing named
pieces **by import** rather than re-specifying them —
`from configs.rockets.demo_75mm import ROCKET` — with a commented note that a flat, whole-`Config`
module remains legal (§31.5 above) for anyone who would rather keep one file.

Each of the four `__init__.py` files is the same ~20 lines the current `configs/__init__.py` already
is, with the same three rules:

1. **Explicit `_MODULES` tuple, never auto-discovery.** Same reason as §30.4: a half-finished draft
   rocket must not break every app's import by existing, and "who uses this rocket" stays one grep.
2. **Piece modules import `from configs.schema import Rocket`**, never `from configs.rockets import
   …` and never `from configs import …`. The extended rule: **pieces never import the top-level
   `configs` package or `configs.scenarios`; scenario modules may import the piece subpackages.** The
   resulting import graph is a DAG — `configs/__init__` → `configs.scenarios` → `configs.{rockets,
   sites, weather}` → `configs.schema` → `sim.*` — with no edge back up, so the existing
   fresh-interpreter circular-import tests (`tests/test_configs.py:205-210`) keep passing and gain two
   siblings.
3. **A name is bound at registration**, keyed off `m.ROCKET.name` / `m.SITE.name` / `m.WEATHER.name`
   / `m.SCENARIO.name`, with the existing basename-equality test extended to all four registries.

**Namespaces are per-kind, deliberately.** `rockets.get("demo_75mm")` and `get("demo_75mm")` (the
scenario) coexist and *should* — backward compatibility requires the scenario to keep the old name,
and the rocket inside it is the same thing under the same name. The kind is always explicit at the
call site, so there is no ambiguity to resolve.

**A flat, whole-`Config` module stays legal and registrable — forever.** This is a requirement, not a
courtesy: the user's own `configs/_TEMPLATE_my_rocket.py` (their branch) is exactly that shape, and it
must keep working so their in-progress vehicle registers unchanged when this lands, and splits into
pieces later only if they want to. Mechanically the scenario registry accepts any module exposing
`CONFIG: Config`; `SCENARIO` is optional metadata. So `configs/scenarios/my_rocket.py` can be a
hand-written `Config(...)` literal, or three pieces plus a `Scenario`, and nothing downstream can
tell the difference. (Whether the flat template file keeps living at `configs/my_rocket.py` or moves
under `configs/scenarios/` is D-55's second half; both work.)

---

## 31.6 Backward compatibility — the blast radius, file by file

**Recommendation: full source-level backward compatibility as a first-class design goal (D-45a).**
`Config`, `Variant` and the `configs.CONFIGS` / `names()` / `get()` API are unchanged; the pieces and
`Scenario` are purely additive; `configs.get("demo_75mm")` returns a `Config` with the same `name`,
the same `params`, the same `s0` and the same `notes` as today. **Zero caller edits, zero test
edits.**

This is argued, not assumed. The argument is F9 + F10: the surface in use is tiny (six members on
`Config`, three on the package), nothing anywhere does `isinstance(x, Config)` or
`dataclasses.replace(cfg, …)`, and the one structural coupling (`CONFIGS[name] is mod.CONFIG`,
F8) is satisfied by eager module-level assembly, which is the right choice anyway. The alternative —
`configs.get` returning a `Scenario` and every caller reaching through `.config.params` — would churn
11 files and force re-verification of two bit-for-bit gates (App 3's printed table and CSV, §30.5;
`run.py`'s and App 2's output, Step 69) in exchange for **no new capability**, since the pieces are
reachable through `get_scenario` either way.

The one *additive* API: `configs.get_scenario(name) -> Scenario | None` (two lines), returning the
composition behind a scenario name, or `None` for a flat `Config`-only module. It is what lets
`--list-configs` grow a "rocket / site / weather" column later (D-54) without any caller noticing.

### The orchestrator's 19-file list, verified

| File | What it actually uses | Edit needed (recommended design) |
|---|---|---|
| `run.py` | `configs.get("toy_05kg")`, `.params`, `.s0` | **none** |
| `run_airbrake.py` | nothing — docstring reference only (F9) | none |
| `run_cfd_conditions.py` | nothing — docstring only | none |
| `run_motor_sweep.py` | nothing — docstring only | none |
| `run_trade.py` | forwards the `--config` **string** to the app; no API use | none |
| `apps/airbrake_sizing/solve_cda.py` | `resolve_config`, `Config` annotation, `cfg.params`/`.s0`/`.name` | **none** |
| `apps/airbrake_sizing/targets.py` | **docstring prose only** (`configs.demo_75mm_airbrake`, `configs/demo_75mm_airbrake.py`) | none functionally; one stale *path* in a docstring if the seeds move to `configs/scenarios/` (D-55) |
| `apps/cfd_conditions/select_conditions.py` | `configs.get("toy_05kg")`, `.params`, `.s0` | **none** |
| `apps/common/artifacts.py` | nothing — `OUTPUT_DIR`/`ensure_dir` only | none |
| `apps/common/cli.py` | `configs.names()`, `configs.get()`, `.notes`, `-> Config` | **none**; gains `--rocket/--site/--weather` only if D-54 says yes, additively |
| `apps/common/flight_stats.py` | nothing — takes `(result, p: Params)` | none |
| `apps/motor_selection/compare_motors.py` | `configs.get("demo_75mm").params`, `.s0` | **none** |
| `apps/weight_aero_tradeoff/compare_configs.py` | `configs.get`, `configs.names`, `.params`/`.s0`/`.name`/`.notes`, `with_variant` | **none** |
| `apps/weight_aero_tradeoff/scenarios.py` | `Config` annotation, `Variant` literals, `cfg.params.aero.*` | **none** (note the name collision in §31.10 risk 6) |
| `apps/weight_aero_tradeoff/trade_surface.py` | `resolve_config`, `Config`, `cfg.params`/`.s0`/`.name` | **none** |
| `tests/test_airbrake_sizing.py` | `configs.get`, `.derive` | **none** |
| `tests/test_apps_common.py` | nothing — doc reference only | none |
| `tests/test_configs.py` | everything, including `configs._MODULES` and the `is` pin | **two module-path strings on one line** (see the amendment below); every assertion, pin and helper unedited |
| `tests/test_control.py` | nothing — builds its own `Params`; comment reference only | none |
| `tests/test_weight_aero_tradeoff.py` | `configs.get`, `.derive` | **none** |

`configs/__init__.py` keeps `_MODULES` as a re-export (`_MODULES = scenarios._MODULES`) purely so
`test_registry_keys_equal_module_basenames` passes unedited — and it still passes on its own terms,
because `mod.__name__.split(".")[-1]` of `configs.scenarios.demo_75mm` is `demo_75mm`.

### Amendment (2026-10-14, found while ticketing): one named exception to "zero test edits"

D-45a's "zero test edits" and D-55a's "the seeds move into `configs/scenarios/`" **cannot both hold
literally**, and the conflict is in exactly one place:

```python
# tests/test_configs.py:205-206 -- unchanged since Step 63
def test_import_configs_demo_75mm_first_has_no_circular_import():
    _run_fresh_interpreter("import configs.demo_75mm\nprint(configs.demo_75mm.CONFIG.name)\n")
```

That test names a **module path**, not an API, and the path is what D-55a moves. Nothing else in the
suite imports a seed module by path (grepped: `configs/demo_75mm_airbrake.py` is the only other such
import, and it is rewritten by the same step). So the gate is stated precisely as:

> **No test file is edited except `tests/test_configs.py`, and there only the two occurrences of the
> string `configs.demo_75mm` on line 206, which become `configs.scenarios.demo_75mm`. No assertion,
> no helper, no pinned literal and no expected value changes anywhere in the suite.**

That is a mechanical consequence of a `git mv`, in the same class as updating an import after moving a
file — not a relaxation of the compatibility goal. The three alternatives were considered and
rejected: leaving the seeds flat (abandons D-55a, and the seeds then never exercise `assemble`);
leaving a three-line `configs/demo_75mm.py` shim that re-exports `CONFIG` (two homes for one name,
and an ambiguous `_MODULES`); and deleting the test (it pins a real property — that importing a
config module *before* the package does not deadlock — and §31.8 #3 extends it to four packages).

---

## 31.7 Migrating the three seed configs, provably

Same discipline as Steps 63/69: the migration must be a **provable no-op**, not an inspection.

### What each seed becomes

| Today | After |
|---|---|
| `configs/toy_05kg.py` (`Config`: 0.5 kg vehicle + implicit default site/atmosphere) | `configs/rockets/toy_05kg.py` (`Rocket`, the four vehicle groups and **all** their justifying comments moved verbatim) + `configs/scenarios/toy_05kg.py` (`Scenario` → `CONFIG`, the existing `notes` string verbatim) |
| `configs/demo_75mm.py` | `configs/rockets/demo_75mm.py` + `configs/scenarios/demo_75mm.py`, same treatment; the long provenance docstring stays with the **rocket** (it is about the vehicle), the `notes` string stays with the **scenario** (it is what `--list-configs` prints) |
| `configs/demo_75mm_airbrake.py` (`demo_75mm.CONFIG.derive(name=…, overrides={})`) | `configs/scenarios/demo_75mm_airbrake.py` — the **same three pieces** under a different name and notes. This is a genuine improvement: the module's current docstring explains at length that it is "demo_75mm, unchanged, registered under its own name", and `derive(overrides={})` was the only way to say that. Composition says it directly, and a future vehicle change for the airbrake demo becomes "point at a different rocket piece", not "add an override". |
| (implicit: every group left at its default) | `configs/sites/origin_msl.py` → `LaunchSite(name="origin_msl", site=Site())` and `configs/weather/isa_dry_calm.py` → `Weather(name="isa_dry_calm")` |

### The two "pin the defaults" pieces, and why they are argument-free

`origin_msl` and `isa_dry_calm` must construct their groups **with no arguments at all** —
`Site()`, not `Site(lat0_deg=0.0, lon0_deg=0.0, h0_m=0.0, azimuth_deg=90.0, L_rail=0.0,
rail_angle_deg=90.0)`. The two are equal today, but they are not the same promise: the pre-split
seeds relied on *whatever `sim/params.py`'s defaults are*, so the byte-equal-forever choice is to keep
relying on them. Spelling the values out would freeze today's defaults into two config modules and
make a future `sim/params.py` default change a silent divergence between the seeds and everything
else. Each module's docstring must say this in one sentence, because an argument-free literal looks
like an oversight otherwise.

Names are open (D-53). `origin_msl` = "lat 0, lon 0, sea level, no rail" — honest that it is a
placeholder, not a field anyone flies from. `isa_dry_calm` = ISA, dry air, no wind, no sounding case.

### The gate

The four exact-equality tests already in `tests/test_configs.py` **are** the gate, unedited:

- `test_toy_05kg_params_pin_run_py_literal_exactly` — `configs.get("toy_05kg").params ==
  _toy_05kg_literal()`, a hand-written `Params` with ten groups at their defaults. Passing this after
  the split *is* the proof that assembly reproduces the implicit defaults exactly.
- `test_toy_05kg_s0_pins_run_py_literal_exactly` — `s0 == State(…, theta=math.pi / 2, …)`. With a
  derived `s0` (D-51) this is the test that F6 makes pass: `math.radians(90.0)` *is* `math.pi / 2`.
- `test_demo_75mm_params_pin_demo_baseline_exactly` / `..._s0_...` — same for the 75 mm vehicle
  against App 3's `_demo_baseline()`.

Three additions, all cheap: `get("demo_75mm_airbrake").params == get("demo_75mm").params` (today's
`derive({})` relation, now a composition identity); a `notes`-string pin for all three seeds (notes is
user-visible through `--list-configs`, so a reworded note is a behaviour change); and the
`assemble`-covers-every-`Params`-field structural test (§31.8).

Belt-and-braces option if the user wants it: snapshot `repr(configs.get(n).params)` for the three
seeds on `develop` before the split and pin the strings. Not recommended — the four equality tests
already compare the real objects, and a `repr` pin breaks on cosmetic `sim/params.py` changes for no
added coverage.

---

## 31.8 Test strategy (additions only)

No existing test is edited beyond §31.6's one named path exception. Eight additions, in the project's
usual pinned style, all in **new** test files so that "no test edits" stays literally checkable:

1. **`assemble` covers `Params` exactly.** `{kw of the Params(...) call} == {f.name for f in
   dataclasses.fields(Params)}` — the structural guard for the one-owner invariant. Implemented
   without reading source text by asserting that assembling a scenario built from *non-default*
   pieces leaves no group equal to its default.
2. **Registry integrity ×4.** The existing basename/duplicate/`names()`/`KeyError` tests,
   parametrised over `rockets`, `sites`, `weather`, `scenarios`.
3. **No circular import ×4.** Fresh interpreter, each subpackage imported first
   (`python -c "import configs.rockets.demo_75mm"`), mirroring `tests/test_configs.py:197-210`.
4. **Override ordering.** A scenario with `overrides={"site.rail_angle_deg": 85.0}` and `s0=None`
   yields `s0.theta == math.radians(85.0)` — the regression test for the §31.4 ordering rule.
5. **Every registered scenario still flies**, parametrised (the existing check, now over the scenario
   registry).
6. **Every `_TEMPLATE_*` module imports cleanly and is absent from its registry.** Parametrised over
   the four template module paths: `importlib.import_module(path)` succeeds, the module exposes the
   expected object name (`ROCKET`/`SITE`/`WEATHER`/`SCENARIO`), and that object's `.name` is **not**
   in the corresponding registry (§31.5 rules 1-2). This is what stops a template from rotting
   unnoticed and what stops one from being accidentally registered.
7. **A flat, whole-`Config` scenario module still registers.** A test-local module exposing only
   `CONFIG: Config` (no `SCENARIO`) is accepted by the scenario registry's own keying logic, and
   `get_scenario` returns `None` for it — the §31.5 guarantee the user's `_TEMPLATE_my_rocket.py`
   shape depends on.
8. **Piece-level slice equality against the independent reconstructions.**
   `rockets.get("demo_75mm").weight == _demo_baseline().weight` and the same for
   `lengths`/`thrust`/`aero`, plus `rockets.get("toy_05kg")`'s four groups against
   `tests/test_configs.py`'s `_toy_05kg_literal()`, plus `sites.get("origin_msl").site == Site()` and
   `weather.get("isa_dry_calm")`'s three groups against their defaults. The reconstructions are the
   same ones the four existing exact-equality pins use (that is why Step 63 wrote them as
   reconstructions rather than imports), so this localises a failure to *which piece* is wrong instead
   of only telling you the assembled `Params` differs.

---

## 31.9 Decision points for the user (D-45 … D-55) — all answered 2026-10-14

Numbering continues §30.10's D-28 … D-42. **D-43 and D-44 are skipped** — they were used by Phase
2.14 (LaTeX sync: keep the Dryden write-up; leave the 3D scaffold out of `main.tex`).

**All eleven came back on 2026-10-14 as the recommended option, with no changes.** The nine
user-facing forks (D-45, D-46, D-47, D-48, D-51, D-52, D-53, D-54, D-55) were put to the user and
answered; D-49 (the one-owner invariant) and D-50 (eager assembly) were relayed as
near-forced-by-the-code recommendations and drew no objection. Each fork below carries a
**Decided** line; the options and their pros/cons are left exactly as written, as the record of what
was weighed.

Summary of the resolved design, in one place:

| Fork | Decided |
|---|---|
| D-45 | (a) full source-level compatibility — zero caller edits; one named test-path exception (§31.6 amendment) |
| D-46 | (a) `recovery` + `control` in the `Rocket` piece |
| D-47 | (a) `gravity` / `solver` / `g0` as plain defaulted `Scenario` fields — no fourth piece, no fourth registry |
| D-48 | (a) one `Weather` piece owning `atmosphere` + `soundings` + `wind` |
| D-49 | (c) whole-group ownership, with the scenario's dotted-path `overrides` as the only field-level mechanism |
| D-50 | (a) eager assembly, `CONFIG = SCENARIO.config` bound at import |
| D-51 | (a) `s0` derived from the post-override `site.rail_angle_deg` when not given explicitly |
| D-52 | (a) four subpackages, `configs/{rockets,sites,weather,scenarios}/`, each with its own explicit-tuple registry |
| D-53 | (a) `Rocket` / `LaunchSite` / `Weather` / `Scenario`; folder `configs/weather/`; defaults `origin_msl` + `isa_dry_calm` |
| D-54 | (a) ad-hoc `--rocket/--site/--weather` CLI **deferred** to a later step, not part of this migration |
| D-55 | (a) split all three seeds into real pieces now |

**Added at approval, not a fork:** every piece type ships a blank `_TEMPLATE_*.py` **and** a
filled-in module from migrated seed data (§31.5, and every ticket's Check list in §31.12).

**D-45 — does the split preserve today's public config surface?** *Purpose: 11 files and 3 test
modules consume `configs.get(name) -> Config`; this decides whether they are touched at all.*

| Option | Pros | Cons |
|---|---|---|
| **(a) full source-level compatibility: `Config`/`Variant`/`get`/`names`/`CONFIGS` unchanged, pieces purely additive, each scenario module exports `CONFIG = SCENARIO.config` (recommended)** | **zero caller edits, zero test edits** — verified member by member (F9/F10); the two existing bit-for-bit gates (App 3's table+CSV, `run.py`/App 2's output) are not re-opened; the risk of the whole phase collapses to "does `assemble` reproduce the three seeds", which four existing tests already answer; same discipline as Step 69 | `Config` keeps carrying a flattened `Params`, so provenance ("which rocket?") needs the extra `get_scenario` accessor rather than being on the object everyone already holds |
| (b) `configs.get` returns a `Scenario`; callers reach through `.config.params` / `.config.s0` | one object type instead of two; provenance always in hand | 11 files edited for no new capability; re-verification of two bit-for-bit gates; `Config` becomes a transient the apps never name, so `apps/*`'s `cfg: Config` annotations all churn; `Variant`'s meaning gets fuzzy (delta against a scenario or against its config?) |
| (c) compatibility now, deprecate later (`get` returns `Config`, a `get_scenario` is added, and a future phase flips the default) | the migration path exists on paper | two surfaces to keep tested for an indefinite period, and the flip is the same 11-file edit as (b), just later and with less context |

**Recommendation: (a)**, plus the two-line `get_scenario(name)` accessor from (c) — the capability (b)
wants, at none of its cost. If this is approved, "no caller edits, no test edits" becomes the phase's
primary gate, exactly as "byte-identical table and CSV" was Step 64's.

**Decided (user, 2026-10-14): (a)** — full source-level compatibility, zero caller edits, plus the
`get_scenario(name)` accessor. "No caller edits, no test edits" is the phase's primary gate, with the
single mechanical exception §31.6's amendment names (two module-path strings renamed by the `git mv`
in Step 73).

**D-46 — where `recovery` and `control` live.** *Purpose: parachute and airbrake hardware are vehicle
subsystems, but their trigger/target fields are per-flight settings.*

| Option | Pros | Cons |
|---|---|---|
| **(a) both in the `Rocket` piece (recommended)** | "my rocket" colloquially includes its parachute; keeps the one-owner invariant; App 4 overwrites `control.airbrake_*` wholesale anyway (§30.6), so a separate owner's values would be discarded; three pieces, matching exactly the three axes asked for | a scenario changing only the canopy area needs a second rocket piece or a one-line override |
| (b) a fourth `FlightPlan` piece owning `recovery` + `control` | the trigger/target/deploy-time fields are genuinely per-flight; "same rocket, three deployment plans" becomes three named pieces | a fourth registry and a fourth axis the user did not ask for; its `Control` half is overwritten by App 4; `Cd`/`S`/`S_max` are *hardware* and would be stranded on the wrong side |
| (c) split by field: hardware (`Cd`, `S`, `S_max`, `kp`) → rocket, flight plan (`trigger`, `deploy_time`, `target_apogee`) → scenario | each field sits where it semantically belongs | **breaks the one-owner invariant** (D-49): two pieces write `Recovery`/`Control`, so assembly needs field-level merge with a precedence rule — the single biggest complexity increase available in this design, for cosmetic gain |

**Recommendation: (a).** Per-flight settings stay reachable as one `overrides` line in the scenario
literal, which is also where a reader looks for them.

**Decided (user, 2026-10-14): (a)** — `recovery` and `control` are owned by the `Rocket` piece. No
`FlightPlan` piece; per-flight trigger/target/deploy-time settings go in the scenario's `overrides`.

**D-47 — where `gravity`, `solver` and `g0` live.** *Purpose: neither is a rocket, a site or a day's
weather, but something must own them.*

| Option | Pros | Cons |
|---|---|---|
| **(a) plain defaulted fields on `Scenario`; no fourth registry (recommended)** | zero machinery; `solver` is self-evidently "how you want to run this" (`with_solver` already exists for it); gravity's *value* already follows the site through `site.lat0_deg` while its *model choice* stays a per-run fidelity knob, which is the right coupling; a named "high fidelity" bundle is a `dict` spread into the literal | no `--list-fidelities`; two scenarios wanting the same tight tolerances repeat two lines |
| (b) a fourth `Fidelity` piece (`gravity` + `solver` + `g0`) with its own registry | symmetric with the other three; "high fidelity" becomes a reusable name; the one place `R_e` (an Earth constant read by `sim/soundings.py`, F2) can honestly live | a registry that ships with one entry ("the defaults"); a fourth axis to explain; changing `Scenario`'s field types later is a breaking change to every scenario literal, so this is cheaper to get right now than to add later |
| (c) `gravity` → the `LaunchSite` piece, `solver`/`g0` → scenario | a site *is* a place on the Earth, so latitude and the Earth model sit together | switching to a hypothetical high-altitude site would silently also switch gravity fidelity; `R_e` is a global constant, never per-site; and `wgs84` gravity already reads the site's latitude without owning the model choice |

**Recommendation: (a).** (b) is the defensible "industrial" answer and the only one worth reconsidering
if the user expects to compare fidelity settings often — it is cheaper to decide now than to retrofit.

**Decided (user, 2026-10-14): (a)** — `gravity`, `solver` and `g0` are plain defaulted fields on
`Scenario`. No fourth piece and no fourth registry; a named "high fidelity" bundle, if ever wanted, is
the `dict`-spread shown in §31.3.2. The retrofit cost of (b) is accepted as a known future expense
and recorded as a backlog candidate (§31.11).

**D-48 — where `wind` and `soundings` live.** *Purpose: `Soundings` is explicitly "the shared data
layer for atmosphere AND wind tiers 2/3" (`sim/params.py:119`), and it is the only group with two
consumers in `sim/` (F4).*

| Option | Pros | Cons |
|---|---|---|
| **(a) one `Weather` piece owning `atmosphere` + `soundings` + `wind` (recommended)** | `soundings.case` gets exactly one writer, so assembly stays merge-free; matches physical reality (one radiosonde ascent measures air *and* wind for one place and time); the user's "today's ISA vs a real sounding from launch day" becomes one swap of one piece, internally consistent by construction | "atmosphere" as an axis now silently includes wind — a naming problem (D-53), not a structural one; "same air, different wind" needs a second piece or an override |
| (b) separate `AtmosphereProfile` and `WindProfile` pieces, with `Soundings` as a third shared piece both reference | each axis is nameable and swappable on its own; honest about the sharing | the common case (ISA, no wind) becomes a three-piece assembly; two pieces can still disagree about which tier they want from one case; five axes total |
| (c) `soundings` with atmosphere; a separate `WindProfile` restricted to tier-1 analytic wind | two clean axes, no shared piece | makes sounding/field-driven wind — an existing, tested capability (`sim/wind.py:349`, `:377`) — unreachable from the config layer |

**Recommendation: (a).**

**Decided (user, 2026-10-14): (a)** — one `Weather` piece owns `atmosphere` + `soundings` + `wind`,
so `soundings.case` has exactly one writer and assembly stays merge-free.

**D-49 — ownership granularity: whole groups, or individual fields?** *Purpose: this is the hinge the
rest of the design hangs on, and it is worth deciding explicitly rather than inheriting.*

| Option | Pros | Cons |
|---|---|---|
| **(a) whole-group ownership: exactly one piece owns each of the twelve groups (recommended)** | `assemble` is a 15-line total function with no merge logic, no precedence rule and no partial groups; mechanically checkable against `dataclasses.fields(Params)`, so a future thirteenth group fails a test instead of silently defaulting; "which piece set this field?" has one answer, always | `Site` (pad geodesy + per-flight rail angle) and `Recovery`/`Control` (hardware + flight plan) each mix two concerns, so those get resolved by overrides rather than by ownership |
| (b) field-level contribution: pieces declare individual fields, assembly merges with a precedence order | every field sits exactly where it semantically belongs; `Site` splits cleanly into "the field" and "today's rail setting" | a merge engine, a documented precedence order, and "where did this number come from" becomes a debugging exercise; partial groups mean a piece can leave a field unspecified, which re-introduces the silent-default class of bug `sim.params.replace` was written to avoid (§29 F1); far more code and far more test surface |
| (c) (a) plus a documented escape: pieces own groups, and the scenario's dotted-path `overrides` is the only field-level mechanism | all of (a)'s properties; the one legitimate field-level need (per-flight rail angle, deploy time, `t_max`) has a home that is already built and already tested (`sim.params.replace`) | an override is one more place to look when reading a scenario |

**Recommendation: (c)** — which is (a) with its escape hatch named. The escape hatch already exists
and is the mechanism `Config.derive` and `Variant` are built on, so it costs nothing new.

**Decided (2026-10-14): (c)**, standing as recommended — relayed as near-forced by the code
(`assemble` must be a total function over `dataclasses.fields(Params)`), no objection raised. The
one-owner invariant is pinned by §31.8 #1 and is the thing a later reader must not quietly relax.

**D-50 — assembly timing.** *Purpose: something must turn three pieces into one `Params`.*

| Option | Pros | Cons |
|---|---|---|
| **(a) eager, bound in the scenario module: `CONFIG = SCENARIO.config` at import (recommended)** | the only option compatible with `tests/test_configs.py`'s `CONFIGS[name] is mod.CONFIG` identity pin (F8) without editing it; one assembly per scenario per process; `mod.CONFIG` keeps meaning what it means today, so `configs/__init__.py`'s registry comprehension is literally unchanged | the module has two public names (`SCENARIO` and `CONFIG`) — which is also the point, since `SCENARIO` is where provenance lives |
| (b) lazy `@property` only, no module-level `CONFIG` | one public name; nothing precomputed | breaks the `is` pin (a fresh `Config` per access) → test edits, and `Config` identity stops being stable, which is a subtle behaviour change for any dict keyed by it; `functools.cached_property` does not work on a frozen dataclass |
| (c) lazy property + memoisation inside the registry | identity stable, single public name | the memo cache is state in the package, and the first access ordering becomes observable; more machinery than a module-level constant |

**Recommendation: (a).** Keep `Scenario.config` as a property too (it is one line and makes ad-hoc
compositions in tests and in a future CLI trivial), but the registry stores the eagerly bound object.

**Decided (2026-10-14): (a)**, standing as recommended — relayed as near-forced by
`tests/test_configs.py:82`'s `CONFIGS[name] is mod.CONFIG` identity pin, no objection raised.

**D-51 — `s0`: still written out, or derived from the site's rail?** *Purpose: `s0.theta` and
`site.rail_angle_deg` are two numbers that must agree and nothing checks them — the user's own
template says so in a comment (F5).*

| Option | Pros | Cons |
|---|---|---|
| **(a) `Scenario.s0: State \| None`, `None` → derived as "at rest on the pad, nose along the rail" from the post-override `site.rail_angle_deg` (recommended)** | turns a documented foot-gun into a structural guarantee; **provably free**: `math.radians(90.0) == math.pi / 2` exactly (F6, measured), so all three seeds keep their `s0` bit-for-bit and the existing `s0` pin tests prove it; a tilted-rail scenario changes **one** number instead of two that can drift; an explicit `s0=State(...)` still overrides, so nothing is taken away | one piece of implicit behaviour (mitigated: it is `None`-gated, documented in `schema.py`, and pinned by the ordering test §31.8 #4) |
| (b) `s0` always written out explicitly in the scenario literal, as today | zero magic; what you read is what flies | the foot-gun survives intact and is now *more* likely, since the rail angle moves to a different file from `s0` |
| (c) the `LaunchSite` piece owns `s0` | the pad position and the launch attitude are both site facts | `s0` also carries `vx`/`vz`/`m`, which are not site facts; a scenario wanting a nonzero initial state would need a whole new site piece; and `s0.m` belongs to the rocket when the mass model is on |

**Recommendation: (a).** Deliberately **not** included: deriving `s0.m` from `weight.m` when the mass
model is on (`weight.m_d is not None`). It is the same class of fix and provably inert for all three
seeds (all have `m_d=None`), but it is a second piece of magic in one step; backlog it.

**Decided (user, 2026-10-14): (a)** — `s0: State | None`, `None` deriving "at rest on the pad, nose
along the rail" from the **post-override** `site.rail_angle_deg`. The `s0.m` derivation stays out and
remains a backlog candidate (§31.11).

**D-52 — directory layout and registry shape.** *Purpose: where the pieces physically live, and
whether they are registered by name at all.*

| Option | Pros | Cons |
|---|---|---|
| **(a) four subpackages (`configs/{rockets,sites,weather,scenarios}/`), each with its own explicit-tuple registry, `configs.get`/`names` delegating to scenarios (recommended)** | `git log configs/rockets/my_rocket.py` is that vehicle's history, which is D-30's whole premise, now per *piece*; `ls configs/rockets/` answers "what rockets do I have"; the three §30.4 registry rules transfer verbatim; named pieces are the precondition for ad-hoc CLI composition (D-54); import graph stays a DAG | four new `__init__.py` files (~20 lines each); `configs/` top level stops being a flat list of scenarios |
| (b) flat with prefixes: `configs/rocket_demo_75mm.py`, `configs/site_origin_msl.py`, `configs/scenario_demo_75mm.py` | no new packages, no new `__init__` files; one registry module | the filename prefix becomes the type system; `ls configs/` is a soup of four kinds; the registry file holds four tuples and grows without bound — the §30.10 D-30(b) objection, one level up |
| (c) one `configs/pieces.py` holding every rocket/site/weather as module constants | fewest files; nothing to import-order | kills per-piece git history (directly contradicts D-30, the user-approved reason the package exists); one file every vehicle edit touches; two vehicles edited in one commit share a diff |

**Recommendation: (a).** Note the requirement that survives all three: a flat, whole-`Config` module
must stay registrable, so the user's `_TEMPLATE_my_rocket.py` shape keeps working unchanged (§31.5).

**Decided (user, 2026-10-14): (a)** — four subpackages, `configs/{rockets,sites,weather,scenarios}/`,
each with its own explicit-tuple registry; `configs.get`/`names` delegate to the scenario registry.
Each directory also gains a non-registered `_TEMPLATE_*.py` (§31.5).

**D-53 — names: the pieces, the third axis, and the two default modules.** *Purpose: these strings are
the user's vocabulary for the rest of the project's life.*

| Option | Pros | Cons |
|---|---|---|
| **(a) `Rocket` / `LaunchSite` / `Weather` / `Scenario`, dir `configs/weather/`, defaults `sites/origin_msl.py` + `weather/isa_dry_calm.py` (recommended)** | `Weather` is honest that the piece carries wind and the sounding case as well as the air (D-48a); `LaunchSite` avoids colliding with the `Site` group name while reading naturally; `Scenario` is the word §30.4 already uses for "one complete runnable thing" | "weather" is not the word the user used ("atmosphere"); `Scenario` collides with `apps/weight_aero_tradeoff/scenarios.py`, which is a *study*-input module (risk 6) |
| (b) `Rocket` / `LaunchSite` / `Atmosphere` / `Scenario`, dir `configs/atmospheres/` | matches the user's own request wording exactly | **the class name collides with `sim.params.Atmosphere`**, which the piece contains — `from sim.params import Atmosphere` and `from configs.schema import Atmosphere` in one file is a real hazard; and the name hides the fact that selecting it also selects your wind |
| (c) `Vehicle` / `Pad` / `Ambient` / `Mission` | no collisions anywhere | four new words for four existing concepts; "mission" and "ambient" are not this project's vocabulary |

**Recommendation: (a)**, with `configs/weather/`'s `__init__` docstring opening with "this is the
user's *atmosphere* axis; it carries wind and the sounding case too, because a sounding measures
both" — so the vocabulary gap is closed in the one place a reader meets it.

**Decided (user, 2026-10-14): (a)** — `Rocket` / `LaunchSite` / `Weather` / `Scenario`, folder
`configs/weather/`, defaults `sites/origin_msl.py` and `weather/isa_dry_calm.py`. The
atmosphere-axis sentence in `configs/weather/__init__.py`'s docstring is part of the ticket, not
optional polish.

**D-54 — an ad-hoc composition CLI (`--rocket X --site Y --weather Z`)?** *Purpose: the user's request
is to mix and match; named pieces make composition possible without writing a scenario module at
all.*

| Option | Pros | Cons |
|---|---|---|
| **(a) yes, but as a later, separate ticket: an additive `add_pieces_args`/`resolve_pieces` in `apps/common/cli.py`, building an unnamed `Scenario` named `rocket+site+weather` (recommended)** | this is arguably the *actual* deliverable — "my rocket + my field + today's ISA" with no new file; purely additive to `cli.py` (`--config` and its default path untouched, D-33 preserved); ~25 lines; every app gets it at once | one more CLI surface to document and test; an ad-hoc combination has no `notes` and no provenance in git, so a result worth keeping should still become a scenario module |
| (b) scenario modules only; pieces are never selected from the command line | smallest surface; every run is reproducible from a committed module name | every what-if study ("the same rocket at a 1500 m site") needs a committed file before it can be run once, which is the friction the user is complaining about |
| (c) yes, in this phase, as part of the core work | capability lands with the structure | couples the one file in the blast radius that *would* gain code (`apps/common/cli.py`) to the migration whose gate is "no caller edits" — the two should not share a commit |

**Recommendation: (a).** Keep the migration's gate clean, then add the flags in their own step with
their own test. The structure (named piece registries, D-52a) is what makes it a ~25-line addition
later instead of a redesign.

**Decided (user, 2026-10-14): (a)** — deferred. The ad-hoc composition CLI is **not** part of Steps
71-74 and `apps/common/cli.py` is not edited by this phase at all; it becomes its own later step once
the structure is in and green.

**D-55 — seed migration shape.** *Purpose: the three existing registry names must keep producing
today's exact `Params`/`State`.*

| Option | Pros | Cons |
|---|---|---|
| **(a) split all three: two rocket pieces + `origin_msl` + `isa_dry_calm` + three scenario modules under `configs/scenarios/` (recommended)** | the new structure is exercised by the only configs that have provable gates, so a bug in `assemble` is caught by the four existing exact-equality tests rather than by the user's own vehicle later; `demo_75mm_airbrake` stops being `derive(overrides={})` and becomes what its docstring says it is; `git mv` preserves each file's history | the three seeds' files move, so `apps/airbrake_sizing/targets.py`'s docstring path reference goes stale (one comment line) |
| (b) leave the three seeds exactly where and as they are (flat whole-`Config` modules); build the piece system alongside and use it only for new configs | zero risk to the seeds; smallest diff | the three configs with provable byte-equality gates never exercise `assemble`, so the first real test of the new path is the user's own vehicle, unpinned; `demo_75mm` keeps existing twice (as a config and inside `demo_75mm_airbrake`) — the defect that motivated the split |
| (c) split the two vehicles, keep the seeds' scenario modules flat at `configs/<name>.py` | no path churn at all; rockets become reusable immediately | `configs/` top level mixes scenario modules with four subpackages, so "what configs do I have" needs two places; the inconsistency is permanent |

**Recommendation: (a).** The whole value of the seed migration is that it is the only part of this
design that can be *proved* correct rather than reviewed.

**Decided (user, 2026-10-14): (a)** — all three seeds split into real pieces now, scenario modules
under `configs/scenarios/` via `git mv`. This is what forces §31.6's one named test-path exception,
accepted with the decision.

---

## 31.10 Risks

1. **Scope creep is the main risk, and it is structural, not accidental.** The user asked for three
   axes; the honest design has three pieces, four registries, a scenario object, an assembly function
   and (optionally) a new CLI surface. *Mitigation:* D-47a and D-46a refuse the fourth and fifth
   axes; D-54a pushes the CLI into its own later step; D-49c keeps assembly at 15 lines by banning
   merge logic outright. If the user wants the smallest possible version, the minimal honest subset is
   **D-52a + D-45a + D-55a with no `Weather` piece at all** (rocket + site only), which still covers
   "my rocket at two sites" and can grow the weather axis additively.
2. **Backward compatibility is claimed from a grep, and a grep can miss dynamic access.** §31.6 is
   based on reading every call site, and F10 specifically checked for `isinstance`/`replace`-style
   coupling, but `getattr`-driven or string-keyed access would not show up. *Mitigation:* the phase's
   primary gate is "the full suite green with **no test edits**" — which is a stronger check than the
   grep, since the 300+ existing tests exercise the real call paths. If any test needs an edit, the
   design is wrong, not the gate.
3. **A `Weather` piece can be paired with the wrong `LaunchSite` and be silently wrong.** Sounding
   stations are projected into the local tangent plane relative to `site.lat0_deg`/`lon0_deg`
   (`sim/soundings.py:462-478`), so "launch-day sounding from field A" composed with "field B"
   produces a plausible-looking, meaningless wind field. *Mitigation (recommended):* notes-only — each
   sounding-backed `Weather` module's `notes` names the site it belongs to, and the "every registered
   scenario flies" test stays. A `Weather.site_hint` field warned about at assembly is a ~5-line later
   addition, deliberately not proposed now because input validation is something this project has
   decided not to own (architecture.md §7).
4. **The two "pin the defaults" modules look like unfinished files.** `Weather(name="isa_dry_calm")`
   with no arguments is exactly right (§31.7) and exactly what a reader will try to "fix" by spelling
   the fields out — which would silently break byte-equality with every pre-split config the day
   `sim/params.py`'s defaults change. *Mitigation:* a one-sentence docstring in each saying so, and the
   four exact-equality seed tests, which would fail loudly.
5. **The `s0` derivation (D-51a) has one wrong order of operations, and it is the obvious one.**
   Deriving `s0` before applying `overrides` leaves a scenario that overrides `site.rail_angle_deg`
   with a stale attitude — the exact foot-gun the feature advertises fixing, now hidden inside the
   mechanism. *Mitigation:* the ordering is stated as a rule in §31.4, and §31.8 #4 is its regression
   test.
6. **Two things in this repo will now be called "scenario".** `configs/scenarios/` (a complete
   runnable combination) and `apps/weight_aero_tradeoff/scenarios.py` (App 5's list of study
   `Variant`s). The §30.3 two-kinds convention already distinguishes them, but the word now appears on
   both sides. *Mitigation:* the §30.3 convention restated in `configs/scenarios/__init__.py`'s
   docstring; alternatively D-53 picks a different word for one of them.
7. **A future thirteenth `Params` group would silently take defaults everywhere.** Assembly names the
   twelve groups explicitly, so a new one added in `sim/params.py` (3D state work, for instance) would
   not be settable from any piece. *Mitigation:* §31.8 #1 — the structural test that `assemble` covers
   every field of `Params` — turns that into a failing test at the moment the group is added.
8. **The user's in-progress vehicle is on another branch.** `configs/_TEMPLATE_my_rocket.py`
   (`usage/my-rocket`) is a flat whole-`Config` module; an untracked copy of it also sits in this
   working tree. Nothing here touches either. *Mitigation:* §31.5's requirement that a flat
   `CONFIG: Config` module stays registrable forever — the template registers unchanged after this
   lands, and splitting it into pieces becomes optional, later, and the user's choice. Whoever
   implements this must verify that claim against the template before closing the phase.
9. **Three pieces means three places to look for a number.** Today "what is this config" is one file;
   after the split it is four (rocket, site, weather, scenario). *Mitigation:* `--list-configs` gains
   the three piece names per scenario (via `get_scenario`, §31.6), so the mapping is printable; and
   the scenario module is short enough to read in one screen.
10. **`Config.derive` now derives from an assembled object, so a derived config has no pieces.**
    `cfg.derive(name, {"weight.m": 2.0})` still returns a `Config` (unchanged behaviour), but
    `get_scenario` cannot report provenance for it, and its overrides live outside any piece — the
    §31.1 indirection complaint, still true for study deltas. *Mitigation:* that is the correct
    behaviour for a *study* delta (§30.3's two kinds); `derive` is not the reuse mechanism any more,
    composition is.

---

## 31.11 Rejected options, and backlog candidates

**Rejected: changing `sim/params.py` to mirror the three-piece split** (e.g. `Params.rocket`,
`Params.environment`). `Params` and its twelve groups are the engine's public contract — `dynamics`,
`forces`, `control`, `wind`, `atmosphere`, `gravity`, `soundings`, `integrate` and ~300 tests consume
the groups directly, and §28.3's "one group per module that owns a dispatch" is the reason the group
set looks the way it does. The authoring layer wanting a different shape is not a reason to move the
consumption layer.

**Rejected: a `Motor` piece.** `thrust` (curve filename, nozzle exit area, reference pressure) is an
obvious fourth axis, and App 3 already sweeps it — *as a study input*, `apps/motor_selection/
motors.py`'s `list[MotorEntry]` with `overrides`, which §30.3's convention and D-32 both put outside
`configs/`. Promoting the motor to a config piece would create a second home for the same concept.
**Backlog candidate** if the user later wants named motor *installations* (a curve plus its own `A_e`,
`p_ref` and `I_sp`) rather than a sweep list.

**Rejected: field-level piece composition with a precedence order** (D-49b). The merge engine, the
documented precedence and the "where did this number come from" debugging cost all exceed what the
three mixed-concern groups (`Site`, `Recovery`, `Control`) actually need, and the dotted-path
`overrides` escape covers them in one line.

**Rejected: auto-discovering piece modules.** Same answer as §30.4, now four times over: a
half-finished draft rocket must not break every app's import by existing.

**Rejected: validating cross-piece consistency at assembly** (sounding case vs site coordinates,
canopy area vs vehicle mass, rail angle vs `s0`). This project does not own a validator
(architecture.md §7); the one consistency that *can* be made structural instead of checked is the rail
angle, which is why D-51a derives `s0` rather than asserting on it.

**Rejected: a `Scenario.derive` / `Variant`-over-`Scenario`.** A scenario is four names and a notes
string; a derive chain over compositions is where this design would start to become hard to read.
`Variant` keeps operating on `Config`, where it is already tested and already used by App 3 and App 5.

**Rejected: a `load_scenario_json(path)` loader in this phase.** Same escape hatch §30.10's D-30 noted
and declined: every app takes a `Config` object, so a loader stays a later ~15-line addition that
changes nothing else.

**Backlog candidates this opens** (numbering to be assigned by the orchestrator against
`docs/roadmap.md`'s backlog, not claimed here):

- Ad-hoc piece composition from the command line (`--rocket/--site/--weather`), if D-54a is approved
  as a later step.
- `s0.m` derived from `rocket.weight.m` when the mass model is on (`m_d is not None`) — provably inert
  for all three seeds, deliberately deferred per D-51's note.
- A named `Fidelity` piece with its own registry, if comparing gravity/solver fidelity across
  scenarios becomes routine (D-47b).
- `Weather.site_hint` + an assembly-time warning for sounding/site mismatch (risk 3).
- Named motor installations as a fourth piece, if the motor becomes a reused object rather than a
  sweep entry.

---

## 31.12 Implementation tickets (Steps 71-74)

Same Files/Spec/Do/Check/Commit shape every roadmap step uses. Step numbers continue the sequence
(last used: **Step 70**); the exact `docs/roadmap.md` placement is the orchestrator's to settle. Four
steps, one commit each, **strictly sequential** — every one of them touches `configs/`, and Step 73 is
a switch-over that must land atomically, so **none is `parallel_safe` against another**. Phase 3 keeps
its reserved 28-32 block.

**No `sim/` file is touched by any ticket in this phase.** Neither is any `apps/` file, any `run_*.py`
wrapper, or `run.py` — that is the whole content of D-45a, and `git diff --stat` is the check.
`apps/common/cli.py` is explicitly *not* edited either (D-54 deferred the ad-hoc CLI).

### The phase gate, stated once

Every ticket inherits all four of these; a step that cannot show them is not done:

1. **Full suite green, no test file edited** — except `tests/test_configs.py`'s two `configs.demo_75mm`
   module-path strings on line 206, in Step 73 only (§31.6 amendment). New tests go in **new** files so
   this stays mechanically checkable (`git diff --stat -- tests/` shows additions only).
2. **The four existing exact-equality pins in `tests/test_configs.py` are the seed-migration gate** —
   `test_toy_05kg_params_pin_run_py_literal_exactly`,
   `test_toy_05kg_s0_pins_run_py_literal_exactly`,
   `test_demo_75mm_params_pin_demo_baseline_exactly`,
   `test_demo_75mm_s0_pins_compare_motors_main_literal_exactly`. They compare against independent
   reconstructions (`_toy_05kg_literal()` in the test file, `_demo_baseline()` in App 3), which is
   exactly why Step 63 wrote them that way and why the migration is provable rather than reviewable.
3. **The structural one-owner test** — `assemble`'s keyword set pinned against
   `dataclasses.fields(Params)` (§31.8 #1). Lands in Step 71 and must stay green in every later step.
4. **`git diff --stat` boundary check** — the files touched are exactly the ticket's own
   Module/boundaries list, nothing else.

---

### [Step 71] `configs/schema.py` — the four piece types and `assemble`

- **Module/boundaries:** `configs/schema.py` (**append only** — `Config` and `Variant` are not
  edited, not reordered and not re-docstringed); new `tests/test_config_pieces.py`. **No other
  `configs/` file. No `sim/` file, no `apps/` file, no `run*.py`.**
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (every later step builds on this file; nothing else in the phase can start)
- **Spec slice:** §31.4 in full (it carries the dataclass listings, `assemble`'s body shape and the
  ordering rule); §31.3's placement table for which group goes where; §31.2 **F5/F6/F8** (why `s0` is
  derived, why `math.radians(90.0)` is safe, why assembly is eager); §31.8 items 1, 4. Nothing else.
- **Do:** add `Rocket`, `LaunchSite`, `Weather`, `Scenario` and the module-level `assemble(sc)` /
  `_pad_state(site)` exactly as §31.4 sketches them — frozen dataclasses, `default_factory` for every
  group, no inheritance, no builders, no validation. `Scenario.config` is a plain `@property`
  returning `assemble(self)`. The three ordering steps (gather → `overrides` → derive `s0`) must appear
  in that order with §31.4's comment naming why step 3 follows step 2. Extend the module docstring
  with: the one-owner invariant and the fact that §31.8 #1 pins it; the import rule, now stated for
  pieces as well (`from configs.schema import Rocket`, never `from configs import …`, never reaching
  up into `configs.scenarios`); and one sentence that `Config`/`Variant` are unchanged and remain the
  consumption-level API every app uses. `__all__` grows by five names.
- **Check:** new `tests/test_config_pieces.py`, covering §31.8 #1 and #4 plus the basics: assembling a
  scenario from hand-built **non-default** pieces leaves no `Params` group equal to its default (the
  one-owner structural test); `assemble`'s keyword set equals `{f.name for f in
  dataclasses.fields(Params)}`; `overrides={"site.rail_angle_deg": 85.0}` with `s0=None` yields
  `s0.theta == math.radians(85.0)` (the ordering regression test); `s0=None` with a 90° rail yields
  **exactly** `math.pi / 2` (F6); an explicit `s0` is passed through untouched; `Scenario.config`
  returns a `Config` whose `name`/`notes` are the scenario's; the pieces are frozen
  (`dataclasses.FrozenInstanceError` on assignment). Full suite green, count up by this step's own
  tests only. `python -c "import configs; print(configs.names())"` still prints the same three names
  — nothing is wired up yet, by design.
- **Commit:** "Step 71 (Phase 2.15): configs/schema.py -- Rocket/LaunchSite/Weather/Scenario + assemble()"

---

### [Step 72] The four subpackages, their registries, and the four TEMPLATE modules

- **Module/boundaries:** new `configs/rockets/{__init__.py,_TEMPLATE_rocket.py}`; new
  `configs/sites/{__init__.py,_TEMPLATE_site.py,origin_msl.py}`; new
  `configs/weather/{__init__.py,_TEMPLATE_weather.py,isa_dry_calm.py}`; new
  `configs/scenarios/{__init__.py,_TEMPLATE_scenario.py}`; new `tests/test_config_registries.py`.
  **`configs/__init__.py` is NOT edited in this step. `configs/schema.py` is not edited. No `sim/`
  file, no `apps/` file, no `run*.py`.**
- **Assignee:** developer
- **depends_on:** [Step 71]
- **parallel_safe:** false
- **Spec slice:** §31.5 in full (the directory tree, the three registry rules, the three template
  rules, the import DAG); §31.7's "the two 'pin the defaults' pieces, and why they are argument-free";
  §31.8 items 2, 3, 6; `configs/__init__.py` as it stands today is the template for all four new
  registry files. Nothing else.
- **Do:** four `__init__.py` files, each a ~20-line copy of the existing registry shape — an explicit
  `_MODULES` tuple, a `{name: obj}` dict (`ROCKETS`/`SITES`/`WEATHER`/`SCENARIOS`), `names()`, and a
  `get()` whose `KeyError` lists every available name. `configs/weather/__init__.py`'s docstring opens
  with the atmosphere-axis sentence D-53 requires. `configs/scenarios/__init__.py` ships with
  **`_MODULES = ()`** — deliberately empty for exactly one commit, inert because nothing delegates to
  it yet; say so in its docstring so it does not read as an omission.
  Then the two argument-free default pieces: `sites/origin_msl.py` →
  `SITE = LaunchSite(name="origin_msl", site=Site())` and `weather/isa_dry_calm.py` →
  `WEATHER = Weather(name="isa_dry_calm")`, each with the §31.7 sentence explaining that the *absence*
  of arguments is the point (they pin `sim/params.py`'s defaults, which is what the pre-split configs
  relied on) and that spelling the fields out would break byte-equality the day a default changes.
  Then the four `_TEMPLATE_*.py` modules per §31.5: every field on its own line with a
  `# <-- fill this in` comment giving units, meaning and the consequence of leaving it alone; the
  user's `configs/_TEMPLATE_my_rocket.py` tone and density are the reference, and the vehicle-group
  comments can be lifted from it where they already say the right thing. Each template docstring ends
  with the three-step instruction: fill in, rename the file **and** the `name=` string, then add one
  line to this package's `_MODULES`. `_TEMPLATE_scenario.py` additionally shows pieces referenced **by
  import** (`from configs.rockets.demo_75mm import ROCKET` — commented as "replace with your own once
  you have one") and carries a commented note that a flat whole-`Config` module stays legal.
  **No template is added to any `_MODULES` tuple.**
- **Check:** new `tests/test_config_registries.py`: registry integrity ×4 (basename equality, no
  duplicate names, `names()` covers the dict, unknown-name `KeyError` lists every name — the existing
  `tests/test_configs.py` block, parametrised over the four packages, skipping the empty scenario
  registry where a check is vacuous); no-circular-import ×4 in a fresh interpreter, each subpackage
  imported first (`python -c "import configs.rockets._TEMPLATE_rocket"` and the three siblings);
  §31.8 #6 — **each of `configs/rockets/_TEMPLATE_rocket.py`, `configs/sites/_TEMPLATE_site.py`,
  `configs/weather/_TEMPLATE_weather.py`, `configs/scenarios/_TEMPLATE_scenario.py` imports cleanly,
  exposes its expected object name, and its `.name` is absent from the corresponding registry**;
  `sites.get("origin_msl").site == Site()` and `weather.get("isa_dry_calm")`'s three groups equal
  `Atmosphere()`/`Soundings()`/`Wind()` exactly. Full suite green, no test file edited, count up by
  this step's own tests only. `configs.names()` still prints today's three names (`configs/__init__.py`
  untouched).
- **Commit:** "Step 72 (Phase 2.15): configs/{rockets,sites,weather,scenarios}/ -- registries, templates, default pieces"

---

### [Step 73] The switch-over — seeds split into pieces, `configs.get` delegates to scenarios

**This is the step the phase's gate exists for.** It is the only one that can change what any existing
caller sees, and it must be provably a no-op for all three seed names.

- **Module/boundaries:** `git mv configs/toy_05kg.py configs/rockets/toy_05kg.py`;
  `git mv configs/demo_75mm.py configs/rockets/demo_75mm.py`;
  `git mv configs/demo_75mm_airbrake.py configs/scenarios/demo_75mm_airbrake.py`; new
  `configs/scenarios/{toy_05kg.py,demo_75mm.py}`; `configs/rockets/__init__.py` and
  `configs/scenarios/__init__.py` (`_MODULES` tuples filled in); `configs/__init__.py` (rewritten to
  delegate); `tests/test_configs.py` (**line 206 only**, two occurrences of the string
  `configs.demo_75mm` → `configs.scenarios.demo_75mm`); new `tests/test_config_migration.py`.
  **No `sim/` file, no `apps/` file, no `run*.py`, no other test file.**
- **Assignee:** developer
- **depends_on:** [Step 72]
- **parallel_safe:** false
- **Spec slice:** §31.7 in full (what each seed becomes, and the gate); §31.6 in full including the
  2026-10-14 amendment (the one permitted test edit, and the file-by-file table of what must *not*
  change); §31.4's "eager or lazy" (the two module-level names); §31.8 items 5, 7, 8. Nothing else.
- **Do:** use **`git mv`**, not delete-and-create, so each vehicle's history follows it — the flat
  seed modules carry the numbers, so they move to `configs/rockets/`, while
  `demo_75mm_airbrake.py` carries no vehicle numbers at all and moves to `configs/scenarios/`.
  Reduce each moved vehicle module to a `Rocket`: the four vehicle groups **number-for-number, every
  justifying comment kept verbatim**, the long provenance docstring kept with the rocket (including
  `demo_75mm`'s `thrust.motor_curve="placeholder.csv"` judgment-call note from Step 63 — **do not
  "fix" it to `synthetic_large.csv"`**, the exact-equality pin against `_demo_baseline()` depends on
  it), and the `notes=` string moved to the scenario. Each exposes `ROCKET`.
  The three scenario modules each expose exactly two public names:
  `SCENARIO = Scenario(name=…, rocket=ROCKET, site=SITE, weather=WEATHER, notes=…)` and
  `CONFIG: Config = SCENARIO.config` (D-50a, F8). `s0` is **omitted** so it is derived (D-51a); the
  `notes=` strings are the current ones **byte-for-byte**, because `--list-configs` and App 5's table
  print their first line. `demo_75mm_airbrake.py` becomes the same three pieces under its own name
  with its own notes — the `derive(overrides={})` call and its apologetic docstring go away, replaced
  by one sentence saying the composition now states directly what that docstring used to explain.
  Rewrite `configs/__init__.py`: import the four subpackages, re-export
  `Config`/`Variant`/`Rocket`/`LaunchSite`/`Weather`/`Scenario` from `configs.schema`, delegate
  `CONFIGS`/`names()`/`get()` to the scenario registry (one implementation, not a copy), add
  `get_scenario(name) -> Scenario | None`, and keep `_MODULES = scenarios._MODULES` so
  `test_registry_keys_equal_module_basenames` passes unedited. The package docstring records that
  `get()` resolves a **scenario** name and that the pieces behind it are reachable via
  `get_scenario`.
- **Check:** the gate, in this order, pasted into the step report:
  1. **The four exact-equality pins in `tests/test_configs.py` green, unedited** — this is the proof
     that `assemble` reproduces every implicit default and that the derived `s0` is bit-for-bit
     (`math.radians(90.0) == math.pi / 2`, F6).
  2. **Full suite green with no test file edited except the one permitted line** —
     `git diff -- tests/` must show exactly two changed strings on `tests/test_configs.py:206` and
     additions in new files. Anything else means the step is wrong, not the gate.
  3. New `tests/test_config_migration.py`: `get("demo_75mm_airbrake").params ==
     get("demo_75mm").params` (today's `derive({})` relation, now a composition identity); a
     `notes`-string pin for all three seeds against the current literals; `get_scenario("demo_75mm")`
     returns a `Scenario` whose `.rocket.name == "demo_75mm"`, `.site.name == "origin_msl"`,
     `.weather.name == "isa_dry_calm"`; §31.8 #7, a flat test-local `CONFIG`-only module registers and
     `get_scenario` returns `None` for it; §31.8 #8, each migrated rocket group equals the
     corresponding group of the independent reconstructions (`_demo_baseline()`,
     `tests/test_configs.py`'s `_toy_05kg_literal()`); §31.8 #5, every registered scenario still flies.
  4. **Files that must exist and import cleanly at the end of this step:**
     `configs/rockets/{_TEMPLATE_rocket.py,toy_05kg.py,demo_75mm.py}`,
     `configs/sites/{_TEMPLATE_site.py,origin_msl.py}`,
     `configs/weather/{_TEMPLATE_weather.py,isa_dry_calm.py}`,
     `configs/scenarios/{_TEMPLATE_scenario.py,toy_05kg.py,demo_75mm.py,demo_75mm_airbrake.py}` —
     checked by `python -c "import …"` for each, with the four `_TEMPLATE_*` still absent from every
     registry. The flat `configs/{toy_05kg,demo_75mm,demo_75mm_airbrake}.py` must be **gone**.
  5. **All five entry points run from a clean checkout** (`run.py`, `run_motor_sweep.py`,
     `run_airbrake.py`, `run_cfd_conditions.py`, `run_trade.py`), plus `--list-configs` on one of them
     printing the same three names with the same first-line notes as before the step. App 3's printed
     table and `output/motor_selection.csv` byte-identical to a pre-step capture — the Step-64/69 gate,
     re-run because this step is what could break it.
  6. `git diff --stat` shows only the Module/boundaries files.
- **Commit:** "Step 73 (Phase 2.15): seeds split into rocket/site/weather pieces; configs.get resolves scenarios"

---

### [Step 74] One worked mix-and-match demo, and the "how do I add mine" guide

Without this step the phase ships without a single example of the thing it was built for: after Step
73 every registered scenario still uses `origin_msl` + `isa_dry_calm`, so nothing in the tree
demonstrates — or exercises end to end — a non-default site or a non-default day's weather.

- **Module/boundaries:** new `configs/sites/highland_1500m.py`; new `configs/weather/breezy_isa.py`;
  new `configs/scenarios/demo_75mm_highland.py`; `configs/sites/__init__.py`,
  `configs/weather/__init__.py`, `configs/scenarios/__init__.py` (one `_MODULES` line each);
  `configs/__init__.py` (**docstring only**); `tests/test_config_migration.py` (append). **No `sim/`
  file, no `apps/` file, no `run*.py`, no other test file.**
- **Assignee:** developer
- **depends_on:** [Step 73]
- **parallel_safe:** false
- **Spec slice:** §31.3.2/§31.3.3/§31.3.4 (what a non-default site and a non-default weather piece may
  legitimately set); §31.2 **F1/F3/F5** (site elevation feeds the atmosphere; `site.azimuth_deg`
  rotates the wind; the rail angle now drives `s0`); §31.10 risk 3 (the sounding/site pairing caveat —
  which is why this demo uses **analytic** wind, not a sounding case). Nothing else.
- **Do:** one synthetic launch site — `highland_1500m`, `h0_m=1500.0` with a plausible latitude, a
  3 m rail at `rail_angle_deg=85.0` — clearly marked synthetic in its notes, the same convention
  `demo_75mm`'s own notes already use ("the architect's own synthetic vehicle"). One weather piece,
  `breezy_isa`: `Atmosphere(model="isa")` plus `Wind(model="analytic", ref_ms=…, dir_deg=…)`, no
  sounding case (risk 3). One scenario, `demo_75mm_highland`, pairing them with the **existing,
  unmodified** `configs/rockets/demo_75mm.py` — the entire point being that the vehicle module is not
  touched, re-typed or derived. Its notes say in one line what it demonstrates. Then turn
  `configs/__init__.py`'s package docstring into the short "how do I add my own" guide: the four
  directories, what each owns, the three-step template instruction, and the one-line statement that a
  flat whole-`Config` module is still legal for anyone who prefers one file.
- **Check:** `demo_75mm_highland` flies (it is picked up automatically by the existing parametrised
  "every registered config flies" test — **note in the step report that this test's count rises by one
  with no test edit**, which is expected and is not an anomaly); the tilted rail is visible in the
  assembled scenario (`get("demo_75mm_highland").s0.theta == math.radians(85.0)`, the D-51a derivation
  doing real work for the first time); `get("demo_75mm_highland").params.weight ==
  get("demo_75mm").params.weight` and the same for `lengths`/`thrust`/`aero` — **the proof that one
  vehicle now serves two sites with zero duplication**, which is the user's original request reduced
  to one assertion; `params.site.h0_m == 1500.0` and `params.wind.model == "analytic"`. Full suite
  green, no test file edited (appends only to this phase's own new file). `--list-configs` now prints
  four names — a user-visible, intended change; state it in the report.
- **Commit:** "Step 74 (Phase 2.15): demo_75mm_highland -- one rocket, two sites, zero duplication"

---

### Not in this ticket set, deliberately

- **The ad-hoc composition CLI** (`--rocket/--site/--weather`) — D-54a defers it to its own later
  step, so `apps/common/cli.py` is untouched here and the Step 73 gate stays clean.
- **Tracker, roadmap and `status.json` updates** — the orchestrator's, not a developer ticket. The
  `docs/architecture.md` §31 pointer section is already written.
- **Anything in `docs/latex/`** — no new physics, so no LaTeX pass (unlike Phase 2.14).
- **The user's `configs/_TEMPLATE_my_rocket.py`** (`usage/my-rocket`) — not touched by any ticket. §31.5
  rule and §31.8 #7 are what guarantee it still registers after this lands; whoever closes the phase
  should confirm that against the actual file before calling it done (§31.10 risk 8).

# Architecture §28 — Phase 2.11 rewrite pass

## Summary

Design proposal (not yet approved, no code written) for the pre-Step-30 rewrite pass the user asked
for: (1) `Params` split from one flat 70-field frozen dataclass into composed sub-dataclasses
(`Weight`/`Thrust`/`Lengths`/`Aero`/`Solver` + six more groups proposed here); (2) `sim/aero.py`
rewritten as an explicit three-way dispatch (`"constant"` | `"linearized"` | `"table"`) with the
placeholder raw-force fields `A_x`/`A_z`/`A_m` replaced by real dimensionless coefficients times
`q·S` (and `q·S·d_ref` for the moment) — **this is the one deliberately non-bit-for-bit change in
the pass**; (3) a structural control-coefficient seam so a future controller can perturb
`C_x`/`C_z`/`C_m`/`l1` directly instead of only adding a separate drag area; (4) an opt-in
fixed-step **sampled-data / zero-order-hold** integration mode, which is what finally unblocks
backlog **B11** and **B12**; (5) `run.py` reduced to scenario definition only, with summary/plot/CSV/
sweep machinery moved to a new `sim/report.py`; (6) a structural/notational LaTeX pass bringing
`§Aerodynamics` into the same explicit-model-variant shape `§Gravity`/`§Atmosphere`/`§Wind` already
have.

Everything else stays bit-for-bit: every default-configuration result is preserved except the
`aero_model="constant"` scenarios, whose numbers change by design (that is the bug being fixed).
Implementation is proposed as **Steps 50-59**, ten independently testable and committable steps, in
a mostly linear dependency chain. 17 decision points are flagged for the user in §28.10 rather than
decided here.

**Not covered, deliberately untouched:** Step 30 (3D rotational EOM) and
`docs/latex/research/3d_equations_of_motion.md` stay paused. No controller and no turbulence model
is written here — only the integrator capability they need.

---

## Contents

- [§28.1 Scope, method, and what "grilling" would have added](#281-scope-method-and-what-grilling-would-have-added)
- [§28.2 Findings from reading the current code (the facts this design rests on)](#282-findings-from-reading-the-current-code-the-facts-this-design-rests-on)
- [§28.3 `Params` composition — the proposed group structure](#283-params-composition--the-proposed-group-structure)
- [§28.4 `dataclasses.replace` under nesting — the dotted-path helper](#284-dataclassesreplace-under-nesting--the-dotted-path-helper)
- [§28.5 Aero rewrite — explicit three-way dispatch](#285-aero-rewrite--explicit-three-way-dispatch)
- [§28.6 The control-coefficient seam (structure only)](#286-the-control-coefficient-seam-structure-only)
- [§28.7 `Solver` group and `run_sim(p, s0)`](#287-solver-group-and-run_simp-s0)
- [§28.8 Sampled-data / zero-order-hold integration mode](#288-sampled-data--zero-order-hold-integration-mode)
- [§28.9 `run.py` → `sim/report.py`](#289-runpy--simreportpy)
- [§28.10 LaTeX rewrite plan](#2810-latex-rewrite-plan)
- [§28.11 Implementation steps 50-59](#2811-implementation-steps-50-59)
- [§28.12 Decision points for the user](#2812-decision-points-for-the-user)
- [§28.13 Risks](#2813-risks)
- [§28.14 Rejected options](#2814-rejected-options)

---

## 28.1 Scope, method, and what "grilling" would have added

This is **incremental architecture on an already-approved stack** (Python 3.12 + numpy + scipy +
matplotlib, flat `sim/` package, dispatch-dict model selection) — not a greenfield design and not a
stack pivot. No new dependency is proposed, no library version question arises, so no Context7
lookup was needed and a full grilling interview is not the mandatory gate it would be for a new
stack. The decision points that *would* have come out of a grilling session are instead enumerated
explicitly in §28.12, each with options and a recommendation, which is the same end state.

Everything below was derived by reading the current code in full: `sim/params.py`,
`sim/aero.py`, `sim/forces.py`, `sim/dynamics.py`, `sim/integrate.py`, `sim/control.py`, `run.py`,
`apps/cfd_conditions/select_conditions.py`, plus targeted greps over `tests/` and
`docs/latex/{main.tex,sections-ai/*.tex}`. Where a claim is load-bearing, the file and line it came
from is named so it can be re-checked rather than taken on trust.

---

## 28.2 Findings from reading the current code (the facts this design rests on)

These are the measured facts that set the size and the risk of each step. Several of them are
better news than expected.

**F1 — `aero_model` is dispatched only in `sim/forces.py`, never in `sim/aero.py`.**
`forces.aero_force_body` (`forces.py:186-193`) and `forces.aero_moment_y` (`forces.py:228-235`) each
carry their own `if p.aero_model == "constant" / elif "coefficients" / else raise ValueError`.
`sim/aero.py` contains no reference to `aero_model` at all — it dispatches independently on the
truthiness of `p.aero_table` inside each of its five public functions. So there are **two
independent, uncoordinated selectors** for one model family. That is the structural defect the
rewrite fixes.

**F2 — the two selectors can disagree, and one of them already leaks.**
`dynamics.derivatives` calls `aero.cop_l1(flow.alpha, flow.M, p)` **unconditionally**
(`dynamics.py:299`), outside any `aero_model` branch. With `aero_model="constant"` and a table
configured, the force/moment come from the raw constants while the CoP moment arm comes from the
table. Nothing in the repo currently sets that combination, but nothing prevents it either.

**F3 — the `"constant"` regime's `A_x`/`A_z`/`A_m` are raw Newtons, not scaled by `q`.**
`forces.py:187-188` and `forces.py:229`. This is the user-identified defect. Consequence worth
naming: the `"constant"` model is today the only aero model that does **not** read the atmosphere,
which `architecture.md` §12 relies on explicitly ("`constant` ignores the atmosphere entirely, which
would make this comparison vacuous" — the reason `run.py`'s atmosphere sweep switches to
`"coefficients"`). After this rewrite that sentence is false: every aero model is
dynamic-pressure-scaled and therefore atmosphere-coupled. §12 needs a one-line correction.

**F4 — almost nothing actually uses the raw-force path with nonzero values.** Measured by grep over
`tests/`, `run.py`, `apps/`: exactly **one** test sets a nonzero one
(`tests/test_forces.py:57`, `A_x=1.23, A_z=2.0, A_m=0.5`, a closed-form moment check), plus
`run.py:118-120` and `apps/cfd_conditions/select_conditions.py:205` (both `A_x=0.5, A_z=0.0,
A_m=0.0`). Every other occurrence sets all three to `0.0`. Since `C_x=C_z=C_m=0.0` (or `S=0.0`)
produces an exactly-zero force in the new convention too, **all of those stay bit-for-bit**. The
non-bit-for-bit blast radius of the aero rewrite is three call sites, not the whole suite.

**F5 — the migration surface for `Params` is large but mechanical.** 164 `Params(...)`
constructions (163 in `tests/`, 1 in `run.py`, 1 in `apps/`), ~104 `replace(...)` calls, across
6831 lines of tests. Every miss is a loud `TypeError`/`AttributeError`, never a silent wrong number.

**F6 — `run_sim`'s solver kwargs are used heavily in tests.** ~60 call sites pass
`method=`/`dt=`/`t_max=`/`rtol=`. Moving them onto `Params` therefore touches those sites; §28.7
proposes how.

**F7 — `tests/test_plotting.py:22` imports `_flight_summary` and `sweep` from `run`.** A test
importing from the top-level entry script is itself an argument for the `sim/report.py` move.

**F8 — the RHS computes `flow_state` three times per call.** `dynamics.derivatives` once
(`dynamics.py:298`), `forces.aero_force_body` once (`forces.py:185`), `forces.aero_moment_y` once
(`forces.py:227`). Each one re-runs the atmosphere and wind models. Collapsing them is pure win and
bit-for-bit (deterministic pure function, same operands), but it is a separable step (Step 56), not
smuggled into the aero rewrite.

**F9 — `tests/test_aero.py` constructs `Params(..., aero_table="example.csv")` without any
`aero_model` at all** (lines 39, 62, 78, 107, 201, 298, 345, 376, 417) and calls `aero.C_A`/`C_N`/
`C_m`/`C_mq`/`cop_l1` directly. Under explicit dispatch those fixtures must set
`aero.model="table"`. Mechanical, but it is ~10 fixtures plus two parametrised bit-for-bit variants
in `tests/test_forces.py:493-495`.

**F10 — `apps/cfd_conditions/select_conditions.py` is untracked in git** (`git status` shows `?? apps/`)
and constructs `Params(m=0.5, I=0.05, l1=0.3, l2=0.4, motor_curve=..., A_x=0.5, A_z=0.0, A_m=0.0)`
with the old flat names. It breaks at Step 51 and again at Step 55. See D-15.

**F11 — the LaTeX does not document the `"constant"` aero model at all.**
`models.tex:250-266` (`§Aerodynamics > Force magnitudes`) states only the coefficient convention
`A_x = qSC_A`, `A_z = qSC_N`, `A_m = qSd_{ref}C_m`; `models.tex:275-299` (`> Coefficients`) describes
the table and a "constant/linear fallback" as one thing, not two models. So the raw-force placeholder
exists **only in code** and has never had document standing — which makes removing it a notational
pass, not a physics change, exactly as the user judged.

**F12 — the LaTeX already anticipates both new seams.** `main.tex:154-155` says an air brake
"enters as a switchable change to $C_A$ and to the CoP" — that is precisely the §28.6 hook.
`main.tex:189-193` and `main.tex:106-111` already record the sampled-data loop as waiting on "a
different integration strategy than this document's solver assumes" — that is precisely §28.8. Both
LaTeX edits are therefore *updating a stated dependency to "now available"*, not inventing content.

**F13 — reference-symbol history.** The report-finalization pass (2026-09-27, recorded in
`PROJECT-STATUS.md`) deliberately renamed the reference area/length from `A,l` to `S,d_ref`
throughout `§Analytical analysis` to fix a symbol collision, and `rocket-2d.tex:74-81` uses `A` for
the **nose tip** point. The user's requested new field name `A` for reference area therefore
reintroduces a collision that was explicitly removed once already. See D-4.

---

## 28.3 `Params` composition — the proposed group structure

Twelve groups plus one top-level shared constant. The five the user named (`Weight`, `Thrust`,
`Lengths`, `Aero`, `Solver`) are as specified, including `thrust_misalign_deg` living in `Lengths`
per the user's explicit choice. The other seven are this document's proposal (D-1).

Guiding rule: **one group per module that owns a dispatch**, so the group structure mirrors the
code structure (`sim/gravity.py` ↔ `Gravity`, `sim/wind.py` ↔ `Wind`, `sim/soundings.py` ↔
`Soundings`, …). That is the only grouping rule that answers "where does this field go?" without
case-by-case taste.

```python
# sim/params.py

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
    C_x: float = 0.0              # axial-force coefficient [-]
    C_z: float = 0.0              # normal-force coefficient [-]
    C_m: float = 0.0              # pitching-moment coefficient [-]
    # model == "linearized"
    C_A0: float = 0.0
    C_N_alpha: float = 0.0        # [1/rad]
    C_m_alpha: float = 0.0        # [1/rad]
    # model == "table"
    table: str = ""               # file under data/aero/
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

@dataclass(frozen=True)
class Params:
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
```

### Notes on specific placements

- **`g0` stays top-level, not in `Gravity`.** Today's `Params.g` has two unrelated readers:
  `gravity.py`'s `"constant"` magnitude model, and `dynamics.py:244`'s `dm/dt = -T/(I_sp·g0)`, where
  it is the *propulsion* standard-gravity constant and must not track a selected gravity model.
  Keeping it a single top-level shared constant makes that dual role explicit; burying it in
  `Gravity` would invite a future reader to make it model-dependent. Renamed `g` → `g0` because that
  is what it already is (the `params.py:28` comment says so). Alternative in D-1.
- **`Soundings` is its own group, not duplicated into `Atmosphere` and `Wind`.** `sounding_case` and
  the tier-3 grid/interpolation fields are read by *both* `sim/atmosphere.py` and `sim/wind.py`, at
  the same altitude of the same file — Step 45 made that shared reading load-bearing. Duplicating
  the case name into two groups creates a configuration that can be internally inconsistent; a
  shared group cannot.
- **`L_rail`/`rail_angle_deg` go in `Site`, not `Recovery`.** The rail is pad infrastructure, not
  recovery hardware. `Site` then means "the launch site and what is bolted to it", which also keeps
  `azimuth_deg` (used by gravity, wind projection and `sim/rotation.py`) in one obvious place.
  Alternative: a separate `Rail` group (D-1).
- **`c_mq` stays in `Aero`, not a separate group.** It is a coefficient like the others and is
  already overridable by the table's optional `c_mq` column.
- **`l_ref` and `d_ref` stay two different fields**, as today. `l_ref` is the Reynolds length;
  `d_ref` is the moment reference length and the static-margin denominator. They are not
  interchangeable (the report-finalization pass already untangled this once).
- **`Weight.m`/`Weight.I` stay required; `Lengths.l1`/`l2` get `0.0` defaults.** Zero mass or zero
  inertia is a division by zero; zero moment arms are a legitimate configuration (forces through the
  CoG). Today all four are required positional. D-1 covers making this stricter.
- **`Params.T` is deleted.** Dead since Step 14 — `thrust_body` reads the curve, never `p.T`. D-14.
- **Field names are shortened where the group already carries the prefix** (`aero_model` →
  `aero.model`, `wind_ref_ms` → `wind.ref_ms`, `parachute_S` → `recovery.S`,
  `thrust_misalign_deg` → `lengths.misalign_deg`). D-3 covers keeping the long names instead.

### Phase 3 files are in scope for the rename

`sim/dynamics3d.py:19` reads `p.m` and `sim/forces3d.py:47` reads `p.m_d`. They become
`p.weight.m` / `p.weight.m_d`. `tests/test_dynamics3d.py` has one `Params(...)` construction.
That is the whole Phase 3 surface — small, and **`docs/latex/research/3d_equations_of_motion.md`
is not touched**: when Step 30 resumes it simply reads the nested names. This is recorded here so
Step 30's implementer is not surprised.

---

## 28.4 `dataclasses.replace` under nesting — the dotted-path helper

Nesting breaks the single most-used idiom in the repo. `dataclasses.replace(p, gravity_model=gm)`
becomes `dataclasses.replace(p, gravity=dataclasses.replace(p.gravity, model=gm))` — verbose, and
wrong in a specific dangerous way: writing `dataclasses.replace(p, gravity=Gravity(model=gm))`
silently **resets every other field in that group to its default**. That is exactly the class of
silent-wrong-number bug this project's conventions exist to prevent.

Proposal: one helper in `sim/params.py`, used everywhere instead of `dataclasses.replace`.

```python
def replace(p: Params, changes: dict[str, Any]) -> Params:
    """`replace(p, {"gravity.model": "wgs84", "aero.S": 0.005})` — a nested
    dataclasses.replace that only ever rebuilds the groups it touches, so no
    untouched field can be reset to its default. Unknown paths raise
    TypeError from dataclasses.replace itself (no input validation, SS7)."""
```

Implementation shape: group the dotted keys by their first segment, `dataclasses.replace` each
affected group once with its own sub-changes, then `dataclasses.replace` the `Params` once with the
rebuilt groups. Single-segment keys (`"g0"`) pass straight through. Arbitrary depth is supported by
recursion, though only two levels exist.

Why this specific API:

- **`run.py`'s `sweep(base_params, field, values, s0)` takes the field as a string already**
  (`run.py:74-92`). A dotted path drops in with **no signature change at all**:
  `sweep(p, "gravity.model", ("constant", "radial", "wgs84"), s0)`. The printed table's column
  header becomes `gravity.model`, which is strictly more informative.
- A dict (not `**kwargs`) because Python identifiers cannot contain dots.
- It is the one place nested replacement logic lives, so the ~104 existing `replace` call sites
  become a mechanical rewrite with no per-site thinking.

Convenience sugar for the solver group, since ~60 test call sites pass solver settings (F6):

```python
def with_solver(p: Params, **kw) -> Params:   # with_solver(p, method="rk4", dt=1e-3)
    return dataclasses.replace(p, solver=dataclasses.replace(p.solver, **kw))
```

---

## 28.5 Aero rewrite — explicit three-way dispatch

### 28.5.1 The seam: one bundle, one dispatch dict

`sim/aero.py` gets a single public coefficient seam returning all five coefficients at once, plus a
module-private dispatch dict keyed on `p.aero.model` — the same shape as
`wind.py`'s `_MODELS`/`_TURBULENCE_MODELS` and `gravity.py`'s two dicts (§12).

```python
class AeroCoeffs(NamedTuple):
    C_x: float    # axial-force coefficient      (today's C_A)
    C_z: float    # normal-force coefficient     (today's C_N)
    C_m: float    # pitching-moment coefficient
    C_mq: float   # pitch-damping derivative
    l1: float     # CoP(D)-to-CoG(B) distance [m]

_AERO_MODELS = {
    "constant":   _constant_coeffs,
    "linearized": _linearized_coeffs,
    "table":      _table_coeffs,
}

def coefficients(t, y, p, flow) -> AeroCoeffs:
    base = _AERO_MODELS[p.aero.model](flow.alpha, flow.M, p)
    return control.aero_coeff_delta(t, y, p, flow, base)   # SS28.6; identity by default
```

The three model bodies, each populating all five fields:

| field | `"constant"` | `"linearized"` | `"table"` |
|---|---|---|---|
| `C_x` | `p.aero.C_x` | `p.aero.C_A0` | table `C_A` column |
| `C_z` | `p.aero.C_z` | `p.aero.C_N_alpha * sin(alpha)` | table `C_N` column |
| `C_m` | `p.aero.C_m` | `p.aero.C_m_alpha * sin(alpha)` | table `C_m` column |
| `C_mq` | `p.aero.c_mq` | `p.aero.c_mq` | table `c_mq` column, else `p.aero.c_mq` |
| `l1` | `p.lengths.l1` | `p.lengths.l1` | table `l1_m` column |

**The `sin(alpha)` smoothing is carried over verbatim** into `_linearized_coeffs` — same expression,
same operand order, same reason (`aero.py`'s module docstring, Phase 2.5 Step 35: it removes the
`atan2` branch-cut discontinuity that hangs the adaptive solver at apogee). That docstring block
moves with it, unedited. It is load-bearing and must not be "simplified".

**The table format, loader and interpolation are reused unchanged** — `_load_table`, `_bracket_M`,
`_table_lookup`, the rectangular-`(M, alpha)`-grid validation, the edge-clamp convention, and the
optional-`c_mq`-column fallback (Step 44's documented exception) all stay byte-identical. The only
change is *when* they are called: on `model == "table"` instead of on `p.aero_table` being a
non-empty string.

**`cop_l1`'s leak (F2) closes as a side effect.** `l1` now comes out of the same bundle as the
forces, so the table can no longer drive the moment arm while constants drive the force. This is a
behaviour change for the (currently unused, currently unreachable from any committed scenario)
combination "table configured + `aero_model='constant'`", and for `tests/test_aero.py`'s fixtures
that set only `aero_table` (F9) — those must now say `model="table"`, which is the point.

**`forces.py` loses both of its `if/elif/else` blocks:**

```python
def aero_force_body(t, s, p, hold=None):
    flow = flow_state(t, s, p, hold)
    c = aero.coefficients(t, s, p, flow)
    A_x = flow.q * p.aero.S * c.C_x
    A_z = flow.q * p.aero.S * c.C_z
    A_brake = flow.q * p.control.airbrake_Cd * p.control.airbrake_S_max \
            * control.airbrake_deploy_fraction(t, s, p, hold)
    return np.array([-(A_x + A_brake), -A_z])

def aero_moment_y(t, s, p, hold=None):
    flow = flow_state(t, s, p, hold)
    c = aero.coefficients(t, s, p, flow)
    A_m = flow.q * p.aero.S * p.aero.d_ref * c.C_m
    A_m += 0.25 * flow.air.rho * flow.V * p.aero.S * p.aero.d_ref**2 * s[OMEGA] * c.C_mq
    return -A_m
```

Two consequences to state out loud:

1. **`"linearized"` is bit-for-bit today's `"coefficients"`.** Same expressions, same multiplication
   order, same functions. The division-free pitch-damping form
   (`0.25·ρ·V·S·d_ref²·ω·C_mq`, never a literal `ω·d_ref/(2V)` intermediate) is preserved verbatim —
   it exists to avoid `0.0·inf = nan` at `V = 0`, which every unperturbed flight hits at apogee.
2. **An unknown model string now raises `KeyError`, not `ValueError`.** That is this project's
   established convention (§12, "Unknown strings raise KeyError at the first call — no input
   validation"), and it matches `gravity_model="linear"` after Step 34. Any test asserting
   `ValueError` on a bad `aero_model` changes accordingly.

### 28.5.2 The moment's reference length: reuse `d_ref` (recommended)

The user asked this to be resolved explicitly. Recommendation: **`q·S·d_ref·C_m` with the existing
shared `d_ref`**, for three reasons.

1. `models.tex` eq. `aero_magnitudes` already *is* `A_m = qSd_{ref}C_m` — making the constant model
   use a different length would put code and document in conflict for no gain.
2. `C_m` must mean the same thing across the three models or they are not comparable; a coefficient
   is only defined relative to its normalisation `(S, d_ref)`. One `(S, d_ref)` pair per airframe,
   three ways to supply the coefficients, is the correct factoring.
3. `d_ref` is already tied to the airframe elsewhere — the caliber static margin is
   `SM = l1/d_ref` (`models.tex:264-265`, `analysis.tex §Static stability`). A model-local second
   length would silently change the meaning of the static margin depending on which aero model is
   selected.

Same argument for the area: **one shared `S`**, not a per-model `A`. See D-4 for the naming fork the
user's `A` opens.

### 28.5.3 Pitch damping under `"constant"`

Today `"constant"` has no damping at all (`A_m = p.A_m`, full stop). Under the rewrite the damping
term needs only `ρ, V, S, d_ref, ω, C_mq` — all available in every model, since `q` is now computed
in every model. Recommendation: **the damping term applies identically in all three models**, with
`C_mq = p.aero.c_mq` in the `"constant"` and `"linearized"` cases and the table column (falling back
to `p.aero.c_mq`) in the `"table"` case.

Rationale: pitch damping is a property of the airframe, not of how you chose to supply the static
coefficients; and the alternative ("`constant` has no damping") would mean `c_mq` silently does
nothing under one model, which is exactly the kind of mode-dependent surprise this rewrite exists to
remove. `c_mq = 0.0` is the default, so the term is exactly `0.0` and no existing result moves. D-8.

### 28.5.4 What changes numerically, and where

This is the pass's **only deliberately non-bit-for-bit change** — the second in the project's
history, after Step 46. It is the requested fix, not a regression, but it must be recorded the same
way Step 46 was.

| site | today | after |
|---|---|---|
| every test with `A_x=A_z=A_m=0.0` | force exactly `0.0` | `q·S·0.0 = 0.0` — **bit-for-bit** |
| `tests/test_forces.py:57` (`A_x=1.23, A_z=2.0, A_m=0.5`) | constant Newtons | `q`-scaled; the closed form in the test must be re-derived through `q` (still closed-form, `flow_state` is deterministic) |
| `run.py` scenario (`A_x=0.5`) | 0.5 N drag for the whole flight | real drag; needs an `S`/`C_x` choice |
| `apps/.../select_conditions.py` (`A_x=0.5`) | same | same (F10) |
| `PROJECT-STATUS.md` Step-27 sweep tables | pinned | must be re-pinned (already known stale since Step 45) |

On `run.py`'s scenario: `A_x = 0.5 N` was never physical (0.5 N of drag on a 300 m/s flight). A
plausible replacement for the same small-model-rocket placeholder is `S = 0.005 m²`, `d_ref = 0.08 m`,
`C_x = 0.5` — the values `run.py:220-230`'s own atmosphere sweep already uses. At this scenario's
~55 kPa max-Q that is ~137 N of drag instead of 0.5 N, so **the committed scenario's apogee will
drop substantially** (the old ~4.6 km figure is a near-drag-free number). Expected, and the reason
Step 55 must re-pin every printed value it touches rather than claim a regression-free diff.

---

## 28.6 The control-coefficient seam (structure only)

Requirement: a controller must be *able* to override or perturb `C_x`/`C_z`/`C_m` (and, for an
airbrake, the CoP arm `l1`) as a function of vehicle state — without writing a controller now, and
without needing a second rewrite when one arrives.

**Where the hook lives: inside `aero.coefficients`, applied to the `AeroCoeffs` bundle.** One choke
point, after the base model, before any consumer. Everything downstream — the axial force, the
normal force, the static moment, the damping term, and `dynamics.py`'s CoP moment arm — then sees
one consistent, controlled coefficient set. Putting it in `forces.py` instead would require applying
it in three places (`aero_force_body`, `aero_moment_y`, and `dynamics.py`'s `l1`), which is how
F2-style leaks happen.

```python
# sim/control.py

def _no_aero_delta(t, y, p, flow, base: AeroCoeffs) -> AeroCoeffs:
    """Variant "none" (the default): returns `base` unchanged — the identity,
    bit-for-bit every prior step."""
    return base

_AERO_COEFF_CONTROLLERS = {"none": _no_aero_delta}

def aero_coeff_delta(t, y, p, flow, base: AeroCoeffs) -> AeroCoeffs:
    return _AERO_COEFF_CONTROLLERS[p.control.aero_coeff_model](t, y, p, flow, base)
```

How a future controller plugs in — the whole contract, so it needs nothing structural added:

- Write `_my_law(t, y, p, flow, base) -> AeroCoeffs`, returning
  `base._replace(C_x=base.C_x + dC_x, C_m=..., l1=...)`. A `NamedTuple._replace` makes "perturb two
  of five, pass the rest through" the default, cheapest thing to write — the opposite of the
  group-reset hazard in §28.4.
- Register it in `_AERO_COEFF_CONTROLLERS` under a new `p.control.aero_coeff_model` string.
- It receives `flow` (so `V`, `M`, `q`, `ρ`, `Re`, `α` are available without recomputing anything
  and without any re-entrancy into `aero`), the full state `y`, and `t`.
- With the §28.8 sampled-data mode, it also receives `hold` and may therefore be a *sampled*
  controller with memory (a PID). Without it, it is a pure memoryless function, exactly like the
  Step 49 airbrake.

**Step 49's existing separate airbrake drag term stays where it is**, as an independent additive
area (`A_brake` in `aero_force_body`). It is verified, it is bit-for-bit, and folding it into the
coefficient hook would mean expressing it as `ΔC_x = Cd_brake·S_max·f/S` — algebraically identical
but a division by `S`, which is `0.0` in most existing fixtures. Two routes with different physical
meanings (a bolted-on extra area vs. a change to the airframe's own coefficients) is the honest
model, not a duplication. D-9.

---

## 28.7 `Solver` group and `run_sim(p, s0)`

`run_sim`'s five keyword arguments (`t_max`, `method`, `rtol`, `atol`, `dt`) move onto
`Params.solver` with identical defaults, so a default `Params()` reproduces today's call exactly.

**Recommended signature: `run_sim(p, s0) -> Result`, with no solver kwargs at all.** The
alternative (keep them as optional overrides) looks cheaper — it avoids touching ~60 test call
sites (F6) — but it breaks a property Step 45 deliberately created: `Result.params` is supposed to
be *the* record of what produced the run. With overrides, a `Result` could carry `solver.method =
"RK45"` while having actually been integrated with `rk4`, and every downstream consumer
(`sim/report.py`'s printed/plotted/CSV output, a future reproducibility check) would be reading a
lie. Strict is better here. D-10.

Test migration is mechanical, and `with_solver` (§28.4) keeps it short:

```python
run_sim(p, s0, method="rk4", dt=1e-3)          # before
run_sim(params.with_solver(p, method="rk4", dt=1e-3), s0)   # after
```

---

## 28.8 Sampled-data / zero-order-hold integration mode

### 28.8.1 What problem this solves

Two backlog items are blocked on the same thing, and only on this thing:

- **B11** — state-coupled turbulence. The Dryden realization should be driven at the *instantaneous*
  true airspeed; `solve_ivp` evaluates the RHS at arbitrary, repeated and later-rejected times, so
  nothing that depends on "the current airspeed, once" can be expressed as a pure function of
  `(t, y, p)` without breaking the solver's own smoothness contract.
- **B12** — a real sampled-data airbrake loop. A flight computer computes at a fixed rate and holds
  its output between ticks; an integral or derivative term needs the previous sample. Same
  impossibility, same root cause.

Both were resolved at the time by deliberately shipping pure, memoryless, re-evaluated-fresh
approximations (Step 46's fixed `turbulence_ref_speed_ms`; Step 49's P-only airbrake). This step
builds the capability they were waiting on — **and nothing else**. No controller and no turbulence
change is written here.

### 28.8.2 Design

**Gate:** `p.solver.sample_rate_hz > 0.0`, the project's standard unset-sentinel convention
(`m_d is None`, `L_rail == 0.0`, `wind_model == "none"`). `0.0` is the default and the mode is then
*structurally* absent — not merely inert. Additionally `p.solver.method` must be `"rk4"`; an
adaptive method with a nonzero sample rate raises immediately, because adaptive stepping cannot
honour a hold boundary. This keeps `method` meaning "which integrator" and sampling an orthogonal
second dispatch, the same orthogonality `gravity_model` / `gravity_direction` already has
(§23.1). D-11.

**Driver:** `_run_rk4` is refactored (not copied) to take an optional sampler, so there is exactly
one event-detection implementation. Structure:

```
for each tick k:                       # period T_s = 1 / sample_rate_hz
    hold = sampling.sample(t_k, y_k, p, prev=hold)   # evaluate every channel ONCE
    for each of n_sub = T_s/dt fixed RK4 substeps:
        y <- RK4(derivatives, t, y, p, hold)          # hold constant across all 4 stages
        ... existing apogee/ground/burnout/rail/parachute crossing detection, unchanged ...
```

Three properties worth stating, because they are the technical argument for this shape:

1. **The hold is constant across all four RK4 stages of every substep**, so inside a tick the RHS is
   again a smooth function of `(t, y)` and RK4's order is preserved. Every discontinuity lands
   exactly on a step boundary, never inside a step. That is what makes this a correct ZOH rather
   than an approximation of one.
2. **The sample is taken at the tick's start, `(t_k, y_k)`** — the causally correct flight-computer
   model: measure, compute, apply until the next tick.
3. **`T_s` must be an exact integer multiple of `dt`.** Computed as `n_sub = T_s/dt` and checked;
   a non-integer ratio raises rather than silently rounding, because silently rounding changes the
   effective sample rate from the one the user configured.

**The hold itself** — new module `sim/sampling.py` (it owns a dispatch-style channel registry, which
is a model-selection concern, not a numerics one; `integrate.py` stays about numerics):

```python
class Hold(NamedTuple):
    t_sample: float            # the tick these values were computed at
    values: dict[str, Any]     # channel name -> held value (float, tuple, or array)

# channel signature: f(t, y, p, prev) -> Any
#   `prev` is this channel's own value from the previous tick, or None at t=0.
_CHANNELS = {"airbrake": control.sample_airbrake}

def sample(t, y, p, prev: Hold | None) -> Hold: ...
```

`prev` is the single most important detail here and the reason this does not need a second rewrite:
it is what makes a channel *recursive*. A PID's integral accumulator, a rate limiter's previous
command, and a Dryden filter's internal state are all `f(t_k, y_k, p, prev)`. The value type is
deliberately `Any`, not `float`, so a channel can hold a tuple or an array of filter states.

**Consumption** — one branch, in the module that owns the quantity, never in `forces.py`:

```python
def airbrake_deploy_fraction(t, y, p, hold=None) -> float:
    if hold is not None and "airbrake" in hold.values:
        return hold.values["airbrake"]          # zero-order hold
    return _AIRBRAKE_CONTROLLERS[p.control.airbrake_model](t, y, p)
```

**Plumbing.** `hold` is threaded as an optional, default-`None` keyword through the RHS chain:

| function | change |
|---|---|
| `dynamics.derivatives(t, y, p)` | `(t, y, p, hold=None)` |
| `forces.aero_force_body` / `aero_moment_y` / `parachute_drag_inertial` / `thrust_body` | `hold=None` |
| `aero.coefficients` | `hold=None` (passes it to the control hook) |
| `control.airbrake_deploy_fraction` / `aero_coeff_delta` | `hold=None` |
| `flow.flow_state` | `hold=None` |
| `wind.wind_inertial` | `hold=None` (accepted and ignored for now — B11's landing site) |

`hold=None` everywhere is today's code path *exactly*: every existing call site stays valid
unedited, and the default `solve_ivp` path never constructs a `Hold` at all. Threading the full
chain now (including `flow`/`wind`, which ignore it) is deliberate: it is what lets B11 and B12 be
written as single-module changes later instead of re-opening the plumbing. This is the same
"ship the seam before the consumer" pattern as Step 44's `c_mq` scaffold and Step 49's controller
dict. D-17 offers the narrower control-only alternative.

### 28.8.3 What this does and does not unblock

**Unblocks:**
- **B12** — a fixed-rate PID airbrake becomes writable as one `control.py` channel plus
  `Params.control` gains `ki`/`kd`/anti-windup fields. No integrator change needed at that point.
- **B11** — a turbulence realization evaluated once per tick at the true instantaneous airspeed, with
  its filter state carried in `prev`, becomes writable as one `wind.py` change.

**Does not unblock / explicitly out of scope:**
- The PID law and the state-coupled turbulence model themselves. Still separate future steps, each
  with its own design questions (anti-windup, actuator rate limits; the Dryden filter's
  discretisation and whether a white-noise draw per tick turns this into a stochastic ODE whose
  results are sample-rate-dependent).
- Adaptive error control in sampled mode. The sampled path inherits `_run_rk4`'s documented
  limitations in full: no step-size control, events located to ~`dt`.
- `solve_ivp`/RK45 sampled-data support. Not attempted; an adaptive solver with hold boundaries
  needs a halt-and-restart-per-tick driver, which is a different and much larger design (and listed
  as rejected in §28.14).
- Any change to a default run. `sample_rate_hz = 0.0` keeps both existing paths bit-for-bit.

**Cost, to be measured not assumed.** A 60 s flight at `dt = 1e-3` is 60 000 steps × 4 stages =
240 000 RHS evaluations, against RK45's low thousands. With a sounding/field-tier atmosphere each
evaluation is an interpolation over a real profile. Step 59 must report the measured wall-clock
factor; Step 56 (one `flow_state` per RHS call) cuts it by roughly 3× and is therefore worth landing
first even though it is formally independent.

---

## 28.9 `run.py` → `sim/report.py`

New module `sim/report.py` (inside `sim/`, per the user's instruction — this is core reporting, not
a consumer app). It receives, from `run.py`:

| moved from `run.py` | lands as |
|---|---|
| `_flight_summary(result, p)` | `report.flight_summary(result, p) -> dict` (public; `tests/test_plotting.py:22` imports it today) |
| `sweep(base_params, field, values, s0)` | `report.sweep(base_params, path, values, s0)` — now a dotted path (§28.4), same signature |
| `_print_sweep_table(title, field, results)` | `report.print_sweep_table(...)` |
| the single-run printed summary (`run.py:129-163`) | `report.print_run_summary(result, p)` |
| plot building + `savefig` + the CSV dump (`run.py:165-188`) | `report.save_run_artifacts(result, p, out_dir)` |
| the overlay-plot + savefig blocks (`run.py:205-240`) | `report.save_sweep_artifacts(name, sweep_results, out_dir, title)` |
| `_OUTPUT_DIR` | `report.DEFAULT_OUTPUT_DIR` |

`sim/plotting.py` is unchanged — it stays the pure figure-builder layer; `report.py` is the
orchestration layer above it (build → print → save).

Target `run.py` in full, after Step 58 — scenario definition and nothing else:

```python
def main() -> None:
    params = Params(
        weight=Weight(m=0.5, I=0.05),
        lengths=Lengths(l1=0.3, l2=0.4),
        thrust=Thrust(motor_curve="placeholder.csv"),
        aero=Aero(model="constant", S=0.005, d_ref=0.08, C_x=0.5),
    )
    state0 = State(x=0.0, z=0.0, vx=0.0, vz=0.0, theta=math.pi / 2, omega=0.0)

    result = run_sim(params, state0)
    report.print_run_summary(result, params)
    report.save_run_artifacts(result, params)

    report.run_sweep(params, "gravity.model", ("constant", "radial", "wgs84"), state0,
                     title="Gravity model comparison")
    report.run_sweep(params.replace({"soundings.case": "example", "site.h0_m": 380.0}),
                     "atmosphere.model", ("isa", "sounding"), state0,
                     title="Atmosphere model comparison (station LKPR)")
```

Two sub-decisions inside this (D-13):

- **The sweep *definitions* stay in `run.py`** (which field, which values — that is scenario
  configuration), while the machinery moves. `report.run_sweep` is the one convenience wrapper that
  does sweep → print table → overlay plot → savefig, so each sweep is one call.
- **`plt.show()` is dropped**, not moved. It is what hung two background runs during Step 45's
  verification (`PROJECT-STATUS.md`, "Recovery note"), and every figure is already saved to
  `output/`. If interactive display is wanted it belongs behind an explicit flag, not at the end of
  `main()`.
- The atmosphere sweep no longer needs `aero_model="coefficients"`: after §28.5 every aero model is
  atmosphere-coupled (F3), so the base scenario is already sufficient. One fewer piece of
  scaffolding.

---

## 28.10 LaTeX rewrite plan

Standing on this project's established division (`PROJECT-STATUS.md`): the architect does
**structural and notational** doc passes; genuinely new physics goes through the user. This pass is
notational — "coefficient × dynamic pressure × reference area" is already the document's convention
(`models.tex` eq. `aero_magnitudes`), and the constant model never had document standing at all
(F11), so nothing new is being derived. Below is the plan only; the prose is written in Step 54,
after approval.

Also standing: **no LaTeX toolchain in this environment.** The pass will be checked statically
(brace/environment balance, every `\autoref` target defined, no dangling or duplicate labels) and
must be compiled locally before being treated as final — the same caveat as every prior doc pass.

### Edits, by file and location

**`sections-ai/models.tex` — the bulk of the work.**

1. **`§Aerodynamics > Force magnitudes` (lines 251-266).** Keep the three equations, restate them
   once as model-independent definitions: `A_x = qSC_x`, `A_z = qSC_z`, `A_m = qSd_{ref}C_m`, with
   one `(S, d_ref)` pair per airframe shared by all three models (§28.5.2). Add the notation bridge
   sentence (`C_x ≡ C_A`, `C_z ≡ C_N`) in the same style the document already uses at line 319 for
   `c_z ≡ C_N` — or, under D-6 option (b), unify the notation outright and delete the bridge.
2. **`§Aerodynamics > Coefficients` (lines 275-308) — the structural change.** Today this is one
   paragraph: "read from a database … lacking such a table, a constant/linear fallback is used
   instead". Rewrite as **three explicitly named, selectable models**, matching the shape
   `§Gravity` (magnitude × direction), `§Atmosphere` (three tiers) and `§Wind` (three tiers) already
   have — this is the inconsistency the section currently has against the rest of the chapter:
   - *Constant:* `C_x, C_z, C_m` fixed numbers, α- and M-independent. The cheapest model, for
     first-cut sizing and for isolating one effect in a comparison sweep. State explicitly that it
     is still dynamic-pressure-scaled, i.e. it is a real (if crude) aerodynamic model and no longer
     a raw-force placeholder.
   - *Linearized:* `C_x = C_{A0}`, `C_z = C_{N\alpha}\sin\alpha`, `C_m = C_{m\alpha}\sin\alpha`,
     `l_1 = l_1^{(0)}`. **Existing text at lines 283-294 preserved essentially verbatim**, including
     the whole `\sin\alpha` robustness paragraph — that paragraph documents a load-bearing fix.
   - *Table:* the `(M,\alpha)` rectangular grid with bracket-and-clamp in `M`, linear in `\alpha`,
     then blend — **existing text at lines 278-281 preserved verbatim**, promoted to its own named
     model instead of being "the database" with the others as its fallback.
3. **`§Aerodynamics > Coefficients`, new short paragraph: pitch damping across models.** State that
   `c_{m,q}` applies in all three models, that the table's optional column overrides the constant
   when present, and cross-reference `analysis.tex §Dynamic stability` (which already owns the sign
   convention: positive `c_{m,q}` is damping *here*, the documented flip from the textbook sign).
4. **`§Aerodynamics > Coefficients`, the `\todo` at lines 306-308.** It currently lists
   "control-surface extension not covered above (airbrake, aileron, etc.)" as missing. After Step 57
   the *structural* seam exists (a control law may perturb `C_x, C_z, C_m, l_1` directly), while the
   laws themselves do not. Narrow the `\todo` to say exactly that, rather than leaving it claiming
   nothing exists.
5. **`§Aerodynamics > Linearization of coefficients` (lines 310-330).** Its whole purpose is
   bridging `c_z ≡ C_N`, `c_m ≡ C_m`; under D-6 option (b) the bridge collapses and this subsection
   shortens to the linearisation itself. Under option (a) it is updated to bridge three names
   instead of two. The `c_x = c_{x,0} + c_z^2/(e\pi\lambda)` drag-polar `\todo` at 321-330 is
   untouched either way (it is a user `\todo`, not notation).

**`sections-ai/rocket-2d.tex`.**

6. **`§Forces and moments`, lines 63-72.** `A_x, A_z` are described as "the drag and lift
   magnitudes, defined in the body frame". Add the half-sentence that they are *always*
   `q`-scaled coefficient products (`\autoref{sec:aero}`) — there is no raw-force model. Minimal
   edit; the vector equations themselves do not change.

**`main.tex`.**

7. **`§Current assumptions`, the "Constant moment arms" bullet (88-93)** mentions the coefficient
   table as *the* source of `(\alpha,M)` dependence. Reword to "the selected aerodynamic model
   (\autoref{sec:aero})", since two of the three models have no `(\alpha,M)` dependence at all and
   the bullet's claim about `l_1` responding to `(\alpha,M)` is true only under the table model.
8. **`§Current assumptions`, the launch-rail/recovery/airbrake bullet (101-111)** ends "the control
   law is a continuous, memoryless proportional law, not a sampled-data controller with memory".
   After Step 59 this needs splitting: the *shipped law* is still proportional and memoryless; the
   *solver* now offers an opt-in fixed-rate zero-order-hold mode in which a law with memory is
   expressible. State which is which.
9. **`§Backlog and future work`, the sampled-data bullet (189-193).** Its "*Waiting on:* a different
   integration strategy than this document's solver assumes" becomes "available, opt-in" — the item
   downgrades from blocked to unwritten.
10. **`§Backlog`, the wing-body bullet (144-160)**, which already says "an air brake enters as a
    switchable change to `C_A` and to the CoP" (F12): add that this seam now exists structurally
    (Step 57) and what is still missing is the airframe and the law, not the plumbing.

**`sections-ai/analysis.tex`.** No edit required under D-6 option (a) — it already writes the
linearised coefficients lowercase (`c_{z,\alpha}`, `c_{m,\alpha}`, `c_{m,q}`), consistent with
`C_z`/`C_m`. Under option (b) (unify on `C_x, C_z, C_m` everywhere) it needs a notation sweep, which
would *reduce* the document's total symbol count — the `C_A`/`C_N` vs `c_z`/`c_x` duality disappears.
Check `§Static stability`'s `SM = l_1/d_{ref}` is unaffected either way: it is (no renaming of
`d_ref` is proposed).

**Not in scope for the LaTeX pass:** anything about `Params` structure, `sim/report.py`, or solver
internals beyond backlog bullet 9 — the physics document does not describe the code's object model,
and should not start.

---

## 28.11 Implementation steps 50-59

Numbering continues the project's actual convention: Phase 2.x refactor/extension passes take the
next free numbers in the 33+ sequence (last used: Step 49, Phase 2.10), while Phase 3 keeps its own
reserved 28-32 block. Label: **Phase 2.11 — rewrite pass**. Ten steps, one commit each, each
independently testable, per the standing one-step-one-commit discipline.

Standing gates for every step below (this project's existing practice, restated so no ticket omits
them): full `pytest` suite green and independently re-run by the orchestrator; bit-for-bit claims
proved by **execution** (`git stash` the change, re-run, byte-compare `output/trajectory.csv` and the
printed summary), not by reading the diff — the Step 45 method.

---

### [S50] `Params` composition, part 1 — groups + `sim/` migration
- **Module/boundaries:** `sim/params.py` (rewrite), and read-site updates in `sim/aero.py`,
  `atmosphere.py`, `control.py`, `dynamics.py`, `dynamics3d.py`, `flow.py`, `forces.py`,
  `forces3d.py`, `gravity.py`, `integrate.py`, `rotation.py`, `soundings.py`, `thrust_curve.py`,
  `wind.py`, `plotting.py`
- **Assignee:** developer
- **depends_on:** []
- **parallel_safe:** false (touches every module)

Add the twelve group dataclasses of §28.3, the composed `Params`, `params.replace(p, {...})` and
`params.with_solver(...)` (§28.4). Migrate every read inside `sim/` to the nested names. Keep a
**transitional** flat layer so nothing outside `sim/` breaks yet: `Params.flat(**old_kwargs)`
(a classmethod routing the old flat names into groups) plus read-only `@property` aliases for every
old flat name. `tests/`, `run.py` and `apps/` are touched only by a mechanical `Params(` →
`Params.flat(` substitution. Bit-for-bit: byte-identical `output/trajectory.csv`.

*Spec slice:* §28.3 (full field table), §28.4.

### [S51] `Params` composition, part 2 — tests, `run.py`, `apps/` migrated to the native API
- **Module/boundaries:** `tests/*.py`, `run.py`, `apps/cfd_conditions/select_conditions.py`
- **Assignee:** developer
- **depends_on:** [S50]
- **parallel_safe:** false

Rewrite all 164 `Params.flat(...)` constructions as nested constructions, and all ~104
`dataclasses.replace(p, field=...)` calls as `params.replace(p, {"group.field": ...})`. No `sim/`
file is touched. Suite green, `trajectory.csv` byte-identical.

*Spec slice:* §28.3, §28.4. Mechanical; the old→new field-name map in §28.3 is the whole ticket.

### [S52] `Params` composition, part 3 — delete the transitional shim
- **Module/boundaries:** `sim/params.py`
- **Assignee:** developer
- **depends_on:** [S51]
- **parallel_safe:** false

Remove `Params.flat` and every flat `@property` alias. Any remaining old-name reader now fails
loudly. Suite green, `trajectory.csv` byte-identical.

### [S53] `Solver` group: integration controls onto `Params`, `run_sim(p, s0)`
- **Module/boundaries:** `sim/integrate.py`, `sim/params.py` (`Solver` already added at S50),
  `tests/*` (~60 `run_sim` call sites), `run.py`, `apps/`
- **Assignee:** developer
- **depends_on:** [S52]
- **parallel_safe:** false

Delete `run_sim`'s five kwargs; read `p.solver.*` instead (§28.7). Defaults unchanged, so a default
`Params` reproduces today's call exactly — `trajectory.csv` byte-identical.

### [S54] LaTeX/notation pass: three aero models, `C_x/C_z/C_m`, shared `S`/`d_ref`
- **Module/boundaries:** `docs/latex/main.tex`, `docs/latex/sections-ai/{models,rocket-2d,analysis}.tex`
- **Assignee:** architect (doc pass, per this project's division of labour)
- **depends_on:** [] (independent of all code steps; must land **before** S55)
- **parallel_safe:** true (no code file touched)

Execute §28.10 items 1-7 and 10 (items 8-9 wait for S59 — see S60 note below). Doc-only, no code.
**Rationale for ordering:** working rule 1 makes the LaTeX the source of truth, and Step 46 was
blocked precisely because `models.tex` contradicted the spec the developer was about to implement.
Landing the notation first means S55's implementer has a document to match instead of contradict —
the same order Phase 2.6 used (doc commit `17da67b` before Steps 38-40).

### [S55] Aero three-way dispatch — `AeroCoeffs`, `aero.coefficients`, `forces.py` simplification
- **Module/boundaries:** `sim/aero.py`, `sim/forces.py`, `sim/dynamics.py` (the `cop_l1` call site),
  `tests/test_aero.py`, `tests/test_forces.py`, `tests/test_dynamics.py`, `run.py`, `apps/`
- **Assignee:** developer
- **depends_on:** [S52, S54]
- **parallel_safe:** false

Implement §28.5. **This is the pass's one deliberately non-bit-for-bit step** — §28.5.4's table is
the complete list of what moves and must be re-pinned (one test's closed form, `run.py`'s scenario,
`apps/`'s scenario, `PROJECT-STATUS.md`'s Step-27 tables). Everything with zero coefficients stays
bit-for-bit and must be *shown* to. Also update `architecture.md` §12's now-false "`constant`
ignores the atmosphere entirely" sentence (F3).

*Spec slice:* §28.5 in full.

### [S56] One `flow_state` per RHS call
- **Module/boundaries:** `sim/dynamics.py`, `sim/forces.py`, `sim/aero.py`
- **Assignee:** developer
- **depends_on:** [S55]
- **parallel_safe:** false

Compute `flow_state` once in `derivatives` and pass it down, instead of three independent
computations per RHS call (F8). Pure plumbing, bit-for-bit (deterministic pure function, same
operands), ~3× fewer atmosphere/wind evaluations per step — which matters directly for S59's cost.
Separable from S55 on purpose: S55 changes numbers, S56 must not, and mixing them would make the
bit-for-bit check unprovable.

### [S57] Control-coefficient seam (structure only, identity by default)
- **Module/boundaries:** `sim/control.py`, `sim/aero.py`, `sim/params.py` (`Control.aero_coeff_model`),
  `tests/test_control.py`, `tests/test_aero.py`
- **Assignee:** developer
- **depends_on:** [S56]
- **parallel_safe:** false

Implement §28.6: `aero_coeff_delta` + `_AERO_COEFF_CONTROLLERS` with only the `"none"` identity
variant. **No controller is written.** Tests: the default is bit-for-bit (`is`-identity of the
returned bundle is a legitimate check here, since the identity variant returns `base` itself); and a
locally-registered dummy variant in the test proves a delta actually reaches the axial force, the
normal force, the moment *and* `dynamics.py`'s CoP arm — the four consumers the single choke point
exists to keep consistent.

### [S58] `run.py` → `sim/report.py`
- **Module/boundaries:** new `sim/report.py`, `run.py`, `tests/test_plotting.py` (its `from run
  import` line), possibly a new `tests/test_report.py`
- **Assignee:** developer
- **depends_on:** [S53]  (independent of S55-S57, but see note)
- **parallel_safe:** false against S55 (both edit `run.py`'s scenario)

Move the summary/print/plot/CSV/sweep machinery per §28.9; `run.py` ends at the shape shown there.
Printed output byte-identical to before the move, apart from the sweep tables' column header
(`gravity_model` → `gravity.model`) and the dropped `plt.show()`.

### [S59] Sampled-data / zero-order-hold integration mode
- **Module/boundaries:** new `sim/sampling.py`, `sim/integrate.py`, `sim/dynamics.py`,
  `sim/forces.py`, `sim/aero.py`, `sim/control.py`, `sim/flow.py`, `sim/wind.py`,
  `sim/params.py` (`Solver.sample_rate_hz`), new `tests/test_sampling.py`, `tests/test_integrate.py`
- **Assignee:** developer
- **depends_on:** [S53, S57]
- **parallel_safe:** false

Implement §28.8. Gated off by default. Tests: `sample_rate_hz = 0.0` is bit-for-bit on both existing
paths; a non-integer `T_s/dt` raises; `method="RK45"` with a nonzero rate raises; with a real
airbrake gain and `sample_rate_hz = 10`, the deploy fraction is **piecewise constant** across each
tick and differs measurably from the continuously-evaluated run; the held value at a tick equals the
live controller evaluated at that tick's own `(t_k, y_k)`; `prev` is threaded (a test channel that
counts its own invocations sees exactly one call per tick, not one per RK4 stage — this is the single
most important assertion in the step). Report the measured wall-clock factor against RK45.

**This is the largest and riskiest step in the pass and must be its own commit** (as the orchestrator
expected). It can land before or after S55-S57 as far as physics goes — its only hard prerequisite
is S53 (the `Solver` group must exist to hold `sample_rate_hz`) and, for the hook argument to exist,
S57. If schedule pressure makes it attractive to split: S59a = the `hold` plumbing (optional
argument threaded everywhere, always `None`, provably inert) and S59b = the driver plus the first
channel. Recommended as one step, since S59a alone has almost nothing to assert.

### [S60] Tracker and LaTeX close-out
- **Module/boundaries:** `docs/PROJECT-STATUS.md`, `docs/roadmap.md`, `docs/latex/main.tex`
  (§28.10 items 8-9 only)
- **Assignee:** architect
- **depends_on:** [S59]
- **parallel_safe:** false

Record Phase 2.11; re-pin the Step-27 sweep tables; move B11/B12 from "blocked on integration
strategy" to "unblocked, law not yet written"; apply the two `main.tex` backlog/assumption edits that
could only be written truthfully once S59 exists.

### Dependency summary

```
S50 → S51 → S52 → S53 → S58
                   │
S54 ─────────────► S55 → S56 → S57 → S59 → S60
  (doc, parallel)                      ↑
                                      S53
```

Only **S54** is genuinely parallel-safe against anything (it touches no code file). Everything else
forms a chain, because `Params` is upstream of every module and the aero/report/solver work all land
on overlapping files. That is a consequence of the user's chosen nested-composition design, not an
accident of this plan.

---

## 28.12 Decision points for the user

Seventeen genuine forks. Each has a recommendation; none is being taken silently.

| # | question | options | recommendation |
|---|---|---|---|
| **D-1** | Grouping of the ~35 fields the user did not name | (a) §28.3 as proposed: `Gravity`, `Site` (site + rail), `Atmosphere`, `Soundings` (shared), `Wind`, `Recovery`, `Control`, `g0` top-level; (b) same but `Rail` split out of `Site`, and `g0` inside `Gravity`; (c) fewer, coarser groups: one `Environment` (gravity + atmosphere + wind + soundings) and one `Vehicle` | **(a)** — one group per dispatch-owning module, so "where does this field go" has a mechanical answer; (c) recreates the flat-file problem one level down |
| **D-2** | `Params` migration strategy | (a) one big commit, no shim; (b) three commits with a transitional `Params.flat` + read-only flat properties (S50/S51/S52); (c) keep flat aliases permanently | **(b)** — separates the physics-adjacent `sim/` change from 6.8k lines of test churn, each commit independently green; costs one throwaway shim |
| **D-3** | Field names inside groups | (a) shorten where the group carries the prefix (`aero.model`, `wind.ref_ms`, `recovery.S`); (b) keep verbatim (`aero.aero_model`, `wind.wind_ref_ms`) | **(a)** — the call sites are being rewritten anyway; (b) buys a slightly smaller diff at the cost of permanent stutter |
| **D-4** | Reference-area symbol for the constant model | (a) one shared `Aero.S` for all three models; (b) a new `Aero.A` as the user named it, alongside `S`; (c) rename the reference area to `A` everywhere in code *and* LaTeX | **(a)** — `A` collides with the nose-tip point `A` (`rocket-2d.tex §Geometry`), with `A_x/A_z/A_m`, and with `\vec{A}_f`; the report-finalization pass already removed exactly this collision by renaming `A,l` → `S,d_ref` (F13). (b) additionally gives one group two reference areas |
| **D-5** | Moment reference length for the constant model | (a) reuse the shared `d_ref`; (b) a model-local length | **(a)** — §28.5.2: `C_m` is only defined relative to `(S, d_ref)`, and `SM = l1/d_ref` would otherwise change meaning with the model selection |
| **D-6** | Coefficient notation | (a) `C_x/C_z/C_m` as the bundle's output names + a one-line bridge `C_x ≡ C_A`, `C_z ≡ C_N`; CSV columns and the linearized slope names unchanged; (b) unify on `C_x/C_z/C_m` everywhere — code, LaTeX, and the aero CSV column headers | **(a)** for this pass — the user asked to reuse the table format as-is, and the document already carries a bridge of exactly this kind at `models.tex:319`. (b) is cleaner long-term and *reduces* total symbols, but renames committed data files and is better as its own later step |
| **D-7** | Aero seam shape | (a) one `AeroCoeffs` bundle + one dispatch dict; (b) five per-coefficient dispatch dicts, keeping today's five public functions | **(a)** — one lookup, one choke point for the control hook, closes F2's `cop_l1` leak by construction, and halves the per-RHS lookups. Thin `C_x/C_z/...` wrappers can be kept for the existing unit tests if wanted |
| **D-8** | Pitch damping under `"constant"` | (a) same damping term in all three models; (b) no damping under `"constant"` | **(a)** — damping is an airframe property, not a function of how the static coefficients were supplied; `c_mq = 0.0` default keeps it inert |
| **D-9** | Step 49's airbrake vs. the new coefficient hook | (a) keep the separate additive area term, hook is a second independent route; (b) re-express the airbrake as `ΔC_x` and delete the area term | **(a)** — (b) requires dividing by `S`, which is `0.0` in most existing fixtures, and would regress a verified step for no physical gain |
| **D-10** | `run_sim` signature | (a) strict `run_sim(p, s0)`; (b) keep `method`/`dt`/`t_max`/`rtol`/`atol` as optional overrides | **(a)** — (b) lets `Result.params` disagree with how the run was actually integrated, breaking the property Step 45 added `Result.params` to create |
| **D-11** | Sampled-mode gate | (a) `solver.sample_rate_hz > 0.0`, requiring `method="rk4"` (raise otherwise); (b) a third method string `"rk4_sampled"`; (c) both | **(a)** — keeps `method` meaning "which integrator" and sampling an orthogonal second dispatch, the `gravity_model`/`gravity_direction` precedent |
| **D-12** | How the held values reach the RHS | (a) optional `hold=None` keyword threaded through the RHS chain; (b) extend the state vector with hold/filter components (`d/dt = 0`, jumps at ticks); (c) a module-level/contextvar "current hold" | **(a)** — (b) is the textbook sampled-data formulation but makes the state dimension configuration-dependent, rippling into `state.py` indices, `Result.y` shape, plotting, every pinned test and the 3D state; (c) is hidden global state, against this codebase's purity style and unsafe for parallel sweeps |
| **D-13** | `run.py` / `report.py` split details | (a) sweep *definitions* stay in `run.py`, machinery in `report.py`, `plt.show()` dropped; (b) `report.py` owns a default sweep set and `run.py` calls one function; (c) keep `plt.show()` behind a flag | **(a)** — which models to compare is scenario configuration; and `plt.show()` is what hung two runs during Step 45's verification |
| **D-14** | Dead/renamed fields | delete `Params.T` (inert since Step 14); rename `g` → `g0`; rename `thrust_misalign_deg` → `lengths.misalign_deg`; rename `parachute_model` → `recovery.model` | **do all four** — all are already-true names; `T` in particular is a trap (settable, read by nothing) |
| **D-15** | `apps/cfd_conditions/select_conditions.py` is untracked (F10) | (a) user commits it before S51 so it migrates with everything else; (b) leave it untracked and fix it in the same commit anyway; (c) let it break and fix later | **(a)** — an untracked consumer of `sim/` cannot be regression-checked and will silently rot; committing it first is one command and makes S51/S55 able to state honestly that every consumer was migrated |
| **D-16** | Who writes the LaTeX prose, and marking | architect writes it (the Step 33/38-40/report-finalization precedent), AI-authored text marked per the existing `\ai{}` convention where that convention is in force | **architect writes it**, as a doc-only commit (S54) landing before the aero code change |
| **D-17** | How far to thread `hold` in S59 | (a) the full chain now, including `flow`/`wind` which ignore it; (b) control-only now, extend when B11 is picked up | **(a)** — the user's explicit ask was that this not need a second rewrite; (b) guarantees re-opening the plumbing for B11 |

---

## 28.13 Risks

- **R1 — the aero rewrite is not bit-for-bit, by design.** Only the second such step in the
  project's history (after Step 46). Blast radius measured at three call sites plus one test's
  closed form (F4, §28.5.4) — small, but every pinned number it touches must be re-derived and
  re-recorded, including `PROJECT-STATUS.md`'s Step-27 sweep tables (already known stale since
  Step 45, and this is the moment to fix them).
- **R2 — S50/S51 are the largest diff in the project's history.** ~20 `sim/` files, 164 `Params`
  constructions, ~104 `replace` calls across 6831 test lines. Mitigations: the three-commit shim
  plan (D-2), the dotted-path helper so nested replacement is written once (§28.4), and the fact
  that every miss is a loud `TypeError`/`AttributeError`, never a silent wrong number.
- **R3 — nested `dataclasses.replace` has a silent-wrong-number mode.**
  `replace(p, aero=Aero(model="table"))` resets every other `Aero` field to its default. The helper
  exists specifically to make that unwritable; the review gate for S50-S52 should include "no bare
  `dataclasses.replace` on a group remains outside `sim/params.py`".
- **R4 — `"constant"` becomes atmosphere-coupled** (F3), invalidating one sentence of
  `architecture.md` §12 and changing what `run.py`'s gravity sweep is actually isolating (gravity
  only before, gravity-with-real-drag after). Called out rather than discovered later.
- **R5 — sampled mode's cost.** 240 000 RHS evaluations for a 60 s flight at `dt=1e-3`, against
  RK45's low thousands. S56 cuts ~3× of it; the rest is inherent to fixed-step integration. S59
  must measure and report, not assume.
- **R6 — S59's sampled results are not comparable to RK45 results** by construction (a ZOH control
  loop is a different dynamical system from a continuously-evaluated one, not a more accurate
  solution of the same one). Needs stating in the step's own docstring so a future reader does not
  "fix" the discrepancy.
- **R7 — Phase 3 collateral.** `dynamics3d.py`, `forces3d.py` and `tests/test_dynamics3d.py` are in
  S50/S51's scope (small: `p.m`, `p.m_d`, one fixture). `docs/latex/research/3d_equations_of_motion.md`
  is **not touched**; Step 30 resumes against the nested names.
- **R8 — no LaTeX toolchain here.** S54 is structurally checkable only (labels/`\autoref`
  targets/brace balance). Must be compiled locally before being treated as final — the standing
  caveat on every doc pass this project has had.
- **R9 — `tests/test_aero.py`'s fixtures change meaning, not just spelling** (F9): a fixture that
  sets only `aero_table` is today a table-driven test and becomes a *constant*-model test unless
  `model="table"` is added. A mechanical find-and-replace that misses this would leave tests passing
  while testing nothing. S55's review must check each one individually.

---

## 28.14 Rejected options

- **Flat-but-grouped `Params` (comment-separated blocks, no nesting).** The user explicitly chose
  nested composition over this, aware of the call-site cost. Not re-litigated.
- **A fourth `"force"` aero model preserving today's raw `A_x/A_z/A_m`.** Would keep every existing
  number bit-for-bit, including `run.py`'s. Rejected: the user's instruction is that the coefficients
  "replace `A_x`/`A_z`/`A_m` entirely", F4 shows the compatibility value is nearly zero (one test),
  and keeping a dimensionally-wrong model as a selectable option preserves exactly the defect being
  fixed.
- **Keeping two aero selectors (`aero_model` and `aero_table`).** The whole point of the step is
  that one model family gets one selector (§12). `aero.table` remains a *field* of the group, read
  only by the `"table"` variant — a parameter, not a selector.
- **Per-coefficient dispatch dicts** (D-7 option b) — five dicts, five lookups per RHS call, and the
  control hook would need applying in five places or in each consumer.
- **State-vector-extension ZOH** (D-12 option b). The textbook formulation, and genuinely better in
  one respect (the held values ride the dense interpolant). Rejected for this project because a
  configuration-dependent state dimension ripples into `state.py`'s index constants, `Result.y`'s
  shape, `plotting.py`, the 3D state, and every pinned-shape test — a far larger change than the
  capability warrants.
- **A contextvar/global "current hold"** (D-12 option c). Zero plumbing, hidden state, unsafe under
  parallel sweeps, and against the `f(t, y, p)`-purity this codebase has maintained since Step 4.
- **Halt-and-restart `solve_ivp` at every sample tick.** Keeps adaptive error control inside each
  tick, which is attractive. Rejected for now: event bookkeeping across thousands of restarted
  segments, dense-output stitching, and the per-call setup cost make it a materially bigger design
  than the fixed-step driver that already exists and only needs a sampler bolted onto it. Worth
  revisiting only if fixed-step cost (R5) proves unacceptable.
- **An outer two-pass iteration** (run once, freeze an airspeed profile, re-run — the other B11
  option named in `roadmap.md`). Does nothing for B12, and makes the result depend on a
  convergence criterion nobody has specified.
- **Writing the PID controller / state-coupled turbulence in this pass.** Explicitly out of scope
  per the orchestrator's instruction; S59 ships the capability, not the consumers.
- **Putting `sim/report.py` under `apps/`.** The user ruled on this: core reporting stays in `sim/`;
  `apps/` is for separate consumers.

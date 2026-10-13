# Architecture — Rocket Trajectory Simulator

## Summary

Personal-use, from-scratch rocket trajectory simulator. Physics source of truth is `main.tex`;
this document turns it into code structure. Stack: plain Python 3.12 + numpy + scipy
(`solve_ivp`) + matplotlib, no packaging, no framework. Single flat package `sim/` with one
module per concern (params, state, frames, forces, dynamics, integrate, plotting) plus a
`run.py` entry point. Key decisions: a single NED-style inertial frame with **z pointing down**
(so `main.tex`'s `W = m g ẑ_g` is literally true), rotation isolated in `frames.py` as one
function, and force models exposed from day one with their *final* signature
`f(t, state, params)` so Phase 2 replaces function **bodies**, not call sites. Phase 1 state is
a 6-vector `[x, z, vx, vz, θ, ω]`. Mass/atmosphere/wind/thrust-curve modules are additive in
Phase 2; Phase 3 adds quaternion-based 6-DOF alongside (not instead of) the 2D code.

**Document layout:** §1-§10 are Phase 1 (implemented, unchanged). §11-§22 are the **Phase 2
design** (gravity ×4, atmosphere ×3 tiers, wind ×3 tiers, relative wind/α, real-data ingestion) —
start at §11 for anything Phase 2. Approval gates and open sign questions are collected in §22.
§23 holds the **Steps 38-40** additions designed after Phase 2.5 closed (non-parallel gravity,
thrust-axis misalignment, humid-air density); it is self-contained — a developer implementing one
of those three needs §23's own subsection plus the LaTeX section it names, not the whole document.
§24 holds the **Steps 41-44** additions (elliptical gravity direction, curved-ground impact
condition, lateral offsets `u_B`/`u_C`, pitch-damping `c_mq` scaffold) on the same self-contained
terms. §25 holds **Step 45** (the curved altitude `h_true` threaded into every altitude reader —
atmosphere, wind, the radial/WGS84 gravity magnitudes, and the reported/plotted altitude in
`run.py`/`plotting.py`), which completes what §24.2 deliberately left to backlog B8; every event
*trigger* is deliberately untouched there. §26 holds **Step 46** (Phase 2.9 — the MIL-F-8785C/
MIL-HDBK-1797 **Dryden** turbulence spectrum replacing the Step-21 placeholder gust mechanism in
`sim/wind.py`), on the same self-contained terms: a developer needs §26 plus
`latex/research/dryden_turbulence_model.md` §3/§5, not this whole file. It supersedes §16's gust
paragraph, and it is the first step that is *deliberately not* bit-for-bit for one configuration
(any run with gusts on) — §26.1 argues why that is a documented behaviour change rather than a
regression. Note the LaTeX section files moved to `latex/sections-ai/` in the
same session §24 was written; §23's `latex/sections/...` citations refer to the same content at the
new path. §27 holds **Steps 47-49** (Phase 2.10 — launch rail, recovery/parachute, and a
control-engineering scaffold with one concrete feedback controller, the apogee-targeting airbrake),
designed directly by the user's own request rather than drafted by the architect agent; it promotes
backlog items B1/B2 and opens B12 (sampled-data/PID control, the same determinism-constraint family
as B11).

---

## 1. Chosen stack

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.12 (installed: 3.12.10) | Already on the machine; fastest path from LaTeX equations to running code. Runtime is irrelevant here (a full flight is ~10⁴ RHS evaluations, milliseconds). |
| Arrays / math | numpy 2.5.3 | 2-vectors and 2×2 rotation matrices; in Phase 3 the same code generalises to 3-vectors and quaternions with no rewrite. |
| ODE integration | scipy 1.18.1 `scipy.integrate.solve_ivp` | Adaptive RK45/DOP853, plus **event detection** for free (ground impact, apogee, burnout, rail exit). Writing an event-locating adaptive integrator by hand is the one piece of this project with no learning payoff. This is a generic ODE solver, not a rocket library — the "no RocketPy" rule is respected: every force, moment and equation of motion is ours. |
| Plotting | matplotlib 3.11.2 | Standard, no alternative worth discussing. |
| Tests | pytest (physics sanity checks only) | ~6 tests total, each an analytic closed-form comparison. This is the mechanism that makes "each step independently committable" real. Not input validation — the user explicitly does not want that. |
| Packaging | **none** — `requirements.txt` + `python run.py` | Personal tool. No `pyproject.toml`, no src layout, no venv discipline enforced, no CI. |
| Config files | **none** — a frozen dataclass in `params.py` | A Python dataclass is a config file that can do arithmetic and has editor completion. YAML/TOML would add a parsing layer for a single user editing a single scenario. |

Everything above is already installed; `requirements.txt` exists only to record the versions.

### Verified API facts (checked against the installed scipy 1.18.1, do not re-research)

- `solve_ivp(fun, t_span, y0, method='RK45', t_eval=None, dense_output=False, events=None, vectorized=False, args=None, **options)`
- `args=(params,)` is the supported way to pass constants into the RHS — no closures or globals needed.
- Events are plain functions `g(t, y, *args)` carrying attributes `g.terminal = True` and
  `g.direction = +1 / -1 / 0`. A root is located by sign change between accepted steps.
- **Gotcha to code around:** the ground event `g = z` is zero at `t = 0` (launch from z = 0) and
  can fire immediately. Guard it: `return 1.0 if t < 0.1 else y[Z]`, or launch from `z0 = -1e-3`.
- `dense_output=True` + `sol.sol(t)` gives smooth interpolation for plotting; prefer it over
  forcing tiny `t_eval` spacing.

---

## 2. Frames and conventions

`main.tex` names three frames (`F0` ground, `Fg` gravity, `Fr` rocket). For a flat, non-rotating
Earth with uniform gravity, **F0 and Fg are the same frame** — they are kept distinct in the
derivation only so a curved/rotating Earth can be introduced later. The code collapses them into
one inertial frame `F_i` and notes the assumption.

**Axis convention: NED-like, z-down.**

- `x̂` — downrange, horizontal, positive in the launch-azimuth direction
- `ŷ` — out of the vertical plane (pitch axis), completing a right-handed set
- `ẑ` — **down**, positive toward the ground

Consequences:

- `W = m g ẑ` with `g = +9.80665` is exactly the equation in `main.tex` — no sign fixups.
- Altitude is `-z`. The **only** place that negation appears is `plotting.py` and the printed
  summary. Nothing in the physics ever refers to "altitude".
  **Superseded at Step 45 (§25).** Altitude is `gravity.altitude_agl(y, p)` — the height above the
  *curved* reference surface, which is `-z` exactly under the default `gravity_direction =
  "parallel"`. `plotting.py` and the printed summary now call that helper like everyone else, so
  the negation lives in exactly one place (`gravity.ground_depth`) rather than in the reporting
  layer. The rest of this bullet stands: nothing in the physics refers to "altitude" except the
  models that genuinely need one (§25.4).
- It generalises directly to standard aerospace NED for Phase 3 (no convention change at 6-DOF).

**Body frame `Fr`:** `x̂_r` along the nose, `ẑ_r` "belly-ward", `ŷ_r ≡ ŷ` (pitch axis, identical
to the inertial `ŷ` in the planar case).

**Attitude:** pitch `θ`, positive nose-up, measured from the inertial `x̂` (horizontal). A
vertical launch is `θ₀ = +π/2`.

### The single rotation function

Everything trigonometric lives in `frames.py` and nowhere else:

```
R_body_to_inertial(θ) = [[ cos θ,  sin θ],
                         [-sin θ,  cos θ]]        # acts on (x, z) components
```

Check: `x̂_r = (1,0)_b → (cos θ, −sin θ)_i`; at `θ = π/2` this is `(0,−1)_i`, i.e. straight up. ✓
`ẑ_r = (0,1)_b → (sin θ, cos θ)_i`; at `θ = 0` this is `ẑ_i` (down). ✓
Inertial→body is the transpose. Two functions, `to_inertial(v_b, θ)` and `to_body(v_i, θ)`, are
the entire public interface; no other module writes `sin`/`cos`.

### How mixed-frame forces are summed

`main.tex` gives `W` in the gravity frame and `T`, `A_f` in the body frame. The rule in code:

1. `forces.py` returns each force **in its natural frame**, exactly as written in the LaTeX —
   `weight_inertial → (0, m g)`, `thrust_body → (T, 0)`, `aero_force_body → (−A_x, −A_z)`.
   This keeps the code line-by-line comparable with the document.
2. `dynamics.py` does the one conversion and the one sum:
   `F_i = weight_inertial + R_body_to_inertial(θ) @ (thrust_body + aero_force_body)`
   `a_i = F_i / m`

### Moments need no rotation at all

In the planar case `ŷ_r ≡ ŷ`, so the moment equation is evaluated entirely in the body frame.
Expanding `main.tex` with `aB = (l₁−l₂) x̂_r`, `aA = l₁ x̂_r`:

- `aB × T = (l₁−l₂) x̂_r × T x̂_r = 0` — with on-axis thrust applied at an on-axis point the
  thrust produces **no pitching moment**. The term is still written in the code (it becomes
  non-zero the moment a gimbal or thrust misalignment is added) but it evaluates to zero now.
- `aA × A_f = l₁ x̂_r × (−A_x x̂_r − A_z ẑ_r) = +l₁ A_z ŷ_r`   (since `x̂ × ẑ = −ŷ`)
- `A_m = −A_m ŷ_r`

Therefore the whole Phase 1 rotational equation is the scalar

```
I θ̈ = l₁·A_z − A_m
```

which is a one-line unit test.

---

## 3. Components and relations

```
run.py                 scenario: build Params, set initial State, call run_sim, call plots
  │
  ├─ params.py         frozen dataclass: every symbol in main.tex, as a constant
  ├─ state.py          State NamedTuple + pack/unpack, index constants
  │
  └─ integrate.py      run_sim(params, state0, t_max) -> Result
        │              owns solve_ivp, t_eval/dense_output, events (ground, apogee)
        └─ dynamics.py derivatives(t, y, params) -> dy/dt      ← the ODE right-hand side
              │        the ONLY place the equations of motion appear
              ├─ frames.py   to_inertial / to_body  (the only trigonometry)
              └─ forces.py   thrust_body, aero_force_body, aero_moment_body, weight_inertial
                              (Phase 2: these call atmosphere.py / thrust_curve.py / wind.py)

  plotting.py          Result -> figures. The only module that knows altitude = −z
                       and that angles are shown in degrees.
```

Dependency direction is strictly downward; `forces.py` never imports `dynamics.py`,
`plotting.py` is imported only by `run.py`. `dynamics.derivatives` has no knowledge of which
integrator calls it, so a hand-written RK4 can be swapped in without touching physics.

---

## 4. Data model

### State vector (Phase 1)

```python
class State(NamedTuple):
    x:     float   # inertial downrange position [m]
    z:     float   # inertial position, DOWN-positive [m]   (altitude = -z)
    vx:    float   # inertial velocity x [m/s]
    vz:    float   # inertial velocity z, down-positive [m/s]
    theta: float   # pitch, rad, positive nose-up, from horizontal
    omega: float   # pitch rate dθ/dt [rad/s]
```

The integrator sees a plain `np.ndarray` of length 6; `State(*y)` unpacks it at the top of
`derivatives`, and index constants (`X, Z, VX, VZ, THETA, OMEGA`) are exported for event
functions and post-processing. Derivative vector:

```
dy/dt = [vx, vz, ax, az, omega, (l₁·A_z − A_m)/I]
```

Phase 2 appends `m` (7th component, `ṁ` from the mass-flow model) — a field added at the end of
the NamedTuple plus one line in the derivative; nothing else changes. (Phase 2 detail: §19.)
Phase 3 uses its own `State3D` (r∈R³, v∈R³, q∈R⁴, ω∈R³ = 13 components).

### Parameters (Phase 1 — everything constant)

```python
@dataclass(frozen=True)
class Params:
    # inertia & geometry (main.tex §Geometry)
    m:  float          # mass [kg]
    I:  float          # pitch moment of inertia about CoG a [kg·m²]
    l1: float          # |Aa|, CoP -> CoG distance [m]
    l2: float          # |AB|, CoP -> thrust point distance [m]
    # environment
    g:  float = 9.80665
    # force magnitudes — Phase 1 constants, Phase 2 model outputs
    T:   float         # thrust magnitude [N]
    A_x: float         # axial aero force magnitude [N]
    A_z: float         # normal aero force magnitude [N]
    A_m: float         # aero pitching moment magnitude [N·m]
```

All SI, all angles in radians internally. Degrees exist only in `run.py` inputs (converted
immediately) and in plot labels.

### The model-swap seam (how Phase 2 avoids a refactor)

The seam is the **function signature**, not a plugin container. From Step 1, `forces.py` exposes:

```python
def thrust_body(t, s: State, p: Params) -> np.ndarray      # Phase 1: np.array([p.T, 0.0])
def aero_force_body(t, s: State, p: Params) -> np.ndarray  # Phase 1: np.array([-p.A_x, -p.A_z])
def aero_moment_y(t, s: State, p: Params) -> float         # Phase 1: -p.A_m
def weight_inertial(t, s: State, p: Params) -> np.ndarray  # Phase 1: np.array([0.0, p.m * p.g])
```

Every function already receives `(t, state, params)` — everything a real model could need.
Phase 2 rewrites a **body** (e.g. `thrust_body` interpolates a thrust curve and subtracts
`A_e·(p_amb(h) − p_ref)`) and adds fields to `Params` (curve table, nozzle exit area). Call
sites in `dynamics.py` never change. This is deliberately cheaper than a
`Callable`-fields-in-a-dataclass strategy-object design, which buys runtime swappability that a
single-user tool never exercises.

> **Phase 2 amendment.** This seam is unchanged for *one-behaviour-per-function* models (thrust
> curve, aero coefficients). It is **extended, not replaced**, for the three model families that
> now have 3-4 co-existing variants each (gravity, atmosphere, wind): the public function keeps
> the `f(t, y, p)` signature and the call site, but its body is a one-line dispatch on a string
> field in `Params`. See **§12**, which states the reasoning and the exact pattern.

---

## 5. "API contracts" (module interfaces)

```python
# frames.py
to_inertial(v_body: np.ndarray, theta: float) -> np.ndarray
to_body(v_inertial: np.ndarray, theta: float) -> np.ndarray
R_body_to_inertial(theta: float) -> np.ndarray          # 2x2

# dynamics.py
derivatives(t: float, y: np.ndarray, p: Params) -> np.ndarray

# integrate.py
run_sim(p: Params, s0: State, t_max: float = 300.0,
        method: str = "RK45", rtol=1e-8, atol=1e-10) -> Result
#   Result: NamedTuple(t: ndarray, y: ndarray(6,N), events: dict[str, float], raw: OdeResult)
#          + params: Params  — appended at Step 45 (§25.5), so a Result is self-describing and
#            plotting.py can resolve the altitude convention without a signature change
#   events: {"apogee": t_apogee, "ground": t_impact}

# plotting.py
plot_trajectory(r: Result)      # downrange x vs altitude (-z)
plot_time_histories(r: Result)  # altitude, speed, theta[deg], omega[deg/s] vs t
```

Events defined in `integrate.py`:

| Event | Function | direction | terminal |
|---|---|---|---|
| ground impact | `z` (guarded for `t < 0.1 s`) | `+1` (falling) | yes |
| apogee | `vz` | `+1` (up→down, z is down-positive) | no |
| burnout (Phase 2) | `t − t_burn` | `+1` | no |
| rail exit (Phase 2) | `‖r − r₀‖ − L_rail` | `+1` | no |

---

## 6. Directory structure

```
d:\Projects\rocket-trajectory\
├── main.tex                 # physics source of truth (user-maintained)
├── architecture.md          # this file
├── roadmap.md               # step-by-step build plan
├── PROJECT-STATUS.md
├── status.json
├── requirements.txt         # numpy, scipy, matplotlib, pytest
├── run.py                   # entry point / scenario definition
├── sim/
│   ├── __init__.py
│   ├── params.py            # Params dataclass — all constants
│   ├── state.py             # State NamedTuple + indices
│   ├── frames.py            # rotation, the only trigonometry
│   ├── forces.py            # forces & moments in their natural frames
│   ├── dynamics.py          # derivatives() — the equations of motion
│   ├── integrate.py         # solve_ivp wrapper, events, Result
│   └── plotting.py          # figures
└── tests/
    ├── test_frames.py       # R(0)=I, R(π/2) maps nose to up, R·Rᵀ=I
    ├── test_forces.py       # moment == l₁·A_z − A_m ; thrust moment == 0
    └── test_dynamics.py     # analytic checks (see below)

# Phase 2 adds:  sim/atmosphere.py, sim/thrust_curve.py, sim/wind.py, sim/aero.py, data/*.csv
# Phase 3 adds:  sim/quaternion.py, sim/state3d.py, sim/dynamics3d.py, sim/forces3d.py
```

### Analytic checks that make each step committable

| Check | Expected |
|---|---|
| `T = 0`, no aero, `θ` free | pure ballistic parabola, apogee `v₀²/2g`, matches closed form to ~1e-6 |
| constant `T`, no aero, vertical | `a = T/m − g`, altitude `½at²` exactly |
| `θ` fixed at 45°, no aero | tilted constant-acceleration parabola |
| `A_z = A_m = 0` | `θ̈ = 0`, `θ` stays at `θ₀` |
| Phase 3 | planar initial conditions reproduce the Phase 1 result to solver tolerance |

---

## 7. Non-functional decisions

- **Performance:** irrelevant. A full flight is <1 s wall clock. No vectorisation, no
  `vectorized=True`, no numba, no caching. Readability wins every time.
- **Accuracy:** `rtol=1e-8, atol=1e-10` on RK45. If Phase 2 stiffens the problem (sharp thrust
  cut-off), switch to `DOP853` or add `max_step` around burnout rather than changing the model.
- **Units:** strict SI, radians internally. Documented once at the top of `params.py`.
- **Validation / normalisation:** none, by user instruction. Wrong input → wrong plot; that is
  acceptable for a single user. The only defensive code is in `frames.py` (none needed) and
  the ground event guard.
- **Persistence:** none required; `Result` stays in memory. Optional one-line CSV dump in
  `run.py` if the user wants to diff runs.
- **Determinism:** fully deterministic through Phase 2 except gusty wind — if random gusts are
  added, seed explicitly in `Params`.
- **Logging:** `print()` of a short flight summary (apogee, apogee time, max speed, impact time,
  downrange). No logging framework.

---

## 8. Rejected options

| Rejected | Why |
|---|---|
| RocketPy / OpenRocket | Excluded by the user; also defeats the point — the goal is to derive and implement the dynamics. |
| Hand-written fixed-step RK4 as the *primary* integrator | No event location, no step control; apogee and impact times would be grid-resolution-limited. Kept as an optional cross-check (Phase 1 Step 8). |
| `pyproject.toml` / src-layout / installable package | Nobody installs this. `python run.py` from the repo root is the whole UX. |
| YAML/TOML/JSON scenario config | Adds a parsing and schema layer; a frozen dataclass is already a readable, arithmetic-capable, completion-friendly config. |
| Strategy objects (`Callable` fields, ABCs, model registry) | Real swappability that a single user never exercises at runtime. Fixed function signatures give the same refactor-freedom at zero structural cost. |
| Class hierarchy (`Rocket`, `Motor`, `Simulation` with inheritance) | The physics is a pure function `(t, y, p) → ẏ`. Wrapping it in mutable objects hides state and makes the ODE harder to test. |
| `pint` / unit-aware quantities | Slows the RHS by orders of magnitude and adds friction; SI discipline plus documented fields is enough at this scale. |
| sympy symbolic derivation of the EOM | `main.tex` is the derivation; re-deriving symbolically duplicates the source of truth. Reconsider only if Phase 3 Euler equations get unwieldy. |
| Euler angles for Phase 3 | Singular at pitch ±90° — which is precisely a rocket's nominal attitude. See roadmap Phase 3. |
| z-up (ENU) inertial frame | Would flip the sign of `main.tex`'s `W = m g ẑ_g` and force a mental translation on every comparison with the document. The cost is one negation in `plotting.py`. |
| Julia / C++ / Rust | Runtime is milliseconds; the constraint is the user's iteration speed, not the CPU's. |

---

## 9. Open physics questions for the user (affect implementation, not structure)

1. **`ẑ_g` direction** — this document assumes **down**, making `W = m g ẑ_g` correct with
   `g > 0`. Confirm.
2. **Sign of `A_m`** — `A_m = −A_m ŷ_r` means a positive `A_m` value pitches the nose *down*
   (restoring, for a stable rocket). Confirm that is the intent.
3. **`A_f` direction is only valid nose-forward.** `A_f = −A_x x̂_r − A_z ẑ_r` hard-codes drag as
   opposing the body axes. That holds while the rocket flies nose-first with positive axial
   velocity; after tip-over or on tail-first descent it is wrong. Phase 1 constants hide this;
   Phase 2 must drive the direction from the relative wind / angle of attack (roadmap Step 9),
   which needs a `main.tex` update.
   **RESOLVED** — `main.tex` §"Relative wind and angle of attack" (commit 9895505) now defines
   `v_rel`, `V`, `α`, `û`, `n̂` and generalises the force to `A_f = −A_x û − A_z n̂`, which reduces
   exactly to the Phase 1 form at `α = 0`. Roadmap Step 9 is unblocked; design in §15.
4. **"CoG doesn't change"** (main.tex §Current assumptions) conflicts with Phase 2 propellant
   depletion, which moves the CoG and changes `I`, `l₁` and `l₂` in time. Needs a derivation
   update before Step 12.
   **RESOLVED** — `main.tex` §Models > Mass and moment of inertia now gives a minimal two-lumped-
   mass derivation (`l_B(t)`, `I(t)` via the parallel-axis theorem); the propellant grain geometry
   itself is still a `\todo`. Unblocks Phase 2.5 Step 36.
5. **Thrust moment is identically zero** under the current geometry (`aB ∥ T`). Worth knowing
   before wondering why the rocket never pitches under thrust.
6. **Aerodynamic force axis** — Step 9's generalisation resolved item 3 above by rotating the
   Phase 1 force into the relative-wind frame (`û, n̂`), but the aerodynamic coefficients
   `C_A(α,M)`/`C_N(α,M)` (Step 25) are themselves body-axis quantities (matching the user's CFD
   data convention), so re-rotating them through `û, n̂` double-applies the `α`-dependence.
   **RESOLVED** — `main.tex` §Models > Aerodynamics now states the force stays in body axes,
   `A_f = -A_x·x̂_r - A_z·ẑ_r`, for every `α`; `û, n̂` are used only for `V, α, q`. Code fix
   scheduled as Phase 2.5 Step 35 (`sim/forces.py::aero_force_body`/`aero_moment_y`).
7. **Earth's rotation, dynamic (Coriolis) term** — the WGS84 gravity model already folds in the
   Earth's rotation *statically* (the equatorial/polar difference in `g`'s magnitude); nothing
   folds in the *dynamic* Coriolis/centrifugal fictitious-force terms on the moving rocket. Not
   previously tracked as an open question at all. `main.tex` §Models > Non-inertial frame
   corrections now states the standard formula; the launch-site-frame projection of `Ω` is a
   `\todo`. Scheduled as Phase 2.5 Step 37.

---

## 10. Implementation task list

The roadmap **is** the ticket list. Every step is sequential (`depends_on` = the previous step)
and `parallel_safe: false` — the user commits after each step and re-checks `main.tex` in
between, so there is nothing to parallelise and no separate `task.md`. Each roadmap step names
the files it touches and the section of this document it needs.

---
---

# PHASE 2 — Real models, still 2D

*Everything from here down is Phase 2 design, added on top of an unchanged Phase 1 (§1-§10).
Phase 1 sections are still current and still correct; nothing above this line was rewritten.*

## 11. Phase 2 overview and module map

Phase 2 replaces Phase 1's constant force magnitudes with physical models, driven by the new
`main.tex` §Models subsections (Gravity, Atmosphere, Wind) and §"Relative wind and angle of
attack". Scope, in the user's words: **four gravity variants, three atmosphere tiers, three wind
tiers**, all selectable; launch rail and recovery deferred to the backlog.

### Phase 2 table of contents

| § | Topic |
|---|---|
| 11 | Overview, module map, dependency direction |
| 12 | **Model selection pattern** — the dispatch-dict extension of the §4 seam (approval gate) |
| 13 | `sim/gravity.py` — constant / radial / wgs84 (`linear` removed, Phase 2.5 Step 34) |
| 14 | `sim/atmosphere.py` — ISA / sounding / field, the `AirState` interface |
| 15 | `sim/flow.py` — relative wind, α, V, q, Re, M; altitude conventions |
| 16 | `sim/wind.py` — analytic / sounding / field |
| 17 | `sim/soundings.py` + `data/` — file format, loading, altitude & horizontal interpolation |
| 18 | `Params` after Phase 2 (full field list) |
| 19 | Thrust curve, variable mass, pressure correction, aero coefficients |
| 20 | Phase 2 non-functional decisions and the test ladder |
| 21 | Phase 2 rejected options |
| 22 | Phase 2 open questions and approval gates |

### Module map (Phase 1 modules unchanged; new modules in **bold**)

```
run.py
  ├─ params.py            + model-selection strings, site, reference geometry (§18)
  ├─ state.py             + m as a 7th component (§19), otherwise unchanged
  └─ integrate.py         + burnout event; otherwise unchanged
        └─ dynamics.py    UNCHANGED in Phase 2 (except the optional tidy in Step 9)
              ├─ frames.py          unchanged
              └─ forces.py          bodies rewritten, signatures identical
                    ├─ **gravity.py**     g(t, y, p) -> float           (§13)
                    ├─ **flow.py**        flow_state(t, y, p) -> Flow   (§15)
                    │     ├─ **atmosphere.py**  air_state(t, y, p) -> AirState  (§14)
                    │     │     └─ **soundings.py**                     (§17)
                    │     └─ **wind.py**        wind_inertial(t, y, p) -> 2-vec (§16)
                    │           └─ **soundings.py**                     (§17)
                    ├─ **thrust_curve.py** T(t, y, p) -> float          (§19)
                    └─ **aero.py**         C_A, C_N, C_m(α, M)          (§19)

data/                     input data, committed to the repo (§17)
  ├─ soundings/<case>/*.csv      atmosphere + wind measurements, one file per station/time
  ├─ motors/<motor>.csv          thrust curve
  └─ aero/<config>.csv           aerodynamic coefficient table
tools/                    optional offline helper scripts, never imported by sim/ (§17)
```

Dependency direction stays strictly downward and acyclic. The important invariant: **`dynamics.py`
does not change in Phase 2.** Every new model is reached from a `forces.py` function body, exactly
as §4 promised.

### Why `flow.py` exists as its own module

`V`, `α`, `û`, `n̂`, `q`, `Re` and `M` are needed by `aero_force_body`, `aero_moment_y`, the aero
coefficient tables and (for `Re`/`M`) by nothing else. They are derived from *state + wind +
atmosphere* — i.e. they are the composition point of two model families. Putting them in
`forces.py` would make `forces.py` import `atmosphere` and `wind` and grow a second
responsibility; putting them in `atmosphere.py` would make the atmosphere know about the rocket.
`flow.py` is the seam: it depends on both environment modules and is depended on only by the aero
force/moment functions. It is a deep module in the §"codebase-design" sense — one small interface
(`flow_state`), a lot of coupling hidden behind it.

---

## 12. Model selection: the dispatch-dict extension of the §4 seam

**This is an approval-gate decision — see §22.** It is a genuine (small) departure from §4's
"one behaviour per function, swap by editing the body", and it needs to be settled before any
Phase 2 code is written, because gravity, atmosphere and wind all follow whatever is chosen.

### Why §4's pure form is not enough here

§4's rule assumes exactly one live implementation per concern, so a swap is "edit the body, keep
the signature". That is true of the thrust curve and the aero table. It is *not* true of the
three new families:

- The whole point of implementing several gravity models is **comparing them in the same
  session** ("how much apogee does the exact inverse-square law buy over a constant `g`?").
  Comment-out-the-body swapping makes a comparison a git-diff-and-rerun exercise and leaves dead
  code in the file.
- Three atmosphere and three wind tiers differ by *data availability*, not by physics preference:
  the user will run ISA when there is no sounding and the multi-station field when there is. That
  is a per-scenario choice, i.e. scenario data, i.e. `Params`.

### Chosen pattern (recommended)

```python
# sim/gravity.py
def _g_constant(t, y, p): return p.g
def _g_radial(t, y, p):   ...
def _g_wgs84(t, y, p):    ...

_MODELS = {"constant": _g_constant, "radial": _g_radial, "wgs84": _g_wgs84}

def g(t: float, y: np.ndarray, p: Params) -> float:
    """Gravitational acceleration magnitude [m/s^2] (main.tex §Models > Gravity)."""
    return _MODELS[p.gravity_model](t, y, p)
```

Properties, stated so the pattern is not re-litigated at every model family:

- The **public seam is still one function with the `(t, y, p)` signature**. `forces.weight_inertial`
  calls `gravity.g(t, y, p)` and never learns that variants exist. §4 holds.
- Each variant is a small private function, side by side, all live, all testable in one test file.
- A swap is a **one-word edit in `run.py`'s `Params(...)`**, not a code edit in `sim/`.
- A comparison sweep is three lines:
  `for gm in ("constant","radial","wgs84"): run_sim(replace(p, gravity_model=gm), s0)`.
- The selection string lands in `print(params)` and in any CSV dump, so a saved run is
  self-describing about which models produced it. Comment-out swapping loses that.
- It is *not* a plugin registry: the dict is module-private, there is no registration API, no ABC,
  no entry points, and unknown strings raise `KeyError` at the first RHS call (acceptable — §7
  "no input validation").

Cost: one dict lookup per RHS evaluation per model family (~4 × 10⁴ lookups per flight, tens of
microseconds total; §7 "performance is irrelevant" applies).

The same pattern applies verbatim to `atmosphere.py` (`p.atmosphere_model`), `wind.py`
(`p.wind_model`), the horizontal interpolator (`p.horizontal_interp`) and the aero force form
(`p.aero_model`, see §19).

### `p.aero_model` deserves a special note

`aero_force_body` has two genuinely different forms in Phase 2: the Phase 1 constants
(`−A_x, −A_z` from `Params`) and the dynamic-pressure form (`q S C_A`, `q S C_N`). Keeping both
behind `p.aero_model ∈ {"constant", "coefficients"}` means **the Phase 1 analytic regression tests
in `tests/test_dynamics.py` keep passing untouched forever** — they simply run with
`aero_model="constant"`. Without it, every Phase 1 closed-form check would have to be rewritten or
deleted at Step 13. That alone pays for the selector.

**Corrected at Step 55** (Phase 2.11 rewrite pass, `architecture-28-rewrite.md` §28.5): the
paragraph above described `"constant"` as a raw, atmosphere-independent force — that is now false.
`aero_model` is a three-way `"constant" | "linearized" | "table"` dispatch, and every variant,
`"constant"` included, is `q`-scaled; see §28.5 for the corrected seam.

---

## 13. `sim/gravity.py` — four gravity models

Spec: `main.tex` §Models > Gravity. All variants here return the **scalar magnitude** `g`. The
direction was the fixed `ẑ_g = ẑ_i` (down) for all of Phase 2, so `forces.weight_inertial` was
`np.array([0.0, p.m * gravity.g(t, y, p)])` and nothing else changed. **Superseded at Step 38**
(§23.1): direction is now its own dispatch seam, `gravity.z_hat_g(t, y, p)`, selected by
`p.gravity_direction` (`"parallel"` — the default, bit-for-bit the line above — or `"radial"`).
The magnitude table below is unaffected and combines freely with either direction.

Altitude used by all variants: `h = -y[Z]` (above the launch point) — plus `p.h0_m` when a
mean-sea-level altitude is needed (`wgs84`); see §15 "Altitude conventions". **Superseded at
Step 45** (§25): `h` is now the height above the *curved* reference surface, `altitude_agl(y, p)` /
`altitude_msl(y, p)`, which reduces to `−y[Z]` bit-for-bit under the default
`gravity_direction = "parallel"`. The magnitude table below is unchanged — only the `h` fed into it
is, and `p.R_e` remains the geocentric radius of the `radial` falloff (§25.2).

| `gravity_model` | Formula | Notes |
|---|---|---|
| `"constant"` | `g = p.g` | Phase 1 baseline, the default. Bit-for-bit reproduces Phase 1. |
| ~~`"linear"`~~ | ~~`g₀(1 − 2h/R_e)`~~ | **Removed at Phase 2.5 Step 34** — first-order expansion of the inverse-square law, strictly dominated by `"radial"` below (exact, equally cheap, doesn't go negative above `h = R_e/2`). |
| `"radial"` | `g₀·(R_e/(R_e+h))²` | Exact for a spherical non-rotating Earth. |
| `"wgs84"` | Somigliana normal gravity + 2nd-order free-air correction, `g(φ, h_msl)` | The "real data" variant — see below. |

### The `"wgs84"` ("real data") variant

`main.tex` explicitly leaves the data source as an implementation choice and only requires a
scalar `g`. The chosen source is the **WGS84 normal-gravity formula (Somigliana) with the
second-order free-air correction** — the reference model the entire geodesy world quotes,
published closed-form constants, no dataset file, no new dependency, no network:

```
γ₀(φ) = 9.7803253359 · (1 + 0.00193185265241·sin²φ) / sqrt(1 − 0.00669437999013·sin²φ)
g(φ,h) = γ₀ · [ 1 − (2/a)(1 + f + m − 2f·sin²φ)·h + (3/a²)·h² ]
a = 6378137.0 m,  f = 1/298.257223563,  m = 0.00344978650684
```
with `φ = p.lat0_deg` (the launch site latitude — under the flat-range assumption latitude does
not change during the flight) and `h = h0_m − z` (metres above the ellipsoid; the ellipsoid/geoid
distinction is far below the model's own error here and is ignored).

This captures what the constant/linear/radial models cannot: the ~0.5 % equator-to-pole variation
and the Earth's rotation (centrifugal) contribution, both folded into `γ₀`.

A true gridded dataset (EGM2008 geoid / gravity anomalies) is **backlog**, not Phase 2: it means a
multi-MB coefficient file or a new geodesy dependency, to capture anomalies of order 10⁻⁴ g — two
orders of magnitude below the atmosphere model's own uncertainty. See roadmap Backlog.

### Should there be a fifth variant?

The obvious candidates and the verdict on each (the user asked; this is the grounded answer):

- **J2 / oblateness-corrected radial** — physically the step between `radial` and `wgs84`, but
  `wgs84` already *is* the oblate-Earth normal gravity with rotation included. Redundant. Skip.
- **Tabulated `g(h)` from a CSV** — mirrors the atmosphere tier-2 idea, but nobody measures a
  vertical gravity profile at a launch site; it would be a file containing a formula's output.
  Skip.
- **Non-parallel gravity (direction varying with downrange distance)** — the one genuinely
  *different* model, and the only one that adds new physics rather than a better magnitude. Was
  blocked on `main.tex` §Current assumptions ("`ẑ_g` fixed for the whole flight"). **Now derived
  and specified** — `models.tex` §Gravity > Direction, implementation in §23.1 — and it turns out
  *not* to be a fifth `gravity_model` at all, but a second, orthogonal dispatch on direction.

Recommendation at the time: **four variants, exactly as `main.tex` listed them.** No fifth.
(Revised at Phase 2.5 Step 34: down to three — `linear` removed, see §13's model table above.)

---

## 14. `sim/atmosphere.py` — three tiers behind one interface

Spec: `main.tex` §Models > Atmosphere. One public function, one return type, three tiers:

```python
class AirState(NamedTuple):
    rho: float   # density [kg/m^3]
    p:   float   # static pressure [Pa]
    T:   float   # temperature [K]
    a:   float   # speed of sound [m/s]
    mu:  float   # dynamic viscosity [Pa·s]

def air_state(t: float, y: np.ndarray, p: Params) -> AirState:
    return _MODELS[p.atmosphere_model](t, y, p)
```

All five quantities are returned together because they are all derived from the same `(T, p)` pair
— splitting them into five functions would recompute the layer lookup / interpolation five times
per RHS evaluation and invite them to drift out of thermodynamic consistency.

The signature is `(t, y, p)`, not `(h)`, deliberately: tier 3 needs horizontal position and time,
which live in the state. Tier 1 ignores everything but `y[Z]`.

| `atmosphere_model` | Tier | Source |
|---|---|---|
| `"isa"` | 1 | International Standard Atmosphere, pure formula |
| `"sounding"` | 2 | one station's measured profile, interpolated in altitude (§17) |
| `"field"` | 3 | N stations, interpolated in altitude + horizontal position (§17) |

There is no `"none"` tier: an atmosphere is always available. Phase 1 behaviour is preserved
through `p.aero_model = "constant"` (§12), not through a null atmosphere.

### Tier 1 — ISA, the reference implementation

Standard layered model, geopotential altitude `H = R_isa·h_msl/(R_isa + h_msl)`,
`R_isa = 6356766 m`:

| Layer | base H [m] | lapse L [K/m] | T_b [K] | p_b [Pa] |
|---|---|---|---|---|
| 0 troposphere | 0 | −0.0065 | 288.15 | 101325 |
| 1 tropopause | 11000 | 0.0 | 216.65 | 22632.06 |
| 2 stratosphere | 20000 | +0.0010 | 216.65 | 5474.889 |
| 3 stratosphere | 32000 | +0.0028 | 228.65 | 868.0187 |
| 4 stratopause | 47000 | 0.0 | 270.65 | 110.9063 |
| 5 mesosphere | 51000 | −0.0028 | 270.65 | 66.93887 |
| 6 mesosphere | 71000 | −0.0020 | 214.65 | 3.956420 |

```
L ≠ 0 : T = T_b + L(H − H_b),  p = p_b·(T/T_b)^(−g_isa/(L·R_d))
L = 0 : T = T_b,               p = p_b·exp(−g_isa(H − H_b)/(R_d·T_b))
ρ = p/(R_d·T)          a = sqrt(γ·R_d·T)
μ = μ₀·(T/T₀)^1.5·(T₀+S_μ)/(T+S_μ)      (Sutherland)
```

Module-level constants (**not** `Params` fields — they are physical constants of the model, not
scenario knobs): `R_d = 287.0528`, `γ = 1.4`, `g_isa = 9.80665`, `μ₀ = 1.716e-5`, `T₀ = 273.15`,
`S_μ = 110.4`.

> **Important and easy to get wrong:** `g_isa` inside the atmosphere model is part of the ISA
> *definition* and must stay `9.80665` regardless of `p.gravity_model`. The atmosphere must not
> call `gravity.g()`. (Physically the ISA pressure column is defined with constant `g`; mixing in
> a radial `g` would give a profile that is neither ISA nor measured.) Layers above 32 km change
> the answer by <0.1 % for a hobby rocket, but they cost four table rows and remove a silent
> ceiling.

Tiers 2 and 3 are `soundings.py` queries wrapped into the same `AirState`; their interpolation
rules (log-linear in pressure, gas law for density, ISA-anchored extrapolation outside the data)
are in §17.

---

## 15. `sim/flow.py` — relative wind, angle of attack, Reynolds, Mach

Spec: `main.tex` §"Relative wind and angle of attack" + the `Re`/`M` definitions in §Models >
Atmosphere.

```python
class Flow(NamedTuple):
    V:     float        # |v_rel| [m/s]
    alpha: float        # angle of attack [rad], atan2(w, u)
    u_hat: np.ndarray   # (cos α, sin α)   — body-frame components, main.tex û
    n_hat: np.ndarray   # (−sin α, cos α)  — body-frame components, main.tex n̂
    q:     float        # dynamic pressure ½ρV² [Pa]
    M:     float        # Mach number V/a
    Re:    float        # Reynolds number ρ·V·l_ref/μ
    air:   AirState     # the atmosphere sample used

def flow_state(t: float, y: np.ndarray, p: Params) -> Flow
```

Computation, line by line against the LaTeX:

```
v_i    = (y[VX], y[VZ])                       inertial velocity
v_w    = wind.wind_inertial(t, y, p)          inertial wind        (main.tex §Models > Wind)
v_rel  = frames.to_body(v_i − v_w, y[THETA])  = (u, w) in F_r      (main.tex eq. v_rel)
V      = hypot(u, w)
alpha  = atan2(w, u)
air    = atmosphere.air_state(t, y, p)
q      = 0.5·air.rho·V²      M = V/air.a      Re = air.rho·V·p.l_ref/air.mu
```

Degenerate case `V = 0` (on the pad at `t = 0`): `α = atan2(0,0) = 0` in Python (no exception),
`q = M = Re = 0`, and every aero force is zero. No guard needed — this is the one place it is
worth stating explicitly so nobody adds a defensive branch later.

### How the aero force uses it (`forces.py`, `aero_model="coefficients"`)

**Revised at Phase 2.5 Step 35.** Step 9 originally rotated the force into the relative-wind
frame, `A_f = −A_x·û − A_z·n̂`. That double-applied the `α`-dependence: `C_A(α,M)`/`C_N(α,M)`
(Step 25) are body-axis (axial/normal) coefficients, the same convention the CFD/wind-tunnel data
is extracted in, so their own table already carries the full `α`-dependence. The force stays in
body axis, unconditionally, matching the Phase 1 expression for every `α`, not just `α = 0`:

```
A_f = −A_x·x̂_r − A_z·ẑ_r                (main.tex §Models > Aerodynamics)
A_x = q·S·C_A(α, M)      A_z = q·S·C_N(α, M)      A_m = q·S·d_ref·C_m(α, M)
```

`flow.û, n̂` (§15 below) are still computed and still used — just to get `V, α, q` into the
coefficient lookup, not to redirect the force. The moment arm term in `dynamics.py` simplifies
accordingly: `cross_y(aA, A_f) = −l₁·A_f,z = l₁·A_z`, exactly, for every `α` — the same closed
form as the Phase 1/constant-model case, no longer just its `α = 0` special case.

### Altitude conventions (three altitudes, do not mix them)

| Symbol | Meaning | Expression | Used by |
|---|---|---|---|
| `z` | state, **down-positive**, zero at the launch point | `y[Z]` | the physics |
| `h_agl` | above the launch point | `−y[Z]` | gravity `radial` (`main.tex` defines `h = −z`), rail/recovery later |
| `h_msl` | above mean sea level | `p.h0_m − y[Z]` | ISA, soundings, `wgs84` |

Soundings are published against MSL and ISA is defined against MSL, so a launch site at 380 m that
is treated as sea level starts the rocket in ~4.5 % too dense air. `p.h0_m` defaults to `0.0`,
which makes the two identical and keeps every Phase 1 check intact. Two module-level helpers in
`flow.py` (`altitude_agl(y)`, `altitude_msl(y, p)`) are the only places the negation appears
outside `plotting.py`.

> **Superseded at Step 45 (§25).** The two helpers moved to `sim/gravity.py` — beside
> `curvature_radius`/`ground_depth`, the construction they now delegate to — and both take
> `Params`: `altitude_agl(y, p)`, `altitude_msl(y, p)`. `h_agl` is no longer `−y[Z]` but the height
> above the *curved* reference surface (`h_true`), which equals `−y[Z]` bit-for-bit under the
> default `gravity_direction = "parallel"`. The row "used by" for `h_agl` gains the tier-1 wind
> shear profile, and for `h_msl` the three atmosphere tiers and wind tiers 2/3, which until Step 45
> each inlined their own copy of `−y[Z] + p.h0_m`. The table's *meanings* are unchanged; only their
> expressions and their home are. See §25.3 for the replacement table.

### Performance note (deliberate, do not "optimise")

`dynamics.derivatives` calls `thrust_body` and `aero_force_body` twice each (once for the force
sum, once for the moment), so `flow_state` — and through it the atmosphere and wind models —
is evaluated up to 2× per RHS call, ~10⁵ times per flight. At microseconds per call this is
irrelevant (§7). **No memoisation, no cache keyed on `t`, no passing a `Flow` object through the
force signatures.** Keeping the `f(t, y, p)` seam is worth far more than the microseconds.
(An optional behaviour-preserving tidy in Step 9: compute `thrust_body`/`aero_force_body` once
into locals in `derivatives` and reuse them for the moment. Identical results, half the calls;
take it or leave it.)

---

## 16. `sim/wind.py` — three tiers behind one interface

Spec: `main.tex` §Models > Wind.

```python
def wind_inertial(t: float, y: np.ndarray, p: Params) -> np.ndarray:
    """Wind velocity in F_0 as (w_x, w_z), z DOWN-positive."""
    return _MODELS[p.wind_model](t, y, p)
```

Returned in the **inertial** frame (not body), because that is where `main.tex` writes
`v_rel = v − v_w`; `flow.py` does the single `to_body` rotation of the difference.

| `wind_model` | Tier | Behaviour |
|---|---|---|
| `"none"` | — | zeros. The default; makes every Phase 1 result reproducible. |
| `"analytic"` | 1 | constant wind + power-law shear + optional deterministic gusts |
| `"sounding"` | 2 | one station's measured `v_w(h)`, interpolated in altitude (§17) |
| `"field"` | 3 | N stations, interpolated in altitude + horizontal position (§17) |

### The 2D projection problem (applies to tiers 1-3)

Real wind is a horizontal vector; the simulator is planar. The launch azimuth `p.azimuth_deg`
(degrees clockwise from North, the direction of `+x̂`) fixes the flight plane. With meteorological
convention (`wdir` = the direction the wind blows **from**, degrees from North):

```
along-plane (downrange) component :  w_x = −W·cos(wdir − azimuth)
cross-plane component            :  w_y = −W·sin(wdir − azimuth)      ← DISCARDED in 2D
vertical                          :  w_z = 0   (z is down; an updraft is negative)
```

The cross-plane component is computed and **thrown away** in Phase 2 — a headwind/tailwind-only
simulation. This is a real modelling limitation, not an oversight: representing crosswind
weathercocking needs the out-of-plane degrees of freedom that only Phase 3 has. Documented in the
module docstring, and `wind.py` should expose `wind_horizontal_enu(...)` returning both components
so Phase 3 can use it unchanged.

### Tier 1, the analytic model

```
W(h) = W_ref·(max(h, h_ref)/h_ref)^shear_exp        power law, shear_exp ≈ 1/7 = 0.143
       (clamped below h_ref rather than extrapolated to 0 at the ground)
wdir  = wind_dir_deg                                constant with altitude
```
plus optional gusts — **and gusts have a hard constraint**: an adaptive ODE solver evaluates the
RHS at arbitrary, repeated and *rejected* times. Drawing a random number per call makes the RHS a
non-function of `t`, which destroys step-size control and makes results non-reproducible. So the
gust model must be a **deterministic function of `t`**: a frozen sum of sinusoids
`Σ aᵢ sin(ωᵢ t + φᵢ)` with amplitudes from a von Kármán/Dryden-like spectrum and phases drawn once
from `np.random.default_rng(p.gust_seed)`. Seed in `Params`, realisation built lazily and cached
per seed. `gust_sigma = 0.0` (default) turns it off entirely.

> **Superseded at Step 46 (§26).** The promise above — "amplitudes from a von Kármán/Dryden-like
> spectrum" — was never kept by the Step-21 implementation, which drew half-normal random weights
> with no spectral shape and no altitude dependence (§26.1). Step 46 replaces it with the real
> MIL-F-8785C/MIL-HDBK-1797 **Dryden** spectrum: `L_u`/`σ_u` from the altitude (AGL) profile,
> amplitudes from `Φ_u`/`Φ_v`, and **two** horizontal components (`u` along-wind, `v` cross-wind)
> composed as a *vector* perturbation of the mean wind rather than one scalar on its speed — so the
> non-negativity clamp goes too (§26.7). The frozen-sum-of-sinusoids form, the deterministic
> frequency grid, the per-seed `lru_cache` and the "off means off, the RNG is never touched"
> convention all survive unchanged. `gust_sigma`/`gust_seed` are replaced by
> `turbulence_model` (the gate, default `"none"`), `turbulence_sigma_high_ms`,
> `turbulence_ref_speed_ms` and `turbulence_seed` (§26.3). Gusts remain **tier-1 only**. See §26.

Tiers 2 and 3 are `soundings.py` queries; wind is interpolated as **(u, v) components, never as
speed/direction** (direction wraps at 360° and would swing a rocket through a phantom 180° shear).

---

## 17. Real data: `data/` layout, `sim/soundings.py`, interpolation

**This section contains approval-gate decisions — see §22** (file format, no-pandas, no-live-API).

### One file format for atmosphere *and* wind

Atmosphere tier 2/3 needs `T(h), p(h)`; wind tier 2/3 needs `wdir(h), wspd(h)`. Every real upper-air
source publishes these **in one table** (radiosonde output, University of Wyoming archive, GFS/ECMWF
point forecasts, Open-Meteo, Windy). Splitting them into two file families would mean two loaders,
two interpolators and two chances for the two to be sampled at inconsistent altitudes. So: **one
canonical sounding file, consumed by both `atmosphere.py` and `wind.py`.** This is the code sharing
the user asked for, at the data level rather than the module level.

```
data/soundings/<case>/<station>_<YYYYMMDDHHMM>.csv
```

```csv
# station: LKPR
# lat_deg: 50.1008
# lon_deg: 14.2600
# elevation_m: 380
# time_utc: 2026-05-01T12:00:00Z
# source: University of Wyoming upper-air archive, manual export
h_msl_m,p_Pa,T_K,wdir_deg,wspd_ms
380,96700,287.3,210,4.1
500,95300,286.5,213,5.0
1000,89900,283.1,220,7.6
```

Rules, all deliberately minimal:

- Metadata lives in `#`-prefixed `key: value` lines above the header. Parsing is `line.split(':', 1)`
  — no YAML front-matter, no sidecar JSON. One file is fully self-describing, so **there is no
  manifest file to keep in sync**; a "case" is just a folder and the loader globs it.
- `h_msl_m` strictly increasing, geometric altitude above MSL. Empty fields are allowed and load as
  `NaN`, so an atmosphere-only or wind-only sounding is the same format with blank columns.
- **Step 40 adds one optional column, `Td_K` (dewpoint, kelvin)** — absent column ⇒ all-`NaN` ⇒
  dry-air density, so every existing file stays valid unchanged. See §23.3.
- One file = one station × one time. Tier 2 = a folder with one file; tier 3 = a folder with
  several. **The tier is chosen by `p.atmosphere_model` / `p.wind_model`, not inferred from the
  file count** — inferring would silently change physics when a file is added.
- `data/` is committed (small CSVs, a few kB each). Input data is not build output; a run must stay
  reproducible from the repo alone. `.gitignore` already only ignores `*.png` and `trajectory.csv`,
  so no change is needed.
- Units are in the column names (`_m`, `_Pa`, `_K`, `_deg`, `_ms`). That is the entire unit
  discipline for input files.

### Loading

`numpy.genfromtxt` + a six-line comment-header parser. **No pandas** — the only pandas feature in
play is `read_csv`, for a handful of ≤200-row files, against a hard-won three-dependency project
(§1). See §22 for the decision table.

```python
class Sounding(NamedTuple):
    station: str; lat: float; lon: float; elev: float; time_utc: str
    h: np.ndarray     # m MSL, ascending
    p: np.ndarray; T: np.ndarray      # Pa, K  (may be NaN)
    u: np.ndarray; v: np.ndarray      # m/s ENU components, derived at load time

@lru_cache(maxsize=None)
def load_case(case: str) -> tuple[Sounding, ...]   # globs data/soundings/<case>/*.csv
```

`Params` stores the **case name only** (`sounding_case: str`), never loaded arrays: `Params` is a
frozen dataclass that gets printed, compared and dumped to CSV, and numpy arrays inside it would
break all three. Every module resolves data through an `lru_cache`d loader, so files are read once
per process, not once per RHS evaluation. The same rule applies to the thrust curve and the aero
table. **Rule: `Params` holds names and paths; modules hold the loaded data, cached.**

### Interpolation in altitude (tier 2)

| Quantity | Method | Why not linear in the quantity itself |
|---|---|---|
| `T` | linear in `h` | the profile *is* piecewise linear by construction |
| `p` | **linear in `ln p`** vs `h` | pressure falls exponentially; linear `p` over a 500 m gap is visibly off and thermodynamically inconsistent |
| `u`, `v` | linear in `h` | never interpolate `wdir` — it wraps at 360° |
| `ρ` | **derived**, `ρ = p/(R_d·T)` | interpolating ρ independently of p and T breaks the gas law |
| `a`, `μ` | derived from interpolated `T` | same reason |
| `T_d` | linear in `h`, edge-held outside the range (Step 40) | same profile shape as `T`; no standard dewpoint profile exists to anchor an extrapolation to (§23.3) |

Outside the data range: below the lowest level, continue with the first layer's lapse rate; above
the highest level, continue with an **ISA-shaped profile anchored at the top data point** (same
lapse-rate structure, but starting from the sounding's `(h_top, T_top, p_top)` so `T` and `p` are
continuous at the seam). Wind is held constant at the edge value. This matters: soundings often
stop at 10-25 km while a high-power rocket can pass through the top, and an unanchored ISA fallback
would put a density step at the seam.

`np.interp` does all of this; no `scipy.interpolate` needed for tier 2.

### Interpolation in horizontal position (tier 3)

At load time, resample every station onto a **common altitude grid** (default 0-30 km at 100 m,
`Params`-settable), giving arrays of shape `(n_stations, n_levels)` for `T`, `ln p`, `u`, `v`.
At query time:

1. Project station `(lat, lon)` and the rocket's ground position into a local tangent plane
   centred on the launch site (equirectangular; `E = R_e·cos φ₀·Δλ`, `N = R_e·Δφ`; <0.1 % error
   inside 100 km — the accuracy of the data is orders of magnitude worse).
   The rocket's 2D ground position is `(x·sin A, x·cos A)` in ENU with `x = y[X]`,
   `A = azimuth`.
2. Weight the stations, normalise, and combine the level arrays (weights depend only on horizontal
   position, so the whole horizontal step is one small dot product).
3. Interpolate the combined profile in altitude exactly as tier 2.

| `horizontal_interp` | Method | Behaviour |
|---|---|---|
| `"idw"` (default) | `wᵢ ∝ 1/(dᵢ² + ε²)` inverse-distance weighting, ~10 lines of numpy | Works with 1, 2 or N stations; defined everywhere including far outside the station polygon; exactly reproduces a station's profile at that station; never oscillates. `ε` (default 500 m) avoids the singularity at zero distance. |
| `"rbf"` | `scipy.interpolate.RBFInterpolator` (verified present in the installed scipy 1.18.1, signature `RBFInterpolator(y, d, neighbors=None, smoothing=0.0, kernel='thin_plate_spline', ...)`) | Smoother with many well-spread stations; can overshoot and needs ≥ (degree+1) points. Offered as an alternative behind the same string selector. |

`scipy.interpolate.griddata` / `LinearNDInterpolator` are **rejected**: they need ≥3 non-collinear
stations and return `NaN` outside the convex hull — and a rocket's ground track routinely leaves
the polygon of two or three weather stations. Silent `NaN` density mid-flight is the worst possible
failure mode here.

### Time (optional, last Phase 2 step)

Each file carries `time_utc`. With `p.t0_utc` set, sim time `t` maps to wall clock and the loader
linearly blends the two bracketing snapshots per station. Default behaviour without `t0_utc`: use
the single nearest snapshot per station. Kept as a separate, optional step so the spatial tiers
land first.

### Getting the data in the first place

Recommended for now: **the user manually exports a sounding and drops the CSV into
`data/soundings/<case>/`**, with the format above and one worked example committed. No network
access from `sim/`, fully offline, fully reproducible, no dependency.

If fetching becomes tedious, the right shape is a **separate offline script**,
`tools/fetch_sounding.py`, run by hand, writing the same canonical CSV, using stdlib `urllib`
(no `requests` dependency). The simulator itself still never touches the network, so runs stay
deterministic and repeatable. A live API call *inside* the RHS or inside `run_sim` is rejected
outright (§21). This is an approval gate — §22.

---

## 18. `Params` after Phase 2

Additions only; every Phase 1 field is unchanged and every new field has a default that
**reproduces Phase 1 exactly**, so `run.py` and all existing tests keep working at every step.

```python
@dataclass(frozen=True)
class Params:
    # ---- Phase 1 (unchanged) ----
    m: float; I: float; l1: float; l2: float
    g: float = 9.80665            # now read as g0 by gravity.py
    T: float = 0.0; A_x: float = 0.0; A_z: float = 0.0; A_m: float = 0.0

    # ---- model selection (§12) ----
    gravity_model:    str = "constant"   # constant | linear | radial | wgs84
    atmosphere_model: str = "isa"        # isa | sounding | field
    wind_model:       str = "none"       # none | analytic | sounding | field
    aero_model:       str = "constant"   # constant | coefficients
    horizontal_interp:str = "idw"        # idw | rbf

    # ---- launch site / Earth (§13, §15, §17) ----
    R_e:         float = 6371000.0   # mean Earth radius [m] (linear & radial gravity)
    lat0_deg:    float = 0.0         # geodetic latitude of the launch site (wgs84 gravity)
    lon0_deg:    float = 0.0         # longitude (station projection, tier 3)
    h0_m:        float = 0.0         # launch site elevation above MSL [m]
    azimuth_deg: float = 90.0        # direction of +x, degrees clockwise from North

    # ---- reference geometry (§15, §19) ----
    S:     float = 0.0   # aerodynamic reference area [m^2]
    d_ref: float = 0.0   # body diameter [m] — moment reference length
    l_ref: float = 0.0   # Reynolds reference length [m] (= d_ref, or body length)

    # ---- wind, analytic tier (§16) ----
    wind_ref_ms:    float = 0.0     # speed at wind_ref_h_m
    wind_dir_deg:   float = 0.0     # meteorological: direction the wind blows FROM
    wind_ref_h_m:   float = 10.0
    wind_shear_exp: float = 0.143   # 1/7 power law
    gust_sigma:     float = 0.0     # 0 disables gusts entirely
    gust_seed:      int   = 0

    # ---- real data (§17) ----
    sounding_case: str   = ""        # folder name under data/soundings/
    t0_utc:        str   = ""        # ISO-8601 launch time; "" = nearest snapshot
    grid_top_m:    float = 30000.0   # common altitude grid for tier 3
    grid_step_m:   float = 100.0
    idw_epsilon_m: float = 500.0

    # ---- thrust & mass (§19) ----
    motor_curve: str   = ""        # file under data/motors/
    A_e:         float = 0.0       # nozzle exit area [m^2]
    p_ref:       float = 101325.0  # ambient pressure the curve was measured at [Pa]
    m_dry:       float = 0.0       # dry mass [kg]
    I_sp:        float = 0.0       # specific impulse [s] (mass-flow model)

    # ---- aero coefficients (§19) ----
    aero_table: str   = ""     # file under data/aero/; "" = use the constants below
    C_A0:       float = 0.0    # constant fallbacks
    C_N_alpha:  float = 0.0    # per radian
    C_m_alpha:  float = 0.0    # per radian

    # ---- Steps 38-40 (§23) — each default reproduces every prior step bit-for-bit ----
    gravity_direction:   str   = "parallel"  # parallel | radial  (§23.1)
    thrust_misalign_deg: float = 0.0         # fixed nozzle cant delta [deg]  (§23.2)
    humid_air:           bool  = False       # virtual-temperature density, measured tiers (§23.3)
```

Note the two defaults that are *not* Phase 1 values: `atmosphere_model = "isa"` is safe because the
atmosphere only reaches the forces through `aero_model = "coefficients"`, which is off by default.

Physical constants of the models (`R_d`, `γ`, Sutherland's `μ₀/T₀/S_μ`, the ISA layer table, the
WGS84 constants) are **module-level constants in `atmosphere.py` / `gravity.py`, not `Params`
fields.** `Params` is scenario configuration; a scenario never varies the gas constant of air.

---

## 19. Thrust, variable mass, pressure correction, aero coefficients

These were already in the Phase 1-era roadmap; Phase 2 only re-slots them. Kept brief because the
design is unchanged — with two Phase 2 clarifications.

- **`thrust_curve.py`** — `data/motors/<motor>.csv` (`t_s,thrust_N`), `np.interp`, zero after the
  last point, loaded through an `lru_cache`d loader, `burnout` event in `integrate.py`. Replaces
  the `T_BURN` hack currently in `forces.py`.
- **Variable mass** — `m` becomes the 7th state component (§4). `dynamics.py` changes here and
  **only** here in all of Phase 2: one extra derivative row `ṁ = −T/(I_sp·g₀)` and `p.m` → `y[M]`
  in the acceleration. Still blocked on a `main.tex` update: §Current assumptions says the CoG does
  not move, which contradicts `I(t)`, `l₁(t)`, `l₂(t)`.
- **Pressure correction** — `T(t,h) = T_ref(t) + A_e·(p_ref − p_amb)`, with `p_amb` from
  `atmosphere.air_state(...).p`. Works identically with tiers 1, 2 and 3 — a good first consumer
  of the tier machinery that is not an aero force.
- **`aero.py`** — `C_A(α, M)`, `C_N(α)`, `C_m(α, M)` from `data/aero/<config>.csv` (a 2D table,
  `np.interp` in α inside a bracketing interpolation in M) or the constant fallbacks in `Params`.
  This is the step that makes `Re` and `M` load-bearing rather than merely computed.
  CoP travel makes `l₁` a function of `(α, M)`, which couples straight back into the moment.
- **Thrust direction (Step 38-40 block, §23.2)** — the thrust *vector* gains a fixed cant
  `δ = p.thrust_misalign_deg`: `thrust_body` returns `(T·cos δ, T·sin δ)` instead of `(T, 0)`.
  `dynamics.py` is unchanged — `_cross_y(aB, thrust)` already produces the correct
  `(l1+l2)·T·sin δ` moment, which is exactly what it was written generically for. `dm/dt` is
  driven by the thrust *magnitude* and is unaffected.

> **Sign warning, carried into the aero-coefficient step.** With `main.tex`'s geometry
> (`Aa = −l₁x̂_r`, so `aA = +l₁x̂_r`), the aero moment is `M_y = l₁(A_x sin α + A_z cos α)`. For a
> linear normal force `A_z = qS·C_Nα·α`, a positive `l₁` gives `θ̈ > 0` for `α > 0` — which
> *increases* α: **divergent, not restoring.** Static stability therefore requires `l₁ < 0` under
> the current definition, i.e. the CoP aft of the CoG. The old roadmap's "static margin (l₁ > 0)
> produces a restoring moment" was backwards. Confirm the intended sign convention with the user
> before the aero-coefficient step (§22) — this is exactly the kind of sign question the working
> rules say to stop and ask about rather than guess.

---

## 20. Phase 2 non-functional decisions and the test ladder

- **Dependencies: `requirements.txt` does not change.** numpy covers loading (`genfromtxt`) and
  altitude interpolation (`np.interp`); IDW is ten lines of numpy; scipy is already present if
  `"rbf"` is ever selected. No pandas, no requests, no geodesy package, no `pymsis`/`ambiance`.
- **Determinism.** Fully deterministic, including gusts (§16: frozen-phase spectral realisation,
  seeded in `Params`). Data loading is `lru_cache`d, so the same process gives the same numbers.
- **Offline.** `sim/` never opens a socket. Anything that fetches lives in `tools/`, is run by
  hand, and only writes files (§17).
- **Failure mode.** Per §7 there is no input validation: a bad model name raises `KeyError`, a
  missing data file raises `FileNotFoundError`, both at the first RHS call, both with the offending
  string in the message. That is the right amount of error handling for one user.
- **Solver.** The dynamic-pressure aero forces plus a real thrust curve make the RHS much
  stiffer around ignition and burnout than Phase 1's constants. If RK45 starts crawling or
  overshooting, switch to `DOP853` and/or add `max_step` near burnout (§7) — do not smooth the
  physics to please the solver.
- **Test ladder** (one or two cheap analytic checks per step, in the Phase 1 style):

| Module | Checks |
|---|---|
| `gravity` | all three give `g(h=0) ≈ g₀` at `lat = 45.5°`; `wgs84` gives 9.7803 at the equator, 9.8322 at the pole, 9.80665 near 45.5°; `radial` matches `wgs84`'s altitude dependence to ~1e-3 relative over 0-30 km |
| `atmosphere` ISA | `ρ(0)=1.225`, `p(11 km)=22632 Pa`, `T(20 km)=216.65 K`, `a(0)=340.29 m/s`, `μ(288.15)=1.789e-5`; monotone ρ |
| `flow` | at `α=0` the aero force equals the Phase 1 `(−A_x, −A_z)` exactly; with zero wind `v_rel == v`; `V=0` on the pad yields finite zeros |
| `wind` | `"none"` reproduces the previous step bit-for-bit; a pure headwind increases `V` by exactly the wind speed; direction→component conversion checked for the four cardinal directions |
| `soundings` | a synthetic CSV generated **from ISA itself** must be re-read and re-interpolated back to ISA within 0.5 % — this single test validates the format, the loader and the altitude interpolation at once |
| tier 3 | one station ⇒ identical to tier 2; querying at a station's own location returns that station's profile; two identical stations return the same profile everywhere |
| regression | with `gravity_model="constant"`, `aero_model="constant"`, `wind_model="none"`, every Phase 1 test still passes unchanged — run after **every** Phase 2 step |

---

## 21. Phase 2 rejected options

| Rejected | Why |
|---|---|
| pandas for CSV loading | One function (`read_csv`) for ≤200-row files. `np.genfromtxt` already returns exactly the arrays the interpolators need, and a pandas import costs more time than the whole simulation. |
| A live weather API called from `sim/` | Turns a deterministic simulation into a network-dependent one: no reproducibility, no offline runs, a new dependency, an API key, and rate limits inside an ODE right-hand side. If fetching is wanted, it belongs in a hand-run `tools/` script writing the canonical CSV (§17). |
| `ambiance` / `pymsis` / `metpy` / `pygeodesy` | The ISA is 15 lines and a 7-row table; Somigliana is one line. Importing a package to avoid writing them contradicts the "from scratch" goal as directly as RocketPy would. |
| `scipy.interpolate.griddata` / `LinearNDInterpolator` for stations | Needs ≥3 non-collinear stations and returns `NaN` outside the convex hull — which a ground track routinely leaves. Silent `NaN` density mid-flight is the worst failure mode available. |
| Strategy objects / `Callable` fields in `Params` for model selection | Still rejected (§8). The string + module-private dict gets the same swappability while keeping `Params` printable, comparable and CSV-dumpable. |
| Separate atmosphere-data and wind-data files | Every real source publishes both in one table; splitting them doubles the loader and lets the two drift onto inconsistent altitude grids (§17). |
| A `manifest.json` per station case | Metadata in the file's own comment header means one file, one truth, no sync problem. A folder glob is the whole "case" concept. |
| Inferring the tier from the number of files in a case folder | Adding one file would then silently change the physics. The tier is an explicit `Params` string. |
| Interpolating wind speed/direction (instead of u/v components) | Direction wraps at 360°; interpolating it invents 180° shears. |
| Interpolating ρ directly from station data | Breaks `ρ = p/(R_d T)` consistency; interpolate `T` and `ln p`, then derive. |
| Caching `flow_state` on `t` inside the RHS | Saves microseconds, adds a cache-invalidation bug surface, and would break the `f(t, y, p)` seam that makes Phase 2 cheap in the first place (§15). |
| Random gusts drawn per RHS call | Makes the RHS a non-function of `t`, breaking adaptive step control and reproducibility. Use a frozen seeded spectral realisation (§16). |
| EGM2008 / a gridded gravity dataset | Multi-MB coefficient set or a new dependency, for anomalies ~10⁻⁴ g — two orders of magnitude below the atmosphere model's own error. Backlog. |
| Making the ISA use the selected gravity model | ISA's `g = 9.80665` is part of the standard's *definition*; substituting radial `g` yields a profile that is neither ISA nor measured (§14). |

---

## 22. Phase 2 open questions and approval gates

Ordered by how much they block. 1-4 need an answer before implementation starts; 5-6 before the
step that hits them.

1. **Model-selection pattern (§12)** — string field + module-private dispatch dict, versus pure
   §4 body-editing, versus `Callable` fields. Recommendation: the dispatch dict. This is a
   deliberate, documented departure from §4 and should be approved explicitly, because gravity,
   atmosphere, wind and `aero_model` all follow it.
2. **Sounding file format and layout (§17)** — one unified CSV per station/time carrying both
   thermodynamics and wind, metadata in comment lines, a "case" = a folder, `data/` committed.
   Recommendation: as specified.
3. **pandas or not (§17, §21)** — recommendation: **no**, `np.genfromtxt` only, `requirements.txt`
   unchanged.
4. **Live weather API or not (§17, §21)** — recommendation: **no API inside `sim/`**; manual CSV
   drop now, and an optional hand-run `tools/fetch_sounding.py` using stdlib `urllib` later, if
   the manual step becomes annoying. Needs approval either way (network access + a data-source
   choice).
5. **Sign of `l₁` / static stability (§19)** — under `main.tex`'s current geometry, a stable
   rocket needs `l₁ < 0`. Confirm the intended convention (or update `main.tex`) before the
   aero-coefficient step.
6. **CoG motion under propellant depletion** — **RESOLVED**, see §9 item 4. Scheduled as
   Phase 2.5 Step 36.
7. **Non-parallel gravity** — **RESOLVED.** The derivation now exists (`models.tex` §Gravity >
   Direction: rigid rotation of the launch basis by `φ = x/R_e`), `main.tex` §Current assumptions
   is updated, and the implementation is specified in §23.1. Scheduled as Step 38. Still distinct
   from item 9 (Coriolis is dynamic and velocity-dependent; this is static and
   position-dependent), and the two are deliberately kept independent — see §23.1's scope note.
8. **Crosswind is discarded in 2D (§16)** — worth confirming the user is happy that wind only ever
   acts along the flight plane until Phase 3.
9. **Coriolis/centrifugal (rotating-Earth) correction** — **RESOLVED** as a design question, see
   §9 item 7; the tangent-plane projection of `Ω` is a `\todo` in `main.tex`. Scheduled as
   Phase 2.5 Step 37.
10. **Sounding file format gains an optional `Td_K` column (Step 40, §23.3)** — the format itself
    was an approval gate (item 2 above), so its extension is flagged here too. Backwards
    compatible in both directions: existing files load unchanged, and the correction is gated by
    `p.humid_air = False`. Recommendation: `Td_K`, kelvin, optional, as specified in §23.3.
11. **Linear gravity model removed** — the `"linear"` variant (`architecture.md` §13,
    `sim/gravity.py::_g_linear`) is being dropped: it is the weakest of the four (first-order
    truncation of inverse-square, goes negative above `h = R_e/2`) and offers no advantage over
    `radial`, which is exact and equally cheap. Scheduled as Phase 2.5 Step 34 (code + tests +
    the Step-27 comparison sweep).

---

## 23. Phase 2.6 — gravity direction, thrust misalignment, humid air (Steps 38-40)

Three additive steps designed after Phase 2.5 closed, from `latex/sections/models.tex`
(restructured in the same pass) and the new `latex/sections/analysis.tex`. Each is one step, one
commit, and each has a `Params` default that reproduces every prior step **bit-for-bit**. None of
them changes the state vector, the solver, the events or the module map; Steps 38 and 39 change
one function body each, Step 40 changes a data format and one derived quantity.

| Step | Physics | `Params` gate | Modules touched |
|---|---|---|---|
| 38 | gravity **direction** rotates with downrange distance | `gravity_direction: str = "parallel"` | `gravity.py`, `forces.py`, `params.py` |
| 39 | fixed thrust-axis cant (nozzle misalignment) | `thrust_misalign_deg: float = 0.0` | `forces.py`, `params.py` |
| 40 | humid-air density in the measured tiers | `humid_air: bool = False` + optional CSV column | `soundings.py`, `atmosphere.py`, `params.py`, `data/` |

### 23.1 Step 38 — non-parallel gravity (`gravity_direction`)

Spec: `models.tex` §Gravity > Direction (eqs. `xhat_g_rotated`, `zhat_g_rotated`,
`phi_downrange`, `weight_rotated`); `analysis.tex` §Forces for the body-axis reading. Resolves
roadmap Backlog B4 and §22 item 7 above.

**Model.** The launch-point basis is rotated rigidly by the ground arc angle `φ = x/R_e` about
the axis normal to the flight plane. In launch-frame `(x, z)` components, with `z` down:

```
phi         = y[X] / p.R_e
x_hat_g(phi) = ( cos(phi), sin(phi))
z_hat_g(phi) = (-sin(phi), cos(phi))
W            = m * g(t, y, p) * z_hat_g(phi) = ( -m*g*sin(phi), m*g*cos(phi) )
```

Only `z_hat_g` is needed by the code; `x_hat_g` is derived in the LaTeX for the construction and
is not used anywhere in `sim/`.

**Structure — a second dispatch dict in `gravity.py`, not a fourth `gravity_model`.** Magnitude
and direction are orthogonal choices (any of `constant`/`radial`/`wgs84` combines with either
direction), so folding direction into `gravity_model` would need a combinatorial product of
names. Instead `sim/gravity.py` gets a second §12-pattern seam beside `g()`:

```python
# sim/gravity.py
from sim.state import X

def _dir_parallel(t, y, p) -> np.ndarray:
    return np.array([0.0, 1.0])          # z_hat_g0, frozen at the launch vertical

def _dir_radial(t, y, p) -> np.ndarray:
    phi = y[X] / p.R_e                    # models.tex eq:phi_downrange
    return np.array([-np.sin(phi), np.cos(phi)])   # eq:zhat_g_rotated

_GRAVITY_DIRECTIONS = {"parallel": _dir_parallel, "radial": _dir_radial}

def z_hat_g(t: float, y: np.ndarray, p) -> np.ndarray:
    """Unit vector along the local gravity direction, inertial (launch-point)
    components. models.tex §Gravity > Direction."""
    return _GRAVITY_DIRECTIONS[p.gravity_direction](t, y, p)
```

`forces.weight_inertial` becomes exactly one line:

```python
m = s[M] if p.m_d is not None else p.m
return m * gravity.g(t, s, p) * gravity.z_hat_g(t, s, p)
```

**Bit-for-bit.** With `"parallel"` this evaluates `(m*g) * array([0.0, 1.0])` =
`array([0.0, m*g])` — identical bits to today's `np.array([0.0, m*g])`, since `x*0.0 == 0.0` and
`x*1.0 == x` exactly for finite positive `x`. Verified.

**`Params`:** `gravity_direction: str = "parallel"   # parallel | radial`. A string rather than a
`bool` (contrast `earth_rotation`) because this is a *choice among named models behind one
symbol* — the §12 pattern used by `gravity_model`, `atmosphere_model`, `wind_model`,
`horizontal_interp`, `aero_model` — and there is a plausible third variant (`φ =
arctan(x/(R_e+h))`, the Cartesian-embedding reading, rejected in `models.tex` as a 0.5 %
refinement of a small term). `earth_rotation` is a `bool` because it is a single term switched on
or off, with no named alternatives.

**Scope — what this step does NOT do** (all three are stated in `models.tex` and
`main.tex` §Current assumptions):

- No change to the state, the integration, or the meaning of `x`/`z`.
- No curved ground: `h = -z` stays measured from the launch-point tangent plane. The true surface
  drops `x²/2R_e` below it (8 m at 10 km, 71 m at 30 km). No curved-Earth impact event.
- **No coupling to the Coriolis frame.** `sim/rotation.py` keeps its launch-site-fixed `Ω`
  decomposition (`φ₀`, `χ` constants). The resulting inconsistency is `O(Ω·x/R_e)`, a relative
  `3e-6` of the retained Coriolis acceleration at 10 km downrange and `3e-4` at 100 km — verified
  numerically. Do not build a unified rotating frame; that is a curvilinear formulation the 2D
  state cannot carry.
- Zero effect on the rotational equation. Weight acts at the CoG, so `M_y` is untouched *exactly*,
  for any direction — verified end-to-end (`domega/dt` delta is exactly `0.0`).

**Checks for the step.** `gravity_direction="parallel"` reproduces every prior result bit-for-bit
(assert on `derivatives()` arrays, the `earth_rotation` test's pattern). With `"radial"`: at
`y[X] = 0` the direction is exactly `(0.0, 1.0)`; `‖z_hat_g‖ = 1` for arbitrary `x`;
`dvx/dt` changes by exactly `-g·sin(φ)` and `dvz/dt` by `g·(cos φ − 1)` relative to `"parallel"`
at the same state, and `domega/dt` by exactly zero; a flat-and-level state (`θ=0`) downrange
acquires a *retarding* downrange acceleration, not an accelerating one.

### 23.2 Step 39 — thrust-axis misalignment (`thrust_misalign_deg`)

Spec: `rocket-2d.tex` eq. `thrust_vector`; `analysis.tex` §Moment and §With thrust, misaligned
(eqs. `moment_full`, `moment_misaligned`, `alpha_trim`). Narrows the `main.tex` §Backlog item
"Thrust-axis misalignment and control" to its control half.

**Model.** One new `Params` field and one changed function body:

```python
# sim/params.py
thrust_misalign_deg: float = 0.0   # fixed nozzle cant delta [deg], +towards +z_hat_r

# sim/forces.py
def thrust_body(t, s, p):
    T = thrust_curve.thrust(t, s, p)
    delta = np.radians(p.thrust_misalign_deg)
    return np.array([T * np.cos(delta), T * np.sin(delta)])
```

**`sim/dynamics.py` needs no change at all.** This was designed in at Step 6: `M_thrust =
_cross_y(aB, thrust)` is already the general 2D cross product of `aB = (-(l1+l2), 0)` with a
general body-frame thrust vector, and

```
_cross_y(aB, (T cos d, T sin d)) = (l1 + l2) * T * sin(d) = (l_C - l_B) * T * sin(delta)
```

which is exactly the `M_δ` term of `analysis.tex` eq. `moment_misaligned` (`l1 + l2` is the code's
spelling of `l_C − l_B`, the CoG-to-nozzle axial arm). **Verified numerically against the actual
`_cross_y` and against `derivatives()` end-to-end**: with the thrust vector canted, `domega/dt`
changes by exactly `(l1+l2)·T·sin(δ)/I` and nothing else in `dydt` moves. `dynamics.py`'s own
comment ("written out … so a future gimbal or thrust misalignment … drops in with no change to
this function's structure") is correct as written; the only edit it needs is to that comment.

**Bit-for-bit.** `np.radians(0.0) == 0.0`, `np.cos(0.0) == 1.0`, `np.sin(0.0) == 0.0` exactly, so
the default returns `array([T, 0.0])` bitwise. No separate on/off flag is needed — same pattern as
`A_e: float = 0.0`.

**Degrees at the edge.** `thrust_misalign_deg` follows the `lat0_deg`/`azimuth_deg`/`wind_dir_deg`
convention: degrees in `Params`, converted with `np.radians` at first use, radians everywhere
inside. Realistic values are 0.1–1.0°.

**Not in this step** (both stated in `analysis.tex` §With thrust, misaligned): a commanded/gimbal
`δ(t)` and any control law; and the lateral offsets `u_B`, `u_C`, which have no `Params` fields
today (implicitly zero) — their term `(u_B−u_C)·T·cos δ` is derived in eq. `moment_full` but not
parameterised. `dm/dt` is unaffected: it is driven by the thrust *magnitude*, which `δ` does not
change.

**Checks for the step.** `thrust_misalign_deg = 0.0` reproduces prior results bit-for-bit. With
`δ ≠ 0` and `T > 0`: `M_y` shifts by exactly `(p.l1+p.l2)·T·sin(δ)`; the shift is **zero** when
`T = 0` (after burnout — the `analysis.tex` "no thrust" cell); the shift is independent of `α`
(evaluate at two angles of attack, same offset — the claim `∂θ̈/∂α` is unchanged); a statically
stable airframe settles at a small nonzero trim `α` of the sign of `M_δ` rather than diverging
(eq. `alpha_trim`), and reversing the sign of `δ` mirrors it.

### 23.3 Step 40 — humid-air density (`humid_air`, `Td_K` column)

Spec: `models.tex` §Atmosphere > Density (eqs. `virtual_temperature`, `magnus`). Resolves roadmap
Backlog B5.

**Formulas** (`T` in K, `T_d` in K, `p` in Pa, result in Pa/K/kg·m⁻³):

```
e_s(T_d) = 100 * 6.1094 * exp(17.625*(T_d-273.15) / ((T_d-273.15) + 243.04))     [Pa]
e        = e_s(min(T_d, T))        # clamp: T_d > T is unphysical (supersaturation in noisy data)
T_v      = T / (1 - (e/p)*(1 - eps)),   eps = R_d/R_v = 287.0528/461.5 = 0.6220
rho      = p / (R_d * T_v)                        # replaces rho = p/(R_d*T)
```

The `100 *` (hPa→Pa) is the one easy mistake. `R_v = 461.5` is a new module constant in
`atmosphere.py` beside `_R_D`; `_EPSILON` is computed from the two, never hard-coded as `0.622`,
so the pair cannot drift.

**Tier scope: `"sounding"` and `"field"` only. Not `"isa"`.** Same argument as `g_isa` (§14): the
ISA is *defined* as dry air of fixed composition; a moist ISA is neither the standard nor a
measurement. Tier 1 is untouched by this step.

**File format — one new optional column** (extends §17's format; backwards compatible):

```csv
h_msl_m,p_Pa,T_K,Td_K,wdir_deg,wspd_ms
380,96700,287.3,283.2,210,4.1
```

- Name `Td_K`, units kelvin, matching `T_K`. Sources publish dewpoint in °C; the conversion
  happens when the file is prepared, exactly as `wdir`/`wspd` are converted to ENU `u`/`v` at load
  time — the repository's canonical files are SI and internally consistent, not raw vendor dumps.
- **Optional**: a file without the column loads exactly as today, with `Td` an all-`NaN` array.
  An *empty field* on one row loads as `NaN` for that level, which §17 already allows.
- No existing committed file needs to change. `tools/fetch_sounding.py` may emit the column later;
  not required by this step.
- Column *order* is irrelevant — `np.genfromtxt(..., names=True)` is keyed by header name.

**`sim/soundings.py`:**

```python
class Sounding(NamedTuple):
    ...                              # unchanged fields
    Td: np.ndarray    # K, dewpoint; all-NaN when the column is absent   <-- appended last

class SoundingState(NamedTuple):
    ...                              # unchanged fields
    Td: float         # K, NaN when unavailable                          <-- appended last
```

- `_load_sounding_file`: `Td = data["Td_K"].astype(float) if "Td_K" in data.dtype.names else
  np.full(h.shape, np.nan)`. This is the *only* place the column's optionality is handled.
- `interp_altitude`: interpolate `Td` **linearly in `h`, exactly like `T`**, and hold it at the
  edge value outside the data range on both sides (the `u`/`v` rule, not the ISA-anchored `T`/`p`
  rule — there is no standard dewpoint profile to anchor to, and the clamp below makes the held
  value harmless). `rho` returned by this function **stays dry**, `p/(R_d*T)`: `interp_altitude`
  has no `p: Params` argument and must not grow one (it is called from the `lru_cache`d
  `_resample_case`). The humidity gate lives one level up.
- Tier 3: `ResampledCase` gains `Td: np.ndarray  # (n_stations, n_levels)`; `_resample_case` fills
  it from `interp_altitude`; `_combine` returns it as a fifth quantity — for `"idw"` one more
  `w @ resampled.Td`, for `"rbf"` the stacked array goes from 4 to 5 blocks of `n_levels` (update
  the slicing); `interp_field_at` passes `Td=Td` into the synthetic `Sounding`. Combining dewpoint
  linearly across stations is consistent with combining `T` linearly.

**`sim/atmosphere.py`** — the correction is applied here, where `p: Params` is in scope:

```python
_R_V = 461.5                 # specific gas constant for water vapour [J/(kg*K)]
_EPSILON = _R_D / _R_V       # 0.6220

def sat_vapor_pressure(T_K: float) -> float: ...        # Magnus/Alduchov-Eskridge, returns Pa
def virtual_temperature(T: float, Td: float, p_Pa: float) -> float: ...
def moist_density(p_Pa: float, T: float, Td: float) -> float: ...   # p/(R_d*T_v)
```

and in `_sounding_air_state` / `_field_air_state`, after the existing `interp_*` call:

```python
rho = state.rho
if p.humid_air and np.isfinite(state.Td):
    rho = moist_density(state.p, state.T, state.Td)
return AirState(rho=rho, p=state.p, T=state.T, a=state.a, mu=state.mu)
```

`a` and `mu` stay dry-air quantities — deliberate, see `models.tex` §Density ("what is
deliberately left dry"): a consistent moist `a` needs the mixture's `γ` too, the two effects
partly cancel, and the residual ~0.2 % is far below the aero table's own uncertainty.

**`Params`:** `humid_air: bool = False`. A `bool`, not a string: there are exactly two states
(dry, or the virtual-temperature correction), the same shape as `earth_rotation`. An explicit gate
rather than "apply it whenever the column happens to be present", because §21 already rejects
inferring physics from what is in the data folder ("adding one file would then silently change the
physics") — adding a column must not silently change the density either. With `humid_air=True` and
no dewpoint data the fallback is dry air, level by level, so the flag is safe to leave on.

**Checks for the step.** `humid_air=False` reproduces every prior result bit-for-bit (the `rho`
expression is not even evaluated). `e_s(0 °C) = 610.94 Pa` and `e_s(20 °C) = 2333.4 Pa` (within
0.4 % of the reference 611.2 / 2339 Pa — that *is* the Magnus fit's accuracy, do not "fix" it).
`T_d = T` gives saturated air and the largest correction at that `(p,T)`; a dewpoint far below `T`
gives a correction tending to zero; `T_v ≥ T` always, so `rho_moist ≤ rho_dry` always. Worked
values to pin: `(T=287.3 K, T_d=283.15 K, p=96700 Pa)` → `e = 1226.0 Pa`, `T_v − T = 1.384 K`,
`rho: 1.17254 → 1.16692` (−0.479 %); `(303.15, 299.15, 101325)` → −1.252 %. A sounding file with no
`Td_K` column must load and run unchanged with `humid_air` either way. Tier 3 with one station must
still reproduce tier 2 exactly, dewpoint included.

---

## 24. Phase 2.7 — elliptical gravity, curved ground, lateral offsets, pitch-damping scaffold (Steps 41-44)

Four additive steps designed after Phase 2.6 closed, from the LaTeX rewrite of the same session.
Same discipline as §23: one step, one commit, a `Params` default that reproduces every prior step
**bit-for-bit**, tests for every new behaviour. None of them changes the state vector, the solver
or the module map. Step 42 is the only one that touches `sim/integrate.py` at all.

**LaTeX path note.** The report's section files moved in the same session: `latex/sections/` no
longer exists, the live files are `latex/sections-ai/{rocket-2d,analysis,models}.tex`, wired into
`latex/main.tex` by `\input{sections-ai/...}`. §23's citations to `latex/sections/...` refer to the
same content at the new path. Every citation below uses the new path.

| Step | Physics | `Params` gate | Modules touched |
|---|---|---|---|
| 41 | ellipsoid-normal local vertical (osculating sphere in the flight azimuth) | `gravity_direction = "elliptical"` (new third value) | `gravity.py`, `params.py` |
| 42 | ground/impact measured from the curved surface, not the tangent plane | implied by `gravity_direction ∈ {radial, elliptical}` | `gravity.py`, `integrate.py` |
| 43 | lateral offsets of the CoG and the nozzle from the body axis | `u_B: float = 0.0`, `u_C: float = 0.0` | `dynamics.py`, `params.py` |
| 44 | pitch-damping derivative `c_mq` — inert scaffold | `c_mq: float = 0.0` + optional CSV column | `aero.py`, `forces.py`, `params.py` |

**Dependency:** 42 depends on 41 (it consumes 41's `curvature_radius` seam and must handle the
`"elliptical"` value). 43 and 44 are independent of 41/42 and of each other. Recommended order
41 → 42 → 43 → 44; strictly sequential regardless, per the project's one-step-one-commit rule.

**One open sign question before Step 44 is implemented** — `analysis.tex` §Dynamic stability states
the physical sign of `c_mq` in the *textbook* convention, which is inverted relative to this
document's own `A_m` convention. See §24.4 "Sign of `c_mq` — a real inconsistency in the spec",
which resolves it from first principles. That resolution must be agreed before the Step 44 tests are
written, because a test encodes the sign permanently.

### 24.1 Step 41 — elliptical gravity direction (`gravity_direction = "elliptical"`)

Spec: `latex/sections-ai/models.tex` §Gravity > Direction, paragraph **"Construction
(elliptical)"** (the `R_χ`, `M(φ)`, `N(φ)` equations, and the sentence "Every formula of the radial
construction above then carries over unchanged with `R_e → R_χ(φ₀,χ)`"). Builds directly on §23.1
(Step 38), which is the radial construction it reuses.

**Model.** The WGS84 ellipsoid's local vertical is the *ellipsoid normal*, which does not pass
through the centre `O` except on the equator and at the poles. Rather than build a second
construction, the ellipsoid is replaced near the launch point by its **osculating sphere in the
flight-plane azimuth `χ`** — the sphere tangent at `O*` whose normal curvature matches the
ellipsoid's in that one direction. Euler/Meusnier:

```
M(φ)      = a_e*(1 - e2) / (1 - e2*sin²φ)^(3/2)      # meridional radius of curvature [m]
N(φ)      = a_e / sqrt(1 - e2*sin²φ)                 # prime-vertical radius of curvature [m]
R_chi     = 1 / (cos²χ / M(φ0) + sin²χ / N(φ0))      # normal curvature radius along heading χ [m]
phi       = y[X] / R_chi                             # same arc-length reading as §23.1
z_hat_g   = (-sin(phi), cos(phi))                    # eq:zhat_g_rotated, unchanged
```

`a_e` and `e2` are **the constants already in `sim/gravity.py`**: `_WGS84_A = 6378137.0` and
`_WGS84_E2 = 0.00669437999013`, defined for `_g_wgs84`. Do not introduce a second copy — the same
reason §23.3 computes `_EPSILON` from `_R_D/_R_V` instead of hard-coding `0.622`: two copies of one
constant are a drift hazard.

**`φ₀` and `χ` reuse `lat0_deg` and `azimuth_deg` — no new `Params` fields.** This is not a
convenience, it is a correctness requirement:

- `lat0_deg` is already documented and used as *the launch site's geodetic latitude on the WGS84
  ellipsoid* — it is the `φ` of Somigliana's formula in `_g_wgs84`, on the same ellipsoid, with the
  same `a_e`, `e2`. `M(φ₀)`/`N(φ₀)` need exactly that quantity. Supplying the magnitude and the
  direction of one ellipsoid's gravity with two different latitudes would be incoherent.
- `azimuth_deg` is already documented as "direction of +x, degrees clockwise from North" — exactly
  the heading `χ` of `models.tex` (§Atmosphere > Field's ground track `(x sin χ, x cos χ)`, §Wind's
  flight-plane projection, and `sim/rotation.py`'s `Ω` decomposition all read it as that). There is
  one flight plane; it has one heading.
- The hypothetical "a user might want a Coriolis latitude different from the ellipsoid latitude" is
  not a real distinction: both are *the launch site's latitude*, and there is one launch site. A
  separate field would create a second source of truth for one physical quantity.

**Structure — a third value in the existing dispatch dict, plus a radius seam.** `sim/gravity.py`:

```python
def _R_chi(p) -> float:
    """Osculating-sphere radius in the flight-plane azimuth (Euler/Meusnier),
    models.tex SSGravity > Direction, "Construction (elliptical)"."""
    phi0 = np.radians(p.lat0_deg)
    chi = np.radians(p.azimuth_deg)
    s2 = np.sin(phi0) ** 2
    M = _WGS84_A * (1.0 - _WGS84_E2) / (1.0 - _WGS84_E2 * s2) ** 1.5
    N = _WGS84_A / np.sqrt(1.0 - _WGS84_E2 * s2)
    return float(1.0 / (np.cos(chi) ** 2 / M + np.sin(chi) ** 2 / N))


# Curvature radius of the ground/vertical construction, per direction model.
# `None` == flat: the launch-point tangent plane, no curvature at all.
# Same dispatch-dict convention as _GRAVITY_MODELS/_GRAVITY_DIRECTIONS, so an
# unknown gravity_direction raises KeyError here too (architecture.md SS7).
_CURVATURE_RADII = {
    "parallel":   lambda p: None,
    "radial":     lambda p: p.R_e,
    "elliptical": _R_chi,
}


def curvature_radius(p) -> "float | None":
    """Radius of the sphere the local vertical (and, from Step 42, the ground)
    is constructed on. `None` for the flat "parallel" model."""
    return _CURVATURE_RADII[p.gravity_direction](p)


def _dir_curved(t, y, p) -> np.ndarray:
    """z_hat_g rotated with downrange distance, on a sphere of radius
    curvature_radius(p) -- models.tex eq:zhat_g_rotated with phi = x/R."""
    phi = y[X] / curvature_radius(p)
    return np.array([-np.sin(phi), np.cos(phi)])


_GRAVITY_DIRECTIONS = {
    "parallel":   _dir_parallel,
    "radial":     _dir_curved,     # was _dir_radial
    "elliptical": _dir_curved,
}
```

`_dir_radial` is replaced by `_dir_curved` rather than duplicated: for `"radial"`,
`curvature_radius(p)` returns `p.R_e` unchanged, so `phi = y[X] / p.R_e` is the **same expression
with the same operands**, hence bit-for-bit identical to Step 38's body. Keeping two near-identical
functions would be the shallower structure and would let the two drift.

**Bit-for-bit.** `"parallel"` never reaches any of the new code (`_dir_parallel` is untouched and
still returns `np.array([0.0, 1.0])`). `"radial"` evaluates `y[X] / p.R_e` exactly as before — one
extra dict lookup and one extra call, zero arithmetic difference. Both existing variants stay
byte-identical; this is a check the step must assert, not assume.

**Pinned numbers** (recompute independently before trusting them — the §23.3 precedent):

| `φ₀` | `χ` | `R_χ` [m] | vs `R_e = 6371000` |
|---|---|---|---|
| 0° | 0° (due N) | 6335439.3273 = `M(0)` | −35560.7 |
| 0° | 90° (due E) | 6378137.0000 = `N(0)` = `a_e` | +7137.0 |
| 50° | 0° | 6372955.9257 | +1955.9 (+0.031 %) |
| 50° | 45° | 6381816.6482 | +10816.6 (+0.170 %) |
| 50° | 90° | 6390702.0442 | +19702.0 (+0.309 %) |
| 90° | any | 6399593.6258 | +28593.6 |

Also: `M(50°) = 6372955.9257`, `N(50°) = 6390702.0442` — i.e. at `χ = 0` the answer *is* `M(φ₀)` and
at `χ = 90°` it *is* `N(φ₀)`, exactly, which is the cheapest correctness check available. At the
pole `M = N`, so `R_χ` is azimuth-independent — also exact, also a test.

Effect size, `φ₀ = 50°, χ = 90°`, elliptical vs radial at the same state: `Δφ = x·(1/R_e − 1/R_χ)`
is `4.839e-6 rad` at `x = 10 km` (`|Δẑ_g| = 4.839e-6`), and the downrange gravity component
`−g·sin φ` goes from `−1.539263e-2` to `−1.534518e-2 m/s²` — a 0.31 % refinement of a term that is
itself small. This is a fidelity option, not a correction anyone's trajectory needs; say so in the
docstring.

**`p.R_e` is not read by the elliptical direction.** With `gravity_direction="elliptical"` the
direction model ignores `R_e` entirely; `gravity_model="radial"`'s *magnitude* still uses it (the
two dispatches stay orthogonal, §23.1). Pin this in a test: sweeping `R_e` must not move an
`elliptical`-direction result, and sweeping `lat0_deg`/`azimuth_deg` must not move a `radial`-
direction one.

**Scope — what this step does NOT do.**

- No curved ground and no curved-ground altitude. That is Step 42; §24.2's scope list applies here
  too, unchanged.
- No third-order ellipsoid fidelity. The osculating sphere is exact at `O*` and correct to second
  order in `φ`; it departs at third order because the true geodetic latitude drifts downrange while
  `R_χ(φ₀,χ)` is frozen at the launch site. `models.tex` states this explicitly as "a refinement not
  carried here". Do not add a `φ(x)` update.
- No coupling to Coriolis, exactly as §23.1: `sim/rotation.py` keeps its launch-site-fixed `Ω`.
- No caching of `R_χ`. It is ~10 flops per RHS call, recomputed like `_g_wgs84`'s Somigliana
  constants already are (§15 "Performance note ... do not optimise"). A cache keyed on `Params`
  would need `Params` to be hashable across every field; it is not worth it.
- Zero effect on the rotational equation, for the same exact reason as §23.1 (weight acts at the
  CoG). `domega/dt` delta must be exactly `0.0`, not approximately.

**Checks for the step.** `"parallel"` and `"radial"` both reproduce every prior `derivatives()`
result bit-for-bit (`np.array_equal`, the `earth_rotation` test's pattern). `R_χ(φ₀, 0°) == M(φ₀)`
and `R_χ(φ₀, 90°) == N(φ₀)` to floating-point equality, at several latitudes. `R_χ(90°, χ)` is
independent of `χ`. `‖z_hat_g‖ = 1` and `z_hat_g(x=0) == (0.0, 1.0)` exactly, for `"elliptical"`.
`elliptical` and `radial` differ by the pinned `Δφ` above at `φ₀=50, χ=90, x=10 km`. `domega/dt`
delta vs `"parallel"` is exactly `0.0`. Sweeping `p.R_e` leaves an `"elliptical"` run unchanged.
An unknown `gravity_direction` string raises `KeyError` (no silent flat fallback).

### 24.2 Step 42 — curved-ground impact condition (`h_true`)

Spec: `latex/sections-ai/models.tex` §Gravity > Direction, paragraph **"Ground and impact
condition"**, eq. `h_true` (and eq. `surface_point`, which it is derived from). This is the
"curved ground" remainder that roadmap Backlog **B4** explicitly left behind when Step 38 was
promoted out of it.

**Model.** The rocket is at `O*R = x·x̂₀ + z·ẑ₀`; the ground point at the *same* downrange arc angle
is `O*P(φ) = R sin φ·x̂₀ + R(1−cos φ)·ẑ₀`. Projecting the offset onto the local up `−ẑ_g(φ)`:

```
phi    = x / R                                      # R = curvature_radius(p), 24.1
h_true = x*sin(phi) - z*cos(phi) - R*(1 - cos(phi))     # models.tex eq:h_true, up-positive
```

Small-`φ` reading: `h_true = x²/2R − z + O(x⁴/R³)` — larger than the flat `−z` by exactly the
curvature drop, because the ground has fallen away beneath a rocket that has not.

**The event must not be `h_true` itself. Use its negation, "depth below ground".** This is the one
place in this phase where a sign slip is silent and costly. Today:

```python
_ground_event.terminal  = True
_ground_event.direction = 1   # z increasing through 0 == falling (z is down-positive)
```

`y[Z]` is *down*-positive and rises through zero at impact. `h_true` is *up*-positive and falls
through zero at impact. Substituting `h_true` for `y[Z]` while leaving `direction = 1` in place
would make `solve_ivp` look for the rocket *leaving* the ground upward and never terminate the run —
and, worse, it would still "work" on any scenario that happens to start below ground. Both
`terminal` and `direction` are attributes on the module-level function object, so they cannot be
varied per-`Params` without global mutation. The fix is to keep the event's sign convention and
change only what fills it:

```python
# sim/gravity.py
def ground_depth(t: float, y: np.ndarray, p) -> float:
    """Signed depth of the rocket below the ground surface, DOWN-positive --
    the curved-ground generalisation of `y[Z]` (models.tex SSGravity >
    Direction, eq:h_true, negated). Negative in flight, zero at impact,
    increasing through zero as the rocket descends, for every direction
    model -- so `integrate._ground_event` keeps `direction = 1`,
    `terminal = True` unchanged.
    """
    R = curvature_radius(p)
    if R is None:                 # "parallel": flat launch-point tangent plane
        return y[Z]               # returned unchanged -- bit-for-bit, see below
    phi = y[X] / R
    return y[Z] * np.cos(phi) - y[X] * np.sin(phi) + R * (1.0 - np.cos(phi))
```

```python
# sim/integrate.py
def _ground_event(t, y, p):
    if t < 0.1:                   # unchanged t=0 guard
        return 1.0
    return gravity.ground_depth(t, y, p)

_ground_event.terminal = True     # unchanged
_ground_event.direction = 1       # unchanged
```

and in `_run_rk4`, the manual crossing detection becomes the same substitution, nothing more:

```python
d_now  = gravity.ground_depth(t, y, p)            # hoist above the step if desired
d_next = gravity.ground_depth(t_next, y_next, p)
if t_next >= 0.1 and d_now < 0.0 <= d_next:
    frac = -d_now / (d_next - d_now)
    t_ground = t + frac * dt_step
    y_ground = y + frac * (y_next - y)
    ...
```

**Why `ground_depth` lives in `gravity.py` and not in `integrate.py` or a new `sim/ground.py`.** It
is derived from, and shares `R` with, the direction construction — `models.tex` puts it inside
§Gravity > Direction for exactly that reason. Putting the geometry in `integrate.py` would make the
integrator know about ellipsoids; a new 15-line `sim/ground.py` would be a shallow module whose only
content is one formula plus an import of `gravity.curvature_radius`. `integrate.py` asks one
question ("how far below the ground am I?") and gets one number: that is the deep-module seam.

**Bit-for-bit, worked out rather than asserted.** For `"parallel"`, `curvature_radius(p)` returns
`None` and `ground_depth` returns the *same object* `y[Z]` — not a recomputation of it. The RK45
event function therefore returns bitwise what it returned before, so `solve_ivp`'s Brent root-find
sees the identical function and produces the identical `t_events[0]`; and `_run_rk4`'s comparison
`d_now < 0.0 <= d_next` with `frac = -d_now/(d_next - d_now)` is the identical arithmetic on the
identical operands. Nothing else in either path is touched.

**The explicit `parallel` branch is mandatory, not stylistic — the limit does not save you.**
`h_true → −z` only as `R → ∞`. At the code's finite `p.R_e = 6371000.0` the formula gives, at
`z = 0`:

| `x` | `h_true(x, 0)` with `R_e` | i.e. the flat `z = 0` plane sits this far above the curved ground |
|---|---|---|
| 1 km | +0.078481 m | |
| 4.6 km | +1.660650 m | |
| 10 km | +7.848057 m | |
| 30 km | +70.632162 m | |

So evaluating the curved formula under `"parallel"` would move the impact event by
`x²/2R_e` of altitude at every nonzero `x`. It happens to be exactly harmless for `run.py`'s default
scenario — that launch is vertical, `x ≡ 0`, and `h_true(0, z) = 0·0 − z·1 − R(1−1) = −z` bitwise —
but it is *not* harmless for any tilted scenario (Step 5 onwards), where at a 4.6 km downrange
impact the event value would be off by 1.661 m, shifting the impact time by ~0.02 s at a 80 m/s
descent rate. Never rely on `R → ∞`; also note that passing `float("inf")` as the radius produces
`inf * 0.0 = nan` in the `R*(1 − cos φ)` term, so the "just use a huge R" shortcut is actively
broken. Branch on `R is None`.

**`_apogee_event` is deliberately NOT touched.** Apogee stays `y[VZ] = 0`, `direction = 1`,
`terminal = False`. With a curved ground the maximum of `h_true` is not the top of the launch-frame
trajectory: differentiating along the path,

```
dh_true/dt = (x*cos(phi) + z*sin(phi))/R * vx  -  cos(phi) * vz
```

which at `vx = 300 m/s`, `x = 10 km`, `R = R_e` is `+0.47 m/s` where `vz = 0`, so the two definitions
of apogee differ by ~0.05 s of flight time and a second-order (i.e. negligible) amount of altitude.
"Apogee" in this simulator means the top of the trajectory in the launch frame — that is what is
plotted, what `run.py` reports, and what every existing test asserts. Changing it would be a
separate, arguable modelling decision, and mixing it into a step about the *ground* is exactly how
the apogee/impact event pair gets silently broken. Leave it, and say so in the docstring.

**Scope — what this step does NOT do, and the recommendation behind it.**

`models.tex` eq. `h_true`'s own prose says `h_true` "is the altitude to use, in place of `−z`, for
every altitude-dependent model once a non-parallel direction model is active — the atmosphere and
wind tiers, and the radial/WGS84 magnitude models". **This step deliberately implements only the
impact/ground event, and leaves the altitude-model swap to a separate later step.** The
recommendation, with its reasons:

1. **It is where nearly all the physics is.** The ground-drop term changes the *answer the simulator
   reports* — impact range and time — at first order: at a flat-reading impact 4.6 km downrange
   descending at 60°, the ground has dropped 1.661 m and the rocket flies ~0.96 m further; at 10 km
   and 45°, 7.848 m of drop gives ~7.85 m of extra range. Feeding the same `+7.85 m` at 10 km into
   the *altitude* lookups instead changes ISA density by ≈ `7.85/8500 ≈ 0.09 %` and radial `g` by
   `2·7.85/6.371e6 ≈ 2.4e-6` relative — both far below the atmosphere model's own error, the same
   threshold §23.3 used to leave `a` and `μ` dry and §13 used to reject EGM2008.
2. **It would break an architectural invariant.** `flow.altitude_agl(y)` takes no `Params`; giving
   it one is a signature change rippling through `gravity.py`, `atmosphere.py`, `wind.py`,
   `soundings.py` and most of the test suite. Worse, `_g_radial`/`_g_wgs84` would then read
   `p.gravity_direction` to compute a *magnitude* — collapsing the magnitude/direction orthogonality
   that §23.1 was specifically designed to establish, and making `gravity_model="radial"` +
   `gravity_direction="elliptical"` a combination whose `h` depends on the ellipsoid while its `g`
   does not.
3. **Blast radius vs. reviewability.** The event change is ~15 lines in two functions with an exact
   bit-for-bit argument. The altitude swap is a cross-cutting refactor of the project's most-called
   helper; it deserves its own step, its own regression sweep, and its own decision about whether
   `altitude_msl` follows suit.

Recorded as a new backlog item (roadmap **B8**, "`h_true` for the altitude-dependent models"). Also
explicitly not in this step: any change to `_apogee_event` or `_burnout_event`; any change to
plotting or to `run.py`'s reported "apogee altitude" (still `−z`); and any notion of terrain — the
"ground" here is the smooth reference surface, nothing else.

**Checks for the step.** `gravity_direction="parallel"`: a full `run_sim` on both integrator paths
reproduces the pre-Step-42 `events["ground"]`, `events["apogee"]`, `t` and `y` arrays bit-for-bit,
including a *tilted* scenario with `x ≠ 0` at impact (the vertical default would pass even with the
bug — say so in the test's docstring). `ground_depth(t, y, p) is y[Z]`-equal for parallel at
arbitrary `x`, `z`. For `"radial"`/`"elliptical"`: `ground_depth` is exactly `z` when `x = 0.0`
(`cos 0 = 1`, `sin 0 = 0`, `R(1−1) = 0` — bitwise); `ground_depth(x, 0, p)` equals the pinned
`−h_true` values above (`−0.078481`, `−1.660650`, `−7.848057`, `−70.632162` m at 1/4.6/10/30 km with
`R_e`); `−h_true` matches `−(x²/2R − z)` to the pinned residuals (`−6.164e-3 m` at `x = 10 km,
z = −5000`, `−0.664 m` at `x = 100 km` — the exact-vs-small-angle gap, which is itself the check
that the *exact* form was implemented, not the approximation). `_ground_event.direction == 1` and
`_ground_event.terminal is True` asserted directly as attributes (a regression guard on the one
mistake this step invites). A tilted `"radial"` run impacts **later and further downrange** than the
same tilted `"parallel"` run — sign check on the whole chain, not just the formula. `"radial"` and
`"elliptical"` give different impact points at the same `lat0_deg`/`azimuth_deg`. RK4 and RK45 agree
on the curved impact time to grid resolution (the Step 8 cross-check, extended to the new event).

### 24.3 Step 43 — lateral offsets `u_B`, `u_C`

Spec: `latex/sections-ai/analysis.tex` eq. `moment_full` and §Moment's term-by-term reading;
`latex/sections-ai/rocket-2d.tex` §Geometry (eqs. for `AB`, `AC`, `AD`, and the `u_D ≡ 0` rule).
Completes eq. `moment_full` — §23.2 recorded its `(u_B−u_C)T cos δ` term as "derived but with no
code path", and status.json carries the same as a flagged item.

**What is already implemented, verified against the actual code.** `sim/dynamics.py` builds two
body-frame position vectors and crosses each with its force via

```python
def _cross_y(a, b):
    a_x, a_z = a
    b_x, b_z = b
    return -(a_x * b_z - a_z * b_x)
```

```python
aA = np.array([-l1_aero, 0.0])          # CoG -> aerodynamic reference point D  (= BD)
aB = np.array([-(p.l1 + p.l2), 0.0])    # CoG -> thrust application point C     (= BC)
M_y = _cross_y(aB, thrust) + _cross_y(aA, aero_force) + aero_moment_y(t, y, p)
```

Mapping to the LaTeX's point labels: the code's `l1 = l_D − l_B` and `l1 + l2 = l_C − l_B` (both
positive, both nose-tip-referenced — the bridge documented in the Phase 2.5 finalization pass), so
`aA` is `BD` and `aB` is `BC`. Both currently carry an **implicit zero lateral component** — that
`0.0` in the second slot is precisely `u_B = u_C = 0`.

**What the geometry actually says.** From `rocket-2d.tex` §Geometry, `AB = −l_B x̂_r − u_B ẑ_r`,
`AC = −l_C x̂_r − u_C ẑ_r`, `AD = −l_D x̂_r` (with `u_D ≡ 0`):

```
BD = AD - AB = (l_B - l_D)*x_hat_r + u_B*z_hat_r          ->  aA = (-l1,          +u_B      )
BC = AC - AB = (l_B - l_C)*x_hat_r + (u_B - u_C)*z_hat_r  ->  aB = (-(l1+l2),  u_B - u_C    )
```

**The diff is two array literals.** `sim/dynamics.py`, inside `derivatives()`, nothing else:

```python
aA = np.array([-l1_aero, p.u_B])                     # was  [-l1_aero, 0.0]
aB = np.array([-(p.l1 + p.l2), p.u_B - p.u_C])       # was  [-(p.l1 + p.l2), 0.0]
```

**Verification that this produces eq. `moment_full` exactly** — do the algebra, do not trust the
shape. With `thrust = (T cos δ, T sin δ)` (Step 39) and `aero_force = (−A_x, −A_z)`:

```
M_thrust = _cross_y(aB, thrust)
         = -[ (-(l1+l2)) * (T sin d)  -  (u_B - u_C) * (T cos d) ]
         =  (l1 + l2)*T*sin(d)  +  (u_B - u_C)*T*cos(d)
         =  (l_C - l_B)*T*sin(d) + (u_B - u_C)*T*cos(d)          <- eq:moment_full terms 2 and 1

M_aero   = _cross_y(aA, aero_force)
         = -[ (-l1) * (-A_z)  -  u_B * (-A_x) ]
         = -l1*A_z - u_B*A_x
         =  (l_B - l_D)*A_z - u_B*A_x                            <- eq:moment_full terms 4 and 3

M_moment = aero_moment_y(...) = -A_m                             <- eq:moment_full term 5
```

Summing gives `I θ̈ = (u_B−u_C)T cos δ + (l_C−l_B)T sin δ − u_B A_x + (l_B−l_D)A_z − A_m`, which is
eq. `moment_full` term for term, with no rearrangement. Note that the two missing terms land in
*different* cross products — `(u_B−u_C)T cos δ` in `aB`'s and `−u_B A_x` in `aA`'s — which is why
both literals change and why `u_B` appears twice with different companions. Getting `aA`'s lateral
component wrong (e.g. `u_B − u_D` with a spurious `u_D`, or the opposite sign) is the realistic
failure mode; `u_D ≡ 0` by definition in `rocket-2d.tex` §Geometry, and the sign follows from
`BD = AD − AB` with `AB` carrying `−u_B ẑ_r`.

**Bit-for-bit.** With the defaults `u_B = u_C = 0.0`: `np.array([-l1_aero, p.u_B])` constructs the
element `0.0`, and `p.u_B - p.u_C` evaluates `0.0 - 0.0 == +0.0` exactly under IEEE
round-to-nearest. Both arrays are therefore **bitwise identical** to the literals they replace, so
`_cross_y` is fed identical operands and `M_y` is identical, not merely equal. (Pathological case
for completeness: `u_B = -0.0` gives `aA[1] = -0.0` and `-0.0 - 0.0 = -0.0`; `_cross_y` then
computes `a_z * b_x = ∓0.0` and `a_x*b_z − (∓0.0)`, which is exact for any finite `a_x*b_z`, so the
result is unchanged there too.) No new branch, no gate flag — same pattern as `A_e = 0.0` and
`thrust_misalign_deg = 0.0`.

**`Params`:**

```python
# Step 43: lateral (off-axis) offsets of the CoG (B) and the thrust point (C)
# from the body axis, measured along +z_hat_r (towards the belly), metres.
# rocket-2d.tex SSGeometry: AB = -l_B*x_hat_r - u_B*z_hat_r, likewise AC with
# u_C; u_D == 0 by definition. As-built manufacturing quantities to be swept,
# not functions of the flight state -- the same standing as
# thrust_misalign_deg. 0.0 (the default) recovers the on-axis geometry
# bit-for-bit.
u_B: float = 0.0   # lateral offset of the centre of gravity [m]
u_C: float = 0.0   # lateral offset of the thrust application point [m]
```

Names match the LaTeX symbols exactly. Unlike `l1`/`l2` — which are code spellings of `l_D − l_B`
and `l_C − l_D` and therefore *cannot* be named after LaTeX symbols — `u_B`/`u_C` are the LaTeX
quantities themselves, with no legacy code name to collide with. Sign convention: **positive is
towards `+ẑ_r`**, i.e. towards the belly, matching `models.tex`/`rocket-2d.tex` and the same
direction a positive `δ` pushes the nozzle exhaust.

**Physical readings worth putting in the tests** (all at the project's standard fixture:
`l1=0.3, l2=0.4, S=0.005, d_ref=0.08, I=0.05`, placeholder motor peak `T = 150 N`):

- The two thrust terms combine into a single closed form,
  `T[(u_B−u_C)cos δ + (l_C−l_B) sin δ] = T·√((u_B−u_C)² + (l_C−l_B)²)·sin(δ + atan2(u_B−u_C, l_C−l_B))`
  — verified to `1.1e-16` at `u_B−u_C = 1 mm, δ = 0.2°`. So a lateral offset is **exactly** a cant
  offset in its effect on the thrust moment: `1 mm` of offset over the `l_C−l_B = 0.7 m` arm is
  equivalent to `δ_eq = atan(0.001/0.7) = 0.08185°`, producing `0.150 N·m` at `T = 150 N` against
  the `0.3665 N·m` a `δ = 0.2°` cant produces. An excellent exactness test, and the reason no new
  trim-angle derivation is needed: eq. `alpha_trim` holds with `M_δ` replaced by the combined term.
- `−u_B A_x` is **the only aerodynamic pitching moment that survives `α = 0`**. At `α = 0` the
  normal force `A_z` and (for a body of revolution) `A_m` both vanish, so with `u_B = 1 mm` and
  `A_x = 0.5 N` the airframe carries a constant `−5.0e-4 N·m`. Unlike `M_δ` this one does *not*
  vanish at burnout — it scales with `q`, so it is largest at max-Q and is the only term of
  eq. `moment_full` that is aerodynamic *and* independent of `α`. Test it directly at `α = 0`.

**Scope — what this step does NOT do.**

- **No effect on the translational equation.** `u_B`/`u_C` are moment arms only; `weight_inertial`,
  `thrust_body` and `aero_force_body` are untouched, so `dvx/dt`, `dvz/dt` and `dm/dt` change only
  through the trajectory `ω` subsequently takes. Assert this at `t = 0` (identical
  `dydt[VX], dydt[VZ], dydt[M]`, different `dydt[OMEGA]`).
- **`u_B` does NOT feed the moment of inertia or the variable-mass model.** `_moment_of_inertia`'s
  parallel-axis terms use axial distances only, and the two-lumped-mass model (`l_d`, `l_p`) has no
  lateral coordinates to derive a `u_B(t)` from. `p.I`/`I(t)` are taken as given about the actual
  CoG. This is the exact precedent Step 36 set for `l1`/`l2` ("main.tex gives a formula for `l_B(t)`
  and `I(t)` only"), and inventing `u_d`/`u_p` would be unstated physics.
- **`u_B` is constant, not `u_B(t)`.** Same reasoning; `rocket-2d.tex` §Geometry calls both "ordinary
  constants ... in principle obtained from manufacturing metrology".
- **No lateral offset for `D`.** `u_D ≡ 0` by definition (`rocket-2d.tex` §Geometry: "any asymmetry
  in the external surfaces instead shows up in the aerodynamic coefficients themselves"). Do not add
  a `u_D` field.
- No interaction with Step 25's CoP travel beyond what already exists: `aA`'s *axial* component
  stays `aero.cop_l1(...)` and `aB`'s stays the constant `p.l1 + p.l2` (§23.2's reasoning: the
  nozzle does not move because the CoP does). The lateral components are constants on both.

**Checks for the step.** `u_B = u_C = 0.0` reproduces every prior `derivatives()` result bit-for-bit
(`np.array_equal`), including with a table-driven CoP and with `thrust_misalign_deg ≠ 0`. `M_y`
shifts by exactly `(u_B − u_C)·T·cos δ − u_B·A_x` relative to the zero-offset case at the same state
— evaluate both and difference them, do not re-derive `M_y` in the test. The closed form
`T√((u_B−u_C)²+(l_C−l_B)²) sin(δ + atan2(u_B−u_C, l_C−l_B))` reproduces `M_thrust` exactly. With
`u_B = u_C ≠ 0` the thrust term is exactly zero (only the *difference* matters for thrust — a
rocket whose CoG and nozzle are offset by the same amount has no thrust-induced moment from it)
while the `−u_B A_x` term is not: that asymmetry between the two fields is the sharpest available
test that they were not conflated. At `α = 0`, `T = 0`: `M_y == −u_B·A_x` exactly, the only
surviving term. `dydt[VX]`, `dydt[VZ]`, `dydt[M]` are unchanged by either field. A statically stable
airframe with `u_B ≠ 0` trims at a small nonzero `α` rather than diverging (eq. `alpha_trim` with
the combined term), and negating both offsets mirrors it.

### 24.4 Step 44 — pitch-damping `c_mq` scaffold

Spec: `latex/sections-ai/analysis.tex` §Dynamic stability (`sec:analysis_dynamic`) — the
coefficient expansion `c_m = c_{m,0} + α c_{m,α} + q̂ c_{m,q}` with `q̂ = ω d_ref/(2V)`, and the
resulting damping term. Narrows `main.tex` §Backlog's "dynamic stability analysis" item.

**This is a scaffold and nothing more.** The user has no value or model for `c_mq`; the step exists
so that the term has a place to be, inert by default, and so that the next person with a number can
supply it without touching `dynamics.py`. Same shape as `A_e = 0.0` and `thrust_misalign_deg = 0.0`:
a zero default, no separate on/off flag.

#### Sign of `c_mq` — a real inconsistency in the spec, resolved

`analysis.tex` §Dynamic stability states, in two linked places, that a conventional aft-finned
statically stable airframe has `c_mq < 0` ("positive `C_m` is a nose-up moment"), and defines
`M_q ≡ −qSd_ref²c_mq/(2VI)` as "positive precisely when `c_mq < 0`", feeding an oscillator
`α̈ + M_q α̇ − M_α α = 0`. **Both statements are written in the standard aerospace convention, which
is inverted relative to this document's own.** Three independent confirmations:

1. **The document's own `A_m` sign.** `rocket-2d.tex` eq. for `A_m` is `−A_m ŷ_r`, eq. `eom_rot`
   carries it as `− A_m`, and `A_m = q c_m S d_ref`. So a **positive `c_m` is a nose-DOWN moment**
   here. This is a closed, recorded decision (status.json, 2026-09-19: "positive `A_m` pitches nose
   down (restoring moment)"). The parenthetical in §Dynamic stability contradicts it.
2. **`c_mα` already has the flipped sign here, for the same reason.** eq. `dtheta_dalpha` is
   `(qS/I)[(l_B−l_D)c_zα − c_mα d_ref]` and must be negative for stability; with `c_zα > 0` and
   `l_B−l_D < 0`, the second term requires **`c_mα > 0`**, the opposite of the textbook's
   `C_mα < 0`. `c_mq` inherits exactly the same flip, and §Dynamic stability applied it to `c_mα`
   (implicitly, via eq. `static_margin`) but not to `c_mq`.
3. **Derived from scratch in this document's frame.** `x̂_r` forward, `ẑ_r` towards the belly,
   `x̂_r × ẑ_r = −ŷ_r`, and from eq. `body_axes_in_ground`, `dx̂_r/dt = −ω ẑ_r`, so `Ω = ω ŷ_r`. A
   point `r = −l x̂_r` (distance `l` aft of the CoG) has velocity `Ω × r = +ω l ẑ_r`, so its velocity
   *through the air* is `(u, w + ωl)` and its local angle of attack is `α + ωl/V`. (`analysis.tex`'s
   prose sketch writes `Δα_i ≈ −ω l_i/V`; that sign is slipped too, though its conclusion —
   "damping" — is right.) Substituting the increased local `α` into the code's own verified
   `M_aero = −l1·qS·C_Nα·sin α` gives `ΔM_y = −l1²qS C_Nα ω / V`, i.e. **negative `M_y` for positive
   `ω`: a nose-down moment opposing a nose-up rate, which is damping**. Matching that against the
   `c_mq` route, `ΔM_y = −qS d_ref q̂ c_mq = −(qSd_ref²/2V)c_mq ω`, gives

   ```
   c_mq = 2 * C_N_alpha * (l1 / d_ref)**2        > 0
   ```

   the single-lifting-surface "strip" estimate, **positive**. Sanity: a realistic 1.5-caliber static
   margin with `C_Nα = 2.0` gives `c_mq = 2·2·1.5² = 9`, the right order of magnitude for a
   published `|C_mq|` of 5-20. At this project's own test fixture (`l1 = 0.3, d_ref = 0.08`,
   `C_Nα = 2.0`) it gives `c_mq = 56.25`, large only because that fixture's 3.75-caliber margin is.

**Resolution for the code: in this simulator, `c_mq > 0` is damping, `c_mq < 0` is anti-damping.**
State it in `aero.py`'s docstring and in `Params`, exactly as the `c_mα > 0`-is-stable flip is
already lived with. **The implementation formula is unaffected** — `c_m += q̂ c_mq` inside the
existing `A_m = qS d_ref c_m` and `M_y += −A_m` is a correct mechanical transcription either way.
Only the *documented physical sign of a real value*, and hence the sign in the damping test, depend
on this. That is why it must be settled before the tests are written.

**Suggested LaTeX fix (documentation, not this step's code):** keep the printed
`α̈ + M_q α̇ − M_α α = 0` and `ζ = M_q/(2ω_n)` by redefining `M_q ≡ +qSd_ref²c_mq/(2VI)`, so
`M_q > 0 ⟺ c_mq > 0 ⟺ damped`; and replace "has `c_{m,q}<0`" / "(positive `C_m` is a nose-up
moment)" with the convention actually in force. That is a three-symbol edit confined to
§Dynamic stability. Not done here — it is the user's document and a separate decision.

#### `sim/aero.py` — a fourth coefficient behind the same seam

```python
class _AeroTable(NamedTuple):
    ...                       # M, alpha, C_A, C_N, C_m, l1 unchanged
    C_mq: "np.ndarray | None"   # (n_M, n_alpha), or None when the column is absent

def C_mq(alpha: float, M: float, p) -> float:
    """Pitch-damping derivative (analysis.tex SSDynamic stability:
    c_m = c_m0 + alpha*c_m_alpha + q_hat*c_mq, q_hat = omega*d_ref/(2V)).

    Table-driven when `p.aero_table` is set AND the table has a `c_mq`
    column; otherwise the constant `p.c_mq` (default 0.0 -- inert).
    SIGN: positive c_mq is DAMPING in this document's convention (positive
    C_m is a nose-down moment -- architecture.md SS24.4), the opposite of
    the textbook C_mq < 0. Same flip c_m_alpha already carries.
    """
    if p.aero_table:
        table = _load_table(p.aero_table)
        if table.C_mq is not None:
            return _table_lookup(table, alpha, M, table.C_mq)
    return p.c_mq
```

`_load_table` gains, beside the five existing `data[...]` reads:

```python
C_mq_col = data["c_mq"].astype(float) if "c_mq" in data.dtype.names else None
...
C_mq=_reshape(C_mq_col) if C_mq_col is not None else None,
```

— the only place the column's optionality is handled, exactly as §23.3 required of `Td_K`.

**The column is optional, and an absent column falls back to `p.c_mq`.** This is a deliberate,
documented exception to `aero.py`'s existing "a table wins completely, constants are the no-table
fallback" rule, and it needs stating because it is the one surprising line in the module:

- Every committed table (`data/aero/example.csv`) predates the column, so "absent ⇒ inert" must
  hold — that part is not optional, it is the bit-for-bit requirement.
- The remaining choice is whether absent means *literal 0.0* or *`p.c_mq`*. `p.c_mq` is recommended:
  `c_mq` is a scaffold whose entire purpose is to be experimented with before anyone has table data,
  and forcing a user to regenerate a full `(M, α)` grid just to try a single constant damping value
  defeats the point. With the `0.0` default the two behave identically for every existing file, so
  the exception costs nothing today.
- Column name `c_mq`, lowercase, matching the LaTeX symbol `c_{m,q}` and distinguishable from the
  existing capitalised `C_A`/`C_N`/`C_m` — which is itself a small inconsistency; `C_mq` is the
  alternative if matching the file's existing capitalisation matters more than matching the symbol.
  Column *order* is irrelevant (`genfromtxt(..., names=True)` is keyed by header name).

#### `sim/forces.py` — where the term enters

`aero_moment_y` already computes `A_m = q·S·d_ref·C_m(α, M, p)` in the `"coefficients"` regime and
returns `−A_m`; the damping term is an addition to `c_m`, so it is an addition to `A_m`:

```python
from sim.state import M, OMEGA          # OMEGA is new here

    elif p.aero_model == "coefficients":
        A_m = flow.q * p.S * p.d_ref * aero.C_m(flow.alpha, flow.M, p)
        # Pitch damping (analysis.tex SSDynamic stability; architecture.md
        # SS24.4). The spec's form is c_m += q_hat*c_mq with
        # q_hat = omega*d_ref/(2V), giving A_m += q*S*d_ref*q_hat*c_mq.
        # Written division-free below, algebraically identically:
        #     q*d_ref*q_hat = (rho*V^2/2)*d_ref*(omega*d_ref/(2V))
        #                   = rho*V*omega*d_ref^2/4
        # -- see the note on V = 0 in SS24.4.
        A_m += 0.25 * flow.air.rho * flow.V * p.S * p.d_ref**2 * s[OMEGA] \
               * aero.C_mq(flow.alpha, flow.M, p)
```

`d_ref` is **reused, not duplicated** — `Params.d_ref` already exists as the aerodynamic reference
diameter and is already the length in `A_m = qS·d_ref·C_m`, which is exactly the `d_ref` of
`q̂ = ω d_ref/(2V)`. (`Params.l_ref` is a *different* reference length, used only for the Reynolds
number in `flow.py`; do not use it here.) `ω` comes from the state, `s[OMEGA]`, not from a
derivative. `V` and `ρ` come from the `flow_state` call `aero_moment_y` already makes.

**Why division-free, and not `q_hat = omega*d_ref/(2*V)` with a `V > 0` guard.** The singularity at
`V = 0` is *removable* — `q ∝ V²` kills the `1/V` — so the damping moment itself is perfectly smooth
through `V = 0` and tends to zero there. But the naive two-step form is not numerically smooth: for
a denormal `V` (say `1e-300`), `q = 0.5ρV²` underflows to exactly `0.0` while `q_hat` overflows to
`inf`, and `0.0 * inf = nan` — which kills the solver. This is not hypothetical: an unperturbed
vertical flight coasts through `V ≈ 0` at apogee on every run, and `aero.py`'s module docstring
already records one solver failure from exactly that neighbourhood (the Step 35 `atan2` branch cut,
which cost a multi-minute step-size collapse). The product `ρ·V·ω·d_ref²/4` has no division, is
exactly `0.0` at `V = 0.0`, and is continuous either side. An epsilon guard would also work but
introduces a (tiny) discontinuity for no benefit. Keep `q̂` in the comment as the conceptual form,
since that is what a real aero table encodes.

**`"constant"` regime untouched.** Damping is added in the `"coefficients"` branch only. The
`"constant"` regime is Phase 1's fixed `A_m = p.A_m` with no `q`, `V` or `ρ` anywhere in it; making
it velocity-dependent would contradict its own definition, and `C_m` is likewise not consulted
there.

**`Params`:**

```python
# Step 44: pitch-damping derivative (analysis.tex SSDynamic stability;
# architecture.md SS24.4). Scaffold only -- 0.0 (the default) makes the
# damping term exactly zero, bit-for-bit every prior step, with no separate
# on/off flag (the A_e/thrust_misalign_deg pattern). SIGN: positive c_mq is
# DAMPING here, because positive C_m is a nose-DOWN moment in this
# document's convention -- the same flip that makes c_m_alpha > 0 the
# statically stable sign. Supplying a real value (measurement, unsteady CFD,
# or the strip estimate 2*C_N_alpha*(l1/d_ref)^2) is future work, not this
# step. Overridden per (alpha, M) by an optional `c_mq` column in
# `aero_table`, when one is present.
c_mq: float = 0.0   # pitch-damping derivative dC_m/d(q_hat) [-]
```

**Bit-for-bit.** With `c_mq = 0.0` and no table column, the added product is `±0.0` and `A_m + 0.0`
is bitwise `A_m` for every finite `A_m` except `A_m = −0.0`, where it becomes `+0.0`. `A_m = −0.0`
is reachable (`C_m = p.C_m_alpha·sin(0.0) = −0.0` whenever `C_m_alpha < 0`, which the standard test
fixtures use). Trace it through: `aero_moment_y` then returns `−0.0` instead of `+0.0`;
`M_y = M_thrust + M_aero + M_moment` is unchanged unless `M_thrust + M_aero` is itself exactly
`−0.0`, and even then `−0.0 + (−0.0) = −0.0` vs `−0.0 + (+0.0) = +0.0` only flips the sign of a zero
`M_y`, giving `domega/dt = ∓0.0` and an integrated state identical in every bit. `np.array_equal`,
which every existing bit-for-bit test uses, compares with `==` and treats `−0.0 == 0.0` as true.
**Conclusion: bit-for-bit under every comparison the suite makes, and observationally identical
under all of them, with the one signed-zero sub-case above spelled out rather than glossed.**

**Pinned numbers** (project fixture `m=0.5, I=0.05, l1=0.3, l2=0.4, S=0.005, d_ref=0.08,
C_N_alpha=2.0, C_m_alpha=0.0`; `ρ = 1.225, V = 100 m/s ⇒ q = 6125 Pa`):

- `M_α = (qS/I)[(l_B−l_D)c_zα] = −367.5 s⁻²`, `ω_n = √(−M_α) = 19.1703 rad/s`, period `0.3278 s`.
- strip estimate `c_mq = 2·C_Nα·(l1/d_ref)² = 56.25`.
- damping rate `D ≡ qS d_ref² c_mq/(2VI) = 1.1025 s⁻¹`, `ζ = D/(2ω_n) = 0.02876`, envelope
  `e^{−Dt/2}` with `τ = 2/D = 1.8141 s`; amplitude falls to `0.8347` of its value over one period.
- damping moment at `ω = 1 rad/s`: `ΔM_y = −0.25·ρ·V·S·d_ref²·ω·c_mq = −5.5125e-2 N·m` (against
  `I = 0.05`, so `Δθ̈ = −1.1025 rad/s²` — sign confirms nose-down for nose-up rate).
- with a more conservative `c_mq = 10`: `D = 0.196 s⁻¹`, `ζ = 0.00511`, `ΔM_y = −9.8e-3 N·m`.

A ~3 % damping ratio is physically right for a finned rocket and is comfortably measurable over the
existing 1-second test runs.

**Scope — what this step does NOT do.**

- **No value for `c_mq`.** The default is `0.0` and the shipped `data/aero/example.csv` gets no
  `c_mq` column. Deriving or measuring one (forced-oscillation tunnel test, unsteady CFD, or a
  distributed strip integration over the real airframe) stays a backlog item (roadmap **B9**). The
  strip formula above is a *test fixture* and an order-of-magnitude sanity check, not a model to
  ship: it assumes the entire normal force acts at one point and ignores the body's own contribution
  and every unsteady effect.
- **No `α̇`/plunge damping (`c_mα̇`).** The standard short-period model has a second damping
  derivative; `analysis.tex` does not derive it and folds the whole thing into `c_mq` via the
  short-period approximation `α̇ ≈ θ̇`. Do not add a second coefficient.
- **No `ω_n`/`ζ` reporting.** `run.py` and `plotting.py` are untouched; computing and printing the
  short-period frequency and damping ratio is a separate (easy, optional) step.
- **No change to `dynamics.py`.** The term reaches `M_y` entirely through `aero_moment_y`'s return
  value, which `dynamics.py` already sums in. Verify this is still true before writing the step —
  it was the Step 39 lesson.
- **No change to `C_m`'s own signature or to the existing four coefficients.**

**Checks for the step.** `c_mq = 0.0`, no column: every prior result bit-for-bit (`np.array_equal`
on `derivatives()`, and a full `run_sim` summary), including with a table configured. An existing
table file with no `c_mq` column loads and runs unchanged; `_AeroTable.C_mq is None` for it. With a
column present, `C_mq(α, M, p)` interpolates it exactly like `C_m` does (bracket-and-clamp in `M`,
`np.interp` in `α`) and ignores `p.c_mq`; with no column, it returns `p.c_mq` regardless of `α, M`.
`A_m` shifts by exactly `0.25·ρ·V·S·d_ref²·ω·c_mq` relative to `c_mq = 0` at the same state
(difference two `aero_moment_y` calls, do not re-derive). The shift is exactly `0.0` at `ω = 0.0`
and at `V = 0.0`, and no `nan`/`inf` appears for a denormal `V` (`V = 1e-300`) — the specific failure
the division-free form exists to prevent; assert `np.isfinite`. The shift is **linear and odd in
`ω`** (negate `ω`, negate the moment) and **independent of `α`** at fixed `(V, ρ, ω)` when `c_mq` is
constant — the `c_mq` analogue of the Step 39 "`δ` does not touch `∂θ̈/∂α`" check. **Sign/behaviour
test, the one that encodes §24.4's resolution:** a statically stable airframe given `c_mq > 0` (use
the strip value `2·C_Nα·(l1/d_ref)² = 56.25`) has its pitch oscillation **decay** — successive `|α|`
peaks strictly decreasing, envelope consistent with `τ = 2/D = 1.81 s` — where `c_mq = 0` gives the
bounded-but-non-decaying oscillation the project has documented since Step 25, and `c_mq < 0` makes
it grow. That triple is the test; getting it backwards is the only real risk in this step.

---

**Summary of §24's open decisions** (each is a naming or scope call, none blocks the physics):
the new `gravity_direction` value name (`"elliptical"` recommended, `"wgs84"` the runner-up but it
collides visually with `gravity_model="wgs84"`); reuse of `lat0_deg`/`azimuth_deg` for `φ₀`/`χ`
(recommended, argued above); Step 42's event-only scope (recommended, argued above); `ground_depth`
living in `gravity.py` (recommended); leaving `_apogee_event` on `vz = 0` (recommended); the
`u_B`/`u_C` field names; the `c_mq` column's absent-means-`p.c_mq` fallback; and — the only one that
is not cosmetic — the `c_mq` sign resolution of §24.4 and the corresponding LaTeX correction.

---

## 25. Phase 2.8 — curved altitude for every altitude-dependent model (Step 45)

One additive step, promoting roadmap Backlog **B8** — the half of `models.tex` eq. `h_true` that
§24.2 deliberately left behind when Step 42 landed the impact event. Same discipline as §23/§24:
one step, one commit, a default that reproduces every prior step **bit-for-bit**, tests for every
new behaviour. It changes no state vector, no solver, no event, and adds **no `Params` field** —
the gate is the *existing* `gravity_direction`, whose default `"parallel"` is the bit-for-bit path.

| Step | Physics | Gate | Modules touched |
|---|---|---|---|
| 45 | every altitude-dependent model **and every reported/plotted altitude** reads the height above the **curved** reference surface, not the launch-point tangent plane | existing `gravity_direction = "parallel"` (default ⇒ flat ⇒ bit-for-bit) | `gravity.py`, `flow.py`, `atmosphere.py`, `wind.py`, `integrate.py`, `plotting.py`, `run.py` |

**Contents:** §25.1 the model and what is already in the code · §25.2 the orthogonality
consequence, named and justified · §25.3 where the helpers live and the exact signatures · §25.4
the per-file change list · §25.5 reported and plotted altitude · §25.6 bit-for-bit · §25.7 pinned
numbers · §25.8 scope — what this step does NOT do · §25.9 checks for the step · §25.10 rejected
options.

> **Scope amendment (user decision, recorded before implementation).** This section originally
> recommended leaving `run.py`'s reported "apogee altitude" and `plotting.py`'s altitude axis at the
> flat `−z`, matching Step 42, and flagged that as the one open question. **The user overrode that
> recommendation: "I want convention to be radial. I want stuff to be physically correct."** The
> reported and plotted altitude is therefore **in scope for Step 45**, specified in §25.5. The
> recommendation and its reasoning are kept in §25.10 (rejected options) rather than deleted,
> because one half of it survives the override intact and is now a *requirement*: the apogee
> **event** is still triggered at `vz = 0` in the launch frame, and only the altitude *value*
> reported at that instant becomes curved (§25.5, §25.8).

**A developer implementing this step needs §25 and `latex/sections-ai/models.tex` §Gravity >
Direction (the paragraphs "Construction (elliptical)" and "Ground and impact condition", eq.
`h_true`) — plus §24.1/§24.2 for the machinery it reuses. Not the whole of either document.**

### 25.1 Step 45 — the model, and what is already implemented

Spec: `latex/sections-ai/models.tex` §Gravity > Direction, eq. `h_true` and the sentence that
follows it — `h_true` "is the altitude to use, in place of `−z`, for every altitude-dependent model
once a non-parallel direction model is active — the atmosphere and wind tiers, and the radial/WGS84
magnitude models". §24.2 implemented the *ground event* half of that sentence and recorded the rest
as backlog **B8**; this step implements the rest, unchanged in derivation.

**There is no new formula.** `sim/gravity.ground_depth(t, y, p)` (Step 42) already *is* `−h_true`,
exactly, for all three direction models, with the mandatory `R is None` flat branch. The altitude
this step needs is therefore its negation and nothing else:

```
h_agl(y, p)  =  −ground_depth(0.0, y, p)
             =  −y[Z]                                                  ("parallel", bitwise)
             =  x·sin φ − z·cos φ − R·(1 − cos φ),  φ = x/R             ("radial"/"elliptical")
                with R = curvature_radius(p)  (§24.1: p.R_e or _R_chi(p))
h_msl(y, p)  =  h_agl(y, p) + p.h0_m
```

**Do not re-type the trigonometric form anywhere.** The whole point of the seam Step 42 built is
that the curved-surface geometry has exactly one implementation; a second copy in `flow.py` (or in
`atmosphere.py`) is the same drift hazard §24.1 refused for `_WGS84_A`/`_WGS84_E2` and §23.3 refused
for `_EPSILON`. Negating `ground_depth` costs one unary minus and guarantees the two can never
disagree about where the ground is. A test asserts the identity directly (§25.9).

**Why `h_msl = h_agl + h0_m` survives the change untouched.** The MSL surface is the sphere
concentric with the reference surface, `h0_m` below it, so a height measured above one differs from
a height above the other by exactly `h0_m` — the same relation as in the flat case, for the same
reason. Consequently `altitude_msl` needs **no** curvature code of its own: it becomes
curvature-aware for free, through `altitude_agl`. (This is worth stating because the opposite choice
— leaving `h_msl` flat while `h_agl` curves — would cost *extra* code, not less, and would put two
different altitudes in play at one state. Recorded as a rejected option, §25.10.)

**Why the effect is real but small, and why that is not a reason to cut corners.** At 10 km
downrange the curved ground has dropped ~7.85 m below the tangent plane, so every altitude lookup
is reading a height ~7.85 m too low today. That moves ISA density by ~0.08-0.10 % and gravity
magnitude by ~2.5 × 10⁻⁶ relative (§25.7 pins both). This is a fidelity-completeness step, exactly
as B8's own text says — not a bug fix. It gets the same rigour as everything else: the bit-for-bit
argument is written out, the invariants are asserted exactly rather than approximately, and the
numbers are pinned.

### 25.2 The orthogonality consequence — named, not smuggled in

§23.1 established `p.gravity_model` (magnitude: `constant`/`radial`/`wgs84`) and
`p.gravity_direction` (direction: `parallel`/`radial`/`elliptical`) as two **orthogonal** dispatches:
any magnitude combines with any direction, and §24.1 reinforced it with a test
("sweeping `p.R_e` must not move an `elliptical`-direction result, and sweeping
`lat0_deg`/`azimuth_deg` must not move a `radial`-direction one").

Curvature lives in exactly one place in this codebase — `gravity.curvature_radius(p)`, which keys
off `p.gravity_direction`. So once `_g_radial`/`_g_wgs84` take a curved `h`, they source that
curvature from `gravity_direction`. **State the consequence plainly rather than discovering it in a
test:**

> Selecting `gravity_direction = "elliptical"` changes the `h` that the gravity-*magnitude* formula
> consumes, even with `gravity_model = "radial"` unchanged. `gravity_model` is therefore no longer
> the *sole* input to the magnitude answer; `gravity_direction` now has a small magnitude-side
> effect, through `h`.

What this is, and is not:

- **It is not a collapse of the dispatch.** The two dicts stay separate and untouched. `g(t, y, p)`
  still dispatches purely on `p.gravity_model`; `z_hat_g(t, y, p)` still dispatches purely on
  `p.gravity_direction`. No combinatorial product of names appears, no variant is added or removed,
  and `gravity_model = "constant"` remains *exactly* `p.g` for every direction (the constant law has
  no `h` in it at all — assert this, §25.9). The coupling is through a **shared input**, not a
  shared dispatch. §24.2's item 2 read this as "collapsing the orthogonality"; on inspection that
  overstated it, and this section is the correction of record.
- **It is the physically coherent reading.** `h` is a geometric fact about where the rocket is
  relative to the reference surface. The magnitude law answers "how does `g` fall off with height";
  the direction/curvature model answers "what does height *mean*". One state has one altitude. The
  alternative — ISA and the wind shear reading a curved `h` while `_g_radial` reads a flat one at
  the same instant — is the actual inconsistency, and it is the one B8 exists to remove.
- **It is tiny, and its size is pinned.** `parallel → radial` at `x = 10 km` moves `_g_radial` by
  `−2.46 × 10⁻⁶` relative; `radial → elliptical` at `φ₀ = 50°, χ = 90°` moves it by a further
  ~`7.6 × 10⁻⁹` (the two curvature radii differ by 0.309 %, of a 7.85 m correction).
- **It is asserted deliberately, not tolerated.** §25.9 requires a test that *pins the coupling*:
  with `gravity_model = "radial"` held fixed, changing `gravity_direction` **must** move `g` by the
  pinned amount. Without that test, a future reader "restoring orthogonality" would silently revert
  this step.

**The three radii, and the one that must not be substituted for another.** With this step there are
four Earth-sized constants in play at once. Confusing them is the single realistic way to get this
step wrong:

| Quantity | Value / source | Role | Keyed off |
|---|---|---|---|
| `p.R_e` | `6371000.0` (`Params`) | **geocentric distance** in the `radial` *magnitude* law `g₀(R_e/(R_e+h))²` | `gravity_model` |
| `gravity.curvature_radius(p)` | `None` / `p.R_e` / `_R_chi(p)` | **radius of curvature** of the reference surface — what "ground" and "altitude" mean | `gravity_direction` |
| `gravity._WGS84_A` | `6378137.0` | ellipsoid semi-major axis, inside Somigliana **and** inside `_R_chi` | fixed physical constant |
| `atmosphere._R_ISA` | `6356766.0` | the ISA standard's own geometric→geopotential conversion radius | fixed, part of the ISA *definition* |

`_R_chi(p)` is a **curvature** radius (Euler/Meusnier), *not* a distance to the Earth's centre. It
must never be substituted into `(R_e/(R_e+h))²`: the inverse-square falloff is governed by the
distance to the mass, which the osculating-sphere construction says nothing about. For
`gravity_direction = "radial"` the two happen to coincide (a sphere's curvature radius *is* its
centre distance); for `"elliptical"` they differ by ~20 km and the difference is meaningless.
Likewise `_R_ISA` stays `6356766.0` whatever the direction model — it is part of the ISA's
definition, exactly like `_G_ISA = 9.80665` (§14). **Only the `h_msl` fed into the ISA changes.**

### 25.3 Where the helpers live, and the exact signatures

**`altitude_agl` and `altitude_msl` move from `sim/flow.py` to `sim/gravity.py`**, beside
`curvature_radius`/`ground_depth`, and both take `Params`:

```python
# sim/gravity.py  (new, immediately after ground_depth)

def altitude_agl(y: np.ndarray, p) -> float:
    """Height above the ground, up-positive -- `h_true` (models.tex
    SSGravity > Direction, eq:h_true; architecture.md SS25).

    Exactly `-ground_depth(t, y, p)`: one construction, one implementation,
    so the altitude the models read and the surface the impact event finds
    can never disagree. `ground_depth` ignores `t` (the reference surface
    does not move), so the `0.0` below is a placeholder, not a time.

    Under the default `gravity_direction = "parallel"` this is `-y[Z]`
    bitwise -- the pre-Step-45 `flow.altitude_agl(y)`, on the same operand.
    """
    return -ground_depth(0.0, y, p)


def altitude_msl(y: np.ndarray, p) -> float:
    """Height above mean sea level, `h_agl + p.h0_m`.

    Unchanged in form from the pre-Step-45 `flow.altitude_msl`: the MSL
    surface is concentric with the reference surface, `h0_m` below it, so
    the offset is exactly `h0_m` on a curved surface as on a flat one.
    Curvature reaches it entirely through `altitude_agl` above.
    """
    return altitude_agl(y, p) + getattr(p, "h0_m", 0.0)
```

**Why they move rather than staying in `flow.py` and importing gravity.** This is the one structural
decision in the step, and the import graph settles it:

- Today `gravity → flow` (module level, for the two helpers) and `flow → atmosphere` (module level)
  and `wind → flow` (module level). Leaving the helpers in `flow.py` would add `flow → gravity`
  (for the curvature) and `atmosphere → flow` (for `h_msl`) — **two new cycles**, resolvable only
  with two more function-scope imports, and it would mean `_g_radial` asking `flow` for a number
  that `gravity` computes. A round trip through a higher-level module to reach a lower-level fact.
- Moving them **deletes** the `gravity → flow` edge instead of adding edges. `gravity.py` becomes
  self-contained (numpy + `sim.state` only) and sits at the bottom of the stack, which is what it
  already is physically: it owns the Earth's shape. `atmosphere → gravity` and `wind → gravity` are
  then plain module-level imports with no cycle anywhere, and `flow.py` — which never calls either
  helper — simply stops defining them.
- It puts the altitude next to the curvature it is derived from, which is where `models.tex` puts
  it too (both live in §Gravity > Direction), and is the same argument §24.2 used to keep
  `ground_depth` in `gravity.py` rather than in `integrate.py`.

**`(y, p)`, not `(t, y, p)`.** `altitude_msl` already had `(y, p)`; `altitude_agl` gains `p` to
match. `t` is not added: the reference surface is time-invariant, and every caller would pass a
value that is thrown away. (`ground_depth` keeps its `(t, y, p)` because it is shaped as a
`solve_ivp` event function.)

**No compatibility alias in `flow.py`.** A re-export (`from sim.gravity import altitude_agl, ...`)
would leave two import paths for one function and hide where it lives. `flow.py` gets a docstring
note pointing at `gravity.py` instead, and its two callers are updated. There is no external
consumer of this package.

**Replacement for §15's altitude-conventions table:**

| Symbol | Meaning | Expression | Home | Used by |
|---|---|---|---|---|
| `z` | state, **down-positive**, zero at the launch point | `y[Z]` | `state.py` | the physics |
| `ground_depth` | depth below the ground, down-positive | `−h_true` | `gravity.py` | `integrate._ground_event`, `_run_rk4` |
| `h_agl` | above the ground (curved surface), up-positive | `altitude_agl(y, p)` = `−ground_depth` | `gravity.py` | `_g_radial`, `wind._analytic_wind` (tier 1 shear) |
| `h_msl` | above mean sea level | `altitude_msl(y, p)` = `h_agl + p.h0_m` | `gravity.py` | `_g_wgs84`, atmosphere tiers 1/2/3, wind tiers 2/3 |
| reported "altitude" | height above the ground under the rocket, for humans | `altitude_agl(y, p)` — **the same function**, called on a `(6, N)` array | `gravity.py` | `plotting.py`'s three altitude series, `run.py`'s two apogee-altitude readouts (§25.5) |

After this step there is no separate "reporting" altitude convention at all: the number printed
beside the apogee and the number plotted on the vertical axis are the *same* `altitude_agl` the
physics reads. That is the point of the user's override — one altitude, everywhere.

### 25.4 The change, file by file

Five files were surveyed; four change. Nothing else in `sim/` touches an altitude.

**`sim/flow.py`** — remove `altitude_agl` and `altitude_msl` (they move, §25.3). Add a one-paragraph
note to the module docstring recording that the altitude conventions moved to `gravity.py` at
Step 45, and why (they are derived from the surface-curvature construction that lives there).
`flow_state`, `Flow`, `_wind_inertial` are untouched; `flow.py` never called either helper. `Z`
then becomes unused in `flow.py`'s `from sim.state import THETA, VX, VZ, Z` — drop it. (The same
happens in `atmosphere.py`, `wind.py` and `plotting.py`; see below and §25.5. **After this step,
`y[Z]` is read as an *altitude* in exactly one place in the whole package: `gravity.ground_depth`.**
Every other altitude in `sim/` and in `run.py` — physics, reporting and plotting alike — goes
through `altitude_agl`/`altitude_msl`. That single-reader property is the cleanest statement of what
Step 45 buys, and it is worth asserting by grep in review. `dynamics.py`'s `dydt[Z] = y[VZ]` is an
index into the derivative vector, and `run.py`'s `trajectory.csv` dump writes the raw state column
`z` (§25.8) — neither is an altitude, neither counts.)

**`sim/gravity.py`** — four edits:

1. Delete `from sim.flow import altitude_agl, altitude_msl` (the module becomes self-contained).
2. Add `altitude_agl(y, p)` and `altitude_msl(y, p)` exactly as in §25.3.
3. `_g_radial`: `h = altitude_agl(y)` → `h = altitude_agl(y, p)`. The formula
   `p.g * (p.R_e / (p.R_e + h)) ** 2` is **unchanged** — `p.R_e` stays the geocentric radius
   (§25.2).
4. `_g_wgs84`: `h = altitude_msl(y, p)` — the call is already spelled that way and does not change;
   only the function it resolves to does. Update its docstring's "`h = h_msl = p.h0_m − z`" to the
   curved reading, and update the module docstring's Step-42 paragraph, which currently says the
   magnitude models "deliberately keep reading `h = −z`; see roadmap.md Backlog B8".

**`sim/atmosphere.py`** — add `from sim.gravity import altitude_msl` at module level (no cycle:
`gravity` imports only numpy and `sim.state` after edit 1 above), then replace the **three**
independent inlined copies of the flat altitude:

| Function | Current line | Becomes |
|---|---|---|
| `_isa_air_state` | `h_msl = -y[Z] + getattr(p, "h0_m", 0.0)` | `h_msl = altitude_msl(y, p)` |
| `_sounding_air_state` | same | same |
| `_field_air_state` | same | same |

The `from sim.state import Z` import becomes unused in this module if nothing else reads `Z` —
check and remove it if so. **`_G_ISA` and `_R_ISA` do not change, and `atmosphere.py` still must not
call `gravity.g()`** (§14): the new import exists solely for the surface-geometry seam. Because that
prohibition used to be enforced structurally (there was no import at all) and is now enforced only
by discipline, §25.9 adds a regression test pinning it.

**`sim/wind.py`** — change `from sim.flow import altitude_agl` to
`from sim.gravity import altitude_agl, altitude_msl`, then three edits:

| Function | Current | Becomes | Note |
|---|---|---|---|
| `_analytic_wind` (tier 1) | `h = altitude_agl(y)` | `h = altitude_agl(y, p)` | AGL is *right* here and gets *more* right: a power-law shear profile is referenced to the ground under the rocket, and with a curved surface that ground is further away than `−z` says. The docstring's existing AGL-vs-MSL argument stands unchanged. |
| `_sounding_wind` (tier 2) | `h_msl = -y[Z] + getattr(p, "h0_m", 0.0)` | `h_msl = altitude_msl(y, p)` | |
| `_field_wind` (tier 3) | same | same | |

Tiers 2/3 **do** change, and the reason is sharper than "consistency": at any given state, wind
tier 2 and atmosphere tier 2 read *the same sounding file* and must read it at *the same level*. If
only the atmosphere curved, the two would sample different rows of one profile for one state — a
genuine inconsistency, not a stylistic one. `from sim.state import Z` becomes unused here too;
check and remove.

**`sim/soundings.py`** — **no change. Confirmed by inspection**, not assumed: it receives `h_msl` as
a plain `float` argument from `interp_altitude(snd, h_msl)` / `interp_field(case, y, h_msl, p)` and
computes no altitude of its own. Its only `_geopotential(h_msl)` helper converts an altitude it is
given. (It does read `y[X]` for the horizontal station projection — out of scope, §25.8.)

**`sim/dynamics.py`, `sim/forces.py`, `sim/rotation.py`, `sim/aero.py`** — no change.
`rotation.py`'s Coriolis decomposition uses `lat0_deg`/`azimuth_deg` and no altitude;
`forces.thrust_body`'s pressure correction gets `p_amb` from `air_state` and therefore inherits the
curved altitude with no edit of its own.

**`sim/integrate.py`, `sim/plotting.py`, `run.py`** — the reported/plotted altitude, specified in
**§25.5**. `integrate.py`'s *event* logic is untouched (it already consumes `ground_depth` from
Step 42); its only change is one new `Result` field.

### 25.5 Reported and plotted altitude (`run.py`, `sim/plotting.py`, `Result.params`)

Per the scope amendment at the top of §25: the printed apogee altitude and every plotted altitude
series become the curved `altitude_agl(y, p)`. Four things have to be got right, and three of them
are traps.

#### AGL, not MSL — the reported quantity keeps its meaning

Use **`altitude_agl`**, not `altitude_msl`. Today's reported altitude is `−y[Z]`, i.e. height above
the *launch point*; its curved generalisation is height above the *ground under the rocket*, which
is `altitude_agl`. Switching to `altitude_msl` would additionally add `p.h0_m` and silently raise
every plotted curve of the LKPR atmosphere sweep by 380 m — a change of *meaning*, not of surface,
and not what "make the convention radial" asks for. The axis label stays `"Altitude [m]"`.

#### The apogee **event** is not touched — only the number reported at it

`integrate._apogee_event` stays `y[VZ]`, `direction = 1`, `terminal = False`, **unchanged**. This
step does not go near the trigger. Apogee continues to mean *the top of the trajectory in the launch
frame*; what changes is only the altitude *value* reported at that instant.

The two are genuinely different questions, and the difference is a known, deliberate property rather
than a defect: §24.2 computed `dh_true/dt = (x cos φ + z sin φ)vx/R − vz cos φ`, which is `+0.47 m/s`
at `vx = 300 m/s, x = 10 km` where `vz = 0`. So on a curved run the reported curved altitude at
`t_apogee` is **not** the maximum of the curved altitude over the flight; the two differ by ~0.05 s
of flight time and a second-order amount of altitude. Redefining apogee as `max h_true` remains out
of scope (§25.8) — it is a modelling decision about the *event*, and §24.2's warning stands:
mixing an event redefinition into a step about altitude is how the apogee/impact pair gets silently
broken. Put this paragraph in `_apogee_event`'s docstring, so the next reader does not "finish the
job".

#### The mechanism: `Result` gains `params`

`plot_trajectory(r)`, `plot_time_histories(r)` and `plot_trajectory_overlay(results, title)` receive
only `Result`s, and now need `Params`. **Add `params` as a fifth field to `integrate.Result`**,
appended last (the `Sounding.Td` / `_AeroTable.C_mq` precedent, §23.3/§24.4):

```python
class Result(NamedTuple):
    t: np.ndarray
    y: np.ndarray
    events: dict[str, Optional[float]]
    raw: Any
    params: Any    # the Params that produced this run -- Step 45, architecture.md SS25.5
```

set in the **two** places `Result` is constructed, both in `integrate.py`, both with `p` already in
scope: `run_sim`'s return and `_run_rk4`'s return, each gaining `params=p`.

Why this and not a `p` argument on the three plotting functions:

- `plot_trajectory_overlay` takes `dict[str, Result]` built by `run.py`'s `sweep()` — **one Params
  per variant**, by construction. A single `p` parameter would be wrong in general (it happens to be
  harmless for the two committed sweeps, which vary `gravity_model`/`atmosphere_model` and share a
  `gravity_direction`, but the function is generic and the next sweep might vary the direction
  itself). `r.params` is right per line, automatically.
- `Result` is constructed in exactly two places and consumed by attribute everywhere — **audited:
  there is no positional unpacking of `Result` anywhere in `sim/`, `tests/` or `run.py`** — so
  appending a field is contained.
- `Params` is a frozen dataclass with no numpy arrays in it (§17: "`Params` holds names and paths"),
  so `Result` stays printable and comparable, and a `Result` finally becomes self-describing about
  which models produced it — which §12 already wanted for saved runs.

#### `altitude_agl` must work on the `(6, N)` history array — it already does

`plotting.py` computes altitude for a whole sampled history at once (`y = r.raw.sol(t)`, shape
`(6, N)`). `ground_depth`'s body is pure elementwise numpy — `y[Z]` and `y[X]` become length-`N`
rows, `np.cos`/`np.sin` broadcast, and the `"parallel"` branch returns the `y[Z]` row unchanged — so
`altitude_agl(y, p)` and `altitude_msl(y, p)` **already vectorise with no code change**. Two things
follow, both required of the step:

- Widen the return annotations to `"float | np.ndarray"` on `ground_depth`, `altitude_agl` and
  `altitude_msl`, and say so in their docstrings. The vectorised use is now load-bearing, not
  incidental; an annotation saying `float` invites someone to "fix" it with a `float()` cast, which
  would break `plotting.py` in a way no gravity test would catch.
- Assert it: the vectorised call over a `(6, N)` array equals the per-column loop **exactly**
  (`np.array_equal`), for all three direction models (§25.9).

`curvature_radius(p)` is scalar and `R is None` is a scalar branch, so neither vectorises *into* a
per-sample decision — correct, because the direction model is a property of the run, not of the
sample.

#### The exact call sites

| File · function | Current | Becomes |
|---|---|---|
| `run.py` · `_flight_summary` | `apogee_altitude = -result.raw.sol(apogee_time)[Z]` | `altitude_agl(result.raw.sol(apogee_time), p)` |
| `run.py` · `main` | `apogee_altitude = -result.raw.sol(apogee_time)[Z]` | `altitude_agl(result.raw.sol(apogee_time), params)` |
| `plotting.py` · `plot_trajectory` | `altitude = -y[Z]` | `altitude = altitude_agl(y, r.params)` |
| `plotting.py` · `plot_trajectory_overlay` | `altitude = -y[Z]` (inside the per-variant loop) | `altitude = altitude_agl(y, r.params)` — each variant's own `r` |
| `plotting.py` · `plot_time_histories` | `altitude = -y[Z]` | `altitude = altitude_agl(y, r.params)` |
| `integrate.py` · `run_sim`, `_run_rk4` | `Result(t=…, y=…, events=…, raw=…)` | `+ params=p` |

**`run.py` has two independent copies of the apogee-altitude expression** — `_flight_summary` (used
by `sweep`) and `main` (which does *not* call `_flight_summary`, it recomputes inline). Both must
change. Converting only one is the realistic failure mode here, and it is **invisible in the
committed scenario's printed output** (which is vertical, see below), so it has to be caught by a
test that exercises a tilted curved run through both paths. Same hazard, same shape, as
`atmosphere.py`'s three inlined copies (§25.4).

`plotting.py`'s module docstring currently opens "The only module allowed to know altitude = -z" —
rewrite it: it is now the module that *asks* `gravity.altitude_agl` for the altitude, and the `-z`
knowledge has moved with the helper. `Z` becomes unused in `plotting.py`'s `from sim.state import`
line — drop it. In `run.py`, `Z` is **still used** by the `trajectory.csv` dump — keep it there.

#### What deliberately does not change in `run.py`

- **`trajectory.csv`'s `z` column stays the raw state.** The column is named `z` and *is* the state
  variable, down-positive — not an altitude claim, and already physically correct. Converting it
  would stop the dump being a state dump and would break run-to-run diffs for reasons unrelated to
  this step. (Adding a separate `h` column is a reasonable idea and is explicitly a different,
  optional step.)
- **Downrange needs no change at all.** `y[X]` is *already* arc length along the reference surface:
  §23.1 defines `φ = x/R`, i.e. `x` is measured along the ground, not as a chord. So
  `downrange_impact`, the CSV's `x` column and the trajectory plot's horizontal axis are already the
  physically correct ground-track distance. Do not "correct" them with an `R sin φ` factor — that
  would convert a correct arc length into a chord.
- **`set_aspect("equal")` stays.** With both axes now surface-referenced, `plot_trajectory` draws
  the path in surface-following coordinates (arc length along the ground against height above it).
  That is exactly the right picture and the equal aspect is still meaningful; nothing is being
  "unbent".

#### The recorded sweep outputs — resolved by proof, not by regeneration

The only **committed** record of `run.py` output is `PROJECT-STATUS.md`'s Step-27 bullet, the
fenced "Actual printed sweep tables" block (the `gravity_model` and `atmosphere_model` tables).
`trajectory.png`, `time_histories.png`, `gravity_sweep.png`, `atmosphere_sweep.png` and
`trajectory.csv` are all **gitignored** (`.gitignore`: `*.png`, `trajectory.csv`) — untracked,
regenerated on every `python run.py`, nothing to migrate.

**Those recorded tables do not move, and the step must prove it — twice over:**

1. `run.py`'s `params` never sets `gravity_direction`, so it is `"parallel"`: flat, bit-for-bit
   (§25.6), for every number in both tables.
2. Even if it were curved, that scenario is **exactly vertical**. `θ₀ = π/2`, `vx₀ = 0`,
   `A_z = A_m = 0`, `wind_model = "none"`, and in the atmosphere sweep `aero_model="coefficients"`
   produces `A_z = qS·C_N(α=0) = 0` and `A_m = 0` — so `ax ≡ 0`, `x ≡ 0.0` for the whole flight, and
   `altitude_agl` returns `−z` **bitwise** at `x = 0` for *every* direction model (§24.2's `cos 0 = 1,
   sin 0 = 0, R(1−1) = 0` argument). Both sweeps inherit this.

Therefore **`PROJECT-STATUS.md`'s Step-27 block is not edited by this step.** It is a dated record of
what Step 27 printed, and the project already treats it that way: it still lists the `linear` gravity
model, removed at Phase 2.5 Step 34, and Step 34 did not rewrite it.

**This is a checkable scope item, not an afterthought.** The step must:

- re-run `python run.py` and confirm the printed sweep tables match the recorded block to the printed
  precision, for the rows that still exist (`constant`, `radial`, `wgs84` — `linear` is gone — and
  both atmosphere rows);
- if any number *has* moved, the discrepancy predates Step 45 (it would have been introduced
  somewhere in Steps 33-44) and must be investigated and recorded explicitly before Step 45 is
  committed, **not silently absorbed into this step's commit**;
- record the verification in the usual tracker commit (`PROJECT-STATUS.md` / `status.json`), stating
  that the sweeps were re-run and are unchanged — the same shape as every prior phase's
  "Record Phase 2.x completion" commit.

No test in the suite pins an absolute apogee altitude — `tests/test_plotting.py`'s four sweep tests
are all ordering/relative comparisons (`constant < radial`, `wgs84 > radial`, `sounding > isa`),
and all run with the default `"parallel"` direction. **Audited; they pass unchanged.** Confirm that
before starting rather than assuming it.

### 25.6 Bit-for-bit, worked out rather than asserted

The default `gravity_direction = "parallel"` makes `curvature_radius(p)` return `None`, so
`ground_depth` returns `y[Z]` with **no arithmetic performed on that path at all** (§24.2). Then:

- `altitude_agl(y, p)` = `-(y[Z])`. IEEE negation is a sign-bit flip: exact for every finite value,
  for ±0.0, ±inf and NaN. The pre-Step-45 `flow.altitude_agl(y)` evaluated `-y[Z]` — *the same
  operation on the same operand*. **Bitwise identical**, not merely equal.
- `altitude_msl(y, p)` = `altitude_agl(y, p) + getattr(p, "h0_m", 0.0)` — the same two operations,
  same order, same operands as before. Bitwise identical.
- The five inlined sites in `atmosphere.py`/`wind.py` evaluated `-y[Z] + getattr(p, "h0_m", 0.0)`;
  they now evaluate `(-y[Z]) + getattr(p, "h0_m", 0.0)` through two function calls. Identical
  expression tree, identical operands. Bitwise identical.
- `_g_radial`/`_g_wgs84` receive a bitwise-identical `h` and their own formulas are untouched.
- `ground_depth` itself is **not edited**, so Step 42's pinned values and the impact event are
  untouched by construction.
- **The reporting path (§25.5) is bit-for-bit under `"parallel"` too, for the same one reason.**
  `run.py`'s two `-result.raw.sol(t_a)[Z]` become `altitude_agl(result.raw.sol(t_a), p)`, which
  under `"parallel"` is `-(y_a[Z])` — the same operation on the same operand. `plotting.py`'s three
  `-y[Z]` become `altitude_agl(y, r.params)`, which under `"parallel"` returns `-(y[Z])` on the
  whole `(6, N)` row — numpy's unary negation, elementwise, exact. Every plotted point and every
  printed apogee altitude is bitwise what it was.
- **`Result.params` cannot perturb anything.** It is an appended field on a NamedTuple, read by
  nobody except `plotting.py`, and `Params` is frozen. No existing consumer reads `Result`
  positionally (audited, §25.5), so `r.t`/`r.y`/`r.events`/`r.raw` resolve exactly as before.
- **`_apogee_event`, `_ground_event` and `_burnout_event` are not edited at all**, so event times
  are unchanged by construction on both integrator paths — the reporting change reads the
  interpolant at the same instant as before.

**Therefore the entire existing test suite must pass unmodified.** That is the step's headline
check, and it is stated as a hard rule in §25.9: the only test edits permitted by this step are the
two `tests/test_flow.py` altitude tests, which must move to `tests/test_gravity.py` and gain the `p`
argument (their import line would otherwise fail at collection). **Any other test that needs editing
is a bug in the step, not in the test.**

The curved-direction tests that already exist (`tests/test_forces.py`'s four
`gravity_direction` tests, `tests/test_gravity.py`'s `ground_depth` tests) also pass unchanged, for
a second and independent reason: they all run with `gravity_model = "constant"` and
`aero_model = "constant"`, so no altitude is consulted on their paths. **Audit that claim before
starting** — if any of them is later given a non-constant gravity or aero model, its numbers move,
by design.

### 25.7 Pinned numbers

**One state, five consequences.** `State(x = 10 000.0, z = −1000.0, …)`, `R_e = 6371000.0`,
`h0_m = 0.0`, comparing `gravity_direction = "parallel"` against `"radial"`:

| Quantity | Configuration | `"parallel"` | `"radial"` | Relative change |
|---|---|---|---|---|
| `altitude_agl` [m] | — | `1000.000000` | `1007.846825` | `+7.846825 m` |
| **reported apogee altitude / plotted altitude** [m] | §25.5 — it *is* `altitude_agl` now | `1000.000000` | `1007.846825` | `+7.846825 m` |
| `_g_radial` [m/s²] | `gravity_model="radial"`, `g=9.80665` | `9.803572196959` | `9.803548051707` | `−2.4629e−6` |
| `_g_wgs84` [m/s²] | `gravity_model="wgs84"`, `lat0_deg=50.0` | `9.807617683881` | `9.807593486449` | `−2.4672e−6` |
| ISA `rho` [kg/m³] | `atmosphere_model="isa"` | `1.111659912` | `1.110803679` | `−7.7023e−4` |
| tier-1 `W` [m/s] | `wind_ref_ms=5.0`, `wind_ref_h_m=10.0`, `wind_shear_exp=0.143` | `9.659841585` | `9.670644585` | `+1.1183e−3` |

Note the signs: the rocket is **higher** than the flat reading said, so `g` is **smaller**, the air
is **thinner**, the sheared wind is **stronger**, and the reported altitude is **larger**. All five
follow from one `+7.846825 m`.

**The committed `run.py` scenario moves by exactly zero — pin that too.** Its printed summary,
both sweep tables and all four figures are unchanged by this step, for two independent reasons
(§25.5): `gravity_direction` is the default `"parallel"`, and the flight is exactly vertical
(`x ≡ 0.0`, where `altitude_agl` returns `−z` bitwise for *every* direction model). The pinned
values are therefore `PROJECT-STATUS.md`'s own recorded Step-27 tables, unchanged to the printed
four decimals — e.g. `constant 4609.2267 m / 30.1209 s`, `radial 4612.2651 m / 30.1465 s`,
`wgs84 4624.2535 m / 30.2202 s`, and `isa 682.3775 m` vs `sounding 685.1434 m`. This is a
*negative* pin — the step is wrong if any of them moves.

**The `h_true` table (§24.2's, un-negated — now read as altitudes rather than depths):** at `z = 0`,
`R = R_e`, `altitude_agl` = `+0.078481 / +1.660650 / +7.848057 / +70.632162` m at
`x = 1 / 4.6 / 10 / 30` km. These are the same literals `tests/test_gravity.py::_PINNED_NEG_H_TRUE`
already carries, with the sign flipped — reuse them, do not re-derive them.

**`altitude_agl` depends on `z` as well as `x`** (the exact form, not the `x²/2R` approximation):
at `x = 10 km` the correction is `+7.848057 m` at `z = 0`, `+7.846825 m` at `z = −1000`,
`+7.841897 m` at `z = −5000`. A test that only ever checks `z = 0` cannot tell the exact form from
the approximation; §24.2's small-angle-residual test already covers this for `ground_depth` and does
not need repeating, but the `z`-dependence is worth one assertion.

**Elliptical vs radial**, `φ₀ = 50°, χ = 90°` (so `R_χ = 6390702.0442` against `R_e = 6371000.0`,
§24.1's pinned value), at `x = 10 km, z = 0`: `altitude_agl` is `7.823862 m` elliptical against
`7.848057 m` radial — a difference of `−0.024195 m`, i.e. `0.31 %` of a 7.85 m correction. Fed into
`_g_radial` that is a `~7.6e−9` relative change in `g`: the magnitude-side effect of
`gravity_direction` described in §25.2, at its realistic size.

**Scale-height reading**, for anyone checking the density pin by hand: `Δρ/ρ ≈ −Δh/H` with
`H ≈ 10.2 km` at 1 km altitude (`−7.7e−4` for `+7.85 m` ✓) and `H ≈ 8.5 km` higher up, which is
where §24.2's "~0.09 %" figure came from. Both are far below the atmosphere model's own error — the
same threshold §23.3 used to leave `a` and `μ` dry and §13 used to reject EGM2008. This step is
taken for *consistency*, not accuracy: it is no longer defensible for the impact event to know the
ground curves while the air above it does not.

### 25.8 Scope — what this step does NOT do

- **No change to any event's trigger — this is the hard line of the step.** `_apogee_event` stays
  `y[VZ]`, `direction = 1`, `terminal = False`; `_ground_event` stays `ground_depth` with
  `direction = 1`, `terminal = True` (Step 42); `_burnout_event` stays `t − t_burn`.
  `sim/integrate.py`'s **only** edit is the new `Result.params` field (§25.5). The reported altitude
  becoming curved is a change to a *number read at an instant*, not to *which instant*. A developer
  who "finishes the job" by also moving the apogee trigger has changed the physics of the run, not
  its reporting, and has broken the pairing §24.2 warned about.
- **Apogee is not redefined as `max h_true`.** On a curved run the reported curved altitude at
  `t_apogee` is *not* the maximum of the curved altitude over the flight — `dh_true/dt` is
  `+0.47 m/s` at `vx = 300 m/s, x = 10 km` where `vz = 0` (§24.2), so the two definitions differ by
  ~0.05 s and a second-order amount of altitude. That is a known, documented property of reporting a
  surface-referenced altitude at a launch-frame apogee, and redefining the event is a separate
  modelling decision with its own tests.
- **`trajectory.csv`'s `z` column stays the raw, down-positive state** (§25.5). It is labelled `z`,
  it is the state variable, and it is already physically correct; converting it would stop the dump
  being a state dump. Adding a separate `h` column is a different, optional step.
- **Downrange is not touched.** `y[X]` is already arc length along the reference surface by
  construction (`φ = x/R`, §23.1), so `downrange_impact`, the CSV's `x` column and the plots'
  horizontal axis are already right. Do not apply an `R sin φ` "correction" — it would turn a
  correct arc length into a chord.
- **No new sweep or scenario in `run.py`.** The committed scenario stays vertical and
  `"parallel"`, which is why its recorded outputs are unchanged (§25.5, §25.7). Adding a tilted
  curved-direction sweep so the new behaviour is visible in the shipped output is a reasonable
  follow-up and is explicitly *not* this step.
- **`PROJECT-STATUS.md`'s Step-27 recorded sweep tables are not rewritten** (§25.5). They are a
  dated record — they still list the `linear` model removed at Step 34 — and this step proves they
  do not move rather than regenerating them.
- **No `ω_n`/`ζ` reporting** (still §24.4's separate optional step) and no other addition to the
  printed summary.
- **No change to `_G_ISA` (`9.80665`) or `_R_ISA` (`6356766.0`).** Both are constants of the ISA
  standard's own definition, exactly as §14 states; only the `h_msl` handed to the ISA changes.
  `atmosphere.py` still must not call `gravity.g()`.
- **`p.R_e` keeps its role** as the geocentric radius of the `radial` magnitude falloff. Do not
  substitute `curvature_radius(p)` into `(R_e/(R_e+h))²` (§25.2).
- **No change to the horizontal station projection.** `soundings.interp_field` still reads `y[X]`
  as a tangent-plane distance rather than an arc length. The mismatch is `x³/6R²` —
  `4.1 mm` at 10 km, `0.11 m` at 30 km — against station spacings of tens of kilometres and an
  IDW `ε` of 500 m. Not worth a step.
- **No `Params` field, no new model string, no new dispatch dict.** The gate is the existing
  `gravity_direction`. This is the first step since Step 38 that adds no field at all; that is a
  feature, and it is why the bit-for-bit argument is as short as it is.
- **No caching of `curvature_radius(p)`**, for §24.1's reason (~10 flops, `Params` is not hashable
  across every field, §15 "do not optimise"). `altitude_agl` is now called ~4-6× per RHS evaluation
  instead of ~2×; at microseconds per call this is irrelevant (§7).
- **No third-order ellipsoid fidelity** (φ₀ stays frozen at the launch site) and **no Coriolis
  coupling** — both inherited unchanged from §24.1/§23.1.
- **No geoid/MSL refinement.** `h_msl = h_agl + h0_m` treats the mean-sea-level surface as
  concentric with the reference surface. The ellipsoid/geoid distinction is already ignored by
  `_g_wgs84` (§13) and is far below this step's own effect size.
- **No terrain.** "Ground" is the smooth reference surface, as in §24.2.

### 25.9 Checks for the step

**Regression (the headline check).**

- The **entire existing suite passes unmodified**, with the single permitted exception of
  `tests/test_flow.py`'s `test_altitude_agl_is_minus_z` and
  `test_altitude_msl_falls_back_to_agl_when_h0_m_absent`, which move to `tests/test_gravity.py`,
  import from `sim.gravity`, and pass `p`. Any other test needing an edit is a bug in the step.
- A full `run_sim` on **both** integrator paths (RK45 and `method="rk4"`), with the default
  `gravity_direction = "parallel"` and a configuration that actually exercises every altitude
  consumer (`gravity_model="wgs84"`, `atmosphere_model="isa"`, `aero_model="coefficients"`,
  `wind_model="analytic"`), reproduces the pre-Step-45 `events`, `t` and `y` arrays **bit-for-bit**
  (`np.array_equal`). Repeat once with `atmosphere_model="sounding"` + `wind_model="sounding"` on
  the committed `example` case, so the tier-2 path is covered too.
- Include a **tilted** scenario with `x ≠ 0` throughout — under `"parallel"` it must still be
  bit-for-bit, and it is the only configuration in which a mistake in the flat branch could show up
  (the vertical default has `x ≡ 0`, where the curved formula also returns `−z`; say so in the
  test's docstring, as Step 42's tests do).
- `tests/test_plotting.py`'s four sweep tests pass unchanged (all ordering/relative, all
  `"parallel"` — audited, §25.5). Re-run `python run.py` and confirm the printed sweep tables match
  `PROJECT-STATUS.md`'s recorded Step-27 block to the printed precision for the rows that still
  exist; a discrepancy predates this step and must be investigated and recorded, not absorbed
  (§25.5).

**Reported and plotted altitude (§25.5).**

- **Bit-for-bit under `"parallel"`:** `run.py`'s printed apogee altitude and `plotting.py`'s three
  altitude series are bitwise what they were. Assert the plotting one directly — call
  `plot_trajectory`/`plot_time_histories`/`plot_trajectory_overlay`, pull the line data back off the
  returned figure (`ax.lines[0].get_ydata()`), and `np.array_equal` it against `-r.y[Z]`-style
  reference arrays built the old way.
- **Reported == the helper, not a re-derivation:** `_flight_summary(result, p)["apogee_altitude"]`
  equals `altitude_agl(result.raw.sol(result.events["apogee"]), p)` **exactly**, for all three
  directions. Same assertion for `main()`'s inline copy — and it must be a *separate* assertion,
  because `main()` does not call `_flight_summary` and converting only one of the two is this
  change's realistic failure mode (§25.5). Exercise both through a **tilted** curved run, where the
  two differ from the flat value.
- **Geometric magnitude:** for a tilted `"radial"` run, `apogee_altitude − (−y_a[Z])` at that run's
  own apogee state `y_a` equals `x·sin φ − z·cos φ − R(1−cos φ) + z` evaluated on `y_a` exactly, is
  strictly positive, and is within a few per cent of `x_a²/2R_e`. Do not pin an absolute apogee
  altitude for a simulated trajectory — pin the *difference*, computed from the state the run
  actually reached.
- **Synthetic pin:** at `(x = 10 km, z = −1000)`, `R_e = 6371000`, the reported altitude is
  `1007.846825 m` under `"radial"` against `1000.000000 m` under `"parallel"` (§25.7's table).
- **AGL not MSL:** with `h0_m = 380.0`, the reported/plotted altitude at `z = 0` is `0.0`, not
  `380.0` — the guard against `altitude_msl` being wired in by mistake, which would silently raise
  every LKPR-sweep curve by 380 m.
- **Vectorisation:** `altitude_agl(y_2d, p)` over a `(6, N)` history equals the per-column loop
  `[altitude_agl(y_2d[:, i], p) for i in range(N)]` **exactly** (`np.array_equal`), for all three
  directions, and returns shape `(N,)`.
- **`Result.params`:** `run_sim(...).params is p` on **both** integrator paths (RK45 and `rk4`), and
  `plot_trajectory_overlay` on a two-variant sweep draws each line with *its own* variant's
  `params` — construct two Results with deliberately different `gravity_direction` values and check
  the two plotted altitude series differ accordingly (the check that `r.params` is read per line,
  not once).
- **The apogee trigger is unchanged:** assert `_apogee_event.direction == 1` and
  `_apogee_event.terminal is False` as attributes, and that `result.events["apogee"]` is bitwise
  identical between the pre- and post-step runs — the regression guard on this step's one real
  hazard, mirroring Step 42's `_ground_event` attribute assertions.

**Identity and structure.**

- `altitude_agl(y, p) == -gravity.ground_depth(0.0, y, p)` exactly, for all three direction models,
  at several `(x, z)` including `x = 0` and large `x` — the anti-duplication guard.
- `altitude_agl(y, p_parallel) == -y[Z]` exactly, for arbitrary `x`, `z`, including `x ≠ 0`.
- `altitude_msl(y, p) == altitude_agl(y, p) + p.h0_m` exactly, for all three directions and a
  nonzero `h0_m`.
- `altitude_agl(y, p) == -y[Z]` exactly at `x = 0.0` for **all three** directions (`cos 0 = 1`,
  `sin 0 = 0`, `R(1−1) = 0` — bitwise, §24.2's argument).
- An unknown `gravity_direction` raises `KeyError` from `altitude_agl` too — i.e. from inside the
  atmosphere and wind paths as well — with no silent flat fallback (§7, and §24.1's own test).
- `sim/gravity.py` no longer imports `sim/flow.py`: assert it structurally if convenient (e.g. that
  `sim.gravity` imports cleanly with `sim.flow` absent from `sys.modules`), or at minimum state it
  in the module docstring.

**Curved-model values.**

- `altitude_agl` at `z = 0`, `"radial"`, `R_e = 6371000`, matches `+0.078481 / +1.660650 /
  +7.848057 / +70.632162` m at `x = 1 / 4.6 / 10 / 30` km — the existing `_PINNED_NEG_H_TRUE`
  literals with the sign flipped.
- `altitude_agl` is **strictly greater** than `−y[Z]` for every `x ≠ 0` under a curved direction
  (the ground fell away beneath a rocket that did not), and equal at `x = 0`.
- `altitude_agl` depends on `z`, not only on `x`: `+7.848057 / +7.846825 / +7.841897` m at
  `x = 10 km` for `z = 0 / −1000 / −5000`.
- `"elliptical"` at `φ₀ = 50°, χ = 90°` gives `7.823862 m` where `"radial"` gives `7.848057 m`
  (`x = 10 km, z = 0`) — a live, distinguishable code path.

**Physics consequences (one state, four pins — §25.7's table, asserted as differences, not
re-derived in the test).**

- `_g_radial`: `9.803572196959 → 9.803548051707` (`−2.4629e−6` relative) between `"parallel"` and
  `"radial"` at `(x = 10 km, z = −1000)`.
- `_g_wgs84` at `lat0_deg = 50.0`: `9.807617683881 → 9.807593486449` (`−2.4672e−6`).
- ISA `rho`: `1.111659912 → 1.110803679` (`−7.7023e−4`); and `rho`, `p`, `T` all move in the
  thermodynamically consistent direction (thinner, lower pressure, warmer or cooler per the layer's
  own lapse) — check `rho == p/(R_d·T)` still holds exactly.
- Tier-1 wind `W`: `9.659841585 → 9.670644585` (`+1.1183e−3`), i.e. a *stronger* wind at a *higher*
  true altitude under a positive shear exponent.
- Tier 2 consistency: at one state, `atmosphere._sounding_air_state` and `wind._sounding_wind` read
  the committed `example` sounding at **the same** `h_msl` — compute `altitude_msl(y, p)` in the
  test and assert both models' outputs equal `soundings.interp_altitude(snd, that_h)`'s
  corresponding fields. This is the check that the five call sites were all converted, and all
  converted the same way.

**Orthogonality, pinned in both directions (§25.2).**

- With `gravity_model = "constant"`, `g(t, y, p)` is exactly `p.g` for **all three** directions, at
  any `x` — the constant law has no `h` in it and must stay immune.
- With `gravity_model = "radial"` held fixed, sweeping `gravity_direction` across
  `parallel/radial/elliptical` **does** change `g`, by the pinned amounts above. This test exists
  specifically so that nobody "restores orthogonality" by reverting the step; its docstring must say
  so and cite §25.2.
- With `gravity_direction = "elliptical"` and `gravity_model = "radial"`: sweeping `p.R_e` changes
  `g` (it is the falloff radius) but leaves `altitude_agl` **exactly** unchanged (curvature comes
  from `_R_chi`). With `gravity_direction = "radial"`, sweeping `p.R_e` changes both. This is the
  sharpest available test that the two roles of "an Earth radius" were not conflated (§25.2), and it
  extends §24.1's own `R_e`-sweep test rather than replacing it.
- With `gravity_direction = "elliptical"`, sweeping `lat0_deg`/`azimuth_deg` moves `altitude_agl`;
  with `"radial"` it does not.

**`atmosphere.py`'s ISA invariant, newly in need of a guard (§25.4).**

- Sweeping `p.gravity_model` across `constant/radial/wgs84` leaves every `air_state(...)` field
  **exactly** unchanged, at a state with `x ≠ 0` and a curved direction active. `atmosphere.py` now
  imports `sim.gravity`, so §14's "the atmosphere must not call `gravity.g()`" is no longer
  guaranteed by the absence of an import; this test guarantees it instead.
- `_R_ISA` and `_G_ISA` are still `6356766.0` and `9.80665` (a literal assertion is cheap and
  documents the rule where a reader will hit it).

### 25.10 Rejected options

| Rejected | Why |
|---|---|
| Keep `altitude_agl`/`altitude_msl` in `flow.py` and import `gravity` from there | Adds two import cycles (`flow → gravity` and `atmosphere → flow`), each needing a function-scope import to break, and routes `_g_radial`'s altitude request up through `flow` and back down to `gravity`. Moving the helpers *removes* an edge instead of adding two (§25.3). |
| A new `sim/surface.py` (or `sim/ground.py`) holding the curvature, the ground and the altitudes | Tempting now that the surface seam has four public functions and four consumers — but `_R_chi` needs `_WGS84_A`/`_WGS84_E2`, which `_g_wgs84` also needs. Splitting means either a second copy of those constants (forbidden, §24.1) or a `gravity ↔ surface` cycle, and it churns three just-landed steps. `gravity.py` is the module that owns the Earth's shape in this codebase; §24.2 already settled this for `ground_depth`. |
| Re-typing the `h_true` trigonometry in a new `altitude_agl` body | Two implementations of one surface, free to drift — the exact hazard §24.1 and §23.3 legislated against. `−ground_depth(...)` is one unary minus and cannot disagree with the impact event. |
| Refactoring `ground_depth` into a shared private `_h_true(y, p)` with `ground_depth = −_h_true` | Bitwise safe (IEEE subtraction is exactly antisymmetric, so `−fl(fl(A−B)−C) == fl(fl(B−A)+C)`, and `−(−y[Z]) == y[Z]` exactly) — but it churns a function that landed one step ago and whose pinned tests are the project's guard on the one sign mistake that phase invited, in exchange for removing a documented placeholder `0.0`. Not worth it. |
| Making `altitude_agl` take `(t, y, p)` for signature uniformity | The reference surface is time-invariant; every caller would pass a value that is discarded. `(y, p)` matches `altitude_msl`'s existing shape. |
| Keeping a `flow.altitude_agl` alias for compatibility | Two import paths for one function, in a package with no external consumers. Update the two callers. |
| Leaving `altitude_msl` flat while `altitude_agl` curves | Would put two different altitudes in play at one state, and would cost *extra* code: `altitude_msl` is `altitude_agl + h0_m` today and inherits curvature for free. The MSL surface is concentric with the reference surface, so the offset really is exactly `h0_m` (§25.1). |
| Leaving wind tiers 2/3 flat because they are "MSL, not AGL" | They read the *same sounding file* as atmosphere tiers 2/3. Curving one and not the other would sample two different rows of one profile for one state. |
| Adding a `Params` flag to gate the curved altitude separately from `gravity_direction` | A second source of truth for "is the ground curved". `gravity_direction = "parallel"` already means "flat", and §21 already rejects inferring physics from anything other than an explicit model string. |
| Substituting `curvature_radius(p)` for `p.R_e` in `_g_radial`'s falloff | `_R_chi` is a radius of *curvature*, not a geocentric distance; the inverse-square law is governed by distance to the mass (§25.2). |
| Making the ISA's `_R_ISA` (geopotential conversion) curvature-aware | Part of the ISA standard's own definition, exactly like `_G_ISA = 9.80665` (§14). Only the input `h_msl` changes. |
| ~~Leaving `run.py`'s reported apogee altitude and `plotting.py` at `−z`~~ | **Rejected by the user**, who asked for the radial convention everywhere ("I want stuff to be physically correct"). The original argument was that it is a reporting decision mixed into a physics step. Its surviving half is now a *requirement*, not a deferral: the apogee **event** stays `vz = 0` and only the reported *value* curves (§25.5, §25.8). Its other half — that recorded sweep outputs would shift — turned out to be false for the committed scenario, which is vertical and `"parallel"` (§25.5); that is now a pinned negative check rather than a reason to defer. |
| Adding a `p: Params` argument to the three `plotting.py` functions | `plot_trajectory_overlay` takes a dict of `Result`s from a *sweep* — one `Params` per variant. A single `p` argument is wrong in general, and would happen to be harmless only for the two committed sweeps. `Result.params` is right per line (§25.5). |
| Redefining apogee as the maximum of `h_true` | Changes *which instant* apogee is, not just the number reported at it — a separate modelling decision with its own tests, and §24.2's warning about breaking the apogee/impact pair applies directly. The ~0.05 s / second-order-altitude difference is documented instead (§25.8). |
| Reporting `altitude_msl` instead of `altitude_agl` | Changes the reported quantity's *meaning* (adds `p.h0_m`), silently raising every LKPR-sweep curve by 380 m. The step changes the surface the altitude is measured from, not what is being measured (§25.5). |
| Converting `trajectory.csv`'s `z` column to an altitude | It is labelled `z`, it *is* the state, and it is already correct; converting it would stop the dump being a state dump and would break run-to-run diffs for unrelated reasons. A separate `h` column is a different, optional step (§25.8). |
| Applying an `R sin φ` "correction" to downrange | `y[X]` is already arc length along the reference surface by construction (`φ = x/R`, §23.1). The "correction" would convert a correct arc length into a chord. |
| Regenerating `PROJECT-STATUS.md`'s Step-27 sweep tables | They do not move (vertical scenario, `"parallel"` default — §25.5), and the file is a dated changelog: it still lists the `linear` model removed at Step 34, which Step 34 did not rewrite. Prove they are unchanged; do not edit the record. |

---

## 26. Phase 2.9 — Dryden turbulence for wind gusts (Step 46)

One additive step. It replaces the **placeholder** gust mechanism that Step 21 shipped in
`sim/wind.py` (`_gust_realization`/`_gust`) with the real MIL-F-8785C / MIL-HDBK-1797 **Dryden**
turbulence spectrum: altitude-dependent scale lengths and intensities, two horizontal components
(`u` along-wind, `v` cross-wind), amplitudes drawn from the published power spectral density instead
of from an arbitrary half-normal weighting. Same discipline as §23/§24/§25: one step, one commit, a
default that reproduces every prior step **bit-for-bit**, tests for every new behaviour.

Unlike §25 this step is **not** bit-for-bit for every configuration: any run that had gusts switched
on (`gust_sigma > 0.0`) changes, deliberately. That is a *behaviour change, not a regression* — the
Step-21 scheme never claimed to be a spectrum (§16's own text promised "amplitudes from a von
Kármán/Dryden-like spectrum" and the implementation never did it), nothing in the repository pins a
gusty number, and the committed `run.py` scenario uses `wind_model="none"`. §26.1 records what was
wrong with the old scheme so the change is auditable rather than merely asserted.

| Step | Physics | Gate | Modules touched |
|---|---|---|---|
| 46 | tier-1 gusts become the Dryden turbulence spectrum: `L_u`, `σ_u` from the MIL-spec altitude profile (AGL), amplitudes from `Φ_u`/`Φ_v`, two horizontal components composed as a **vector** perturbation of the mean wind | new `turbulence_model = "none"` (default ⇒ no turbulence ⇒ bit-for-bit) | `sim/params.py`, `sim/wind.py`, `tests/test_wind.py` |

**Contents:** §26.1 what is being replaced, and why it was a placeholder · §26.2 the verified
formulas, and the foot/metre problem · §26.3 the `Params` fields — three added, two removed · §26.4
the reference implementation · §26.5 the altitude bands · §26.6 from PSD to a frozen sum of
sinusoids · §26.7 composition into `(w_x, w_y)` · §26.8 determinism — what it does and does not
constrain · §26.9 the reference-airspeed limitation, stated · §26.10 scope — what this step does NOT
do · §26.11 pinned numbers · §26.12 checks for the step · §26.13 rejected options · §26.14 cached
research facts.

**A developer implementing this step needs §26 and
`latex/research/dryden_turbulence_model.md` §3 and §5 — not the whole of either document, and not
§§1-25 of this file.** `sim/wind.py` in full is the third input (it is 275 lines; read it, not a
grep of it). Note the mismatch flagged in §26.14: `latex/sections-ai/models.tex` §Wind > Analytic
still documents the Step-21 placeholder. **Resolved 2026-10-02** — the user nominated this §26
(plus the research note) as the interim physics reference, with `models.tex` to be brought in line
later by the user's own edit. A developer must still not edit `models.tex` to paper over the gap.
**Closed 2026-10-13** (Phase 2.14 LaTeX sync pass, at the user's own request): `models.tex` §Wind
now carries a `Turbulence` paragraph transcribing this §26 — the mean profile keeps the `Analytic`
paragraph, the fluctuation is its own paragraph, and the three contradicted statements (the
placeholder sum, the non-negativity clamp, `σ = 0` as the off switch) are gone. The standing rule
is unchanged for implementers: the LaTeX is still the user's document and still wins, and a
developer still does not edit it to paper over a gap.

### 26.1 What is being replaced, and why the Step-21 mechanism was a placeholder

`sim/wind.py`'s Step-21 gust model is:

```python
_GUST_N = 8
periods_s = np.geomspace(3.0, 600.0, _GUST_N)     # deterministic grid
omegas    = 2.0 * np.pi / periods_s
phases    = rng.uniform(0.0, 2.0 * np.pi, _GUST_N)
weights   = np.abs(rng.normal(0.0, 1.0, _GUST_N)) # half-normal
weights  /= np.sqrt(np.sum(weights ** 2))         # => sum(w_i**2) == 1
...
W = max(W + p.gust_sigma * np.sum(weights * np.sin(omegas * t + phases)), 0.0)
```

Five separate things are wrong with it as *physics* (the machinery around it is sound and is kept):

1. **No spectrum.** The weights are a random draw, not a function of frequency. Each seed gets its
   own arbitrary spectral shape; the ensemble has no particular shape either.
2. **No altitude dependence.** One `gust_sigma` for the whole flight, from the pad to apogee, where
   MIL-spec says intensity falls from ~19 % of the mean wind at 20 ft to a separate free-atmosphere
   value above 2000 ft, and the scale length grows from tens of metres to 533 m.
3. **One scalar on a speed, not a vector perturbation.** The perturbation is added to `W(h)` and
   then decomposed with the *unperturbed* direction, so the gust can only ever strengthen or weaken
   the mean wind, never turn it. Real turbulence has a cross-wind component of the **same**
   intensity (`σ_v = σ_u`), which this model cannot represent at all.
4. **The non-negativity clamp.** `max(W + Δ, 0.0)` exists only because perturbing a *speed* and then
   applying a fixed direction makes a negative sum silently flip the wind through 180°. Once the
   perturbation is a vector along the mean-wind direction, a negative along-component **is** that
   180° reversal, correctly — which is what a gust stronger than the mean wind does. The clamp
   becomes an artefact and goes (§26.7).
5. **`gust_sigma` is not the standard deviation it claims to be.** `_gust_realization`'s docstring
   says normalising to `Σ wᵢ² == 1` "makes `p.gust_sigma` approximately the resulting perturbation's
   standard deviation". A sinusoid `a·sin(ωt+φ)` has time-variance `a²/2`, so
   `Var[Σ σ wᵢ sin(·)] = σ² · Σwᵢ²/2 = σ²/2`: the realised standard deviation is `σ/√2 ≈ 0.707 σ`,
   not `σ`. An off-by-√2 in the only user-facing knob. The replacement normalises to `Σwᵢ² == 2`
   and gets an **exact** variance identity (§26.6), asserted as such.

What is **kept, unchanged in kind**: the frozen-sum-of-sinusoids form
`σ · Σ wᵢ sin(ωᵢ t + φᵢ)`, the deterministic log-spaced frequency grid, `np.random.default_rng(seed)`
for the phases, the `functools.lru_cache` per seed, and the "a zero/`"none"` setting skips the RNG
entirely" off-switch convention. The diff is therefore small and legible: the weights stop being a
random draw and become a function of `(ω, L, V)`; `σ` stops being a `Params` field and becomes a
function of altitude; there are two components instead of one.

### 26.2 The verified formulas, and the foot/metre problem

**Source:** `latex/research/dryden_turbulence_model.md` §3, which transcribes Madden (NASA Langley,
NTRS 20190000875) eqs. (1)-(3) for the PSDs and cross-checks the scale-length/intensity formulas
against Cole & Wickenheiser (arXiv:1905.09954) Table 3.1. Both sources were fetched and read as
rendered pages, not reconstructed. **Do not re-derive these and do not re-research them**; the one
transcription hazard the research pass found is recorded there (an initial tool summary misread the
scale length as a product `h·(0.177+0.000823h)^1.2` instead of a quotient — it is a **quotient**).

Low altitude, `h < 1000 ft`, `h` AGL:

```
L_u = L_v = h / (0.177 + 0.000823·h)^1.2                 [ft, with h in ft]
σ_w       = 0.1 · W20                                     W20 = mean wind speed at 20 ft AGL
σ_u = σ_v = σ_w / (0.177 + 0.000823·h)^0.4
```

Dryden PSD, temporal form, `ω` in rad/s, `V` the reference airspeed (§26.9):

```
Φ_u(ω) = σ_u² · (2L_u)/(πV) · 1 / (1 + (L_u ω/V)²)
Φ_v(ω) = σ_v² · (L_v )/(πV) · (1 + 3(L_v ω/V)²) / (1 + (L_v ω/V)²)²
```

Both are one-sided and normalised: `∫₀^∞ Φ_u dω = σ_u²` and `∫₀^∞ Φ_v dω = σ_v²` exactly (substitute
`x = Lω/V`; the `u` integral is `(2/π)·arctan`, the `v` integral is `(1/π)(π/4 + 3·π/4)`). **That
check is worth repeating in the implementation's docstring**, because it is what licenses §26.6's
amplitude formula.

#### Units: the MIL spec is in feet, this codebase is in metres

`Params`, the state vector and every altitude in this project are **strict SI** (`params.py`'s
module docstring). The MIL-spec formulas are in **feet** and **ft/s**. Getting this wrong is the
single most likely way to produce a plausible-looking but wrong answer, so the conversion is
specified line by line rather than left to the implementer:

| Quantity | In the formula | In the code | Conversion |
|---|---|---|---|
| `h` (altitude AGL) | ft | m, from `gravity.altitude_agl(y, p)` | `h_ft = h_m / 0.3048` — **once**, at the top of `_dryden_scales` |
| the bracket `0.177 + 0.000823·h` | dimensionless, **requires `h` in ft** | — | the `0.000823` has units of 1/ft; feeding metres here is the error to look for |
| `L_u`, `L_v` | ft (the formula *produces* ft) | m | `L_m = L_ft * 0.3048` on the way out |
| `σ_u`, `σ_v`, `W20` | ft/s | m/s | **no conversion needed.** `σ_u = 0.1·W20/bracket^0.4` is *linear* in `W20` and the bracket is dimensionless, so feeding `W20` in m/s yields `σ_u` in m/s directly |
| `1750 ft`, `1000 ft`, `2000 ft`, `20 ft` | ft | compared/used in ft | keep the band logic **in feet** (§26.5) — never convert the thresholds to metres |
| `ω`, `V` | rad/s, ft/s | rad/s, m/s | the PSDs depend on `V` only through `L ω / V`, and `L/V` is a time; with `L` in m and `V` in m/s it is the same number of seconds as with both in ft. **No conversion needed in the PSD at all.** |

So exactly **two** conversions exist: `h_m → h_ft` on the way in and `L_ft → L_m` on the way out.
Both use the single exact constant `_M_PER_FT = 0.3048` (the international foot is *defined* as
0.3048 m, so this literal is not an approximation), one as a divisor and one as a multiplier.
`(1000.0 * 0.3048) / 0.3048 == 1000.0` exactly in IEEE-754 double (verified), so the round trip does
not shift a band boundary.

**Corollary, and the reason the band logic stays in feet:** `1000 ft` is `304.8 m` exactly in
decimal but `1500 ft` is `457.20000000000005 m` in float. Comparing `h_m` against a metre-valued
threshold would make the boundary depend on which side the constant was rounded to. Comparing
`h_ft` against the literal `1000.0` cannot.

### 26.3 The `Params` fields — three added, two removed

```python
# sim/params.py, replacing the Step-21 `gust_sigma`/`gust_seed` pair in the
# "Step 21: wind tier 1" block (architecture.md SS26.3)

    # Step 46: Dryden turbulence (MIL-F-8785C / MIL-HDBK-1797) for tier-1
    # gusts (architecture.md SS26; latex/research/dryden_turbulence_model.md).
    # Same "unset = bit-for-bit reproduces every prior step" gate convention
    # as `wind_model`/`aero_model`: "none" (the default) means wind.py never
    # builds a realization, never touches the RNG, and `_analytic_wind`
    # returns exactly the mean-profile decomposition. Orthogonal to
    # `wind_model` in the same sense `gravity_direction` is orthogonal to
    # `gravity_model` (architecture.md SS23.1): a second dispatch inside one
    # module, not a product of names -- and the seam a von Karman variant
    # would slot into later with no other change (SS26.13).
    # TIER 1 ONLY. Tiers 2/3 ("sounding"/"field") ignore it entirely, exactly
    # as they ignore today's gusts (SS26.10).
    turbulence_model: str = "none"           # none | dryden

    # Isotropic turbulence intensity above 2000 ft AGL [m/s]. MIL-F-8785C
    # gives no closed form here -- only a probability-of-exceedance chart --
    # so this is set by the user per scenario (the user's own decision, see
    # the research note SS5), not looked up and not a light/moderate/severe
    # preset. 0.0 means "no turbulence above 2000 ft AGL", which also tapers
    # the 1000-2000 ft transition band to zero; it is a legitimate setting,
    # not an error, and the low-altitude band is still driven by W20 (SS26.5).
    turbulence_sigma_high_ms: float = 0.0

    # The single constant airspeed `V` used for the Taylor frozen-turbulence
    # conversion `omega = V*Omega`, for the whole flight [m/s]. A DELIBERATE
    # SIMPLIFICATION with a documented limitation (architecture.md SS26.9):
    # this rocket's true airspeed spans 0 to supersonic, and a realization
    # that tracked it would make the solver's RHS a non-function of its own
    # arguments (SS26.8). Must be > 0 when turbulence_model != "none"; the
    # default is a representative mid-flight airspeed for a small sounding
    # rocket, to be set per scenario, NOT a value with any authority.
    turbulence_ref_speed_ms: float = 100.0

    # RNG seed for the frozen phase draw (architecture.md SS26.8). Renamed
    # from Step 21's `gust_seed` so the family reads as one group; the
    # quantity and its role are unchanged.
    turbulence_seed: int = 0
```

**Removed:** `gust_sigma` and `gust_seed`. `gust_sigma`'s meaning (the standard deviation of a
scalar perturbation on the wind *speed*) no longer exists in the new model — intensity is
`σ_u(h, W20, σ_high)`, derived, not set — and keeping it as a dimensionless overall multiplier
would put two sources of truth on one physical quantity (§26.13). `gust_seed` is renamed, not
deleted. This is the first step since Step 34 (which removed the `linear` gravity model) to remove
anything from the public surface; it is safe because `gust_sigma`/`gust_seed` appear in exactly
three files — `sim/params.py`, `sim/wind.py` and `tests/test_wind.py` lines 223-277 — all three of
which this step edits anyway. **`run.py` and `tools/` never mention either field** (audited by
grep across `*.py`; re-audit before starting, do not take this sentence's word for it).

**No `W20` field.** `W20` is the mean wind speed at 20 ft AGL, which tier 1 **already knows**: it is
the existing power-law profile evaluated at `6.096 m`. Adding a field would create a second source
of truth for the mean wind and let a scenario be internally inconsistent. §26.4 extracts the power
law into `_mean_speed(h, p)` so the expression exists once and both callers share it. Note the
consequence of the existing clamp: with the default `wind_ref_h_m = 10.0 ≥ 6.096`,
`max(h, h_ref) == h_ref` and so **`W20 == p.wind_ref_ms` exactly**; only a scenario with
`wind_ref_h_m < 6.096` makes them differ.

**No `Params` field for the frequency band or the component count.** They are numerics, not scenario
configuration — module-level constants, the same rule §18 states for `R_d`, the ISA layer table and
the WGS84 constants, and the same place `_GUST_N` lives today.

### 26.4 The reference implementation

This is the specification, not a suggestion: the pinned numbers in §26.11 were computed from exactly
this code, and they lock the frequency grid, the phase draw order and the amplitude formula together.
Deviating from any of the three invalidates the pins.

```python
# sim/wind.py -- module-level constants, replacing `_GUST_N`

_M_PER_FT = 0.3048          # the international foot, exactly (not an approximation)
_W20_H_M = 20.0 * _M_PER_FT  # 6.096 m -- the MIL-spec reference height for W20
_H_LOW_FT = 1000.0           # top of the low-altitude regime        (MIL-F-8785C)
_H_HIGH_FT = 2000.0          # bottom of the isotropic free-atmosphere regime
_L_HIGH_FT = 1750.0          # isotropic scale length above _H_HIGH_FT (= 533.4 m)

_TURB_N = 64                 # superposed sinusoids per component (was _GUST_N = 8)
_TURB_PERIOD_MAX_S = 600.0   # longest period in the synthesis band  (omega ~ 0.01047 rad/s)
_TURB_PERIOD_MIN_S = 0.2     # shortest period in the synthesis band (omega ~ 31.42 rad/s)


def _mean_speed(h: float, p) -> float:
    """Tier 1's mean wind speed at altitude `h` AGL [m] -- the power-law
    shear profile, clamped below `p.wind_ref_h_m` rather than extrapolated
    to zero at the ground (architecture.md SS16).

    Extracted from `_analytic_wind` at Step 46 because the Dryden model
    needs the *same* profile evaluated at 20 ft (`_W20_H_M`) for `W20`
    (architecture.md SS26.3): one expression, one implementation, so a
    scenario cannot have two different mean winds. The expression is
    character-for-character Step 21's, so `_analytic_wind` is bitwise
    unchanged by the extraction.
    """
    h_ref = p.wind_ref_h_m
    return p.wind_ref_ms * (max(h, h_ref) / h_ref) ** p.wind_shear_exp


@functools.lru_cache(maxsize=None)
def _turbulence_realization(seed: int):
    """The frozen part of the realization: the frequency grid and the two
    independent phase sets (architecture.md SS26.6). Cached per seed, same
    convention as the Step-21 `_gust_realization` it replaces.

    Only the PHASES are random. The frequencies are a deterministic
    log-spaced grid, exactly as in Step 21 -- a seed needs to decorrelate
    realizations, and independent phases do that; randomising the grid as
    well would only make the pinned numbers depend on 64 more draws.

    `domegas` are the bin widths of the geometric grid, taken between
    geometric-mean bin edges: with ratio `r = (w[-1]/w[0])**(1/(N-1))`, bin
    `i` spans `w_i/sqrt(r) .. w_i*sqrt(r)`, so `dw_i = w_i*(sqrt(r) -
    1/sqrt(r))` and the bins tile `[w_0/sqrt(r), w_-1*sqrt(r)]` with no gap
    and no overlap. `sum(domegas)` therefore equals that span exactly (to
    roundoff), which makes `sum(Phi_i*dw_i)` a genuine Riemann sum of
    `integral Phi dw` -- the property SS26.6's amplitude formula rests on.

    DRAW ORDER IS PART OF THE SPEC: `phases_u` first, then `phases_v`, from
    one `default_rng(seed)`. Swapping them changes every pinned number in
    SS26.11 while breaking no invariant -- which is exactly why it is pinned.
    """
    periods_s = np.geomspace(_TURB_PERIOD_MAX_S, _TURB_PERIOD_MIN_S, _TURB_N)
    omegas = 2.0 * np.pi / periods_s
    r = (omegas[-1] / omegas[0]) ** (1.0 / (_TURB_N - 1))
    domegas = omegas * (np.sqrt(r) - 1.0 / np.sqrt(r))
    rng = np.random.default_rng(seed)
    phases_u = rng.uniform(0.0, 2.0 * np.pi, _TURB_N)
    phases_v = rng.uniform(0.0, 2.0 * np.pi, _TURB_N)
    return omegas, domegas, phases_u, phases_v


def _dryden_scales(h: float, p) -> tuple[float, float]:
    """`(L_u, sigma_u)` in **metres** and **m/s** at altitude `h` AGL
    [metres] -- the MIL-F-8785C/MIL-HDBK-1797 horizontal scale length and
    intensity (architecture.md SS26.2/SS26.5; research note SS3).

    `L_v == L_u` and `sigma_v == sigma_u` in this model, so one pair serves
    both horizontal components. The vertical (`w`) component is out of
    scope (backlog B7, architecture.md SS26.10).

    Units: the MIL formulas are in feet. `h` is converted to feet ONCE here;
    the `0.177 + 0.000823*h_ft` bracket is dimensionless but only with `h`
    in feet, `L` comes out in feet and is converted back, and `sigma` needs
    no conversion because the formula is linear in `W20` (SS26.2's table).
    """
    h_ft = max(h, 0.0) / _M_PER_FT   # clamp: a negative h would give a negative L
    sigma_w = 0.1 * _mean_speed(_W20_H_M, p)      # = 0.1*W20, already m/s

    def _low(hf: float) -> tuple[float, float]:
        bracket = 0.177 + 0.000823 * hf
        return hf / bracket ** 1.2, sigma_w / bracket ** 0.4   # (L [ft], sigma [m/s])

    if h_ft <= _H_LOW_FT:
        L_ft, sigma = _low(h_ft)
    elif h_ft >= _H_HIGH_FT:
        L_ft, sigma = _L_HIGH_FT, p.turbulence_sigma_high_ms
    else:
        # MIL-F-8785C leaves 1000-2000 ft undefined; implementors fill it
        # with a linear interpolation of the PARAMETERS between the two
        # regimes' boundary values (research note SS3.5). At exactly
        # 1000 ft the bracket is 0.177 + 0.823 == 1.0 exactly, so the low
        # anchor is L = 1000 ft and sigma = 0.1*W20 with no arithmetic.
        L_lo, sigma_lo = _low(_H_LOW_FT)
        f = (h_ft - _H_LOW_FT) / (_H_HIGH_FT - _H_LOW_FT)
        L_ft = (1.0 - f) * L_lo + f * _L_HIGH_FT
        sigma = (1.0 - f) * sigma_lo + f * p.turbulence_sigma_high_ms

    return L_ft * _M_PER_FT, sigma


def _no_turbulence(t: float, h: float, p) -> tuple[float, float]:
    """Tier-1 turbulence model "none" (the default): no perturbation at
    all. Returns exact zeros without building a realization or touching the
    RNG -- turbulence off, not merely small, the same off-switch standard
    Step 21's `gust_sigma == 0.0` set (architecture.md SS26.3).
    """
    return (0.0, 0.0)


def _dryden_turbulence(t: float, h: float, p) -> tuple[float, float]:
    """`(u, v)` [m/s]: the along-wind and cross-wind Dryden turbulence
    components at time `t` and altitude `h` AGL [m] (architecture.md SS26).

    A frozen sum of sinusoids, `sigma * sum_i w_i*sin(omega_i*t + phi_i)`,
    with the SHAPE of the weights taken from the Dryden PSD instead of the
    Step-21 half-normal draw:

        k_i = Phi(omega_i) * domega_i        (energy in bin i)
        w_i = sqrt(2*k_i / sum_j k_j)        => sum_i w_i**2 == 2 exactly
                                             => Var[u] == sigma**2 exactly

    The `sqrt(2*Phi*domega)` of textbook random-phase spectral synthesis,
    renormalised by `sum k` so the realised variance is EXACTLY `sigma**2`
    rather than the 81-98 % of it that the finite band captures
    (architecture.md SS26.6 pins the capture fraction and argues the
    choice). Note that the constant prefactors `2L/(pi*V)` and `L/(pi*V)`
    cancel in `k_i/sum k`; they are written out anyway so the code visibly
    matches the cited formula, and SS26.12 asserts the cancellation.

    `sigma**2` IS LEFT OUT of `k_u`/`k_v` below -- it is a common factor and
    cancels in `k_i/sum k` just as the prefactors do, and leaving it out
    keeps `sigma` appearing exactly once, in the final line. The consequence
    for testing, stated because it is the easy mistake: `k_u.sum()` IS the
    capture fraction `integral_band Phi_u dw / sigma_u**2` directly -- do NOT
    divide it by `sigma**2` again when comparing against SS26.11's pinned
    capture table.

    The weights depend on altitude (through `L`, and on `V`), so they are
    recomputed per call and CANNOT live in the `lru_cache` -- only the grid
    and the phases are frozen. That is not a determinism problem: `h` is a
    function of the state, exactly like the mean profile's own `W(h)`
    (architecture.md SS26.8).
    """
    omegas, domegas, phases_u, phases_v = _turbulence_realization(p.turbulence_seed)
    L, sigma = _dryden_scales(h, p)
    V = p.turbulence_ref_speed_ms

    x2 = (L * omegas / V) ** 2
    k_u = (2.0 * L / (np.pi * V)) / (1.0 + x2) * domegas
    k_v = (L / (np.pi * V)) * (1.0 + 3.0 * x2) / (1.0 + x2) ** 2 * domegas
    sum_u, sum_v = k_u.sum(), k_v.sum()
    if sum_u <= 0.0 or sum_v <= 0.0:
        # Only reachable at h <= 0, where the MIL formula gives L == 0 and
        # the whole spectrum collapses to zero energy (sigma stays finite,
        # so this is a genuine 0/0 and must be guarded, not relied on).
        return (0.0, 0.0)

    w_u = np.sqrt(2.0 * k_u / sum_u)
    w_v = np.sqrt(2.0 * k_v / sum_v)
    u = sigma * float(np.sum(w_u * np.sin(omegas * t + phases_u)))
    v = sigma * float(np.sum(w_v * np.sin(omegas * t + phases_v)))
    return (u, v)


# Module-private dispatch dict (architecture.md SS12), nested inside tier 1
# the same way `_GRAVITY_DIRECTIONS` sits beside `_GRAVITY_MODELS` (SS23.1):
# orthogonal to `_MODELS` below, not a product of names. Unknown strings
# raise KeyError at the first call -- no input validation (SS7).
_TURBULENCE_MODELS = {
    "none": _no_turbulence,
    "dryden": _dryden_turbulence,
}
```

and `_analytic_wind`'s body becomes:

```python
    h = altitude_agl(y, p)
    W = _mean_speed(h, p)
    u, v = _TURBULENCE_MODELS[p.turbulence_model](t, h, p)

    delta = np.radians(p.wind_dir_deg - p.azimuth_deg)
    cos_d, sin_d = np.cos(delta), np.sin(delta)
    w_x = -(W + u) * cos_d + v * sin_d
    w_y = -(W + u) * sin_d - v * cos_d
    return (w_x, w_y)
```

`altitude_agl` is **reused, not reinvented** — it is already the first line of `_analytic_wind`
(Step 45, §25) and it is the correct altitude for this model for the same reason it is correct for
the shear profile: the MIL-spec scale lengths and intensities are boundary-layer quantities
referenced to the ground under the vehicle, not to sea level. It is called **once** and the value is
passed down, so this step adds no `altitude_agl` calls at all.

### 26.5 The altitude bands

All three bands key off `h_ft = altitude_agl(y, p) / 0.3048`, i.e. **AGL metres converted to feet**
(§26.2):

| Band | Condition | `L_u = L_v` | `σ_u = σ_v` |
|---|---|---|---|
| Low | `h_ft ≤ 1000` | `h_ft / (0.177 + 0.000823·h_ft)^1.2` ft | `0.1·W20 / (0.177 + 0.000823·h_ft)^0.4` |
| Transition | `1000 < h_ft < 2000` | linear in `h_ft` from `1000 ft` to `1750 ft` | linear in `h_ft` from `0.1·W20` to `σ_high` |
| High | `h_ft ≥ 2000` | `1750 ft` (= `533.4 m`) | `p.turbulence_sigma_high_ms` |

**The transition band is an implementor's fill, not a MIL-spec formula.** MIL-F-8785C/MIL-HDBK-1797
define the low-altitude regime below 1000 ft and the isotropic regime above 2000 ft and leave the
gap undefined; both primary sources in the research note describe linear interpolation between the
two regimes' boundary values as the standard fill (research note §3.5). What is interpolated is the
**two parameters** `(L, σ)`, not the PSD and not the 64 amplitudes — the gap is a gap in the
parameters, so that is where the fill belongs, and interpolating amplitudes would not even give the
same answer (`aᵢ ∝ √Φ`, not `∝ Φ`).

**The low anchor is exact.** At `h_ft = 1000` the bracket is `0.177 + 0.000823·1000 = 1.0` **exactly**
in IEEE-754 double, so `1.0^1.2 == 1.0` and `1.0^0.4 == 1.0`, and the low formula returns
`L_u = 1000 ft` and `σ_u = 0.1·W20` with no residue. The transition band is therefore
`L_ft = 1000 + 0.75·(h_ft − 1000)` and `σ = 0.1·W20 + (σ_high − 0.1·W20)·(h_ft − 1000)/1000` — both
exactly pinnable (§26.11), and both continuous at *both* ends by construction.

**Continuity, and the two kinks.** `L(h)` and `σ(h)` are continuous (C⁰) across both boundaries and
have a slope discontinuity at each. That is fine and has precedent in this codebase: the ISA's
piecewise-linear lapse rates put exactly the same kind of kink in `T(h)`, `ρ(h)` and hence in the
aerodynamic force, at every layer boundary (§14), and `solve_ivp`'s error control handles a C⁰ RHS
without incident. Do **not** smooth it — a smoothing that no source specifies would be this
project's own invention sitting on top of a cited model.

**Below the ground.** `h` is clamped at `0.0` before conversion. At `h = 0` the low formula gives
`L_u = 0` exactly (the numerator is `h_ft`), which collapses the whole spectrum to zero energy while
`σ_u` stays finite at `0.1·W20/0.177^0.4 ≈ 0.1934·W20` — a genuine `0/0` in the renormalisation,
guarded explicitly in `_dryden_turbulence` and pinned by a test (§26.12). Physically this is the
right limit: at the surface there is no eddy left to resolve. Without the clamp, `h_ft < 0` would
give a negative `L` and, below `−215 ft`, a fractional power of a negative bracket, i.e. `nan`.

### 26.6 From PSD to a frozen sum of sinusoids

**The amplitude formula.** Random-phase spectral synthesis: for a one-sided PSD `Φ(ω)` sampled on a
grid `{ωᵢ}` with bin widths `{Δωᵢ}`,

```
aᵢ = sqrt(2·Φ(ωᵢ)·Δωᵢ)      =>   Var[Σ aᵢ sin(ωᵢ t + φᵢ)] = Σ aᵢ²/2 = Σ Φ(ωᵢ)Δωᵢ  ->  ∫Φ dω = σ²
```

(each sinusoid contributes `aᵢ²/2` to the time-variance, and independent phases make the cross terms
vanish in the mean). The sum is a Riemann sum of the PSD integral, so the realised variance tends to
`σ²` as the grid refines and the band widens. This is the standard construction and it is the
*concrete* content of §16's original promise of "amplitudes from a von Kármán/Dryden-like spectrum".

**Renormalisation to exact `σ`.** The implementation does not use `aᵢ` directly; it uses

```
kᵢ = Φ(ωᵢ)·Δωᵢ ,      wᵢ = sqrt(2·kᵢ / Σⱼ kⱼ) ,      u(t) = σ · Σ wᵢ sin(ωᵢ t + φᵢ)
```

which is the same thing rescaled so that `Σ wᵢ² == 2` and hence `Var[u] == σ²` **exactly**, for any
band, any `N`, any altitude and any `V`. (§26.4's code leaves the common `σ²` out of its `kᵢ` — it
cancels in `kᵢ/Σk` — so there the coded `k_u.sum()` *is* the capture fraction below, already divided
by `σ²`. Do not divide twice.) Three reasons:

1. **`σ` stays the physical knob.** `σ_u` is the quantity MIL-F-8785C actually specifies; the band
   and `N` are arbitrary numerics this document invented. Delivering 81 % of a specified intensity
   because of an internal constant is the wrong failure mode; delivering the specified intensity
   with a slightly over-weighted low-frequency tail is the right one.
2. **It makes the band a numerics knob rather than a physics knob.** `_TURB_PERIOD_MIN_S` can be
   raised for solver speed (§26.10) without changing the delivered intensity — only the spectral
   detail.
3. **It buys an exact invariant to test.** `Σ wᵢ²/2 == 1.0` to the last bit is a far sharper check
   than a Monte-Carlo standard deviation, and it is the same trick Step 21 used (`Σ wᵢ² == 1`) —
   just with the `√2` bookkeeping corrected (§26.1 item 5).

The price is quantified, not hand-waved. The **capture fraction** `Σ kᵢ / σ²` — the share of the
true spectrum inside the band — over the plausible envelope `V ∈ {30, 100, 300} m/s`,
`h ∈ {6.1, 30, 100, 304.8, 609.6, 1000} m`, with `N = 64` and periods `600 s … 0.2 s`:

- `u`: **0.871 … 0.979**, worst case `V = 300 m/s` at `h = 20 ft` (where `L_u = 43.77 m` puts the
  break period at `0.92 s`, near the top of the band).
- `v`: **0.809 … 0.982**, same worst case (`Φ_v` has a fatter high-frequency tail than `Φ_u`).

So the renormalisation multiplies amplitudes by `1.01 … 1.11`. It is a correction, not a crutch. The
in-band Riemann sum itself is accurate to `~7·10⁻⁴` of the exact band integral
`(2/π)[arctan(L·ω_hi/V) − arctan(L·ω_lo/V)]` at `N = 64` — i.e. essentially all of the shortfall is
**band truncation**, not discretisation, which is why `N = 64` is enough and `N = 128` barely moves
it (0.9757 vs 0.9770 at the reference state).

**The grid.** `_TURB_N = 64` log-spaced periods from `600 s` to `0.2 s`
(`ω` from `0.0104720` to `31.4159 rad/s`, ratio `r = 1.1355137588494644`, ~18.1 points per decade),
replacing Step 21's 8 points over `3 s … 600 s`. Why these endpoints:

- **`600 s` (low end), unchanged from Step 21.** Longer than any flight, so the lowest components act
  as a quasi-steady wind bias — which is exactly what the low-frequency end of a turbulence spectrum
  *is* for a 60-second flight.
- **`0.2 s` (high end), 15× higher than Step 21's `3 s`.** It has to be: the break frequency is
  `ω_b = V/L_u`, and `L_u` is as small as `22 m` just off the pad, so with `V = 300 m/s` the break
  period is under a second and a band stopping at `3 s` would capture only **20 %** of the `u`
  variance (computed: 0.1955). Going further to `0.05 s` buys ~10 points of capture at the worst
  corner and costs solver steps; `0.2 s` is the chosen compromise and is a module constant so it can
  be revisited without touching `Params`.
- **`N = 64`, 8× Step 21's.** 8 points over the wider band would be ~2 points per decade, where the
  Riemann sum overshoots (capture `1.0416` at the reference state — a sum that claims *more* energy
  than the spectrum has). 64 is where the sum has converged to the band integral.

**Solver cost — measure it, do not assume it.** A 15× higher top frequency means a stiffer-looking
RHS. The scaling: `wᵢ ∝ √(Φ(ωᵢ)Δωᵢ)` with `Φ ∝ ω⁻²` and `Δωᵢ ∝ ωᵢ` gives `wᵢ ∝ ω^(−1/2)` in the
high-frequency tail, so the fifth derivative of the forcing scales as `w·ω⁵ ∝ ω^4.5` and RK45's step
size as `ω^(−0.9)`: expect roughly an order of magnitude more steps on a turbulent run than on a
Step-21 gusty one. At today's runtimes (a full flight is milliseconds to a second) that is
affordable, but it is **not zero**, so the step's checklist requires recording the measured
wall-clock of one turbulent run (§26.12). Runs with `turbulence_model = "none"` — including every
committed scenario and every existing test — are untouched.

### 26.7 Composition into `(w_x, w_y)`: the along/cross decomposition

Dryden's `u` is by construction the component **along the mean wind** and `v` the component
**perpendicular to it, horizontally**. With `δ = wind_dir_deg − azimuth_deg` and the flight-plane
axes of §16 (`+x` downrange along the azimuth, `+y` the out-of-plane axis, `x̂` rotated −90°):

```
ê_u = (−cos δ, −sin δ)        unit vector along the mean FLOW (wdir blows FROM)
ê_v = ( sin δ, −cos δ)        ê_u rotated +90° in the (x, y) plane;  ê_u · ê_v = 0 identically

(w_x, w_y) = (W + u)·ê_u + v·ê_v
           = ( −(W + u)·cos δ + v·sin δ ,  −(W + u)·sin δ − v·cos δ )
```

Three things to note, each of which is the reason this is right rather than merely plausible:

1. **The `u` term reduces to Step 21's structure exactly.** `−(W + u)cos δ` is Step 21's
   `−(W + Δ)cos δ`. Adding the along-wind component to the speed before decomposition is not a
   leftover — it is *correct*, because `u` is defined along the mean wind. Step 21's error was never
   the placement of the scalar; it was the weights, the missing altitude dependence, and the missing
   `v`.
2. **`v` is genuinely new and genuinely perpendicular.** Only `v` can turn the wind vector. It is
   the first thing in this project to perturb wind *direction* at all.
3. **The non-negativity clamp is dropped** (`max(W + Δ, 0.0)` → nothing). With a vector perturbation
   along `ê_u`, a negative `W + u` is the *correct* physical statement "the gust is stronger than the
   mean wind and the local flow has reversed" — the 180° flip the clamp was protecting against is
   the right answer, not a bug. The clamp was a symptom of perturbing a scalar speed. Consequences,
   named: (a) with `turbulence_model = "none"` the clamp's removal is a no-op for any `W ≥ 0`, which
   is every scenario with `wind_ref_ms ≥ 0`; (b) a **negative** `wind_ref_ms` is not a supported
   input (§7, no input validation) — today's clamp happens to silently zero it, after this step it
   would be a reversed mean wind. Not guarded, just recorded.
4. **The handedness of `ê_v` is a free choice, taken and documented.** `v` is zero-mean and
   symmetric, so the opposite sign gives a statistically identical model with different pinned
   numbers. `+90°` in the `(x, y)` plane is chosen because it makes `(ê_u, ê_v)` right-handed in the
   same axes §16 already uses, and `ê_u · ê_v = 0` is an identity worth asserting (§26.12).

**`v` has zero effect on any trajectory this simulator can integrate today** — `wind_inertial`
discards the cross-plane component (§16's 2D projection limitation, backlog B6), so `w_y` and now
the `v` that feeds it are Phase-3 scaffolding, exposed through `wind_horizontal_enu` and nothing
else. State this plainly: Step 46's effect on *simulated flights* is entirely in `u`. `v` is
implemented anyway for the same reason `w_y` already is — it costs three lines, it is the half of
the model that makes "Dryden" an honest label, and Phase 3 picks it up unchanged.

### 26.8 Determinism — what it does and does not constrain

Step 21's hard constraint carries over **unchanged and non-negotiable**: `solve_ivp` evaluates the
RHS at arbitrary, repeated and *rejected* times, so the turbulence must be a deterministic pure
function of its arguments. A fresh RNG draw per call makes the RHS a non-function, destroying
step-size control and reproducibility.

What that forbids, and what it does **not**, needs saying precisely, because this step moves work
out of the cache and a careless reading would call that a violation:

- **Forbidden:** any RNG consumption outside `_turbulence_realization`, which is called once per
  seed and `lru_cache`d. `_dryden_turbulence` must contain no `rng` of any kind.
- **Forbidden:** any dependence on call *history* — no accumulators, no "last `t`", no filter state.
  This is what rules out the textbook state-coupled Dryden implementation (white noise through a
  speed-varying linear filter), and it is the deeper reason for §26.9's fixed reference speed.
- **Allowed, and already the case:** dependence on the **state** `y` through `h = altitude_agl(y, p)`.
  An ODE right-hand side is a function of `(t, y)` by definition; tier 1's mean profile `W(h)` has
  depended on `y` since Step 21. So recomputing `(L, σ)` and the 64 weights per call from `h` is
  not a weakening of the constraint — the function `(t, y, p) ↦ (u, v)` is single-valued, and that
  is the whole requirement.
- **Consequence for the cache:** only `(omegas, domegas, phases_u, phases_v)` are frozen per seed.
  The weights are altitude-dependent and must **not** be cached (and cannot be: `Params` is not
  hashable across every field, and `h` is continuous — §15, "do not optimise").

### 26.9 The reference-airspeed limitation, stated

**The user's decision (research note §5, option 4.1a):** one fixed `turbulence_ref_speed_ms` supplies
the constant `V` of the Taylor frozen-turbulence conversion `ω = V·Ω` for the whole flight.

This is a **known, deliberate fiction**, recorded here to the same standard as §16's 2D-crosswind
projection and backlog B7's vertical wind — the two limitations this project already names rather
than hides:

> Dryden's temporal PSDs describe what a vehicle flying at airspeed `V` through a spatially frozen
> turbulence field measures. This rocket's airspeed spans zero at the pad to supersonic at burnout,
> so for most of the flight the `V` driving the spectral shape is not the rocket's airspeed. The
> turbulence field it flies through is a legitimate Dryden field; the *vehicle* sampling it is
> modelled as one flying at `turbulence_ref_speed_ms` throughout.

The alternative — a filter driven by the instantaneous true airspeed, which is the "gold standard"
and what flight simulators do — is incompatible with §26.8's determinism requirement, since the
airspeed at time `t` is part of what the solver is still solving for and is re-evaluated at rejected
steps. That is not a limitation of this design; it is a property of putting a stochastic process
inside an adaptive-step ODE solve, and Step 21 already designed around it for a simpler model.

**The good news, and it is worth stating because it bounds the damage precisely.** After the
renormalisation of §26.6, the constant prefactors `2L/(πV)` and `L/(πV)` cancel out of the weights,
so **`V` and `L` enter the model only through the ratio `L/V`** — a time, the eddy-crossing period.
Therefore:

- `V` has **no effect whatever on the turbulence intensity**. `σ_u` is `V`-free, and the realised
  variance is exactly `σ_u²` for any `V > 0`. The MIL-spec intensity profile is delivered faithfully.
- `V` affects **only where the spectrum's knee sits in frequency** — i.e. whether the turbulence the
  rocket meets is dominated by 30-second swells or 1-second buffets. Doubling `V` halves the break
  period and nothing else.

That is a far smaller and far more legible error than "the whole spectrum is wrong", and it gives a
concrete rule for choosing the field: **set `turbulence_ref_speed_ms` to the airspeed over the part
of the flight where turbulence matters most to the question being asked** — low-altitude airspeed
(tens of m/s) when the question is rail-exit/early weathercocking, mid-burn airspeed (hundreds of
m/s) when it is max-Q loads. `V` must be `> 0`; there is no validation (§7), and `0.0` would produce
`inf`/`nan` rather than an error.

Promoted to the backlog as **B11** (state-coupled turbulence) rather than deferred silently.

### 26.10 Scope — what this step does NOT do

- **No vertical (`w`) component.** The user's standing deferral of backlog **B7** covers it (research
  note §4.3/§5). `wind_inertial`'s `w_z` stays exactly `0.0`, the function is **not edited**, and
  `_dryden_scales` returns one `(L, σ)` pair for the two horizontal components only. `Φ_w` is in the
  research note (§3.3) and is structurally identical to `Φ_v` with `L_w = h`, `σ_w = 0.1·W20`, so
  B7 can pick it up for a handful of lines if it is ever scheduled — that is a note, not a plan.
- **Tiers 2 and 3 are untouched.** `_sounding_wind` and `_field_wind` get no turbulence, exactly as
  they have no gusts today. This is not an oversight and it is not scope creep avoided by accident:
  the MIL-spec intensity profile is keyed on `W20` and on *AGL* altitude, and the measured tiers
  carry neither (they are MSL-referenced profiles from a station whose own 20 ft wind is not in the
  file, §25's own argument for why those tiers read `altitude_msl`). Adding turbulence there needs a
  decision about where `W20` comes from and whether the sounding's own measured shear already
  contains part of what Dryden would add. Promoted to backlog **B10**; **do not** expand this step
  to cover it, and do not add a `turbulence_model` branch to those two functions.
- **No change to the three public functions' signatures.** `wind_horizontal_enu(t, y, p)`,
  `wind_inertial(t, y, p)` and the `_MODELS` tier dispatch are untouched; `_TURBULENCE_MODELS` is a
  second, nested dispatch private to tier 1.
- **No von Kármán variant.** The scale lengths and intensities are shared between the two models and
  only the PSD shape differs (research note §2), so `"von_karman"` is a one-function addition to
  `_TURBULENCE_MODELS` later. Not this step — its PSD has a non-rational `^(5/6)` form that has not
  been verified against a primary source here, and verifying it is a research pass, not a spec pass.
- **No MIL-F-8785B continuous closed form.** The research note (§3.5) flags
  `L_u = L_FA^(2/3)·h^(1/3)`, `L_w = h` as an alternative that covers the whole boundary layer with
  no stitched gap and so avoids the 1000-2000 ft interpolation entirely. Attractive, but it is a
  *different standard* from the one the user asked to verify, its PSD pairing was not checked
  against a source read in full, and swapping it in would silently change every number here.
  Recorded in §26.13 and as a candidate backlog item, not adopted.
- **No light/moderate/severe presets.** The user's decision (research note §4.2/§5):
  `turbulence_sigma_high_ms` is set directly. No chart, no lookup table, no named severity strings.
- **No turbulence in the `Params` for the band or `N`** (§26.3), and **no caching** of the per-call
  weights (§26.8).
- **No new `run.py` scenario, no new sweep, no plotting change.** The committed scenario is
  `wind_model = "none"`, so its printed summary, both sweep tables and all four figures are
  unchanged. Adding a turbulence sweep so the new behaviour is visible in the shipped output is a
  reasonable follow-up and is explicitly not this step.
- **`PROJECT-STATUS.md`'s recorded tables are not rewritten** (and note the Step-45 finding already
  recorded there and in roadmap Step 46's predecessor: the Step-27 block has been stale since
  somewhere in Steps 28-44, unrelated to this step and not to be absorbed into it).
- **No LaTeX edit by the developer.** `latex/sections-ai/models.tex` §Wind > Analytic documents the
  Step-21 placeholder and needs updating, but `main.tex` and its sections are the **user's**
  document and the source of truth (working rule 1). See §26.14 — this is an input to be resolved
  with the user, not a file for the implementer to rewrite. (The update itself landed 2026-10-13 in
  the Phase 2.14 LaTeX sync pass, requested by the user; §26's preamble records it. This bullet's
  rule still stands as written for any future step.)
- **No `float | np.ndarray` vectorisation promise.** Unlike `altitude_agl` (§25), the turbulence
  functions are scalar-only: `max(h, 0.0)` and the `k.sum()` renormalisation are both scalar-shaped,
  and nothing plots or post-processes turbulence over a `(6, N)` history. If that is ever wanted it
  is a separate change with its own test.

### 26.11 Pinned numbers

**All values below were computed from §26.4's reference implementation while writing this section.**
They lock together the frequency grid, the phase draw order, the amplitude formula and the unit
conversions — four independent things, any one of which can be got wrong while every invariant still
passes. Reproduce them; if the implementation disagrees, the implementation is wrong unless it can
point at the specified line it followed differently. Compare with `rel_tol = 1e-12` (64-term sums
with cancellation; not bit-for-bit across expression orderings).

**Unit-conversion anchors.**

| ft | m (float) |
|---|---|
| `20` | `6.096` exactly |
| `1000` | `304.8` exactly |
| `1500` | `457.20000000000005` ← **why the band logic stays in feet** (§26.2) |
| `1750` | `533.4` exactly |
| `2000` | `609.6` exactly |

and `(1000.0 * 0.3048) / 0.3048 == 1000.0` exactly.

**`(L_u, σ_u)` versus altitude**, `W20 = 8.0 m/s`, `turbulence_sigma_high_ms = 2.0 m/s`:

| `h` [m AGL] | `h` [ft] | `L_u` [m] | `σ_u` [m/s] | Band |
|---|---|---|---|---|
| `0.0` | `0.000` | `0.000000000` | `1.599192265` | low (degenerate — the §26.5 guard) |
| `6.096` | `20.000` | `43.765867198` | `1.543311220` | low |
| `30.0` | `98.425` | `152.464823369` | `1.375433044` | low |
| `100.0` | `328.084` | `262.794137166` | `1.103981708` | low |
| `304.8` | `1000.000` | `304.800000000` | `0.800000000` | low boundary — **exact**, `bracket == 1.0` |
| `457.2` | `1500.000` | `419.100000000` | `1.400000000` | transition midpoint — **exact** |
| `609.6` | `2000.000` | `533.400000000` | `2.000000000` | high boundary — **exact** |
| `1000.0` | `3280.840` | `533.400000000` | `2.000000000` | high (isotropic, altitude-independent) |
| `5000.0` | `16404.199` | `533.400000000` | `2.000000000` | high |

Read the physics in the column: intensity falls from `0.1934·W20` at the ground to `0.1·W20` at
1000 ft, then rises to whatever the user set for the free atmosphere; scale length grows from zero at
the surface to the isotropic `533.4 m`.

**The frequency grid** (`_TURB_N = 64`, periods `600 … 0.2 s`):

```
omega_min = 0.010471975511965976      omega_max = 31.41592653589793       rad/s
r         = 1.1355137588494644        18.1184 points per decade
bin edges = 0.009827259348288165  ..  33.476964605289695                  rad/s
sum(domegas) = 33.46713734594138   ==  edge span 33.46713734594141   (to roundoff)
```

**The headline state.** `t = 3.7 s`, `wind_model = "analytic"`, `turbulence_model = "dryden"`,
`wind_ref_ms = 8.0`, `wind_ref_h_m = 10.0`, `wind_shear_exp = 0.143`, `wind_dir_deg = 45.0`,
`azimuth_deg = 90.0`, `turbulence_sigma_high_ms = 2.0`, `turbulence_ref_speed_ms = 100.0`,
`turbulence_seed = 42`, `gravity_direction` default (`"parallel"`, so `h = −y[Z]`). `W20 = 8.0`
exactly for all three (the `wind_ref_h_m = 10 ≥ 6.096` clamp, §26.3):

| `h` [m] | band | `W(h)` | `L_u` | `σ_u` | `u` | `v` | `w_x` | `w_y` |
|---|---|---|---|---|---|---|---|---|
| `50.0` | low | `10.070306700894818` | `202.28958863483254` | `1.2747484599502108` | `−1.5022093894541353` | `−3.3434568705794283` | `−3.694378684994467` | `8.422740736577401` |
| `457.2` | transition | `13.819272372755785` | `419.1` | `1.4` | `−1.6001656723976778` | `−2.9278856678836176` | `−6.569885397565788` | `10.710541018164609` |
| `1000.0` | high | `15.455746536135392` | `533.4` | `2.0` | `−2.3168833092956147` | `−3.75706117623484` | `−6.633935849732609` | `11.947222719829334` |

The `h = 50 m` row's **no-turbulence** counterpart, for the size of the effect:
`w_x = −7.120782156831056`, `w_y = +7.120782156831056`. So at this instant the turbulence moved the
along-plane wind by `+3.43 m/s` — about `2.7 σ_u`, a high-but-legitimate excursion for a 64-component
frozen realization (the realization's own maximum over a long sample is `4.08 σ`).

**Seed sensitivity** (same `h = 50 m` state): `u, v =`

| seed | `u` | `v` |
|---|---|---|
| `0` | `−1.1724777592914615` | `+0.6459965707657919` |
| `7` | `−1.1730878365895998` | `−0.09124657436161275` |
| `42` | `−1.5022093894541353` | `−3.3434568705794283` |

**Capture fractions** (the share of the true variance inside the band, `∫_band Φ dω / σ²` — which is
`k_u.sum()` / `k_v.sum()` **as §26.4 codes them**, since the `σ²` is factored out there; do not
divide by `σ²` again), `W20 = 8`, `σ_high = 2`:

| `V` [m/s] | `h = 6.096 m` | `h = 30 m` | `h = 100 m` | `h = 304.8 m` | `h = 609.6 m` |
|---|---|---|---|---|---|
| `30` — `u` | `0.978513` | `0.965162` | `0.943833` | `0.935447` | `0.889474` |
| `100` — `u` | `0.954551` | `0.978664` | `0.977000` | `0.975371` | `0.963768` |
| `300` — `u` | `0.871176` | `0.960118` | `0.973492` | `0.975605` | `0.978856` |
| `30` — `v` | `0.976561` | `0.979150` | `0.969949` | `0.965981` | `0.942917` |
| `100` — `v` | `0.934295` | `0.977198` | `0.981597` | `0.981778` | `0.978625` |
| `300` — `v` | `0.809066` | `0.943062` | `0.965390` | `0.969432` | `0.979070` |

At the headline state (`h = 50 m`, `V = 100`): `u` capture `0.9786190127603707`, `v` capture
`0.9802450406408341`. The exact band integral for `u` at `(h = 100 m, V = 100)` is `0.976327` against
the grid's `0.977000` — a `6.9·10⁻⁴` discretisation error, confirming that the shortfall from `1.0` is
band truncation, not grid coarseness (§26.6).

**Band/`N` sensitivity**, kept as a record of why the constants are what they are:

| `N` (periods `600…0.2 s`, `h = 100 m`, `V = 100`) | `u` capture |
|---|---|
| `8` | `1.041642` ← Step 21's `N` over this band: the Riemann sum **overshoots** |
| `16` | `0.992594` |
| `32` | `0.980611` |
| `64` | `0.977000` ← chosen |
| `128` | `0.975722` |

| shortest period | `u` capture at `20 ft`, `V = 100` | at `20 ft`, `V = 300` |
|---|---|---|
| `3.0 s` (Step 21's) | `0.4830` | `0.1955` ← the reason the band had to move |
| `1.0 s` | `0.7858` | `0.4877` |
| `0.5 s` | `0.8894` | `0.6965` |
| `0.2 s` | `0.9546` | `0.8712` ← chosen |
| `0.05 s` | `0.9875` | `0.9678` |

**Exact invariants** (these are the sharp ones — assert them to the last bit, not with a tolerance
beyond `1e-15`): `Σ w_u²/2 == 1.0` and `Σ w_v²/2 == 1.0` (measured `0.9999999999999999` and `1.0` at
the headline state); `0.177 + 0.000823·1000.0 == 1.0`; the prefactor-cancellation check — replacing
`2L/(πV)` by any other positive constant leaves `w_u` unchanged (measured max abs difference
`5.55·10⁻¹⁷`).

**The negative pin.** With `turbulence_model = "none"` (the default) every existing result is
unchanged: `python run.py`'s printed summary, both sweep tables and all four figures, and the whole
test suite. See §26.12 for the exact sense in which "unchanged" is meant (`np.array_equal`, with the
one sign-of-zero caveat spelled out).

### 26.12 Checks for the step

**Regression (the headline check).**

- The **entire existing suite passes unmodified**, with exactly two permitted exceptions:
  `tests/test_wind.py`'s `test_gust_is_deterministic_bit_for_bit_across_repeated_calls` and
  `test_gust_sigma_zero_reproduces_no_gust_analytic_profile_exactly` (lines ~223-277), which are
  **rewritten against the new fields** — they pass `gust_sigma`/`gust_seed` to `Params` and would
  fail at construction. *Any other test needing an edit is a bug in the step.* In particular the
  eight other wind tests, which all use `wind_model` without gusts, must pass untouched.
- **They are rewritten, not deleted, and not converted to pinned-value tests of the old scheme.**
  The two tests assert *properties* — bit-for-bit determinism across repeated calls, per-seed
  reproducibility, seed-sensitivity, and the exact off-switch — and every one of those properties
  survives this step and must be re-asserted against `turbulence_model`/`turbulence_seed`. There is
  no prior "real" value to preserve: the half-normal weighting was itself a placeholder (§26.1), so
  no pinned gusty number exists anywhere in the repo to regress against.
- A full `run_sim` on **both** integrator paths (RK45 and `method="rk4"`) with
  `turbulence_model = "none"` and `wind_model = "analytic"` reproduces the pre-Step-46 `events`, `t`
  and `y` arrays (`np.array_equal`). Repeat with `wind_model` `"none"`/`"sounding"`/`"field"` so
  every tier is covered — tiers 2/3 must be *provably* untouched, since §26.10 says they are.
- `python run.py` output is byte-identical to the pre-step run (the committed scenario is
  `wind_model = "none"`; diff the captured stdout, do not eyeball it).

**The "none" path's exactness, stated precisely rather than claimed.** `_analytic_wind`'s new body
evaluates `-(W + 0.0)*cos_d + 0.0*sin_d` where Step 21's evaluated `-W*cos_d`. `x + 0.0 == x`
exactly for every finite `x` in IEEE-754, and `0.0 * y == ±0.0`, so the two expressions agree
**bitwise except possibly for the sign bit of an exact zero** — i.e. when `W == 0` or `cos δ == 0`
the result may be `+0.0` where it was `−0.0`. `np.array_equal` treats those as equal, every
downstream arithmetic operation (`v_rel = v − v_w`, then multiplication by `q`) is insensitive to it,
and nothing in the package calls `copysign` or divides by `w_x`. So: assert with `np.array_equal`,
and state this caveat in the test's docstring rather than discovering it. Extracting `_mean_speed`
is separately exact — the expression is character-for-character Step 21's on the same operands.

**Determinism (Step 21's constraint, carried over).**

- `wind_inertial(t, y, p)` twice with identical arguments and `turbulence_model = "dryden"` is
  bit-for-bit identical (`np.array_equal`). Same for two different `turbulence_seed` values, each
  self-consistent.
- A full `run_sim` with turbulence on, run twice, gives bit-for-bit identical `events`/`t`/`y`. This
  is the check that actually exercises the solver's rejected steps, which the unit test cannot.
- `_dryden_turbulence`'s source contains no RNG: assert structurally if convenient (e.g. patch
  `np.random.default_rng` to raise and confirm a *second* call at a different `t` with the same seed
  still works, the realization having been cached by the first).
- `_turbulence_realization` is `lru_cache`d: two calls with the same seed return the **same objects**
  (`is`), and the arrays are never mutated in place by `_dryden_turbulence` (it must not write into
  the cached arrays — a real hazard with numpy and the one way to poison every later call).

**The off switch.**

- `turbulence_model = "none"` gives exactly the mean-profile decomposition for *any*
  `turbulence_seed`, `turbulence_sigma_high_ms` and `turbulence_ref_speed_ms`, including values that
  would be nonsense for the dryden path (`turbulence_ref_speed_ms = 0.0`): none of them may be
  consulted. Build two `Params` differing only in those three and assert `np.array_equal`.
- An unknown `turbulence_model` raises `KeyError` on the first `wind_inertial` call, with no silent
  fallback (§7; the same assertion `_MODELS` and `_GRAVITY_DIRECTIONS` already carry).
- `turbulence_model = "dryden"` with `wind_model` set to `"none"`, `"sounding"` or `"field"` changes
  **nothing** — turbulence is tier-1-only (§26.10). Assert it for all three, with a seed and
  intensity that would be clearly visible in tier 1.

**Units and bands — where the real mistakes live.**

- `_dryden_scales` matches §26.11's nine-row table (`rel_tol = 1e-12`), including the three **exact**
  boundary rows. The `h = 304.8 m` row is the sharpest single check in the step: it simultaneously
  pins the metre→foot conversion, the `0.177 + 0.000823·h` bracket and the band comparison, and it
  does so against the round number `L_u = 304.8 m`, `σ_u = 0.1·W20` that only comes out if all three
  are right.
- **The foot/metre guard:** feeding metres into the bracket instead of feet gives
  `L_u(h = 100 m) = 532.4 m` instead of `262.79 m` — a factor of 2 the other invariants would not
  catch. Assert the `h = 100 m` row explicitly and say so in the docstring.
- Continuity at both boundaries: `_dryden_scales(304.8 − ε)` → `_dryden_scales(304.8 + ε)` and the
  same at `609.6`, agreeing to `O(ε)` in both `L` and `σ`, for `ε = 1e-6`. Approach each boundary
  from both sides; the `≤`/`≥` comparisons must not create a step.
- Monotonicity through the transition band: `L_u` strictly increasing and `σ_u` monotone from
  `0.1·W20` to `σ_high` across `1000 → 2000 ft` (for `σ_high > 0.1·W20`; assert the reverse ordering
  too with a small `σ_high`, to catch a swapped interpolation weight).
- `σ_high` is read **only** above 1000 ft: sweeping `turbulence_sigma_high_ms` leaves
  `_dryden_scales(h)` exactly unchanged for any `h_ft ≤ 1000`, and changes it for `h_ft > 1000`.
  The mirror check: sweeping `wind_ref_ms` (hence `W20`) leaves `σ_u` exactly unchanged for
  `h_ft ≥ 2000` and scales it *linearly* below 1000 ft (double `W20`, double `σ_u`, exactly — the
  formula is linear in `W20`, and this is a cheap, sharp test).
- `W20` comes from the shared profile: with the default `wind_ref_h_m = 10.0`,
  `σ_u(h_ft = 1000) == 0.1 * p.wind_ref_ms` **exactly**; with `wind_ref_h_m = 2.0` it instead equals
  `0.1 * p.wind_ref_ms * (6.096/2.0)**p.wind_shear_exp` — the check that `_mean_speed(_W20_H_M, p)`
  was used and not a hardcoded `wind_ref_ms`.
- `h ≤ 0`: `_dryden_scales(0.0, p)` gives `L_u == 0.0` exactly with `σ_u > 0`, and
  `_dryden_turbulence(t, 0.0, p)` returns exactly `(0.0, 0.0)` via the `Σk <= 0` guard — for several
  `t`, and for `h = −5.0` too (the clamp), with no `nan`/`inf` anywhere. Assert `np.isfinite`.
- `h` above 2000 ft is altitude-**independent**: `_dryden_scales(609.6)` ==
  `_dryden_scales(30_000.0)` exactly.

**The spectrum and the amplitude formula.**

- **The exact variance identity:** `Σ w_u² == 2.0` and `Σ w_v² == 2.0` to within `1e-15` relative,
  at a dozen `(h, V, σ_high, W20)` combinations spanning all three bands. This is the invariant that
  replaces Step 21's `Σwᵢ² == 1` and corrects its `√2` (§26.1 item 5) — its docstring should say so.
- **The PSD normalisation it rests on:** `∫₀^∞ Φ_u dω == σ_u²` and `∫₀^∞ Φ_v dω == σ_v²`, checked
  numerically (`scipy.integrate.quad` or a fine grid out to `1000·V/L`) to ~`1e-6` relative. This is
  the test that would catch a mistranscribed PSD, which no other check here would.
- **Prefactor cancellation:** multiplying `2L/(πV)` by an arbitrary positive constant leaves `w_u`
  unchanged to `~1e-16` (measured `5.55e−17`) — documents §26.9's bound on the reference-speed
  fiction *as a test*, not just as prose.
- **Spectral shape, not just energy:** the weights must actually fall off. Assert
  `w_u[i] / w_u[j] ≈ sqrt(Φ_u(ω_i)Δω_i / (Φ_u(ω_j)Δω_j))` for a few `(i, j)`, and the qualitative
  consequence: `w_u` is **not** monotone (it rises as `√Δω ∝ √ω` below the knee and falls as
  `ω^(−1/2)` above it, peaking near `ω_b = V/L`), while `w_u[-1] < w_u[peak]`. A test that only
  checks `Σw² == 2` would pass with Step 21's half-normal weights.
- **Band-shape independence of `σ`:** halving `_TURB_PERIOD_MIN_S` (monkeypatched) changes the
  realised `u(t)` but leaves `Σ w_u²/2 == 1` exactly — the renormalisation's whole point (§26.6).
- **The break frequency is where the model says it is** (`ω_b = V/L_u`): the weight peak's index
  moves with `V` and with `h` in the predicted direction, and doubling `V` halves the break period.
  **This test also pins the `L_v` convention** — see §26.14's flagged risk: if a later reading shows
  the source's `Φ_v` is written in the `2L_v` convention, this is the test that goes red, which is
  exactly what should happen.
- **Capture fractions** match §26.11's grid to `rel_tol = 1e-9`, and the exact-band-integral
  cross-check `(2/π)[arctan(L ω_hi/V) − arctan(L ω_lo/V)]` agrees with the grid sum to `< 1e-3`
  absolute for `u` at `(h = 100 m, V = 100)`.

**The vector composition (§26.7).**

- `ê_u · ê_v == 0` and `‖ê_u‖ == ‖ê_v‖ == 1` to `1e-15` for a sweep of `δ` — assert on the
  decomposition's geometry, not just on the final numbers.
- **The `u`-only reduction:** with `v` forced to zero (a monkeypatched `_dryden_turbulence` returning
  `(u, 0.0)`), `(w_x, w_y)` equals Step 21's `−(W+u)cos δ, −(W+u)sin δ` **exactly** — the check that
  the along-wind component is still composed the old way (§26.7 item 1).
- **The `v`-only rotation:** with `u` forced to zero and `v > 0`, the wind vector's **magnitude**
  grows as `√(W² + v²)` and its direction rotates, and the magnitude is identical for `±v`. This is
  the check that `v` is genuinely perpendicular rather than a second scalar on the speed — the
  specific defect of the Step-21 model.
- **No clamp:** with `turbulence_ref_speed_ms`, `σ_high` and `W20` chosen so that `u < −W` at some
  `t` (e.g. a small `wind_ref_ms` with a large `σ_high` at high altitude), `w_x` **changes sign**
  relative to the mean wind instead of saturating at zero. Search a few hundred `t` values for such
  an instant and assert it exists and is not clamped — the explicit test of §26.7 item 3, so a future
  reader does not "restore" the clamp.
- **`w_z` is still exactly `0.0`:** `wind_inertial(...)[1] == 0.0` with turbulence fully on, at
  several `(t, h)` — the B7 guard (§26.10), asserted as `== 0.0`, not `isclose`.
- **`v` is still discarded by `wind_inertial`:** `wind_horizontal_enu` returns a nonzero second
  component where `wind_inertial` shows no trace of it. Assert that `wind_inertial`'s `w_x` equals
  `wind_horizontal_enu`'s first element exactly, for a turbulent state.
- **The headline state:** `_dryden_scales`, `u`, `v`, `w_x`, `w_y` match §26.11's three-row table at
  `t = 3.7 s`, `h ∈ {50, 457.2, 1000} m`, `seed = 42` (`rel_tol = 1e-12`), and the three seeds in
  §26.11's seed table give those `(u, v)` pairs.

**Physical sanity (the step's "does it behave like turbulence" checks).**

- Over a long sample (`t` on a fine grid out to ~`10 × 2π/ω_min`), `u(t)` has sample mean `≈ 0`
  (`|mean| < 0.01 σ`; measured `−5.8e−4` against `σ = 1.27`) and sample standard deviation within
  1 % of `σ_u` (measured `1.2773` against `1.2747`). Use a loose tolerance and say why: the exact
  identity is on `Σw²`, and a finite sample of a quasi-periodic signal is not the ensemble.
- `max |u|` over that sample is a few `σ`, not tens (measured `4.08 σ`) — a 64-component frozen sum is
  quasi-Gaussian, and a wildly larger figure means the weights are not normalised.
- Intensity ordering with altitude, at fixed `W20` and a `σ_high` above the surface value: `σ_u`
  decreases from the ground to 1000 ft, then increases to `σ_high` — assert the ordering of three
  sampled altitudes rather than the values, as an independent readable statement of the profile.
- A full `run_sim` with turbulence on reaches a **different** apogee than the same scenario with
  `turbulence_model = "none"`, and a different one again for a different seed: the model is actually
  coupled into the flight (and the two must bracket each other sensibly, not differ by 10×).

**Cost (do not skip this one).**

- Record the measured wall-clock of one full `run_sim` with `turbulence_model = "dryden"` against the
  same scenario with `"none"`, in the step's commit message or tracker note. §26.6 predicts roughly
  an order of magnitude more solver steps. If it is worse than ~30× or the run fails to converge,
  **stop and report** — raising `_TURB_PERIOD_MIN_S` is the dial, and it is a module constant
  precisely so this is a one-line decision rather than a redesign. Do not silently change the
  constant and leave the pins stale; it invalidates §26.11.

### 26.13 Rejected options

| Rejected | Why |
|---|---|
| A state-coupled Dryden filter (white noise through a linear filter driven by the instantaneous true airspeed) — the "gold standard" | Incompatible with Step 21's determinism constraint, which this step inherits unchanged (§26.8): the airspeed at `t` is part of what the solver is still solving for, and the RHS is re-evaluated at repeated and rejected times. Backlogged as **B11**. |
| Research-note option 4.1(b): choose temporal frequencies directly and skip the `ω = V·Ω` conversion entirely | **Decided against by the user** (research note §5) in favour of a fixed reference speed. It would also have left `V` in the PSD prefactors with no defined value. |
| Keeping `gust_sigma` as an overall dimensionless multiplier on the Dryden intensity | Two sources of truth for one physical quantity: MIL-F-8785C *specifies* `σ_u`, and a user multiplier on top of it makes the model's headline output un-citable. It would also silently change the field's units from m/s to dimensionless while keeping its name. Removed instead (§26.3). |
| `turbulence_sigma_high_ms = 0.0` as the on/off gate, matching `gust_sigma = 0.0` | Genuinely ambiguous: the **low**-altitude band does not depend on that field at all (it comes from `W20`), so "the high-altitude intensity is zero" and "turbulence is off" would be the same setting with two different meanings. §21 already rejects inferring physics from anything but an explicit model string. |
| Hardcoded light/moderate/severe `σ_high` presets from MIL-F-8785C's exceedance chart | **User decision** (research note §4.2/§5): a directly-set field, no presets. The chart was also never read against a primary source in the research pass, so shipping numbers from it would be exactly the unverified-formula hazard §26.2 exists to avoid. |
| The vertical (`w`) component | Backlog **B7**, deferred by the user, and `Φ_w` is the same territory (research note §4.3/§5). `w_z` stays `0.0` (§26.10). |
| MIL-F-8785**B**'s continuous closed form (`L_u = L_FA^(2/3)·h^(1/3)`, `L_w = h`) instead of the stitched 1000-2000 ft interpolation | Genuinely attractive — it removes the one hand-made piece of the altitude model. But it is a different standard from the one the user asked to verify, its PSD pairing was not checked against a source read in full, and adopting it would change every number in §26.11 on the strength of a parenthetical remark. A candidate backlog item, not a silent substitution (research note §3.5). |
| Von Kármán instead of Dryden | The user chose Dryden. The scale lengths and intensities are shared between the two models and only the PSD shape differs, so `"von_karman"` is one function in `_TURBULENCE_MODELS` later — which is the payoff of making the turbulence a dispatch rather than an `if` (§26.3). Its `^(5/6)` PSD needs its own verification pass first. |
| Using `aᵢ = sqrt(2 Φ(ωᵢ) Δωᵢ)` directly, without renormalising to exact `σ` | Would deliver 81-98 % of the specified intensity depending on `(V, h)`, with the shortfall a function of an arbitrary internal constant (`_TURB_PERIOD_MIN_S`) rather than of any physics — and would lose the exact `Σ wᵢ² == 2` invariant that is the step's sharpest test (§26.6). The renormalisation's cost is an over-weighted low-frequency tail, which is both smaller and far easier to explain. |
| Randomising the frequencies (or jittering them within each bin) as well as the phases | Step 21's grid is already deterministic and nothing was wrong with that. Independent phases are sufficient to decorrelate seeds, and jittering would make every pinned number depend on the draw order of 64 more values for no modelling gain. |
| Turbulence on wind tiers 2/3 | Needs `W20` and an AGL altitude the measured tiers do not carry, plus a decision about whether the sounding's own measured shear already contains part of what Dryden would add. Backlog **B10** (§26.10). |
| `_TURB_N` / the frequency band as `Params` fields | Numerics, not scenario configuration — the same rule §18 states for `R_d`, the ISA layer table and the WGS84 constants, and where `_GUST_N` already lives. A scenario does not vary its own discretisation. |
| Keeping the `max(W + u, 0.0)` non-negativity clamp | It existed only because Step 21 perturbed a scalar *speed* and then applied a fixed direction, where a negative sum silently flipped the wind 180°. With a vector perturbation along `ê_u`, that flip is the **correct** physics for a gust stronger than the mean wind (§26.7 item 3). |
| Caching the per-call weights (keyed on `h`, or on a rounded `h`) | `Params` is not hashable across every field, `h` is continuous, and rounding `h` to make it cacheable would put a staircase in the RHS — the one thing an adaptive solver genuinely dislikes. §15, "do not optimise". |
| Interpolating the PSD, or the 64 amplitudes, across the transition band instead of `(L, σ)` | The MIL-spec gap is a gap in the **parameters**; that is where the fill belongs. It is also not the same answer — `aᵢ ∝ √Φ` is not linear in `Φ` — and it is 64× the arithmetic for a worse-justified result. |
| Smoothing the two slope kinks at 1000 ft and 2000 ft | An invention of this project sitting on top of a cited model. The ISA's layer boundaries already put the same kind of kink in the aerodynamic force and the solver has never minded (§26.5). |
| A separate `W20` (or `turbulence_w20_ms`) `Params` field | A second source of truth for the mean wind, and a way for a scenario to be internally inconsistent. Tier 1 already knows the wind at 6.096 m: it is `_mean_speed(_W20_H_M, p)` (§26.3). |
| Re-deriving or re-researching the Dryden formulas in this document | They are in `latex/research/dryden_turbulence_model.md`, verified against two primary sources read as rendered pages, with the one transcription hazard the pass found recorded there. §26.2 transcribes and cites; it does not re-litigate. §26.14 caches what a developer needs so nobody re-runs the research. |
| Making this step bit-for-bit for gusty runs too (e.g. by keeping the old model as a `turbulence_model = "legacy"` variant) | Preserves a placeholder with no physics behind it as a permanent public option, and invites someone to compare against it as if it meant something. The behaviour change is deliberate, documented (§26.1), and pins nothing that exists. |

### 26.14 Cached research facts, and the two flagged risks

**Do not re-run the research.** `latex/research/dryden_turbulence_model.md` is the cached result of a
verification pass against two primary sources fetched and read as rendered pages:

| Fact | Where | Status |
|---|---|---|
| Dryden PSDs `Φ_u`, `Φ_v`, `Φ_w` (temporal form) | Madden, NASA Langley, NTRS 20190000875, eqs. (1)-(3) | read as rendered PDF; transcribed in research note §3.3 and §26.2 |
| Low-altitude `L_u`, `σ_u` (the **quotient** form) | Cole & Wickenheiser, arXiv:1905.09954, Table 3.1 (p.11), cross-checking Madden | read as rendered PDF; a tool summary had misread the quotient as a product — both primary sources say quotient |
| Isotropic `L = 1750 ft` above 2000 ft, `σ` from an exceedance chart (no closed form) | both sources | research note §3.4; the chart is deliberately **not** pinned — `Params` field instead |
| 1000-2000 ft gap filled by linear interpolation | both sources describe it as the standard implementor's fill | research note §3.5 |
| Shared scale lengths/intensities between Dryden and von Kármán (only the PSD shape differs) | both sources | research note §2 — the reason a von Kármán variant is cheap later |

**Risk 1 — the `L_v` factor-of-two convention, flagged not hidden.** MIL-F-8785C/MIL-HDBK-1797 write
the lateral and vertical spectra in terms of `2L_v` and `2L_w` in some editions and renderings, and
the literature carries both conventions. The research note states `L_u = L_v` and `L_w = h`, paired
with the `Φ_v = σ_v²(L_v/πV)(1+3x²)/(1+x²)²` form transcribed from the same source — which is
self-consistent (both of this document's PSDs integrate to `σ²` exactly, §26.2, and the alternative
`(1+12x²)/(1+4x²)²` form is the *same function* with `L` relabelled by 2). Normalisation therefore
cannot discriminate between the two conventions; only the break frequency can. **If a later reading
of Madden shows the source's `Φ_v` is written in the `2L_v` convention, the entire correction is
`L_v = L_u/2` on one line** — `σ_v` is unaffected, the variance identity is unaffected, and the
visible consequence is that the cross-wind spectrum's knee sits one octave away. §26.12 pins the
break frequency for exactly this reason: the convention is locked by a test, so a change is loud.
This is a bounded, named uncertainty inside a model whose reference speed `V` is itself an admitted
simplification (§26.9) — it is not a reason to delay the step, and it **is** a reason not to pretend
the question does not exist.

**Risk 2 — the LaTeX is out of date, and the LaTeX is the source of truth. Resolved 2026-10-02.**
`latex/sections-ai/models.tex` §Wind > Analytic (lines ~514-526) still documents the Step-21
placeholder verbatim: `ΔW(t) = σ Σ wᵢ sin(ωᵢ t + φᵢ)` added to `W(h)` and "clamped non-negative,
since `W` is a speed", with `σ = 0` as the off switch. Every one of those three statements is
contradicted by this section. Roadmap working rule 1 says the LaTeX wins over the roadmap and this
document; `main.tex` and its section files are the **user's** document. So this went to the user:

> The user nominated `latex/research/dryden_turbulence_model.md` + this §26 as the interim physics
> reference for the turbulence model, with `latex/sections-ai/models.tex` §Wind > Analytic to be
> brought in line later, by the user's own edit. Implementation may proceed against §26. A developer
> must still **not** resolve the mismatch by editing `models.tex`.

No longer listed as blocking in the roadmap's blocked-steps table against Step 46 (the entry is kept,
struck through, for the record).

**Closed 2026-10-13.** The deferred `models.tex` edit was made in the Phase 2.14 LaTeX sync pass, on
the user's own request to write up everything implemented but undocumented. `§Wind` now reads: an
`Analytic` paragraph for the mean profile alone, then a `Turbulence` paragraph carrying this
section's scale-length/intensity bands, both PSDs, the renormalised random-phase synthesis, the
along/cross composition with the clamp's removal stated, and §26.9's reference-airspeed limitation
with a backlog pointer. The line numbers quoted above are therefore historical.

---

## 27. Phase 2.10 — Launch rail, recovery/parachute, control-engineering scaffold (Steps 47-49)

Designed in one pass, at the user's explicit request ("design the rail and parachute dynamics on
your own... then you can start with 3D"), with a late addition folded in before implementation began
("before doing 2D, add a somehow way to do control engineering... feedback rn is going to be
airbrake but also create base for direction control (guided)... control engineering can go in 3D").
Self-contained like §23/§24/§26: a developer implementing one of Steps 47-49 needs that step's own
subsection plus the relevant main.tex section, not the whole document. The three are bundled because
they are the last 2D-only physics gaps (rail: B1; recovery: B2) plus the one genuinely new *kind* of
subsystem this project has not built yet (a feedback controller) — and because, perhaps usefully,
**rail and parachute turn out to be the same mechanical pattern**: both are a constrained phase of
flight in which `dtheta/dt = domega/dt = 0` (attitude frozen by a mechanical constraint — the rail
buttons, then the canopy) and only the translational force model changes. Direction/guidance control
is explicitly **not** designed here — see §27.3's scope note — only its architectural seam is.

### 27.1 Step 47 — Launch rail constraint (promotes backlog B1)

**Files:** `sim/params.py`, `sim/dynamics.py`, `sim/integrate.py`.

**Physics.** While the rocket's travel along the rail is less than `L_rail`, the rail buttons
mechanically react every force component transverse to the rail and prevent rotation — the rocket
can only slide, not pitch or drift sideways. This is **not** a new force; it is a kinematic
constraint on the same force sum `F_i` every other step already computes. Let `e_rail` be the fixed
unit vector along the rail, in the inertial frame:

```
e_rail = to_inertial([1.0, 0.0], radians(p.rail_angle_deg))
```

i.e. the rail points the way the nose initially points — `rail_angle_deg` is a `Params` field
describing the physical rail mount angle, independent of (but meant to be set consistent with) the
launch `State.theta` the scenario supplies; nothing in the code enforces that consistency, the same
standing as every other scenario-setup fact this project trusts the caller to get right (e.g.
`azimuth_deg` vs. the launch heading). Default `90.0` (vertical), matching every existing scenario's
`theta = pi/2`, so the rail is vertical by default — consistent with, not derived from, those
scenarios.

`rail_distance(y, p) = dot((y[X], y[Z]), e_rail)` — the signed distance travelled along the rail
from the launch point (assumed to be the origin, as every scenario in this repo already launches
from `x=0, z=0`). On the rail (`0 < rail_distance < L_rail`... in practice just `rail_distance <
L_rail`, since the rocket starts at `rail_distance = 0`):

```
a_i_unconstrained = F_i / m          # exactly today's computation, unchanged
a_parallel = dot(a_i_unconstrained, e_rail) * e_rail   # project out the transverse component
dvx/dt, dvz/dt = a_parallel
dtheta/dt = 0.0
domega/dt = 0.0
```

Off the rail (`rail_distance >= L_rail`, or `L_rail <= 0.0`): exactly today's unconstrained
equations, bit-for-bit. **`L_rail = 0.0` is the off switch** — at `t=0`, `rail_distance = 0`, so
`0 < 0.0` is false and the rocket is never on the rail; this reproduces every existing test and
scenario without a separate boolean gate, the same "a zero/empty sentinel disables the model"
convention as `aero_table`, `wind_model`, `m_d`.

No friction term. A real rail has some, but it is small (low-friction buttons, short travel) and
the roadmap's own B1 sketch does not ask for it; if it matters later it is one `mu_rail` field and
one more term in `a_parallel`'s magnitude — not designed now (no speculative scaffolding for an
unrequested refinement).

**`Params` additions** (append near the geometry fields, §1 pattern — new fields, defaults
reproduce every prior step bit-for-bit):
```python
L_rail: float = 0.0          # launch rail length [m]; 0.0 = off, unconstrained from t=0
rail_angle_deg: float = 90.0  # rail elevation from horizontal [deg]; direction of e_rail
```

**`dynamics.py`.** Add two small helpers near `_propellant_mass`/`_cog_position` (same "private
helper supporting `derivatives`" placement):
```python
def _e_rail(p) -> np.ndarray:
    return to_inertial(np.array([1.0, 0.0]), np.radians(p.rail_angle_deg))

def rail_distance(y: np.ndarray, p) -> float:
    return float(np.dot(np.array([y[X], y[Z]]), _e_rail(p)))

def on_rail(y: np.ndarray, p) -> bool:
    return p.L_rail > 0.0 and rail_distance(y, p) < p.L_rail
```
`rail_distance`/`on_rail` are exported (no leading underscore) — `integrate.py`'s rail-exit event
needs `rail_distance` directly, matching the existing precedent of event functions reaching into the
module that owns their predicate (`_burnout_event` reads `thrust_curve.thrust` directly).

In `derivatives`, after `a_i` is fully computed (including the Step 37 Coriolis term, so the rail
constraint reacts the *same* total acceleration gravity/Earth-rotation produces, not a partial one)
and `M_y`/`I` are computed as today (cheap, and keeps the function's structure — every force/moment
is still evaluated every call, only the final assembly branches), replace the final assembly block:
```python
if on_rail(y, p):
    e = _e_rail(p)
    a_parallel = np.dot(a_i, e) * e
    dydt[VX], dydt[VZ] = a_parallel
    dydt[THETA] = 0.0
    dydt[OMEGA] = 0.0
else:
    dydt[VX], dydt[VZ] = a_i
    dydt[THETA] = y[OMEGA]
    dydt[OMEGA] = M_y / I
```
(`dydt[X] = y[VX]`, `dydt[Z] = y[VZ]`, `dydt[M] = dm_dt` are unaffected either way.)

**`integrate.py`.** A new non-terminal event, reported but not stopping the run (the dynamics branch
above already handles the transition smoothly — this event exists purely so `Result.events` can
report the rail-exit time/speed, the same informational role as `_burnout_event`):
```python
def _rail_exit_event(t, y, p):
    if t < 0.1 or p.L_rail <= 0.0:
        return -1.0  # same t=0/off-switch guard as _ground_event/_burnout_event
    return dynamics.rail_distance(y, p) - p.L_rail

_rail_exit_event.terminal = False
_rail_exit_event.direction = 1
```
Add to `events=[...]` in `run_sim`, and `"rail_exit": ...` to both `Result(...)` constructions
(`run_sim`'s RK45 path and `_run_rk4`). `_run_rk4` needs the equivalent manual crossing detection
(sign change of `dynamics.rail_distance(y,p) - p.L_rail`, negative to positive, guarded the same way)
— mirror the existing burnout/apogee/ground block structure there, don't restructure it.

**Check.**
- `L_rail = 0.0` (default) reproduces every existing test and scenario bit-for-bit — this is the
  load-bearing regression check, same as every prior step's off-switch test.
- A scenario with `L_rail > 0`, `rail_angle_deg = 90.0`, some nonzero crosswind (`wind_model =
  "analytic"`, `wind_ref_ms > 0`): `theta` and `omega` stay exactly at their initial values and `x`
  stays exactly `0.0` (no transverse drift) for the entire rail phase, despite the crosswind — this
  is the check that the constraint is actually doing something (a run with `L_rail = 0.0` under the
  same crosswind drifts in `x` and tips `theta` immediately).
- `rail_exit` event fires once, at `rail_distance == L_rail` to solver tolerance; the reported
  rail-exit speed `|v_i|` at that instant is the quantity that actually matters physically (roadmap
  B1: "rail-exit speed is what decides whether the wind model tips the rocket over").
- A tilted rail (`rail_angle_deg = 85.0`, no wind): the rocket leaves the rail already moving at
  `85°` from horizontal, not `90°` — `atan2(-vz, vx)` at rail-exit equals `rail_angle_deg` to solver
  tolerance.

### 27.2 Step 48 — Recovery / parachute (promotes backlog B2)

**Files:** `sim/params.py`, `sim/forces.py`, `sim/dynamics.py`, `sim/integrate.py`.

**Physics, and the design choice behind it.** The roadmap's own B2 sketch says attitude dynamics
should be "disabled or heavily damped" under canopy. This section chooses **disabled** — `dtheta/dt
= domega/dt = 0` once deployed, exactly the rail phase's mechanism, re-used rather than invented:
both are "a mechanical constraint freezes the attitude state" phases, one at the start of flight, one
at the end. The alternative (an artificial damping constant) would need a made-up time constant with
no source; freezing needs nothing but the deployment condition itself, and is no less physical a
description of "the canopy holds the body in a fixed hang attitude" than a damping term would be.

The more consequential choice is **where the chute drag acts**: not through the body axial/normal
decomposition (`aero_force_body`'s `-A_x*x_hat_r - A_z*z_hat_r`, Step 35's convention), because a
round canopy is axisymmetric and its drag opposes the *relative wind vector*, not the *body's nose
direction* — under canopy the body may hang at any frozen `theta`, and routing chute drag through
`x_hat_r` would make the descent rate depend on whatever `theta` happened to be at deployment, which
is not how a parachute works. Instead the chute force is computed **directly in the inertial frame**,
the same standing as `weight_inertial` (the one existing force already natively inertial, needing no
`to_inertial` rotation):
```
v_rel_i = (y[VX], y[VZ]) - wind_inertial(t, y, p)      # inertial relative-wind vector
V = |v_rel_i|                                           # == flow_state(t,y,p).V, frame-invariant
F_chute_i = -0.5 * air.rho * p.parachute_Cd * p.parachute_S * V * v_rel_i
```
— standard quadratic drag, `F = -(1/2)*rho*Cd*S*|v|*v`, opposing `v_rel_i` exactly (this is the
vector form of `A = 0.5*rho*V^2*Cd*S`; splitting the `|v|*v` product, rather than writing
`(1/2 rho V^2 Cd S) * v_hat`, avoids a `0/0` direction at `V=0` the same way Step 44's `aero_moment_y`
avoids a `0.0*inf` at `V=0`, architecture.md precedent in `forces.py`'s own docstring).

**Deployment condition**, a pure function of `(t, y, p)` — no event-time lookup from inside the RHS
(the RHS runs *before* any event is finalised; it cannot read `Result.events`, so "has apogee
happened" has to be reconstructed from the state actually being integrated, not referenced):
```python
def parachute_deployed(t, y, p) -> bool:
    if p.parachute_model == "none":
        return False
    if p.parachute_deploy_trigger == "timer":
        return t >= p.parachute_deploy_time
    # "apogee" (the default): y[VZ] > 0 means currently descending. On any
    # simple ballistic/drag trajectory this is true from apogee onward and
    # false before it -- a continuous, RHS-computable stand-in for "has
    # apogee happened yet", not a reference to the apogee *event* itself.
    # Known simplification: a pre-apogee transient dip (vz briefly positive
    # mid-boost on an unstable trajectory) would arm deployment early. Not a
    # concern for the nominal trajectories this project models; documented
    # here rather than guarded against, the same standing as B11.
    return y[VZ] > 0.0
```

**`Params` additions:**
```python
parachute_model: str = "none"              # none | deploy
parachute_deploy_trigger: str = "apogee"   # apogee | timer
parachute_deploy_time: float = 0.0         # [s], used only when trigger == "timer"
parachute_Cd: float = 0.8                  # [-], typical flat-circular canopy; override per design
parachute_S: float = 0.0                   # [m^2] canopy reference area; 0.0 = inert even if deployed
```
`parachute_model = "none"` (default) is the primary off switch; `parachute_S = 0.0` is a second,
independent one (same belt-and-suspenders style as `turbulence_sigma_high_ms`/`A_e`) — either alone
reproduces every prior step bit-for-bit.

**`forces.py`.** Add `parachute_deployed` (above) and:
```python
def parachute_drag_inertial(t, s, p) -> np.ndarray:
    """F_chute_i, inertial frame, (0,0) whenever not deployed -- natively
    inertial like weight_inertial, since a round canopy's drag does not
    depend on body attitude (architecture.md SS27.2)."""
    if not parachute_deployed(t, s, p):
        return np.zeros(2)
    flow = flow_state(t, s, p)
    v_rel_i = np.array([s[VX], s[VZ]]) - wind.wind_inertial(t, s, p)
    return -0.5 * flow.air.rho * p.parachute_Cd * p.parachute_S * flow.V * v_rel_i
```
(local `from sim import wind` import, same circular-import-avoidance precedent as `flow.py`'s own
`_wind_inertial`; `VX`/`VZ` imported from `sim.state`.)

**`dynamics.py`.** A third branch in the same final-assembly block Step 47 introduced — rail,
parachute and free-flight are mutually exclusive (a rocket cannot be both on the rail and under
canopy; `on_rail` is false long before `parachute_deployed` can be true on any realistic flight, but
the branch order below makes rail take priority defensively, no behaviour depends on it):
```python
if on_rail(y, p):
    ...                      # Step 47, unchanged
elif forces.parachute_deployed(t, y, p):
    F_chute = forces.parachute_drag_inertial(t, y, p)
    a_chute = (F_i + F_chute) / m          # F_i already excludes nothing -- add the chute force in
    dydt[VX], dydt[VZ] = a_chute
    dydt[THETA] = 0.0
    dydt[OMEGA] = 0.0
else:
    dydt[VX], dydt[VZ] = a_i
    dydt[THETA] = y[OMEGA]
    dydt[OMEGA] = M_y / I
```
Note `a_chute` recomputes `/m` from `F_i + F_chute`, not `a_i + F_chute/m` — identical arithmetic,
written this way so the Coriolis term (already folded into `a_i` earlier) is included exactly once,
not silently dropped by reusing a stale `F_i`.

**`integrate.py`.** A non-terminal `_parachute_deploy_event`, same shape as `_rail_exit_event`:
```python
def _parachute_deploy_event(t, y, p):
    return 1.0 if forces.parachute_deployed(t, y, p) else -1.0

_parachute_deploy_event.terminal = False
_parachute_deploy_event.direction = 1
```
Add to `events=[...]`, `Result.events["parachute_deploy"]`, and `_run_rk4`'s manual detection
(sign change of the same boolean-as-±1, negative to positive).

**Check.**
- `parachute_model = "none"` (default) reproduces every existing test/scenario bit-for-bit.
- The roadmap's own closed-form check: with `parachute_model = "deploy"`, no wind, deployed well
  before ground impact, the descent speed converges to `V_terminal = sqrt(2*m*g/(rho*Cd*S))` to
  within the ISA density's own altitude variation over the convergence distance (not exact, since
  `rho` is not constant with altitude — state the tolerance, don't claim exactness `rho` doesn't
  support).
- `theta`/`omega` are frozen at their deployment-instant values for the rest of the flight — assert
  `y[THETA]`/`y[OMEGA]` constant post-deployment to the array's last sample.
- A deployed chute with a strong crosswind descends at an angle (drifts horizontally) — the vector
  (not scalar) nature of `F_chute_i` actually coupling to crosswind, the same kind of "is it really a
  vector, not a second scalar" check Step 46 ran for the Dryden cross-wind component (§26's own
  check list).
- `parachute_deploy_trigger = "timer"` deploys at exactly `parachute_deploy_time`, independent of
  the trajectory's own apogee.

### 27.3 Step 49 — Control-engineering scaffold: feedback airbrake, and the seam for guidance

**Scope, stated up front** (the user's own split): *"the 3d section for now is just simulation,
optimization, cfd is only for 2D, while control engineering can go in 3D."* Read together with
*"create base for direction control (guided)"*, this step builds (a) a generic, reusable
feedback-controller pattern, and (b) one concrete instance of it — an apogee-targeting airbrake,
the classic active-drag control problem in amateur high-power rocketry, and the only control problem
2D's one rotational DOF (`theta`, already fully occupied by the rocket's own passive pitch dynamics)
can meaningfully host. It does **not** build a 2D guidance/direction-control law — that is explicitly
Phase 3's job (steering needs an out-of-plane DOF this project doesn't have until then). The "base"
for it is the module structure and the determinism discipline below, not a stub function with no
caller — an uncalled `guidance_command()` today would be exactly the kind of speculative scaffolding
this project avoids elsewhere; Phase 3 adds a second dispatch dict to this same module when it needs
one, following the shape `_AIRBRAKE_CONTROLLERS` sets below.

**The determinism constraint, again, and why it shapes the control law.** Step 21 established it,
Step 46/B11 ran into it for turbulence: `solve_ivp`'s RHS is called at arbitrary, repeated, and
rejected times, so any stateful element (memory, an integral accumulator, a derivative needing the
previous call, a fixed-rate sample-and-hold) is not a pure function of `(t, y, p)` and breaks the
solver's contract. A real flight computer's airbrake loop would be a **sampled-data system** — a
fixed-rate (e.g. 20 Hz) loop with a zero-order-hold actuator command and very possibly PID's integral
and derivative terms. None of that is buildable without either a fixed-step integrator or an outer
loop that halts and restarts `solve_ivp` at every sample tick (a materially bigger change, and the
same shape of problem B11 already deferred for turbulence). This step makes the same call B11 made,
for the same reason: **a pure proportional (P) control law, re-evaluated fresh at every RHS call,
with no memory** — fully compliant with the existing determinism contract, no new integration
strategy needed, at the cost of not modelling sample-rate lag or integral trim. Flagged as a new
backlog item below (B12), not silently accepted as the final word.

**Files:** `sim/control.py` (new), `sim/params.py`, `sim/forces.py`.

**`sim/control.py`.** New module — a first-class concern, same standing as `wind.py`/`atmosphere.py`,
not a function buried in `forces.py`, because the user asked for a *reusable* pattern:
```python
"""Feedback control (architecture.md SS27.3). Every controller here is a
pure, memoryless function of (t, y, p) -- see SS27.3's determinism-contract
note for why: solve_ivp's RHS is evaluated at arbitrary/repeated/rejected
times, so no controller may carry state across calls (no integral term, no
fixed-rate sample-and-hold) without a different integration strategy
(backlog B12). A dispatch dict per controllable actuator, selected by a
Params string field -- same pattern as wind.py's _TURBULENCE_MODELS.

Only one actuator is implemented: the airbrake (apogee-targeting P control).
Direction/guidance control is Phase-3 scope (SS27.3) -- this module's shape
(a dict dispatch keyed on a Params string, one pure function per variant) is
the base the user asked for; a guidance controller adds a second dict here
when Phase 3 needs one, not before.
"""

def _no_airbrake(t, y, p) -> float:
    return 0.0

def _proportional_airbrake(t, y, p) -> float:
    if thrust_curve.thrust(t, y, p) > 0.0 or y[VZ] >= 0.0:
        return 0.0   # only active during unpowered ascent (post-burnout, pre-apogee)
    predicted_apogee = gravity.altitude_agl(y, p) + y[VZ]**2 / (2.0 * gravity.g(t, y, p))
    error = predicted_apogee - p.airbrake_target_apogee_m
    return float(np.clip(p.airbrake_kp * error, 0.0, 1.0))

_AIRBRAKE_CONTROLLERS = {"none": _no_airbrake, "proportional": _proportional_airbrake}

def airbrake_deploy_fraction(t, y, p) -> float:
    return _AIRBRAKE_CONTROLLERS[p.airbrake_model](t, y, p)
```
`predicted_apogee` is the standard real-world estimator: the altitude the rocket would reach if drag
vanished right now (`h + v_up^2/(2g)`, using `y[VZ]**2` since the sign is squared away) — an
*upper-bound* prediction, deliberately ignoring further drag (including the brake's own, which is
exactly the quantity the controller is deciding whether to add). It is a pure function of the state
being integrated, no different in kind from the thrust curve or the aero table — no new determinism
risk.

**`Params` additions:**
```python
airbrake_model: str = "none"           # none | proportional
airbrake_target_apogee_m: float = 0.0  # target AGL altitude [m]
airbrake_kp: float = 0.0               # proportional gain [1/m]
airbrake_Cd: float = 1.0               # [-], flat-plate-ish brake surface
airbrake_S_max: float = 0.0            # [m^2] exposed area at full (fraction=1.0) deployment
```
Three independent off-switches (`airbrake_model = "none"`, `airbrake_kp = 0.0`, `airbrake_S_max =
0.0`) — any one alone reproduces every prior step bit-for-bit, the established belt-and-suspenders
style for a feature with real consequences if it accidentally activates.

**`forces.py`.** `aero_force_body` gains one additive term, after the existing `aero_model` branch,
unconditionally (linear deployment-fraction-to-area model, `S_brake(f) = f * S_max` — the simplest
model that needs no new geometry beyond what the step already introduces; refine later if a real
brake's area-vs-angle curve is nonlinear enough to matter):
```python
A_brake = flow.q * p.airbrake_Cd * p.airbrake_S_max * control.airbrake_deploy_fraction(t, s, p)
return np.array([-(A_x + A_brake), -A_z])
```
Routed through the body axial direction (`x_hat_r`), unlike the parachute: an airbrake is rigidly
mounted to the body and shaped to add axial drag regardless of pitch, the opposite physical situation
from the free-swinging canopy (§27.2) — this is a deliberate difference in treatment, not an
inconsistency between the two steps.

**Check.**
- `airbrake_model = "none"` (default) reproduces every prior step bit-for-bit.
- `airbrake_S_max = 0.0` with `airbrake_model = "proportional"` also reproduces it bit-for-bit (the
  independent-off-switch check).
- No closed-form pinned number exists once drag depends on a feedback law (the same standing as
  Step 25's aero-table checks) — the regression is **directional**: for one scenario, run with
  `airbrake_model = "none"` and record its (unconstrained) apogee; run again with `"proportional"`,
  a large `airbrake_kp` (saturating), and `airbrake_target_apogee_m` set below that unconstrained
  apogee — the second run's apogee must be lower than the first's, and `airbrake_deploy_fraction`
  must reach exactly `1.0` (saturated, not merely "high") during the coast phase.
- `airbrake_deploy_fraction` is exactly `0.0` at every sample while `thrust > 0` (powered ascent) and
  at every sample once `y[VZ] >= 0` (past apogee) — the activation-window gate actually gates.
- A small-gain case (`airbrake_kp` modest, target close to the unconstrained apogee):
  `deploy_fraction` varies continuously between `0` and `1` across the coast (not a bang-bang jump),
  confirming the proportional law is genuinely proportional, not accidentally saturating everywhere.

### 27.4 New backlog item opened by Step 49

**B12 — Sampled-data control (fixed-rate loop, zero-order hold, PID).** Step 49's airbrake is a
continuous, memoryless proportional law, by the same necessity Step 46/B11 already documented for
turbulence: `solve_ivp`'s RHS has no concept of "the last sample," so a real flight computer's
fixed-rate loop (and any integral/derivative control term) cannot be expressed as a pure function of
`(t, y, p)` without a different integration strategy — either a fixed-step integrator for the whole
flight, or an outer loop that halts and restarts `solve_ivp` at each sample tick, carrying a
hold-value forward as an extra `Params`-like input to each segment. Both are materially bigger than
this step; picking this up is a prerequisite for a *realistic* (not merely stable) airbrake or
direction-control loop, and for comparing against a real flight computer's logged behaviour. Revisit
alongside B11, which has the same root cause.

---

## 28. Phase 2.11 — rewrite pass (Steps 50-59) — *lives in a separate file*

**→ `docs/architecture-28-rewrite.md`** (proposal, not yet approved; no code written).

This section is **not** inlined here. `architecture.md` is already past the point where any agent can
read it whole, so from §28 on, each stage's design goes in its own `architecture-<n>-<slug>.md` file
with its own table of contents and stable anchors — append-only navigation here, content there.

§28 covers the pre-Step-30 rewrite pass: (28.3) `Params` split into twelve composed sub-dataclasses
plus a dotted-path `replace` helper; (28.5) `sim/aero.py` rewritten as an explicit
`"constant" | "linearized" | "table"` dispatch with the raw-force placeholders `A_x`/`A_z`/`A_m`
replaced by `q·S·C_x`, `q·S·C_z`, `q·S·d_ref·C_m` — **the one deliberately non-bit-for-bit change in
the pass**; (28.6) a control-coefficient seam so a future law can perturb `C_x`/`C_z`/`C_m`/`l1`
directly; (28.7) a `Solver` group and `run_sim(p, s0)`; (28.8) an opt-in fixed-step
sampled-data/zero-order-hold integration mode, which is what unblocks backlog **B11** and **B12**;
(28.9) `run.py` reduced to scenario definition with the reporting machinery moved to a new
`sim/report.py`; (28.10) the matching structural/notational LaTeX pass. Ordered tickets are §28.11,
the 17 open decisions §28.12.

Two corrections to **this** document that §28 forces, recorded here so a reader does not take a
stale claim on trust: §12's description of `"constant"` as a raw, atmosphere-independent force
becomes false (every aero model is dynamic-pressure-scaled after §28.5), and §18's flat `Params`
field list is superseded by §28.3. §12 was corrected at Step 55 (its own one-line addendum, not a
rewrite). §18's flat field list is a larger rewrite, out of Step 55's scope, and still not
edited — it describes the pre-S50 flat `Params`, now historical.

---

## 29. Phase 2.12 — motor-selection app (Steps 61-62) — *lives in a separate file*

**→ `docs/architecture-29-motor-selection.md`** (proposal, not yet approved; no code written).

Same split as §28, for the same reason: content there, navigation here.

§29 designs the app the user asked for on 2026-10-12 — feed in a list of motors, get the
trajectories back ranked by **apogee**, with a per-motor stats bundle richer than
`sim.report.flight_summary`'s four fields (max/avg velocity, max acceleration, burnout time, max-Q,
delivered impulse, impact time, downrange). It is a **separate consumer app**,
`apps/motor_selection/` ("App 3"), on the `apps/cfd_conditions/select_conditions.py` precedent: it
imports `sim/` as a library, adds no physics and changes **nothing** under `sim/` — the user's own
instruction ("make it as a separate thing; that also concerns optimizers"). Two steps: (61) the
sweep plus four synthetic motor-curve fixtures under `data/motors/`; (62) the per-motor
configuration methodology — each motor entry also carrying dry-rocket-parameter overrides (smaller
motor, smaller casing), which needs **no change to `sim/params.py`** because its dotted-path
`replace(p, {...})` already accepts arbitrarily many keys per call (§29.2 F1). The load-bearing
convention is the **ascent-only measurement window** for every extremum (§29.4.1), grounded in Step
55's recorded finding that this project's own scenarios can put max speed during *descent*. Tickets
are §29.9, the ten open decision forks §29.10 (numbered D-18 … D-27, continuing §28's D-1 … D-17),
and three proposed backlog items (B14 real `.eng` motor data, B15 per-motor mass metadata, B16
two-dimensional sweeps) §29.12.

**Not covered, deliberately:** the airbrake. The user's same message asked for airbrake capability as
`C_dA_total = C_dA_rocket + C_dA_airbrake`; that already exists, in exactly that additive-under-a-
shared-`q` form and off by default, in `sim/forces.py`'s `aero_force_body` (§27.3, Step 49). §29
designs no airbrake change.

---

## 30. Phase 2.13 — Apps 4-5, the shared app layer, reusable configs (Steps 63-69) — *lives in a separate file*

**→ `docs/architecture-30-apps-4-5-and-configs.md`** (proposal, not yet approved; no code written).

Same split as §28/§29, for the same reason: content there, navigation here.

§30 designs the **five-tool layout** the user asked for on 2026-10-13 — (1) simple simulation,
(2) motor sweep, (3) airbrake `C_dA` determination, (4) CFD input conditions, (5) CFD optimization
(weight vs aerodynamics) — plus "configs I can create and reuse across multiple apps". Two of the
five already exist and are untouched: the user's "2nd" is **App 3** (`apps/motor_selection/`, §29)
and their "4th" is **App 2** (`apps/cfd_conditions/`); their "1st" is `run.py`, which stays at the
repo root and never carries an "App N" label. **The internal "App N" numbering is not the user's 1-5
list order** — App 2 = CFD conditions, App 3 = motor selection, **App 4 = airbrake sizing (new)**,
**App 5 = weight-vs-aero trade (new)**. Recorded here because it is the single most likely thing for
a later reader to misread.

New in §30: `configs/` (one module per named scenario, `Config` + `Variant`, registry in
`__init__.py`; Python literals per the already-approved D-23, and git history *is* the config
history); `apps/common/` (App 3's `flight_stats` promoted so three apps share one tested
implementation); **App 4** (`apps/airbrake_sizing/`, the user's MATLAB `fminbnd`/explicit-Euler
prototype re-done against the real solver, with three selectable deployment triggers); **App 5**
(`apps/weight_aero_tradeoff/`, a 2-D apogee(`C_dA`, mass) trade surface with an iso-apogee exchange
rate, plus a named-scenario comparison). Seven steps, 63-69, one commit each; Phase 3 keeps its
reserved 28-32 block. **User-approved 2026-10-13:** the four root wrappers (D-29), the `configs/`
package and its migration (D-30/D-31/D-32), and both App 5 modes (D-38).

**A consumer phase with exactly one `sim/` step, and that step is the open gate.** Apps 4 and 5
themselves need no `sim/` change, no new dependency and no `docs/latex/` pass (no new physics). The
exception is the three airbrake deployment triggers the user asked for — "after burnout, after
specified time, after apogee": only the first is reachable through `Params`, because
`_proportional_airbrake` reads `t` solely via `thrust_curve.thrust` and returns `0.0` unconditionally
once `y[VZ] >= 0.0` (§30.2 F15), and Step 59's `hold`/sampling path recomputes that same law rather
than offering an injection seam (F16). The recommended fix is **Step 65: +2 defaulted `Control`
fields and ~35 lines in `sim/control.py`** — a trigger dispatch dict copying the pattern
`sim/forces.py`'s `parachute_deployed` already uses for the parachute's `timer`/`apogee` triggers —
bit-for-bit safe for every existing config, in its own commit, with `"proportional"` untouched.
**D-36-revised** (§30.10) puts that choice to the user.

Everything load-bearing here was measured against this tree, not assumed (§30.2): apogee is strictly
monotone decreasing in `C_dA_airbrake`, so App 4 is a bracketed `brentq` root-find (17 runs, 1.2 s,
1.4e-4 m residual) rather than the precedent's squared-residual minimization; a *post-apogee* brake
leaves the apogee **flat to 2.4e-3 m of solver noise** across the whole bound range, so App 4 must
refuse to solve under that trigger (F19 — and the descent it would be judged on is itself
nonphysical here, B17/B23); apogee depends on the **product** `aero.S * aero.C_x` to the last printed
digit, which licenses App 5's one-dimensional drag axis; and the measured exchange rate at the demo
vehicle is **1 g of mass ≈ 1.86 mm² of `C_dA`** — the number App 5 exists to produce. Tickets are
§30.9, the decision forks §30.10 (**D-28 … D-42**, continuing §29's D-18 … D-27; D-29/D-30/D-31/D-32
and D-38 answered, D-36 reworked and open), and six proposed backlog items (B18 higher-dimensional
trades, B19 airbrake deployment beyond an onset latch, B20 CFD-output ingestion, B21 coast-only
restart, B22 mass changes that also move inertia/geometry, B23 a descent objective for the
post-apogee brake, blocked on B17) §30.12.

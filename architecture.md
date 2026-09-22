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
| 13 | `sim/gravity.py` — constant / linear / radial / wgs84 |
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

- The whole point of implementing four gravity models is **comparing them in the same session**
  ("how much apogee does inverse-square buy over linear?"). Comment-out-the-body swapping makes a
  comparison a git-diff-and-rerun exercise and leaves dead code in the file.
- Three atmosphere and three wind tiers differ by *data availability*, not by physics preference:
  the user will run ISA when there is no sounding and the multi-station field when there is. That
  is a per-scenario choice, i.e. scenario data, i.e. `Params`.

### Chosen pattern (recommended)

```python
# sim/gravity.py
def _g_constant(t, y, p): return p.g
def _g_linear(t, y, p):   ...
def _g_radial(t, y, p):   ...
def _g_wgs84(t, y, p):    ...

_MODELS = {"constant": _g_constant, "linear": _g_linear,
           "radial": _g_radial, "wgs84": _g_wgs84}

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
  `for gm in ("constant","linear","radial","wgs84"): run_sim(replace(p, gravity_model=gm), s0)`.
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

---

## 13. `sim/gravity.py` — four gravity models

Spec: `main.tex` §Models > Gravity. All variants return the **scalar magnitude** `g`; the
direction is always the fixed `ẑ_g = ẑ_i` (down) under the flat-Earth assumption, so
`forces.weight_inertial` becomes `np.array([0.0, p.m * gravity.g(t, y, p)])` and nothing else
changes.

Altitude used by all variants: `h = -y[Z]` (above the launch point) — plus `p.h0_m` when a
mean-sea-level altitude is needed (`wgs84`); see §15 "Altitude conventions".

| `gravity_model` | Formula | Notes |
|---|---|---|
| `"constant"` | `g = p.g` | Phase 1 baseline, the default. Bit-for-bit reproduces Phase 1. |
| `"linear"` | `g₀(1 − 2h/R_e)` | First-order expansion of the inverse-square law. Goes negative above `h = R_e/2`; physically irrelevant here, documented not guarded. |
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
  *different* model, and the only one that adds new physics rather than a better magnitude. But it
  breaks `main.tex` §Current assumptions ("`ẑ_g` fixed for the whole flight") and would have to be
  derived there first. Flagged as a question in §22, listed in the roadmap backlog. Not Phase 2.

Recommendation: **four variants, exactly as `main.tex` lists them.** No fifth.

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

```
A_f = −A_x·û − A_z·n̂                (main.tex §Forces, generalised)
    = (−A_x·cos α + A_z·sin α,  −A_x·sin α − A_z·cos α)   in body components
A_x = q·S·C_A(α, M)      A_z = q·S·C_N(α)      A_m = q·S·d_ref·C_m(α, M)
```

At `α = 0` this is exactly `(−A_x, −A_z)` — the Phase 1 expression — which is the regression test
for Step 9. The moment arm term in `dynamics.py` is unchanged and still correct:
`cross_y(aA, A_f) = −l₁·A_f,z = l₁(A_x sin α + A_z cos α)`, which reduces to `l₁·A_z` at `α = 0`.

### Altitude conventions (three altitudes, do not mix them)

| Symbol | Meaning | Expression | Used by |
|---|---|---|---|
| `z` | state, **down-positive**, zero at the launch point | `y[Z]` | the physics |
| `h_agl` | above the launch point | `−y[Z]` | gravity `linear`/`radial` (`main.tex` defines `h = −z`), rail/recovery later |
| `h_msl` | above mean sea level | `p.h0_m − y[Z]` | ISA, soundings, `wgs84` |

Soundings are published against MSL and ISA is defined against MSL, so a launch site at 380 m that
is treated as sea level starts the rocket in ~4.5 % too dense air. `p.h0_m` defaults to `0.0`,
which makes the two identical and keeps every Phase 1 check intact. Two module-level helpers in
`flow.py` (`altitude_agl(y)`, `altitude_msl(y, p)`) are the only places the negation appears
outside `plotting.py`.

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
| `gravity` | all four give `g(h=0) ≈ g₀` at `lat = 45.5°`; `linear` and `radial` agree to ~1e-6 relative at 10 km and diverge measurably at 100 km; `wgs84` gives 9.7803 at the equator, 9.8322 at the pole, 9.80665 near 45.5° |
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
7. **Non-parallel gravity** — `main.tex` §Current assumptions fixes `ẑ_g` for the whole flight.
   A gravity *direction* that rotates with downrange distance would be the one genuinely new
   physics among the gravity variants, but it needs a derivation update first. **Still backlog** —
   distinct from item 9 below (Coriolis is a dynamic, velocity-dependent effect on the equations
   of motion; this is a static, position-dependent effect on `ẑ_g`'s direction). Unless the user
   wants it.
8. **Crosswind is discarded in 2D (§16)** — worth confirming the user is happy that wind only ever
   acts along the flight plane until Phase 3.
9. **Coriolis/centrifugal (rotating-Earth) correction** — **RESOLVED** as a design question, see
   §9 item 7; the tangent-plane projection of `Ω` is a `\todo` in `main.tex`. Scheduled as
   Phase 2.5 Step 37.
10. **Linear gravity model removed** — the `"linear"` variant (`architecture.md` §13,
    `sim/gravity.py::_g_linear`) is being dropped: it is the weakest of the four (first-order
    truncation of inverse-square, goes negative above `h = R_e/2`) and offers no advantage over
    `radial`, which is exact and equally cheap. Scheduled as Phase 2.5 Step 34 (code + tests +
    the Step-27 comparison sweep).

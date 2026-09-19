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
the NamedTuple plus one line in the derivative; nothing else changes.
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
4. **"CoG doesn't change"** (main.tex §Current assumptions) conflicts with Phase 2 propellant
   depletion, which moves the CoG and changes `I`, `l₁` and `l₂` in time. Needs a derivation
   update before Step 12.
5. **Thrust moment is identically zero** under the current geometry (`aB ∥ T`). Worth knowing
   before wondering why the rocket never pitches under thrust.

---

## 10. Implementation task list

The roadmap **is** the ticket list. Every step is sequential (`depends_on` = the previous step)
and `parallel_safe: false` — the user commits after each step and re-checks `main.tex` in
between, so there is nothing to parallelise and no separate `task.md`. Each roadmap step names
the files it touches and the section of this document it needs.

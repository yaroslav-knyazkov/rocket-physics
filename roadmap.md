# Roadmap — Rocket Trajectory Simulator

## Summary

Step-by-step build plan, one small committable increment per step. Phase 1 (Steps 1-8) builds
the complete 2D planar rigid-body simulator from `main.tex` with every force as a constant,
ending with a working trajectory plot. Phase 2 (Steps 9-17) replaces those constants with real
models one at a time — relative wind, ISA atmosphere, thrust curve, mass depletion, pressure
correction, aero coefficients, wind, launch rail — each swap touching one function body.
Phase 3 (Steps 18-22) extends to 6-DOF using **quaternions** (Euler angles are singular at
pitch ±90°, a rocket's nominal attitude), reusing forces, params and plotting. Architecture
reference: `architecture.md`. Rule for every step: re-read the relevant `main.tex` section
first, because the user keeps extending the derivation.

---

## Working rules

1. **`main.tex` is the source of truth and it is a moving target.** Before starting any step,
   re-read the sections it implements. If the derivation has changed since this roadmap was
   written, the step changes with it — the roadmap does not override the LaTeX.
2. **One step = one commit.** A step is done when it runs, its check passes, and the repo is in
   a state the user would be happy to leave it in.
3. **Steps are strictly sequential.** Each depends on the previous one; nothing is parallelised.
4. **No input validation, no config plumbing, no generality that is not needed now** — except
   the function signatures fixed in `architecture.md` §4, which exist precisely so Phase 2 does
   not become a refactor.
5. If a step reveals a physics question (see `architecture.md` §9), stop and ask rather than
   guessing a sign.

---

## Phase 1 — 2D planar, everything constant

Goal: every equation currently in `main.tex` implemented, integrated and plotted.

### Step 1 — Scaffolding and constants
- **Files:** `requirements.txt`, `sim/__init__.py`, `sim/params.py`, `sim/state.py`, `run.py`
- **Spec:** `architecture.md` §4 (State, Params), §6 (structure)
- **Do:** create the package skeleton, the `Params` frozen dataclass with every symbol from
  `main.tex` (`m, I, l1, l2, g, T, A_x, A_z, A_m`), the `State` NamedTuple with index constants,
  and a `run.py` that builds a `Params`/`State` and prints them.
- **Check:** `python run.py` prints the parameter set. Nothing else.
- **Commit:** "Scaffolding: params and state containers"

### Step 2 — Vertical point mass: gravity + constant thrust
- **Files:** `sim/dynamics.py`, `sim/integrate.py`, `run.py`
- **Spec:** `architecture.md` §5 (interfaces), §2 (z-down convention)
- **Do:** `derivatives(t, y, p)` with `θ` frozen at π/2 and no aero — translation only.
  `run_sim()` wrapping `solve_ivp` with the guarded ground event (see the gotcha in
  `architecture.md` §1). Print apogee altitude, apogee time, impact time.
- **Check:** with `T` constant and no drag the answer is closed-form `a = T/m − g`; the printed
  apogee must match `½at_b²(1 + a/g)` analytically. This is the step that proves the integrator
  and the z-down sign convention are right — take it seriously, everything later rests on it.
- **Commit:** "Vertical point-mass flight under constant thrust and gravity"

### Step 3 — First plot (close the feedback loop early)
- **Files:** `sim/plotting.py`, `run.py`
- **Do:** altitude (`−z`) and vertical speed versus time. This is deliberately pulled forward
  from the end of the phase: from here on every step is checked by looking at a curve, not by
  reading numbers.
- **Check:** the plot shows a powered climb, a ballistic arc and a hard stop at ground impact.
- **Commit:** "Altitude and velocity plots"

### Step 4 — Constant axial aerodynamic force
- **Files:** `sim/forces.py` (new), `sim/dynamics.py`
- **Spec:** `main.tex` §Forces; `architecture.md` §4 (the seam)
- **Do:** move all force construction into `forces.py` with the final signatures
  `f(t, s, p) -> ...`. Phase 1 bodies just return the constants. Add `A_x` (still vertical
  flight, so `A_z` has no effect yet).
- **Check:** apogee is lower than in Step 3 with the same thrust; setting `A_x = 0` reproduces
  Step 3 exactly.
- **Note:** a constant drag magnitude is unphysical (it does not vanish at `v = 0` and does not
  reverse on descent). That is expected and intended at this stage — Step 10 fixes it. Just be
  aware the descent leg is nonsense until then.
- **Commit:** "Aerodynamic forces module, constant axial force"

### Step 5 — Frames: body↔inertial rotation, 2D translation at a fixed attitude
- **Files:** `sim/frames.py` (new), `sim/dynamics.py`, `tests/test_frames.py`
- **Spec:** `architecture.md` §2 (the rotation matrix and its sign checks)
- **Do:** `R_body_to_inertial(θ)`, `to_inertial`, `to_body`. `dynamics` now sums
  `W_inertial + R(θ)·(T_body + A_f_body)`. `θ` is still a fixed constant from `Params`, but now
  it can be something other than vertical.
- **Check:** `R(0) = I`; `R(π/2)` maps the body nose axis to inertial "up" (`(0,−1)`);
  `R·Rᵀ = I`. With `θ₀ = π/2` the result is identical to Step 4. With `θ₀ = 60°` the rocket
  flies a tilted trajectory with downrange motion.
- **Commit:** "Body-to-inertial rotation, 2D translation at fixed pitch"

### Step 6 — Rotational dynamics
- **Files:** `sim/state.py`, `sim/forces.py`, `sim/dynamics.py`, `tests/test_forces.py`
- **Spec:** `main.tex` §Moments, §Geometry, §Equations of motion; `architecture.md` §2
  ("Moments need no rotation at all")
- **Do:** `θ` and `ω` become integrated states. Moment about the CoG:
  `M_y = [aB×T + aA×A_f + A_m]·ŷ`, which with the current geometry reduces to
  `M_y = l₁·A_z − A_m`. Write the cross products explicitly in code so a future gimbal/thrust
  misalignment drops in — but assert in a test that the thrust term is zero today.
- **Check:** `A_z = A_m = 0` ⇒ `θ` constant ⇒ Step 5 result reproduced exactly. Non-zero `A_m`
  visibly pitches the rocket over.
- **Commit:** "Pitch dynamics: moments about the CoG"
- **Milestone:** all of `main.tex` (as of this writing) is now implemented.

### Step 7 — Full Phase 1 output
- **Files:** `sim/plotting.py`, `sim/integrate.py`, `run.py`
- **Do:** trajectory plot (downrange `x` vs altitude `−z`, equal aspect), time histories of
  altitude, speed, `θ` in degrees and `ω` in deg/s. Apogee event recorded in `Result.events`.
  Printed flight summary. Optional CSV dump.
- **Check:** a full, readable flight picture from a single `python run.py`.
- **Commit:** "Trajectory and pitch plots, flight summary"

### Step 8 — (optional) Hand-written RK4 cross-check
- **Files:** `sim/integrate.py`, `tests/test_dynamics.py`
- **Do:** a ~20-line fixed-step RK4 and a `method="rk4"` path through `run_sim`.
- **Check:** RK4 at small `dt` agrees with RK45 to within tolerance. This proves `dynamics.py`
  is genuinely solver-agnostic before Phase 2 makes the RHS complicated — and it is worth doing
  for its own sake if the "from scratch" goal includes the integrator.
- **Commit:** "Fixed-step RK4 integrator for cross-validation"

---

## Phase 2 — Real models, still 2D

Each step replaces one constant with a model. The pattern is always the same: rewrite one
function body in `forces.py`, add fields to `Params`, add a new module if the model is big
enough to deserve one. `dynamics.py` should not need to change at all except in Step 12.

**Before each step, re-read `main.tex`** — this phase is exactly where the user's derivation is
still growing (`§Models > Thrust` is currently a stub).

### Step 9 — Relative wind and angle of attack  ⚠ do this first
- **Files:** `sim/forces.py`, `sim/frames.py`
- **Why first:** `A_f = −A_x x̂_r − A_z ẑ_r` hard-codes the aero force direction against the body
  axes. That is only valid nose-first with positive axial speed. Every later aero model
  (`½ρV²S·C(α)`) needs `α` and `V_rel`, so this is the prerequisite for Steps 10 and 14 — and it
  makes the descent leg physical for the first time.
- **Do:** compute `v_rel` in the body frame (`to_body(v_inertial − v_wind, θ)`), speed
  `V = ‖v_rel‖`, angle of attack `α = atan2(w_body, u_body)`. Aero force direction now follows
  `v_rel` instead of being assumed.
- **Blocked on:** a `main.tex` update defining `α` and the aero force in terms of relative wind.
- **Check:** at `α = 0` the result reduces to Phase 1; drag now opposes motion on descent too.
- **Commit:** "Relative wind and angle of attack"

### Step 10 — Atmosphere model
- **Files:** `sim/atmosphere.py` (new), `sim/forces.py`, `sim/params.py`
- **Do:** ISA troposphere + lower stratosphere: `T(h)`, `p(h)`, `ρ(h)`, speed of sound `a(h)`,
  with `h = −z`. Aero forces become `½ρV²S·C_x`, `½ρV²S·C_z`, `½ρV²S·d·C_m` with the
  coefficients still constant. Add `S`, `d`, `C_x`, `C_z`, `C_m` to `Params`.
- **Check:** `ρ(0) ≈ 1.225 kg/m³`, `ρ(11 km) ≈ 0.364`; drag now falls with altitude and the
  apogee rises relative to Step 9.
- **Commit:** "ISA atmosphere, dynamic-pressure-based aero forces"

### Step 11 — Thrust curve
- **Files:** `sim/thrust_curve.py` (new), `data/<motor>.csv`, `sim/forces.py`
- **Spec:** `main.tex` §Models > Thrust (check what the user has derived by then)
- **Do:** load a (time, thrust) table, linear interpolation, `T = 0` after burnout. A `burnout`
  event in `integrate.py`.
- **Check:** the integral of the curve equals the motor's total impulse; the acceleration trace
  shows ignition spike, tail-off and a clean cut at burnout.
- **Commit:** "Thrust curve interpolation"

### Step 12 — Propellant depletion: variable mass
- **Files:** `sim/state.py`, `sim/dynamics.py`, `sim/params.py`
- **Do:** mass becomes the 7th state component with `ṁ = −T(t)/(I_sp·g₀)` (or a mass-flow table).
  `I`, `l₁`, `l₂` become functions of the current propellant mass.
- **Blocked on:** `main.tex` — "CoG doesn't change" in §Current assumptions directly contradicts
  this step. Needs the user's derivation of `I(t)` and the CoG shift before implementation.
- **Check:** final mass equals dry mass; with `l₁, l₂` held fixed the trajectory changes only
  through `m(t)`, which isolates the effect.
- **Commit:** "Propellant depletion: mass, inertia and CoG as states"

### Step 13 — Pressure correction to thrust
- **Files:** `sim/thrust_curve.py`, `sim/params.py`
- **Spec:** `main.tex` §Models > Thrust — the pressure-effect derivation the user is planning
- **Do:** `T(t, h) = T_ref(t) + A_e·(p_ref − p_amb(h))` (exact form per the LaTeX), using the
  atmosphere from Step 10.
- **Check:** thrust rises a few percent with altitude; at sea level it reproduces Step 11.
- **Commit:** "Altitude pressure correction on thrust"

### Step 14 — Aerodynamic coefficients as functions
- **Files:** `sim/aero.py` (new), `sim/forces.py`, `data/aero.csv`
- **Do:** `C_x(M, α)`, `C_z(α)`, `C_m(α)` from tables or polynomials, with `M = V/a(h)`. Centre
  of pressure travel makes `l₁` a function of `(α, M)` — which couples straight back into the
  moment equation from Step 6.
- **Check:** static margin `(l₁ > 0)` produces a restoring moment; the rocket weathercocks into
  the relative wind instead of tumbling.
- **Commit:** "Mach- and alpha-dependent aerodynamic coefficients"

### Step 15 — Wind
- **Files:** `sim/wind.py` (new), `sim/forces.py`
- **Do:** `v_wind(t, h)` — constant plus a shear profile, optional seeded gusts. Enters purely
  through `v_rel` from Step 9, so no other module changes.
- **Check:** crosswind produces weathercocking and downrange drift in the expected direction.
- **Commit:** "Wind model"

### Step 16 — Launch rail
- **Files:** `sim/integrate.py`, `sim/dynamics.py`
- **Do:** while `‖r − r₀‖ < L_rail`, constrain motion to the rail direction and hold `θ` fixed
  (`ω = θ̈ = 0`); a rail-exit event switches to free flight. This matters more than it looks —
  rail-exit velocity is what determines whether the wind model above tips the rocket over.
- **Check:** rail-exit speed is reported; `L_rail = 0` reproduces Step 15.
- **Commit:** "Launch rail constraint and rail-exit event"

### Step 17 — (optional) Recovery
- **Files:** `sim/forces.py`, `sim/integrate.py`
- **Do:** parachute deployment triggered by the apogee event (or a timer): swap the drag model
  for `½ρV²·C_dS_chute`, with attitude dynamics disabled or heavily damped under canopy.
- **Check:** descent settles at the analytic terminal velocity `√(2mg/ρC_dS)`.
- **Commit:** "Parachute recovery"

---

## Phase 3 — 3D, full 6-DOF

### Attitude representation: quaternions — recommended

Euler angles must be rejected here for a concrete reason, not a stylistic one: the standard
aerospace 3-2-1 sequence is singular at pitch `±90°`, and a vertically launched rocket **sits at
that singularity** for the entire boost phase. The kinematic equations blow up exactly where the
simulation spends most of its accuracy budget. Quaternions have no singularity, their kinematics
`q̇ = ½ q ⊗ ω` are cheaper than the Euler rate matrix, and the only costs are a 4th state
component and a renormalisation. Euler angles are still computed — but only in `plotting.py`,
for human-readable output.

(Rotation matrices as the state, 9 components with 6 constraints, are the third option: no
singularity either, but more drift to correct and no advantage over quaternions.)

### Step 18 — Quaternion algebra
- **Files:** `sim/quaternion.py` (new), `tests/test_quaternion.py`
- **Do:** multiply, conjugate, normalise, rotate a vector, `from_euler` / `to_euler`,
  `q̇ = ½ q ⊗ ω`, and the 3×3 DCM.
- **Check:** round-trip `euler → q → euler`; a pitch-only quaternion reproduces the 2D
  `R_body_to_inertial` from Step 5 exactly. Pure algebra, no dynamics — fully testable alone.
- **Commit:** "Quaternion algebra"

### Step 19 — 3D state and translation
- **Files:** `sim/state3d.py`, `sim/dynamics3d.py`, `sim/forces3d.py`
- **Do:** 13-component state `[r(3), v(3), q(4), ω(3)]`. Translation only, attitude held fixed:
  `m·v̇ = W + R(q)·(T_body + A_body)` in NED — the same equation as Phase 1 with a 3×3 rotation.
- **Check:** planar initial conditions reproduce the Phase 1 trajectory to solver tolerance.
- **Commit:** "3D state vector and translational dynamics"

### Step 20 — 3D rotational dynamics
- **Files:** `sim/dynamics3d.py`
- **Do:** Euler's equations `ω̇ = I⁻¹(M − ω × I ω)` with the inertia tensor, plus `q̇` and
  renormalisation each step (or as a solver event).
- **Blocked on:** a `main.tex` extension of §Equations of motion to 3D (inertia tensor, the
  `ω × Iω` gyroscopic term).
- **Check:** with a body-symmetric rocket and planar initial conditions the Phase 1 pitch history
  is reproduced; `‖q‖ = 1` holds throughout; torque-free motion conserves angular momentum.
- **Commit:** "Full 6-DOF rotational dynamics"

### Step 21 — 3D aerodynamics
- **Files:** `sim/aero.py`, `sim/forces3d.py`
- **Do:** total angle of attack from the 3D relative wind, sideslip `β`, normal force in the
  correct plane, roll moment from fin cant, roll and pitch damping.
- **Check:** zero sideslip reproduces Step 20; fin cant produces a steady roll rate.
- **Commit:** "3D aerodynamics: sideslip, roll and damping"

### Step 22 — 3D output and regression
- **Files:** `sim/plotting.py`, `run.py`, `tests/`
- **Do:** 3D trajectory plot, ground track, Euler-angle time histories, and a regression test
  pinning the 2D-equivalent case.
- **Check:** the planar case still matches Phase 1. That single test is what keeps the 6-DOF code
  honest.
- **Commit:** "3D visualisation and 2D regression test"

---

## Dependency summary

```
1 → 2 → 3 → 4 → 5 → 6 → 7 → [8]            Phase 1 (all constants)
                            ↓
        9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → [17]    Phase 2 (real models)
                            ↓
                      18 → 19 → 20 → 21 → 22            Phase 3 (6-DOF)
```

Steps in `[brackets]` are optional. Steps 9, 12, 13 and 20 are **blocked on `main.tex` updates**
from the user — see `architecture.md` §9 for the exact questions.

# Roadmap — Rocket Trajectory Simulator

## Summary

Step-by-step build plan, one small committable increment per step. Phase 1 (Steps 1-8) builds
the complete 2D planar rigid-body simulator from `main.tex` with every force as a constant,
ending with a working trajectory plot — **DONE and committed**. Phase 2 (Steps 9-27) replaces
those constants with real models: relative wind/α first (now unblocked by `main.tex`), then
**four gravity models**, ISA atmosphere, thrust curve + mass + pressure correction, then the
**real-data tiers** (single-station soundings, then multi-station spatial interpolation) for
**atmosphere and wind alike**, and finally Mach/α-dependent aero coefficients — **DONE and
committed**. Phase 2.5 (Steps 33-37) is a documentation-and-review follow-up: drop the linear
gravity model, fix the aero force to stay in body axis, add variable mass (CoG/I travel) and a
Coriolis/centrifugal correction — **DONE and committed**. Phase 2.6 (Steps 38-40) promotes three
deferred items to real physics: non-parallel gravity, a fixed thrust-axis misalignment, and
humid-air density — **DONE and committed, still 2D**. Phase 2.7 (Steps 41-44) promotes four more:
elliptical gravity direction, curved-ground impact condition, lateral offsets `u_B`/`u_C`, and a
pitch-damping `c_mq` scaffold — **DONE and committed, still 2D**. Phase 3 (Steps 28-32,
renumbered from 18-22) extends to 6-DOF using **quaternions** (Euler angles are singular at pitch
±90°, a rocket's nominal attitude) — **not worked on yet**. Launch rail and recovery are moved to
**Backlog / later**. Architecture reference: `architecture.md` §1-§10 (Phase 1), §11-§22
(Phase 2, **with Phase 2.5 resolutions inline**), §23 (Phase 2.6), §24 (Phase 2.7). Physics
reference: `latex/main.tex` plus `latex/sections-ai/{rocket-2d,analysis,models}.tex` (the section
files moved from `latex/sections/` — earlier citations mean the same content at the new path).
Rule for every step: re-read the relevant LaTeX section first, because the user keeps extending
the derivation.

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
5. If a step reveals a physics question (see `architecture.md` §9 for Phase 1, **§22 for
   Phase 2**), stop and ask rather than guessing a sign.
6. **Phase 2 additions must default to the previous step's behaviour.** Every new `Params` field
   gets a default that reproduces the run before it, so the Phase 1 test suite keeps passing
   unchanged through all of Phase 2 (`architecture.md` §18, §20).

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
  reverse on descent). That is expected and intended at this stage — Step 9 fixes the direction
  and Step 13 the magnitude. Just be aware the descent leg is nonsense until then.
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

Each step replaces one constant with a model, or adds one model variant. The pattern is always
the same: rewrite one function body in `forces.py`, add fields to `Params` (always with a default
that reproduces the previous step), add a new module when the model deserves one. **`dynamics.py`
does not change in the whole of Phase 2 except in Step 15** (variable mass).

Spec for this phase: `main.tex` §"Relative wind and angle of attack" and §Models > {Gravity,
Atmosphere, Wind}; `architecture.md` **§11-§22**. Each step below names the exact section it
needs — do not read the whole architecture document for a single step.

**Approval gate before Step 10:** `architecture.md` §22 items 1-4 (the model-selection pattern,
the sounding file format, no-pandas, no-live-API) must be answered by the user first. Step 9 is
unaffected and can start immediately.

**Before each step, re-read `main.tex`** — this phase is exactly where the user's derivation is
still growing (`§Models > Thrust` is still a stub).

**After every step, re-run the full Phase 1 test suite.** With `gravity_model="constant"`,
`aero_model="constant"` and `wind_model="none"` the Phase 1 results must stay bit-for-bit
identical. That regression is what keeps 19 steps of model-building honest.

### Step 9 — Relative wind and angle of attack  ⚠ do this first, now unblocked
- **Files:** `sim/flow.py` (new), `sim/forces.py`, `tests/test_flow.py` (new)
- **Spec:** `main.tex` §"Relative wind and angle of attack"; `architecture.md` §15
- **Why first:** every later aero model needs `V`, `α`, `û`, `n̂`. Nothing else in Phase 2 can
  start until this exists.
- **Do:** `flow.flow_state(t, y, p) -> Flow` with `v_rel = to_body(v_i − v_w, θ)`,
  `V = ‖v_rel‖`, `α = atan2(w, u)`, `û = (cos α, sin α)`, `n̂ = (−sin α, cos α)`. Wind is zero
  for now (a stub `wind_inertial` returning zeros, or inline zeros — Step 21 fills it in).
  Rewrite `aero_force_body` as `−A_x·û − A_z·n̂` with `A_x, A_z` still the `Params` constants.
  Add `altitude_agl` / `altitude_msl` helpers.
- **Optional tidy (behaviour-preserving):** in `dynamics.derivatives`, compute `thrust_body` and
  `aero_force_body` once into locals and reuse them for the moment instead of calling them twice.
  Identical numbers; halves the model evaluations for the rest of Phase 2.
- **Check:** with zero wind and `θ` such that `α = 0`, the aero force equals `(−A_x, −A_z)` and
  the whole Phase 1 test suite passes unchanged; on the descent leg drag now opposes the motion
  instead of pointing at the nose.
- **Commit:** "Relative wind, angle of attack and the aero force direction"

### Step 10 — Gravity models: constant, linear, radial
*(`linear` removed at Phase 2.5 Step 34 — kept here as the historical record of what this step
originally did and why.)*
- **Files:** `sim/gravity.py` (new), `sim/params.py`, `sim/forces.py`, `tests/test_gravity.py`
- **Spec:** `main.tex` §Models > Gravity; `architecture.md` §12 (the dispatch pattern) and §13
- **Do:** `gravity.g(t, y, p) -> float` dispatching on `p.gravity_model` over three private
  variants: `g₀`, `g₀(1 − 2h/R_e)`, `g₀(R_e/(R_e+h))²`, with `h = −z`. `weight_inertial` becomes
  `[0, m·gravity.g(t, y, p)]`. Add `gravity_model` and `R_e` to `Params`.
- **Check:** all three agree at `h = 0`; `linear` and `radial` agree to ~1e-6 relative at 10 km
  and visibly diverge at 100 km; `"constant"` reproduces Step 9 exactly.
- **Commit:** "Gravity models: constant, linear and radial"

### Step 11 — Gravity: the real-data (WGS84 normal gravity) variant
- **Files:** `sim/gravity.py`, `sim/params.py`, `tests/test_gravity.py`
- **Spec:** `architecture.md` §13 ("the `wgs84` variant" — the formula and constants are there)
- **Do:** the Somigliana normal-gravity formula plus the second-order free-air correction,
  `g(φ, h_msl)`, with `φ = p.lat0_deg` and `h_msl = p.h0_m − z`. Add `lat0_deg`, `lon0_deg`,
  `h0_m`, `azimuth_deg` to `Params` (the site block; the last three are also used from Step 12
  and Step 19 onward).
- **Check:** 9.7803 m/s² at the equator, 9.8322 at the pole, 9.80665 near 45.5° at sea level;
  the altitude dependence matches `radial` to ~1e-4 relative over 0-30 km.
- **Commit:** "WGS84 normal gravity model"

### Step 12 — ISA atmosphere
- **Files:** `sim/atmosphere.py` (new), `sim/params.py`, `tests/test_atmosphere.py`
- **Spec:** `main.tex` §Models > Atmosphere; `architecture.md` §14 (the layer table is there)
- **Do:** `air_state(t, y, p) -> AirState(rho, p, T, a, mu)` dispatching on
  `p.atmosphere_model`, with the `"isa"` variant implemented: geopotential altitude, the 7-layer
  table, hydrostatic pressure, gas-law density, `a = √(γR_dT)`, Sutherland viscosity. Uses
  `h_msl`. No force changes in this step — the atmosphere is not wired into anything yet.
- **Careful:** the `g = 9.80665` inside the pressure integral is part of the ISA definition and
  must **not** come from `gravity.g()` (`architecture.md` §14).
- **Check:** `ρ(0)=1.225`, `p(11 km)=22632 Pa`, `T(20 km)=216.65 K`, `a(0)=340.29 m/s`,
  `μ(288.15 K)=1.789e-5 Pa·s`; ρ monotone decreasing to 80 km.
- **Commit:** "ISA atmosphere model"

### Step 13 — Dynamic-pressure aero forces, Reynolds and Mach
- **Files:** `sim/flow.py`, `sim/forces.py`, `sim/params.py`, `tests/test_flow.py`
- **Spec:** `main.tex` §Models > Atmosphere (the `Re`, `M` definitions), §Forces;
  `architecture.md` §15, §12 (`aero_model`)
- **Do:** `Flow` gains `air`, `q = ½ρV²`, `M = V/a`, `Re = ρVl_ref/μ`. Add `aero_model` to
  `Params` with `"constant"` (Phase 1 behaviour) and `"coefficients"`
  (`A_x = qS·C_A0`, `A_z = qS·C_Nα·α`, `A_m = qS·d_ref·C_mα·α`). Add `S`, `d_ref`, `l_ref`,
  `C_A0`, `C_N_alpha`, `C_m_alpha`.
- **Check:** `aero_model="constant"` reproduces Step 12 exactly; with `"coefficients"` drag now
  vanishes at `V = 0`, reverses on descent and falls with altitude, and the apogee moves in the
  expected direction. Sanity-check `Re ~ 10⁵-10⁷` and `M < 1` for a small rocket.
- **Commit:** "Dynamic-pressure aerodynamic forces with Reynolds and Mach numbers"

### Step 14 — Thrust curve
- **Files:** `sim/thrust_curve.py` (new), `data/motors/<motor>.csv` (new), `sim/forces.py`,
  `sim/integrate.py`, `sim/params.py`
- **Spec:** `main.tex` §Models > Thrust (check what the user has derived by then);
  `architecture.md` §19
- **Do:** load a `t_s,thrust_N` table through an `lru_cache`d loader, `np.interp`, zero after the
  last point. Removes the `T_BURN` hack from `forces.py`. Add a `burnout` event to
  `integrate.py`.
- **Check:** the trapezoidal integral of the curve equals the motor's stated total impulse; the
  acceleration trace shows the ignition spike, the tail-off and a clean cut at burnout.
- **Commit:** "Thrust curve interpolation and burnout event"

### Step 15 — Propellant depletion: variable mass
- **Files:** `sim/state.py`, `sim/dynamics.py`, `sim/params.py`, `tests/test_dynamics.py`
- **Spec:** `architecture.md` §4 (7th state component), §19
- **Blocked on:** `main.tex` — "CoG doesn't change" in §Current assumptions directly contradicts
  this step. Needs the user's derivation of `I(t)` and the CoG shift first
  (`architecture.md` §22 item 6).
- **Do:** `m` becomes the 7th state component, `ṁ = −T(t)/(I_sp·g₀)` (or a mass-flow table).
  This is the **only** step in Phase 2 that touches `dynamics.py`'s equations.
- **Check:** the final mass equals the dry mass; with `I`, `l₁`, `l₂` held fixed the trajectory
  changes only through `m(t)`, isolating the effect.
- **Commit:** "Propellant depletion: mass as a state"

### Step 16 — Pressure correction to thrust
- **Files:** `sim/thrust_curve.py`, `sim/params.py`
- **Spec:** `main.tex` §Models > Thrust — the pressure-effect derivation; `architecture.md` §19
- **Do:** `T(t, h) = T_ref(t) + A_e·(p_ref − p_amb)` with `p_amb` from `atmosphere.air_state`.
  First consumer of the atmosphere outside the aero forces — and it will work unchanged with the
  real-data tiers added in Steps 18 and 20.
- **Check:** thrust rises a few percent with altitude; `A_e = 0` reproduces Step 15.
- **Commit:** "Altitude pressure correction on thrust"

### Step 17 — Sounding data: format, loader, altitude interpolation
- **Files:** `sim/soundings.py` (new), `data/soundings/<case>/*.csv` (new, one worked example),
  `tests/test_soundings.py`
- **Spec:** `architecture.md` §17 (file format, loading rules, interpolation table)
- **Requires:** `architecture.md` §22 items 2-4 approved (format, no pandas, no live API).
- **Do:** the shared data layer for **both** atmosphere and wind tiers 2-3, and nothing else —
  no physics changes in this step. `np.genfromtxt` + a comment-header metadata parser →
  `Sounding` NamedTuple (wind stored as ENU `u`, `v` components, converted at load time);
  `load_case()` behind `lru_cache`; altitude interpolation with `T` linear, `ln p` linear,
  `u`/`v` linear, `ρ`/`a`/`μ` derived; ISA-anchored extrapolation above the top level and
  lapse-rate extrapolation below the bottom.
- **Check:** generate a synthetic sounding CSV **from the ISA model itself**, load it back and
  interpolate — the result must match ISA to within 0.5 % in ρ, p and T across 0-20 km. That one
  test covers the format, the loader and the interpolation at once.
- **Commit:** "Sounding data format, loader and altitude interpolation"

### Step 18 — Atmosphere tier 2: single-station real data
- **Files:** `sim/atmosphere.py`, `sim/params.py`, `tests/test_atmosphere.py`
- **Spec:** `main.tex` §Models > Atmosphere item 2; `architecture.md` §14, §17
- **Do:** the `"sounding"` variant — `air_state` reads the single sounding in
  `p.sounding_case` and returns the same `AirState`. Add `sounding_case` to `Params`.
- **Check:** with the ISA-derived synthetic case from Step 17, the trajectory matches the
  `"isa"` run to within the interpolation error; with a real sounding, sea-level density and
  apogee shift in a physically sensible direction.
- **Commit:** "Atmosphere tier 2: single-station sounding data"

### Step 19 — Horizontal interpolation core (stations → local tangent plane, IDW)
- **Files:** `sim/soundings.py`, `sim/params.py`, `tests/test_soundings.py`
- **Spec:** `architecture.md` §17 ("Interpolation in horizontal position")
- **Do:** again pure infrastructure, no physics change. Equirectangular projection of station
  `(lat, lon)` into a launch-site-centred tangent plane; the rocket's ground position as
  `(x·sin A, x·cos A)`; resampling of all stations onto a common altitude grid at load time;
  inverse-distance weighting with `idw_epsilon_m`, plus the optional `"rbf"` path through
  `scipy.interpolate.RBFInterpolator`. Add `horizontal_interp`, `grid_top_m`, `grid_step_m`,
  `idw_epsilon_m`.
- **Check:** one station ⇒ the tier-2 profile exactly; a query at a station's own coordinates ⇒
  that station's profile; two identical stations ⇒ the same profile everywhere; projected
  station distances match a great-circle reference to <0.1 % inside 100 km.
- **Commit:** "Horizontal station interpolation: tangent-plane projection and IDW"

### Step 20 — Atmosphere tier 3: multi-station spatial interpolation
- **Files:** `sim/atmosphere.py`, `tests/test_atmosphere.py`, `data/soundings/<case>/` (a
  multi-station example)
- **Spec:** `main.tex` §Models > Atmosphere item 3; `architecture.md` §14, §17
- **Do:** the `"field"` variant — combine stations horizontally at the rocket's current ground
  position, then interpolate in altitude. This is the first model whose output depends on `x`.
- **Check:** a case folder with a single station reproduces Step 18 exactly; with two stations
  differing in sea-level pressure, the sampled density varies monotonically along the ground
  track.
- **Commit:** "Atmosphere tier 3: multi-station spatially interpolated data"

### Step 21 — Wind tier 1: analytic model
- **Files:** `sim/wind.py` (new), `sim/flow.py`, `sim/params.py`, `tests/test_wind.py`
- **Spec:** `main.tex` §Models > Wind item 1; `architecture.md` §16
- **Note on ordering:** this step depends only on Step 13, not on Steps 17-20. Pull it forward
  to straight after Step 13 if you want a non-zero `α` early; it is placed here only to keep the
  shared-data-layer steps adjacent.
- **Do:** `wind_inertial(t, y, p)` dispatching on `p.wind_model`, with `"none"` (zeros, the
  default) and `"analytic"` (power-law shear + constant direction) implemented, and the
  meteorological-direction → downrange-component conversion of `architecture.md` §16. Wire it
  into `flow.flow_state`. Optional gusts **must** be a deterministic, seeded, frozen-phase
  sinusoid sum — never a per-call random draw (it would break the adaptive solver).
- **Check:** `"none"` reproduces Step 20 bit-for-bit; a pure headwind raises `V` by exactly the
  wind speed; the four cardinal wind directions map to the expected downrange sign; a tailwind
  and a headwind of the same speed bracket the still-air apogee.
- **Commit:** "Wind tier 1: analytic shear profile"

### Step 22 — Wind tier 2: single-station real data
- **Files:** `sim/wind.py`, `tests/test_wind.py`
- **Spec:** `main.tex` §Models > Wind item 2; `architecture.md` §16, §17
- **Do:** the `"sounding"` variant, reading `u(h)`, `v(h)` from the same `p.sounding_case` files
  the atmosphere already uses — no new format, no new loader, no new `Params` field.
- **Check:** a synthetic constant-wind sounding reproduces the analytic model with
  `shear_exp = 0`; a real profile shows the wind veering with altitude.
- **Commit:** "Wind tier 2: single-station sounding data"

### Step 23 — Wind tier 3: multi-station spatial interpolation
- **Files:** `sim/wind.py`, `tests/test_wind.py`
- **Spec:** `main.tex` §Models > Wind item 3; `architecture.md` §16, §17
- **Do:** the `"field"` variant, reusing the Step 19 weighting machinery unchanged. By
  construction this should be a handful of lines — if it is not, Step 19 drew the seam in the
  wrong place.
- **Check:** a single-station case reproduces Step 22 exactly; with two stations of opposing
  wind direction, the wind sampled along the ground track reverses smoothly.
- **Commit:** "Wind tier 3: multi-station spatially interpolated data"

### Step 24 — (optional) Interpolation in time between sounding snapshots
- **Files:** `sim/soundings.py`, `sim/params.py`
- **Spec:** `architecture.md` §17 ("Time")
- **Do:** with `p.t0_utc` set, map sim time onto wall clock and linearly blend the two bracketing
  snapshots per station. Without it, the nearest snapshot is used (current behaviour).
- **Check:** two identical snapshots at different times give a time-invariant profile; a single
  snapshot reproduces Step 23.
- **Commit:** "Time interpolation between sounding snapshots"

### Step 25 — Aerodynamic coefficients as functions of α and M
- **Files:** `sim/aero.py` (new), `sim/forces.py`, `data/aero/<config>.csv` (new),
  `tests/test_aero.py`
- **Spec:** `main.tex` §Forces (`C_A(α, M)`, `C_N(α)`); `architecture.md` §19
- **Do:** `C_A(α, M)`, `C_N(α)`, `C_m(α, M)` from a table (`np.interp` in α, bracketed in M) with
  the `Params` constants as the fallback. CoP travel makes `l₁` a function of `(α, M)`, feeding
  straight back into the Step 6 moment equation. This is the step that makes `Re` and `M`
  load-bearing rather than merely computed.
- **⚠ Sign question, resolve before starting:** under `main.tex`'s geometry the aero moment is
  `M_y = l₁(A_x sin α + A_z cos α)`, so `l₁ > 0` is **divergent**, not restoring — static
  stability needs `l₁ < 0` (CoP aft of the CoG). Confirm the convention with the user
  (`architecture.md` §22 item 5) rather than guessing; the previous version of this roadmap had
  it backwards.
- **Check:** with the confirmed stable sign, the rocket weathercocks into the relative wind
  instead of tumbling, and `α` decays after a wind gust instead of growing.
- **Commit:** "Mach- and alpha-dependent aerodynamic coefficients"

### Step 26 — (optional) `tools/fetch_sounding.py`
- **Files:** `tools/fetch_sounding.py` (new)
- **Requires:** explicit approval — this is the only part of the project that touches the network
  (`architecture.md` §22 item 4).
- **Do:** a hand-run script (never imported by `sim/`) that downloads a sounding with stdlib
  `urllib` and writes the canonical CSV of `architecture.md` §17. The simulator stays offline and
  deterministic; only the data acquisition moves out of the browser.
- **Check:** the fetched file loads with the Step 17 loader with no edits.
- **Commit:** "Offline sounding fetch helper"

### Step 27 — Model comparison sweep and overlay plots
- **Files:** `run.py`, `sim/plotting.py`
- **Spec:** `architecture.md` §12 (this step is the payoff for the selection pattern)
- **Do:** a small sweep helper — `dataclasses.replace(p, gravity_model=...)` over a list of model
  selections, one `run_sim` each, and an overlay plot plus a table of apogee / max-Q / impact per
  variant. The point of having four gravity and three atmosphere models is comparing them.
- **Check:** the four gravity models differ by a predictable, small amount at a 3 km apogee and a
  visible one at 100 km; ISA vs a real sounding shows where the real atmosphere matters.
- **Commit:** "Model comparison sweeps and overlay plots"
- **Milestone:** Phase 2 complete — every model in `main.tex` §Models implemented and selectable.

---

## Phase 2.5 — Corrections and extensions (still 2D)

Five follow-up steps raised by reviewing `main.tex`/`architecture.md` against the code after
Phase 2 closed: one documentation-only step, one removal, one bug fix, and two new physics items
(one previously blocked, one previously not tracked at all). Phase 3 (3D, quaternions) is
deliberately not worked on yet — these steps stay 2D, same discipline as Phase 2 (one step, one
commit, re-run the Phase 1/2 regression suite after each).

### Step 33 — Documentation restructuring
- **Files:** `latex/main.tex`, `latex/sections/rocket-2d.tex`, `latex/sections/models.tex`
- **Do:** move the real (non-stub) content out of `main.tex`'s old `§Archived models` into the
  matching `models.tex` stub subsections; add the `§Current assumptions` section main.tex had
  been referencing without ever defining; fill previously-empty stubs (frame axis definitions,
  gravity direction, Reynolds/Mach, aero-coefficient "what affects them") with base text; fix the
  missing `V, α` equation in §Relative wind and angle of attack; clarify the `{}^r(\cdot)` notation
  in §Analytical analysis as a body-axis projection, not a rotating-frame derivative. AI-authored
  text marked with the new `\ai{}` command (blue), so it's visually distinct from the user's own
  writing. No code changes.
- **Check:** the three `.tex` files still balance (braces, `\begin`/`\end` pairs); nothing the
  user wrote was deleted, only relocated or extended; every `\todo` for work not done in this step
  is still present.
- **Commit:** "Documentation restructuring: consolidate models.tex, add Current assumptions"

### Step 34 — Remove the linear gravity model
- **Files:** `sim/gravity.py`, `tests/test_gravity.py`, `run.py`, `architecture.md`, `roadmap.md`
  (this file, Step 10's wording), `latex/main.tex` (done in Step 33)
- **Why:** weakest of the four variants — a first-order truncation of inverse-square that goes
  negative above `h = R_e/2` — and strictly dominated by `radial`, which is exact and equally
  cheap to evaluate.
- **Do:** delete `_g_linear` and its `_GRAVITY_MODELS["linear"]` entry from `sim/gravity.py`;
  remove the corresponding test cases from `tests/test_gravity.py`; drop `"linear"` from the
  Step-27 comparison sweep in `run.py`; reword "four gravity models"/"four variants" down to
  three wherever it appears in `architecture.md`/`roadmap.md`.
- **Check:** `p.gravity_model = "linear"` now raises `KeyError` (no silent fallback); the three
  remaining models and every other test still pass unchanged.
- **Commit:** "Remove the linear gravity model"

### Step 35 — Aerodynamic force in body axis, not wind axis
- **Files:** `sim/forces.py`, `tests/test_forces.py`, `architecture.md` §15
- **Why:** `main.tex` §Models > Aerodynamics (Step 33) now states the aero force stays resolved
  along the fixed body axes `x̂_r, ẑ_r` — matching the body-axis (axial/normal) convention the
  aero-coefficient CFD/wind-tunnel data is extracted in — not rotated into the relative-wind frame
  `û, n̂`. The two conventions agree at `α = 0` (why the Step-9 regression test didn't catch this)
  and diverge exactly where it matters: nonzero angle of attack.
- **Do:** in `aero_force_body`, replace `-A_x*flow.u_hat - A_z*flow.n_hat` with the plain body-axis
  vector `np.array([-A_x, -A_z])`. `flow.u_hat`/`flow.n_hat` stay in `flow.py` — still needed to
  compute `V, α, q` — just no longer used to redirect the force. No change to `aero_moment_y`
  (the moment was already a scalar about `ŷ_r`, frame-independent).
- **Check:** bit-for-bit identical to the current behaviour at `α = 0` (the Phase 1/2 regression
  suite is unaffected); at nonzero `α` the force direction changes and should be sanity-checked
  against a hand-worked example before relying on it for the stability-margin work in
  `rocket-2d.tex` §Analytical analysis.
- **Found during this step, fixed in the same commit — `sim/aero.py`'s constant-fallback `C_N`/
  `C_m`:** the full regression suite hung (not merely slow — still running after 90+ seconds on a
  scenario the pre-Step-35 code finished in ~1s). Traced to an unperturbed, symmetric vertical
  flight (no wind, no off-axis launch) coasting through `V = 0` at apogee with `theta` unchanged
  (no restoring moment ever having engaged), landing the rocket tail-first (`alpha` near `±π`)
  right where `atan2(w, u)` sits on its own branch cut — floating-point noise in `w` alone flips
  `alpha` between `+π` and `−π` every solver evaluation, and the fallback's *unbounded* linear
  `C_N = C_N_alpha·alpha` turned that into a multi-unit jump in the moment every RHS call, which
  `solve_ivp`'s adaptive step control could not recover from. A magnitude clamp on `alpha` was
  tried first and does not fix it (any discontinuity, however small, still defeats the solver's
  local-smoothness assumption) — the fix that works is `C_N = C_N_alpha·sin(alpha)` (and same for
  `C_m`): continuous everywhere, `≈alpha` to well within this fallback's own small-angle error at
  realistic angles (<0.4% at 8.6°), and arguably more physically honest at large `alpha` besides
  (correctly zero at exactly tail-first, by symmetry, instead of a large nonsensical value). See
  `sim/aero.py`'s module docstring for the full derivation. One exact-equality test
  (`tests/test_aero.py::test_no_table_reproduces_pre_step25_coefficients_exactly`) updated to
  assert against `sin(alpha)`; `tests/test_forces.py`'s old/new-sign contrast test re-verified and
  re-pinned (the old-sign case no longer runs away monotonically now that `C_N` saturates — it
  tumbles instead, which the test now checks for directly).
- **Commit:** "Aerodynamic force resolved in body axis, not wind axis"

### Step 36 — Variable mass: CoG and moment-of-inertia travel
- **Files:** `sim/state.py`, `sim/dynamics.py`, `sim/params.py`, `sim/forces.py`,
  `tests/test_dynamics.py`
- **Spec:** `main.tex` §Models > Mass and moment of inertia (Step 33) — the two-lumped-mass model:
  `ṁ(t) = -T_ref(t)/(I_sp·g0)`, `l_B(t)` the mass-weighted centroid, `I(t)` via the parallel-axis
  theorem. Supersedes the old blocked Step 15.
- **Do:** `m` becomes the 7th state component (`ṁ` above); `l_B(t)`, `I(t)` recomputed each RHS
  call from `m(t)` and the `Params` constants `m_d, l_d, l_p, I_d`, replacing the fixed `p.I`,
  `p.l1`(`l_B`) wherever the moment equation (`rocket-2d.tex` §Equations of motion) uses them.
  Placeholder grain model per `main.tex`'s `\todo`: `l_p` constant, `I_p(t) ∝ m_p(t)` (uniform
  density, fixed shape) until real grain geometry is supplied.
- **Check:** final `m` equals the dry mass `m_d`; with `l_p = l_d` (no CoG shift) the trajectory
  is unchanged from Step 35, isolating the effect of `l_B(t) ≠ l_d` when a real offset is set.
- **Commit:** "Propellant depletion: CoG and moment-of-inertia travel"

### Step 37 — Non-inertial (Coriolis/centrifugal) correction — done
- **Files:** `sim/rotation.py` (new), `sim/dynamics.py`, `sim/params.py`, `tests/test_dynamics.py`
- **Spec:** `main.tex` §Models > Non-inertial frame corrections (Step 33) — the standard
  `a_Coriolis = -2Ω×v`, `a_centrifugal = -Ω×(Ω×r)` terms; derivation resolved in
  `latex/sections/models.tex` §Non-inertial frame corrections (commit `a98f283`), reviewed and
  scoped by the user (Option B, below).
- **Resolved projection:** `Ω = Ω(cosφ₀cosχ x̂_g − cosφ₀sinχ ŷ_g − sinφ₀ ẑ_g)` (ẑ_g down); the
  in-plane Coriolis term comes *only* from the plane-normal component `Ω_y`, giving
  `a_Cor,2D = 2Ω cosφ₀ sinχ (ż x̂_g − ẋ ẑ_g)`. The in-plane components of `Ω` (`Ω_x`, `Ω_z`)
  produce a purely lateral acceleration a 2D model cannot carry — a documented closure, not a
  smallness argument.
- **Scope decision (Option B, user-approved):** in-plane Coriolis only, gated by
  `p.earth_rotation: bool` (default `False`, bit-for-bit pre-Step-37). The discarded lateral
  (out-of-plane, `y_g`) component is computed and exposed as a labeled diagnostic
  (`sim.rotation.coriolis_lateral_diagnostic`) — never fed back into the state, since this is a
  genuinely 2D model with no lateral DOF to receive it — so a due-North/South launch
  (`χ=0°`/`180°`, where the *retained* in-plane term is exactly zero) does not read as "no
  Coriolis effect here". The residual centrifugal term (Option D) is **not** implemented: ~3
  orders of magnitude below Coriolis, and its vertical part risks double-counting against the
  WGS84 free-air correction; documented in `sim/rotation.py`'s module docstring, not built.
- **Check:** `earth_rotation=False` reproduces every prior step bit-for-bit (verified directly —
  `test_earth_rotation_off_reproduces_derivatives_bit_for_bit`); with it on, the vertical-launch,
  ~4.6 km-apogee scenario already used elsewhere in `tests/test_dynamics.py` deflects downrange by
  ~8.4 m at apogee (`φ₀=50°`, `χ=90°`, apogee at t~=30 s) — matching models.tex's own worked
  estimate ("order 10 m of displacement over a 30 s powered ascent") almost exactly. The in-plane
  term is verified exactly zero at `χ=0°`/`180°` (`test_coriolis_inplane_zero_for_due_north_south_launch`),
  and the lateral diagnostic is verified *nonzero* there instead — the documented blind spot —
  per `test_coriolis_lateral_diagnostic_nonzero_at_the_blind_spot`.
- **Commit:** "Coriolis correction to the equations of motion (Option B: in-plane only + lateral diagnostic)"

**Not scheduled:** vertical wind (`main.tex` §Models > Wind > Vertical wind) — no theory found
that fits the current data pipeline (station soundings, no terrain/NWP source) without adding a
new data dependency; stays a documented `\todo`, not a step, until that changes.

---

## Phase 2.6 — Gravity direction, thrust misalignment, humid air (still 2D)

Three additive steps, designed in one derivation/spec pass after Phase 2.5 closed. Each promotes
a previously-deferred item to real physics; none changes the state vector, the solver, the events
or the module map; each has a `Params` default that reproduces every prior step **bit-for-bit**.
Same discipline as Phase 2.5 — one step, one commit, re-run the full regression suite after each.

Spec location, per step: `architecture.md` §23.1 / §23.2 / §23.3 (implementation) plus the named
LaTeX section (physics). **A developer needs only the one §23 subsection and the LaTeX section it
names** — not the whole of either document.

Same pass also restructured the LaTeX: `latex/sections/models.tex` is now ordered by force
(Gravity, Thrust, Mass, Aerodynamics, then Atmosphere, Wind, Relative wind, Non-inertial), and
§Analytical analysis moved out of `rocket-2d.tex` into its own `latex/sections/analysis.tex`
(label `sec:analysis` unchanged). Documentation only; no code implication.

### Step 38 — Non-parallel gravity: direction varying with downrange distance — done, commit `da77aa6`
- **Files:** `sim/gravity.py`, `sim/forces.py`, `sim/params.py`, `tests/test_gravity.py`,
  `tests/test_forces.py`
- **Spec:** `latex/sections/models.tex` §Gravity > Direction (the construction, `φ = x/R_e`, and
  the scope limits); `latex/sections/analysis.tex` §Forces for the body-axis reading
  (`θ → θ + φ`); `architecture.md` §23.1 for the code. Promotes Backlog **B4** and resolves
  `architecture.md` §22 item 7.
- **Do:** add a second dispatch seam to `sim/gravity.py` — `z_hat_g(t, y, p)` over
  `_GRAVITY_DIRECTIONS = {"parallel", "radial"}` — and make `forces.weight_inertial` return
  `m * gravity.g(t, s, p) * gravity.z_hat_g(t, s, p)`. `"radial"` returns
  `(-sin φ, cos φ)` with `φ = y[X]/p.R_e`. New field `gravity_direction: str = "parallel"`
  (a string, not a bool: this is a choice among named models behind one symbol, the §12 pattern —
  unlike `earth_rotation`, which is a single term switched on or off).
- **Scope, explicitly not in this step:** no change to the state or to what `x`/`z` mean; no
  curved ground and no curved-Earth impact event (`h = -z` stays measured from the launch-point
  tangent plane, which the true surface falls `x²/2R_e` below — 8 m at 10 km); and **no coupling
  to the Coriolis frame** — `sim/rotation.py` keeps its launch-site-fixed `Ω` decomposition. The
  resulting inconsistency is `O(Ω·x/R_e)`, a relative `3e-6` of the retained Coriolis term at
  10 km downrange (verified numerically). The two corrections stay independent and additive, as
  `models.tex` §Non-inertial's closing caveat now states.
- **Check:** `"parallel"` reproduces prior `derivatives()` output bit-for-bit. `"radial"`:
  `‖z_hat_g‖ = 1` for any `x`; exactly `(0.0, 1.0)` at `x = 0`; relative to `"parallel"` at the
  same state, `dvx/dt` shifts by exactly `-g·sin φ`, `dvz/dt` by `g·(cos φ − 1)`, and
  `domega/dt` by **exactly zero** (weight acts at the CoG — no moment, whatever direction it
  points). A level, downrange state gets a *retarding* downrange acceleration.
- **Commit:** "Non-parallel gravity: local vertical rotates with downrange distance"

### Step 39 — Thrust-axis misalignment (fixed nozzle cant) — done, commit `f3089aa`
- **Files:** `sim/forces.py`, `sim/params.py`, `tests/test_forces.py`, `tests/test_dynamics.py`
- **Spec:** `latex/sections/rocket-2d.tex` §Forces and moments (eq. `thrust_vector`);
  `latex/sections/analysis.tex` §Moment, §With thrust misaligned (eqs. `moment_full`,
  `moment_misaligned`, `alpha_trim`); `architecture.md` §23.2. Narrows `main.tex` §Backlog
  "Thrust-axis misalignment and control" to its control half.
- **Do:** `thrust_misalign_deg: float = 0.0` (degrees at the edge, radians inside — the
  `lat0_deg`/`azimuth_deg` convention; no separate on/off flag, same pattern as `A_e = 0.0`), and
  `thrust_body` returns `(T·cos δ, T·sin δ)` instead of `(T, 0)`.
- **`sim/dynamics.py` needs no change at all** — verified against the actual code, not assumed.
  `_cross_y(aB, thrust)` with `aB = (-(l1+l2), 0)` already yields `(l1+l2)·T·sin δ`, which is
  exactly `analysis.tex`'s `M_δ = (l_C − l_B)·T·sin δ`. This is what that function was written
  generically for (see its own Step-6 comment); only the comment needs updating. `dm/dt` is
  driven by the thrust *magnitude* and is likewise untouched.
- **Check:** `0.0` reproduces prior results bit-for-bit (`cos 0 = 1.0`, `sin 0 = 0.0` exactly).
  With `δ ≠ 0`: `M_y` shifts by exactly `(p.l1+p.l2)·T·sin δ`; the shift is **zero** once
  `T = 0` after burnout; the shift is independent of `α` (the static-stability derivative
  `∂θ̈/∂α` is unchanged by a constant `δ` — check at two angles of attack); a statically stable
  airframe settles at a small nonzero trim `α` of the sign of `M_δ` instead of diverging, and
  reversing `δ` mirrors it.
- **Commit:** "Thrust-axis misalignment: fixed nozzle cant and its pitching moment"

### Step 40 — Humid-air density (virtual temperature) in the measured tiers — done, commit `069abce`
- **Files:** `sim/soundings.py`, `sim/atmosphere.py`, `sim/params.py`, `tests/test_soundings.py`,
  `tests/test_atmosphere.py`, optionally one file under `data/soundings/`
- **Spec:** `latex/sections/models.tex` §Atmosphere > Density (eqs. `virtual_temperature`,
  `magnus`); `architecture.md` §23.3 for the column name, the loader change and the exact
  formulas. Resolves Backlog **B5**.
- **Do:** one new *optional* CSV column `Td_K` (dewpoint, kelvin — SI at rest in the repo, the
  same rule that converts `wdir`/`wspd` to ENU `u`/`v` at load time); `Sounding`,
  `SoundingState` and `ResampledCase` each gain a `Td`; `interp_altitude` interpolates it
  linearly in `h` and holds it at the edge outside the range, but keeps returning **dry** `rho`
  (it has no `Params` and must not grow one — `_resample_case` caches it). The correction is
  applied one level up, in `atmosphere.py`'s `_sounding_air_state`/`_field_air_state`, where
  `Params` is in scope: `rho = p/(R_d·T_v)` with `T_v` from `e = e_s(min(T_d, T))`. Gate:
  `humid_air: bool = False`.
- **Scope:** measured tiers only. **ISA is not touched** — it is *defined* as dry air of fixed
  composition, exactly the argument that keeps `g_isa = 9.80665` inside it regardless of the
  gravity model. `a` and `μ` stay dry-air quantities too (a consistent moist `a` needs the
  mixture's `γ`; the residual ~0.2 % is far below the aero table's own error).
- **Check:** `humid_air=False` reproduces prior results bit-for-bit. `e_s(0 °C) = 610.94 Pa`,
  `e_s(20 °C) = 2333.4 Pa` (0.4 % off the reference values — that is the Magnus fit's own
  accuracy, not a bug). `T_v ≥ T` always, so `rho_moist ≤ rho_dry` always; `T_d = T` gives the
  largest correction at that `(p,T)`; a very low dewpoint gives one tending to zero. Pinned
  values: `(T=287.3 K, T_d=283.15 K, p=96700 Pa)` → `T_v − T = 1.384 K`, `rho 1.17254 → 1.16692`
  (−0.479 %); `(303.15, 299.15, 101325)` → −1.252 %. A file with no `Td_K` column must load and
  run unchanged either way, and tier 3 with one station must still equal tier 2 exactly.
- **Gate:** the sounding file format was an approval-gated decision (`architecture.md` §22
  item 2); this extends it, so §22 item 10 records the extension.
- **Commit:** "Humid-air density: virtual-temperature correction in the sounding/field tiers"

---

## Phase 2.7 — Elliptical gravity, curved ground, lateral offsets, pitch damping (still 2D)

Four additive steps, designed in one spec pass after Phase 2.6 closed, from the LaTeX rewrite of
the same session. Same discipline as Phase 2.6 — one step, one commit, re-run the full regression
suite after each, and every new `Params` field defaults to reproducing the previous step
**bit-for-bit**. None changes the state vector, the solver or the module map; Step 42 is the only
one that touches `sim/integrate.py` at all.

Spec location, per step: `architecture.md` §24.1 / §24.2 / §24.3 / §24.4 (implementation) plus the
named LaTeX section (physics). **A developer needs only the one §24 subsection and the LaTeX
section it names** — not the whole of either document.

**LaTeX path changed:** `latex/sections/` no longer exists; the live files are
`latex/sections-ai/{rocket-2d,analysis,models}.tex`, wired in by `\input{sections-ai/...}`. Earlier
phases' citations to `latex/sections/...` mean the same content at the new path.

**Sign question resolved before Step 44 (user-approved 2026-09-27):** `analysis.tex` §Dynamic
stability originally gave the physical sign of `c_mq` in the textbook convention, inverted
relative to this project's own `A_m` sign (positive `C_m` = nose-down here, the same flip that
makes `c_mα > 0` the *stable* sign). The LaTeX was corrected to state **`c_mq > 0` is damping
here**, matching `architecture.md` §24.4's first-principles derivation, before Step 44's tests
were written.

### Step 41 — Elliptical gravity direction (ellipsoid normal via the osculating sphere) — done, commit `f5d0120`
- **Files:** `sim/gravity.py`, `sim/params.py`, `tests/test_gravity.py`, `tests/test_forces.py`
- **Spec:** `latex/sections-ai/models.tex` §Gravity > Direction, paragraph "Construction
  (elliptical)" (`R_χ`, `M(φ)`, `N(φ)`, and "every formula of the radial construction carries over
  with `R_e → R_χ`"); `architecture.md` §24.1 for the code. Builds directly on Step 38 (§23.1).
- **Do:** add a third value `"elliptical"` to `_GRAVITY_DIRECTIONS`, and a curvature-radius seam
  beside it: `_CURVATURE_RADII = {"parallel": None, "radial": p.R_e, "elliptical": _R_chi(p)}` with
  `curvature_radius(p)` as the public accessor. `_R_chi` is Euler/Meusnier,
  `R_χ = (cos²χ/M(φ₀) + sin²χ/N(φ₀))⁻¹`, **reusing `gravity.py`'s existing `_WGS84_A`/`_WGS84_E2`**
  — no second copy of those constants. Replace `_dir_radial` with one `_dir_curved(t, y, p)` used
  by both curved variants (`phi = y[X] / curvature_radius(p)`), which is the *same expression with
  the same operands* for `"radial"`, hence bit-for-bit.
- **No new `Params` fields.** `φ₀` and `χ` are `lat0_deg` and `azimuth_deg`, already in use for
  exactly these quantities (`lat0_deg` is the geodetic latitude of Somigliana's formula in
  `_g_wgs84`, on the *same* ellipsoid; `azimuth_deg` is the flight-plane heading read by
  `wind.py`, `soundings.py` and `rotation.py`). Two latitudes for one launch site would be a second
  source of truth, not a feature.
- **Scope, explicitly not in this step:** no curved ground (that is Step 42); no third-order
  ellipsoid fidelity (the osculating sphere is exact at `O*` and second-order nearby — `models.tex`
  itself calls the drift of `φ` with downrange distance "a refinement not carried here"); no
  Coriolis coupling (`sim/rotation.py` keeps its launch-site-fixed `Ω`, as in Step 38); no caching
  of `R_χ` (recomputed per RHS call like `_g_wgs84`'s Somigliana constants — `architecture.md` §15
  "do not optimise"); and **`p.R_e` is not read at all** by the elliptical direction.
- **Check:** `"parallel"` and `"radial"` both reproduce prior `derivatives()` output bit-for-bit.
  `R_χ(φ₀, 0°) == M(φ₀)` and `R_χ(φ₀, 90°) == N(φ₀)` exactly (pinned: `M(50°) = 6372955.9257`,
  `N(50°) = 6390702.0442`); `R_χ(90°, χ)` is azimuth-independent. `‖ẑ_g‖ = 1`, exactly `(0.0, 1.0)`
  at `x = 0`. Elliptical vs radial at `φ₀=50, χ=90, x=10 km`: `Δφ = 4.839e-6 rad`, and the downrange
  gravity component moves from `−1.539263e-2` to `−1.534518e-2 m/s²` (a 0.31 % refinement of a small
  term). `domega/dt` delta vs `"parallel"` is **exactly zero** (weight acts at the CoG). Sweeping
  `p.R_e` leaves an `"elliptical"` run unchanged. An unknown direction string raises `KeyError`.
- **Commit:** "Elliptical gravity direction: ellipsoid normal via the osculating sphere"

### Step 42 — Curved-ground impact condition (`h_true`) — done, commit `bdc7e07`
- **Files:** `sim/gravity.py`, `sim/integrate.py`, `tests/test_gravity.py`, `tests/test_integrate.py`
- **Spec:** `latex/sections-ai/models.tex` §Gravity > Direction, paragraph "Ground and impact
  condition", eq. `h_true`; `architecture.md` §24.2 for the code and the sign analysis. Promotes the
  *curved-ground remainder* Backlog **B4** explicitly left behind when Step 38 was taken out of it.
- **Depends on Step 41** — it consumes `curvature_radius(p)` and must handle `"elliptical"`.
- **Do:** add `gravity.ground_depth(t, y, p)` — the **negation** of `h_true`, i.e. signed depth
  below the ground, DOWN-positive: `z·cos φ − x·sin φ + R(1−cos φ)` with `φ = x/R`,
  `R = curvature_radius(p)`; and `return y[Z]` unchanged when `R is None` (`"parallel"`). Then
  `_ground_event` returns `ground_depth(...)` instead of `y[Z]`, and `_run_rk4`'s sign-change test
  and linear interpolation use it in place of `y[Z]`. **`_ground_event.terminal = True` and
  `.direction = 1` stay exactly as they are** — that is the whole point of negating `h_true`:
  `h_true` is up-positive and *falls* through zero at impact, so substituting it directly while
  leaving `direction = 1` in place would look for the rocket leaving the ground upward and never
  terminate.
- **The `"parallel"` branch is mandatory — the limit does not save you.** `h_true → −z` only as
  `R → ∞`; at the code's finite `p.R_e` the formula gives `+0.078481 m` at `x = 1 km`,
  `+1.660650 m` at `x = 4.6 km`, `+7.848057 m` at `x = 10 km`, `+70.632162 m` at `x = 30 km` for
  `z = 0`. `run.py`'s default is vertical (`x ≡ 0`, where `h_true(0,z) = −z` bitwise) and would pass
  anyway — a tilted scenario would not. Passing `float("inf")` as the radius is *not* a workaround:
  `inf * 0.0 = nan` in the `R(1−cos φ)` term. Branch on `R is None`.
- **`_apogee_event` is deliberately untouched** (`vz = 0`, `direction = 1`, `terminal = False`).
  With a curved ground, `dh_true/dt = vx(x cos φ + z sin φ)/R − vz cos φ`, which is `+0.47 m/s` at
  `vx = 300, x = 10 km` where `vz = 0` — the two apogee definitions differ by ~0.05 s and a
  second-order amount of altitude. "Apogee" in this simulator means the top of the launch-frame
  trajectory: that is what is plotted, reported and asserted everywhere. Mixing that redefinition
  into a step about the ground is exactly how the apogee/impact pair gets silently broken.
- **Scope, explicitly not in this step — the impact event ONLY.** `models.tex` says `h_true` should
  also replace `−z` in every altitude-dependent model (atmosphere, wind, radial/WGS84 `g`). That is
  deliberately deferred to Backlog **B8**, for three reasons: (1) nearly all the physics is in the
  event — at 10 km downrange and a 45° descent the ground drop adds ~7.85 m of range, whereas the
  same 7.85 m fed into the altitude lookups moves ISA density by ~0.09 % and radial `g` by
  `2.4e-6` relative, both far below the atmosphere model's own error; (2) `flow.altitude_agl(y)`
  takes no `Params`, so the swap is a signature change rippling through four modules and most of the
  suite, and it would make `_g_radial`/`_g_wgs84` read `p.gravity_direction` — collapsing the
  magnitude/direction orthogonality Step 38 was built to establish; (3) blast radius: 15 reviewable
  lines here versus a cross-cutting refactor of the most-called helper in the project. Also not in
  this step: any change to `_apogee_event`/`_burnout_event`, to plotting, or to `run.py`'s reported
  apogee altitude (still `−z`); and no terrain — "ground" is the smooth reference surface.
- **Check:** `"parallel"` reproduces prior `run_sim` output bit-for-bit on *both* integrator paths
  (`events`, `t`, `y`), **including a tilted scenario with `x ≠ 0` at impact** — the vertical default
  passes even with the bug, so the test must say so. For the curved variants: `ground_depth` is
  exactly `z` at `x = 0.0`; matches the pinned `−h_true` table above at 1/4.6/10/30 km; differs from
  the small-angle form `x²/2R − z` by the pinned `−6.164e-3 m` at `(x=10 km, z=−5000)` and
  `−0.664 m` at `x = 100 km` (which is itself the check that the *exact* form, not the
  approximation, was implemented). Assert `_ground_event.direction == 1` and `.terminal is True`
  directly, as a regression guard on this step's one real hazard. A tilted `"radial"` run impacts
  **later and further downrange** than the same tilted `"parallel"` run. `"radial"` and
  `"elliptical"` give different impact points at the same `lat0_deg`/`azimuth_deg`. RK4 and RK45
  agree on the curved impact time to grid resolution (Step 8's cross-check, extended).
- **Commit:** "Curved-ground impact condition: h_true replaces z=0 for the non-parallel variants"

### Step 43 — Lateral offsets `u_B`, `u_C` (off-axis CoG and nozzle) — done, commit `ad359eb`
- **Files:** `sim/dynamics.py`, `sim/params.py`, `tests/test_dynamics.py`
- **Spec:** `latex/sections-ai/analysis.tex` eq. `moment_full` and §Moment's term-by-term reading;
  `latex/sections-ai/rocket-2d.tex` §Geometry (`AB = −l_B x̂_r − u_B ẑ_r`, likewise `AC`,
  `u_D ≡ 0`); `architecture.md` §24.3 for the code and the algebra. Completes eq. `moment_full` —
  §23.2 recorded `(u_B−u_C)T cos δ` as "derived but with no code path", and status.json carries the
  same as a flagged item.
- **Do:** two new `Params` constants `u_B: float = 0.0`, `u_C: float = 0.0` (metres, positive
  towards `+ẑ_r`/the belly, as-built manufacturing quantities on the same footing as
  `thrust_misalign_deg`), and **two array literals** in `dynamics.derivatives()`:
  `aA = np.array([-l1_aero, p.u_B])` and `aB = np.array([-(p.l1 + p.l2), p.u_B - p.u_C])`. Nothing
  else. The generic `_cross_y` machinery then produces eq. `moment_full` exactly — verify the
  algebra before trusting it (§24.3 works it through; the mapping is `aA = BD`, `aB = BC`, with the
  code's `l1 = l_D − l_B` and `l1 + l2 = l_C − l_B`). The two missing terms land in *different*
  cross products — `(u_B−u_C)T cos δ` in `aB`'s and `−u_B A_x` in `aA`'s — which is why both
  literals change and why `u_B` appears twice with different companions.
- **Bit-for-bit:** `np.array([-l1_aero, 0.0])` and `0.0 - 0.0 == +0.0` exactly, so both arrays are
  bitwise the literals they replace. No gate flag needed (the `A_e = 0.0` pattern).
- **Scope, explicitly not in this step:** no effect on the translational equation (moment arms
  only — `dvx/dt`, `dvz/dt`, `dm/dt` unchanged at `t = 0`); `u_B` does **not** feed
  `_moment_of_inertia` or the two-lumped-mass model (which has no lateral coordinates to derive a
  `u_B(t)` from — the same precedent Step 36 set for `l1`/`l2`); `u_B`, `u_C` are constants, not
  `u(t)`; **no `u_D` field** (`u_D ≡ 0` by definition — surface asymmetry belongs in the
  coefficients); and no interaction with Step 25's CoP travel beyond what exists (`aA`'s axial
  component stays `aero.cop_l1(...)`, `aB`'s stays constant).
- **Check:** `u_B = u_C = 0.0` reproduces prior `derivatives()` bit-for-bit, including with a table
  CoP and with `thrust_misalign_deg ≠ 0`. `M_y` shifts by exactly
  `(u_B−u_C)·T·cos δ − u_B·A_x`. The two thrust terms collapse to the exact closed form
  `T·√((u_B−u_C)² + (l_C−l_B)²)·sin(δ + atan2(u_B−u_C, l_C−l_B))` (verified to `1.1e-16`) — so
  `1 mm` of offset over the `0.7 m` arm is exactly equivalent to a `0.08185°` cant, worth
  `0.150 N·m` at the placeholder motor's `T = 150 N` peak against `0.3665 N·m` for a `δ = 0.2°`
  cant. **With `u_B = u_C ≠ 0` the thrust term is exactly zero while `−u_B A_x` is not** — only the
  *difference* matters for thrust; that asymmetry is the sharpest test that the two fields were not
  conflated. At `α = 0, T = 0`: `M_y == −u_B·A_x` exactly, the only surviving term, and the only
  aerodynamic pitching moment that exists at zero angle of attack (it scales with `q`, so it is
  largest at max-Q, and unlike `M_δ` it does not vanish at burnout). A stable airframe with
  `u_B ≠ 0` trims at a small nonzero `α` rather than diverging; negating both offsets mirrors it.
- **Commit:** "Lateral offsets of the CoG and thrust point, and their pitching moments"

### Step 44 — Pitch-damping `c_mq` scaffold — done, commit `ff10242`
- **Files:** `sim/aero.py`, `sim/forces.py`, `sim/params.py`, `tests/test_aero.py`,
  `tests/test_forces.py`, `tests/test_dynamics.py`
- **Spec:** `latex/sections-ai/analysis.tex` §Dynamic stability (`sec:analysis_dynamic`):
  `c_m = c_{m,0} + α c_{m,α} + q̂ c_{m,q}` with `q̂ = ω d_ref/(2V)`; `architecture.md` §24.4 for the
  code, the `V = 0` analysis and **the sign resolution**. Narrows `main.tex` §Backlog's "dynamic
  stability analysis" item to its data half.
- **Gate:** `c_mq: float = 0.0`. Scaffold only, inert by default, no separate on/off flag — the
  `A_e`/`thrust_misalign_deg` pattern. **The user has no value or model for `c_mq`; supplying one is
  future work (Backlog B9), not this step.**
- **Do:** (a) `Params.c_mq: float = 0.0`; (b) an **optional** `c_mq` column in the `aero_table` CSV
  (`_AeroTable.C_mq` is `None` when absent, handled in `_load_table` only — the `Td_K` precedent);
  (c) a new public `aero.C_mq(alpha, M, p)` beside `C_A`/`C_N`/`C_m`/`cop_l1`, table-driven when a
  table *and* the column are present, else the constant `p.c_mq` — a deliberate, documented
  exception to the module's "table wins completely" rule, so a constant damping value can be tried
  against an existing table without regenerating a full `(M, α)` grid; (d) the term enters in
  `forces.aero_moment_y`'s `"coefficients"` branch (the `"constant"` branch is Phase 1's fixed
  `p.A_m` with no `q`/`V`/`ρ` in it and stays untouched), reusing **`p.d_ref`** — which already *is*
  the `d_ref` of `A_m = qS·d_ref·C_m` — and `s[OMEGA]`; `p.l_ref` is a different reference length
  (Reynolds only), do not use it. `dynamics.py` needs no change; verify that before starting, as
  Step 39 taught.
- **Write it division-free:** `A_m += 0.25*rho*V*S*d_ref**2*omega*C_mq`, which is algebraically
  `q·S·d_ref·q̂·c_mq` exactly. The `1/V` singularity is *removable* (`q ∝ V²`), but the naive
  two-step form is not numerically safe: at a denormal `V` (`1e-300`) `q` underflows to `0.0` while
  `q̂` overflows to `inf`, and `0.0 * inf = nan` kills the solver — and an unperturbed vertical
  flight coasts through `V ≈ 0` at apogee on every run (`aero.py`'s docstring already records one
  solver collapse from that exact neighbourhood, at Step 35).
- **SIGN — settle this before writing the tests.** `architecture.md` §24.4: in this project's
  convention **`c_mq > 0` is damping**, because positive `C_m` is a nose-*down* moment here (`−A_m`
  in eq. `moment_full`, `A_m = q c_m S d_ref`; the same flip that already makes `c_mα > 0` the
  statically stable sign, cf. eq. `static_margin`). `analysis.tex`'s "`c_{m,q}<0`" and its
  `α̈ + M_q α̇ − M_α α = 0` are written in the textbook convention and are inverted here; §24.4
  derives the correct sign three independent ways and proposes a three-symbol LaTeX fix. The
  *formula* is unaffected either way — only the documented sign of a real value, and the test.
- **Scope, explicitly not in this step:** no value for `c_mq` and no `c_mq` column in the shipped
  `data/aero/example.csv`; no second damping derivative `c_mα̇` (`analysis.tex` folds it in via the
  short-period `α̇ ≈ θ̇`); no `ω_n`/`ζ` reporting in `run.py`/`plotting.py`; no change to
  `dynamics.py` or to the existing four coefficients.
- **Check:** `c_mq = 0.0` and no column reproduce prior results bit-for-bit (including with a table
  configured; §24.4 traces the one signed-zero sub-case, which `np.array_equal` treats as equal and
  which cannot change an integrated state). An existing column-less table loads with
  `_AeroTable.C_mq is None` and runs unchanged. With a column, `C_mq` interpolates exactly like
  `C_m` and ignores `p.c_mq`; with none, it returns `p.c_mq` for every `(α, M)`. `A_m` shifts by
  exactly `0.25·ρ·V·S·d_ref²·ω·c_mq`; the shift is exactly `0.0` at `ω = 0` and at `V = 0`, is
  finite (`np.isfinite`) at `V = 1e-300`, is linear and **odd in `ω`**, and is independent of `α` at
  fixed `(V, ρ, ω)`. **The behaviour test that encodes the sign:** at the standard fixture
  (`I=0.05, l1=0.3, S=0.005, d_ref=0.08, C_N_alpha=2.0`; `ρ=1.225, V=100` ⇒ `q=6125 Pa`,
  `M_α = −367.5 s⁻²`, `ω_n = 19.1703 rad/s`, period `0.3278 s`), the strip estimate
  `c_mq = 2·C_Nα·(l1/d_ref)² = 56.25` gives `D = qS d_ref² c_mq/(2VI) = 1.1025 s⁻¹`, `ζ = 0.02876`,
  envelope `τ = 2/D = 1.8141 s`, amplitude `×0.8347` per period, and `ΔM_y = −5.5125e-2 N·m` at
  `ω = 1 rad/s`. Assert the triple: `c_mq > 0` ⇒ successive `|α|` peaks strictly **decrease**;
  `c_mq = 0` ⇒ the bounded, non-decaying oscillation documented since Step 25; `c_mq < 0` ⇒ growth.
  Getting that backwards is the only real risk in this step.
- **Commit:** "Pitch-damping derivative c_mq: scaffold, inert by default"

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

### Step 28 — Quaternion algebra
- **Files:** `sim/quaternion.py` (new), `tests/test_quaternion.py`
- **Do:** multiply, conjugate, normalise, rotate a vector, `from_euler` / `to_euler`,
  `q̇ = ½ q ⊗ ω`, and the 3×3 DCM.
- **Check:** round-trip `euler → q → euler`; a pitch-only quaternion reproduces the 2D
  `R_body_to_inertial` from Step 5 exactly. Pure algebra, no dynamics — fully testable alone.
- **Commit:** "Quaternion algebra"

### Step 29 — 3D state and translation
- **Files:** `sim/state3d.py`, `sim/dynamics3d.py`, `sim/forces3d.py`
- **Do:** 13-component state `[r(3), v(3), q(4), ω(3)]`. Translation only, attitude held fixed:
  `m·v̇ = W + R(q)·(T_body + A_body)` in NED — the same equation as Phase 1 with a 3×3 rotation.
- **Check:** planar initial conditions reproduce the Phase 1 trajectory to solver tolerance.
- **Commit:** "3D state vector and translational dynamics"

### Step 30 — 3D rotational dynamics
- **Files:** `sim/dynamics3d.py`
- **Do:** Euler's equations `ω̇ = I⁻¹(M − ω × I ω)` with the inertia tensor, plus `q̇` and
  renormalisation each step (or as a solver event).
- **Blocked on:** a `main.tex` extension of §Equations of motion to 3D (inertia tensor, the
  `ω × Iω` gyroscopic term).
- **Check:** with a body-symmetric rocket and planar initial conditions the Phase 1 pitch history
  is reproduced; `‖q‖ = 1` holds throughout; torque-free motion conserves angular momentum.
- **Commit:** "Full 6-DOF rotational dynamics"

### Step 31 — 3D aerodynamics
- **Files:** `sim/aero.py`, `sim/forces3d.py`
- **Do:** total angle of attack from the 3D relative wind, sideslip `β`, normal force in the
  correct plane, roll moment from fin cant, roll and pitch damping.
- **Check:** zero sideslip reproduces Step 30; fin cant produces a steady roll rate.
- **Commit:** "3D aerodynamics: sideslip, roll and damping"

### Step 32 — 3D output and regression
- **Files:** `sim/plotting.py`, `run.py`, `tests/`
- **Do:** 3D trajectory plot, ground track, Euler-angle time histories, and a regression test
  pinning the 2D-equivalent case.
- **Check:** the planar case still matches Phase 1. That single test is what keeps the 6-DOF code
  honest.
- **Commit:** "3D visualisation and 2D regression test"

---

## Backlog / later

Not scheduled, not designed further, not deleted. Each of these was deliberately pushed out of
Phase 2 — pick them up when the models above are in place and the user asks.

### B1 — Launch rail constraint  *(Step 16 in the old, pre-rewrite Phase 2 numbering)*
- **Files:** `sim/integrate.py`, `sim/dynamics.py`
- **Sketch:** while `‖r − r₀‖ < L_rail`, constrain motion to the rail direction and hold `θ`
  fixed (`ω = θ̈ = 0`); a rail-exit event switches to free flight. Matters more than it looks —
  rail-exit speed is what decides whether the wind model tips the rocket over.
- **Check:** rail-exit speed reported; `L_rail = 0` reproduces the unconstrained run.
- **Note:** this is the first Phase-2-adjacent feature that changes `dynamics.py` structurally
  (a constrained phase, not just a different force). Design it properly when it comes up.

### B2 — Recovery / parachute  *(Step 17 in the old, pre-rewrite Phase 2 numbering)*
- **Files:** `sim/forces.py`, `sim/integrate.py`
- **Sketch:** deployment triggered by the apogee event or a timer; drag swaps to
  `½ρV²·C_d·S_chute`, with attitude dynamics disabled or heavily damped under canopy.
- **Check:** descent settles at the analytic terminal velocity `√(2mg/ρC_dS)`.

### B3 — Gridded gravity data (EGM2008 / geoid)
A multi-MB coefficient set or a new geodesy dependency, to capture anomalies of order 10⁻⁴ g —
two orders of magnitude below the atmosphere model's own error. The `wgs84` variant of Step 11
already covers the latitude and altitude dependence. See `architecture.md` §13.

### B4 — Non-parallel gravity (direction varying with downrange distance) — **PROMOTED to Step 38**
Was blocked by `main.tex` §Current assumptions ("`ẑ_g` fixed for the whole flight"). The
derivation now exists (`latex/sections/models.tex` §Gravity > Direction) and the step is
specified in `architecture.md` §23.1. Still distinct from Step 37 (Coriolis): this is a static,
position-dependent effect on `ẑ_g`'s direction under a non-rotating Earth; Step 37 is a dynamic,
velocity-dependent fictitious force under a rotating one — and the two stay deliberately
independent. **The curved-ground remainder of this family is now PROMOTED to Step 42** (the impact
event), with the altitude-model half split off as **B8** below.

### B5 — Humidity / virtual temperature in the sounding tiers — **PROMOTED to Step 40**
Soundings carry dewpoint; moist air is ~1 % less dense than dry air at the same `p`, `T`.
Derived in `latex/sections/models.tex` §Atmosphere > Density, specified in `architecture.md`
§23.3 (optional `Td_K` column, `humid_air` gate, measured tiers only).

### B6 — Crosswind (out-of-plane) effects
Phase 2 discards the cross-plane wind component by construction (`architecture.md` §16); real
crosswind weathercocking needs the Phase 3 degrees of freedom.

### B7 — Vertical wind
`main.tex` §Models > Wind > Vertical wind: no theory found (terrain-slope orographic lift, thermal
parameterizations) that fits the current data pipeline (station soundings, no terrain/NWP source)
without adding a new data dependency. Revisit if/when such a source is added.

### B8 — `h_true` for the altitude-dependent models  *(split off from Step 42)*
`latex/sections-ai/models.tex` eq. `h_true` says the curved-ground altitude should replace `−z`
everywhere, not just in the impact event: the atmosphere and wind tiers, and the radial/WGS84
gravity *magnitudes*. Step 42 deliberately implements the event only (`architecture.md` §24.2
argues the scope call in full). What is left: `flow.altitude_agl(y)`/`altitude_msl(y, p)` would
have to become `Params`-aware, rippling through `gravity.py`, `atmosphere.py`, `wind.py`,
`soundings.py` and most of the test suite, and `_g_radial`/`_g_wgs84` would start reading
`p.gravity_direction` — collapsing the magnitude/direction orthogonality Step 38 established. The
physics at stake is small (at 10 km downrange the `+7.85 m` correction moves ISA density by
~0.09 % and radial `g` by `2.4e-6` relative), so this is a fidelity-completeness step, not a
correctness one. Design the `altitude_agl` signature change properly when it comes up.

### B9 — A real value or model for `c_mq`  *(unblocks Step 44's scaffold)*
Step 44 lands the pitch-damping term with a `0.0` default and an optional table column; it does not
supply a number. Getting one needs a forced-oscillation wind-tunnel test, an unsteady CFD run, or a
distributed strip integration over the real airframe. The single-lifting-surface estimate
`c_mq = 2·C_Nα·(l1/d_ref)²` (`architecture.md` §24.4, positive-is-damping in this project's
convention) is a test fixture and a sanity check, not a model to ship — it puts the whole normal
force at one point and ignores the body's own contribution and every unsteady effect. Also open in
the same family: `c_mα̇` (plunge damping), which `analysis.tex` folds into `c_mq` via the
short-period approximation `α̇ ≈ θ̇`, and reporting `ω_n`/`ζ` from `run.py`.

---

## Dependency summary

```
1 → 2 → 3 → 4 → 5 → 6 → 7 → [8]                              Phase 1 (all constants) — DONE
                            ↓
9 → 10 → 11 → 12 → 13 → 14 → [15] → 16                       Phase 2a: α, gravity, ISA, thrust
                                     ↓
                      17 → 18 → 19 → 20                      Phase 2b: atmosphere real data
                                     ↓
                      21 → 22 → 23 → [24] → 25 → [26] → 27   Phase 2c: wind, aero coeffs, sweeps
                                     ↓
                      33 → 34 → 35 → 36 → 37                 Phase 2.5: corrections/extensions
                                     ↓
                           38 · 39 · 40                      Phase 2.6: mutually independent — DONE
                                     ↓
                      41 → 42  ·  43  ·  44                  Phase 2.7: only 41→42 is a real dep
                                     ↓
                      28 → 29 → 30 → 31 → 32                 Phase 3 (6-DOF) — not worked on yet

Backlog (unscheduled): B1 launch rail · B2 recovery · B3 EGM gravity · B6 crosswind
                       B7 vertical wind (no fitting theory found)
                       B8 h_true for the altitude models · B9 a real c_mq value
Promoted out of the backlog: B4 → Step 38 (+ its curved-ground remainder → Step 42) · B5 → Step 40
```

Steps 38, 39 and 40 touch disjoint files (`gravity.py`+`forces.py` · `forces.py`+`params.py` ·
`soundings.py`+`atmosphere.py`) and are physically independent of one another, so their order is
free — but they are still **one step, one commit** each, and 38 and 39 both edit `forces.py`, so
they are not to be done simultaneously.

Phase 2.7 has exactly one real dependency: **42 needs 41** (it consumes `gravity.curvature_radius`
and must handle the `"elliptical"` value). 43 (`dynamics.py`) and 44 (`aero.py`+`forces.py`) are
independent of 41/42 and of each other and touch different regions, but every step in this project
edits `sim/params.py`, and the rule is **one step, one commit, full regression suite after each** —
so run them sequentially, 41 → 42 → 43 → 44, not concurrently.

Steps in `[brackets]` are optional or gated. Step 21 (analytic wind) depends only on Step 13 and
may be pulled forward. **Blocked or gated steps:**

| Step | Blocked on |
|---|---|
| 10-27 | `architecture.md` §22 items 1-4 approved by the user (selection pattern, data format, no pandas, no live API) |
| 16 | `main.tex` §Models > Thrust — the pressure-effect derivation is still a stub |
| 25 | the sign of `l₁` / static stability convention (`architecture.md` §22 item 5) |
| 30 | `main.tex` §Equations of motion extended to 3D (inertia tensor, `ω × Iω`) |
| 37 | ~~`main.tex` §Non-inertial frame corrections — the `Ω` tangent-plane projection~~ — **resolved**, derived in `models.tex`, step done |
| 40 | nothing technically, but the sounding-format extension (`Td_K`) touches an approval-gated decision — `architecture.md` §22 items 2 and 10 |
| 42 | Step 41 (needs `gravity.curvature_radius` and the `"elliptical"` value) |
| 44 | the `c_mq` **sign** question — `architecture.md` §24.4 resolves it (`c_mq > 0` is damping here) and proposes the `analysis.tex` correction; agree it before the tests are written |

Steps 38 and 39 are **not blocked**: both derivations now exist
(`latex/sections/models.tex` §Gravity > Direction, `latex/sections/analysis.tex` §With thrust,
misaligned) and both have a complete implementation spec in `architecture.md` §23.

Step 15 (the old "CoG doesn't change" blocker) is superseded by Step 36 — resolved, see
`architecture.md` §9 item 4 / §22 item 6.

# Rocket Trajectory Simulation — Project Status

## Summary
Personal-use rocket trajectory simulator, built from scratch in Python (no RocketPy).
Physics spec lives in `main.tex` (source of truth, updated by the user as derivations evolve).
Approach: incremental, step-by-step, one small piece at a time, committed individually.

- Phase 1: 2D planar rigid-body sim (translation + pitch rotation), all force/model parameters
  as constants (no real thrust curve, no wind, no varying atmosphere yet).
- Phase 2: replace constants with real models (thrust curve + mass depletion, atmosphere,
  wind, aerodynamic coefficients as functions).
- Phase 3: extend to 3D (full 6-DOF).

## Scope notes (per user)
- Single user, personal tool — no need for input validation/normalization, multi-user config, etc.
- Everything currently in `main.tex` should be reflected in code; models start as constants.
- Commit after every completed step (small, reviewable increments).

## Current stage
Phase 1, Step 5 — frames: body↔inertial rotation, 2D translation at fixed attitude.

## Completed steps
- Step 1 — scaffolding: `Params`/`State` containers, `run.py` prints them. Commit `4c3f836`.
- Step 2 — vertical point-mass flight under constant thrust + gravity (theta frozen at pi/2,
  no aero). Sign convention validated: apogee altitude/time match the analytic closed form
  (`a = T/m - g`) to ~1e-7 relative error. Introduced a temporary `T_BURN = 2.0s` constant in
  `sim/dynamics.py` (Step-2-only device, to be replaced by the real thrust curve in Step 11).
  Commit `2024207`.
- Step 3 — altitude and vertical-velocity plots vs. time (`sim/plotting.py`), sampled from the
  dense `solve_ivp` interpolant. `run.py` saves `output.png` (gitignored) and calls `plt.show()`.
  Trajectory shape confirmed numerically (monotonic climb, peak at apogee, monotonic descent to
  impact). Added `.gitignore` (pycache, generated PNGs). Commit `3c5f261`.
- Step 4 — `sim/forces.py` (weight_inertial, thrust_body, aero_force_body, aero_moment_y, per
  architecture.md's model-swap seam); `dynamics.py` refactored to build forces from it (rotation
  matrix at theta=pi/2 written inline, not yet in frames.py — that's Step 5). Constant axial drag
  `A_x` now lowers apogee (1650.70 m vs Step 3's 1839.43 m); regression-checked A_x=0 reproduces
  Step 3 exactly. Commit `68eb716`.

## Active modules
architect (done for now), developer (implementation, one roadmap step at a time). Everything
else (product, qa, security, documentation) — on hold, not needed for this scope unless it grows.

## Links
- `main.tex` — physics derivation (source of truth, user-maintained, re-check before every step)
- `architecture.md` — project structure + tech stack (approved)
- `roadmap.md` — step-by-step build plan, 22 steps across 3 phases (approved) — **this is the
  ticket list**, no separate task.md

## Decisions log
- 2026-09-19 — Architecture approved as recommended: z-down (NED-like) inertial frame,
  `scipy.integrate.solve_ivp` as integrator, fixed-signature `f(t, state, params)` seam for
  Phase 2 model swaps, quaternions for Phase 3 attitude, minimal pytest physics-sanity tests.
- 2026-09-19 — Physics confirmed by user: `ẑ_g` points down (`W = m·g·ẑ_g` correct as-is);
  positive `A_m` pitches the nose down (restoring/stabilizing moment).
- 2026-09-19 — CoG kept fixed for now (matches current `main.tex`); user will update `main.tex`
  with the CoG/inertia-shift derivation before Phase 2 Step 12 (propellant depletion).

## Known future main.tex updates needed (not blocking now)
- Aero force direction (`A_f`) is currently hard-coded against body axes — valid only nose-first;
  Step 9 (relative wind / angle of attack) needs a `main.tex` update to generalize this.
- CoG/inertia shift from propellant depletion — needed before Step 12.
- Thrust model (`§Models > Thrust`) is still a stub — needed before Steps 11/13.

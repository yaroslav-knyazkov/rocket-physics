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
Phase 1, Step 2 — vertical point mass under constant gravity + thrust.

## Completed steps
- Step 1 — scaffolding: `Params`/`State` containers, `run.py` prints them. Commit `4c3f836`.

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

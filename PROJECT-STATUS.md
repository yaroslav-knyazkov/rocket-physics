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
Phase 2, Step 18 — Atmosphere tier 2: single-station real data (Step 15, propellant depletion, is
optional and still blocked — see below)

## Gravity models complete (all 4 main.tex variants)
Step 10-11 finished all four gravity variants (constant/linear/radial/wgs84). Next steps move to
atmosphere.

## Phase 2 progress
- Step 9 — `sim/flow.py` (Flow: V, alpha, u_hat, n_hat; wind stubbed at zero until Step 21).
  `aero_force_body` now uses actual relative wind instead of fixed body axes. 13/13 tests passing
  (6 new). Ascent leg unchanged (apogee 1650.7038 m / 18.5071 s, exact match to Step 8). Impact
  time changed 35.9856s -> 37.8688s and max speed 188.88 -> 178.30 m/s — this is the intended
  physics fix: previously drag always added to the fall during descent (nose up, moving down);
  now it correctly opposes the actual relative wind and slows the fall, as roadmap Step 9 intended
  ("makes the descent leg physical for the first time"). Commit `79af229`.
- Step 10 — `sim/gravity.py`: constant/linear/radial models via `Params.gravity_model` string +
  dispatch dict (approved pattern). `Params` gains `gravity_model` (default "constant", preserves
  all behavior) and `R_e` (Earth radius, 6.371e6 m). 20/20 tests passing (7 new). Default-model
  regression exact match to Step 9. At current scenario altitude (~1650m) linear/radial differ
  from constant by ~0.39 m; at h=100km they diverge by ~7.5e-4 relative, as physically expected.
  Commit `1f8c641`.
- Step 11 — `sim/gravity.py`: 4th variant "wgs84" (Somigliana normal gravity + second-order
  free-air correction, standard published NIMA TR8350.2 constants). `Params` gains
  `lat0_deg`, `lon0_deg`, `h0_m`, `azimuth_deg` (site block, per architecture.md §18, safe
  defaults, no behavior change for other models). 26/26 tests passing. Spot-checks: equator
  9.7803253 m/s^2, pole 9.8321849 m/s^2 (both match published constants to 7 sig figs — the pole
  value is a derived cross-check, not an input, giving high confidence the formula is correct),
  45° mid-latitude 9.8061978 m/s^2, decreasing with altitude as expected. Commit `f53a0f8`.
- Step 12 — `sim/atmosphere.py`: full 7-layer ISA (troposphere through mesosphere), `AirState`
  (rho, p, T, a, mu). Fixed g_isa=9.80665 kept separate from the user's selected gravity model
  (correct per the standard's own definition). NOT yet wired into flow/forces/dynamics (that's
  Step 13). 36/36 tests passing. Sea-level values match standard reference exactly (rho=1.225,
  p=101325, T=288.15K, a=340.29 m/s, mu=1.789e-5 Pa*s); tropopause and 5000m checks correct.
  Commit `09950ce`.
- Step 13 — `sim/flow.py`, `sim/forces.py`, `sim/params.py`: Flow gains air, q=½ρV², M=V/a,
  Re=ρVl_ref/μ; added aero_model with "constant" and "coefficients" (A_x = qS·C_A0,
  A_z = qS·C_Nα·α, A_m = qS·d_ref·C_mα·α); added S, d_ref, l_ref, C_A0, C_N_alpha, C_m_alpha to
  Params. Verified that aero_model="constant" reproduces Step 12 exactly; with "coefficients"
  drag vanishes at V=0, reverses on descent and falls with altitude. Commit `9b558c1`.
- Step 14 — `sim/thrust_curve.py` (new): time/thrust table via `lru_cache`d loader + `np.interp`,
  zero after the last point. Removed the `T_BURN` constant-thrust hack from `sim/forces.py`
  entirely — `thrust_body` now calls `thrust_curve.thrust(t, s, p)`. Added `motor_curve: str = ""`
  to `Params` (default reproduces the "no thrust" case, matching every other Phase 2 field's
  Phase-1-preserving-default pattern; `run.py`'s scenario now sets `motor_curve="placeholder.csv"`
  explicitly, since the old `T=50.0` field is no longer read by `thrust_body` at all). Added a
  `burnout` event to both integrators in `sim/integrate.py` (`Result.events["burnout"]`), including
  a real scipy `solve_ivp` gotcha found and fixed along the way: an event function that stays
  *exactly* zero over an extended interval (post-burnout, or the whole flight with no curve) gets
  classified as both a rising and falling edge by scipy's `<=`/`>=` event logic, causing spurious
  detections at t=0; fixed with a tiny epsilon shift (`_BURNOUT_EPS = 1e-9` N) on the RK45 path
  only (the hand-written RK4 path does a direct numeric comparison and doesn't need it).
  `data/motors/placeholder.csv` is a small illustrative solid-motor-shaped curve (ignition spike to
  150N, settle to 90N, flat sustain, linear tail-off to 0 by t=2.0s; stated total impulse
  162.75 N·s, verified by `np.trapezoid` in `tests/test_thrust_curve.py`). 47/47 tests passing (4
  new thrust-curve tests + 3 new burnout-event tests in `tests/test_integrate.py`; `T_BURN`'s old
  regression test in `tests/test_dynamics.py` updated to use the new curve, since the field it used
  to set, `T`, is now inert). This step intentionally changes the trajectory versus Step 13 (a real
  motor curve replacing a fake constant-thrust rectangle is the point of the step) — there is no
  bit-for-bit regression claim here, unlike the gravity/atmosphere/aero model-selection steps.
  Commit `0d184bf`.
- Step 16 — `sim/thrust_curve.py`, `sim/params.py`: altitude pressure correction on top of the
  curve lookup, `T(t,h) = T_ref(t) + A_e*(p_ref - p_amb)` with `p_amb` from
  `atmosphere.air_state(t, s, p).p`. `Params` gains `A_e` (default 0.0, nozzle exit area) and
  `p_ref` (default 101325.0 Pa). The correction is guarded to only apply while `T_ref(t) > 0`
  (motor actually flowing) — otherwise `A_e*(p_ref - p_amb)` would manufacture nonzero thrust from
  ambient pressure alone during coast/pre-ignition, breaking the clean zero-after-burnout cutoff
  Step 14's burnout event depends on. `A_e = 0.0` (the default, used by `run.py`'s scenario)
  short-circuits before touching the atmosphere model at all, reproducing Step 14 bit-for-bit
  regardless of `p_ref` or `atmosphere_model` — confirmed via `run.py` (identical printed summary:
  burnout 2.0000s, apogee 4609.2267m/30.1209s, max speed 304.0110 m/s, impact 62.4745s). 50/50
  tests passing (3 new: inert-at-default, sign/magnitude-correct pressure boost mid-burn verified
  against the exact ISA sea-level pressure, still-zero after burnout with `A_e != 0`).
  Commit `0882da3`.
- Step 17 — `sim/soundings.py` (new): shared data layer for atmosphere tiers 2/3 AND wind tiers
  2/3 (no physics wired in yet — pure infrastructure). `Sounding` NamedTuple per architecture.md
  §17 (station/lat/lon/elev/time_utc + h/p/T arrays + u/v ENU wind components derived at load time
  from wdir/wspd via the standard meteorological convention). `load_case(case)` (`lru_cache`d,
  globs `data/soundings/<case>/*.csv`). `interp_altitude(sounding, h) -> SoundingState(p,T,rho,a,mu,u,v)`
  — the tier-2 (single-station) altitude-interpolation seam Steps 18/22 will call: T linear in h,
  p linear in ln(p), u/v linear in h, rho/a/mu derived (reusing `atmosphere.py`'s own physical
  constants, not duplicated). Below the lowest data point: continues with the sounding's own local
  lapse rate from its first two points (isothermal fallback for a degenerate single-row file).
  Above the highest data point: an ISA-*shaped* profile re-anchored at the sounding's own top point
  so T/p stay continuous at the seam (reuses `atmosphere.py`'s layer-crossing algorithm, walking
  forward from the new anchor rather than sea level). Worked example committed at
  `data/soundings/example/LKPR_202605011200.csv` (extends architecture.md §17's own literal LKPR
  example up through the tropopause, hand-crafted, ISA-like-but-not-identical — no live weather
  API, offline only). 62/62 tests passing (12 new): the roadmap's stated check (an ISA-derived
  synthetic sounding round-trips through the loader/interpolator to within 0.5% of
  `atmosphere.air_state` between its nodes), wind ENU conversion at the four cardinal directions,
  continuity at both extrapolation seams, physical sanity (finite, positive, monotone p/rho) well
  above the data range, the local-lapse-rate below-range behavior, the single-row degenerate case,
  and `load_case` caching/missing-case-error behavior. Commit `<pending>`.

## Step 15 — skipped for now (optional, still blocked)
Step 15 (propellant depletion / variable mass) is marked optional in the roadmap's dependency
graph and remains blocked: `main.tex` §Current assumptions still states "CoG doesn't change",
which directly contradicts a time-varying `I(t)`/`l1(t)`/`l2(t)`. Re-checked 2026-09-20 before
starting Step 16 — still unchanged. Proceeding straight to Step 16 (pressure correction), which
does not depend on Step 15. Revisit Step 15 if/when the user updates `main.tex` with the CoG/
inertia-shift derivation.

## Phase 2 scope (expanded per user request 2026-09-19)
- Gravity: constant, linear, radial (inverse-square), WGS84 real-data — selectable via
  `Params.gravity_model` string.
- Atmosphere: ISA / real single-station sounding / real multi-station spatially-interpolated —
  goal is rho, Reynolds number, Mach number.
- Wind: same three-tier structure (analytic / single-station / multi-station interpolated),
  sharing data infrastructure (`sim/soundings.py`) with atmosphere.
- Launch rail and recovery moved to a Backlog section (deferred, not deleted).
- `main.tex` updated (commit `9895505`) with relative-wind/AoA derivation and Gravity/Atmosphere/
  Wind model specs. `architecture.md`/`roadmap.md` revised for Phase 2 (commit `84b70f2`):
  Steps 9-27 + Backlog (B1-B6).

## Phase 2 decisions log (2026-09-19)
- Model selection: `Params` string field + dispatch dict per family (not pure §4 single-body
  seam, not strategy objects) — keeps one public function per family, makes model comparison
  trivial, self-documents in printed/CSV output.
- Real-data format: one unified sounding CSV per station/time (T, p, wind together), folder =
  "case" under `data/soundings/`. Shared loader/interpolator for atmosphere AND wind tiers 2-3.
- No pandas — `numpy.genfromtxt` + a small header parser. `requirements.txt` unchanged.
- No live weather API — manual CSV drop into `data/soundings/` for now. An optional offline
  fetch script (`tools/fetch_sounding.py`, stdlib urllib, no dependency) may be added later as
  its own approved step; `sim/` never touches the network.

## Known issue flagged by architect (not blocking yet)
Sign convention check needed before Step 25 (aero coefficients): per `main.tex`'s geometry
(`Aa = -l1*x_hat_r`), a normal aero force produces a **divergent** moment when `l1 > 0` — static
stability requires `l1 < 0` (CoP aft of CoG). The old roadmap had this backwards. Revisit before
Step 25.

## Milestone
All of `main.tex` (as of Step 6) is implemented in code: translation + rotation, all
forces/moments, everything as constants. Confirmed by 7 passing tests (frames, forces, and an
independent RK4-vs-RK45 cross-check) plus multiple regression checks across steps. Full 2D
trajectory + pitch plots and flight summary in place (Step 7). Two independent integrators
(scipy RK45 and a hand-written RK4) agree on the same physics (Step 8), proving `dynamics.py`
itself — not just the solver — is correct.

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
- Step 5 — `sim/frames.py` (R_body_to_inertial, to_inertial, to_body — the only trig in the
  codebase); `dynamics.py` refactored to use it instead of inline cos/sin. First tests added
  (`tests/test_frames.py`, 4 passing: identity at theta=0, nose-to-up at theta=pi/2, orthogonality,
  round-trip). `theta` still fixed (not yet integrated). Step 4 regression reproduced exactly;
  tilted trajectory (theta0=60°) demonstrated non-zero downrange motion (throwaway check, not
  committed to run.py). Commit `f794ec8`.
- Step 6 — rotational dynamics: `theta`/`omega` are now real integrated states, moment
  `M_y = cross_y(aB,T) + cross_y(aA,A_f) + A_m` about the CoG (cross products written explicitly,
  not pre-simplified, so a future gimbal/misalignment drops in cleanly). 2 new tests
  (`tests/test_forces.py`: thrust moment is exactly zero on-axis; moment matches closed form
  `l1*A_z - A_m` to 1e-12). Regression: theta stays exactly constant when A_z=A_m=0 (current
  placeholder), apogee/impact unchanged from Step 5. Demonstrated correct-direction pitch-over
  (positive A_m -> nose down) via throwaway check. Commit `d5226ac`.
- Step 7 — `plot_trajectory` (downrange vs altitude, equal aspect) and extended
  `plot_time_histories` (2x2: altitude, speed, pitch deg, pitch-rate deg/s) added to
  `sim/plotting.py`. `run.py` prints a full flight summary (apogee altitude/time, max speed,
  impact time, downrange at impact) and saves `trajectory.png`, `time_histories.png`,
  `trajectory.csv` (all gitignored). With current placeholder (vertical launch, A_z=0):
  downrange at impact = 0 m, as expected. Commit `81615c6`.
- Step 8 — hand-written fixed-step RK4 integrator (`method="rk4"` in `run_sim`), independent of
  `scipy.integrate.solve_ivp`. Cross-check test confirms RK4 and RK45 agree on apogee
  altitude/time and impact time to well within grid-resolution tolerance (apogee time diff
  ~2e-4 s, impact time diff ~4e-4 s, apogee altitude diff ~0.036 m at dt=1e-4s) — proves
  `dynamics.py` itself is correct, independent of which integrator drives it. RK45 remains the
  default; `run.py`'s output is byte-for-byte unchanged. Commit `53a3894`.

## Phase 1 — closed out
8/8 steps done. Everything currently in `main.tex` is implemented, tested, plotted. Next: Phase 2
(Steps 9-17), replacing constants with real models one at a time.

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
